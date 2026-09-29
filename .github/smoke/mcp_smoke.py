"""Start the jevmcp server exactly as a client does (uv run --quiet --script), with no API key,
on a small throwaway project, and check that it answers MCP and that every free tool works.
The three tools that send data must refuse clearly without a key. The project's spec, rules,
code and CI log hold Cyrillic, Chinese and typographic quotes, and the log's name is Cyrillic: on
Windows the server's locale is cp1252 (and on macOS, in the C locale, ASCII), and every map it writes
must still be UTF-8 and every preview must show that text exactly. On Linux in the C locale the
server starts itself again in Python's UTF-8 mode, so there the run checks that restart and the name.
Standard library only; runs on Linux, macOS and Windows.
    python .github/smoke/mcp_smoke.py [path/to/jevmcp_server.py]"""
import codecs
import json
import locale
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SERVER = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "plugins/jevmcp/scripts/jevmcp_server.py").resolve()
FREE = {"draft_spec_map", "validate_spec_map", "preview_spec_check", "draft_rule_map", "validate_rule_map",
        "preview_code_audit", "preview_ci_triage"}
SENDING = {"check_spec_drift", "triage_ci_failure", "check_code_rules"}
SPEC = ["An order may contain at most 50 items, set by MAX_ITEMS in app.py.",
        "A larger order is refused with the error “too many items — слишком много товаров”.",
        "Заказ не может содержать больше MAX_ITEMS позиций.",
        "订单最多包含 MAX_ITEMS 个商品。"]
RULES = ["Every function in app.py must have a docstring.",
         "Error messages must name the limit, for example “too many items — слишком много товаров”.",
         "所有函数必须有文档字符串。"]
CODE_COMMENT = "# «лимит» → 订单上限"                   # only in app.py: a preview showing it read the code right
LOG_LINE = "✕ refuses a larger order → «слишком много товаров» (5 ms)"
LOG = "ci/журнал.log"                                  # a name in UTF-8, as git checks it out


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=smoke", "-c", "user.email=smoke@localhost", *args],
                   cwd=root, check=True, capture_output=True)


def make_project(root: Path) -> None:
    files = {
        "docs/spec.md": "# Orders spec — «Заказы»\n\n" + "\n\n".join(SPEC) + "\n",
        "app.py": f"MAX_ITEMS = 50  {CODE_COMMENT}\n\n\ndef place(items):\n    if len(items) > MAX_ITEMS:\n"
                  "        raise ValueError('too many items')\n    return len(items)\n",
        "CLAUDE.md": "# Rules — «Правила»\n\n" + "".join(f"- {r}\n" for r in RULES),
        LOG: "##[group]Run python -m pytest -q\npython -m pytest -q\n##[endgroup]\n"
             f"    {LOG_LINE}\n"
             "E       ValueError: too many items\nFAILED tests/test_app.py::test_limit\n"
             "##[error]Process completed with exit code 1.\n",
    }
    for rel, text in files.items():
        # a bytes path: in the C locale this script's own Python cannot encode a Cyrillic name
        path = os.path.join(os.fsencode(root), *(part.encode("utf-8") for part in rel.split("/")))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(text.encode("utf-8"))
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "first")


class Client:
    def __init__(self, cwd: Path) -> None:
        # no key from anywhere: not the environment, not a plugin data folder, not --set-key storage
        drop = {"TYPESAFE_API_KEY", "PLUGIN_DATA", "CLAUDE_PLUGIN_DATA", "CLAUDE_PROJECT_DIR"}
        env = {k: v for k, v in os.environ.items() if k not in drop}
        env["XDG_CONFIG_HOME"] = str(cwd.parent / "config")          # no stored key either
        env["APPDATA"] = env["XDG_CONFIG_HOME"]
        stored = Path(env["XDG_CONFIG_HOME"]) / "jevmcp" / "typesafe.env"
        assert not env.get("TYPESAFE_API_KEY") and not stored.exists(), "a key would reach the server"
        self.p = subprocess.Popen(["uv", "run", "--quiet", "--script", str(SERVER)], cwd=cwd, env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr,
                                  text=True, encoding="utf-8", bufsize=1)
        self.n = 0
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.p.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def call(self, method: str, params: dict | None = None, timeout: float = 90) -> dict:
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        while True:
            try:
                line = self.lines.get(timeout=timeout)
            except queue.Empty:
                self.p.kill()
                raise SystemExit(f"FAIL: no answer to {method} {json.dumps(params or {})[:200]} within {timeout:.0f} s")
            if not line:
                raise SystemExit(f"FAIL: the server closed its output during {method}")
            msg = json.loads(line)
            if msg.get("id") == self.n:
                if "error" in msg and method != "tools/call":
                    raise SystemExit(f"FAIL: {method}: {msg['error']}")
                return msg

    def tool(self, name: str, **args) -> tuple[bool | None, str]:
        """(isError, text); None when the server failed inside the tool (a JSON-RPC error): a failed check."""
        msg = self.call("tools/call", {"name": name, "arguments": args})
        if "error" in msg:
            return None, f"JSON-RPC error {msg['error'].get('code')}: {msg['error'].get('message')}"
        r = msg["result"]
        return bool(r.get("isError")), "\n".join(c.get("text", "") for c in r.get("content", []))

    def close(self) -> None:
        self.p.stdin.close()
        try:
            self.p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.p.kill()


def load(path: Path) -> tuple[list[str] | None, str]:
    """A map the server wrote, read as the next machine reads it: the texts of its entries if it is UTF-8
    JSON (else None), and what the file holds, for the log."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        return None, str(e)
    try:
        return [e.get("text") for e in json.loads(raw.decode("utf-8"))["entries"]], ""
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        return None, f"{e}\n{raw[:2000].decode('utf-8', 'replace')}"


def review(path: Path, fill) -> None:
    m = json.loads(path.read_text(encoding="utf-8"))
    for e in m["entries"]:
        fill(e)
    path.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):     # the replies hold Cyrillic and Chinese; a pipe on Windows is cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    # the server gets this same environment; where file names are not UTF-8 (Linux in the C locale) it starts
    # itself again in Python's UTF-8 mode, so there this run checks that restart, not how text is read and written
    restarts = (os.name == "posix" and not sys.flags.utf8_mode
                and codecs.lookup(sys.getfilesystemencoding()).name != "utf-8"
                and os.environ.get("JEVMCP_NO_UTF8_RESTART", "").strip() in ("", "0"))
    print(f"locale encoding {locale.getpreferredencoding(False)}, UTF-8 mode "
          f"{'on' if sys.flags.utf8_mode else 'off'} - "
          + ("file names are not UTF-8 here, so the server starts itself again in Python's UTF-8 mode: this run "
             f"checks that restart and the name {LOG}, not how text is read and written" if restarts else
             "the server runs with the same locale encoding"))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        root.mkdir()
        make_project(root)
        c = Client(root)
        t0 = time.time()
        init = c.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "smoke", "version": "1"}}, timeout=300)["result"]
        print(f"server {init['serverInfo']['name']} {init['serverInfo']['version']} answered in {time.time() - t0:.1f} s")
        c.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        c.p.stdin.flush()
        names = {t["name"] for t in c.call("tools/list")["result"]["tools"]}
        assert names == FREE | SENDING, f"tools: {sorted(names)}"
        results = []

        def check(label: str, ok: bool, detail: str, text: str = "") -> None:
            results.append(ok)
            print(f"{'ok  ' if ok else 'FAIL'} {label}: {detail}")
            if not ok and text:
                print(text[:2000])

        def run(name: str, want_error: bool = False, must: tuple[str, ...] = (), **args) -> None:
            err, text = c.tool(name, **args)
            check(name, err == want_error and all(m in text for m in must),
                  text.strip().splitlines()[0][:110] if text.strip() else "(empty)", text)

        run("draft_spec_map", must=(f"wrote {len(SPEC)} spec sentences",), docs=["docs/spec.md"], out="spec_map.json")
        texts, held = load(root / "spec_map.json")
        check("spec_map.json", texts == SPEC, f"UTF-8, the {len(SPEC)} sentences exactly as written", held or str(texts))
        if texts is not None:
            review(root / "spec_map.json", lambda e: e.update(
                status="reviewed", code=e.get("code") or ["app.py:MAX_ITEMS"]))
        run("validate_spec_map", must=("OK - ",), map="spec_map.json")
        sent = tuple(f'"claim": {json.dumps(s, ensure_ascii=False)}' for s in SPEC)   # each state as it would go
        run("preview_spec_check", must=(f"{len(SPEC)} claim(s)", *sent), map="spec_map.json", files=["app.py"])
        run("draft_rule_map", must=(f"{len(RULES)} rule sentence(s)",), out="rule_map.json")
        texts, held = load(root / "rule_map.json")
        check("rule_map.json", texts == RULES, f"UTF-8, the {len(RULES)} rules exactly as written", held or str(texts))
        if texts is not None:
            review(root / "rule_map.json", lambda e: e.update(status="reviewed") if e.get("status") != "excluded" else None)
        run("validate_rule_map", must=("OK - ",), map="rule_map.json")
        run("preview_code_audit", must=("nothing was sent", CODE_COMMENT, RULES[1]), map="rule_map.json", all=True)
        run("preview_ci_triage", must=("1 distinct failure", LOG_LINE), logs=[LOG])
        # an audit first asks for the unit count the user agreed to; then, with no key, it must refuse
        _, text = c.tool("check_code_rules", map="rule_map.json", all=True)
        units = re.search(r"confirm_units: (\d+)", text)
        run("check_spec_drift", want_error=True, must=("API key",), map="spec_map.json", all=True)
        if units:
            run("check_code_rules", want_error=True, must=("API key",), map="rule_map.json", all=True,
                confirm_units=int(units.group(1)))
        else:
            check("check_code_rules", False, "its first answer names no confirm_units to agree to", text)
        run("triage_ci_failure", want_error=True, must=("API key",), logs=[LOG])
        c.close()
    print(f"{sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
