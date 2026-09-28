"""Start the jevmcp server exactly as a client does (uv run --quiet --script), with no API key,
on a small throwaway project, and check that it answers MCP and that every free tool works.
The three tools that send data must refuse clearly without a key. Standard library only;
runs on Linux, macOS and Windows.   python .github/smoke/mcp_smoke.py [path/to/jevmcp_server.py]"""
import json
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


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=smoke", "-c", "user.email=smoke@localhost", *args],
                   cwd=root, check=True, capture_output=True)


def make_project(root: Path) -> None:
    files = {
        "docs/spec.md": "# Orders spec\n\nAn order may contain at most 50 items, set by MAX_ITEMS in app.py.\n",
        "app.py": "MAX_ITEMS = 50\n\n\ndef place(items):\n    if len(items) > MAX_ITEMS:\n"
                  "        raise ValueError('too many items')\n    return len(items)\n",
        "CLAUDE.md": "# Rules\n\n- Every function in app.py must have a docstring.\n",
        "ci/failed.log": "##[group]Run python -m pytest -q\npython -m pytest -q\n##[endgroup]\n"
                         "E       ValueError: too many items\nFAILED tests/test_app.py::test_limit\n"
                         "##[error]Process completed with exit code 1.\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8", newline="\n")
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
                if "error" in msg:
                    raise SystemExit(f"FAIL: {method}: {msg['error']}")
                return msg["result"]

    def tool(self, name: str, **args) -> tuple[bool, str]:
        r = self.call("tools/call", {"name": name, "arguments": args})
        return bool(r.get("isError")), "\n".join(c.get("text", "") for c in r.get("content", []))

    def close(self) -> None:
        self.p.stdin.close()
        try:
            self.p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.p.kill()


def review(path: Path, fill) -> None:
    m = json.loads(path.read_text(encoding="utf-8"))
    for e in m["entries"] if isinstance(m, dict) else m:
        fill(e)
    path.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "proj"
        root.mkdir()
        make_project(root)
        c = Client(root)
        t0 = time.time()
        init = c.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "smoke", "version": "1"}}, timeout=300)
        print(f"server {init['serverInfo']['name']} {init['serverInfo']['version']} answered in {time.time() - t0:.1f} s")
        c.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        c.p.stdin.flush()
        names = {t["name"] for t in c.call("tools/list")["tools"]}
        assert names == FREE | SENDING, f"tools: {sorted(names)}"
        results = []

        def run(name: str, want_error: bool = False, must: str = "", **args) -> None:
            err, text = c.tool(name, **args)
            ok = err == want_error and must in text
            results.append(ok)
            print(f"{'ok  ' if ok else 'FAIL'} {name}: {text.strip().splitlines()[0][:110] if text.strip() else '(empty)'}")
            if not ok:
                print(text[:2000])

        run("draft_spec_map", docs=["docs/spec.md"], out="spec_map.json")
        review(root / "spec_map.json", lambda e: e.update(
            status="reviewed", code=e.get("code") or ["app.py:MAX_ITEMS"]))
        run("validate_spec_map", must="OK - ", map="spec_map.json")
        run("preview_spec_check", must="1 claim(s)", map="spec_map.json", files=["app.py"])
        run("draft_rule_map", out="rule_map.json")
        review(root / "rule_map.json", lambda e: e.update(status="reviewed") if e.get("status") != "excluded" else None)
        run("validate_rule_map", must="OK - ", map="rule_map.json")
        run("preview_code_audit", must="nothing was sent", map="rule_map.json", all=True)
        run("preview_ci_triage", must="1 distinct failure", logs=["ci/failed.log"])
        # an audit first asks for the unit count the user agreed to; then, with no key, it must refuse
        _, text = c.tool("check_code_rules", map="rule_map.json", all=True)
        units = int(re.search(r"confirm_units: (\d+)", text).group(1))
        for name, args in (("check_spec_drift", {"map": "spec_map.json", "all": True}),
                           ("check_code_rules", {"map": "rule_map.json", "all": True, "confirm_units": units}),
                           ("triage_ci_failure", {"logs": ["ci/failed.log"]})):
            run(name, want_error=True, must="API key", **args)
        c.close()
    print(f"{sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
