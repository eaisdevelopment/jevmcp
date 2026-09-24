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
"""Documentation drift checker.

The question "have the docs drifted?" is not one question — it is one question
per *claim*. So the tool has three jobs, and only the second involves the model:

  1. PAIR   find the code each doc sentence is talking about   (deterministic)
  2. ASK    is this sentence still true of this code?          (Jev)
  3. GATE   act only where it is confident                     (deterministic)

Step 1 is where most of the value is. A claim paired with the wrong code is
noise no model can fix.

What it can read
    Python       functions, classes, class attributes, constants; FastAPI / Flask
                 routes, Django URLconfs; os.environ reads, pydantic settings
    Java         types, methods, fields, constants, enums; Spring MVC routes,
                 @Value, @ConfigurationProperties, application*.yml/.properties
    JavaScript   functions, classes, consts, config objects, CommonJS exports;
    TypeScript   + interfaces, type aliases, enums; Express-style routers
                 (with app.use mounts), NestJS controllers, Next.js file routes,
                 process.env / import.meta.env reads, .env.example templates

    Python needs nothing extra. Java / JavaScript / TypeScript / YAML need the
    parsers listed at the top of this file: `uv run --script` installs them, or
        pip install tree-sitter tree-sitter-java tree-sitter-javascript \\
                    tree-sitter-typescript pyyaml

Usage (from the folder of the project you are checking):
    uv run --script <path>/spec_drift.py --docs docs/spec.md --src . --dry-run    # pairs only
    uv run --script <path>/spec_drift.py --docs docs/spec.md --src . --draft-map map.json
    uv run --script <path>/spec_drift.py --map map.json --src . --out drift.json
"""
from __future__ import annotations

import argparse
import ast
import bisect
import contextlib
import functools
import heapq
import importlib
import io
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap
import time
import tokenize
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

API = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"           # pinned, never an alias
ACT_ABOVE = 0.905              # off-grid: values are rounded to 2dp
# Passing a claim as clean is the dangerous direction: a wrong "clean" hides drift
# silently, a wrong DRIFT costs someone a minute. So clean needs 3 sigma of headroom
# over the act line (sigma 0.0273 = p95 spread of confidence across identical calls).
# Found on a real project: a drifted claim answered "accurate" at 0.87-0.94 over 8
# identical calls - it passed as clean in 4 of them with a 0.905 line.
CLEAN_ABOVE = 0.987
SAMPLES = 3                    # asks for a claim the first answer did not settle (1 = never re-ask)
AGREE_FLOOR = 0.85             # every sample must be at least this confident to decide by agreement
MAX_CODE_CHARS = 2_600         # keep state small; accuracy falls with clutter
MAX_FILE_BYTES = 1_500_000     # bigger than this is generated or vendored

DEFAULT_IGNORE = [".venv", "venv", "node_modules", ".git", "build", "dist", "__pycache__",
                  ".gradle", "target", ".next", ".nuxt", ".svelte-kit", ".turbo", "coverage",
                  ".idea", ".mypy_cache", ".pytest_cache", ".tox", "bower_components",
                  ".claude", ".agents", ".cursor"]         # agent tooling and worktree copies, not product code
HTTP_VERBS = ("get", "post", "put", "delete", "patch", "options", "head")


# ─────────────────────────────────────────────────────────── 1. what we index

class Symbol:
    """A named piece of code a spec can talk about.

    `source` is rendered on first use: a 16,000-file repository has hundreds of
    thousands of symbols, and only the few that get paired are ever shown to
    the model.
    """
    __slots__ = ("name", "kind", "file", "line", "value", "_source", "_loader")

    def __init__(self, name: str, kind: str, file: str, line: int, source: str | None = None,
                 value: str = "", loader: Callable[[], str] | None = None):
        self.name, self.kind, self.file, self.line, self.value = name, kind, file, line, value
        self._source, self._loader = source, loader

    @property
    def source(self) -> str:
        if self._source is None:
            try:
                self._source = (self._loader() if self._loader else "")[:MAX_CODE_CHARS]
            except Exception as e:  # noqa: BLE001 - a broken render must not stop a run
                self._source = f"(source unavailable: {type(e).__name__})"
        return self._source

    @source.setter
    def source(self, value: str) -> None:
        self._source = value[:MAX_CODE_CHARS]

    def __repr__(self) -> str:
        return f"Symbol({self.kind} {self.name} @ {self.file}:{self.line})"


# (resolved file, name) -> Symbol. A map entry names its file, so lookups must
# honour it: `A.java:Foo.get` must never resolve to `B.java`'s `Foo.get`.
_BY_FILE: dict[tuple[str, str], Symbol] = {}
_BY_NAME: dict[str, list[Symbol]] = {}      # every symbol by name, across files
_ROUTES: dict[str, list[Symbol]] = {}       # normalised path -> handlers (Symbol.value = verb)
_CONFIG: dict[str, Symbol] = {}             # canonical key -> definitions and uses
_NOTES: list[str] = []

# collected during indexing, resolved once every file has been read
_CFG: dict[str, dict] = {}
_PENDING: list[dict] = []                   # routes whose prefix or handler needs other files
_EDGES: list[tuple[tuple[str, str], tuple, str]] = []   # (parent router, child ref, mount prefix)
_LOCAL_PREFIX: dict[tuple[str, str], str] = {}
_BINDINGS: dict[str, dict[str, tuple]] = {}  # file -> imported name -> ("module"|"default"|"attr", file[, name])
_DEFAULT_EXPORT: dict[str, str] = {}         # file -> variable exported as default / module.exports
_JAVA_CONST: dict[str, str] = {}             # "Paths.ORDERS" and "ORDERS" -> string literal
_JAVA_IMPLEMENTS: dict[str, list[str]] = {}  # interface -> implementing classes
_NEST_PREFIX: list[str] = []


def _reset() -> None:
    for d in (_BY_FILE, _BY_NAME, _PY_BY_TAIL, _ROUTES, _CONFIG, _CFG, _LOCAL_PREFIX, _BINDINGS, _DEFAULT_EXPORT,
              _JAVA_CONST, _JAVA_IMPLEMENTS):
        d.clear()
    for lst in (_NOTES, _PENDING, _EDGES, _NEST_PREFIX):
        lst.clear()


def _register(syms: dict[str, Symbol], sym: Symbol, bare: bool = True, merge: bool = False) -> Symbol:
    """Index a symbol by (file, name); first one wins, except overloads, which merge."""
    key = (str(Path(sym.file).resolve()), sym.name)
    prev = _BY_FILE.get(key)
    if prev is not None:
        if merge and sym.kind == "function":
            a, b = prev._loader, sym._loader
            prev._loader = (lambda a=a, b=b: (a() if a else "") + "\n\n" + (b() if b else ""))
            prev._source = None
        return prev
    _BY_FILE[key] = sym
    _BY_NAME.setdefault(sym.name, []).append(sym)
    if bare:
        syms.setdefault(sym.name, sym)
    return sym


@functools.lru_cache(maxsize=None)
def _is_test(file: str) -> bool:
    f = Path(file).as_posix()
    name = f.rsplit("/", 1)[-1]
    stem = name[:name.rfind(".")] if name.rfind(".") > 0 else name
    return ("/src/test/" in f or "/tests/" in f or "/test/" in f or "/__tests__/" in f
            or name.startswith("test_") or ".test." in name or ".spec." in name
            or stem.endswith(("Test", "Tests", "IT", "_test", "Spec")))


# ───────────────────────────────────────────── 1a. text helpers and redaction

C_FAMILY = {".java", ".kt", ".kts", ".scala", ".groovy", ".ts", ".tsx", ".mts", ".cts", ".js",
            ".jsx", ".mjs", ".cjs", ".go", ".cs", ".c", ".h", ".cc", ".cpp", ".hpp", ".rs", ".swift"}
JS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs"}
TS_SUFFIXES = {".ts", ".tsx", ".mts", ".cts"}
TREE_SITTER = {".java": ("Java", "tree-sitter-java", "tree_sitter_java", "language"),
               **{s: ("JavaScript", "tree-sitter-javascript", "tree_sitter_javascript", "language")
                  for s in JS_SUFFIXES},
               **{s: ("TypeScript", "tree-sitter-typescript", "tree_sitter_typescript", "language_typescript")
                  for s in (".ts", ".mts", ".cts")},
               ".tsx": ("TypeScript", "tree-sitter-typescript", "tree_sitter_typescript", "language_tsx")}
UNINDEXED = (C_FAMILY | {".rb", ".php"}) - set(TREE_SITTER)


_RUST_CHAR = re.compile(r"'(?:[^'\\\n]|\\(?:[nrt0\\'\"]|x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]{1,6}\}))'")


_RUST_RAW = re.compile(r'b?r(#*)"')
_WORD_CHAR = re.compile(r"\w")


def mask_c_family(text: str, strings: bool, rust: bool = False) -> str:
    """Blank out comments (and, if `strings`, string contents), keeping every
    newline and offset so braces and line numbers still line up. Used where no
    parser is available; tree-sitter languages use their real comment nodes.
    In Rust a lone ' starts a lifetime or label (&'static, 'outer:), not a char.
    """
    out = list(text)
    i, n = 0, len(text)

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if text[k] != "\n":
                out[k] = " "

    while i < n:
        two = text[i:i + 2]
        if two == "//":
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j); i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j); i = j
        elif text.startswith('"""', i):          # Java text block
            j = text.find('"""', i + 3)
            j = n if j < 0 else j + 3
            if strings:
                blank(i + 3, max(i + 3, j - 3))
            i = j
        elif text[i] == "`":                     # JS template literal, Go raw string: may span lines
            j = i + 1
            while j < n and text[j] != "`":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            if strings:
                blank(i + 1, max(i + 1, j - 1))
            i = j
        elif rust and text[i] in "br" and (m := _RUST_RAW.match(text, i)) and not (i and _WORD_CHAR.match(text[i - 1])):
            end = '"' + m.group(1)               # r"..", r#".."#, br##".."##: no escapes, may span lines
            j = text.find(end, m.end())
            j = n if j < 0 else j + len(end)
            if strings:
                blank(m.end(), max(m.end(), j - len(end)))
            i = j
        elif rust and text[i] == "'" and not _RUST_CHAR.match(text, i):
            i += 1                               # a lifetime or loop label
        elif text[i] in "\"'":
            q, j = text[i], i + 1
            while j < n and text[j] != q and (rust or text[j] != "\n"):     # a Rust string may span lines
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            if strings:
                blank(i + 1, max(i + 1, j - 1))
            i = j
        else:
            i += 1
    return "".join(out)


def tidy(src: str) -> str:
    """Drop the blank lines comment-stripping leaves behind, then dedent."""
    lines, blank_run = [], 0
    for line in src.split("\n"):
        line = line.rstrip()
        blank_run = blank_run + 1 if not line else 0
        if blank_run <= 1:
            lines.append(line)
    return textwrap.dedent("\n".join(lines)).strip("\n")


_SECRET_NAME = re.compile(r"pass(?:word|wd|phrase)|(?-i:(?<![A-Za-z])(?:[Pp]ass|PASS)(?![a-z])|(?<=[a-z0-9])Pass(?![a-z]))|secret|token|api[-_.]?key|private[-_.]?key|"
                          r"credential|access[-_.]?key|signing[-_.]?key|client[-_.]?secret|(?:^|[-_.])key$|dsn$", re.I)
_SECRET_LITERAL = re.compile(      # (?<!...) starts matches only at a name's start: same matches, linear time
    r"""((?:(?<![\w.\-])[\w.\-]*(?:pass(?:word|wd|phrase)|(?-i:(?<![A-Za-z])(?:[Pp]ass|PASS)(?![a-z])|(?<=[a-z0-9])Pass(?![a-z]))|secret|token|api[-_.]?key|private[-_.]?key|"""
    r"""credential|access[-_.]?key)[\w.\-]*)["']?\s*(?::|=>|=)\s*)(["'`])(?!\$\{)([^"'`\n]{4,})\2""", re.I)
_SECRET_SHAPES = [re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{8,}"),     # Stripe
                  re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[0-9A-Za-z_]{20,}"),     # GitHub
                  re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}"),                          # Slack
                  re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),                               # Google
                  re.compile(r"\bsk-(?:ant-|proj-)?[0-9A-Za-z_\-]{20,}"),                 # OpenAI / Anthropic
                  re.compile(r"://[^/\s:@]+:[^/\s@]+@"),                                   # user:password@ in URLs
                  re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"),
                  re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
                  re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
                  re.compile(r"\bgl(?:pat|dt|rt|ptt|cbt|imt|soat|ft|oas)-[0-9A-Za-z_\-]{20,}"),   # GitLab
                  re.compile(r"\bnpm_[0-9A-Za-z]{36}\b"),                                  # npm
                  re.compile(r"\bpypi-[0-9A-Za-z_\-]{50,}"),                              # PyPI
                  re.compile(r"https://hooks\.slack\.com/services/[0-9A-Za-z/]{20,}"),    # Slack webhook
                  re.compile(r"\bhv[sb]\.[0-9A-Za-z_\-]{24,}")]                           # HashiCorp Vault


def redact(text: str) -> str:
    """Remove secret-looking values before anything is sent to the API.

    A spec check never needs a real password. Placeholders like `${DB_PASSWORD}`
    reveal nothing and are kept - they are often what the claim is about.
    """
    text = _SECRET_LITERAL.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>{m.group(2)}", text)
    for pat in _SECRET_SHAPES:
        text = pat.sub(lambda m: "://<redacted>@" if m.group(0).startswith("://") else "<redacted>", text)
    return text


def _secret_key(key: str) -> bool:
    """A setting whose value is a secret: by its name, including camelCase (`encryptionKey`)."""
    return bool(_SECRET_NAME.search(key) or re.search(r"[a-z0-9]Key$", key))


def _secret_value(key: str, value: str) -> str:
    v = value.strip()
    if v and _secret_key(key) and not v.startswith("${"):
        return "<redacted>"
    return redact(value)


_CONFIG_LINE = re.compile(r"^(\s*(?:export\s+)?-?\s*)([\w.\-\[\]]+)(\s*[:=]\s*)(\S.*?)\s*$")


def redact_config_text(text: str) -> str:
    """Config files paired whole or by line range: redact secret settings line by line, quoted
    or not (`spring.datasource.password=hunter2`, `  password: hunter2`), keeping placeholders."""
    out = []
    for line in text.split("\n"):
        m = _CONFIG_LINE.match(line)
        if m and _secret_key(m.group(2)) and not m.group(4).startswith(("${", "|", ">")):
            line = f"{m.group(1)}{m.group(2)}{m.group(3)}<redacted>"
        out.append(line)
    return "\n".join(out)


def _is_config_file(path: Path) -> bool:
    return path.suffix in {".properties", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".env"} \
        or bool(_ENV_TEMPLATES.match(path.name))


def _blank_py_docstrings(src: str, lines: list[str]) -> None:
    """Blank every module, class and function docstring in `lines` (line count kept)."""
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                    and (isinstance(node, ast.Module) or first.lineno > node.lineno)):
                for k in range(first.lineno - 1, first.end_lineno):
                    lines[k] = ""


def _py_clean(src: str) -> str:
    """Python code with comments and docstrings removed.

    Same rule as every other language: the model judges the code, not what
    someone wrote about it. A stale docstring is exactly the kind of author
    text that sways a verdict.
    """
    src = textwrap.dedent(src)
    lines = src.split("\n")
    try:
        _blank_py_docstrings(src, lines)
    except SyntaxError:
        return tidy(src)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                r, c = tok.start
                lines[r - 1] = lines[r - 1][:c].rstrip()
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return tidy("\n".join(lines))


def strip_comments(path: Path, text: str) -> str:
    """A whole file (for line-range refs) with comments blanked, line numbers kept."""
    if path.suffix == ".py":
        lines = text.split("\n")
        with contextlib.suppress(SyntaxError, ValueError):
            _blank_py_docstrings(text, lines)
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.COMMENT:
                    r, c = tok.start
                    lines[r - 1] = lines[r - 1][:c].rstrip()
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
        return "\n".join(lines)
    if path.suffix in TREE_SITTER and (loaded := _ts_load(str(path))) is not None:
        src, tree = loaded
        return _ts_blank(src, 0, len(src), tree.root_node).decode("utf-8", "replace")
    if path.suffix in C_FAMILY:
        return mask_c_family(text, strings=False, rust=path.suffix == ".rs")
    return text


# ───────────────────────────────────────── 1b. routes, paths and config keys

def _norm_path(p: str) -> str:
    """`/orders/:id`, `/orders/{id}`, `/orders/<int:id>/`, `/orders/[id]` -> `/orders/{}`."""
    p = re.sub(r"\$\{[^}]*\}|\{[^{}]*\}|:[A-Za-z_]\w*\??|<[^<>]*>|\[\.{0,3}[^\]]*\]|\(\?P<\w+>[^)]*\)", "{}", p.strip())
    p = re.sub(r"[\^$]", "", p)
    return "/" + "/".join(s for s in p.split("/") if s)


def _join(*parts: str) -> str:
    segs = [s for part in parts if part for s in part.split("/") if s]
    return "/" + "/".join(segs)


def _add_route(verb: str, path: str, handler: Symbol | None, how: str, header_extra: str = "") -> Symbol:
    verb = verb.upper()
    path = _join(_fill_placeholders(path))
    name = f"{verb} {path}"
    h = handler

    def render() -> str:
        c = "#" if h is not None and h.file.endswith(".py") else "//"
        head = f"{c} {name}  ({how})" + (f"\n{c} {header_extra}" if header_extra else "")
        return head + ("\n" + h.source if h is not None else "")

    sym = Symbol(name, "route", h.file if h else "", h.line if h else 0, value=verb, loader=render)
    _ROUTES.setdefault(_norm_path(path), []).append(sym)
    return sym


def _segments_match(route_segs: list[str], want: list[str]) -> bool:
    return len(route_segs) == len(want) and all(r == w or r == "{}" or w == "{}" for r, w in zip(route_segs, want))


def route_lookup(verb: str | None, path: str) -> list[Symbol]:
    """Exact match first. Otherwise a parameter on either side matches one segment, so a
    spec's `/orders/123` finds `/orders/{id}`, and `/v1/ping` finds `/${api.version}/ping`."""
    key = _norm_path(path)
    found = _ROUTES.get(key, [])
    if not found:
        want = key.split("/")
        found = [s for k, v in _ROUTES.items() if _segments_match(k.split("/"), want) for s in v]
    if verb:
        exact = [s for s in found if s.value == verb.upper()]
        return exact or [s for s in found if s.value == "ANY"]
    return list(found)


def _canon(key: str) -> str:
    """Spring relaxed binding: max-items, maxItems and max_items are one key.
    Environment variable names are kept as they are."""
    key = key.strip()
    if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        return key
    return ".".join(re.sub(r"[-_]", "", seg).lower() for seg in key.split("."))


def _kebab(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", name).lower()


def _cfg(key: str, role: str, file: str, line: int, text: str, value: str | None = None,
         profile: str | None = None) -> None:
    """Record a definition ("defined") or use ("used", "bound", "read") of a config key."""
    entry = _CFG.setdefault(_canon(key), {"key": key, "rows": [], "file": file, "line": line, "value": None})
    if role == "defined" and not any(r[0] == "defined" for r in entry["rows"]):
        entry["key"], entry["file"], entry["line"] = key, file, line
    if role == "defined" and value is not None and not profile and not _is_test(file) and entry["value"] is None:
        entry["value"] = value
    entry["rows"].append((role, file, line, " ".join(text.split())[:300]))


def _fill_placeholders(path: str) -> str:
    """`/${api.version}/orders` -> `/v1/orders` when the key is defined; `${x:dflt}` -> dflt.
    An undefined placeholder stays, and matches like a path parameter."""
    def one(m: re.Match) -> str:
        e = _CFG.get(_canon(m.group(1)))
        if e is not None and e["value"] not in (None, ""):
            return e["value"]
        return m.group(2) if m.group(2) is not None else m.group(0)
    return re.sub(r"\$\{([^}:]+)(?::([^}]*))?\}", one, path)


def config_lookup(name: str) -> Symbol | None:
    return _CONFIG.get(_canon(name)) or _CONFIG.get(name.upper())


def _finish_config(syms: dict[str, Symbol]) -> None:
    order = {"defined": 0, "bound": 1, "used": 2, "read": 3}
    for canon, e in _CFG.items():
        rows = sorted(e["rows"], key=lambda r: (order.get(r[0], 9), _is_test(r[1]), r[1], r[2]))
        body = [f"# config key {e['key']}"]
        spring_def = next(((f, ln) for role, f, ln, txt in rows if role == "defined" and _SPRING_CONFIG.match(Path(f).name)
                           and "[profile" not in txt and not _is_test(f)), None)
        if spring_def and e["value"] is not None and any(r[0] in ("bound", "used") for r in rows):
            # Spring semantics, stated so the model need not know them: a value in
            # application.yml / .properties overrides a field default or @Value default.
            body.append(f"# effective value (default profile): {e['value']}  from {Path(spring_def[0]).as_posix()}:"
                        f"{spring_def[1]}; defaults in code apply only when the key is not set")
        body += [f"{role:<8} {Path(f).as_posix()}:{ln}  {txt}" for role, f, ln, txt in rows]
        sym = Symbol(e["key"], "config", e["file"], e["line"], source="\n".join(body))
        _CONFIG[canon] = sym
        syms.setdefault(e["key"], sym)


# ─────────────────────────────────────────────────────────── 1c. Python (ast)

_PY_BY_TAIL: dict[str, list[str]] = {}     # "items.py" / "routers/__init__.py" -> files


def _py_module_file(importer: Path, module: str | None, level: int, files: set[str]) -> str | None:
    """Resolve `from .x import y` / `import a.b` to a file under the source root."""
    parts = (module or "").split(".") if module else []
    if level:
        base = importer.parent
        for _ in range(level - 1):
            base = base.parent
        for cand in (base.joinpath(*parts).with_suffix(".py") if parts else None,
                     base.joinpath(*parts, "__init__.py")):
            if cand is not None and str(cand.resolve()) in files:
                return str(cand.resolve())
        return None
    if not parts:
        return None
    tails = ("/" + "/".join(parts) + ".py", "/" + "/".join(parts) + "/__init__.py")
    pool = _PY_BY_TAIL.get(parts[-1] + ".py", []) + _PY_BY_TAIL.get(parts[-1] + "/__init__.py", [])
    cands = [f for f in pool if f.endswith(tails)]
    if not cands:
        return None
    imp = str(importer.resolve())
    return max(cands, key=lambda f: (len(os.path.commonprefix([f, imp])), -len(f)))


def _py_bindings(path: Path, tree: ast.Module, files: set[str]) -> dict[str, tuple]:
    rp = str(path.resolve())
    out: dict[str, tuple] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            modfile = _py_module_file(path, node.module, node.level, files)
            for a in node.names:
                local = a.asname or a.name
                sub = _py_module_file(path, ((node.module + ".") if node.module else "") + a.name,
                                      node.level, files) if a.name != "*" else None
                if sub:
                    out[local] = ("module", sub)
                elif modfile:
                    out[local] = ("attr", modfile, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if (f := _py_module_file(path, a.name, 0, files)):
                    out[a.asname or a.name.split(".")[0]] = ("module", f)
    out["__file__"] = ("self", rp)
    return out


def _py_ref(expr: ast.AST, rp: str) -> tuple | None:
    """A router expression -> ("ref", file, name) to resolve later."""
    if isinstance(expr, ast.Name):
        return ("name", rp, expr.id)
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        return ("attr", rp, expr.value.id, expr.attr)
    return None


def _py_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return None
    return None


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _django_path(route: str, regex: bool) -> str:
    if regex:
        route = re.sub(r"\(\?P<\w+>[^)]*\)|\([^)]*\)", "{}", route)
        route = route.replace("^", "").replace("$", "").replace("\\", "")
    return route


def index_python_file(p: Path, text: str, syms: dict[str, Symbol], files: set[str]) -> int:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 0
    rp, lines, count = str(p.resolve()), text.split("\n"), 0
    _BINDINGS[rp] = _py_bindings(p, tree, files)

    def seg(node: ast.AST) -> tuple[int, int]:
        decos = getattr(node, "decorator_list", None) or []
        start = min([d.lineno for d in decos] + [node.lineno])
        return start, node.end_lineno

    def render(a: int, b: int) -> Callable[[], str]:
        return lambda: _py_clean("\n".join(lines[a - 1:b]))

    def render_class(node: ast.ClassDef) -> Callable[[], str]:
        def go() -> str:
            a, b = seg(node)
            full = _py_clean("\n".join(lines[a - 1:b]))
            if len(full) <= MAX_CODE_CHARS:
                return full
            out = lines[a - 1:node.body[0].lineno - 1] if node.body else []
            for st in node.body:
                sa, sb = seg(st)
                if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out += lines[sa - 1:st.body[0].lineno - 1] + [" " * (st.col_offset + 4) + "..."]
                else:
                    out += lines[sa - 1:sb]
            return _py_clean("\n".join(out))
        return go

    def rec(name: str, node: ast.AST, kind: str, value: str = "", loader=None, bare=True) -> Symbol:
        nonlocal count
        a, b = seg(node)
        count += 1
        return _register(syms, Symbol(name, kind, str(p), a, value=value[:400],
                                      loader=loader or render(a, b)), bare=bare)

    def unparse(v: ast.AST | None) -> str:
        try:
            return ast.unparse(v) if v is not None else ""
        except Exception:  # noqa: BLE001
            return ""

    settings_prefix: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            handler = rec(node.name, node, "function")
            _py_routes(node, handler, rp)
        elif isinstance(node, ast.ClassDef):
            rec(node.name, node, "class", loader=render_class(node))
            is_settings = any(unparse(b).endswith("BaseSettings") for b in node.bases)
            prefix = ""
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    rec(f"{node.name}.{sub.name}", sub, "function", bare=False)
                elif isinstance(sub, (ast.Assign, ast.AnnAssign)):
                    targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                    for t in targets:
                        if not isinstance(t, ast.Name):
                            continue
                        val = unparse(sub.value)
                        rec(f"{node.name}.{t.id}", sub, "constant" if t.id.isupper() else "field",
                            val, bare=False)
                        if t.id == "model_config" and "env_prefix" in val:
                            m = re.search(r"env_prefix\s*=\s*['\"]([^'\"]*)", val)
                            prefix = m.group(1) if m else prefix
                elif isinstance(sub, ast.ClassDef) and sub.name == "Config":
                    for st in sub.body:
                        if isinstance(st, ast.Assign) and any(getattr(t, "id", "") == "env_prefix" for t in st.targets):
                            prefix = _py_str(st.value) or prefix
            if is_settings:
                for sub in node.body:
                    if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) \
                            and not sub.target.id.startswith("_") and sub.target.id != "model_config":
                        _cfg((prefix + sub.target.id).upper(), "bound", str(p), sub.lineno,
                             f"{node.name}.{sub.target.id}: {unparse(sub.annotation)}"
                             + (f" = {unparse(sub.value)}" if sub.value is not None else "") + "  (pydantic settings)")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    rec(t.id, node, "constant", unparse(node.value))
                    _py_router_def(t.id, node.value, rp)
            if p.name == "urls.py" and any(getattr(t, "id", "") == "urlpatterns" for t in targets):
                _py_django(node.value, rp)
        elif isinstance(node, ast.AugAssign) and getattr(node.target, "id", "") == "urlpatterns" and p.name == "urls.py":
            _py_django(node.value, rp)

    for node in ast.walk(tree):                   # mounts and environment reads, anywhere
        key, default = None, None
        if isinstance(node, ast.Call):
            _py_mount(node, rp)
            f = unparse(node.func)
            if f in ("os.environ.get", "os.getenv", "getenv", "environ.get", "os.environ.setdefault") and node.args:
                key = _py_str(node.args[0])
                default = unparse(node.args[1]) if len(node.args) > 1 else None
        elif isinstance(node, ast.Subscript) and unparse(node.value) in ("os.environ", "environ"):
            key = _py_str(node.slice)
        if key:
            ln = getattr(node, "lineno", 1)
            _cfg(key, "read", str(p), ln, lines[ln - 1].strip() + (f"   (default {default})" if default else ""))
    return count


def _py_router_def(var: str, value: ast.AST | None, rp: str) -> None:
    if not isinstance(value, ast.Call):
        return
    fn = value.func.attr if isinstance(value.func, ast.Attribute) else getattr(value.func, "id", "")
    if fn in ("APIRouter", "Blueprint", "FastAPI", "Flask", "Starlette"):
        prefix = _py_str(_kw(value, "prefix")) or _py_str(_kw(value, "url_prefix")) or ""
        _LOCAL_PREFIX[(rp, var)] = prefix


def _py_mount(call: ast.Call, rp: str) -> None:
    if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name):
        return
    attr = call.func.attr
    if attr in ("include_router", "register_blueprint") and call.args:
        prefix = _py_str(_kw(call, "prefix")) or _py_str(_kw(call, "url_prefix")) or ""
        if (ref := _py_ref(call.args[0], rp)):
            _EDGES.append((("name", rp, call.func.value.id), ref, prefix))
    elif attr == "mount" and len(call.args) >= 2 and (prefix := _py_str(call.args[0])) is not None:
        if (ref := _py_ref(call.args[1], rp)):
            _EDGES.append((("name", rp, call.func.value.id), ref, prefix))


def _py_routes(fn: ast.FunctionDef | ast.AsyncFunctionDef, handler: Symbol, rp: str) -> None:
    for dec in fn.decorator_list:
        if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                and isinstance(dec.func.value, ast.Name)):
            continue
        attr = dec.func.attr
        path = _py_str(dec.args[0]) if dec.args else _py_str(_kw(dec, "path")) or _py_str(_kw(dec, "rule"))
        if path is None or (path and not path.startswith("/")):
            continue
        if attr in HTTP_VERBS:
            verbs = [attr.upper()]
        elif attr in ("route", "api_route"):
            m = _kw(dec, "methods")
            verbs = [e.value.upper() for e in getattr(m, "elts", []) if isinstance(e, ast.Constant)] or ["GET"]
        elif attr == "websocket":
            verbs = ["WS"]
        else:
            continue
        for v in verbs:
            _PENDING.append({"node_ref": ("name", rp, dec.func.value.id), "verb": v, "path": path,
                             "handler": handler, "how": f"{dec.func.value.id}.{attr} in {Path(rp).name}"})


def _py_django(value: ast.AST | None, rp: str) -> None:
    if not isinstance(value, (ast.List, ast.Tuple)):
        return
    for call in value.elts:
        if not isinstance(call, ast.Call):
            continue
        fn = getattr(call.func, "id", getattr(call.func, "attr", ""))
        if fn not in ("path", "re_path", "url") or len(call.args) < 2:
            continue
        route = _py_str(call.args[0])
        if route is None:
            continue
        route = _django_path(route, regex=fn != "path")
        view = call.args[1]
        if isinstance(view, ast.Call) and getattr(view.func, "id", getattr(view.func, "attr", "")) == "include":
            target = view.args[0] if view.args else None
            if (mod := _py_str(target)):
                _EDGES.append((("node", rp, "urlpatterns"), ("module-str", rp, mod), route))
            elif target is not None and (ref := _py_ref(target, rp)):
                _EDGES.append((("node", rp, "urlpatterns"), ("module-ref",) + ref[1:], route))
            continue
        if isinstance(view, ast.Call) and isinstance(view.func, ast.Attribute) and view.func.attr == "as_view":
            view = view.func.value
        ref = _py_ref(view, rp)
        if ref:
            _PENDING.append({"node_ref": ("node", rp, "urlpatterns"), "verb": "ANY", "path": route,
                             "handler_ref": ref, "how": f"Django URLconf {Path(rp).parent.name}/urls.py"})


# ──────────────────────────────────────────── 1d. Java / JS / TS (tree-sitter)

_PARSERS: dict[str, object] = {}
_MISSING: dict[str, str] = {}                  # suffix -> pip package that would fix it


def _ts_parser(suffix: str):
    if suffix in _PARSERS:
        return _PARSERS[suffix]
    lang_name, pip_name, module, fn = TREE_SITTER[suffix]
    parser = None
    try:
        from tree_sitter import Language, Parser
        parser = Parser(Language(getattr(importlib.import_module(module), fn)()))
    except ImportError:
        _MISSING[suffix] = f"tree-sitter {pip_name}"
    except Exception as e:  # noqa: BLE001
        _MISSING[suffix] = f"{pip_name} ({type(e).__name__}: {e})"
    _PARSERS[suffix] = parser
    return parser


@functools.lru_cache(maxsize=48)
def _ts_load(path: str):
    parser = _ts_parser(Path(path).suffix)
    if parser is None:
        return None
    src = Path(path).read_bytes()
    return src, parser.parse(src)


_COMMENT_TYPES = {"comment", "line_comment", "block_comment", "html_comment"}


def _ts_blank(src: bytes, a: int, b: int, scope) -> bytes:
    """src[a:b] with every comment node inside `scope` blanked (newlines kept)."""
    buf = bytearray(src[a:b])
    stack = [scope]
    while stack:
        n = stack.pop()
        if n.end_byte <= a or n.start_byte >= b:
            continue
        if n.type in _COMMENT_TYPES:
            for k in range(max(n.start_byte, a), min(n.end_byte, b)):
                if buf[k - a] != 10:
                    buf[k - a] = 32
            continue
        stack.extend(n.children)
    return bytes(buf)


def _ts_node_at(path: str, a: int, b: int, types: tuple[str, ...]):
    loaded = _ts_load(path)
    if loaded is None:
        return None, None
    src, tree = loaded
    node = tree.root_node.descendant_for_byte_range(a, max(a, b - 1))
    if node is not None and node.type not in types:
        inner = next((c for c in node.named_children if c.type in types), None)
        if inner is not None:
            return src, inner
    while node is not None and node.type not in types:
        node = node.parent
    return src, node


def _ts_render(path: str, a: int, b: int, outline_types: tuple[str, ...] = ()) -> str:
    """Code from the start of the line holding byte `a` to byte `b`, comments removed.
    A class too long for the budget is shown as an outline: members, bodies elided."""
    loaded = _ts_load(path)
    if loaded is None:
        return ""
    src, tree = loaded
    start = src.rfind(b"\n", 0, a) + 1
    scope = tree.root_node.descendant_for_byte_range(a, max(a, b - 1)) or tree.root_node
    while scope.parent is not None and (scope.start_byte > a or scope.end_byte < b):
        scope = scope.parent
    full = tidy(_ts_blank(src, start, b, scope).decode("utf-8", "replace"))
    if len(full) <= MAX_CODE_CHARS or not outline_types:
        return full
    _, node = _ts_node_at(path, a, b, outline_types)
    body = node.child_by_field_name("body") if node is not None else None
    if body is None:
        return full
    parts = [_ts_blank(src, start, body.start_byte + 1, node).decode("utf-8", "replace")]
    for m in body.named_children:
        if m.type in _COMMENT_TYPES:
            continue
        inner = m.child_by_field_name("body")
        m_start = src.rfind(b"\n", 0, m.start_byte) + 1
        if inner is not None and m.type not in ("enum_body_declarations",):
            parts.append(_ts_blank(src, m_start, inner.start_byte, m).decode("utf-8", "replace").rstrip() + " { … }")
        else:
            parts.append(_ts_blank(src, m_start, m.end_byte, m).decode("utf-8", "replace"))
    parts.append("}")
    return tidy("\n".join(parts))


def _txt(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _string_value(src: bytes, node) -> str | None:
    """A string literal's value (Java or JS/TS), or None if it is not a plain literal."""
    if node is None:
        return None
    if node.type in ("string_literal", "string"):
        return "".join(_txt(src, c) for c in node.named_children if c.type in ("string_fragment", "escape_sequence"))
    if node.type == "template_string":
        if any(c.type == "template_substitution" for c in node.named_children):
            return None
        return _txt(src, node)[1:-1]
    if node.type == "binary_expression":
        l, r = node.child_by_field_name("left"), node.child_by_field_name("right")
        lv, rv = _string_value(src, l), _string_value(src, r)
        return lv + rv if lv is not None and rv is not None else None
    return None


# ── Java

_JAVA_TYPES = ("class_declaration", "interface_declaration", "enum_declaration",
               "record_declaration", "annotation_type_declaration")
_SPRING_VERBS = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
                 "DeleteMapping": "DELETE", "PatchMapping": "PATCH", "RequestMapping": None}


def _java_annotations(src: bytes, decl) -> list[tuple[str, dict[str, list[str]]]]:
    """[(name, {arg: [values]})]; a constant reference becomes '@ref:Type.NAME'."""
    out = []
    mods = next((c for c in decl.children if c.type == "modifiers"), None)
    for a in (mods.named_children if mods else []):
        if a.type not in ("annotation", "marker_annotation"):
            continue
        name = _txt(src, a.child_by_field_name("name")).split(".")[-1]
        args: dict[str, list[str]] = {}
        al = a.child_by_field_name("arguments")
        for arg in (al.named_children if al else []):
            if arg.type == "element_value_pair":
                k, v = _txt(src, arg.child_by_field_name("key")), arg.child_by_field_name("value")
            else:
                k, v = "value", arg
            args[k] = _java_values(src, v)
        out.append((name, args))
    return out


def _java_values(src: bytes, v) -> list[str]:
    if v is None:
        return []
    if v.type == "element_value_array_initializer":
        return [x for c in v.named_children for x in _java_values(src, c)]
    s = _string_value(src, v)
    if s is not None:
        return [s]
    if v.type in ("identifier", "field_access", "scoped_identifier"):
        return ["@ref:" + _txt(src, v)]
    if v.type == "binary_expression":
        return ["@expr:" + _txt(src, v)]
    return [_txt(src, v)]


def index_java_file(p: Path, syms: dict[str, Symbol]) -> int:
    loaded = _ts_load(str(p))
    if loaded is None:
        return 0
    src, tree = loaded
    fs, count = str(p), 0

    def rec(name, kind, node, start=None, bare=True, merge=False, value="", outline=False):
        nonlocal count
        a, b = (start if start is not None else node.start_byte), node.end_byte
        count += 1
        loader = (lambda a=a, b=b: _ts_render(fs, a, b, _JAVA_TYPES if outline else ()))
        return _register(syms, Symbol(name, kind, fs, node.start_point[0] + 1, value=value[:400], loader=loader),
                         bare=bare, merge=merge)

    def walk(body, owner: str, owner_kind: str, class_paths: list[str], feign: bool, props_prefix: str | None):
        for m in body.named_children:
            t = m.type
            if t in _JAVA_TYPES:
                visit_type(m)
            elif t == "enum_body_declarations":
                walk(m, owner, owner_kind, class_paths, feign, props_prefix)
            elif t == "enum_constant":
                n = _txt(src, m.child_by_field_name("name"))
                s = rec(f"{owner}.{n}", "constant", m, bare=False, value=_txt(src, m))
                syms.setdefault(n, s)
            elif t in ("method_declaration", "constructor_declaration", "compact_constructor_declaration"):
                nm = m.child_by_field_name("name")
                n = _txt(src, nm) if nm is not None else owner
                handler = rec(f"{owner}.{n}", "function", m, bare=False, merge=True)
                anns = _java_annotations(src, m)
                for ann, args in anns:
                    if ann in _SPRING_VERBS and not feign:
                        verbs = ([_SPRING_VERBS[ann]] if _SPRING_VERBS[ann] else
                                 [v.split(".")[-1] for v in args.get("method", [])] or ["ANY"])
                        paths = args.get("value") or args.get("path") or [""]
                        _PENDING.append({"java": True, "owner": owner, "owner_kind": owner_kind,
                                         "method": n, "verbs": verbs, "paths": paths, "class_paths": class_paths,
                                         "handler": handler, "file": fs})
                params = m.child_by_field_name("parameters")
                for prm in (params.named_children if params else []):
                    java_value_injection(prm, f"{owner}.{n}")
            elif t in ("field_declaration", "constant_declaration"):
                words = set(_txt(src, next((c for c in m.children if c.type == "modifiers"), m)).split()) \
                    if any(c.type == "modifiers" for c in m.children) else set()
                const = {"static", "final"} <= words or owner_kind == "interface_declaration" or t == "constant_declaration"
                for d in m.children_by_field_name("declarator"):
                    n = _txt(src, d.child_by_field_name("name"))
                    val = d.child_by_field_name("value")
                    vtext = _txt(src, val) if val is not None else ""
                    s = rec(f"{owner}.{n}", "constant" if const else "field", m, bare=False, value=vtext)
                    if const:
                        syms.setdefault(n, s)
                        if (sv := _string_value(src, val)) is not None:
                            _JAVA_CONST[f"{owner}.{n}"] = sv
                            _JAVA_CONST.setdefault(n, sv)
                    if props_prefix is not None and "static" not in words:
                        key = f"{props_prefix}.{_kebab(n)}"
                        _cfg(key, "bound", fs, m.start_point[0] + 1,
                             f"{owner}.{n} = {vtext or '(no default)'}   (@ConfigurationProperties \"{props_prefix}\")")
                java_value_injection(m, f"{owner}")

    def java_value_injection(decl, where: str):
        for ann, args in _java_annotations(src, decl):
            if ann != "Value":
                continue
            for v in args.get("value", []):
                for key, default in re.findall(r"\$\{([^:}]+)(?::([^}]*))?\}", v):
                    _cfg(key, "used", fs, decl.start_point[0] + 1,
                         f"{_txt(src, decl)}   (in {where}" + (f"; default {default}" if default else "") + ")")

    def visit_type(node):
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _txt(src, name_node)
        rec(name, "class", node, outline=True)
        anns = dict((a, args) for a, args in _java_annotations(src, node))
        class_paths = [""]
        if "RequestMapping" in anns:
            class_paths = anns["RequestMapping"].get("value") or anns["RequestMapping"].get("path") or [""]
        feign = "FeignClient" in anns
        props = None
        if "ConfigurationProperties" in anns:
            cp = anns["ConfigurationProperties"]
            vals = cp.get("prefix") or cp.get("value") or []
            props = vals[0] if vals and not vals[0].startswith("@ref:") else None
        ifaces = node.child_by_field_name("interfaces")
        if ifaces is not None:
            for tid in re.findall(r"[A-Z]\w*", _txt(src, ifaces).replace("implements", "")):
                _JAVA_IMPLEMENTS.setdefault(tid, []).append(name)
        if node.type == "record_declaration" and props:
            for prm in (node.child_by_field_name("parameters").named_children
                        if node.child_by_field_name("parameters") else []):
                pn = prm.child_by_field_name("name")
                if pn is not None:
                    _cfg(f"{props}.{_kebab(_txt(src, pn))}", "bound", fs, prm.start_point[0] + 1,
                         f"{name}({_txt(src, prm)})   (@ConfigurationProperties record \"{props}\")")
        body = node.child_by_field_name("body")
        if body is not None:
            walk(body, name, node.type, class_paths, feign, props)

    for top in tree.root_node.named_children:
        if top.type in _JAVA_TYPES:
            visit_type(top)
    if b"getenv" in src:
        for n in _ts_iter(tree.root_node, {"method_invocation"}):
            if _txt(src, n.child_by_field_name("name") or n) == "getenv":
                args = n.child_by_field_name("arguments")
                key = _string_value(src, args.named_children[0]) if args and args.named_children else None
                if key:
                    _cfg(key, "read", fs, n.start_point[0] + 1, _line_of(src, n))
    return count


def _ts_iter(root, types: set[str]):
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type in types:
            yield n
        if n.type not in ("string", "string_literal", "template_string", "comment", "line_comment", "block_comment"):
            stack.extend(reversed(n.children))


def _line_of(src: bytes, node) -> str:
    a = src.rfind(b"\n", 0, node.start_byte) + 1
    b = src.find(b"\n", node.end_byte)
    return src[a:b if b >= 0 else len(src)].decode("utf-8", "replace").strip()


# ── JavaScript / TypeScript

_JS_FUNCS = ("arrow_function", "function_expression", "function", "generator_function")
_JS_CLASSES = ("class_declaration", "abstract_class_declaration", "class")
_NEST_VERBS = {"Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE", "Patch": "PATCH",
               "Options": "OPTIONS", "Head": "HEAD", "All": "ANY"}
_ROUTER_CTORS = re.compile(r"^(?:express\.Router|Router|express|fastify|Fastify|new\s+Hono|new\s+Router|"
                           r"new\s+KoaRouter|KoaRouter|createRouter|polka|restify\.createServer)\b")
_CLIENT_CTORS = re.compile(r"^(?:axios|ky|got|fetch|superagent|request|supertest|new\s+HttpClient)\b")
_ROUTER_NAMES = re.compile(r"^(?:app|router|server|api|routes?|\w*[Rr]outer|\w*[Aa]pp)$")


def _js_resolve_module(importer: str, spec: str) -> str | None:
    if not spec.startswith("."):
        return None
    base = (Path(importer).parent / spec)
    swapped = []
    if base.suffix in (".js", ".mjs", ".cjs", ".jsx"):          # TypeScript NodeNext: './x.js' is x.ts on disk
        swapped = [base.with_suffix(s) for s in (".ts", ".tsx", ".mts", ".cts")]
    for cand in [base] + swapped + [base.with_name(base.name + s) for s in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")] \
            + [base / f"index{s}" for s in (".ts", ".tsx", ".js", ".jsx", ".mjs")]:
        if cand.is_file():
            return str(cand.resolve())
    return None


def _decorators(src: bytes, nodes) -> list[tuple[str, list]]:
    out = []
    for d in nodes:
        expr = d.named_children[0] if d.named_children else None
        if expr is None:
            continue
        if expr.type == "call_expression":
            name = _txt(src, expr.child_by_field_name("function")).split(".")[-1]
            args = expr.child_by_field_name("arguments")
            out.append((name, list(args.named_children) if args else []))
        else:
            out.append((_txt(src, expr).split(".")[-1], []))
    return out


def _nest_paths(src: bytes, args: list) -> list[str]:
    if not args:
        return [""]
    a = args[0]
    if (s := _string_value(src, a)) is not None:
        return [s]
    if a.type == "array":
        return [s for c in a.named_children if (s := _string_value(src, c)) is not None] or [""]
    if a.type == "object":
        for pair in a.named_children:
            if pair.type == "pair" and _txt(src, pair.child_by_field_name("key")).strip("'\"") == "path":
                return _nest_paths(src, [pair.child_by_field_name("value")])
    return [""]


def index_js_file(p: Path, syms: dict[str, Symbol], root: Path) -> int:
    loaded = _ts_load(str(p))
    if loaded is None:
        return 0
    src, tree = loaded
    fs, rp, count = str(p), str(p.resolve()), 0
    binds: dict[str, tuple] = {}
    routers: set[str] = set()
    clients: set[str] = set()

    def rec(name, kind, node, start=None, bare=True, merge=False, value="", outline=False):
        nonlocal count
        a, b = (start if start is not None else node.start_byte), node.end_byte
        count += 1
        loader = (lambda a=a, b=b: _ts_render(fs, a, b, _JS_CLASSES if outline else ()))
        return _register(syms, Symbol(name, kind, fs, node.start_point[0] + 1, value=value[:400], loader=loader),
                         bare=bare, merge=merge)

    def object_keys(prefix: str, obj, start, depth: int = 0):
        if depth > 2:
            return
        for pair in obj.named_children:
            if pair.type != "pair":
                continue
            k = _txt(src, pair.child_by_field_name("key")).strip("'\"`")
            v = pair.child_by_field_name("value")
            rec(f"{prefix}.{k}", "constant", pair, bare=False, value=_txt(src, v) if v else "")
            if v is not None and v.type == "object":
                object_keys(f"{prefix}.{k}", v, None, depth + 1)

    def visit_class(node, start, decos):
        nm = node.child_by_field_name("name")
        name = _txt(src, nm) if nm is not None else "default"
        rec(name, "class", node, start=start, outline=True)
        cdec = dict(_decorators(src, decos))
        controller = "Controller" in cdec
        cpaths = _nest_paths(src, cdec["Controller"]) if controller else [""]
        body = node.child_by_field_name("body")
        pending_decos: list = []
        for m in (body.named_children if body else []):
            if m.type == "decorator":
                pending_decos.append(m)
                continue
            mstart = pending_decos[0].start_byte if pending_decos else None
            if m.type in ("method_definition", "abstract_method_signature", "method_signature"):
                mn = _txt(src, m.child_by_field_name("name"))
                handler = rec(f"{name}.{mn}", "function", m, start=mstart, bare=False, merge=True)
                if controller:
                    for dn, dargs in _decorators(src, pending_decos):
                        if dn in _NEST_VERBS:
                            for cp in cpaths:
                                for mp in _nest_paths(src, dargs):
                                    _PENDING.append({"nest": True, "verb": _NEST_VERBS[dn], "path": _join(cp, mp),
                                                     "handler": handler, "how": f"NestJS {name}.{mn}"})
            elif m.type in ("public_field_definition", "field_definition"):
                fnode = m.child_by_field_name("name") or m.child_by_field_name("property")
                if fnode is not None:
                    v = m.child_by_field_name("value")
                    rec(f"{name}.{_txt(src, fnode)}", "field", m, start=mstart, bare=False,
                        value=_txt(src, v) if v else "")
            pending_decos = []

    def visit_decl(node, start, decos, exported_default=False):
        t = node.type
        if t in ("function_declaration", "generator_function_declaration"):
            nm = node.child_by_field_name("name")
            rec(_txt(src, nm) if nm is not None else "default", "function", node, start=start)
        elif t in _JS_CLASSES:
            visit_class(node, start, decos + [c for c in node.children if c.type == "decorator"])
        elif t in ("lexical_declaration", "variable_declaration"):
            for d in node.named_children:
                if d.type != "variable_declarator":
                    continue
                nm, val = d.child_by_field_name("name"), d.child_by_field_name("value")
                if nm is None or nm.type != "identifier":
                    if nm is not None and nm.type == "object_pattern" and val is not None:
                        req = _require(val)
                        if req:
                            for c in nm.named_children:
                                local = _txt(src, c.child_by_field_name("value") or c).split(":")[-1].strip()
                                orig = _txt(src, c.child_by_field_name("key") or c).split(":")[0].strip()
                                binds[local] = ("attr", req, orig)
                    continue
                n = _txt(src, nm)
                vt = val.type if val is not None else ""
                vtext = _txt(src, val) if val is not None else ""
                if vt in _JS_FUNCS:
                    rec(n, "function", node, start=start)
                elif vt == "class":
                    visit_class(val, start or node.start_byte, decos)
                else:
                    rec(n, "constant", node, start=start, value=vtext)
                    if vt == "object":
                        object_keys(n, val, None)
                    if (req := _require(val)):
                        binds[n] = ("default", req)
                    if _ROUTER_CTORS.match(vtext):
                        routers.add(n)
                    elif _CLIENT_CTORS.match(vtext):
                        clients.add(n)
        elif t in ("interface_declaration", "type_alias_declaration"):
            rec(_txt(src, node.child_by_field_name("name")), "class", node, start=start)
        elif t == "enum_declaration":
            en = _txt(src, node.child_by_field_name("name"))
            rec(en, "class", node, start=start)
            body = node.child_by_field_name("body")
            for m in (body.named_children if body else []):
                mn = m.child_by_field_name("name") if m.type == "enum_assignment" else m
                if mn is not None and mn.type in ("property_identifier", "identifier", "string"):
                    rec(f"{en}.{_txt(src, mn).strip(chr(39) + chr(34))}", "constant", m, bare=False, value=_txt(src, m))

    def _require(val) -> str | None:
        if val is None:
            return None
        if val.type == "await_expression" and val.named_children:
            val = val.named_children[0]
        if val.type == "call_expression" and _txt(src, val.child_by_field_name("function")) == "require":
            args = val.child_by_field_name("arguments")
            spec = _string_value(src, args.named_children[0]) if args and args.named_children else None
            return _js_resolve_module(fs, spec) if spec else None
        return None

    for top in tree.root_node.named_children:
        t = top.type
        if t == "export_statement":
            decos = [c for c in top.children if c.type == "decorator"]
            decl = top.child_by_field_name("declaration")
            val = top.child_by_field_name("value")
            if decl is not None:
                visit_decl(decl, top.start_byte, decos)
                if any(c.type == "default" for c in top.children) and (dn := decl.child_by_field_name("name")) is not None:
                    _DEFAULT_EXPORT[rp] = _txt(src, dn)
            elif val is not None:
                if val.type == "identifier":
                    _DEFAULT_EXPORT[rp] = _txt(src, val)
                elif val.type in _JS_FUNCS or val.type in _JS_CLASSES:
                    visit_decl(val, top.start_byte, decos) if val.type in _JS_CLASSES else \
                        rec("default", "function", top)
                elif val.type == "object":
                    rec("default", "constant", top, value=_txt(src, val))
                    object_keys("default", val, None)
        elif t == "import_statement":
            srcn = top.child_by_field_name("source")
            mod = _js_resolve_module(fs, _string_value(src, srcn) or "") if srcn is not None else None
            clause = next((c for c in top.named_children if c.type == "import_clause"), None)
            if mod and clause is not None:
                for c in clause.named_children:
                    if c.type == "identifier":
                        binds[_txt(src, c)] = ("default", mod)
                    elif c.type == "namespace_import":
                        binds[_txt(src, c.named_children[-1])] = ("module", mod)
                    elif c.type == "named_imports":
                        for spec in c.named_children:
                            nm, al = spec.child_by_field_name("name"), spec.child_by_field_name("alias")
                            if nm is not None:
                                binds[_txt(src, al or nm)] = ("attr", mod, _txt(src, nm))
        elif t in ("function_declaration", "generator_function_declaration", "class_declaration",
                   "abstract_class_declaration", "lexical_declaration", "variable_declaration",
                   "interface_declaration", "type_alias_declaration", "enum_declaration"):
            visit_decl(top, None, [])
        elif t == "expression_statement" and top.named_children and top.named_children[0].type == "assignment_expression":
            asg = top.named_children[0]
            left, right = _txt(src, asg.child_by_field_name("left")), asg.child_by_field_name("right")
            if left == "module.exports" and right is not None:
                if right.type == "identifier":
                    _DEFAULT_EXPORT[rp] = _txt(src, right)
                elif right.type == "object":
                    # A CommonJS module is almost always required under its file name
                    # (`const config = require('./config')`), so its keys are `config.key` too.
                    stem = p.stem if p.stem != "index" else p.parent.name
                    for pair in right.named_children:
                        if pair.type == "pair" and (v := pair.child_by_field_name("value")) is not None:
                            k = _txt(src, pair.child_by_field_name("key")).strip("'\"")
                            kind = "function" if v.type in _JS_FUNCS else "constant"
                            rec(k, kind, pair, value=_txt(src, v))
                            rec(f"{stem}.{k}", kind, pair, value=_txt(src, v))
                        elif pair.type == "method_definition":
                            rec(_txt(src, pair.child_by_field_name("name")), "function", pair)
                elif right.type in _JS_FUNCS:
                    nm = right.child_by_field_name("name")
                    rec(_txt(src, nm) if nm is not None else "module.exports", "function", top)
            elif re.fullmatch(r"(?:module\.)?exports\.\w+", left) and right is not None:
                rec(left.split(".")[-1], "function" if right.type in _JS_FUNCS else "constant", top,
                    value=_txt(src, right))

    _BINDINGS[rp] = binds
    toplevel = {n for (f, n) in _BY_FILE if f == rp} | set(binds)
    _js_calls(p, src, tree, root, routers, clients, binds, toplevel)
    return count


def _enclosing_function(src: bytes, node) -> str | None:
    """Name of the function a node sits in: `function f() {}`, `const f = () => {}`, `f() {}`."""
    n = node.parent
    while n is not None:
        if n.type in ("function_declaration", "generator_function_declaration", "method_definition"):
            nm = n.child_by_field_name("name")
            return _txt(src, nm) if nm is not None else None
        if n.type in ("arrow_function", "function_expression", "function") and n.parent is not None \
                and n.parent.type == "variable_declarator":
            return _txt(src, n.parent.child_by_field_name("name"))
        n = n.parent
    return None


def _js_router_ref(src: bytes, rp: str, obj, toplevel: set[str]) -> tuple:
    """The router a call is made on. A router made inside a factory function
    (`function makeRoutes() { const r = new Hono(); r.get(...); return r }`) is
    identified by the factory, because that is what gets mounted: app.route('/x', makeRoutes())."""
    name = _txt(src, obj) if obj is not None else ""
    if name not in toplevel and (fn := _enclosing_function(src, obj)):
        return ("node", rp, f"{fn}()")
    return ("js", rp, name)


def _js_calls(p: Path, src: bytes, tree, root: Path, routers: set[str], clients: set[str], binds: dict,
              toplevel: set[str]) -> None:
    """Express/Hono/Fastify-style routes and mounts, NestJS global prefix, env reads, Next.js file routes."""
    fs, rp = str(p), str(p.resolve())
    routers, clients = set(routers), set(clients)
    for dcl in _ts_iter(tree.root_node, {"variable_declarator"}):
        nm, val = dcl.child_by_field_name("name"), dcl.child_by_field_name("value")
        if nm is not None and val is not None and nm.type == "identifier":
            vt = _txt(src, val)
            if val.type == "await_expression":
                vt = vt[len("await"):].lstrip()
            if _ROUTER_CTORS.match(vt):
                routers.add(_txt(src, nm))
            elif _CLIENT_CTORS.match(vt):
                clients.add(_txt(src, nm))
    for n in _ts_iter(tree.root_node, {"call_expression", "member_expression", "subscript_expression"}):
        if n.type in ("member_expression", "subscript_expression"):
            t = _txt(src, n)
            m = re.match(r"(?:process\.env|import\.meta\.env)(?:\.([A-Za-z_]\w*)|\[\s*['\"]([^'\"]+)['\"]\s*\])$", t)
            if m:
                key = m.group(1) or m.group(2)
                default = ""
                par = n.parent
                if par is not None and par.type == "binary_expression" and par.child_by_field_name("left") == n:
                    op = _txt(src, par)[len(t):].lstrip()[:2]
                    if op in ("||", "??"):
                        default = f"   (default {_txt(src, par.child_by_field_name('right'))[:60]})"
                _cfg(key, "read", fs, n.start_point[0] + 1, _line_of(src, n) + default)
            continue
        fn = n.child_by_field_name("function")
        args = n.child_by_field_name("arguments")
        if fn is None or args is None or fn.type != "member_expression":
            continue
        prop = _txt(src, fn.child_by_field_name("property"))
        obj = fn.child_by_field_name("object")
        argv = list(args.named_children)
        if prop == "setGlobalPrefix" and argv and (s := _string_value(src, argv[0])) is not None:
            _NEST_PREFIX.append(s)
            continue
        if (prop == "use" and argv) or (prop == "route" and len(argv) == 2):      # express use / hono route
            prefix = _string_value(src, argv[0]) if len(argv) >= 2 else ""
            target = argv[-1] if len(argv) >= 2 else argv[0]
            if prefix is not None and obj is not None and obj.type in ("identifier", "member_expression"):
                ref = None
                if target.type == "identifier":
                    ref = ("js", rp, _txt(src, target))
                elif target.type == "call_expression":
                    callee = target.child_by_field_name("function")
                    cname = _txt(src, callee) if callee is not None else ""
                    if cname == "require":
                        a2 = target.child_by_field_name("arguments")
                        spec = _string_value(src, a2.named_children[0]) if a2 and a2.named_children else None
                        mod = _js_resolve_module(fs, spec) if spec else None
                        ref = ("js-default", mod) if mod else None
                    elif callee is not None and callee.type == "identifier":
                        ref = ("js-call", rp, cname)                    # app.use('/x', makeRouter(deps))
                if ref:
                    _EDGES.append((_js_router_ref(src, rp, obj, toplevel), ref, prefix))
            continue
        if prop not in HTTP_VERBS + ("all",) or not argv:
            continue
        path = _string_value(src, argv[0])
        chain_path = None
        if obj is not None and obj.type == "call_expression":        # router.route('/x').get(h)
            inner = obj
            while inner is not None and inner.type == "call_expression":
                ifn = inner.child_by_field_name("function")
                if ifn is not None and ifn.type == "member_expression" \
                        and _txt(src, ifn.child_by_field_name("property")) == "route":
                    ia = inner.child_by_field_name("arguments")
                    chain_path = _string_value(src, ia.named_children[0]) if ia and ia.named_children else None
                    obj = ifn.child_by_field_name("object")
                    break
                inner = ifn.child_by_field_name("object") if ifn is not None and ifn.type == "member_expression" else None
            if chain_path is None:
                continue
            path, handlers = chain_path, argv
        else:
            handlers = argv[1:]
        if path is None or not (path.startswith("/") or path == "*"):
            continue
        if not handlers or handlers[-1].type in ("object", "string", "number", "template_string", "array"):
            continue                                                   # axios.get('/x', {params}) - a client call
        oname = _txt(src, obj) if obj is not None else ""
        if oname in clients or _CLIENT_CTORS.match(oname):
            continue
        if not (oname in routers or _ROUTER_NAMES.match(oname.split(".")[-1])):
            continue
        stmt = n
        while stmt.parent is not None and stmt.parent.type not in ("program", "statement_block"):
            stmt = stmt.parent
        a, b = stmt.start_byte, stmt.end_byte
        call_sym = Symbol(f"{prop.upper()} {path}", "function", fs, n.start_point[0] + 1,
                          loader=lambda a=a, b=b: _ts_render(fs, a, b))
        last = handlers[-1]
        href = None
        if last.type == "identifier":
            href = ("js", rp, _txt(src, last))
        elif last.type == "member_expression":
            href = ("js-member", rp, _txt(src, last.child_by_field_name("object")),
                    _txt(src, last.child_by_field_name("property")))
        _PENDING.append({"node_ref": _js_router_ref(src, rp, obj, toplevel),
                         "verb": "ANY" if prop == "all" else prop.upper(), "path": path,
                         "handler": call_sym, "handler_ref": href, "how": f"{oname}.{prop} in {p.name}"})

    # Next.js file-based routes
    rel = p.relative_to(root).as_posix() if p.is_relative_to(root) else p.as_posix()
    segs = rel.split("/")
    if p.stem == "route" and "app" in segs[:-1]:
        i = len(segs) - 2 - segs[:-1][::-1].index("app")
        route = [s for s in segs[i + 1:-1] if not (s.startswith("(") and s.endswith(")")) and not s.startswith("@")]
        for verb in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            h = _BY_FILE.get((rp, verb))
            if h is not None:
                _add_route(verb, _join(*route), h, f"Next.js app route {rel}")
    elif "pages" in segs[:-1] and "api" in segs:
        i = len(segs) - 2 - segs[:-1][::-1].index("pages")
        route = segs[i + 1:-1] + ([] if p.stem == "index" else [p.stem])
        h = _BY_FILE.get((rp, _DEFAULT_EXPORT.get(rp, "default")))
        if h is not None and route and route[0] == "api":
            _add_route("ANY", _join(*route), h, f"Next.js pages API route {rel}")


# ───────────────────────────────────────────────── 1e. configuration files

_OPENAPI_HEAD = re.compile(rb'^\s*"?(?:openapi|swagger)"?\s*:', re.M)


def index_openapi_file(p: Path) -> int:
    """Routes from an OpenAPI / Swagger document. In API-first projects the
    controller code is generated from this file, and each operationId names the
    method that implements it - so a spec sentence pairs with the contract AND
    the code. Handlers are resolved after all code is indexed."""
    text = p.read_text(encoding="utf-8", errors="replace")
    try:
        if p.suffix == ".json":
            doc = json.loads(text)
        else:
            import yaml
            doc = yaml.safe_load(text)
    except Exception as e:  # noqa: BLE001
        _NOTES.append(f"skipped OpenAPI {p}: {type(e).__name__}")
        return 0
    if not isinstance(doc, dict) or not isinstance(doc.get("paths"), dict):
        return 0
    base = doc.get("basePath", "")
    servers = doc.get("servers") or []
    if not base and servers and isinstance(servers[0], dict):
        url = str(servers[0].get("url", ""))
        base = re.sub(r"^[a-z]+://[^/]+", "", url) if "{" not in url else ""
    n = 0
    for path, item in doc["paths"].items():
        if not isinstance(item, dict):
            continue
        for verb, op in item.items():
            if verb.lower() not in HTTP_VERBS or not isinstance(op, dict):
                continue
            summary = {k: op[k] for k in ("operationId", "summary", "description", "parameters", "requestBody",
                                          "responses", "security") if k in op}
            _PENDING.append({"openapi": True, "verb": verb.upper(), "path": _join(base, path),
                             "operation_id": op.get("operationId"), "file": str(p),
                             "contract": json.dumps(summary, ensure_ascii=False, default=str)[:900]})
            n += 1
    return n


_ENV_TEMPLATES = re.compile(r"^(?:\.env\.(?:example|sample|template|dist|defaults)|(?:example|sample)\.env|env\.example)$")
_SPRING_CONFIG = re.compile(r"^(?:application|bootstrap)(?:-([\w.\-]+))?\.(?:properties|ya?ml)$")


def index_config_file(p: Path) -> int:
    """Spring application*.yml / .properties and .env templates -> config keys.
    A real `.env` is never read: it holds secrets and no spec is about it."""
    fs, count = str(p), 0
    text = p.read_text(encoding="utf-8", errors="replace")
    m = _SPRING_CONFIG.match(p.name)
    profile = m.group(1) if m else None
    if _ENV_TEMPLATES.match(p.name):
        for i, line in enumerate(text.split("\n"), 1):
            mm = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
            if mm:
                val = _secret_value(mm.group(1), mm.group(2).strip().strip("'\""))
                _cfg(mm.group(1), "defined", fs, i, f"{mm.group(1)}={val}   ({p.name})", value=val)
                count += 1
    elif p.suffix == ".properties":
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            start, line = i + 1, lines[i]
            while line.rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                line = line.rstrip()[:-1] + lines[i].lstrip()
            i += 1
            s = line.strip()
            if not s or s[0] in "#!":
                continue
            mm = re.match(r"((?:\\.|[^=:\s])+)\s*[=:\s]\s*(.*)$", s)
            if mm:
                key = mm.group(1).replace("\\", "")
                val = _secret_value(key, mm.group(2))
                _cfg(key, "defined", fs, start, f"{key}={val}" + (f"   [profile {profile}]" if profile else ""),
                     value=val, profile=profile)
                count += 1
    else:
        try:
            import yaml
        except ImportError:
            _MISSING[".yml"] = "pyyaml"
            return 0
        try:
            # Maven resource filtering (`version: @revision@-@maven.build.timestamp@`) is not YAML
            # until Maven runs: quote any value that starts with '@'.
            filtered = re.sub(r"(?m)^(\s*(?:-\s+|[^#\n:]+:\s+))(@[^\n#]*?)\s*$",
                              lambda m: m.group(1) + "'" + m.group(2).replace("'", "''") + "'", text)
            docs = list(yaml.compose_all(filtered, Loader=yaml.SafeLoader))
        except yaml.YAMLError as e:
            _NOTES.append(f"skipped {fs}: not valid YAML ({str(e).splitlines()[0][:80]})")
            return 0
        for doc in docs:
            if doc is None:
                continue
            rows: list[tuple[str, int, str]] = []

            def flat(node, prefix: str):
                if isinstance(node, yaml.MappingNode):
                    for k, v in node.value:
                        flat(v, f"{prefix}.{k.value}" if prefix else str(k.value))
                elif isinstance(node, yaml.SequenceNode):
                    for idx, item in enumerate(node.value):
                        flat(item, f"{prefix}[{idx}]")
                elif isinstance(node, yaml.ScalarNode):
                    rows.append((prefix, node.start_mark.line + 1, node.value))

            flat(doc, "")
            doc_profile = profile
            for key, _, val in rows:
                if key in ("spring.config.activate.on-profile", "spring.profiles"):
                    doc_profile = val
            for key, line, val in rows:
                val = _secret_value(key, val)
                _cfg(key, "defined", fs, line, f"{key}: {val}" + (f"   [profile {doc_profile}]" if doc_profile else ""),
                     value=val, profile=doc_profile)
                count += 1
    return count


# ────────────────────────────────────────────── 1f. index everything, resolve

def _discover(root: Path, ignore: tuple[str, ...]):
    """Walk once, pruning ignored folders (never descend into node_modules)."""
    ign = set(ignore)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in ign)
        for f in filenames:
            yield Path(dirpath) / f


def _resolve_ref(ref: tuple) -> tuple[str, str] | None:
    """A router/handler reference -> (file, name) of the thing it points at."""
    kind = ref[0]
    if kind == "node":
        return (ref[1], ref[2])
    if kind == "name":                                   # Python local or imported name
        _, rp, name = ref
        b = _BINDINGS.get(rp, {}).get(name)
        if b and b[0] == "attr":
            return (b[1], b[2])
        return (rp, name)
    if kind == "attr":                                   # Python module.attr
        _, rp, mod, attr = ref
        b = _BINDINGS.get(rp, {}).get(mod)
        return (b[1], attr) if b and b[0] == "module" else None
    if kind in ("module-str", "module-ref"):             # Django include()
        if kind == "module-str":
            _, rp, mod = ref
            files = {f for (f, _) in _BY_FILE} | set(_BINDINGS)
            target = _py_module_file(Path(rp), mod, 0, files)
        else:
            b = _BINDINGS.get(ref[1], {}).get(ref[2]) if len(ref) == 3 else None
            target = b[1] if b and b[0] == "module" else None
        return (target, "urlpatterns") if target else None
    if kind == "js":                                     # JS identifier: local or imported
        _, rp, name = ref
        b = _BINDINGS.get(rp, {}).get(name)
        if b is None:
            return (rp, name)
        if b[0] == "default":
            return (b[1], _DEFAULT_EXPORT.get(b[1], "default"))
        if b[0] == "attr":
            return (b[1], b[2])
        return None
    if kind == "js-default":
        return (ref[1], _DEFAULT_EXPORT.get(ref[1], "default"))
    if kind == "js-call":                                # a router factory: makeRoutes(...)
        _, rp, fn = ref
        b = _BINDINGS.get(rp, {}).get(fn)
        if b and b[0] == "attr":
            return (b[1], f"{b[2]}()")
        if b and b[0] == "default":
            return (b[1], f"{_DEFAULT_EXPORT.get(b[1], 'default')}()")
        return (rp, f"{fn}()")
    if kind == "js-member":                              # controller.list / OrdersController.list
        _, rp, obj, prop = ref
        b = _BINDINGS.get(rp, {}).get(obj)
        if b and b[0] in ("module", "default"):
            return (b[1], prop)
        target = (b[1], f"{b[2]}.{prop}") if b and b[0] == "attr" else (rp, f"{obj}.{prop}")
        return target
    return None


def _prefixes(node: tuple[str, str] | None, seen: frozenset = frozenset()) -> list[str]:
    """Every mount prefix above a router: app.use('/api', r) / include_router(r, prefix=...)
    / Django include(). A router's own prefix (APIRouter(prefix=...)) is added by the caller."""
    if node is None:
        return [""]
    out = []
    for parent_ref, child_ref, prefix in _EDGES:
        if _resolve_ref(child_ref) != node:
            continue
        parent = _resolve_ref(parent_ref)
        if parent is None or parent in seen:
            continue
        for pp in _prefixes(parent, seen | {node}):
            out.append(_join(pp, _LOCAL_PREFIX.get(parent, ""), prefix))
    return out or [""]


def _finish_routes() -> None:
    impl_cache: dict[str, list[str]] = _JAVA_IMPLEMENTS
    nest_prefix = _NEST_PREFIX[0] if _NEST_PREFIX else ""
    openapi_ops: list[dict] = []
    by_member: dict[str, list[Symbol]] = {}
    for name, lst in _BY_NAME.items():
        if "." in name:
            by_member.setdefault(name.rsplit(".", 1)[1], []).extend(lst)
    for r in _PENDING:
        if r.get("java"):
            def const(v: str) -> str:
                def one(ref: str) -> str:
                    ref = ref.strip()
                    if ref.startswith('"') and ref.endswith('"'):
                        return ref[1:-1]
                    return _JAVA_CONST.get(ref) or _JAVA_CONST.get(ref.split(".")[-1]) or "{" + ref + "}"
                if v.startswith("@ref:"):
                    return one(v[5:])
                if v.startswith("@expr:"):
                    return "".join(one(part) for part in re.split(r"\s*\+\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", v[6:]))
                return v
            handler, how = r["handler"], f"Spring {r['owner']}.{r['method']}"
            extra = ""
            if r["owner_kind"] == "interface_declaration":      # API-first: route on the interface
                for cls in impl_cache.get(r["owner"], []):
                    impl = next(iter(_BY_NAME.get(f"{cls}.{r['method']}", [])), None)
                    if impl is not None:
                        extra = f"declared on interface {r['owner']}.{r['method']}:\n" + \
                                "\n".join("// " + ln for ln in r["handler"].source.split("\n")[:6])
                        handler, how = impl, f"Spring {cls}.{r['method']} implementing {r['owner']}"
                        break
            for cp in r["class_paths"]:
                for mp in r["paths"]:
                    for verb in r["verbs"]:
                        _add_route(verb, _join(const(cp), const(mp)), handler, how, extra)
            continue
        if r.get("nest"):
            _add_route(r["verb"], _join(nest_prefix, r["path"]), r["handler"], r["how"])
            continue
        if r.get("openapi"):
            openapi_ops.append(r)
            continue
        node = _resolve_ref(r["node_ref"])
        handler = r.get("handler")
        if r.get("handler_ref"):
            target = _resolve_ref(r["handler_ref"])
            found = _BY_FILE.get(target) if target else None
            if found is not None and handler is not None and handler.kind == "function" and handler is not found:
                call, fn = handler, found
                handler = Symbol(call.name, "function", call.file, call.line,
                                 loader=lambda c=call, f=fn: c.source + "\n\n" + f.source)
            elif found is not None and handler is None:
                handler = found
                if found.kind == "class":                     # Django class-based view: one route per method
                    for verb in HTTP_VERBS:
                        m = _BY_FILE.get((str(Path(found.file).resolve()), f"{found.name}.{verb}"))
                        if m is not None:
                            for pre in _prefixes(node):
                                _add_route(verb, _join(pre, _LOCAL_PREFIX.get(node, ""), r["path"]), m, r["how"])
        for pre in _prefixes(node):
            _add_route(r["verb"], _join(pre, _LOCAL_PREFIX.get(node, ""), r["path"]), handler, r["how"])
    # OpenAPI operations last, so code routes win. An operation becomes a route only when the
    # code doesn't declare it (API-first: the interface is generated at build time) AND its
    # operationId names a method in server-side code. Client contracts (APIs this service
    # CALLS) and duplicated contract versions are left out - and a contract is never shown
    # to the model as if it were code.
    skipped, seen = 0, set()
    for r in openapi_ops:
        key = (r["verb"], _norm_path(_fill_placeholders(r["path"])))
        if key in seen or route_lookup(r["verb"], r["path"]):
            seen.add(key)
            continue
        cands = [s for s in by_member.get(r["operation_id"] or "", []) if s.kind == "function"
                 and not _is_test(s.file)
                 and re.search(r"(?i)controller|resource|endpoint|handler|router|views?", Path(s.file).name)
                 and not re.search(r"(?i)client|feign|gateway", Path(s.file).name)]
        if not cands:
            skipped += 1
            continue
        seen.add(key)
        _add_route(r["verb"], r["path"], cands[0],
                   f"path from OpenAPI {Path(r['file']).name}, operationId {r['operation_id']} -> {cands[0].name}")
    if skipped:
        _NOTES.append(f"{skipped} OpenAPI operations not used as routes: no server-side implementation in source "
                      f"(client contracts, or code generated at build time - see --ignore to include target/)")


# Registries a per-file indexer writes. Each file is indexed against empty ones and what it
# wrote is kept, so a long-running process (jevmcp_server.py) re-parses only the files that
# changed and replays the rest; the cross-file passes then run on the merged result.
_PER_FILE = ("_BY_FILE", "_BY_NAME", "_ROUTES", "_CFG", "_BINDINGS", "_LOCAL_PREFIX", "_EDGES", "_PENDING",
             "_JAVA_CONST", "_JAVA_IMPLEMENTS", "_DEFAULT_EXPORT", "_NEST_PREFIX", "_NOTES")


def _captured(p: Path, run: Callable[[dict], int]) -> tuple[int, dict]:
    """Run one file's indexer against empty registries; return its count and what it wrote."""
    g = globals()
    saved = {n: g[n] for n in _PER_FILE}
    fresh = {n: type(saved[n])() for n in _PER_FILE}
    g.update(fresh)
    local: dict[str, Symbol] = {}
    try:
        count = run(local)
    except Exception as e:  # noqa: BLE001 - one odd file must not stop a 10,000-file run
        count = 0
        fresh["_NOTES"].append(f"skipped {p}: {type(e).__name__}: {e}")
    finally:
        g.update(saved)
    fresh["syms"] = local
    return count, fresh


def _replay(c: dict, syms: dict[str, Symbol]) -> None:
    """Merge one file's contribution, with the same first-wins / last-wins rules as indexing
    the files one after another."""
    for n in ("_BY_FILE", "_BINDINGS", "_LOCAL_PREFIX", "_DEFAULT_EXPORT"):     # keyed by file: no clashes
        globals()[n].update(c[n])
    for n in ("_BY_NAME", "_ROUTES", "_JAVA_IMPLEMENTS"):
        reg = globals()[n]
        for k, v in c[n].items():
            reg.setdefault(k, []).extend(v)
    _PENDING.extend(dict(r) for r in c["_PENDING"])
    for n in ("_EDGES", "_NEST_PREFIX", "_NOTES"):
        globals()[n].extend(c[n])
    for k, v in c["_JAVA_CONST"].items():             # Owner.NAME: last wins; bare NAME: first wins
        if "." in k:
            _JAVA_CONST[k] = v
        else:
            _JAVA_CONST.setdefault(k, v)
    for k, e in c["_CFG"].items():                    # the rules of _cfg(), applied to a whole file
        m = _CFG.get(k)
        if m is None:
            _CFG[k] = {**e, "rows": list(e["rows"])}
            continue
        if not any(r[0] == "defined" for r in m["rows"]) and any(r[0] == "defined" for r in e["rows"]):
            m["key"], m["file"], m["line"] = e["key"], e["file"], e["line"]
        if m["value"] is None:
            m["value"] = e["value"]
        m["rows"].extend(e["rows"])
    for k, v in c["syms"].items():
        syms.setdefault(k, v)


def index_code(root: Path, ignore: tuple[str, ...],
               cache: dict | None = None) -> tuple[dict[str, Symbol], dict[str, int]]:
    """Everything a spec could name: symbols, routes and configuration keys.

    `cache` (a dict the caller keeps between calls) holds each file's contribution under
    its path, modification time and size; files that have not changed are not parsed
    again. Python and JS/TS imports resolve against the set of files that exist, so when
    files are added or removed those languages are parsed again in full."""
    _reset()
    _ts_load.cache_clear()
    syms: dict[str, Symbol] = {}
    counts = {"Python": 0, "Java": 0, "JavaScript": 0, "TypeScript": 0}
    code, configs, openapi = [], [], []
    for p in _discover(root, ignore):
        suf, name = p.suffix, p.name
        if suf == ".py" or suf in TREE_SITTER:
            if name.endswith((".d.ts", ".min.js", ".bundle.js")):
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            code.append(p)
        elif _SPRING_CONFIG.match(name) or _ENV_TEMPLATES.match(name):
            configs.append(p)
        elif suf in (".yaml", ".yml", ".json") and name != "package.json" and not name.endswith("lock.json"):
            try:
                if p.stat().st_size < MAX_FILE_BYTES:
                    with open(p, "rb") as fh:
                        if _OPENAPI_HEAD.search(fh.read(4096)):
                            openapi.append(p)
            except OSError:
                pass
    code.sort(key=lambda p: (_is_test(str(p)), p.as_posix()))
    py_files = {str(p.resolve()) for p in code if p.suffix == ".py"}
    for f in py_files:
        fp = Path(f)
        _PY_BY_TAIL.setdefault(fp.parent.name + "/__init__.py" if fp.name == "__init__.py" else fp.name, []).append(f)
    configs.sort(key=lambda p: (_is_test(str(p)), p.as_posix()))
    openapi.sort()
    if cache is not None:
        present = frozenset(str(p) for p in (*code, *configs, *openapi))
        if cache.get("_files") != present:            # Python/JS imports may now resolve differently
            keep = {str(p) for p in code if p.suffix == ".java"} | {str(p) for p in (*configs, *openapi)}
            for k in [k for k in cache if k != "_files" and k not in keep]:
                del cache[k]
            cache["_files"] = present

    def python(p: Path, local: dict) -> int:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return 0
        return index_python_file(p, text, local, py_files)

    def one(p: Path, run: Callable[[dict], int]) -> int:
        stamp = None
        if cache is not None:
            try:
                st = p.stat()
                stamp = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
        hit = cache.get(str(p)) if cache is not None else None
        if hit is not None and stamp is not None and hit[0] == stamp:
            count, contrib = hit[1], hit[2]
        else:
            count, contrib = _captured(p, run)
            if cache is not None and stamp is not None:
                cache[str(p)] = (stamp, count, contrib)
        _replay(contrib, syms)
        return count

    for p in code:
        if p.suffix == ".py":
            counts["Python"] += one(p, lambda local, p=p: python(p, local))
        elif p.suffix == ".java":
            counts["Java"] += one(p, lambda local, p=p: index_java_file(p, local))
        else:
            counts[TREE_SITTER[p.suffix][0]] += one(p, lambda local, p=p: index_js_file(p, local, root))
    for p in configs:
        one(p, lambda local, p=p: index_config_file(p) or 0)
    for p in openapi:
        one(p, lambda local, p=p: index_openapi_file(p) or 0)
    _finish_routes()
    _finish_config(syms)
    counts["routes"] = sum(len(v) for v in _ROUTES.values())
    counts["config keys"] = len(_CONFIG)
    return syms, counts


def unindexed_sources(root: Path, ignore: tuple[str, ...]) -> dict[str, int]:
    """Source files we cannot index. A silent zero here once read as 'your spec
    is plain prose' when the real answer was 'this tool cannot see your code'."""
    seen: dict[str, int] = {}
    for p in _discover(root, ignore):
        if p.suffix in UNINDEXED or p.suffix in _MISSING:
            seen[p.suffix] = seen.get(p.suffix, 0) + 1
    return seen


# ──────────────────────────────────────────────────── 2. pair claims with code

SENT_SPLIT = re.compile(r"(?<=[.!?:])\s+(?=[A-Z`#\-*\d])|\n(?=[-*|#])")
_TABLE_SEP = re.compile(r"^\|?[\s:|-]*-[\s:|-]*\|?$")        # the |---|---| row under a table header
_LIST_ITEM = re.compile(r"(?:[-*+]|\d+\.)\s")                 # "- ", "* ", "1. "
# A heading that is a statement ("What is never sent") rather than a label ("The tools"):
# its list items are fragments that only mean something with it in front.
_STEM_HEADING = re.compile(r"\b(?:is|are|was|were|do|does|can|will|never|always|must|should|"
                           r"leaves?|goes|happens|stores?|sends?|sent|kept|stored|checked)\b", re.I)
IDENT = re.compile(r"`([A-Za-z_][\w.\-]{2,})`|\b([A-Z][A-Z0-9_]{3,})\b")
NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
ROUTE_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+`?(/[^\s`,;)\]]*)")
PATH_RE = re.compile(r"`(/[^\s`]*)`")


@dataclass
class Claim:
    text: str
    doc: str
    line: int
    symbols: list[Symbol]      # every symbol the sentence names
    why_paired: str
    numbers: list[str] = field(default_factory=list)
    map_line: int | None = None    # the line the map stores, when the sentence has since moved to `line`

    @property
    def symbol(self) -> Symbol:
        return self.symbols[0]


_BLOCK_START = re.compile(r"\s*(#|[-*+]\s|\d+[.)]\s|[a-z][.)]\s|\||>|```|---+\s*$)")


def _paragraphs(text: str) -> list[tuple[int, str]]:
    """Markdown lines, with hard-wrapped continuation lines joined back on.

    Most specs wrap at 80-100 columns, so one sentence spans several lines.
    Read line by line, the model is asked to judge "...a clean, swappable
    `ChunkStore` port with" - half a claim. Each logical line keeps the
    number of the line it started on. Fences are passed through untouched.
    """
    out: list[tuple[int, str]] = []
    in_fence = False
    for i, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append((i, line))
            continue
        if in_fence or not stripped:
            out.append((i, line))
            continue
        prev = out[-1][1] if out else ""
        joinable = (out and prev.strip() and not prev.strip().startswith(("```", "|", "#"))
                    and not re.fullmatch(r"-{3,}", prev.strip()))
        quoted = prev.lstrip().startswith(">") and stripped.startswith(">") and stripped != ">"
        if joinable and (quoted or not _BLOCK_START.match(line)):
            out[-1] = (out[-1][0], prev.rstrip() + " " + stripped.lstrip("> ").strip())
        else:
            out.append((i, line))
    return out


def prose_blocks(doc: Path) -> list[tuple[int, str]]:
    """The documentation inside a file, as (line_number, text).

    A .py file's documentation is its docstrings — they drift exactly like a
    README does, and they are the docs most projects actually have. Reading the
    whole .py as prose instead would feed executable lines to the model as if
    they were claims, which is the fastest way to a report full of noise.
    """
    text = doc.read_text(encoding="utf-8", errors="replace")
    if doc.suffix != ".py":
        return _paragraphs(text)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        ds = ast.get_docstring(node, clean=True)
        if not ds:
            continue
        base = 1 if isinstance(node, ast.Module) else getattr(node, "lineno", 1)
        for off, line in enumerate(ds.split("\n")):
            out.append((base + off, line))
    # plus `#:` comments, the convention for documenting a constant
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if s.startswith("#:") or (s.startswith("# ") and len(s) > 40):
            out.append((i, s.lstrip("#: ")))
    return sorted(out)


def lookup(name: str, syms: dict[str, Symbol]) -> Symbol | None:
    """A name from a spec -> the code it names: symbol, Type.member, or config key."""
    if name in syms:
        return syms[name]
    if name in _BY_NAME:
        return _BY_NAME[name][0]
    return config_lookup(name)


def _mentions(sent: str, syms: dict[str, Symbol]) -> tuple[list[Symbol], list[str]]:
    """Everything a sentence names that exists: routes first, then names by length."""
    found: list[Symbol] = []
    why: list[str] = []
    for verb, path in ROUTE_RE.findall(sent):
        path = path.rstrip(".")
        for s in route_lookup(verb, path):
            if s not in found:
                found.append(s); why.append(f"`{s.name}`")
    for path in PATH_RE.findall(sent):
        if not any(path in w for w in why):
            for s in route_lookup(None, path):
                if s not in found:
                    found.append(s); why.append(f"`{s.name}`")
    names = {m.group(1) or m.group(2) for m in IDENT.finditer(sent)}
    for n in sorted(names, key=len, reverse=True):
        s = lookup(n, syms)
        if s is not None and s not in found:
            found.append(s); why.append(f"`{n}`")
    return found, why


_CODE_LINE = re.compile(r'[=<>]=|->|\bf"|\{[a-z_]+[.\[]|\breturn\b|\bdef\b|\bimport\b')


def spec_sentences(doc: Path, min_len: int = 5, code_line: re.Pattern = _CODE_LINE):
    """(line, sentence) for every sentence that could be a requirement: not a
    heading, not inside a code fence, at least `min_len` words, not code.

    Two shapes need help before they read as requirements at all — found by running this
    tool on its own PRIVACY.md, where they produced three "??" results out of four claims:

    * A markdown **table row** is a requirement written with cell separators. Joining the
      cells gives a sentence ("The spec sentence - as written in your spec map"); leaving
      the `|` in gives a fragment no model can judge. The header row is labels, not a
      requirement, so only rows after the `|---|` separator are taken.
    * A **list item** under a heading like "What is never sent" carries its predicate in
      that heading: "Code that no requirement in the map points at." means nothing alone.
      When the heading is a statement rather than a label, it is put back on the front of
      the item's first sentence - the later sentences of the item stand on their own.
    """
    in_fence = False
    heading = ""        # the nearest heading, for list items whose predicate lives in it
    in_table = False    # past a table's |---| separator, so the rows are its body
    for lineno, raw in prose_blocks(doc):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            in_table = False
            continue
        if stripped.startswith("#"):
            heading, in_table = stripped.lstrip("#").strip(), False
            continue
        # Only a TOP-LEVEL item takes the heading: a nested item's predicate comes from the
        # item above it, so prefixing the heading there is noise.
        item = bool(_LIST_ITEM.match(stripped)) and not raw[:1].isspace()
        first = True
        for sent in SENT_SPLIT.split(raw):
            sent = sent.strip()
            if _TABLE_SEP.match(sent):
                in_table = True
                continue
            if sent.startswith("|"):
                if not in_table:            # the header row: column labels, not a requirement
                    continue
                cells = [c.strip() for c in sent.strip().strip("|").split("|") if c.strip()]
                sent = " - ".join(cells)
            sent = " ".join(sent.strip(" -*|#>").split())
            if first and item and _STEM_HEADING.search(heading):
                sent, first = f"{heading}: {sent}", False
            if len(sent.split()) >= min_len and (ROUTE_RE.search(sent) or not code_line.search(sent)):
                yield lineno, sent


def find_claims(doc: Path, syms: dict[str, Symbol], min_len: int = 5,
                unpaired: list | None = None) -> list[Claim]:
    """A sentence is checkable when it names a symbol, route or config key that exists.
    Sentences that name nothing we can find go to `unpaired`, so they can be listed:
    silently skipping them reads as "the whole spec was covered"."""
    out: list[Claim] = []
    for lineno, sent in spec_sentences(doc, min_len):
        # Pair with EVERY named thing. Picking only the longest name once
        # showed the model `token_urlsafe(TOKEN_BYTES)` but hid
        # `TOKEN_BYTES = 32` — the one line the claim was actually about.
        found, why = _mentions(sent, syms)
        if not found:
            if unpaired is not None:
                unpaired.append((lineno, sent))
            continue
        out.append(Claim(text=sent[:400], doc=str(doc), line=lineno, symbols=found,
                         why_paired="names " + ", ".join(why), numbers=NUMBER.findall(sent)))
    return out


# ─────────────────────────────────────────── 2b. do the arithmetic ourselves

_UNITS = [(86400 * 365, "years"), (86400 * 7, "weeks"), (86400, "days"), (3600, "hours"), (60, "minutes")]


def _human(n: int) -> str:
    """A number of seconds, if that is plausibly what it is, in plain units."""
    for size, name in _UNITS:
        if n >= size and n % size == 0:
            k = n // size
            return f"{k} {name[:-1] if k == 1 else name}"
    return ""


def _human_bytes(n: int) -> str:
    for size, name in ((1 << 30, "GiB"), (1 << 20, "MiB"), (1 << 10, "KiB")):
        if n >= size and n % size == 0:
            return f"{n // size} {name}"
    return ""


def _human_ms(n: int) -> str:
    if n >= 1000 and n % 1000 == 0:
        s = n // 1000
        return _human(s) or f"{s} second{'s' if s != 1 else ''}"
    return ""


_C_EXPR = re.compile(r"(?<![\w.])[(\d][\dxXa-fA-F_lL\s()*+\-/<>|&^~]*[\dlL)]")
_DURATION_NAME = re.compile(r"(?i)(ms|millis|milliseconds?|timeout|ttl|interval|delay|seconds?|secs?|"
                            r"duration|expir\w*|period|window|max[-_]?age|backoff)")
_BYTES_NAME = re.compile(r"(?i)(bytes|size|kb|mb|gb|capacity|buffer)")
_NAMED_NUMBER = re.compile(r"\b([A-Za-z_][\w]*)\s*(?::\s*[\w<>\[\]|]+\s*)?[:=]\s*(\d[\d_]{3,})[lLnN]?\b")


def _c_expressions(source: str) -> str:
    """Numeric expressions in C-family code, rewritten as Python ones.

    `2L * 1024 * 1024` -> `2 * 1024 * 1024`; `1_000` -> `1000`. Anything that
    then fails to parse as a Python expression is simply skipped.
    """
    out = []
    for line in mask_c_family(source, strings=True).split("\n"):
        for m in _C_EXPR.finditer(line):
            e = re.sub(r"(?<=[0-9a-fA-F])_(?=[0-9a-fA-F])", "", m.group(0))
            e = re.sub(r"(?<=[0-9a-fA-F])[lLnN](?![\w])", "", e).strip()
            try:
                ast.parse(e, mode="eval")
            except SyntaxError:
                continue
            out.append(e)
    return "\n".join(out)


def _named_numbers(source: str) -> list[str]:
    """`timeoutMs = 30000` -> "30 seconds". Only where the NAME says what unit the
    number is in: the model cannot convert, and a readout for every number
    (port 3000 = "3 seconds") would be noise."""
    out = []
    for name, digits in _NAMED_NUMBER.findall(source):
        n = int(digits.replace("_", ""))
        if _DURATION_NAME.search(name):
            if re.search(r"(?i)ms|millis", name):
                h = _human_ms(n)
                if h:
                    out.append(f"`{name}` = {n:,} milliseconds = {h}")
            elif re.search(r"(?i)sec", name):
                if (h := _human(n)):
                    out.append(f"`{name}` = {n:,} seconds = {h}")
            else:
                notes = [f"{h} if milliseconds" for h in [_human_ms(n)] if h] + \
                        [f"{h} if seconds" for h in [_human(n)] if h]
                if notes:
                    out.append(f"`{name}` = {n:,}  (= {'; = '.join(notes)})")
        elif _BYTES_NAME.search(name) and (h := _human_bytes(n)):
            out.append(f"`{name}` = {n:,} bytes = {h}")
    return out


def resolve_arithmetic(source: str, suffix: str = ".py") -> list[str]:
    """Evaluate every constant-only expression in `source` and state the result.

    Jev cannot do arithmetic. Leaving `30 * 24 * 3600` for it to interpret made
    it call a "7 days" claim accurate. So the code does the sum and the model
    only has to compare "30 days" with "7 days" — which it can do.
    """
    named = _named_numbers(source)
    unit_of: dict[str, str] = {}                 # expression -> "ms" / "s", from the name it is assigned to
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*(?::\s*[\w<>\[\]|]+\s*)?[:=]\s*([^,;\n]+)", source):
        nm, rhs = m.group(1), re.sub(r"(?<=\d)_(?=\d)|(?<=\d)[lLnN]\b", "", m.group(2))
        if re.search(r"(?i)ms$|millis", nm):
            unit_of[" ".join(rhs.split())] = "ms"
        elif re.search(r"(?i)sec(ond)?s?$", nm):
            unit_of[" ".join(rhs.split())] = "s"
    if suffix in C_FAMILY:
        source = _c_expressions(source)
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return named
    def const_only(n: ast.AST) -> bool:
        return isinstance(n, ast.BinOp) and all(
            isinstance(x, (ast.Constant, ast.BinOp, ast.UnaryOp, ast.operator, ast.unaryop))
            for x in ast.walk(n))

    # Only the OUTERMOST constant expression. Reporting `30 * 24 = 720` as well
    # would invite "720 seconds = 12 minutes" — a wrong reading we'd be feeding in.
    inner: set[int] = set()
    for n in ast.walk(tree):
        if const_only(n):
            for child in ast.walk(n):
                if child is not n:
                    inner.add(id(child))
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not const_only(node) or id(node) in inner:
            continue
        try:
            expr = ast.unparse(node)
            val = eval(compile(ast.Expression(node), "<expr>", "eval"), {"__builtins__": {}}, {})
        except Exception:
            continue
        if not isinstance(val, (int, float)) or expr in found:
            continue
        whole = isinstance(val, int) or float(val).is_integer()
        flat = re.sub(r"[\s(){}\[\]]", "", expr)
        unit = next((u for rhs, u in unit_of.items() if re.sub(r"[\s(){}\[\]]", "", rhs) == flat), None)
        notes = []
        if whole and unit != "ms" and (human := _human(int(val))):
            notes.append(f"= {human} if this is seconds" if unit is None else f"= {human}")
        if whole and unit != "s" and (suffix in C_FAMILY or unit == "ms") and (ms := _human_ms(int(val))):
            notes.append(f"= {ms} if this is milliseconds" if unit is None else f"= {ms}")
        if whole and (size := _human_bytes(int(val))):
            notes.append(f"= {size} if this is bytes")
        found[expr] = f"`{expr}` = {val:,}" + (f"  ({'; '.join(notes)})" if notes else "")
    return list(found.values()) + named



# ───────────────────────────── 2c. prose specs: an explicit spec -> code map

WORD = re.compile(r"[A-Za-z]{3,}")
STOP = set("the and for are with that this from have has was were will shall must should can "
           "not any all its into when then than their there which each user users".split())


def _parts(name: str) -> set[str]:
    """create_session -> {create, session}; SessionExpired -> {session, expired};
    app.orders.max-items -> {app, orders, max, items}; GET /api/orders/{id} -> {api, orders}."""
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    s = re.sub(r"\{[^}]*\}|:\w+|<[^>]*>", " ", s)
    return {w.lower() for w in re.split(r"[\s_.\-/:\[\]()]+", s) if len(w) > 2}


def _ref_of(s: Symbol) -> str:
    if s.kind == "route":
        return f"route:{s.name}"
    if s.kind == "config":
        return f"config:{s.name}"
    return f"{s.file}:{s.name}"


MAP_README = [
    "A map says which code each spec requirement is about. One entry per spec sentence.",
    "Review EVERY entry, then run:  spec_drift.py --map <this file> --dry-run --strict   and then without --dry-run.",
    "text        - the requirement that will be checked. Edit it only to make it clearer.",
    "code        - where the code for it is. One of these, or a list of several:",
    "                route:GET /api/orders/{id}           an endpoint (its handler, wherever it lives)",
    "                config:app.orders.max-items          a setting: its definitions, defaults, and the places that",
    "                                                     name the key (@Value, process.env.X, os.environ[...]);",
    "                                                     uses through a settings object are NOT found",
    "                src/Orders.java:OrderService.place   a method, class, function or constant in a file",
    "                src/app.ts:120-160                   a line range (any language)",
    "                src/config.py                        a whole file (small files only)",
    "              For a setting, also point at the code that ENFORCES it, not just the setting.",
    "status      - 'named in the sentence' and 'suggested' are the tool's guesses ('suggested' ones are",
    "              often wrong). Set it to 'reviewed' once you have checked the entry, or to 'excluded'",
    "              if the sentence is not a requirement (rationale, history, plans, examples).",
    "              An excluded entry needs no code and is never sent; it records that someone decided,",
    "              so --strict does not report the sentence as unchecked. Say why in 'why'.",
    "why         - your note: why this code, or why the sentence is excluded. Not sent anywhere.",
    "alternatives- other candidates, for your information. Not sent anywhere.",
    "spec, line, spec_text - where the sentence came from. spec_text is a copy of the spec text you",
    "              reviewed, used only to notice when the spec changes afterwards. If the tool says the",
    "              spec changed, re-check the entry, then paste the current spec paragraph (or the lines",
    "              of a code block) into spec_text - markdown and line breaks are fine.",
    "Deleting an entry also works, but --strict then reports its sentence as not in the map.",
    "specs       - (top level) the spec file(s) this map was drafted from - the one(s) the user named as current.",
    "confirmed_current - (top level, optional) spec files the USER confirmed are current although a line near",
    "              their top reads as if they were out of date (a line about something else). Listed there, that",
    "              line is a warning instead of a problem. Add a file only on the user's word.",
    "              A check warns when a newer version of one appears in the project, and refuses to run when",
    "              one says at its top that it is superseded, deprecated or obsolete.",
]


def draft_map(docs: list[Path], syms: dict[str, Symbol], out: Path) -> int:
    """Suggest a code location for every spec sentence, for a human to review.

    Real specs describe behaviour in prose and rarely name functions, so they
    cannot be paired automatically with confidence. Named routes, config keys
    and symbols are suggested first; everything else by word overlap. A person
    confirms or corrects each line.
    """
    pool: list[Symbol] = [s for s in _BY_FILE.values()
                          if not (s.kind == "function" and s.name.count(".") == 1
                                  and s.name.split(".")[0] == s.name.split(".")[1])]      # not constructors
    pool += [s for v in _ROUTES.values() for s in v] + list(_CONFIG.values())
    inv: dict[str, list[int]] = {}
    for i, s in enumerate(pool):
        for w in _parts(s.name):
            inv.setdefault(w, []).append(i)
    entries = []
    for d in docs:
        paragraphs = dict(prose_blocks(d))
        for lineno, sent in spec_sentences(d):
            words = {w.lower() for w in WORD.findall(sent)} - STOP
            if not words:
                continue
            named, _ = _mentions(sent, syms)
            score: dict[int, float] = {}
            for w in words:
                hits = inv.get(w, ())
                weight = 1.0 + 1.0 / (1 + len(hits) / 5)          # a rare word says more than a common one
                for i in hits:
                    score[i] = score.get(i, 0) + weight
            top = heapq.nlargest(200, score, key=lambda i: (score[i], pool[i].kind != "config"))
            ranked = sorted(top, key=lambda i: (-score[i], pool[i].kind == "config", pool[i].name))
            # Main code first. Descriptive test names ("returnsCachedOrderWhenStockUnchanged...")
            # share more words with prose than the code they test, and outrank it;
            # the best test is still offered, as an alternative.
            main = [pool[i] for i in ranked if not _is_test(pool[i].file)][:2]
            test = [pool[i] for i in ranked if _is_test(pool[i].file)][:1]
            best = named + [s for s in (main + test if main else test) if s not in named]
            entries.append({
                "spec": str(d), "line": lineno, "text": sent[:400],
                "code": _ref_of(best[0]) if best else "",
                "status": ("named in the sentence" if named else "suggested") if best
                          else "NO MATCH - point 'code' at what enforces this, or set 'excluded' with a why",
                "alternatives": [_ref_of(s) for s in best[1:4]],
                "spec_text": _norm_text(paragraphs.get(lineno, sent)),
            })
    out.write_text(json.dumps({"_readme": MAP_README, "specs": [Path(d).as_posix() for d in docs],
                               "entries": entries}, indent=1, ensure_ascii=False))
    named = sum(1 for e in entries if e["status"] == "named in the sentence")
    guessed = [e for e in entries if e["status"] == "suggested"]
    print(f"wrote {len(entries)} spec sentences to {out}")
    print(f"  {named} name a route, config key or code in backticks - usually right, still check them")
    print(f"  {len(guessed)} have a GUESS by word overlap - often wrong: lines "
          + ", ".join(str(e["line"]) for e in guessed[:25]) + (" ..." if len(guessed) > 25 else ""))
    print(f"  {sum(1 for e in entries if not e['code'])} have no suggestion")
    print(f"\nNext: open {out}; its \"_readme\" explains every field. Fix each \"code\" and set \"status\" to\n"
          f"\"reviewed\"; for sentences that are not requirements set \"status\" to \"excluded\" with a \"why\".\n"
          f"Then check it loads:  --map {out} --dry-run --strict")
    return len(entries)


def _norm_text(t: str) -> str:
    """For comparing spec wording: no markdown emphasis, numbering or spacing differences."""
    t = re.sub(r"[*_`>]", "", t)
    t = re.sub(r"^\s*(?:[-+]|\d+[.)]|[a-z][.)])\s+", "", t)
    return " ".join(t.split()).lower()


def _snap(t: str) -> str:
    """A spec_text as written in a map - normalised already, or pasted from the spec with
    markdown and line breaks - in the form the spec is searched in."""
    return " ".join(n for n in (_norm_text(ln) for ln in str(t).split("\n")) if n)


def _spec_index(doc: Path) -> tuple[str, list[int], list[int]]:
    """The spec as one normalised string, plus where each line starts in it. A snapshot can
    then span a hard-wrapped paragraph, several paragraphs, or the lines of a code block."""
    parts, starts, lines, pos = [], [], [], 0
    for ln, t in prose_blocks(doc):
        if n := _norm_text(t):
            parts.append(n); starts.append(pos); lines.append(ln)
            pos += len(n) + 1
    return " ".join(parts), starts, lines


def _find_snapshot(index: tuple[str, list[int], list[int]], snap: str, near: int = 0) -> int | None:
    """The spec line where `snap` starts (the occurrence closest to line `near`), or None
    if the spec no longer contains it."""
    text, starts, lines = index
    found, at = [], text.find(snap) if snap else -1
    while at >= 0:
        found.append(lines[bisect.bisect_right(starts, at) - 1])
        at = text.find(snap, at + 1)
    return min(found, key=lambda ln: abs(ln - near)) if found else None


_VERB_RE = re.compile(r"\s*(?:(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|ANY|WS)\s+)?(\S+)\s*$", re.I)
_SECRET_FILE = re.compile(r"^\.env(?:\..+)?$|\.(?:pem|key|p12|jks|pfx)$|^id_(?:rsa|ed25519|ecdsa)$")


def _close(word: str, options) -> str:
    import difflib
    near = difflib.get_close_matches(word, list(options), n=3, cutoff=0.6)
    return f" Did you mean: {', '.join(near)}?" if near else ""


def _read_ref(ref: str, syms: dict[str, Symbol], bases: list[Path] | None = None,
              problems: list | None = None, where: str = "") -> Symbol | None:
    """route:GET /orders/{id}  |  config:app.orders.max-items  |  file:Symbol  |  file:120-160  |  file

    File paths are tried against each of `bases` in turn (the folder you run in,
    --src, the map's folder). A .env file, a key file, or anything outside those
    folders is refused: a map must never be able to send a secret."""
    def fail(msg: str) -> None:
        text = f"{where + ': ' if where else ''}{msg}"
        if problems is None:
            print(f"  WARNING: {text}")
        else:
            problems.append(text)

    if ref.startswith("route:"):
        m = _VERB_RE.match(ref[6:])
        found = route_lookup(m.group(1), m.group(2)) if m else []
        if not found:
            names = {s.name for v in _ROUTES.values() for s in v}
            fail(f"route {ref[6:].strip()!r} not found among {len(names)} routes." + _close(ref[6:].strip(), names))
            return None
        if len(found) == 1:
            return found[0]
        return Symbol(ref[6:].strip(), "route", found[0].file, found[0].line,
                      loader=lambda fs=found: "\n\n".join(s.source for s in fs))
    if ref.startswith("config:"):
        s = config_lookup(ref[7:].strip())
        if s is None:
            fail(f"config key {ref[7:].strip()!r} not found." + _close(ref[7:].strip(), [c.name for c in _CONFIG.values()]))
        return s
    file, _, target = ref.partition(":")
    bases = bases or [Path.cwd()]
    path = next((b / file for b in bases if (b / file).is_file()), None)
    if path is None:
        fail(f"file {file!r} not found (looked in: {', '.join(str(b.resolve()) for b in dict.fromkeys(bases))})")
        return None
    rp = path.resolve()
    if _SECRET_FILE.search(rp.name) and not _ENV_TEMPLATES.match(rp.name):
        fail(f"{file!r} looks like a secrets file - refused, never sent")
        return None
    if not any(rp.is_relative_to(b.resolve()) for b in bases):
        fail(f"{file!r} is outside the project folders - refused")
        return None
    if target and (s := _BY_FILE.get((str(rp), target))):
        return s
    text = strip_comments(path, path.read_text(encoding="utf-8", errors="replace"))
    if _is_config_file(path):
        text = redact_config_text(text)
    lines = text.split("\n")
    if m := re.fullmatch(r"(\d+)-(\d+)", target or ""):
        a, b = int(m.group(1)), int(m.group(2))
        if a < 1 or b < a or a > len(lines):
            fail(f"line range {a}-{b} is outside {file} ({len(lines)} lines)")
            return None
        return Symbol(ref, "lines", _shown(path), a, tidy("\n".join(lines[a - 1:b]))[:MAX_CODE_CHARS])
    if target:
        names = [n for (f, n) in _BY_FILE if f == str(rp)]
        fail(f"{target!r} not found in {file}." + (_close(target, names) or
             (f" It has: {', '.join(names[:8])}" if names else "")))
        return None
    return Symbol(file, "file", _shown(path), 1, tidy("\n".join(lines))[:MAX_CODE_CHARS])


def _shown(path: Path) -> str:
    """A path as it may appear in a payload: relative to where you run, never your home folder."""
    rel = os.path.relpath(path.resolve(), Path.cwd())
    return rel if not rel.startswith("..") else path.name


def load_map(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Stop(f"{path} is not valid JSON: {e.msg} at line {e.lineno}, column {e.colno}. "
                   f"A trailing comma or a missing quote is the usual cause.") from None
    except UnicodeDecodeError as e:
        raise Stop(f"{path} is not UTF-8 text (byte {e.start} cannot be read), so it is not a map. Save it as "
                   f"UTF-8.") from None
    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise Stop(f"{path} should hold a list of entries (or {{\"entries\": [...]}}), as --draft-map writes.")
    return entries


def _as_line(value) -> int:
    """A map entry's "line" as a line number: a hand-edited "12" is 12; missing, null or anything
    that is not a whole number is 0 (unknown), so a claim's line is always a number."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def claims_from_map(path: Path, syms: dict[str, Symbol], src: Path | None = None,
                    problems: list | None = None) -> list[Claim]:
    """Claims from a reviewed map. An entry that cannot be used is NOT checked, and
    says why in `problems` - never silently dropped."""
    def fail(msg: str) -> None:
        if problems is None:
            print(f"  WARNING: {msg}")
        else:
            problems.append(msg)

    bases = list({b.resolve(): b for b in [Path.cwd(), src or Path.cwd(), path.parent]}.values())
    spec_cache: dict[str, tuple] = {}
    covered: dict[str, set] = {}
    out, unreviewed, moved, nosnap = [], 0, 0, 0
    excluded, no_reason, stale_excluded = [], [], []
    for i, e in enumerate(load_map(path), 1):
        if not isinstance(e, dict):
            fail(f"map entry {i} is not an object - not checked"); continue
        where = f"map entry {i} ({e.get('spec', '?')}:{e.get('line', '?')})"
        is_excluded = str(e.get("status", "")).strip().lower() == "excluded"
        refs = [e["code"]] if isinstance(e.get("code"), str) else list(e.get("code") or [])
        refs = [r for r in refs if r]
        if not refs and not is_excluded:
            fail(f"{where} has no \"code\" - NOT checked. Fill it in, or if the sentence is not a requirement "
                 f"set \"status\": \"excluded\" and say why in \"why\"."); continue
        spec_file = next((b / e["spec"] for b in bases
                          if isinstance(e.get("spec"), str) and e["spec"] and (b / e["spec"]).is_file()), None)
        if e.get("spec") and spec_file is None:
            fail(f"{where}: spec file {e['spec']!r} not found - NOT checked."); continue
        line = _as_line(e.get("line"))
        text = e.get("text")
        if not text and spec_file is not None and line:
            spec_lines = spec_file.read_text(encoding="utf-8", errors="replace").split("\n")
            text = spec_lines[line - 1].strip(" -*|#") if line <= len(spec_lines) else None
        if not isinstance(text, str) or not text:
            fail(f"{where} has no \"text\" - NOT checked."); continue
        if spec_file is not None:
            if str(spec_file) not in spec_cache:          # not setdefault(): that would parse the spec every time
                spec_cache[str(spec_file)] = _spec_index(spec_file)
            index = spec_cache[str(spec_file)]
            snap = _snap(e.get("spec_text") or "")
            norm = _norm_text(text)
            verbatim = _find_snapshot(index, norm) is not None
            if snap:
                hit = _find_snapshot(index, snap, line if isinstance(line, int) else 0)
                if hit is None and is_excluded:
                    stale_excluded.append(line); continue
                if hit is None:
                    fail(f"{where}: the spec changed since this entry was reviewed - NOT checked. "
                         f"Review the entry against the current spec, then update its text, and paste the "
                         f"current spec paragraph into spec_text."); continue
                if hit != line:
                    moved += 1
                    line = hit
            elif not verbatim:
                nosnap += 1
            # An entry always covers its own sentence - including when that sentence is one the
            # reader assembles (a table row joined from its cells, a list item carrying the heading
            # that holds its predicate), which is not word-for-word anywhere in the file. Only a
            # paraphrase ALSO stands for the whole snapshot; otherwise mapping one sentence would
            # count every other sentence in its paragraph as covered.
            here = covered.setdefault(str(spec_file), set())
            here.add(norm)
            if not verbatim and snap:
                here.add(snap)
        if is_excluded:
            excluded.append(line)
            if not str(e.get("why") or "").strip():
                no_reason.append(line)
            continue
        found = [_read_ref(r, syms, bases, problems, where) for r in refs]
        if not all(found):
            fail(f"{where} - NOT checked: {sum(1 for f in found if f is None)} of its {len(refs)} code "
                 f"reference(s) could not be resolved (see above)."); continue
        if str(e.get("status", "reviewed")).lower() != "reviewed":
            unreviewed += 1
        out.append(Claim(text=text, doc=e.get("spec", str(path)), line=line, symbols=found, why_paired="from map",
                         map_line=_as_line(e.get("line")) or None))
    MAP_COUNTS.update(excluded=len(excluded), moved=moved)
    notes = []
    if no_reason:
        notes.append(f"{len(no_reason)} excluded entries do not say why (lines "
                     + ", ".join(str(ln) for ln in no_reason[:15]) + (" ..." if len(no_reason) > 15 else "")
                     + ") - add a \"why\" so a reviewer can see it was a decision")
    if stale_excluded:
        notes.append(f"{len(stale_excluded)} excluded sentences have changed in the spec (were at lines "
                     + ", ".join(str(ln) for ln in stale_excluded[:15])
                     + (" ..." if len(stale_excluded) > 15 else "")
                     + ") - decide again whether each is a requirement, then update its spec_text")
    if unreviewed:
        notes.append(f"{unreviewed} map entries are not marked \"status\": \"reviewed\" - a real run checks them "
                     f"as they are, and word-overlap guesses are often wrong")
    if moved:
        print(f"  note: {moved} entries' sentences moved to a new line in the spec; the new line numbers are shown")
    if nosnap:
        notes.append(f"{nosnap} entries have no spec_text and their text is not word-for-word in the spec, so a "
                     f"spec change cannot be ruled out - paste the spec paragraph each one is about into its "
                     f"spec_text")
    for f, texts in covered.items():
        missing = [(ln, snt) for ln, snt, n in ((ln, snt, _norm_text(snt)) for ln, snt in spec_sentences(Path(f)))
                   if not any(n in t or t in n for t in texts)]
        if missing:
            notes.append(f"{len(missing)} sentences in {os.path.relpath(f)} are not in the map, so NOT checked: lines "
                         + ", ".join(str(ln) for ln, _ in missing[:15]) + (" ..." if len(missing) > 15 else ""))
    MAP_NOTES[:] = notes
    for n in notes:
        print(f"  note: {n}")
    return out


MAP_NOTES: list[str] = []      # coverage and review notes from the last map load (--strict turns them into problems)
MAP_COUNTS: dict[str, int] = {"excluded": 0, "moved": 0}

# ─────────────────────────────────────────── 2b. which spec file is the current one
#
# A project can hold several spec documents, or several versions of one: spec-v1.md next to
# spec-v2.md, a copy in archive/, a dated snapshot, a file whose first lines say it was
# superseded. The map is the only record of what is checked, so an outdated file in it means
# the code is compared with requirements nobody holds any more - silently. So: list the
# candidates for the user to choose from, refuse a folder that mixes versions, warn about a
# named file that looks old, and tell every check when the spec it checks is no longer current.
import datetime as _datetime  # noqa: E402
import subprocess as _subprocess  # noqa: E402
import threading as _threading  # noqa: E402
from pathlib import PurePosixPath  # noqa: E402

SPEC_SUFFIXES = (".md", ".rst")
HEAD_LINES = 40                  # a document says it is superseded at its top, if anywhere
_HISTORY_WORDS = frozenset("old archive archived archives deprecated obsolete superseded legacy backup backups bak "
                           "previous prev history outdated".split())
# Words that mark another edition of the same document without saying it is old: they are left
# out of the family key only, and never reported as a sign of age.
_EDITION_WORDS = frozenset("new latest final copy updated revised".split())
_SPEC_WORDS = frozenset("spec specs specification specifications requirement requirements design designs "
                        "architecture adr adrs decision decisions rfc rfcs prd prds srs proposal proposals api "
                        "apis pep peps".split())
_DATE_TOKEN = re.compile(r"(?<!\d)((?:19|20)\d\d)([-_.]?)(0[1-9]|1[0-2])(?:\2(0[1-9]|[12]\d|3[01]))?(?!\d)")
# A pre-release belongs to its version: spec-2.0-rc1.md and v1.10.0-next.0-changelog.md are versions
# of spec.md and of the changelog, older than 2.0 and 1.10.0. Oldest kind first. The word must have a
# number after it or end the name: api-v2-dev-guide.md is a developer guide, not a pre-release.
_PRERELEASE = ("dev", "alpha", "beta", "pre", "preview", "next", "rc")
_VERSION_TOKEN = re.compile(r"(?:^|(?<=[-_.\s]))(?:(?:v|ver|version|rev|revision)[-_\s]?(\d+(?:\.\d+)*)"
                            r"|(\d+(?:\.\d+)+))(?:[-_.]?(dev|alpha|beta|preview|pre|next|rc)(?:[-_.]?(\d+)|$))?"
                            r"(?=$|[-_.\s])", re.I)

# How the top of a document says that it is no longer the current one.
_OLD = r"(?:superseded|deprecated|obsolete|outdated|retired|archived|replaced|withdrawn|reverted)"
_NO_LONGER = (r"no\s+longer\s+(?:current|valid|maintained|in\s+use|used|accurate|applies|applicable|"
              r"up[-\s]to[-\s]date)")
# Quote, admonition, emphasis - not list items. An emphasis mark must be followed by text, never by
# another mark: otherwise a line of 35 stars (a Sphinx title's underline) is split every possible
# way before the match fails, and that takes minutes.
_BANNER_MARKS = r"(?:>\s*|\[!\w+\]\s*|[*_]{1,3}(?=[^\s*_]))*"
_BANNER_END = r"[*_`]*\s*(?:$|[:.,;!()\[\]|–—-]|\s+(?:by|in\s+favou?r\s+of|see|use)\b)"
_LATER = r"(?:ultimately|finally|later|eventually|since|subsequently)"
_DOC_NOUN = r"(?:document|doc|page|spec|specification|design|adr|rfc|proposal|decision|prd|srs|requirements)"
_DECLARATIONS = [
    # "Status: Superseded by ADR-7", "- **Status:** deprecated", "| Status | Obsolete |", "status: accepted,
    # superseded by ADR-9", "Status: Proposed, accepted, reconsidered, and ultimately reverted.", YAML front matter
    re.compile(rf"^\s*(?:[>*_|-]\s*)*status\s*[*_]*\s*[:=|]\s*[*_`]*\s*(?:(?:{_OLD}|{_NO_LONGER}){_BANNER_END}"
               rf"|\w+\s*[,;(]\s*superseded\s+by\b|[^|]*?[,;]\s*(?:and\s+)?{_LATER}\s+[*_]*{_OLD}{_BANNER_END})",
               re.I),
    re.compile(r"^\s*(?:deprecated|obsolete|superseded|archived|outdated)\s*:\s*(?:true|yes)\s*$", re.I),
    # "> **Deprecated:** see v2", "Superseded by spec-v2.md", "OBSOLETE", "No longer maintained."
    # Only where a paragraph starts, or after a quote or emphasis mark (see declared_old).
    re.compile(rf"^\s*{_BANNER_MARKS}(?:(?:note|warning|important|caution|attention)[*_]*\s*:?\s*[*_]*\s*)?"
               rf"(?:{_OLD}|{_NO_LONGER}){_BANNER_END}", re.I),
    # "This document is obsolete", "This spec has been superseded by ...", "This page is no longer
    # maintained", "This RFC was previously approved, but later withdrawn". Only "this": "the file is
    # archived after 30 days" is a requirement, not a status. Never a part of it: "This RFC was
    # previously approved, but part of it later withdrawn", "Part of this RFC was later withdrawn".
    # The look ahead for "part" reads at most 300 characters: unbounded, it read to the end of the
    # sentence at every "this spec", and a long line that repeats it took minutes.
    re.compile(rf"\bthis\s+{_DOC_NOUN}\b[^.;]{{0,80}}?\b(?:is|was|are|were|has\s+been|have\s+been)\s+(?:now\s+)?"
               rf"(?:{_OLD}|{_NO_LONGER})\b"
               rf"|(?<!\bpart of )(?<!\bparts of )\bthis\s+{_DOC_NOUN}\b"
               rf"(?![^.;]{{0,300}}\b(?:part|parts|partly|partially|mostly|largely)\b)"
               rf"[^.;]{{0,80}}?\b{_LATER}\s+(?:been\s+)?[*_]*{_OLD}\b", re.I),
]
# A header field that names what replaced the document: "Superseded-By: 3333" (a PEP's header). It
# counts anywhere in the header block, not only where a paragraph starts.
_FIELD_BY = re.compile(r"^\s*(?:superseded|replaced|obsoleted)[-_ ]by\s*:\s*\S", re.I)
# A template's empty field says nothing: "Superseded by: N/A", "| Replaced by | - |", "Superseded-By:
# <pep number>". One run of marks, then at most one placeholder: no two parts of the pattern can take
# the same characters, so a long line cannot make the search slow.
_EMPTY_BY = re.compile(r"\b(?:by|favou?r\s+of)[\s*_`|:=]*(?:(?:n/?a|none|nothing(?:\s+yet)?|tbd|null|-+|–|—|~|"
                       r"<[^>/@]*>)[\s*_`|]*)?$", re.I)
# After such a line the next line starts a new paragraph, as it does after a blank line: a lone HTML
# tag, an admonition (:::, !!!, ???) or an RST directive (".. note::").
_BLOCK_OPENER = re.compile(r"^\s*(?:</?[A-Za-z][^>]*>\s*$|:::|!!!|\?\?\?|\.\.\s+[\w-]+::)")
_TITLE_MARK = re.compile(rf"[(\[]\s*(?:{_OLD}|{_NO_LONGER})\s*[)\]]|[-–—:|]\s*[*_]*(?:{_OLD}|{_NO_LONGER})"
                         rf"[*_]*\s*$", re.I)
_UNDERLINE = re.compile(r"^\s*([=\-~^*#+`])\1{2,}\s*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def _name_tokens(name: str) -> tuple[list, list, list[str]]:
    """What one file or folder name says about its age: (dates, versions, other words). Dates are
    real calendar dates only; a bare number is not a version (0001-use-postgres.md is decision 1,
    not version 1 of anything)."""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=v\d)", " ", name)
    dates: list = []
    versions: list = []

    def date(m: re.Match) -> str:
        year, sep, month, day = m.group(1), m.group(2), m.group(3), m.group(4)
        if not sep and day is None:
            return m.group(0)                     # 202405 is not how anyone writes a date
        try:
            when = _datetime.date(int(year), int(month), int(day or 1))
        except ValueError:
            return m.group(0)                     # 2024-02-30
        if not 1990 <= when.year <= _datetime.date.today().year + 1:
            return m.group(0)
        dates.append((when, m.group(0)))
        return " "

    def version(m: re.Match) -> str:
        numbers = tuple(int(x) for x in (m.group(1) or m.group(2)).split("."))
        numbers += (0,) * (8 - len(numbers))
        pre = (0, _PRERELEASE.index(m.group(3).lower()), int(m.group(4) or 0)) if m.group(3) else (1,)
        versions.append((numbers + pre, m.group(0).strip("-_. ")))     # (sort key, as written)
        return " "
    s = _VERSION_TOKEN.sub(version, _DATE_TOKEN.sub(date, s))
    return dates, versions, [w.lower() for w in re.split(r"[^A-Za-z0-9]+", s) if w]


def _age_words(words: list[str]) -> list[str]:
    """The words of one name that mark it as an old copy - old, archive, legacy and the like - when
    such a word is the whole name, or its first or last word (words such as copy or new are not
    counted). In the middle it is the name's subject: infra-database-backups-bucket is a bucket for
    backups and no-deprecated-bui-tokens a lint rule, not old copies of anything."""
    core = [w for w in words if w not in _EDITION_WORDS]
    return [w for k, w in enumerate(core) if w in _HISTORY_WORDS and k in (0, len(core) - 1)]


_INDEX_NAMES = frozenset("readme index contents".split())


def _segments(rel: str) -> list[tuple[str, str, bool]]:
    """(the part as written, the name to read, is it the file itself) for each part of a path."""
    parts = PurePosixPath(rel).parts
    return [(p, PurePosixPath(p).stem if k == len(parts) - 1 else p, k == len(parts) - 1)
            for k, p in enumerate(parts)]


def _family_word(name: str) -> str:
    core = [w for w in _name_tokens(name)[2] if w not in _EDITION_WORDS]
    return "".join(w for w in core if w not in _age_words(core))


def spec_family(rel: str) -> str:
    """The document a file is a version of: its path with version numbers, dates, words such as
    old/archive/legacy, and separators taken out. docs/spec-v2.md, docs/archive/spec.md and
    docs/2024-05/spec.md are all 'docs/spec'. Numbered documents stay apart: 0001-use-postgres.md
    and 0002-use-redis.md are two decisions, not two versions of one. When nothing of the name is
    left (versions/3.0.0.md) the folder is the family: 'versions/'. A README, index or contents
    file directly in a folder named only by such a word (archive/, _archive_/, old/) is that
    folder's own page, not an old copy of the README above it: _archive_/README.md is
    'archive/readme'. app-legacy/README.md is still a version of app/README.md."""
    segs = _segments(rel)
    words = [_family_word(n) for _, n, last in segs if not last]
    if words and not words[-1] and segs[-1][1].lower() in _INDEX_NAMES and _age_words(_name_tokens(segs[-2][1])[2]):
        words[-1] = "".join(_name_tokens(segs[-2][1])[2])  # the folder's name is only such words: archive/, _old_/
    folder = "/".join(w for w in words if w)
    stem = _family_word(segs[-1][1]) if segs else ""
    if stem:
        return f"{folder}/{stem}" if folder else stem
    return f"{folder}/" if folder else "./"


def _family_key(rel: str) -> str:
    return spec_family(rel).rstrip("/") or "."      # docs/spec.md and docs/spec/v2.md are one family


def path_history(rel: str) -> list[str]:
    """Why a path looks like an old copy, in plain words: a version number, a date, or a word such
    as old or archive, in its name or in one of its folders."""
    out = []
    for seg, name, last in _segments(rel):
        dates, versions, words = _name_tokens(name)
        where = "its name" if last else f"its folder '{seg}'"
        out += [f"{where} has a date ({raw})" for _, raw in dates]
        out += [f"{where} has a version number ({raw})" for _, raw in versions]
        old = list(dict.fromkeys(_age_words(words)))
        if not last and old and words == old[:1]:
            out.append(f"it is in a folder named '{seg}'")
        else:
            out += [f"{where} has the word '{w}'" for w in old]
    return out


# The other words a template's name may have: template.md, 0000-template.md, adr000-template.md,
# 2019-01-01-Proposal-Template.md. email-template.md is a spec about an email, not a template.
_TEMPLATE_WORDS = frozenset("template adr rfc pep proposal decision record spec design doc document madr".split())


def template_name(rel: str) -> str | None:
    """Why a file's name says it is a template to copy, not a document, in plain words; None when
    it does not. A placeholder number (pep-NNNN.rst, adr-XXXX.md), or the word template with only
    a number or a word such as adr or proposal next to it."""
    words = [w for w in re.split(r"[^a-z0-9]+", PurePosixPath(rel).stem.lower()) if w]
    if holder := next((w for w in words if re.fullmatch(r"n{3,}|x{3,}", w)), None):
        return f"its name has the placeholder '{holder.upper()}'"
    if "template" in words and all(w in _TEMPLATE_WORDS or re.fullmatch(r"(?:adr|rfc|pep)?\d+", w) for w in words):
        return "its name has the word 'template'"
    return None


def _read_head(path: Path, n: int = HEAD_LINES) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\r\n") for line, _ in zip(f, range(n))]
    except OSError:
        return []


def _title_index(lines: list[str]) -> int | None:
    """The line of the document's first heading (markdown #, or a line underlined with === or ---)."""
    start = 0
    if lines and lines[0].strip() == "---":                 # YAML front matter
        start = next((i + 1 for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), 0)
    fence = None
    for i in range(start, len(lines)):
        if m := _FENCE.match(lines[i]):
            fence = None if fence and m.group(1)[0] == fence else (fence or m.group(1)[0])
            continue
        if fence or not lines[i].strip():
            continue
        if re.match(r"^\s{0,3}#{1,6}\s+\S", lines[i]):
            return i
        if i + 1 < len(lines) and _UNDERLINE.match(lines[i + 1]) and not _UNDERLINE.match(lines[i]):
            return i
    return None


def _front_matter_end(lines: list[str]) -> int:
    """The index of the line that closes the YAML front matter; 0 when there is none."""
    if lines and lines[0].strip() == "---":
        return next((i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), 0)
    return 0


def _title_says_old(text: str) -> bool:
    """Does a title say the document is old: "Payments spec (DEPRECATED)", "ADR013: [superseded] ..."."""
    return bool(_TITLE_MARK.search(text) or _DECLARATIONS[2].match(text) or _DECLARATIONS[3].search(text))


def declared_old(lines: list[str]) -> tuple[int, str] | None:
    """(line number, the line) where the top of a document says it is superseded, deprecated,
    obsolete, withdrawn, reverted or no longer current; None if it does not. Code blocks are
    skipped, and so is a template's empty field ("Superseded by: N/A"). A spec that talks ABOUT
    deprecated things ("Deprecated endpoints return 410") is not saying that it is deprecated
    itself. A bare "Deprecated." or "Replaced by ..." counts only where a paragraph starts (or after
    a quote or emphasis mark): in the middle of a hard-wrapped paragraph it is the end of a sentence
    ("... until all non-terminal symbols have been / replaced by terminal characters.")."""
    title = _title_index(lines)
    matter = _front_matter_end(lines)
    fence = None
    starts = True                                           # does this line start a paragraph?
    for i, raw in enumerate(lines):
        if m := _FENCE.match(raw):
            fence = None if fence and m.group(1)[0] == fence else (fence or m.group(1)[0])
            starts = True
            continue
        if fence:
            continue
        if not raw.strip() or _UNDERLINE.match(raw):       # a blank line, ---, a title's underline
            starts = True
            continue
        first, starts = starts, bool(_BLOCK_OPENER.match(raw))
        if _EMPTY_BY.search(raw):
            continue
        if 0 < i < matter and (m := re.match(r"\s*title\s*:\s*['\"]?(.+?)['\"]?\s*$", raw, re.I)):
            if _title_says_old(m.group(1)):                 # title: 'ADR013: [superseded] Use node-fetch'
                return i + 1, raw.strip()
            continue
        if i == title:
            if _title_says_old(re.sub(r"^\s{0,3}#{1,6}\s+", "", raw)):
                return i + 1, raw.strip()
            starts = True
            continue
        if raw.lstrip().startswith("#"):
            starts = True
            continue                                        # a section heading ("## Deprecated fields")
        banner = first or raw.lstrip().startswith((">", "[!", "*", "_"))
        if (_DECLARATIONS[0].match(raw) or _DECLARATIONS[1].match(raw) or _FIELD_BY.match(raw)
                or (banner and _DECLARATIONS[2].match(raw)) or _DECLARATIONS[3].search(raw)):
            return i + 1, raw.strip()
    return None


def _title_of(lines: list[str], fields: bool = True) -> str | None:
    """The document's title: its front matter's title, a Title: field of a header block at the top
    (not with fields=False), else its first heading."""
    if lines and lines[0].strip() == "---":
        for ln in lines[1:]:
            if ln.strip() in ("---", "..."):
                break
            if m := re.match(r"\s*title\s*:\s*['\"]?(.+?)['\"]?\s*$", ln, re.I):
                return m.group(1)
    # A header block of "Name: value" fields at the very top, as PEPs and Rust RFCs have ("Title:
    # Style Guide for Python Code", "- Feature Name: `box_syntax`"): their first heading is only
    # "Abstract" or "Summary".
    field = re.compile(r"(?:[-*]\s+)?[A-Za-z][\w -]*:(?:\s|$)")
    if fields and lines and field.match(lines[0]):
        for ln in lines:
            if m := re.match(r"(?:[-*]\s+)?(?:title|feature[-\s]name)\s*:\s*(.+?)\s*$", ln, re.I):
                return m.group(1).strip("`'\" ") or None
            if not ln.strip() or not (field.match(ln) or ln[:1].isspace()):
                break                                       # the end of the header block
    i = _title_index(lines)
    if i is None:
        return None
    return re.sub(r"^\s{0,3}#{1,6}\s+|\s+#+\s*$", "", lines[i]).strip() or None


def _suggests_spec(rel: str, title: str | None) -> bool:
    words = {w for _, name, _ in _segments(rel) for w in _name_tokens(name)[2]}
    if title:
        words |= {w.lower() for w in re.split(r"[^A-Za-z0-9]+", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", title)) if w}
    return bool(words & _SPEC_WORDS)


def _git_list(root: Path, extra: list[str]) -> list[str]:
    r = _subprocess.run(["git", "-C", str(root), "ls-files", "-z", *extra], capture_output=True, timeout=60)
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace")
        if "not a git repository" in err:
            raise LookupError(err)
        raise Stop(f"git could not list this project's files, so no spec file could be looked for: "
                   f"{err.strip()[:200]}")
    # os.fsdecode, not a decode that replaces bytes: a name that is not valid UTF-8 must still name
    # the file on disk (SpecSurvey sets such names aside, see _utf8).
    return [os.fsdecode(p) for p in r.stdout.split(b"\0") if p]


def _doc_listing(root: Path, ignore: tuple[str, ...]) -> tuple[list[str], set[str], bool]:
    """(every .md/.rst file git would commit - tracked, or new and not ignored; the ones git
    tracks; whether this is a git repository). Outside git: every such file outside the ignored
    folders. Symbolic links, files in ignored folders, and tracked files deleted from the working
    tree (git still lists them until the deletion is committed) are never listed."""
    ign = set(ignore)

    def keep(rel: str) -> bool:
        parts = rel.split("/")
        return (PurePosixPath(rel).suffix.lower() in SPEC_SUFFIXES and not any(p in ign for p in parts[:-1])
                and not (root / rel).is_symlink() and (root / rel).is_file())
    try:
        tracked = _git_list(root, [])
        new = _git_list(root, ["-o", "--exclude-standard"])
    except (LookupError, FileNotFoundError):
        walked = (p.relative_to(root).as_posix() for p in _discover(root, ignore))
        return sorted(f for f in walked if keep(f)), set(), False
    except _subprocess.TimeoutExpired:
        raise Stop("git took more than 60 s to list this project's files, so no spec file could be looked "
                   "for.") from None
    return sorted({f for f in tracked + new if keep(f)}), set(tracked), True


def _last_commits(root: Path, paths: list[str], timeout: float = 60) -> tuple[dict[str, int], str | None]:
    """Unix time of the last commit that touched each path - ONE `git log` pass, newest commit
    first, stopped as soon as every path has been seen. Paths git never committed are left out.
    Returns (those times, None) - or, when git log did not get to the end, (what it found, why):
    the paths it had not reached yet may well be committed, so they are unknown, not uncommitted."""
    want, found = set(paths), {}
    if not want:
        return found, None
    cmd = ["git", "-C", str(root), "-c", "core.quotepath=off", "log", "-z", "--relative", "--no-renames",
           "--format=%x01%ct", "--name-only", "--", *(f":(literal){p}" for p in sorted(want))]
    try:
        proc = _subprocess.Popen(cmd, stdout=_subprocess.PIPE, stderr=_subprocess.DEVNULL)
    except OSError as e:
        return found, f"git log could not be run ({e})"
    stopped = _threading.Event()

    def stop() -> None:
        stopped.set()
        proc.kill()
    timer = _threading.Timer(timeout, stop)
    timer.start()
    try:
        buf, when = b"", None
        while len(found) < len(want):
            chunk = proc.stdout.read1(65536)
            if not chunk:
                break
            *tokens, buf = (buf + chunk).split(b"\0")
            for t in tokens:
                t = t.lstrip(b"\n")
                if t.startswith(b"\x01"):
                    when = int(t[1:] or 0)
                elif t and when is not None:
                    name = os.fsdecode(t)                       # as _git_list names it
                    if name in want and name not in found:
                        found[name] = when
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    if stopped.is_set() and len(found) < len(want):
        return found, f"git log was stopped after {timeout:g} s"
    return found, None


def _utf8(name: str) -> bool:
    """Is a file name valid UTF-8? One that is not cannot be written into a map (JSON is UTF-8)
    or shown in a reply, so such a file is named in a warning and never used."""
    try:
        name.encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


def _readable(name: str) -> str:
    """A file name as it can be shown: each byte that is not UTF-8 becomes the replacement mark."""
    return name.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _not_utf8_warning(names: list[str], where: str) -> str | None:
    """The warning for files that were set aside because their names are not valid UTF-8."""
    if not names:
        return None
    return (f"{len(names)} file(s) {where} were left out because their names are not valid UTF-8, so a map "
            f"cannot record them: {', '.join(_readable(n) for n in names)}. Rename them if they are part of the "
            f"spec.")


class SpecSurvey:
    """What a project's documents say about which spec is current: one listing of the documents,
    the top of each file read at most once, one `git log` pass per prefetch."""

    def __init__(self, root: Path, ignore) -> None:
        self.root = Path(root).resolve()
        listed, self.tracked, self.is_git = _doc_listing(self.root, tuple(ignore))
        self.docs = [f for f in listed if _utf8(f)]
        self.not_utf8 = [f for f in listed if not _utf8(f)]     # set aside: see _utf8
        self._known = set(self.docs)
        self._groups: dict[str, list[str]] = {}
        for f in self.docs:
            self._groups.setdefault(_family_key(f), []).append(f)
        self._heads: dict[str, list[str]] = {}
        self._declared: dict[str, tuple[int, str] | None] = {}
        self._commits: dict[str, int] = {}
        self._unknown: dict[str, str] = {}      # committed file -> why its last commit was not found
        self._asked: set[str] = set()

    def head(self, rel: str) -> list[str]:
        if rel not in self._heads:
            self._heads[rel] = _read_head(self.root / rel)
        return self._heads[rel]

    def declared(self, rel: str) -> tuple[int, str] | None:
        if rel not in self._declared:
            self._declared[rel] = declared_old(self.head(rel))
        return self._declared[rel]

    def title(self, rel: str) -> str | None:
        return _title_of(self.head(rel))

    def reasons(self, rel: str) -> list[str]:
        """Every sign that `rel` is an old copy (see path_history), and what its top says."""
        out = path_history(rel)
        if d := self.declared(rel):
            out.append(f"line {d[0]} says it is out of date: \"{d[1]}\"")
        return out

    def marked_old(self, rel: str) -> bool:
        """A word such as old or archive in its path, or its top says it is superseded."""
        return (any(_age_words(_name_tokens(name)[2]) for _, name, _ in _segments(rel))
                or self.declared(rel) is not None)

    def against(self, rel: str) -> list[str]:
        """The signs that count against using `rel`: all of them, except that a version number or a
        date in its path is not held against the newest version of a document."""
        why = self.reasons(rel)
        if why and not self.marked_old(rel) and self.newest(rel)[0] == rel:
            return []
        return why

    def members(self, rel: str) -> list[str]:
        """Every document that looks like a version of the same one, `rel` included."""
        return sorted(set(self._groups.get(_family_key(rel), [])) | {rel})

    def family(self, rel: str) -> str:
        return min(spec_family(m) for m in self.members(rel))

    def add(self, paths) -> None:
        """Count files the listing left out (git ignores them, or they are in an ignored folder) as
        documents too: a folder the user named is still searched for versions of one spec."""
        for f in paths:
            if f not in self._known:
                self._known.add(f)
                self.docs.append(f)
                self._groups.setdefault(_family_key(f), []).append(f)

    def prefetch(self, paths) -> None:
        """Ask git, once, for the last commit of every path a caller is about to need."""
        todo = [p for p in dict.fromkeys(paths) if p in self.tracked and p not in self._asked]
        if todo:
            self._asked.update(todo)
            found, why = _last_commits(self.root, todo)
            self._commits.update(found)
            if why:
                self._unknown.update({p: why for p in todo if p not in found})

    def prefetch_versions(self, paths) -> None:
        """prefetch, for those of `paths` that have other versions, and for those versions. A file
        with no other version never needs its last commit (newest() answers at once), and on a long
        history git log can take all of its 60 s to reach a file that was last changed long ago."""
        self.prefetch([m for f in dict.fromkeys(paths) if len(ms := self.members(f)) > 1 for m in ms])

    def commit_date(self, rel: str) -> str | None:
        self.prefetch([rel])
        ts = self._commits.get(rel)
        return _datetime.datetime.fromtimestamp(ts).date().isoformat() if ts else None     # local, as git log shows it

    def commit_unknown(self, rel: str) -> str | None:
        """Why the last commit of a file git tracks was not found (git log stopped before it got
        there), or None. Such a file is not "not committed": its last commit is simply unknown."""
        self.prefetch([rel])
        return self._unknown.get(rel)

    def changed(self, rel: str) -> tuple[float | None, bool]:
        """When the file last changed: (its last commit, True), else - not committed, or no git -
        (its file time, False). (None, False) when git log stopped before it reached the file's
        last commit: its file time would be a guess (after a clone every file has the same one)."""
        self.prefetch([rel])
        if rel in self._commits:
            return float(self._commits[rel]), True
        if rel in self._unknown:
            return None, False
        try:
            return (self.root / rel).stat().st_mtime, False
        except OSError:
            return None, False

    @staticmethod
    def _version(rel: str) -> tuple | None:
        for _, name, _ in reversed(_segments(rel)):
            if versions := _name_tokens(name)[1]:
                return versions[-1][0]              # 8 numbers, then the pre-release (see _name_tokens)
        return None

    @staticmethod
    def _date(rel: str):
        for _, name, _ in reversed(_segments(rel)):
            if dates := _name_tokens(name)[0]:
                return dates[-1][0]
        return None

    def newest(self, rel: str) -> tuple[str | None, str]:
        """The newest of the documents that look like versions of `rel`'s, and how that was decided,
        in plain words; None when nothing tells them apart. A file marked old (a word such as
        archive in its path, or a line at its top) is never the newest while another one is not.
        Then: the version number in the name, else the date in the name, else the last commit."""
        members = self.members(rel)
        if len(members) == 1:
            return rel, "it is the only version"
        pool = [m for m in members if not self.marked_old(m)] or members
        if len(pool) == 1:
            return pool[0], "the others are marked as old, by a word in their path or a line at their top"
        names = []                                          # what their names said, when it did not decide
        for how, key, what in (("the version number in the name", self._version, "version number"),
                               ("the date in the name", self._date, "date")):
            keys = {m: key(m) for m in pool}
            have = [m for m in pool if keys[m] is not None]
            if len(have) == len(pool):
                best = max(keys.values())
                pool = [m for m in pool if keys[m] == best]
                if len(pool) == 1:
                    return pool[0], f"by {how}"
                names.append(f"{len(pool)} of them have the same {what} in their name")
            elif have:
                names.append(f"only {len(have)} of the {len(pool)} have a {what} in their name")
        times = {m: self.changed(m) for m in pool}
        unknown = [m for m in pool if times[m][0] is None]
        if not unknown:
            best = max(t for t, _ in times.values())
            top = [m for m in pool if times[m][0] == best]
            if len(top) == 1:
                return top[0], ("by the date of each file's last commit" if all(c for _, c in times.values()) else
                                "by when each file last changed (its last commit, or its file time when it is not "
                                "committed)")
            last = "the same last change"
        else:
            why = "; ".join(dict.fromkeys(self._unknown.get(m, "the file could not be read") for m in unknown))
            last = f"the last change of {', '.join(unknown)} is not known ({why})"
        return None, (f"nothing tells them apart: {', '.join(names) or 'no version numbers or dates in their names'}"
                      f", and {last}")


def spec_candidates(root: Path, ignore, survey: SpecSurvey | None = None) -> list[dict]:
    """Every .md/.rst file git would commit (outside git: every one outside the ignored folders)
    whose path, title or first heading suggests a spec - spec, specification, requirements, design,
    architecture, ADR, decision, RFC, PEP, PRD, SRS, proposal, API - with what the user needs to choose
    the current one: its last commit, every sign of age, and the other versions of it. The whole
    list, nothing left out."""
    s = survey or SpecSurvey(root, ignore)
    picked = [f for f in s.docs if _suggests_spec(f, s.title(f)) or _suggests_spec(f, _title_of(s.head(f), False))]
    s.prefetch(picked + [m for f in picked for m in s.members(f)])
    out = []
    for f in picked:
        members = s.members(f)
        newest, how = s.newest(f)
        decl = s.declared(f)
        # s.against, not s.reasons: a version number or a date in the name of the newest version, or of
        # a document that has no other version, is not a sign of age (proposals/2019-07-17-Webhooks.md).
        out.append({"path": f, "title": s.title(f), "last_commit": s.commit_date(f), "committed": f in s.tracked,
                    "last_commit_not_found": s.commit_unknown(f),
                    "looks_historical": s.against(f), "self_declared": decl[1] if decl else None,
                    "family": s.family(f), "family_size": len(members), "newest_in_family": newest,
                    "newest_decided_by": how if len(members) > 1 else ""})
    return out


def not_utf8_specs(survey: SpecSurvey) -> list[str]:
    """The files spec_candidates cannot list because their names are not valid UTF-8 (see _utf8):
    those whose name, title or first heading suggests a spec. The caller names them in a warning."""
    return [f for f in survey.not_utf8 if _suggests_spec(_readable(f), survey.title(f))
            or _suggests_spec(_readable(f), _title_of(survey.head(f), False))]


def spec_families(candidates: list[dict], survey: SpecSurvey) -> list[dict]:
    """The candidates' families that have more than one member: every member with its last
    commit, the newest, and how that was decided."""
    out, seen = [], set()
    for c in candidates:
        key = _family_key(c["path"])
        if c["family_size"] < 2 or key in seen:
            continue
        seen.add(key)
        members = survey.members(c["path"])
        out.append({"family": c["family"], "members": members, "newest": c["newest_in_family"],
                    "decided_by": c["newest_decided_by"], "last_commits": {m: survey.commit_date(m) for m in members},
                    "last_commit_not_found": {m: why for m in members if (why := survey.commit_unknown(m))}})
    return out


def candidates_text(candidates: list[dict], families: list[dict]) -> list[str]:
    """The candidates as a person reads them: path, last commit, title, and every flag."""
    if not candidates:
        return ["No file in this project looks like a spec by its path, title or first heading."]
    out = [f"{len(candidates)} file(s) in this project look like specs (by their path, title or first heading):"]
    for c in candidates:
        when = (f"last commit {c['last_commit']}" if c["last_commit"] else
                f"last commit not found: {c['last_commit_not_found']}" if c.get("last_commit_not_found") else
                "not committed")
        out.append(f"  {c['path']}  ({when})" + (f"  \"{c['title']}\"" if c["title"] else ""))
        if c["self_declared"]:
            out.append(f"      SAYS IT IS OUT OF DATE: \"{c['self_declared']}\"")
        signs = [r for r in c["looks_historical"] if not r.startswith("line ")]
        if signs:
            out.append("      looks like an old copy: " + "; ".join(signs))
        if c["family_size"] > 1:
            if c["newest_in_family"] == c["path"]:
                out.append(f"      the newest of {c['family_size']} files that look like versions of one document "
                           f"({c['newest_decided_by']})")
            elif c["newest_in_family"]:
                out.append(f"      a newer version exists: {c['newest_in_family']} ({c['newest_decided_by']})")
            else:
                out.append(f"      one of {c['family_size']} files that look like versions of one document; which "
                           f"is newest cannot be told - {c['newest_decided_by']}")
    if families:
        out += ["", "Files that look like versions of one document:"]
        for f in families:
            unknown = f.get("last_commit_not_found") or {}
            out.append(f"  {f['family']}: " + ", ".join(
                f"{m} ({f['last_commits'][m] or ('last commit not found' if m in unknown else 'not committed')})"
                for m in f["members"]))
            if unknown:
                out.append(f"      last commit not found for {len(unknown)} of them: "
                           + "; ".join(dict.fromkeys(unknown.values())))
            out.append(f"      newest: {f['newest']} ({f['decided_by']})" if f["newest"] else
                       f"      newest: cannot be told - {f['decided_by']}")
    return out


def _newer_warning(s: SpecSurvey, rel: str, role: str) -> str | None:
    """A warning when another version of `rel` looks newer, or when nothing tells them apart.
    `role` finishes "which ...": "was named", "this map checks"."""
    members = s.members(rel)
    if len(members) < 2:
        return None
    newest, how = s.newest(rel)
    if newest == rel:
        return None
    if newest is None:
        return (f"the project has other files that look like versions of {rel}, which {role}: "
                f"{', '.join(m for m in members if m != rel)}. Which is newest cannot be told - {how}. Ask the user "
                f"which one is the current spec.")
    return (f"{newest} looks like a newer version of {rel}, which {role} ({how}). Ask the user whether {newest} is "
            f"the current spec; if it is, draft a new map from it and review that instead.")


def _walk_docs(root: Path, rel: str, ignore) -> list[str]:
    """Every .md/.rst file on disk in the folder `rel` of `root` and below it, whatever git ignores:
    folders with an ignored name below it and symbolic links are skipped, and so is anything a
    symbolic link leads to (os.walk does not follow them)."""
    base = root if rel == "." else root / rel
    return sorted(p.relative_to(root).as_posix() for p in _discover(base, tuple(ignore))
                  if p.suffix.lower() in SPEC_SUFFIXES and not p.is_symlink())


def expand_docs(root: Path, docs: list[str], ignore) -> tuple[list[Path], list[str]]:
    """The spec files to draft from or pair, and warnings to show the user. A FILE that is named is
    always used - the user chose it - but gets a warning when it looks like an old copy, says at
    its top that it is superseded, or has a newer version in the project. A FOLDER is searched for
    .md and .rst files (skipping ignored folders, files git ignores and symbolic links, never leaving
    the project; when git ignores all of them, or the folder is inside an ignored one, they are used
    with a warning - the folder was named); if
    it holds a file that looks like an old copy, or several versions of one document, it is
    refused and nothing is used: which of them is current is for the user to say, never a guess.
    The refusal lists each such file once, each document with several versions once with its
    newest, and then every file here that nothing flags - the list to name if they are the spec.
    A file whose name says it is a template (template.md, 0000-template.md, pep-NNNN.rst) is left
    out of a folder that is used, with a warning. A path that is missing or outside the project is
    refused. A file whose name is not valid UTF-8 cannot be recorded in a map: named, it is
    refused; in a folder, it is left out with a warning."""
    root = Path(root).resolve()
    s = SpecSurvey(root, ignore)
    files: list[Path] = []
    warnings: list[str] = []
    for d in docs:
        p = Path(d).expanduser()
        p = p if p.is_absolute() else root / p
        if not p.exists():
            raise Stop(f"spec not found in the project: {_readable(d)}")
        real = p.resolve()
        if not real.is_relative_to(root):
            raise Stop(f"spec not found in the project: {_readable(d)} - it is outside the project ({root}), refused")
        rel = real.relative_to(root).as_posix()
        if not real.is_dir():
            if not _utf8(rel):
                raise Stop(f"the name of {_readable(rel)} is not valid UTF-8, so a map cannot record it - rename it, "
                           f"then name it again")
            files.append(real)
            s.prefetch_versions([rel])
            if why := s.against(rel):
                warnings.append(f"{rel} may be an old copy: {'; '.join(why)}. It was named, so it is used - make "
                                f"sure with the user that it is the current spec.")
            if w := _newer_warning(s, rel, "was named"):
                warnings.append(w)
            continue
        found = [f for f in s.docs if rel == "." or f.startswith(rel + "/")]
        not_utf8 = [f for f in s.not_utf8 if rel == "." or f.startswith(rel + "/")]
        if not found and not not_utf8:
            # The listing has nothing here: git ignores these files, or the folder is inside one that is
            # skipped (build/, ...). It was named, so its files are the ones meant - use them.
            on_disk = _walk_docs(root, rel, ignore)
            found, not_utf8 = [f for f in on_disk if _utf8(f)], [f for f in on_disk if not _utf8(f)]
            if found:
                s.add(found)
                skipped = next((part for part in rel.split("/") if part in set(ignore)), None)
                warnings.append(
                    f"{_readable(d)} is inside a folder named '{skipped}', which is skipped when the project is "
                    f"searched; it was named, so its {len(found)} file(s) were used." if skipped else
                    f"git ignores the .md and .rst files in {_readable(d)}; the folder was named, so its {len(found)} "
                    f"file(s) were used. Where they are not present (a fresh clone, CI) the map cannot be checked.")
        unusable = _not_utf8_warning(not_utf8, f"in {_readable(d)}")
        if not found:
            raise Stop(f"nothing was used: {unusable}" if unusable else f"no .md or .rst files in {_readable(d)}")
        s.prefetch_versions(found)
        here: dict[str, list[str]] = {}
        for f in found:
            here.setdefault(_family_key(f), []).append(f)
        old, usable, templates = [], [], []
        for f in found:
            why = s.against(f)
            if len(here[_family_key(f)]) > 1 and (newest := s.newest(f)[0]) != f:
                why = why + [f"{'an older' if newest else 'one of the'} version{'' if newest else 's'} of "
                             f"{s.family(f)} (see below)"]
            elif why and len(s.members(f)) > 1 and (newer := s.newest(f))[0] not in (None, f):
                why = why + [f"a newer version exists outside {_readable(d)}: {newer[0]} ({newer[1]})"]
            if why:
                old.append(f"  - {f}: {'; '.join(why)}")
            elif template_name(f):
                templates.append(f)
            else:
                usable.append(f)
        groups = []                                         # each document with several versions here, once
        for group in here.values():
            if len(group) > 1:
                newest, how = s.newest(group[0])
                groups += [f"  - {s.family(group[0])} ({len(group)} files): {', '.join(group)}",
                           f"      newest: {newest} ({how})" if newest else f"      newest: cannot be told - {how}"]
        if old or groups:
            parts = [f"{d} was refused and nothing was used: it holds files that look like old copies or several "
                     f"versions of one spec, and drafting from an outdated one would go unnoticed."]
            if old:
                parts += [f"Files that look like old copies ({len(old)}):", *old]
            if groups:
                parts += ["Files here that look like versions of one document:", *groups]
            parts.append("Name the current spec file(s) instead - ask the user which they are.")
            if usable:
                parts += [f"Nothing flags these {len(usable)} file(s) here"
                          + (" (of a document with several versions, only its newest is among them)" if groups else "")
                          + ". If they are the spec, name exactly these:", *(f"  {f}" for f in usable)]
            else:
                parts.append("Every file here is flagged: there is none to name without the user choosing.")
            if templates:
                parts.append("Left out of that list because their names say they are templates: "
                             + ", ".join(templates))
            if unusable:
                parts.append(unusable)
            raise Stop("\n".join(parts))
        if unusable:
            warnings.append(unusable)
        kept = 0
        for f in found:
            if why := template_name(f):
                warnings.append(f"{f} was left out: {why}, so it looks like a template, not part of the spec. Name "
                                f"it on its own if it is part of the spec.")
                continue
            kept += 1
            files.append(root / f)
            if w := _newer_warning(s, f, f"is in {d}"):
                warnings.append(w)
        if not kept:
            raise Stop(f"the only .md or .rst files in {d} look like templates ({', '.join(found)}) - name one on its "
                       f"own if it is the spec")
    return list(dict.fromkeys(files)), list(dict.fromkeys(warnings))


def spec_version_report(map_path: Path, root: Path, ignore, src: Path | None = None) -> dict:
    """Is every spec file the map checks still the current one? For each distinct spec file (the
    entries' "spec", and the map's "specs" list): a file whose top says it is superseded,
    deprecated, obsolete or no longer current is a PROBLEM - the map is not ready and nothing may
    be sent; a newer version of it in the project is a WARNING - the check still runs, and the
    user is asked. Free: reads files and git's history, sends nothing.
    A spec file is found as claims_from_map finds it - against `root`, then `src` (the code
    folder), then the map's folder - so every spec that is checked is also looked at here. Newer
    versions are looked for in whichever of `root` and `src` holds the spec; for a spec outside
    both, a warning says that none was looked for."""
    root = Path(root).resolve()
    mp = Path(map_path)
    mp = mp if mp.is_absolute() else root / mp
    report: dict = {"specs": [], "problems": [], "warnings": []}
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return report                                       # loading the map reports this itself
    entries = data.get("entries") if isinstance(data, dict) else data
    names = [e["spec"] for e in (entries if isinstance(entries, list) else [])
             if isinstance(e, dict) and isinstance(e.get("spec"), str) and e["spec"]]
    if isinstance(data, dict) and isinstance(data.get("specs"), list):
        names += [n for n in data["specs"] if isinstance(n, str) and n]
    confirmed = {Path(c).as_posix().removeprefix("./") for c in
                 (data.get("confirmed_current") if isinstance(data, dict) else None) or [] if isinstance(c, str) and c}
    tops = list(dict.fromkeys([root] + ([Path(src).resolve()] if src is not None else [])))
    bases = list(dict.fromkeys(tops + [mp.parent.resolve()]))       # claims_from_map's order: cwd, src, map
    found, seen = [], set()
    for n in dict.fromkeys(names):
        f = next((b / n for b in bases if (b / n).is_file()), None)
        if f is not None and f.resolve() not in seen:       # a missing spec is reported when the map loads
            real = f.resolve()
            seen.add(real)                                  # "docs/spec.md" and "./docs/spec.md": one file
            top = next((t for t in tops if real.is_relative_to(t)), None)
            found.append((n, real, top, real.relative_to(top).as_posix() if top else None))
    surveys: dict[Path, SpecSurvey | None] = {}
    for top in dict.fromkeys(t for _, _, t, _ in found if t is not None):
        try:
            surveys[top] = SpecSurvey(top, ignore)
            surveys[top].prefetch_versions([rel for _, _, t, rel in found if t == top])
        except Stop as e:
            surveys[top] = None
            report["warnings"].append(f"could not look for newer versions of the spec: {e}")
    for n, real, top, rel in found:
        shown = rel or n
        survey = surveys.get(top) if top is not None else None
        if top is None:
            report["warnings"].append(f"{shown} is outside the project ({root}), so no newer version of it was "
                                      f"looked for. Make sure with the user that it is the current spec.")
        decl = declared_old(_read_head(real))
        is_confirmed = bool({Path(n).as_posix().removeprefix("./"), shown} & confirmed)
        item = {"spec": shown, "declares_old": {"line": decl[0], "text": decl[1]} if decl else None,
                "confirmed_current": is_confirmed, "newer": None, "other_versions": [], "newest_decided_by": ""}
        if decl and is_confirmed:                           # the user's word beats a heuristic reading of one line
            report["warnings"].append(
                f"{shown} line {decl[0]} reads as if the spec were out of date (\"{decl[1]}\"), but the map lists it "
                f"in confirmed_current: the user confirmed it is the current spec, so it is checked.")
        elif decl:
            report["problems"].append(
                f"{shown} says it is out of date - line {decl[0]}: \"{decl[1]}\". This map checks it, so the code "
                f"would be compared with an outdated spec. Ask the user which file is the current spec, then draft a "
                f"new map from that file and review it. If the user says this spec IS current and that line is about "
                f"something else, add {shown} to the map's top-level \"confirmed_current\" list.")
        if survey is not None and rel:
            members = survey.members(rel)
            if len(members) > 1:
                newest, how = survey.newest(rel)
                item.update(other_versions=[m for m in members if m != rel], newest_decided_by=how,
                            newer=newest if newest not in (None, rel) else None)
                if w := _newer_warning(survey, rel, "this map checks"):
                    report["warnings"].append(w)
        report["specs"].append(item)
    return report


def _entry_line_spans(text: str) -> list[tuple[int, int] | None]:
    """Where each map entry's "line" value sits in the map file's text: (start, end), or None for an
    entry without one. The entries are the top-level list, or the top-level object's "entries".
    The text must be valid JSON already (load_map checked it)."""
    ws = re.compile(r"[ \t\n\r]*")
    scalar = re.compile(r"-?(?:\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|Infinity)|true|false|null|NaN")

    def skip(i: int) -> int:
        return ws.match(text, i).end()

    def value(i: int):
        i = skip(i)
        if text[i] in "{[":
            close, node = ("}", {}) if text[i] == "{" else ("]", [])
            i = skip(i + 1)
            while text[i] != close:
                if close == "}":
                    key, i = json.decoder.scanstring(text, i + 1)
                    i = skip(skip(i) + 1)                   # past the colon
                start = skip(i)
                child, end = value(start)
                if close == "}":
                    node[key] = (start, end, child)
                else:
                    node.append((start, end, child))
                i = skip(end)
                if text[i] == ",":
                    i = skip(i + 1)
            return node, i + 1
        if text[i] == '"':
            return None, json.decoder.scanstring(text, i + 1)[1]
        return None, scalar.match(text, i).end()

    top, _ = value(0)
    entries = top if isinstance(top, list) else (top.get("entries", (0, 0, None))[2] if isinstance(top, dict) else None)
    out = []
    for _, _, node in entries if isinstance(entries, list) else []:
        hit = node.get("line") if isinstance(node, dict) else None
        out.append((hit[0], hit[1]) if hit else None)
    return out


def update_map_lines(path: Path, src: Path | None = None) -> tuple[int, list[str]]:
    """Store the current line of every entry whose sentence has moved in the spec. Only the digits
    of those "line" values change; every other byte of the file stays as it was. The file is
    replaced atomically: a crash leaves the old map or the new one, never half of each. Returns
    (entries changed, notes)."""
    entries = load_map(path)                                # first: it says so plainly when the file is not a map
    text = path.read_bytes().decode("utf-8")
    spans = _entry_line_spans(text)
    bases = list({b.resolve(): b for b in [Path.cwd(), src or Path.cwd(), path.parent]}.values())
    indexes: dict[str, tuple] = {}
    edits, notes = [], []                                   # (entry index, span of its line, new line)
    for i, e in enumerate(entries):
        if not isinstance(e, dict) or not isinstance(e.get("spec"), str) or not e["spec"] \
                or not isinstance(e.get("spec_text"), str) or not e["spec_text"]:
            continue
        spec_file = next((b / e["spec"] for b in bases if (b / e["spec"]).is_file()), None)
        if spec_file is None:
            notes.append(f"map entry {i + 1}: its spec file {e['spec']!r} was not found, so its line was left as it is")
            continue
        if str(spec_file) not in indexes:
            indexes[str(spec_file)] = _spec_index(spec_file)
        line = e.get("line", 0)
        hit = _find_snapshot(indexes[str(spec_file)], _snap(e["spec_text"]), line if isinstance(line, int) else 0)
        if hit is None:
            notes.append(f"map entry {i + 1} ({e['spec']}): its spec_text is no longer in the spec, so its line was "
                         f"left as it is - the spec changed; review the entry")
            continue
        if hit == line:
            continue
        span = spans[i] if i < len(spans) else None
        if span is None:
            notes.append(f"map entry {i + 1} ({e['spec']}) has no \"line\" field, so it was left as it is; its "
                         f"sentence is at line {hit}")
            continue
        edits.append((i, span, hit))
    if not edits:
        return 0, notes
    new = text
    for _, (a, b), hit in sorted(edits, key=lambda x: x[1][0], reverse=True):
        new = new[:a] + str(hit) + new[b:]
    expected = json.loads(json.dumps(entries))              # prove that nothing but those lines changed
    for i, _, hit in edits:
        expected[i]["line"] = hit
    after = json.loads(new)
    if (after.get("entries") if isinstance(after, dict) else after) != expected:
        raise Stop(f"could not update the lines in {path} without changing anything else - nothing was written.")
    target = path.resolve()
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(new.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, target.stat().st_mode & 0o7777)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return len(edits), notes


# ───────────────────────────────────────────────────────────────── 3. ask Jev

def canonical(state: dict) -> dict:
    """Fixed key order, always. Reordering keys flips ~12.5% of decisions."""
    return {k: state[k] for k in sorted(state)}


def build_questions() -> dict:
    """One plain question per judgement. Never phrased as steps.

    The extra questions cost ~57 tokens and ~5ms each, so we ask them even
    though we only read them when the verdict is `drifted`.
    """
    q = {
        "verdict": {
            "type": "choice",
            "instructions": (
                "The documentation sentence is in `claim`. The current code is in `code`, and "
                "any arithmetic in it has already been worked out in `computed_values`. "
                "Is the sentence still an accurate description of that code?"
            ),
            "criteria": {
                "accurate": "The sentence correctly describes what the code does now.",
                "drifted": "The code has changed so the sentence is now wrong or misleading.",
                "unrelated": "The sentence is not describing this piece of code at all.",
                "not_enough_information": (
                    "The code shown does not contain enough to judge the sentence either way."
                ),
            },
        },
        # speculative — only read when verdict == drifted
        "severity": {
            "type": "score",
            "instructions": "If a reader followed `claim` but the code behaves as in `code`, how badly would they be misled?",
            "criteria": [
                "Not at all - the difference is cosmetic.",
                "Mildly - they would be briefly confused.",
                "Seriously - they would write code that fails.",
                "Critically - they would make an unsafe or data-losing choice.",
            ],
        },
        "value_mismatch": {
            "type": "noul",
            "instructions": "Does `claim` state a specific value, default, limit or name that differs from the one in `code`?",
            "criteria": {
                "true": "A concrete value in the sentence contradicts the code.",
                "false": "No concrete value conflicts, or the sentence states no specific value.",
            },
        },
    }
    return q


def ask(state: dict, questions: dict, key: str, timeout: int = 60, retries: int = 3,
        cancelled: Callable[[], bool] | None = None) -> dict:
    body = json.dumps({"state": canonical(state), "model": MODEL, "questions": questions}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    delay = 1.0

    def pause(seconds: float) -> None:
        """Wait before a retry: at most 30 s, and not at all once the check is cancelled."""
        end = time.monotonic() + min(seconds, 30.0)
        while time.monotonic() < end and not (cancelled and cancelled()):
            time.sleep(0.05)

    for attempt in range(retries + 1):
        if attempt and cancelled and cancelled():
            return {"_error": "cancelled before it was sent again"}
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read())
                out["_upstream_ms"] = r.headers.get("x-envoy-upstream-service-time")
                out["_request_id"] = r.headers.get("x-typesafe-request-id")
                return out
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")[:400]
            if e.code == 402:
                raise VendorStop("TypeSafe's credits are used up (HTTP 402). There is no low-balance warning. "
                           "Top up and switch on auto-reload: https://console.typesafe.ai/settings/billing")
            if e.code in (401, 403):
                raise Stop(f"TypeSafe rejected the API key (HTTP {e.code}). Check TYPESAFE_API_KEY. {raw[:160]}")
            if e.code in (429, 529) and attempt < retries:
                try:
                    wait = float(e.headers.get("retry-after") or delay)
                except ValueError:                   # an HTTP date is allowed too
                    wait = delay
                pause(wait); delay *= 2; continue
            if 400 <= e.code < 500:
                return {"_error": f"HTTP {e.code}: {raw}"}   # never retry a 4xx
            if attempt < retries:
                pause(delay); delay *= 2; continue
            return {"_error": f"HTTP {e.code}: {raw}"}
        except Exception as e:  # noqa: BLE001
            if attempt < retries:
                pause(delay); delay *= 2; continue
            return {"_error": f"{type(e).__name__}: {e}"}
    return {"_error": "exhausted"}


# ─────────────────────────────────────────────────────── 3b. do not ask twice for nothing

CACHE_FILE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "jevmcp" / "verdicts.json"
CACHE_MAX = 20_000                 # entries; the oldest are dropped when it grows past this
LAST_RUN_REPLAYED = 0              # answers the last check took from the cache instead of the API


def _cache_key(state: dict, questions: dict) -> str:
    """A verdict is a pure function of what was asked. The key is a hash of exactly that, so
    NO code and no claim text is ever written to the cache file - only a digest of them."""
    blob = json.dumps({"state": canonical(state), "model": MODEL, "questions": questions},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def load_cache(path: Path | None = None) -> dict[str, list]:
    """Answers kept from earlier runs, as {key: [answer, ...]}. A list, not one answer: the
    agreement gate needs several INDEPENDENT answers, and replaying one answer three times
    would make unanimity meaningless."""
    try:
        data = json.loads((path or CACHE_FILE).read_text())
        return data.get("answers", {}) if isinstance(data, dict) else {}
    except Exception:                                  # noqa: BLE001 - a bad cache is not an error
        return {}


def save_cache(answers: dict[str, list], path: Path | None = None) -> None:
    """Merge into what is on disk now: another run (a second session, a parallel CLI) may have saved
    since this one loaded, and writing only this run's copy would throw its answers away."""
    tmp = None
    try:
        path = path or CACHE_FILE          # read at call time: a default argument could not be patched
        merged = load_cache(path)
        merged.update(answers)
        if len(merged) > CACHE_MAX:
            merged = dict(list(merged.items())[-CACHE_MAX:])
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".verdicts-", suffix=".tmp")   # one per writer
        with os.fdopen(fd, "w") as fh:
            json.dump({"version": 1, "model": MODEL, "answers": merged}, fh)
        os.replace(tmp, path)
        tmp = None
    except Exception:                                  # noqa: BLE001 - never fail a run over a cache
        pass
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)


def map_health(results: list[dict], claims: list[Claim], syms: dict[str, Symbol] | None = None) -> dict:
    """What the run says about the MAP rather than the code.

    A "??" is not a fact about the project: it is an entry whose pairing cannot settle its
    sentence. On this tool's own documentation 38% of claims came back that way, and nothing
    in the output said so - the user had to notice. It is reported now, with the pairing the
    claim's own words suggest, because that is the cheapest fix available.
    """
    unver = [r for r in results if r.get("label") == "??"]
    by_line = {(c.doc, c.line): c for c in claims}
    worst: dict[str, int] = {}
    fixes: list[dict] = []
    for r in unver:
        worst[r.get("symbol", "?")] = worst.get(r.get("symbol", "?"), 0) + 1
        c = by_line.get((r.get("doc"), r.get("line")))
        entry = {"doc": r.get("doc"), "line": r.get("line"), "claim": r.get("claim"),
                 "paired_with": r.get("code_refs", []), "why": r.get("why", "")}
        if c is not None:
            entry["reasons"] = preflight(c)
            if syms:
                named, _why = _mentions(c.text, syms)
                have = {s.name for s in c.symbols}
                better = [f"{s.file}:{s.name}" for s in named if s.name not in have]
                if better:
                    entry["try_pairing_with"] = better[:4]
        fixes.append(entry)
    return {"checked": len(results), "unverifiable": len(unver),
            "unverifiable_pct": round(100.0 * len(unver) / len(results), 1) if results else 0.0,
            "most_often_paired_with": sorted(worst.items(), key=lambda kv: -kv[1])[:5],
            "entries_to_fix": fixes}


def next_step_for_drift(r: dict) -> str:
    """What a human or an agent has to do about one DRIFT.

    Jev answers questions; it does not write prose, so it cannot produce the corrected
    sentence. It can say exactly what the decision is, which is the part that is easy to get
    wrong: which side is being changed, and against what evidence.
    """
    return (f"Read {r['doc']}:{r['line']} against {', '.join(r.get('code_refs', [])) or 'the paired code'}, "
            f"and the code around it. Then decide ONE of: (a) the code is wrong - fix it; "
            f"(b) the sentence is stale - rewrite it to describe what the code does now, and update the "
            f"map entry's text and spec_text; (c) neither - the pairing is wrong, so repoint `code`. "
            f"`git log -p`/`git blame` on the paired code usually shows which.")


def check_claims(claims: list[Claim], key: str, jobs: int = 4, show: Callable[[str], None] = print,
                 on_answer: Callable[[int, int], None] | None = None,
                 cancelled: Callable[[], bool] | None = None,
                 samples: int = SAMPLES, agree_floor: float = AGREE_FLOOR, use_cache: bool = True
                 ) -> tuple[list[dict], int, list[str], list[str]]:
    """Ask Jev about every claim, `jobs` at a time, and label each answer. Returns the results
    in claim order, the input tokens used, and what kept claims from being checked: problems
    (exit 2 - fix your setup, e.g. a rejected key) and vendor failures (exit 3 - TypeSafe
    could not be used). Shared by the CLI and jevmcp_server.py, so both judge identically.

    `on_answer(done, total)` is called as each answer arrives (from worker threads);
    once `cancelled()` returns true, no further claims are sent.

    Every claim is asked once. A claim the single-answer gate does NOT settle is then asked
    `samples - 1` more times, and is decided only if every answer agrees and none is below
    `agree_floor`. Claims the first answer already settled are never asked again, so the extra
    cost falls only on the uncertain middle. `samples=1` restores the single-answer behaviour
    exactly."""
    problems: list[str] = []
    vendor: list[str] = []
    results: list[dict] = []
    tokens = 0
    states = [build_state(c) for c in claims]
    import threading
    done_lock, done = threading.Lock(), [0]
    questions = build_questions()
    store = load_cache() if use_cache else {}
    keys = [_cache_key(s, questions) for s in states]
    cache_lock, replayed = threading.Lock(), [0]

    def answer_n(k: int, n: int) -> dict:
        """The n-th independent answer for claim k: replayed from the cache when we already
        have that many, otherwise asked and remembered. Answers are kept as a LIST per claim,
        because the agreement gate needs independent answers - handing it one answer three
        times would make unanimity mean nothing."""
        with cache_lock:
            have = store.get(keys[k], [])
            if n < len(have):
                replayed[0] += 1
                return {"answers": have[n], "usage": {"input_tokens": 0}, "_cached": True}
        got = ask(states[k], questions, key, cancelled=cancelled)
        if use_cache and "answers" in got:
            with cache_lock:
                store.setdefault(keys[k], []).append(got["answers"])
        return got

    def one(k: int):
        if cancelled and cancelled():
            return {"_error": "cancelled before it was sent"}
        try:
            return answer_n(k, 0)
        except Stop as e:                      # re-raised in order below
            return {"_stop": e}
        finally:
            if on_answer:
                with done_lock:
                    done[0] += 1
                    n = done[0]
                on_answer(n, len(claims))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        answers = list(pool.map(one, range(len(claims))))
    try:
        for i, (c, state, ans) in enumerate(zip(claims, states, answers), 1):
            if "_stop" in ans:
                raise ans["_stop"]
            if "_error" in ans:
                vendor.append(f"{c.doc}:{c.line} was not checked - API error: {ans['_error'][:120]}")
                show(f"  [{i}/{len(claims)}] ERROR  {c.doc}:{c.line}  {ans['_error'][:80]}")
                continue
            a = ans["answers"]
            action, conf, why = classify(a)
            tokens += ans.get("usage", {}).get("input_tokens", 0)
            results.append({
                "label": {"act": "DRIFT", "review": "review", "unverifiable": "??", "clean": "ok"}[action],
                "action": action, "confidence": round(conf, 3), "why": why,
                "doc": c.doc, "line": c.line, "claim": c.text,
                "code_file": c.symbol.file, "code_line": c.symbol.line, "symbol": c.symbol.name,
                "code_refs": [f"{s.file}:{s.line} {s.name}" for s in c.symbols],
                "verdict": a["verdict"]["choice"],
                "probabilities": a["verdict"]["probabilities"],
                "severity": round(a["severity"]["score"], 2),
                "severity_legend": a["severity"]["legend"],
                "value_mismatch": a["value_mismatch"]["noul"],
                "code_sent": state["code"] + (f"\n\n[computed_values]\n{state['computed_values']}"
                                              if "computed_values" in state else ""),
                "request_id": ans.get("_request_id"),
                "upstream_ms": ans.get("_upstream_ms"),
                "samples": 1,
                "_k": i - 1, "_a": a,
            })
            flag = {"act": "DRIFT ", "review": "review", "unverifiable": "  ??  ", "clean": "  ok  "}[action]
            show(f"  [{i}/{len(claims)}] {flag} {conf:.2f}  {c.doc}:{c.line}  {c.text[:64]}")
    except VendorStop as e:
        vendor.append(f"the run stopped early: {e}")
    except Stop as e:
        problems.append(f"the run stopped early: {e}")

    # Ask again about what one answer did not settle. Measured on the graded corpus: this
    # takes the share of claims decided without a human from 4.3% to 18.3%, with no real
    # drift passed as `ok` and no accurate claim called drifted (tools/score_eval.py).
    undecided = [r for r in results if r["action"] not in ("act", "clean")]
    if samples > 1 and undecided and not problems and not vendor and not (cancelled and cancelled()):
        show(f"  asking again about {len(undecided)} claim(s) one answer did not settle "
             f"({samples - 1} more each)")

        def again(r: dict) -> list[dict]:
            return [answer_n(r["_k"], n) for n in range(1, samples)]

        try:
            with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
                more = list(pool.map(again, undecided))
        except Stop as e:
            problems.append(f"re-asking stopped early: {e}")
            more = []
        changed = 0
        for r, extra in zip(undecided, more):
            good = [m["answers"] for m in extra if "_error" not in m and "answers" in m]
            tokens += sum(m.get("usage", {}).get("input_tokens", 0) for m in extra if "_error" not in m)
            r["samples"] = 1 + len(good)
            settled = classify_samples([r["_a"], *good], agree_floor)
            if settled:
                action, conf, why = settled
                r["action"], r["confidence"], r["why"] = action, round(conf, 3), why
                r["label"] = {"act": "DRIFT", "review": "review",
                              "unverifiable": "??", "clean": "ok"}[action]
                changed += 1
        if changed:
            show(f"  {changed} settled by agreement across answers")
    for r in results:
        r.pop("_k", None); r.pop("_a", None)
    if use_cache:
        save_cache(store)
    globals()["LAST_RUN_REPLAYED"] = replayed[0]
    if replayed[0]:
        show(f"  {replayed[0]} answer(s) replayed from the cache - unchanged code is never asked about twice")
    return results, tokens, problems, vendor


# ──────────────────────────────────────────────────────────────── 4. the gate

def classify(ans: dict) -> tuple[str, float, str]:
    """act / review / unverifiable / clean — deterministic, given the answer.

    The rule that matters: **a low-confidence "accurate" is not a clean bill of
    health.** It is the model saying "probably fine, but I am not sure", and
    that is exactly as unsafe as a low-confidence "drifted". Gating only the
    drifted branch silently passes those through. On the demo set that single
    mistake hid a real drift the model had already half-spotted (accurate 0.74,
    drifted 0.24, confidence 0.66).
    """
    v = ans.get("verdict", {})
    choice = v.get("choice")
    conf = v.get("confidence", 0.0)
    probs = v.get("probabilities", {})
    drift_p = probs.get("drifted", 0.0)
    mismatch = ans.get("value_mismatch", {}).get("noul", 0.0)

    if choice == "not_enough_information":
        # Not a pass. The claim is simply not covered by this check - say so,
        # or you end up trusting a report that never looked.
        return "unverifiable", conf, "model abstained - the paired code does not settle this claim"

    if choice == "unrelated":
        return "unverifiable", conf, "sentence is not about the paired code - fix the pairing"

    if choice == "drifted":
        if conf >= ACT_ABOVE:
            return "act", conf, "drifted, confident"
        return "review", conf, f"drifted but confidence {conf:.2f} below {ACT_ABOVE}"

    # choice == "accurate"
    if conf < CLEAN_ABOVE:
        return "review", conf, (
            f"says accurate at {conf:.2f}, below the {CLEAN_ABOVE} needed to pass it unseen "
            f"(drifted carried {drift_p:.2f} of the probability)"
        )
    # Second opinion: a strong value mismatch outranks a confident "accurate".
    # Two questions OR'd together catch what either alone misses.
    if mismatch >= 0.70:
        return "review", conf, f"says accurate, but a stated value conflicts with the code ({mismatch:.2f})"
    return "clean", conf, "no drift"



def classify_samples(answers: list[dict], floor: float = AGREE_FLOOR) -> tuple[str, float, str] | None:
    """A verdict the model gave the SAME answer to every time, each time confidently.

    Measured on the 115-claim graded corpus (tools/score_eval.py, `--sweep`): the verdict
    itself moves between identical calls on 32% of claims, so agreement is real evidence
    rather than a formality. Unanimity alone decides 69% of claims but lets 5 real drifts
    through as `ok`; unanimity *plus* a floor of 0.85 on every sample decides 18.3% (against
    4.3% for a single answer) with zero false cleans and zero false alarms.

    Returns None when the samples do not settle it, and the caller keeps the single-answer
    label - so this can only ever move a claim OUT of `review`, never quietly into it.
    """
    if len(answers) < 2:
        return None
    votes = [a.get("verdict", {}).get("choice") for a in answers]
    confs = [a.get("verdict", {}).get("confidence", 0.0) for a in answers]
    if len(set(votes)) > 1 or min(confs, default=0.0) < floor:
        return None
    conf = sum(confs) / len(confs)
    if votes[0] == "drifted":
        return "act", conf, f"all {len(answers)} answers say drifted, none below {floor:.2f}"
    if votes[0] == "accurate":
        worst = max(a.get("value_mismatch", {}).get("noul", 0.0) for a in answers)
        if worst >= 0.70:
            return None                       # a value conflict still outranks agreement
        return "clean", conf, f"all {len(answers)} answers say accurate, none below {floor:.2f}"
    if set(votes) <= {"not_enough_information", "unrelated"}:
        return "unverifiable", conf, f"all {len(answers)} answers abstained - fix the pairing"
    return None


# A claim about what the code does NOT do. One excerpt can never settle it: code that does
# not do X proves nothing, and the one place that does X reads as a refutation. Measured on
# this project's own PRIVACY.md, where "sends no telemetry" paired with the single function
# that makes a request came back DRIFT at 0.93 against correct code.
_NEGATIVE_UNIVERSAL = re.compile(r"\b(?:never|nothing|nobody|no one|none|no other|anyone but)\b", re.I)


def _relevant_slice(source: str, claim: str, budget: int) -> tuple[str, bool]:
    """As much of `source` as fits, preferring the lines the claim is actually about.

    Cutting at the first `budget` characters hands the model the top of a long function and
    calls it the whole thing - which is how 31 claims pointed at one big function came back
    "??" in this project's own audit. Keeping the lines that mention the claim's identifiers,
    with a little context, puts the relevant part inside the budget instead.

    Returns the text and whether anything was left out.
    """
    if len(source) <= budget:
        return source, False
    lines = source.splitlines()
    wanted = {m.group(1) or m.group(2) for m in IDENT.finditer(claim)} - {None}
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if any(w in line for w in wanted):
            keep.update(range(max(0, i - 2), min(len(lines), i + 3)))
    if not keep:                                     # nothing to aim at: the head, honestly marked
        return source[:budget].rstrip() + "\n# ... cut here: the rest of this code was not sent", True
    out, last, used = [], -1, 0
    for i in sorted(keep):
        gap = (last < 0 and i > 0) or (last >= 0 and i > last + 1)
        piece = ("# ... lines skipped ...\n" if gap else "") + lines[i]
        if used + len(piece) + 1 > budget:
            out.append("# ... lines skipped ...")
            break
        out.append(piece); used += len(piece) + 1; last = i
    if 0 <= last < len(lines) - 1:
        out.append("# ... lines skipped ...")
    return "\n".join(out), True


def preflight(c: Claim) -> list[str]:
    """Why this claim will probably come back "??", worked out locally and for free.

    A "??" costs a request and returns nothing, and in this project's own audit 38% of claims
    came back that way. Every cause below is visible without asking anyone.
    """
    out = []
    if _NEGATIVE_UNIVERSAL.search(c.text):
        out.append("says what the code does NOT do - no excerpt can settle that; exclude it with a "
                   "why, or reword the sentence to name the one place involved")
    if c.text.rstrip().endswith(":"):
        out.append("ends in a colon - a lead-in, not a requirement; exclude it and check the items below it")
    total = sum(len(s.source) for s in dict.fromkeys(c.symbols))
    if total > MAX_CODE_CHARS:
        out.append(f"the paired code is {total:,} characters and only {MAX_CODE_CHARS:,} are sent - "
                   f"point at the part that enforces the sentence, not the whole thing")
    return out


def build_state(c: Claim) -> dict:
    """The exact `state` sent for one claim: the sentence, the paired code
    (comments already stripped, secrets redacted, capped), and any arithmetic
    the tool worked out so the model does not have to.

    When the code does not fit, the part the claim names is preferred over the first N
    characters, and the cut is marked so the model knows it is judging an excerpt."""
    parts, seen_src, budget = [], set(), MAX_CODE_CHARS
    for s in c.symbols:
        if s.source in seen_src or budget <= 0:
            continue
        seen_src.add(s.source)
        shown = _shown(Path(s.file)) if os.path.isabs(s.file) else s.file     # never an absolute path
        head = f"# {shown}:{s.line}\n"
        body, _cut = _relevant_slice(s.source, c.text, max(0, budget - len(head)))
        block = head + body
        parts.append(block)
        budget -= len(block)
    state = {"claim": c.text, "code": redact("\n\n".join(parts))}
    resolved = [r for s in c.symbols for r in resolve_arithmetic(s.source, Path(s.file).suffix)]
    if resolved:
        state["computed_values"] = "\n".join(dict.fromkeys(resolved))
    return state


def estimate_cost(claims: list[Claim], samples: int = 1) -> float:
    """From the real payload sizes: ~3.4 bytes per token plus the fixed 259-token
    charge per request, at $0.042 per million input tokens (output is free).

    With `samples > 1` this is the WORST case - every claim needing every re-ask. Claims the
    first answer settles are never asked again, so a real run costs less."""""
    total = 0
    for c in claims:
        body = json.dumps({"state": canonical(build_state(c)), "model": MODEL, "questions": build_questions()})
        total += 259 + len(body) / 3.4
    return total * max(1, samples) * 0.042 / 1e6


def _tool_path(p: Path | None = None) -> str:
    """A path next to this tool, absolute: examples must work from ANY folder you cd into."""
    return str((p or Path(__file__)).resolve())


def _cmd() -> str:
    """The exact command prefix. uv installs the parsers listed at the top of this file;
    without uv, this Python runs the tool (and needs the parsers installed)."""
    if shutil.which("uv"):
        return f"uv run --quiet --script {_tool_path()}"
    return f"{sys.executable} {_tool_path()}"


def quick_start() -> str:
    tool, cmd = _tool_path(), _cmd()
    return f"""\
spec drift - check that a specification still matches the code.

It reads your spec one sentence at a time, finds the code each sentence is
about, and asks a model whether the sentence is still true of that code.
The model is Jev, run by TypeSafe (typesafe.ai); only the check in step 3
calls it. Everything else runs on your machine.

Run every command from the folder of the PROJECT YOU ARE CHECKING (the one
that holds its spec and its code). This tool is at:
  {tool}

PARSERS - Python needs nothing extra. Java, JavaScript, TypeScript and YAML
need the tree-sitter parsers listed at the top of this tool. `uv run --script`
installs them; without uv, install them into the Python that runs the tool:
  pip install tree-sitter tree-sitter-java tree-sitter-javascript tree-sitter-typescript pyyaml

THE USUAL 3 STEPS

  0. Not sure which file is the spec, or does the project keep several
     versions of it? List the candidates with their last commit dates and
     anything that marks one as an old copy, then choose:

       {cmd} --find-specs

  1. See which spec sentences it can pair with code on its own. It pairs a
     sentence that names something in backticks that exists in the code -
     `MAX_ITEMS`, `GET /api/orders/{{id}}`, `app.orders.max-items` - and lists
     the sentences it could not pair. Free: nothing is sent anywhere.

       {cmd} --docs docs/spec.md --dry-run

  2. Draft a map: a file with one entry per spec sentence and a suggested
     place in the code for each. Free: nothing is sent anywhere.

       {cmd} --docs docs/spec.md --draft-map spec_map.json

     Open spec_map.json. Its "_readme" explains every field. Check each
     entry and fix the "code" of wrong ones; set "status" to "reviewed", or
     to "excluded" with a "why" for sentences that are not requirements.
     Then confirm it loads (--strict also fails on undecided sentences):

       {cmd} --map spec_map.json --dry-run

  3. Run the check. Sends each sentence and its paired code to TypeSafe
     (about $0.0005 per 10 sentences; the dry run estimates it for your
     spec) and writes the results to drift.json - overwriting an old one;
     --out FILE writes somewhere else.

       {cmd} --map spec_map.json

  Shortcut: if step 1 paired every sentence you care about, skip the map:
       {cmd} --docs docs/spec.md

FOR STEP 3 - an API key from https://console.typesafe.ai, either in the
environment (wins if both are set) or in a .env file in the folder you run
from. That .env is read only for this key and is never sent:
  TYPESAFE_API_KEY=...

MORE
  Every option, the result labels and the exit codes:
       {cmd} --help
  See exactly what would be sent:                      add --dry-run --show-payload
  Guide and source: https://github.com/eaisdevelopment/jevmcp
"""


def help_epilog() -> str:
    tool, cmd = _tool_path(), _cmd()
    return f"""\
examples (run from the folder of the project you are checking):
  Step 1 - what pairs on its own (no API calls):
      {cmd} --docs docs/spec.md --dry-run
  Which file is the spec? List the candidates, with dates and signs of old copies (no API calls):
      {cmd} --find-specs
  Step 2 - draft a map from the current spec file(s), then check it loads (no API calls):
      {cmd} --docs docs/spec.md --draft-map spec_map.json
      {cmd} --map spec_map.json --dry-run
  The spec was edited above some entries - store their new line numbers (nothing else changes):
      {cmd} --map spec_map.json --update-lines
  Step 3 - the check:
      {cmd} --map spec_map.json
  Try 5 claims first, and see exactly what is sent:
      {cmd} --map spec_map.json --limit 5 --dry-run --show-payload
  Code in a sub-folder; also skip a generated/ folder:
      {cmd} --docs README.md --src backend --ignore generated

"code" in a map entry can be:
  route:GET /api/orders/{{id}}        an endpoint - its handler, wherever it is
  config:app.orders.max-items       a setting - its definitions, defaults, and every place that names
                                    the key; add the function that enforces it too
  src/Orders.java:OrderService.place   a method, class, function or constant
  src/app.ts:120-160                a line range (any language)
  src/config.py                     a whole file (small files only)
  [ ... , ... ]                     several of the above
  File paths are looked up from the folder you run in, then --src, then the map's folder.

what the results mean:
  DRIFT   spec and code disagree; the model is at least 0.905 confident -> fix the spec or the code
  review  the model leans one way but is not sure enough                  -> a person reads both
  ??      the code shown cannot settle the claim                           -> NOT a pass: pair it with
                                                                              code that can, or check by hand
  ok      spec and code agree; the model is at least 0.987 confident      -> nothing to do

exit codes (review and ?? never change them; with --limit they cover the claims checked):
  0  every claim was checked; no DRIFT
  1  every claim was checked; at least one DRIFT
  2  fix your setup: usage error, missing key or parsers, a map entry that cannot be
     resolved, is stale or points at a missing spec - and with --strict also unmapped
     spec sentences, unreviewed entries, entries that may be stale, excluded entries
     with no "why", excluded sentences the spec has since changed
  3  TypeSafe could not be used (outage, errors, credits used up) - not your code's
     fault. Results produced so far are still written.
  Suggested CI policy: 2 fails the job (the team must fix it); 1 and 3 report without
  blocking the merge (TypeSafe has no uptime guarantee).

--docs checks only the sentences that name code; everything else is listed as NOT
checked (with --strict that fails the run). A map covers every sentence you review.

what is sent, per claim: the spec sentence; the paired code with comments removed,
secret-looking values redacted and paths relative to your project; any arithmetic the
tool worked out ("computed_values"); and 3 fixed questions (see --show-payload). Your
.env is read only for TYPESAFE_API_KEY and never sent; .env.example templates are
read as configuration.

drift.json - one object per claim: label (DRIFT / review / ?? / ok), confidence, why,
doc, line, claim, code_refs, code_sent (exactly what was sent), verdict, probabilities,
severity (0-3), value_mismatch, request_id. Thresholds are fixed: DRIFT >= 0.905,
ok >= 0.987 (measured over repeated identical calls - see CLEAN_ABOVE in the source;
not configurable on purpose).
languages: Python, Java, JavaScript, TypeScript by name; anything else by line range.
"""


class Stop(Exception):
    """End the run with a plain message and exit code 2 (fix your setup)."""


class VendorStop(Stop):
    """TypeSafe could not be used (outage, credits). Exit code 3: not your code's fault."""


class _Parser(argparse.ArgumentParser):
    """argparse, but a mistake gets a plain sentence instead of a usage dump."""
    def error(self, message: str) -> None:
        _die(message)


def _die(message: str) -> None:
    sys.stdout.flush()
    sys.stderr.write(f"spec_drift: {message}\n\n"
                     "Run with no options for the quick start, or with --help for every option.\n")
    sys.exit(2)


def build_parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="spec_drift.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                 description="Check that a specification still matches the code.\n"
                             "Run it from the folder of the project you are checking. "
                             "With no options it prints a quick start.",
                 epilog=help_epilog())
    spec = ap.add_argument_group("the spec - give --docs or --map")
    spec.add_argument("--docs", nargs="+", default=[], metavar="PATH",
                      help="Your spec: one or more Markdown/.rst files, or folders to search for them. "
                           "A sentence is paired automatically when it names, in backticks, something that "
                           "exists in the code: a function, class, constant, endpoint or setting. "
                           "Sentences it cannot pair are listed. Example: --docs docs/spec.md. "
                           "A folder that holds old copies or several versions of a spec (spec-v1.md next to "
                           "spec-v2.md, an archive/ folder, a file that says it is superseded) is refused: name "
                           "the current file(s). A named file that looks old gets a WARNING. Not sure which file "
                           "is the spec? --find-specs lists the candidates.")
    spec.add_argument("--map", metavar="FILE",
                      help="A reviewed map saying which code each requirement is about (JSON). Make it with "
                           "--draft-map; the file explains its own fields. Use this to check every "
                           "requirement, not only those that name code. Example: --map spec_map.json")
    code = ap.add_argument_group("the code")
    code.add_argument("--src", default=".", metavar="DIR",
                      help="Folder to read the code from. Default: the current folder.")
    code.add_argument("--ignore", nargs="+", default=[], metavar="NAME",
                      help="More folder names to skip, anywhere in the tree, ON TOP of the defaults "
                           "(node_modules, .git, build, dist, target, .venv, ... - see --no-default-ignore). "
                           "Example: --ignore generated vendor")
    code.add_argument("--no-default-ignore", action="store_true",
                      help="Do not skip the default folders; skip only what --ignore names. Defaults: "
                           + " ".join(DEFAULT_IGNORE))
    todo = ap.add_argument_group("what to do - default: run the check (calls the API)")
    todo.add_argument("--dry-run", action="store_true",
                      help="Show each claim, every piece of code paired with it, how much would be sent, "
                           "and the estimated cost. Makes no API calls. Exit code 2 if anything is wrong "
                           "with the map, so it doubles as a map check in CI.")
    todo.add_argument("--show-payload", action="store_true",
                      help="Also print, for each claim, exactly what would be sent to the API.")
    todo.add_argument("--draft-map", metavar="FILE",
                      help="Write a first-draft map to FILE (a suggested code location for every spec sentence, "
                           "plus a _readme explaining the fields) and stop. Needs --docs. Makes no API calls. "
                           "Refuses to overwrite an existing file, so a reviewed map is never lost.")
    todo.add_argument("--find-specs", action="store_true",
                      help="List every file in this project that looks like a spec (by its path, title or first heading) "
                           "with its last commit date and anything that marks it as a possible old copy - a version "
                           "number or date in its name, a folder such as archive/, a first line that says it is "
                           "superseded - and, where several look like versions of one document, which is newest. "
                           "Then stop. Makes no API calls. Use it to choose the file(s) for --docs.")
    todo.add_argument("--update-lines", action="store_true",
                      help="With --map: store the current line of every entry whose sentence has moved in the "
                           "spec. Only those \"line\" values change; every other byte of the file stays as it was, "
                           "and the file is replaced in one step. Makes no API calls.")
    todo.add_argument("--out", default=None, metavar="FILE",
                      help="Where the check writes its results (an existing file is overwritten). Default: "
                           "drift.json. With --dry-run, writes the plan instead: every claim, its code "
                           "references, what would be sent, and any problems - a CI artifact that costs nothing.")
    todo.add_argument("--strict", action="store_true",
                      help="For CI: also fail (exit 2) on spec sentences that are not checked - unpaired in "
                           "--docs mode, missing from the map (entries marked \"excluded\" count as decided), "
                           "map entries not marked reviewed, excluded entries with no \"why\" or whose "
                           "sentence has changed, or entries whose spec_text is missing and whose text no "
                           "longer appears in the spec.")
    todo.add_argument("--changed", nargs="*", default=None, metavar="FILE",
                      help="Check only claims whose paired code is in these files. With no FILE: the files "
                           "git reports as changed or new (git diff HEAD, plus untracked). For checking "
                           "after each edit.")
    todo.add_argument("--jobs", type=int, default=4, metavar="N",
                      help="Ask about N claims at the same time. Default: 4. Use 1 to go one at a time.")
    todo.add_argument("--key-file", metavar="FILE",
                      help="Read TYPESAFE_API_KEY=... from this file instead of the environment or ./.env - "
                           "keep one protected file instead of a key in every project.")
    todo.add_argument("--no-cache", action="store_true",
                      help=f"Ask again even for code and sentences that have not changed since the last "
                           f"run. Answers are cached in {CACHE_FILE} as hashes only - never your code.")
    todo.add_argument("--samples", type=int, default=SAMPLES, metavar="N",
                      help=f"how many times to ask about a claim the first answer did not settle "
                           f"(default {SAMPLES}; 1 never re-asks). A claim is decided by agreement "
                           f"only when every answer matches and none is below {AGREE_FLOOR}.")
    todo.add_argument("--limit", type=int, default=0, metavar="N",
                      help="Check only the first N claims, in spec order - a cheap first try. Default: all")
    return ap


def _load_key(key_file: str | None = None, dotenv: bool = True) -> str:
    """--key-file alone if given; else TYPESAFE_API_KEY; else (command line only, dotenv=True)
    the .env of the folder you run from. The MCP server passes dotenv=False: a project it is
    pointed at must not be able to supply a key of its own."""
    if key_file:
        kf = Path(key_file).expanduser()
        if not kf.is_file():
            raise Stop(f"--key-file {key_file} not found.")
        for line in kf.read_text(errors="replace").splitlines():
            if m := re.match(r"\s*(?:export\s+)?TYPESAFE_API_KEY\s*=\s*(.+)", line):
                return m.group(1).strip().strip('"').strip("'")
        raise Stop(f"{key_file} has no TYPESAFE_API_KEY=... line.")
    key = os.environ.get("TYPESAFE_API_KEY")
    env = Path.cwd() / ".env"
    if not key and dotenv and env.is_file():
        for line in env.read_text(errors="replace").splitlines():
            if m := re.match(r"\s*(?:export\s+)?TYPESAFE_API_KEY\s*=\s*(.+)", line):
                key = m.group(1).strip().strip('"').strip("'")
    if not key:
        where = (f", or put the line\n  TYPESAFE_API_KEY=...\ninto {env} (only the .env in the folder you run from is read)"
                 if dotenv else ", or pass --key-file FILE (this command never reads a .env file)")
        raise Stop(f"no API key, so nothing was sent. Set TYPESAFE_API_KEY in the environment{where}.\n"
                   f"Get a key at https://console.typesafe.ai. To look without a key, add --dry-run.")
    return key


def _changed_files(given: list[str], src: Path) -> set[str]:
    """Resolved paths of the changed files: as given, or what git reports as changed or new."""
    import subprocess
    if given:
        return {str(Path(f).resolve()) for f in given}
    out = set()
    for cmd in (["git", "diff", "--name-only", "HEAD"], ["git", "ls-files", "--others", "--exclude-standard"]):
        r = subprocess.run(cmd, cwd=src, capture_output=True, text=True)
        if r.returncode != 0:
            raise Stop(f"--changed with no files needs a git repository at {src.resolve()}: {r.stderr.strip()[:120]}")
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=src, capture_output=True, text=True).stdout.strip()
        out |= {str((Path(top) / f).resolve()) for f in r.stdout.split()}
    return out


def _touches(c: Claim, changed: set[str]) -> bool:
    for s in c.symbols:
        files = [s.file]
        if s.kind == "config":                  # a setting lives in several files
            files += re.findall(r"^\w+\s+(\S+?):\d+", s.source, re.M)
        if any(str(Path(f).resolve()) in changed for f in files if f):
            return True
    return False


def _print_claim(i: int, c: Claim, sent: int, total: int) -> None:
    print(f"\n  [{i}/{total}] {c.doc}:{c.line}  ({c.why_paired})")
    print(f"    claim: {c.text[:110]}")
    for k, s in enumerate(c.symbols):
        print(f"    {'code :' if k == 0 else '       '} {s.file}:{s.line} {s.kind} {s.name}")
    print(f"    sends: {sent:,} characters")


def safe_path() -> None:
    """Drop empty and relative PATH entries: with '.' on PATH a `git` or `gh` planted in the project
    folder would run instead of the real one."""
    os.environ["PATH"] = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if p and os.path.isabs(p))


def main() -> None:
    safe_path()
    here = Path(__file__).resolve().parent
    inside_tool_folder = Path.cwd().resolve() == here
    if len(sys.argv) == 1:
        if inside_tool_folder:
            print("NOTE: you are inside the tool's own folder. First cd into the project you want to check.\n")
        print(quick_start())
        if not sys.stdout.isatty():
            sys.exit(2)        # in CI, an empty argument list is a mistake, not a pass
        return
    args = build_parser().parse_args()
    try:
        sys.exit(run(args, inside_tool_folder))
    except Stop as e:
        _die(str(e))


def _cli_ignore(args) -> tuple[str, ...]:
    return tuple(dict.fromkeys(([] if args.no_default_ignore else DEFAULT_IGNORE)
                               + [n.strip("/").removeprefix("./") for n in args.ignore]))


def _cli_find_specs(args) -> int:
    """--find-specs: the candidate spec files, for the user to choose from. Nothing is drafted."""
    if args.docs or args.map or args.draft_map:
        raise Stop("--find-specs lists the files that look like specs and stops: leave out --docs, --map and "
                   "--draft-map.")
    if Path(args.src).resolve() != Path.cwd().resolve():
        raise Stop(f"--find-specs lists the files of the folder you run from ({Path.cwd()}), not of --src: cd into "
                   f"the project and leave out --src.")
    root = Path.cwd()
    survey = SpecSurvey(root, _cli_ignore(args))
    found = spec_candidates(root, (), survey=survey)
    print("\n".join(candidates_text(found, spec_families(found, survey))))
    if w := _not_utf8_warning(not_utf8_specs(survey), "that look like specs"):
        print(f"\nWARNING: {w}")
    print("\nNothing was drafted. Decide which file(s) are the current spec - never a folder that holds several "
          "versions - then:\n    " + _cmd() + " --docs <file> [<file> ...] --draft-map spec_map.json")
    return 0


def _cli_update_lines(args) -> int:
    """--update-lines: store the current line of every map entry whose sentence has moved."""
    if not args.map:
        raise Stop("--update-lines needs --map: the map whose line numbers to update.")
    if args.docs or args.draft_map:
        raise Stop("--update-lines works on a map only: leave out --docs and --draft-map.")
    if not Path(args.map).is_file():
        raise Stop(f"map file not found: {args.map}  (paths are relative to the folder you run from: {Path.cwd()})")
    n, notes = update_map_lines(Path(args.map), Path(args.src))
    for note in notes:
        print(f"  note: {note}")
    print(f"updated the line of {n} map entr{'y' if n == 1 else 'ies'} in {args.map} whose sentence had moved in the "
          f"spec; nothing else in the file changed." if n else
          f"no entry of {args.map} has moved in the spec: nothing was changed.")
    return 0


def run(args, inside_tool_folder: bool) -> int:
    if getattr(args, "find_specs", False):
        return _cli_find_specs(args)
    if getattr(args, "update_lines", False):
        return _cli_update_lines(args)
    if args.draft_map and not args.docs:
        raise Stop("--draft-map needs the spec to draft from: add --docs docs/spec.md")
    if not args.docs and not args.map:
        raise Stop("say which spec to check: --docs docs/spec.md (the spec itself) "
                   "or --map spec_map.json (a reviewed map).")
    if args.docs and args.map and not args.draft_map:
        raise Stop("use --docs OR --map, not both. --docs pairs sentences automatically; "
                   "--map uses the pairings you reviewed. With both, the map would silently win.")
    if args.map and not Path(args.map).is_file():
        raise Stop(f"map file not found: {args.map}  (paths are relative to the folder you run from: {Path.cwd()})")
    for d in args.docs:
        if not Path(d).exists():
            raise Stop(f"spec not found: {d}  (paths are relative to the folder you run from: {Path.cwd()})")
    src = Path(args.src)
    if inside_tool_folder and args.src == ".":
        raise Stop("you are inside the tool's own folder, so there is no project code here to check.\n"
                   f"cd into the project you want to check, then run:\n    python {Path(__file__).resolve()} "
                   + " ".join(sys.argv[1:]))
    if not src.is_dir():
        raise Stop(f"no folder {args.src!r}. --src is the folder with your code; leave it out to use the current folder.")
    if args.limit < 0:
        raise Stop("--limit must be 0 (all claims) or a positive number.")
    if args.draft_map and Path(args.draft_map).exists():
        raise Stop(f"{args.draft_map} already exists and may hold a reviewed map - nothing was written.\n"
                   f"Draft into a new file and compare, e.g.  --draft-map {Path(args.draft_map).stem}.draft.json")
    ignore = tuple(dict.fromkeys(([] if args.no_default_ignore else DEFAULT_IGNORE)
                                 + [n.strip("/").removeprefix("./") for n in args.ignore]))
    problems: list[str] = []          # exit 2: the team must fix something
    vendor: list[str] = []            # exit 3: TypeSafe could not be used
    docs: list[Path] = []
    doc_warnings: list[str] = []
    if args.docs:                     # before any code is read: a folder of spec versions is refused at once
        here = Path.cwd().resolve()
        files, doc_warnings = expand_docs(here, args.docs, ignore)
        docs = [Path(os.path.relpath(f, here)) for f in files]

    t0 = time.time()
    syms, counts = index_code(src, ignore)
    langs = ", ".join(f"{k} {v:,}" for k, v in counts.items() if v and k not in ("routes", "config keys")) or "none"
    total_syms = sum(v for k, v in counts.items() if k not in ("routes", "config keys"))
    print(f"read the code in {src.resolve()} ({time.time() - t0:.1f}s): {total_syms:,} functions, classes and "
          f"constants ({langs}), {counts['routes']} routes, {counts['config keys']} config keys")
    if args.ignore:
        print(f"  also skipping folders: {', '.join(args.ignore)}")
    for suffix, n in sorted(unindexed_sources(src, ignore).items()):
        if suffix in _MISSING:
            problems.append(f"{n} {suffix} files were NOT read - the parser is missing. Install it into this Python:\n"
                            f"      {sys.executable} -m pip install {_MISSING[suffix]}\n"
                            f"    (or skip those folders with --ignore)")
        else:
            print(f"  note: {n} {suffix} files can only be paired by line range (file:120-160)")
    if ".yml" in _MISSING:
        problems.append(f"Spring YAML config was NOT read - install PyYAML:  {sys.executable} -m pip install pyyaml")
    for note in _NOTES[:10]:
        print(f"  note: {note}")
    if total_syms == 0 and not _MISSING:
        problems.append(f"no code found in {src.resolve()}. Run from the project's folder, or point --src at the code.")

    for w in doc_warnings:
        print(f"  WARNING: {w}")

    if args.draft_map:
        draft_map(docs, syms, Path(args.draft_map))
        for pr in problems:
            print(f"  PROBLEM: {pr}")
        return 2 if problems else 0

    claims: list[Claim] = []
    if args.map:
        claims = claims_from_map(Path(args.map), syms, src=src, problems=problems)
        print(f"  {args.map}: {len(claims)} map entries ready to check"
              + (f"; {MAP_COUNTS['excluded']} marked excluded (not requirements, never sent)"
                 if MAP_COUNTS["excluded"] else ""))
        if MAP_COUNTS.get("moved"):
            print(f"  note: to store the current line numbers in the map, run:  --map {args.map} --update-lines  "
                  f"(it changes only the \"line\" fields)")
        versions = spec_version_report(Path(args.map), Path.cwd(), ignore, src=src)
        for w in versions["warnings"]:
            print(f"  WARNING: {w}")
        problems.extend(versions["problems"])
        if versions["problems"] and not args.dry_run:
            raise Stop("the check was refused and nothing was sent: " + " ".join(versions["problems"]))
        if args.strict:
            problems.extend(f"{n} (--strict)" for n in MAP_NOTES)
    else:
        for d in docs:
            unpaired: list[tuple[int, str]] = []
            found = find_claims(d, syms, unpaired=unpaired)
            claims.extend(found)
            print(f"  {d}: {len(found)} of {len(found) + len(unpaired)} sentences paired with code")
            if unpaired and args.strict:
                problems.append(f"{len(unpaired)} sentences in {d} are not paired with code (--strict)")
            if unpaired:
                print(f"  not paired, so NOT checked - name the code in backticks, or use a map (step 2):")
                for ln, sent in unpaired[:30]:
                    print(f"      line {ln}: {sent[:90]}")
                if len(unpaired) > 30:
                    print(f"      ... and {len(unpaired) - 30} more")
    if args.changed is not None:
        changed = _changed_files(args.changed, src)
        before = len(claims)
        claims = [c for c in claims if _touches(c, changed)]
        print(f"  --changed: {len(changed)} changed file(s); {len(claims)} of {before} claims are about them")
        if not claims:
            print("  nothing in the spec is about the changed files - nothing to check.")
            return 0
    if args.limit and args.limit < len(claims):
        print(f"  --limit {args.limit}: checking the first {args.limit} of {len(claims)} claims")
        claims = claims[: args.limit]
    for pr in problems:
        print(f"  PROBLEM: {pr}")
    if not claims:
        raise Stop("nothing to check. " + ("No map entry could be used - see the PROBLEM lines above."
                                          if args.map else
                                          "No sentence names code in backticks. Draft a map instead (step 2):\n"
                                          f"    python {_tool_path()} --docs {' '.join(args.docs)} --draft-map spec_map.json"))

    if args.show_payload and claims:
        print("\nEvery request is: model " + MODEL + ", a \"state\" (shown per claim below: the sentence as \"claim\",\n"
              "the paired \"code\", and \"computed_values\" when the tool did arithmetic for the model), and these\n"
              "3 fixed questions, identical for every claim:")
        print(textwrap.indent(json.dumps(build_questions(), indent=2, ensure_ascii=False), "    "))
    if args.dry_run:
        plan = []
        for i, c in enumerate(claims, 1):
            state = build_state(c)
            _print_claim(i, c, len(json.dumps(state)), len(claims))
            if args.show_payload:
                print("    state sent for this claim:")
                print(textwrap.indent(json.dumps(canonical(state), indent=2, ensure_ascii=False), "      "))
            warn = preflight(c)
            for w in warn:
                print(f"    LIKELY ?? : {w}")
            plan.append({"doc": c.doc, "line": c.line, "claim": c.text,
                         "code_refs": [f"{s.file}:{s.line} {s.name}" for s in c.symbols],
                         "likely_unverifiable": warn, "state": canonical(state)})
        weak = sum(1 for e in plan if e["likely_unverifiable"])
        if weak:
            print(f"\n  {weak} of {len(claims)} claims will probably come back \"??\" - each costs a request "
                  f"and answers nothing. Fix those entries before spending.")
        print(f"\ndry run - nothing was sent. {len(claims)} claim{'s' if len(claims) != 1 else ''}, "
              f"estimated cost ${estimate_cost(claims):.4f}"
              + (f", up to ${estimate_cost(claims, args.samples):.4f} if every claim needs re-asking."
                 if getattr(args, "samples", 1) > 1 else "."))
        if args.out:
            Path(args.out).write_text(json.dumps({"claims": plan, "problems": problems,
                                                  "estimated_cost_usd": round(estimate_cost(claims), 5)},
                                                 indent=1, ensure_ascii=False))
            print(f"plan -> {Path(args.out).resolve()}")
        if problems:
            print(f"INCOMPLETE: {len(problems)} problem(s) above - fix them before the real check. Exit code 2.")
            return 2
        return 0

    key = _load_key(args.key_file)
    t0 = time.time()
    print(f"\nchecking {len(claims)} claim{'s' if len(claims) != 1 else ''}, {max(1, args.jobs)} at a time")
    if args.show_payload:
        for c in claims:
            print(textwrap.indent(json.dumps(canonical(build_state(c)), indent=2, ensure_ascii=False), "      "))
    results, tokens, stopped, failed = check_claims(claims, key, args.jobs,
                                                    samples=max(1, args.samples),
                                                    use_cache=not args.no_cache)
    problems += stopped
    vendor += failed

    args.out = args.out or "drift.json"
    Path(args.out).write_text(json.dumps(results, indent=1, ensure_ascii=False))
    acts = [r for r in results if r["action"] == "act"]
    revs = [r for r in results if r["action"] == "review"]
    unv = [r for r in results if r["action"] == "unverifiable"]
    print(f"\n{'─' * 72}")
    print(f"checked {len(results)} of {len(claims)} claims in {time.time() - t0:.1f}s | "
          f"{tokens:,} input tokens | ${tokens * 0.042 / 1e6:.4f}")
    print(f"DRIFT:          {len(acts)}")
    print(f"needs review:   {len(revs)}")
    print(f"??:             {len(unv)}   <- NOT a pass: the code shown could not settle these")
    print(f"ok:             {len(results) - len(acts) - len(revs) - len(unv)}")
    if LAST_RUN_REPLAYED:
        print(f"({LAST_RUN_REPLAYED} answer(s) came from the cache - unchanged code is not paid for twice)")
    health = map_health(results, claims, syms)
    if health["unverifiable"]:
        print(f"\nMAP HEALTH: {health['unverifiable']} of {health['checked']} claims "
              f"({health['unverifiable_pct']}%) came back ?? - their pairing cannot settle their sentence. "
              f"That is a map problem, not a code problem.")
        for e in health["entries_to_fix"][:5]:
            print(f"  {e['doc']}:{e['line']}  {e['claim'][:70]}")
            for why in e.get("reasons", [])[:1]:
                print(f"      because: {why}")
            if e.get("try_pairing_with"):
                print(f"      try pairing with: {', '.join(e['try_pairing_with'])}")
        if len(health["entries_to_fix"]) > 5:
            print(f"  ... and {len(health['entries_to_fix']) - 5} more (every one is in {args.out})")
    print(f"\nfull results -> {Path(args.out).resolve()}")
    for r in sorted(acts, key=lambda r: -r["severity"])[:10]:
        print(f"\n  {r['doc']}:{r['line']}  severity {r['severity']}/3  conf {r['confidence']}"
              + (f"  ({r['samples']} answers agreed)" if r.get("samples", 1) > 1 else ""))
        print(f"    says: {r['claim'][:100]}")
        print(f"    code: {r['code_file']}:{r['code_line']} ({r['symbol']})")
    if problems or vendor:
        code = 2 if problems else 3
        print(f"\nINCOMPLETE - exit code {code}. Not everything was checked:")
        for pr in problems + vendor:
            print(f"  - {pr}")
        return code
    return 1 if acts else 0


if __name__ == "__main__":
    main()
