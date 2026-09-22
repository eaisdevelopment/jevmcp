#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "tree-sitter>=0.25",
#   "tree-sitter-java>=0.23",
#   "tree-sitter-javascript>=0.23",
#   "tree-sitter-typescript>=0.23",
#   "pyyaml>=6.0",
# ]
# ///
"""docdrift as an MCP server: the same spec-drift checks as docdrift.py, as tools a coding
agent calls (Claude Code, or any MCP client).

Why a server when the command line exists:
  * It keeps the parsed code in memory. After an edit only the changed files are parsed
    again: a 16,000-file repository re-indexes in ~2 s instead of ~20 s.
  * It returns the results as text written for the agent - DRIFT first, "review" sorted by
    how likely the drift is, "??" called out as not a pass - instead of console output.
  * The TypeSafe key stays in this process. The agent calls a tool; it never reads, passes
    or prints the key.

The checks, thresholds and redaction are docdrift.py's own (this file imports it), so the
command line and the server always judge the same way.

Works in any project: it serves the project it is started in (the client's working folder,
or CLAUDE_PROJECT_DIR), finds the project's spec map (any file named *spec_map.json) on its
own, and a project without one can draft it with the draft_map tool.

Speaks MCP over stdio (newline-delimited JSON-RPC 2.0) with no dependencies beyond
docdrift's. The plugin packages register it for you and keep the key in the client's own
settings. To register it by hand instead, e.g. in Claude Code:

  claude mcp add --scope user docdrift -- uv run --script /path/to/docdrift_mcp.py --key-file ~/.config/typesafe.env

where that file holds the line TYPESAFE_API_KEY=... and only you can read it (chmod 600).
Never put the key itself on a command line or in a settings file.

Closing its input ends the session (the stdio transport's shutdown signal): a request not yet
answered is dropped, so a client keeps stdin open until it has read the replies.

Run it by hand to see the options:  uv run --script docdrift_mcp.py --help
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import queue
import shutil
import signal
import sys
import tempfile
import threading
import time
import traceback
from collections import deque
from pathlib import Path

# The protocol owns stdout. Anything else that prints - docdrift's notes, a library
# warning - goes to stderr, which Claude Code keeps in its MCP log.
_PROTOCOL_OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n", write_through=True)
try:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass
sys.stdout = sys.stderr

sys.dont_write_bytecode = True                     # never leave a .pyc inside an installed plugin
sys.path.insert(0, str(Path(__file__).resolve().parent))
import docdrift as dd  # noqa: E402

VERSION = "1.0.0"

# MCP 2026-07-28 is stateless: every request carries its protocol version and the client's
# capabilities in _meta, and there is no initialize handshake. Clients of earlier revisions
# still open with initialize; this server is "dual-era" and serves both on one stdio process.
MODERN_VERSIONS = ("2026-07-28",)
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")    # need initialize
SUPPORTED_VERSIONS = MODERN_VERSIONS + LEGACY_VERSIONS                         # newest first
M = "io.modelcontextprotocol/"                     # reserved _meta prefix
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
UNSUPPORTED_PROTOCOL_VERSION = -32022
LIST_TTL_MS = 3_600_000                            # the tool list never changes while the server runs
SERVER_INFO = {"name": "docdrift", "title": "docdrift", "version": VERSION,
               "description": "Checks code against its design spec: TypeSafe's fast model screens every "
                              "requirement, the agent investigates only what it flags."}
CAPABILITIES = {"tools": {"listChanged": False}}

INSTRUCTIONS = """\
docdrift checks code against its design spec. A fast model (TypeSafe's Jev) screens every
claim in the spec map and labels it; spend your effort only on what it flags.
- No spec map in the project yet: draft_map, then review every entry before checking.
- check_drift after changing code (default: claims about the files git reports as changed);
  all=true for a full check. Labels: DRIFT = investigate each one; review = sorted by
  P(drifted), investigate from 0.3 up; ?? = NOT a pass (the code shown cannot settle the
  claim - fix the map entry); ok = spot-check a couple.
- validate_map after editing the spec or the map (free, sends nothing).
- show_payload to see exactly what would be sent for some claims (free).
Never pass or ask for the API key; the server holds it."""

TOOLS = [
    {
        "name": "check_drift",
        "title": "Check code against the spec",
        # Not read-only: it sends the spec sentences and the paired code to TypeSafe, and sending
        # data out of the user's machine is a write action (OpenAI app guidelines).
        "annotations": {"title": "Check code against the spec", "readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": True},
        "description": (
            "Check code against the spec with TypeSafe's fast model and return the results, most "
            "important first: DRIFT, then 'review' sorted by P(drifted), then '??' (not a pass), then "
            "a count of 'ok'. By default only claims about the files git reports as changed are "
            "checked (a few seconds, fractions of a cent). Sends the spec sentence and the paired code "
            "(comments removed, secrets redacted) to TypeSafe."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "files": {"type": "array", "items": {"type": "string"},
                          "description": "Check only claims about these files (paths relative to the "
                                         "project). Leave out to use the files git reports as changed."},
                "all": {"type": "boolean",
                        "description": "Check every claim in the map - a full check. Default false."},
                "map": {"type": "string",
                        "description": "The spec map to use, relative to the project. Leave out: the "
                                       "project's only *spec_map.json is found automatically."},
                "project": {"type": "string",
                            "description": "Absolute path of the project folder - your working directory. "
                                           "Needed when the client does not tell the server which project "
                                           "it is in (Codex); harmless otherwise."},
            },
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"}, "map": {"type": "string"},
                "claims_in_map": {"type": "integer"}, "claims_selected": {"type": "integer"},
                "checked": {"type": "integer"},
                "counts": {"type": "object", "properties": {k: {"type": "integer"} for k in ("DRIFT", "review", "??", "ok")},
                           "required": ["DRIFT", "review", "??", "ok"]},
                "cost_usd": {"type": "number"},
                "complete": {"type": "boolean", "description": "every selected claim was checked"},
                "results_file": {"type": ["string", "null"], "description": "full results, with the exact code sent"},
                "map_problems": {"type": "array", "items": {"type": "string"}},
                "not_checked": {"type": "array", "items": {"type": "string"}},
                "flagged": {"type": "array", "description": "DRIFT, then review by P(drifted), then ??",
                            "items": {"type": "object", "properties": {
                    "label": {"type": "string", "enum": ["DRIFT", "review", "??"]},
                    "doc": {"type": "string"}, "line": {"type": "integer"}, "claim": {"type": "string"},
                    "p_drifted": {"type": "number"}, "severity": {"type": "number"},
                    "value_mismatch": {"type": ["number", "null"]},
                    "code_refs": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}},
                    "required": ["label", "doc", "line", "claim", "p_drifted", "code_refs", "why"]}},
            },
            "required": ["project", "map", "claims_in_map", "claims_selected", "checked", "counts", "cost_usd",
                         "complete", "results_file", "map_problems", "not_checked", "flagged"],
        },
    },
    {
        "name": "validate_map",
        "title": "Validate the spec map",
        "annotations": {"title": "Validate the spec map", "readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "description": (
            "Check that the spec map still fits the spec and the code - every reference resolves, "
            "nothing is stale, and (strict, the default) every spec sentence is either mapped or "
            "marked excluded with a reason. Free: sends nothing. Run after editing the spec or the map."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "strict": {"type": "boolean",
                           "description": "Also report unmapped sentences, unreviewed entries, "
                                          "exclusions without a 'why'. Default true."},
                "map": {"type": "string",
                        "description": "The spec map to use, relative to the project. Leave out: the "
                                       "project's only *spec_map.json is found automatically."},
                "project": {"type": "string",
                            "description": "Absolute path of the project folder - your working directory. "
                                           "Needed when the client does not tell the server which project "
                                           "it is in (Codex); harmless otherwise."},
            },
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"}, "map": {"type": "string"},
                "ready": {"type": "boolean", "description": "no problems: the map can be checked"},
                "entries_to_check": {"type": "integer"}, "excluded": {"type": "integer"},
                "full_check_cost_usd": {"type": "number"},
                "problems": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["project", "map", "ready", "entries_to_check", "excluded", "full_check_cost_usd",
                         "problems", "notes"],
        },
    },
    {
        "name": "show_payload",
        "title": "Show what a check would send",
        "annotations": {"title": "Show what a check would send", "readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "description": (
            "Show exactly what check_drift would send to TypeSafe for some claims: the sentence, the "
            "code with comments removed and secrets redacted, any computed values, and the 3 fixed "
            "questions. Free: sends nothing."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "files": {"type": "array", "items": {"type": "string"},
                          "description": "Claims about these files. Leave out (and leave out 'line') "
                                         "for the files git reports as changed."},
                "line": {"type": "integer",
                         "description": "Only the claim(s) from this line of the spec."},
                "map": {"type": "string",
                        "description": "The spec map to use, relative to the project. Leave out: the "
                                       "project's only *spec_map.json is found automatically."},
                "project": {"type": "string",
                            "description": "Absolute path of the project folder - your working directory. "
                                           "Needed when the client does not tell the server which project "
                                           "it is in (Codex); harmless otherwise."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "draft_map",
        "title": "Draft a spec map",
        "annotations": {"title": "Draft a spec map", "readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
        "description": (
            "Set up a project that has no spec map yet: suggest a code location for every sentence of the "
            "spec(s) and write them to a new map file for review. Every entry must then be reviewed - point "
            "'code' at what enforces the sentence and set status 'reviewed', or set status 'excluded' with a "
            "'why' - before check_drift is worth running. Free: sends nothing. Never overwrites a file."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "docs": {"type": "array", "items": {"type": "string"},
                         "description": "The spec file(s) or folder(s), relative to the project."},
                "out": {"type": "string",
                        "description": "The new map file, relative to the project - usually next to the "
                                       "spec, named spec_map.json."},
                "project": {"type": "string",
                            "description": "Absolute path of the project folder - your working directory. "
                                           "Needed when the client does not tell the server which project "
                                           "it is in (Codex); harmless otherwise."},
            },
            "required": ["docs", "out"],
            "additionalProperties": False,
        },
    },
]


KEY_FILE_NAME = "typesafe.env"


def _plugin_data_dir() -> Path | None:
    """The plugin's data folder, which Agent Plugins clients create and pass to the server
    (PLUGIN_DATA; Claude Code: CLAUDE_PLUGIN_DATA). It survives plugin updates."""
    for var in ("PLUGIN_DATA", "CLAUDE_PLUGIN_DATA"):
        if os.environ.get(var):
            return Path(os.environ[var])
    return None


def _plugin_data_key_file() -> str | None:
    """The portable place for the key: Agent Plugins forbids secrets in a server's env, so a
    client with no secret mechanism of its own has the user put it in the plugin's data folder.
    Used only when TYPESAFE_API_KEY is not already in the environment."""
    if os.environ.get("TYPESAFE_API_KEY"):
        return None
    folder = _plugin_data_dir()
    return str(folder / KEY_FILE_NAME) if folder and (folder / KEY_FILE_NAME).is_file() else None


class ToolError(Exception):
    """A problem the agent should see and act on (bad map, no key, a wrong argument): reported
    as a tool result with isError, so the model can read it and correct itself."""


class ProtocolError(Exception):
    """A malformed or unsupported request: reported as a JSON-RPC error."""
    def __init__(self, code: int, message: str, data: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


class Server:
    def __init__(self, root: Path | None, map_path: str | None, key_file: str | None, jobs: int,
                 ignore: tuple[str, ...], max_checks_per_minute: int = 20, max_calls_per_minute: int = 120):
        """`root` is the project the client started us in, or None when it did not say (Codex
        starts plugin servers in the plugin's own folder): then each call must pass `project`."""
        self.default_root, self.map_path, self.key_file, self.jobs, self.ignore = root, map_path, key_file, jobs, ignore
        self.root = root
        self.map_used = map_path or ""
        self.caches: dict[Path, dict] = {}    # one parsed index per project
        self.cache: dict = {}
        self.lock = threading.Lock()          # docdrift's index lives in module globals: one user at a time
        self.last_index = ""
        self.legacy_version: str | None = None    # set by initialize: this process then also speaks legacy MCP
        self.max_checks = max_checks_per_minute   # each check spends TypeSafe credits; 0 = no limit
        self.check_times: deque[float] = deque()
        self.max_calls = max_calls_per_minute     # every tool call (each may re-read a large project)
        self.call_times: deque[float] = deque()
        self.subscriptions: set = set()           # open subscriptions/listen requests (nothing is ever sent on them)
        self._progress_lock = threading.Lock()
        self._last_done = -1
        self.state = threading.Lock()             # guards the request bookkeeping below
        self.pending: set = set()                 # request ids read but not answered yet
        self.cancelled: set = set()               # of those, the ones the client cancelled
        self.current_id = None
        self.current_cancel = threading.Event()
        self.progress_token = None
        self._last_progress = 0.0
        self._results_dir: Path | None = None
        self.closed = False                       # the client closed our input: shutting down

    # ── request bookkeeping: cancellation and progress (MCP message patterns) ──
    def received(self, request_id) -> None:
        with self.state:
            self.pending.add(request_id)

    def cancel(self, request_id, reason: str = "") -> None:
        """notifications/cancelled: stop that request if it is queued or running; ignore otherwise."""
        with self.state:
            if request_id not in self.pending:
                return                            # unknown, or already answered: ignore, as the spec says
            self.cancelled.add(request_id)
            if request_id == self.current_id:
                self.current_cancel.set()
                self.progress_token = None        # no further messages for a cancelled request
        print(f"docdrift-mcp: request {request_id!r} cancelled" + (f": {reason}" if reason else ""), file=sys.stderr)

    def shutdown(self) -> None:
        """The client closed our input: stop the running request and never start a queued one."""
        with self.state:
            self.closed = True
            self.cancelled |= self.pending
            self.current_cancel.set()
            self.progress_token = None

    def begin(self, request_id, progress_token=None) -> bool:
        """Start a request; False if the client cancelled it while it was queued."""
        with self.state:
            if request_id in self.cancelled:
                return False
            self.current_id, self.progress_token, self._last_progress = request_id, progress_token, 0.0
            self._last_done = -1
            self.current_cancel = threading.Event()
            return True

    def finish(self, request_id) -> bool:
        """End a request; True if its response must not be sent (it was cancelled)."""
        with self.state:
            self.pending.discard(request_id)
            dropped = request_id in self.cancelled
            self.cancelled.discard(request_id)
            if self.current_id == request_id:
                self.current_id, self.progress_token = None, None
            return dropped

    def progress(self, done: int, total: int) -> None:
        """notifications/progress for the running request, at most twice a second."""
        with self._progress_lock:                 # called from worker threads: keep it ordered
            token = None if self.current_cancel.is_set() else self.progress_token
            now = time.monotonic()
            if (token is None or done <= self._last_done
                    or (done < total and now - self._last_progress < 0.5)):
                return
            self._last_progress, self._last_done = now, done
            _send({"jsonrpc": "2.0", "method": "notifications/progress",
                   "params": {"progressToken": token, "progress": done, "total": total,
                              "message": f"{done} of {total} claims checked"}})

    def results_file(self) -> Path:
        """Where the last check's full results go (they include the code sent): a private
        folder of this process (0700), a file per project (0600)."""
        if self._results_dir is None:
            self._results_dir = Path(tempfile.mkdtemp(prefix="docdrift-mcp-"))
        tag = hashlib.sha256(str(self.root).encode()).hexdigest()[:8]
        return self._results_dir / f"last-check-{self.root.name}-{tag}.json"

    def cleanup(self) -> None:
        """Remove this process's results folder (it holds the code that was sent)."""
        if self._results_dir is not None:
            shutil.rmtree(self._results_dir, ignore_errors=True)
            self._results_dir = None

    def use_project(self, project: str | None) -> None:
        """Point the server at the project for this call: the one named, else the client's."""
        if project:
            p = Path(project).expanduser()
            if not p.is_absolute():
                raise ToolError(f"project must be an absolute path (got {project!r}) - your working directory")
            p = p.resolve()
            if not p.is_dir():
                raise ToolError(f"project folder not found: {project}")
            if self.default_root is not None and not p.is_relative_to(self.default_root):
                raise ToolError(f"project {p} is outside the project this server was started for "
                                f"({self.default_root}) - refused")
        elif self.default_root is not None:
            p = self.default_root
        else:
            raise ToolError("this client did not tell the server which project it is working in - pass "
                            "project: the absolute path of the project folder (your working directory).")
        if p in (Path.home().resolve(), Path(p.anchor)):
            raise ToolError(f"{p} is a home or root folder, not a project - pass the project's own folder "
                            f"as project.")
        self.root = p
        self.cache = self.caches.setdefault(p, {})

    # ── the index, kept warm ────────────────────────────────────────────────
    def index(self) -> dict:
        before = {k: id(v) for k, v in self.cache.items() if k != "_files"}
        t = time.perf_counter()
        syms, counts = dd.index_code(Path("."), self.ignore, self.cache)
        dt = time.perf_counter() - t
        parsed = sum(1 for k, v in self.cache.items() if k != "_files" and before.get(k) != id(v))
        state = "cold" if not before else "warm"
        self.last_index = (f"index {dt:.2f}s ({state}: {parsed} of {len(self.cache) - 1} files parsed"
                           f"{'' if state == 'cold' else ' again'})")
        return syms

    def find_maps(self, depth: int = 5) -> list[str]:
        """Spec maps in the project (*spec_map.json), a few folders deep, skipping ignored folders."""
        found, ign = [], set(self.ignore)
        for dirpath, dirnames, filenames in os.walk("."):
            level = 0 if dirpath == "." else dirpath.count(os.sep)
            dirnames[:] = sorted(d for d in dirnames if d not in ign and not d.startswith(".")) if level < depth else []
            found += [os.path.normpath(os.path.join(dirpath, f)) for f in sorted(filenames) if f.endswith("spec_map.json")]
        return found

    def warm(self) -> None:
        if self.default_root is None or self.default_root in (Path.home().resolve(), Path(self.default_root.anchor)):
            return                                # no project known yet, or not a project folder
        self.use_project(None)
        with self.lock, _in(self.root), contextlib.redirect_stdout(io.StringIO()):
            try:
                if not (self.map_path or self.find_maps()):
                    return                        # not a project with a spec map: stay idle
                self.index()
            except Exception as e:  # noqa: BLE001 - the first tool call will report it properly
                print(f"docdrift-mcp: warm-up failed: {e}", file=sys.stderr)

    # ── shared steps ────────────────────────────────────────────────────────
    def resolve_map(self, map: str | None) -> str:
        """The map to use: the one asked for, the server's --map, or the project's only map."""
        chosen = map or self.map_path
        if not chosen:
            maps = self.find_maps()
            if not maps:
                raise ToolError(f"this project ({self.root}) has no spec map yet (no *spec_map.json). Set one up: "
                                f"draft_map with the spec file(s), then review every entry.")
            if len(maps) > 1:
                raise ToolError("this project has several spec maps - say which one with 'map': " + ", ".join(maps))
            chosen = maps[0]
        path = (self.root / chosen).resolve()
        if not path.is_relative_to(self.root):
            raise ToolError(f"{chosen} is outside the project - refused")
        if not path.is_file():
            raise ToolError(f"map file not found: {chosen} (relative to {self.root})")
        self.map_used = os.path.relpath(path, self.root)
        return self.map_used

    def claims(self, syms: dict, problems: list[str], map: str | None = None) -> list:
        return dd.claims_from_map(Path(self.resolve_map(map)), syms, src=Path("."), problems=problems)

    def select(self, claims: list, files: list[str] | None) -> tuple[list, str]:
        changed = dd._changed_files(files or [], Path("."))
        picked = [c for c in claims if dd._touches(c, changed)]
        where = (f"{len(changed)} file(s) named" if files else f"{len(changed)} file(s) git reports as changed")
        return picked, where

    # ── tools ───────────────────────────────────────────────────────────────
    def check_drift(self, files: list[str] | None = None, all: bool = False,
                    map: str | None = None) -> tuple[str, bool]:
        problems: list[str] = []
        self.resolve_map(map)                     # a project without a map: say so before reading the code
        syms = self.index()
        claims = self.claims(syms, problems, map)
        total = len(claims)
        scope = f"all {total} claims in the map"
        if not all:
            claims, where = self.select(claims, files)
            scope = f"{len(claims)} of {total} claims, about {where}"
        head = [f"docdrift check ({self.map_used}): {scope} | {self.last_index}"]
        if problems:
            head += ["", "MAP PROBLEMS - these entries were NOT checked (fix the map, then validate_map):"]
            head += [f"  - {p}" for p in problems]
        structured = {"summary": head[0], "project": str(self.root), "map": self.map_used, "claims_in_map": total,
                      "claims_selected": len(claims), "checked": 0,
                      "counts": {"DRIFT": 0, "review": 0, "??": 0, "ok": 0}, "cost_usd": 0.0,
                      "complete": not problems, "results_file": None, "map_problems": problems,
                      "not_checked": [], "flagged": []}
        if not claims:
            head.append("nothing to check" + ("" if all else " - no claim in the map is about those files. "
                                              "Use all=true for a full check."))
            return "\n".join(head), False, structured
        key_file = self.key_file or _plugin_data_key_file()
        try:
            key = dd._load_key(key_file, dotenv=False)          # never a key the project supplies
        except dd.Stop:
            where = _plugin_data_dir()
            raise ToolError("No TypeSafe API key is configured for this MCP server, so nothing was sent. Do not ask "
                            "for the key in chat. Tell the user to set it in the plugin's settings (Claude Code asks "
                            "when the plugin is enabled), or to export TYPESAFE_API_KEY in the environment that starts "
                            "the agent" + (f", or to put the line TYPESAFE_API_KEY=... into {where / KEY_FILE_NAME}"
                                           if where else "") + ". validate_map and show_payload work without a key."
                            ) from None
        self.rate_limit()
        t = time.perf_counter()
        results, tokens, stopped, failed = dd.check_claims(claims, key, self.jobs, show=lambda _: None,
                                                           on_answer=self.progress,
                                                           cancelled=self.current_cancel.is_set)
        out = self.results_file()
        out.touch(mode=0o600)
        out.write_text(json.dumps(results, indent=1, ensure_ascii=False))
        head[0] += f" | checked {len(results)} in {time.perf_counter() - t:.1f}s | ${tokens * 0.042 / 1e6:.4f}"
        text = "\n".join(head + [""] + _report(results, str(out)))
        if stopped or failed:
            text += "\n\nINCOMPLETE - not everything was checked:\n" + "\n".join(f"  - {p}" for p in stopped + failed)
            if failed and not stopped:
                text += "\n  (TypeSafe could not be used - not a problem with the code. Carry on without it.)"
        structured.update(
            checked=len(results), cost_usd=round(tokens * 0.042 / 1e6, 6), results_file=str(out),
            counts={k: sum(1 for r in results if r["label"] == k) for k in ("DRIFT", "review", "??", "ok")},
            complete=not (problems or stopped or failed), not_checked=stopped + failed,
            flagged=[{"label": r["label"], "doc": r["doc"], "line": r["line"], "claim": r["claim"],
                      "p_drifted": r["probabilities"].get("drifted", 0.0), "severity": r["severity"],
                      "value_mismatch": r.get("value_mismatch"), "code_refs": r["code_refs"], "why": r["why"]}
                     for r in _in_triage_order(results) if r["label"] != "ok"])
        structured["summary"] = text.split("\n", 1)[0] + (" - DRIFT: investigate each; review: from p_drifted 0.3 up; "
                                                            "??: NOT a pass, fix the map entry; full results in "
                                                            "results_file")
        return text, bool(stopped) or (bool(failed) and not results), structured

    def rate_limit(self) -> None:
        """Tool invocations must be rate limited (MCP tools, security). A check spends TypeSafe
        credits, so a runaway loop is stopped here, with a message the model can act on."""
        if not self.max_checks:
            return
        now = time.monotonic()
        while self.check_times and now - self.check_times[0] > 60:
            self.check_times.popleft()
        if len(self.check_times) >= self.max_checks:
            wait = 60 - (now - self.check_times[0])
            raise ToolError(f"rate limit: at most {self.max_checks} checks a minute (each one spends TypeSafe "
                            f"credits). Try again in {wait:.0f} s, or check more files in one call.")
        self.check_times.append(now)

    def validate_map(self, strict: bool = True, map: str | None = None) -> tuple[str, bool]:
        problems: list[str] = []
        self.resolve_map(map)
        syms = self.index()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            claims = self.claims(syms, problems, map)
        if strict:
            problems += [f"{n} (strict)" for n in dd.MAP_NOTES]
        excluded = dd.MAP_COUNTS.get("excluded", 0)
        lines = [f"{self.map_used}: {len(claims)} entries ready to check"
                 + (f"; {excluded} marked excluded (not requirements, never sent)" if excluded else "")
                 + f" | {self.last_index}",
                 f"a full check would cost about ${dd.estimate_cost(claims):.4f}"]
        notes = [ln.strip()[len("note: "):] for ln in buf.getvalue().splitlines() if ln.strip().startswith("note:")]
        if not strict:
            lines += [f"note: {n}" for n in notes]
        if problems:
            lines += ["", f"PROBLEMS ({len(problems)}) - fix these; the map is not ready:"] + [f"  - {p}" for p in problems]
        else:
            lines.append("OK - the map is complete and every entry resolves.")
        structured = {"project": str(self.root), "map": self.map_used, "ready": not problems,
                      "entries_to_check": len(claims), "excluded": excluded,
                      "full_check_cost_usd": round(dd.estimate_cost(claims), 6), "problems": problems,
                      "notes": [] if strict else notes}
        return "\n".join(lines), False, structured

    def show_payload(self, files: list[str] | None = None, line: int | None = None,
                     map: str | None = None) -> tuple[str, bool]:
        problems: list[str] = []
        self.resolve_map(map)
        syms = self.index()
        with contextlib.redirect_stdout(io.StringIO()):
            claims = self.claims(syms, problems, map)
        if line is not None:
            claims = [c for c in claims if c.line == line]
            if files:
                claims, _ = self.select(claims, files)
        else:
            claims, _ = self.select(claims, files)
        if not claims:
            return "no claim matches (a line number is the spec line; files are paths relative to the project).", False
        parts = [f"{len(claims)} claim(s). Every request is model {dd.MODEL} with these 3 fixed questions:",
                 json.dumps(dd.build_questions(claims[0]), indent=1, ensure_ascii=False)]
        for c in claims:
            parts += ["", f"--- {c.doc}:{c.line}  state sent:",
                      json.dumps(dd.canonical(dd.build_state(c)), indent=1, ensure_ascii=False)]
        return "\n".join(parts), False

    def draft_map(self, docs: list[str], out: str) -> tuple[str, bool]:
        target = (self.root / out).resolve()
        if not target.is_relative_to(self.root):
            raise ToolError(f"{out} is outside the project - refused")
        if target.exists():
            raise ToolError(f"{out} already exists and may hold a reviewed map - nothing was written. "
                            f"Draft into a new file and compare.")
        specs: list[Path] = []
        for d in docs:
            p = (self.root / d).resolve()
            if not p.is_relative_to(self.root) or not p.exists():
                raise ToolError(f"spec not found in the project: {d}")
            specs += sorted(f for f in [*p.rglob("*.md"), *p.rglob("*.rst")]) if p.is_dir() else [p]
        if not specs:
            raise ToolError("no .md or .rst files in " + ", ".join(docs))
        syms = self.index()
        if self.current_cancel.is_set():
            raise ToolError("cancelled - nothing was written")
        target.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dd.draft_map([Path(os.path.relpath(f, self.root)) for f in specs], syms, Path(os.path.relpath(target, self.root)))
        return (f"{self.last_index}\n{buf.getvalue().strip()}\n\nNothing is checked until the entries are reviewed. "
                f"Then validate_map (map: {out}) must report OK before check_drift."), False

    def call(self, name: str, args: dict) -> tuple:
        """(text, is_error) or (text, is_error, structured). An unknown tool is a protocol error;
        wrong arguments are tool errors, so the model can correct them."""
        tool = {"check_drift": self.check_drift, "validate_map": self.validate_map,
                "show_payload": self.show_payload, "draft_map": self.draft_map}.get(name)
        if tool is None:
            raise ProtocolError(INVALID_PARAMS, f"Unknown tool: {name} (the tools are: "
                                                + ", ".join(t["name"] for t in TOOLS) + ")")
        args = _check_arguments(next(t for t in TOOLS if t["name"] == name), args)
        if self.max_calls:
            now = time.monotonic()
            while self.call_times and now - self.call_times[0] > 60:
                self.call_times.popleft()
            if len(self.call_times) >= self.max_calls:
                raise ToolError(f"rate limit: at most {self.max_calls} tool calls a minute - try again in "
                                f"{60 - (now - self.call_times[0]):.0f} s")
            self.call_times.append(now)
        project = args.pop("project", None)
        with self.lock:
            if self.closed:
                raise ToolError("the server is shutting down")
            self.use_project(project)
            with _in(self.root), contextlib.redirect_stdout(io.StringIO()):
                try:
                    return tool(**args)
                except dd.Stop as e:
                    raise ToolError(str(e)) from None
                except OSError as e:                  # a file problem the model can act on, not a server fault
                    raise ToolError(f"{type(e).__name__}: {e.strerror or e}"
                                    + (f" ({e.filename})" if getattr(e, "filename", None) else "")) from None


def _check_arguments(tool: dict, args: dict) -> dict:
    """Validate tool inputs against the tool's inputSchema (all flat: strings, booleans,
    integers, lists of strings), with messages the model can act on."""
    schema, name = tool["inputSchema"], tool["name"]
    props = schema["properties"]
    if extra := sorted(set(args) - set(props)):
        raise ToolError(f"{name} does not take {', '.join(extra)}; it takes: {', '.join(sorted(props))}")
    if missing := [k for k in schema.get("required", []) if k not in args]:
        raise ToolError(f"{name} needs {', '.join(missing)}")
    args = dict(args)
    for key, value in list(args.items()):
        kind = props[key]["type"]
        if kind == "integer" and isinstance(value, float) and value.is_integer():
            value = args[key] = int(value)            # 3.0 is an integer in JSON Schema 2020-12
        fits = {"string": isinstance(value, str),
                "boolean": isinstance(value, bool),
                "integer": isinstance(value, int) and not isinstance(value, bool),
                "array": isinstance(value, list) and all(isinstance(v, str) for v in value)}[kind]
        if not fits:
            want = {"array": "a list of strings", "integer": "an integer", "boolean": "true or false",
                    "string": "a string"}[kind]
            raise ToolError(f"{key} must be {want} (got {json.dumps(value)[:60]})")
    return args


def _in_triage_order(results: list[dict]) -> list[dict]:
    """DRIFT by severity, then review by P(drifted), then ??, then ok - where an agent's effort goes."""
    rank = {"DRIFT": 0, "review": 1, "??": 2, "ok": 3}
    return sorted(results, key=lambda r: (rank[r["label"]],
                                          -r["severity"] if r["label"] == "DRIFT" else
                                          -r["probabilities"].get("drifted", 0) if r["label"] == "review" else 0))


def _report(results: list[dict], path: str) -> list[str]:
    """The results, in the order an agent should spend its effort."""
    by = {k: [r for r in results if r["label"] == k] for k in ("DRIFT", "review", "??", "ok")}
    out = [f"DRIFT {len(by['DRIFT'])} · review {len(by['review'])} · ?? {len(by['??'])} · ok {len(by['ok'])}"
           f"   full results (with the exact code sent): {path}"]

    def item(r: dict, extra: str = "") -> list[str]:
        refs = r["code_refs"]
        return [f"  {r['doc']}:{r['line']}  P(drifted) {r['probabilities'].get('drifted', 0):.2f}  "
                f"severity {r['severity']}/3{extra}",
                f"    claim: {r['claim']}",
                f"    code:  {refs[0]}" + (f"  (+{len(refs) - 1} more: {', '.join(refs[1:])})" if len(refs) > 1 else ""),
                f"    why:   {r['why']}"]

    if by["DRIFT"]:
        out += ["", "DRIFT - investigate each one (which side is wrong: code or spec?):"]
        for r in sorted(by["DRIFT"], key=lambda r: -r["severity"]):
            out += item(r)
    if by["review"]:
        out += ["", "review - sorted by P(drifted); investigate from 0.3 up, skim below:"]
        for r in sorted(by["review"], key=lambda r: -r["probabilities"].get("drifted", 0)):
            out += item(r)
    if by["??"]:
        out += ["", "?? - NOT a pass: the code shown cannot settle these. Fix the map entry (add the "
                    "implementation, the constant, the caller), then check again:"]
        for r in by["??"]:
            out += item(r)
    if by["ok"]:
        odd = [r for r in by["ok"] if (r.get("value_mismatch") or 0) >= 0.5]
        out += ["", f"ok {len(by['ok'])} - spot-check a couple"
                + (f"; these have value_mismatch >= 0.5, check them:" if odd else ".")]
        for r in odd:
            out += item(r, f"  value_mismatch {r['value_mismatch']:.2f}")
    return out


@contextlib.contextmanager
def _in(folder: Path):
    """docdrift resolves paths against the working directory; the server's is the project root."""
    before = Path.cwd()
    os.chdir(folder)
    try:
        yield
    finally:
        os.chdir(before)


# ── the protocol ────────────────────────────────────────────────────────────────
_SEND_LOCK = threading.Lock()


def _send(msg: dict) -> None:
    """One JSON-RPC message per line on stdout (json.dumps never emits a raw newline)."""
    with _SEND_LOCK:
        try:
            _PROTOCOL_OUT.write(json.dumps(msg, ensure_ascii=False) + "\n")
            _PROTOCOL_OUT.flush()
        except (OSError, ValueError):
            # The client stopped reading. Point fd 1 at devnull so the bytes still buffered are
            # not written (and fail) again when the process exits.
            with contextlib.suppress(OSError):
                os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
            raise


OPEN = object()                                    # a request that stays open (subscriptions/listen)
LOG_LEVELS = ("debug", "info", "notice", "warning", "error", "critical", "alert", "emergency")


def _valid_id(x) -> bool:
    return isinstance(x, (str, int)) and not isinstance(x, bool)


def _error(mid, code: int, message: str, data: dict | None = None) -> dict:
    """An error response. An id that could not be read is left out (MCP's schema makes it optional)."""
    err: dict = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    msg: dict = {"jsonrpc": "2.0", "error": err}
    if _valid_id(mid):
        msg["id"] = mid
    return msg


def _tool_result(server: Server, params: dict) -> dict:
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise ProtocolError(INVALID_PARAMS, "tools/call needs params.name, the tool's name")
    args = params.get("arguments")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ProtocolError(INVALID_PARAMS, "tools/call params.arguments must be an object")
    try:
        text, is_error, *rest = server.call(name, args)
    except ToolError as e:
        text, is_error, rest = str(e), True, []
    result: dict = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if rest and rest[0] is not None and not is_error:
        result["structuredContent"] = rest[0]
        # for clients that do not read structuredContent (MCP tools: SHOULD also return the serialized JSON)
        result["content"].append({"type": "text", "text": json.dumps(rest[0], ensure_ascii=False)})
    return result


def _list_tools(params: dict) -> dict:
    if params.get("cursor") is not None:           # one page, so no cursor was ever handed out
        raise ProtocolError(INVALID_PARAMS, "unknown cursor: tools/list returns every tool in one page")
    return {"tools": TOOLS}


def _modern(server: Server, method: str, params: dict, meta: dict) -> dict:
    """A 2026-07-28 request: stateless; version and capabilities come with the request."""
    version = meta.get(M + "protocolVersion")
    if not isinstance(version, str) or not version:
        raise ProtocolError(INVALID_PARAMS, f"_meta {M}protocolVersion must be a version string such as "
                                            f"{MODERN_VERSIONS[0]}", {"supported": list(MODERN_VERSIONS)})
    if version not in MODERN_VERSIONS:
        # Only per-request versions are listed; 2025-11-25 and earlier are served after initialize.
        hint = (" - versions up to 2025-11-25 open with initialize instead" if version in LEGACY_VERSIONS else "")
        raise ProtocolError(UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version" + hint,
                            {"supported": list(MODERN_VERSIONS), "requested": version})
    if not isinstance(meta.get(M + "clientCapabilities"), dict):
        raise ProtocolError(INVALID_PARAMS, f"_meta must include {M}clientCapabilities (required on every "
                                            f"{version} request)")
    level = meta.get(M + "logLevel")
    if level is not None and level not in LOG_LEVELS:
        raise ProtocolError(INVALID_PARAMS, f"_meta {M}logLevel must be one of: {', '.join(LOG_LEVELS)}")
    cache = {"ttlMs": LIST_TTL_MS, "cacheScope": "private"}     # per client; nothing to share
    if method == "subscriptions/listen":
        # Subscribe and Notify: acknowledge with the subset honoured - none, the tool list never
        # changes - and keep the request open until the client cancels it or the input ends.
        msg_id = params.get("_request_id")
        with server.state:
            if msg_id in server.cancelled:
                return OPEN                       # cancelled before it started: send nothing for it
            server.subscriptions.add(msg_id)
        _send({"jsonrpc": "2.0", "method": "notifications/subscriptions/acknowledged",
               "params": {"_meta": {M + "subscriptionId": msg_id}, "notifications": {}}})
        return OPEN
    if method == "server/discover":
        result = {"supportedVersions": list(MODERN_VERSIONS), "capabilities": CAPABILITIES,
                  "instructions": INSTRUCTIONS, **cache}
    elif method == "tools/list":
        result = {**_list_tools(params), **cache}
    elif method == "tools/call":
        result = _tool_result(server, params)
    else:
        raise ProtocolError(METHOD_NOT_FOUND, f"method not found: {method}")
    result["resultType"] = "complete"
    result["_meta"] = {M + "serverInfo": SERVER_INFO}
    return result


def _legacy(server: Server, method: str, params: dict) -> dict:
    """A request after initialize (2025-11-25 and earlier), answered in that revision's shapes."""
    if method == "ping":
        return {}
    if method == "tools/list":
        return _list_tools(params)
    if method == "tools/call":
        return _tool_result(server, params)
    raise ProtocolError(METHOD_NOT_FOUND, f"method not found: {method}")


def _initialize(server: Server, params: dict) -> dict:
    """Legacy handshake: selects legacy semantics for this stdio process (dual-era server)."""
    asked = params.get("protocolVersion")
    server.legacy_version = asked if asked in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
    return {"protocolVersion": server.legacy_version, "capabilities": CAPABILITIES,
            "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS}


def handle(server: Server, msg) -> dict | None:
    """One JSON-RPC message in, its response out (None for notifications)."""
    if not isinstance(msg, dict):
        return _error(None, INVALID_REQUEST, "not a JSON-RPC 2.0 message (one object per line; no batches)")
    raw_id = msg.get("id")
    if msg.get("jsonrpc") != "2.0":
        return _error(raw_id, INVALID_REQUEST, "not a JSON-RPC 2.0 message (jsonrpc must be \"2.0\")")
    method = msg.get("method")
    if not isinstance(method, str):
        if "result" in msg or "error" in msg:
            return None                            # a stray response: clients do not send those; ignore
        return _error(raw_id, INVALID_REQUEST, "a request needs a method name")
    if "id" not in msg:
        return None                                # a notification (cancellation is handled on arrival)
    mid = raw_id
    if not _valid_id(mid):
        return _error(None, INVALID_REQUEST, "a request id must be a string or an integer, not null")
    params = msg.get("params") if msg.get("params") is not None else {}
    try:
        if not isinstance(params, dict):
            raise ProtocolError(INVALID_PARAMS, "params must be an object")
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        if method == "initialize":
            result = _initialize(server, params)
        elif M + "protocolVersion" in meta:
            result = _modern(server, method, {**params, "_request_id": mid}, meta)
            if result is OPEN:
                return None
        elif server.legacy_version:
            result = _legacy(server, method, params)
        else:
            raise ProtocolError(INVALID_PARAMS,
                                f"missing _meta {M}protocolVersion: send it on every request (2026-07-28), or "
                                f"open with initialize (2025-11-25 and earlier). Supported: "
                                + ", ".join(SUPPORTED_VERSIONS), {"supported": list(MODERN_VERSIONS)})
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except ProtocolError as e:
        return _error(mid, e.code, e.message, e.data)
    except Exception as e:  # noqa: BLE001 - report, keep serving
        print(f"docdrift-mcp: internal error on {method}: {type(e).__name__}: {e}", file=sys.stderr)
        return _error(mid, INTERNAL_ERROR, f"docdrift failed: {type(e).__name__}: {e}")


def serve(server: Server, stdin=None) -> None:
    """Read on one thread, answer on this one. Reading ahead is what lets a cancellation reach a
    request that is still running (stdio has no per-request stream to close)."""
    inbox: queue.Queue = queue.Queue()

    def read() -> None:
        try:
            read_lines()
        finally:
            # End of input is the stdio transport's shutdown signal: exit promptly. The running
            # request stops (a check sends no further claims) and nothing queued is started.
            server.shutdown()
            inbox.put(None)

    def read_lines() -> None:
        for raw in (stdin or sys.stdin.buffer):
            line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except (ValueError, RecursionError) as e:  # bad JSON, a 5000-digit number, deep nesting
                inbox.put({"_parse_error": getattr(e, "msg", str(e))[:200]})
                continue
            if isinstance(msg, dict) and msg.get("method") == "notifications/cancelled" and "id" not in msg:
                p = msg.get("params") if isinstance(msg.get("params"), dict) else {}
                rid = p.get("requestId")
                if _valid_id(rid):                 # anything else is a malformed cancellation: ignore it
                    server.subscriptions.discard(rid)
                    server.cancel(rid, str(p.get("reason") or ""))
                continue
            if isinstance(msg, dict) and isinstance(msg.get("method"), str) and _valid_id(msg.get("id")):
                server.received(msg["id"])
            inbox.put(msg)

    threading.Thread(target=read, daemon=True).start()
    while (msg := inbox.get()) is not None:
        if server.closed:
            continue                               # shutting down: nothing more is answered
        if isinstance(msg, dict) and "_parse_error" in msg:
            _send(_error(None, PARSE_ERROR, f"parse error: {msg['_parse_error']}"))
            continue
        is_request = isinstance(msg, dict) and isinstance(msg.get("method"), str) and _valid_id(msg.get("id"))
        mid = msg.get("id") if is_request else None
        if is_request:
            params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
            meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
            if not server.begin(mid, meta.get("progressToken")):
                server.finish(mid)                 # cancelled while queued: never started, never answered
                continue
        reply = handle(server, msg)
        dropped = server.finish(mid) if is_request else False
        if dropped:
            server.subscriptions.discard(mid)      # a cancelled listen gets no closing result
        if reply is not None and not dropped:
            _send(reply)
    for sid in sorted(server.subscriptions, key=str):  # graceful end of the open subscriptions
        with contextlib.suppress(OSError, ValueError):     # the client may already be gone
            _send({"jsonrpc": "2.0", "id": sid, "result": {"resultType": "complete",
                   "_meta": {M + "subscriptionId": sid, M + "serverInfo": SERVER_INFO}}})


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="docdrift_mcp.py",
        description="docdrift's spec-drift checks as an MCP server (stdio). Started by an MCP client such "
                    "as Claude Code, not by hand - see the top of this file for how to register it.")
    ap.add_argument("--root", default=None,
                    help="The project folder. Default: $CLAUDE_PROJECT_DIR if set (Claude Code), else the "
                         "folder the client starts the server in - unless that is this plugin's own folder "
                         "(Codex), in which case every tool call names the project with 'project'.")
    ap.add_argument("--map", metavar="FILE", help="The spec map, relative to --root. Default: the project's "
                                                  "only *spec_map.json, found automatically.")
    ap.add_argument("--key-file", metavar="FILE",
                    help="Read TYPESAFE_API_KEY=... from this file (and only from it); an absolute path "
                         "(~ allowed). Put it outside the project so the agent has no reason to open it. Default: the TYPESAFE_API_KEY "
                         "environment variable, then typesafe.env in the plugin's data folder ($PLUGIN_DATA "
                         "or $CLAUDE_PLUGIN_DATA). A project's own .env is never read for the key.")
    ap.add_argument("--jobs", type=int, default=8, metavar="N", help="Claims asked about at once (default 8).")
    ap.add_argument("--ignore", nargs="*", default=[], metavar="NAME",
                    help="More folders to skip, on top of docdrift's defaults (node_modules, build, ...).")
    ap.add_argument("--no-warm", action="store_true",
                    help="Do not read the code at start-up (the first tool call does it instead).")
    ap.add_argument("--max-calls-per-minute", type=int, default=120, metavar="N",
                    help="At most N tool calls of any kind a minute (default 120; 0 = no limit).")
    ap.add_argument("--max-checks-per-minute", type=int, default=20, metavar="N",
                    help="Stop a runaway agent loop from spending TypeSafe credits: at most N check_drift "
                         "calls a minute (default 20; 0 = no limit).")
    a = ap.parse_args(argv)
    if a.key_file:
        kf = Path(a.key_file).expanduser()
        if not kf.is_absolute():
            ap.error(f"--key-file {a.key_file}: give an absolute path (e.g. ~/.config/typesafe.env); a relative "
                     "one would be read from inside the project being checked")
        a.key_file = str(kf)
    given = a.root or os.environ.get("CLAUDE_PROJECT_DIR")
    root: Path | None = Path(given or ".").resolve()
    if given and not root.is_dir():
        ap.error(f"--root {given}: no such folder")
    plugin_home = Path(__file__).resolve().parent.parent
    if not given and root.is_relative_to(plugin_home):
        root = None                               # started inside the plugin itself: wait for a project
    ignore = tuple(dict.fromkeys(dd.DEFAULT_IGNORE + [n.strip("/").removeprefix("./") for n in a.ignore]))
    server = Server(root, a.map, a.key_file, max(1, a.jobs), ignore, max(0, a.max_checks_per_minute),
                    max(0, a.max_calls_per_minute))
    if not a.no_warm:
        threading.Thread(target=server.warm, daemon=True).start()
    with contextlib.suppress(ValueError, AttributeError):   # SIGTERM (the client's next step): clean up, go
        signal.signal(signal.SIGTERM, lambda *_: (server.cleanup(), os._exit(0)))
    try:
        serve(server)
    finally:
        server.cleanup()


def _exit_code(e: SystemExit) -> int:
    if e.code is None or isinstance(e.code, int):
        return e.code or 0
    print(e.code, file=sys.stderr)
    return 1


if __name__ == "__main__":
    code = 0
    try:
        main()
    except SystemExit as e:
        code = _exit_code(e)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        code = 1
    finally:
        # Leave without interpreter finalization: the reader thread may still hold stdin's
        # buffer lock, and finalizing then aborts ("could not acquire lock for <stdin>").
        with contextlib.suppress(Exception):
            sys.stderr.flush()
        os._exit(code)
