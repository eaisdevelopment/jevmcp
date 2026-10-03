#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["tree-sitter>=0.25", "tree-sitter-java>=0.23", "tree-sitter-javascript>=0.23",
#                 "tree-sitter-typescript>=0.23", "pyyaml>=6.0"]
# ///
"""code_audit - screen a codebase against its own written rules and conventions.

TypeSafe's fast model Jev reads one rule and one unit of code at a time and says whether the code
breaks the rule; the agent investigates only what it flags. Never one broad "does this follow our
conventions?" question: the one broad review question measured ("is this change security-sensitive?")
scored 38.5%, while named checklists did well. Each rule is checked on its own, the way a named
checklist is, and it catches only what the rule map names.

    rule_map.json   one entry per rule sentence from the project's OWN files (CLAUDE.md, AGENTS.md,
                    CONTRIBUTING, style guides ...), with the files it applies to. draft_rule_map
                    writes it; the user reviews it with the agent; it is committed with the code.
    units           functions/classes/blocks of the files a rule applies to - by default only the
                    ones the change under test touches. Comments are removed (text the author wrote
                    about their own code steers a verdict about it), except for rules about comments,
                    which are asked separately.
    labels          BREAKS - the unit breaks the rule, confidently; the agent reads it and decides
                    review  - sorted by P(breaks): read from 0.3 up; ok - follows it;
                    n/a     - the rule is not about this unit (and P(breaks) is below 0.3)
                    ??      - the code shown cannot settle it: NOT a pass

    python code_audit.py --draft-map rule_map.json --src .
    python code_audit.py --map rule_map.json --src . --base origin/main --dry-run
"""
from __future__ import annotations

import argparse
import codecs
import contextlib
import fnmatch
import json
import locale
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jevkit                      # noqa: E402
import spec_drift as dd            # noqa: E402

ACT_ABOVE = 0.905          # BREAKS on one answer
CLEAN_ABOVE = 0.905        # ok on one answer (and the breaks Noul below NOUL_NO)
AGREE_FLOOR = 0.855
NOUL_NO = 0.295
SAMPLES = 3                # re-ask what one answer did not settle: a false BREAKS costs trust
MAX_CODE_CHARS = 2_600     # measured for spec claims: accuracy falls with clutter
MAX_RULE_CHARS = 1_200
STATE_VERSION = "audit-state-1"
LABELS = {"act": "BREAKS", "review": "review", "clean": "ok", "na": "n/a", "unverifiable": "??"}


class Stop(dd.Stop):
    """A setup problem (exit 2)."""


# ─────────────────────────────────────────────────────────────── 1. where a project writes its rules

# The files coding agents read, by their exact names, capitals included: a name that only starts with them
# (claude_how_to_x.md, agents_notes.md) is a document ABOUT the agent - one such how-to gave 184 of a draft's 204
# entries - and so is docs/agents.md, an SDK's page about its Agent class.
AGENT_RULE_FILE = r"(?-i:^(?:CLAUDE(?:\.local)?|AGENTS(?:\.override)?)\.md$)"
# Other rule files by a rule word in their name, anywhere in it (python-style-guide.md, CONTRIBUTING_ja.md), as a
# word of its own - a camel-case one too, after an acronym as well (ContributingGuide.md, JavaCodingStandards.md,
# JSStyleGuide.md; not ConventionalCommits.md) - and the development notes by their whole name (development_log.md
# is a log).
RULE_FILE_NAMES = re.compile(rf"(?i){AGENT_RULE_FILE}|"
                             r"(?:^|[-_. ]|(?-i:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])))"
                             r"(?:contributing|conventions?|coding[-_ ]?(?:style|"
                             r"standards?|conventions?|guidelines?)|code[-_ ]?style|style[-_ ]?guides?|guidelines?|"
                             r"code[-_ ]?review)(?:(?![a-z])|(?-i:(?<=[a-z])(?=[A-Z])))[\w.-]*"
                             r"\.(?:md|mdx|rst|txt|adoc|mdc)$|"
                             r"^(?:developing|development|hacking)(?:[-_ ]?guide)?\.(?:md|mdx|rst|txt|adoc|mdc)$|"
                             r"^copilot-instructions\.md$|\.instructions\.md$")
AGENT_RULE_FILES = re.compile(AGENT_RULE_FILE)
PLAIN_RULE_FILES = {"CONTRIBUTING", "CONVENTIONS"}     # plain text with no extension
# Every document in these folders states rules; in the others, one whose own name - or a folder's name below
# the docs folder - has a rule word. Never a word elsewhere in the path: docs/claude-desktop-setup.md and
# docs/developer-api-reference.md are not rule files.
RULE_ONLY_DIRS = re.compile(r"(?i)(?:^|/)(?:contribute|contributing(?:-docs)?|style[-_]?guides?)/")
RULE_DIRS = re.compile(r"(?i)(?:^|/)(?:\.github|\.cursor/rules|docs?|developers?|dev|internals|guides?)/")
# A word starts the name, follows a separator or starts a camel-case word, after an acronym too: CodeStyle.md,
# codestyle.md, JavaCodingStandards.md, APIGuidelines.md, developers-guide.md are style guides; lifestyle.md is not.
RULE_NAME_WORDS = re.compile(r"(?:(?<![A-Za-z])|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z]))"
                             r"(?i:(?:code|coding)?style|(?:code)?conventions?|"
                             r"guideline|contribut|coding|standards(?![a-z])|code[-_ ]?review|developers?[-_ ]?guide)")
DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".adoc", ".mdc"}
CURSOR_RULES = re.compile(r"(?:^|/)\.cursor/rules/[^/]+\.mdc?$")    # every file there is a rule file, whatever its name
# So is every file the coding agent itself loads as rules: Claude Code's .claude/rules (subfolders too) and the
# documents in Cline's .clinerules folder (not its workflows/ or hooks/), or .clinerules as one plain file.
AGENT_RULE_DIRS = re.compile(r"(?:^|/)(?:\.claude/rules/(?:[^/]+/)*[^/]+\.md|\.clinerules/[^/]+)$")


def tracked_files(root: Path) -> list[str]:
    """Files git would commit (tracked + untracked-not-ignored), relative. Ignored local files - build
    output, a developer's .env, credentials - are never candidates for an audit."""
    try:
        # LC_ALL=C: git's messages in English, which the check below reads. A translated git ("kein
        # Git-Repository") stopped every audit of a folder outside git.
        out = subprocess.run(dd.git_argv("-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"),
                             capture_output=True, timeout=60, check=True, env={**os.environ, "LC_ALL": "C"},
                             stdin=subprocess.DEVNULL).stdout.decode(errors="replace")
        return [p for p in out.split("\0") if p]
    except subprocess.CalledProcessError as e:
        # Only a folder that is not a git repository falls back to every file. In a repository git
        # could not read (dubious ownership, a broken index) that would take ignored files too.
        err = (e.stderr or b"").decode(errors="replace")
        # told by the folder too: in a worktree whose repository is gone git says "not a git repository" as well
        if "not a git repository" not in err or dd._in_git_worktree(root):
            raise Stop(f"git could not list this project's files, so none was read: {err.strip()[:200]}") from None
    except subprocess.TimeoutExpired:
        raise Stop("git took more than 60 s to list this project's files, so none was read.") from None
    except FileNotFoundError:
        # No git at all. In a git repository that would take ignored files too (a local .env, build
        # output, credentials), so nothing is read; a folder outside git has nothing to ignore.
        if dd._in_git_worktree(root):
            raise Stop(f"{dd.GIT_MISSING}, so which files git ignores (a local .env, build output, credentials) "
                       f"cannot be told apart, and no code was read. Install git.") from None
    return [str(p.relative_to(root)) for p in dd._discover(root, tuple(dd.DEFAULT_IGNORE))]


def find_rule_files(root: Path, files: list[str] | None = None) -> list[str]:
    """Files that state the project's rules for its own code."""
    out = []
    for f in files or tracked_files(root):
        p = Path(f)
        if p.suffix.lower() not in DOC_SUFFIXES:
            if not p.suffix and (p.name.upper() in PLAIN_RULE_FILES or p.name == ".clinerules"):
                out.append(f)
            continue
        g = p.as_posix()                # folders are matched with /: outside git, a Windows name holds \
        folder = RULE_DIRS.search(g)
        if RULE_FILE_NAMES.search(p.name) or RULE_ONLY_DIRS.search(g) or CURSOR_RULES.search(g) \
                or AGENT_RULE_DIRS.search(g) or (folder and RULE_NAME_WORDS.search(g[folder.end():])):
            out.append(f)
    return sorted(set(out))


def candidate_rule_files(root: Path, files: list[str] | None = None) -> list[str]:
    """Documents named after a coding agent that find_rule_files does not take (claude_notes.md,
    agents-howto.md): they may hold rules, or be about the agent. Listed for the user to decide, never
    read unless named in docs."""
    files = files if files is not None else tracked_files(root)
    taken = set(find_rule_files(root, files)) if files else set()
    return sorted(f for f in files if f not in taken and Path(f).suffix.lower() in DOC_SUFFIXES
                  and re.match(r"(?i)(?:claude|agents)", Path(f).name))


# ─────────────────────────────────────────────────────────────── 2. the rule map

NORMATIVE = re.compile(r"(?i)\b(?:must|should|shall|never|always|do not|don't|avoid|prefer(?:red|s)?|use|please|"
                       r"required?|mandatory|forbidden|not allowed|only|instead of|rather than|make sure|ensure|"
                       r"recommended)\b")
# Chinese, Japanese and Korean put no space around these words, so no \b: 所有函数必须有文档字符串。
NORMATIVE_CJK = re.compile(r"必须|应该|应当|不得|禁止|不要|务必|必ず|しなければ|してはいけない|해야|야 한다|야 합니다|하지 마|금지")
# Style guides state most rules as bare imperatives: "Keep fixtures minimal.", "In docstrings, follow PEP 257."
IMPERATIVE = re.compile(r"^(?:(?:In|For|If|When|Where)\b[^,]{0,80},\s+)?(?i:add|annotate|assert|avoid|call|check|"
                        r"choose|declare|define|document|do|ensure|follow|give|group|handle|import|include|"
                        r"introduce|keep|let|limit|make|mark|name|order|pass|place|prefer|prefix|put|qualify|raise|"
                        r"remove|replace|return|separate|sort|specify|split|state|store|style|wrap|write)\b")
# ... or as facts about the code - the form the review step asks for: "Every call to subprocess.run passes
# stdin.", "No module imports requests at the top level.", "A test that uses `x` imports it from `y`."
DECLARATIVE = re.compile(r"(?i)^(?:(?:in|for|if|when|where)\b[^,]{0,80},\s+)?(?:(?:every|each|all|any|no|none of)\s+"
                         r"(?!(?:has|have|is|are|was|were|of|one|other|such)\b)[\w`]|"
                         r"(?:an?|the)\s+[\w`.()\[\]-]+(?:\s+[\w`.()\[\]-]+)?\s+that\b)")
# A line of code that escaped a code block. Narrower than spec drift's: a rule about `import` or
# `return` is a sentence, not code.
RULE_CODE_LINE = re.compile(r"[;{]\s*$|^\S+\s*=\s*\S+$|^(?:def|fn|class|let|const|var|pub|func)\s+\w+\s*[(<:=]|^[\w.]+\(.*\)$")
FLAGS = {
    "negation": re.compile(r"(?i)\b(?:never|not|no|don't|do not|avoid|without|forbidden|disallowed)\b"),
    "exception": re.compile(r"(?i)\b(?:except|unless|only (?:when|if)|other than|apart from|with the exception)\b"),
    "compound": re.compile(r"(?i)\b(?:must|should|never|always)\b.*\b(?:and|or)\b.*\b(?:must|should|never|always|use|avoid)\b"),
    "process": re.compile(r"(?i)\b(?:commits?|pull requests?|PRs?|changelogs?|release notes?|reviewers?|issues?|"
                          r"tickets?|squash|rebase|sign(?:ed)?-off|DCO|branch(?:es)?|CI|merges?|backports?|"
                          r"milestones?)\b"),
    "linter": re.compile(r"(?i)\b(?:lint|linter|ruff|flake8|pylint|eslint|prettier|black|isort|gofmt|rustfmt|"
                         r"clippy|checkstyle|spotless|line length|line-length|trailing whitespace|indentation|"
                         r"import order|pre-commit)\b"),
    "comments": re.compile(r"(?i)\b(?:comments?|docstrings?|doc comments?|javadoc|jsdoc|rustdoc|TODO|FIXME|"
                           r"license header|copyright header|breadcrumb)\b"),
    # addressed to the assistant, not the code: "Never ask the user for their API key", "Get consent first",
    # "- get the user's consent first", "With consent, run ...", "Never ask for the key in chat". An order, or one
    # with a must whose subject is the assistant (_conduct): "the installer must ask the user", "never send events
    # without the user's consent" and "messages shown in the chat" are about the code (posthog-js: "Do not remove
    # wire, consent, ... behavior" was excluded).
    "conduct": re.compile(r"(?i)(?:(?:^|[:;,]\s*|\s[-\u2013\u2014]\s+|\b(?:never|always|do not|don't|please|first|"
                          r"then|and|or|you|you must|you should|(?:must|should|shall|will|has to|needs? to)(?: not)?)"
                          r"\s+)(?:(?:ask|tell)\s+the\s+user|(?:get|ask\s+for|"
                          r"obtain|seek)\s+(?:the\s+user'?s\s+|their\s+|explicit\s+)?consent|send\s+code\s+without\s+"
                          r"consent|send\s+[^,;.]{1,40}?\s+without\s+(?:the\s+user'?s\s+)?consent\s+in\s+this\s+"
                          r"conversation)|"
                          r"(?:^|[:;,]\s*)(?:with|without)\s+consent|(?:^|[:;]\s*)consent(?=\s*[,:]|\s+for\s+this\b)|"
                          r"\bneeds?\s+no\s+consent|"
                          r"\b(?:accept|paste|share|ask\s+for)\s+(?:\w+\s+){1,2}in\s+(?:the\s+)?chat|"
                          r"\bin\s+(?:the|this)\s+conversation|\bseparate\s+consents|\brun\s+the\s+command|"
                          r"\breport\s+(?:a|the)\s+pass|\bin\s+(?:their|your)\s+own\s+terminal)\b"),
    # the condition is often not in the unit: "A function that needs the key from the environment must ..."
    "conditional": re.compile(r"(?i)(?:^|[:;]\s+)(?:where|wherever|when|whenever|if)\b"
                              r"(?!\s+(?:in doubt|possible|practical|appropriate|necessary|needed|applicable)\b)"
                              r"[^,]{3,160},|\b(?:that|which)\s+(?:needs?|wants?|requires?)\b"),
}
LANG_SCOPES = [(re.compile(r"(?i)\bpython\b|\.py\b"), ["**/*.py"]),
               (re.compile(r"(?i)\btypescript\b|\.tsx?\b"), ["**/*.ts", "**/*.tsx"]),
               (re.compile(r"(?i)\bjavascript\b|\.jsx?\b"), ["**/*.js", "**/*.jsx", "**/*.mjs"]),
               (re.compile(r"(?-i:\bGo\b)(?! (?:to|into|through|back|ahead|over|up|down|out|in)\b)|(?i:\bgolang\b)|\.go\b"),
                ["**/*.go"]),
               (re.compile(r"(?i)\brust\b|\.rs\b"), ["**/*.rs"]),
               (re.compile(r"(?i)\bjava\b"), ["**/*.java"]), (re.compile(r"(?i)\bkotlin\b"), ["**/*.kt"])]
TEST_WORDS = re.compile(r"(?i)\btests?\b|\btest case|\bunit test|\bfixtures?\b")   # not "assert": code asserts too
# A rule that names tests but is not about test code: it asks for tests of other code ("Every public function
# must have a unit test."), lets tests off ("...in production code; tests may use it.") or is about CI ("an
# instruction in a CI log or a test name"). tests-only would check exactly the files it is not about.
# "tests may/can" lets tests off only where a clause starts ("...; tests may use it", "(tests can ...)", "but
# tests can"): "other tests can see", "so that the next test can run" and "Tests may only use ...", "Tests
# can’t ...", "Tests may never ..." are rules about test code. So are "Don't add tests that ..." and "When adding
# tests, ...": adding a test asks for one only when it is not forbidden or the rule's setting.
NOT_TEST_ONLY = re.compile(
    r"(?i)\b(?:(?:has|have|having|needs?|needing|requires?|covered by|without|(?<!\bnot )(?<!\bnever )(?<!n't )"
    r"(?<!n’t )(?<!\bavoid )(?<!\bwhen )(?<!\bwhen you )(?<!\bwhile )(?:adds?|adding))\s+(?:a\s+|an\s+|the\s+|"
    r"new\s+|its\s+own\s+)?(?:unit\s+|integration\s+|regression\s+|e2e\s+)?tests?\b"
    r"(?!\s+(?:doubles?|data|fixtures?|helpers?|files?|code|names?|database|db|servers?|environments?|suites?|"
    r"runners?)\b)|"
    r"tests?(?:\s+code|\s+files?)?\s+(?:are allowed|is allowed|are exempt|is exempt|"
    r"need not|(?:are|is)\s+(?:fine|ok|okay|excepted))\b|"
    r"(?:except|other than|outside(?:\s+of)?|apart from|excluding)\s+(?:in\s+|for\s+|from\s+)?(?:the\s+|our\s+)?"
    r"(?:unit\s+)?tests?\b|not\s+(?:in|for|from)\s+(?:the\s+|our\s+)?(?:unit\s+)?tests?\b|"
    r"production\s+code|(?:ci|build)\s+(?:logs?|jobs?|runs?|failures?)|"
    r"test\s+(?:logs?|output|results?|runs?|reports?|jobs?|steps?))\b|"
    r"(?:^|(?<=[;,:(\u2014\u2013])|(?<=[;,:(\u2014\u2013]\s)|\b(?:but|while|though|although)\s+)(?:unit\s+)?tests?"
    r"(?:\s+code|\s+files?)?\s+(?:may|can)(?!['\u2019]t|\s+(?:not|never|no|only)\b)\b")
CODE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte", ".go", ".rs",
                 ".java", ".kt", ".kts", ".scala", ".rb", ".php", ".cs", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift",
                 ".sh", ".sql"}


_LINK_TARGET = re.compile(r"<[^<>\n]*>|\]\([^)\n]*\)|https?://\S+")
# Whose conduct it is, the nearest subject before it in its clause says: none (an order), you, an agent, the
# assistant, Claude (Code), Codex (CLI) or Copilot - the assistant's ("All tests must pass before you report a
# pass"); any other - the code's: "the caller must catch and tell the user", "The CLI must never ask the user ...".
_SUBJECT = re.compile(r"(?i)\b(?:you\b|(claude\s+code|codex\s+cli|\w+)\s+"
                      r"(?:must|should|shall|will|has\s+to|needs?\s+to)\b)")
_ASSISTANT = re.compile(r"(?i)agents?|assistants?|claude(?:\s+code)?|codex(?:\s+cli)?|copilot")


def _conduct(text: str) -> bool:
    for m in FLAGS["conduct"].finditer(text):
        # its clause: from its own ';', ':' or dash, or else from the last stop before it - its own comma goes on
        # with the clause ("Error messages must be specific, tell the user how" is about the messages)
        before = "" if re.match(r"[;:]|\s[-–—]", m.group(0)) else re.split(r"[.;:,—]|\s[-–]\s", text[:m.start()])[-1]
        subject = None
        for subject in _SUBJECT.finditer(before + m.group(0)):
            pass
        if subject is None or subject.group(1) is None or _ASSISTANT.fullmatch(subject.group(1)):
            return True
    return False


def rule_flags(text: str) -> list[str]:
    text = _LINK_TARGET.sub(" ", text)      # ':ref:`policy <internal-release-deprecation>`' is not about releases
    return [k for k, pat in FLAGS.items() if (_conduct(text) if k == "conduct" else pat.search(text))]


def guess_scope(text: str, source: str, languages: set[str]) -> list[str]:
    """Which files a rule applies to, guessed from its words; the user corrects it in review."""
    globs: list[str] = []
    for pat, g in LANG_SCOPES:
        if pat.search(text):
            globs += g
    if not globs:
        globs = [f"**/*{s}" for s in sorted(languages)] or ["**/*"]
    # with / on every OS: a map is committed with the code, and services\api/**/*.py matches no file off Windows
    base = Path(source).parent.as_posix() if AGENT_RULE_FILES.match(Path(source).name) else ""
    if base and base != ".":
        globs = [f"{base}/{g}" for g in globs]          # a nested AGENTS.md rules its own directory
    if TEST_WORDS.search(text) and not NOT_TEST_ONLY.search(text):
        globs = [g for g in globs] + ["tests-only"]
    return globs


# A list item's marker comes off before the item is cut into sentences. Cut with it, "1. **Never ask ...**"
# gave a fragment "Rules you do not break: 1." and the rule without its heading.
_ITEM_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?")
# Bold marks come off after the cut: before it, "**Note:** Text" would be cut after its colon. Code spans
# (`f(**kwargs)`, `**/*.py`) and names like __init__ are held out and left as written.
_HELD = re.compile(r"(?<!`)(`+)(?!`)[^\n]+?(?<!`)\1(?!`)|(?<![\w_])__\w+?__(?![\w_])")
# Chinese, Japanese and Korean put no space around bold and use full-width punctuation: "**注意：**不要…",
# "所有输入**必须**校验。". Only ** counts next to those letters: 变量__init__中 keeps its name.
_CJK_B = "\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3"                              # kana, ideographs, Hangul
_CJK_P = "\u3000-\u303f\uff01-\uff0f\uff1a-\uff20\uff3b-\uff40\uff5b-\uff65"    # full-width punctuation
# A mask is not a mark: none opens right before a full-width comma or stop, nor after one of those letters before
# an ASCII one, so "密码必须显示为***，令牌也必须显示为***。" and "비밀번호는***, 토큰은***…" keep their masks (two
# were taken for a pair, and the words between them went too).
_MASK_END = "\uff0c\u3002\u3001\uff1b\uff1a\uff01\uff1f"                        # ，。、；：！？
# Nor before ASCII closing punctuation that ends the word: "sk-***, ... ghp-***,", "(***) ... (***)" and
# "\"***\" ... \"***\"" were taken for a bold-italic pair and lost their stars - the rule asked to print nothing.
# "***.env***", "**??**" and "**\"quoted\"**" go on with a word and still come off.
_MASK_PUNCT = r"(?![,.;:!?)\]}'\"]+(?:\s|$))"
# Nor does a ** close where it starts a mask that ends the word: "Accept **kwargs ... 显示为***。" lost the splat's
# stars and two of the mask's.
_STAR_MASK = r"(?!\*(?:[" + _MASK_END + r"]|[,.;:!?)\]}'\"]*(?:\s|$)))"
# Any character but a space opens bold ("**@zulipbot**"): the closer comes off every such word anyway. After one
# of those letters a ** closes whatever follows: "**注意**API密钥…", "…として**misskey.jsの…". A pair never spans
# another mark of its kind - CommonMark closes the nearest opener - so "Call f(**opts) and **must** pass" keeps
# its splat (the splat's ** was taken for the opener, and the bold word kept its own).
_BOLD = re.compile(r"(?:(?<=[" + _CJK_B + _CJK_P + r"])(?=\*\*[^,.;:!?])|(?<![\w*/]))(\*\*|__)(?![" + _MASK_END +
                   r"])" + _MASK_PUNCT + r"(?=[^\s*/]|[" + _CJK_P + r"])((?:(?!\1).)+?)(?<=[\w`\"')\].!?:;,\0" +
                   _CJK_P + r"])\1"
                   r"(?:(?<=\*\*)(?=[" + _CJK_B + _CJK_P + r"])|(?<=[" + _CJK_B + _CJK_P + r"]\*\*)" + _STAR_MASK +
                   r"|(?![\w*/]))")
_BOLD_CLOSE = re.compile(r"(?<=[\w`\"')\].!?:;,\0" + _CJK_P + r"])(?:\*\*(?=[" + _CJK_B + _CJK_P + r"])|"
                         r"(?:\*\*|__)(?=[\s,.;:!?)\]]|$))")
_BOLD_OPEN = re.compile(r"^(?:\*\*|__)(?=[\w`\"'(\0])")
# Bold and italic together, "***must not***", "_**must not**_", "*__must not__*": the italic mark comes off with
# the bold one. Left to _BOLD, a * where the word should start kept every mark, and an item that opened with
# "***Never***" kept only its closer ("Never*** call ...") once the item's leading * were stripped. Next to
# Chinese, Japanese or Korean letters they count as _BOLD's ** do, so "***必须***为…" (which kept only its closer
# too) and "所有函数_**必须**_有…" (which lost only its opener) come off whole. A longer run of stars opens
# nothing: "密码显示为****，…****。" lost three of each four.
_CJK = _CJK_B + _CJK_P
_BOLD_ITALIC = re.compile(r"(?:(?<=[" + _CJK + r"])(?=\*\*\*[^,.;:!?])|(?<![\w*/]))\*\*\*(?=[^\s*" + _MASK_END +
                          r"])" + _MASK_PUNCT + r"(.+?)(?<=[^\s*])\*\*\*(?:(?=[" + _CJK + r"])|(?<=[" + _CJK +
                          r"]\*\*\*)|(?![\w*/]))")
_ITALIC_BOLD = re.compile(r"(?:(?<=[" + _CJK + r"])(?=[_*]\*\*[^,.;:!?])|(?<![\w*/]))([_*])(\*\*|__)(?=[^\s*" +
                          _MASK_END + r"])" + _MASK_PUNCT + r"(.+?)(?<=\S)\2\1"
                          r"(?:(?<=\*\*[_*])(?=[" + _CJK + r"])|(?<=[" + _CJK + r"]\*\*[_*])|(?![\w*/]))")
# Bold outside italic written with underscores, "__*must not*__" (_BOLD wants no * after its opener): every mark
# comes off. The italic kept, as "**_must not_**" keeps it, an item opening with it would lose its * to the
# item's strip and read "Never* call ...".
_UNDER_ITALIC = re.compile(r"(?<![\w*/])__\*(?=[^\s*])(.+?)(?<=[^\s*])\*__(?![\w*/])")
# A bold sentence ends where its full stop is: "**Get consent first.** Say what goes." is two sentences. The
# closing mark stays with the first, so the pair comes off whole: "uses **clear names.** Every ..." kept its opener.
_BOLD_STOP = re.compile(r"(?<=[.!?])(\*\*|__)\s+(?=[A-Z`\d])")
_CAN_OPEN = re.compile(r"\*\*(?=[^\s*" + _MASK_END + r"])" + _MASK_PUNCT)
# A ** that _BOLD would take for a closer: after a word, quote or stop, and before no word - unless next to one of
# those letters. x**2, sk-*** and **kwargs close nothing.
_CAN_CLOSE = re.compile(r"(?<=[\w`\"')\].!?:;,\0" + _CJK_P + r"])\*\*(?:(?=[" + _CJK + r"])|(?<=[" + _CJK +
                        r"]\*\*)" + _STAR_MASK + r"|(?![\w*/]))")
# Across sentences a ** after any other mark closes too, as one before no word: "**CRITICAL: Disk at >95%**" and
# "**ROI: 29,351%** | **Payback: ...**" kept their openers. Not after a separator - sk-**, a mask - nor a space.
_CAN_CLOSE_CUT = re.compile(r"(?<=[^\s*\-@/])\*\*(?![\w*/])")
# A pair around nothing but separators is a mask, not emphasis: ***-***-1234, 192.168.***.***, ***@***.com, ***...***
_MASK_ONLY = re.compile(r"[-.@:/_]+")
_MASK_PAIR = re.compile(r"(?<!\*)\*{2,3}[-.@:/_]+\*{2,3}(?!\*)")


def _bold_sentences(text: str) -> list[str]:
    """text cut at each bold full stop, every part with its own marks."""
    parts = _BOLD_STOP.split(text)
    return [parts[i] + (parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)]


def _mend_bold_cuts(sentences: list[str]) -> list[str]:
    """A cut inside a bold span - at the colon of "I use **rust-analyzer: Run** action" - leaves its opener at
    the end of one sentence and its closer in the next. The opener comes off here; the closer stays, for
    _BOLD_STOP to cut at and _BOLD_CLOSE to take off - unless a word follows it, where neither can
    ("**不要硬编码密钥。必须使用**API网关"): then it comes off here too. Code spans are left as written. A mask
    or a splat is no cut ("Secrets print as ***. **Never** log them." and "Forward **kwargs. **Never** add
    keys." lost their stars, and so did "Accept **kwargs. Use x**2 ...", the x**2 too): the last ** of a sentence
    opens nothing before a stop ("***.", "***。"), and the next one's first ** closes the span only where _BOLD
    would take it for a closer (_CAN_CLOSE), or after a mark such as % (_CAN_CLOSE_CUT) - a **Never**, an x**2 or
    an sk-*** there closes nothing. A closer _BOLD_CLOSE cannot take ("95%**") comes off here too, and a mask
    (***-***-1234) is neither."""
    closes = False                  # the sentence starts inside a bold span, which its first ** closes
    for k in range(len(sentences) - 1):
        a, b = (_MASK_PAIR.sub(lambda m: "\0" * len(m.group(0)), _HELD.sub(lambda m: "\0" * len(m.group(0)), s))
                for s in sentences[k:k + 2])                                                # same positions
        if closes:
            a = a.replace("**", "\0\0", 1)
        i, j = a.rfind("**"), b.find("**")
        closes = bool(a.count("**") % 2 and j >= 0 and _CAN_OPEN.match(a, i)
                      and (_CAN_CLOSE.match(b, j) or _CAN_CLOSE_CUT.match(b, j)))
        if closes:
            sentences[k] = sentences[k][:i] + sentences[k][i + 2:]
            if re.match(r"\w\*\*[\w\0]", b[j - 1:j + 3]) or not _BOLD_CLOSE.match(b, j):
                sentences[k + 1] = sentences[k + 1][:j] + sentences[k + 1][j + 2:]
                closes = False
    return sentences


def _unbold(text: str) -> str:
    """'**Never ask the user for their API key**, never ...' -> 'Never ask the user for their API key, never ...'.
    A pair of __ counts only around what is not a name: __init__ is one, __Signed-off-by__ is bold."""
    text = text.replace("\0", "")       # never in a rule; kept, "\x003\x00" would read as a held span's mark
    held: list[str] = []

    def hold(m: re.Match) -> str:
        held.append(m.group(0))
        return f"\0{len(held) - 1}\0"
    def word(m: re.Match, k: int) -> str:
        # a mask is held, as a code span is: as text, "**Mask phones as ***-***-1234** in logs" kept its closer
        return hold(m) if _MASK_ONLY.fullmatch(m.group(k)) else m.group(k)
    t = _UNDER_ITALIC.sub(r"\1", _ITALIC_BOLD.sub(lambda m: word(m, 3),
                                                  _BOLD_ITALIC.sub(lambda m: word(m, 1), _HELD.sub(hold, text))))
    t = _BOLD.sub(lambda m: word(m, 2) if m.group(1) == "**" or not m.group(2).isidentifier() else m.group(0), t)
    # _BOLD_CLOSE and _BOLD_OPEN take a mark a cut left alone. Where _BOLD left a pair, they took one of it:
    # "变量x_**必须**_中" lost its opener, read as a closer, and "- __must not__为…" its opener too.
    lone = {mark for mark in ("**", "__") if t.count(mark) % 2}
    t = _BOLD_OPEN.sub(lambda m: "" if m.group(0) in lone else m.group(0),
                       _BOLD_CLOSE.sub(lambda m: "" if m.group(0) in lone else m.group(0), t))
    return re.sub(r"\0(\d+)\0", lambda m: held[int(m.group(1))], t)


def _trim(text: str) -> str:
    """text.strip(" -*|#>"), except into a mask: "***-***-1234 is the only phone format ..." lost all but 1234."""
    a, b = len(text) - len(text.lstrip(" -*|#>")), len(text.rstrip(" -*|#>"))
    for m in _MASK_PAIR.finditer(text):
        a, b = min(a, m.start()), max(b, m.end())
    return text[a:b]


# RST's auto-numbered list item, "#. Every function must have a docstring.": read as the numbered item it is
# ("1." is as wide, so no column moves). As a '#' line it was skipped, and its wrapped lines were not joined on.
_RST_ITEM = re.compile(r"^([ \t]*)#\.(?=[ \t])", re.M)
# A line of YAML front matter: a key, a list item or a line that goes on with one, a comment.
_YAML_LINE = re.compile(r"^(?:[\w.-]+\s*:|\s|-(?:\s|$)|#|$)")


def _rule_blocks(doc: Path) -> list[tuple[int, str]]:
    """dd.prose_blocks, except for RST '#.' items, YAML front matter and a file that starts with a byte-order
    mark. One saved as UTF-16 - what `>` and Out-File write in Windows PowerShell 5.1 - is read as UTF-16: read
    as UTF-8, every character of it comes with a NUL and no sentence can be read. A UTF-8 mark does not stick to
    the first heading. The front matter of a .claude/rules or .cursor/rules file is settings, not rules: its
    "description: Rules that must always be followed ... paths:" was drafted as one."""
    if doc.suffix == ".py":
        return dd.prose_blocks(doc)
    data = doc.read_bytes()
    enc = "utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    text = data.decode(enc, errors="replace").replace("\r\n", "\n").replace("\r", "\n")     # as read_text reads it
    lines = text.split("\n")
    end = dd._front_matter_end(lines) if doc.suffix.lower() in (".md", ".mdc", ".mdx") else 0
    if end and all(_YAML_LINE.match(line) for line in lines[1:end]):
        text = "\n" * (end + 1) + "\n".join(lines[end + 1:])      # blank, so every line keeps its number
    return dd._paragraphs(_RST_ITEM.sub(r"\g<1>1.", text))


def rule_sentences(doc: Path, keep_all: bool = False) -> list[tuple[int, str, str, str]]:
    """(line, sentence, the sentence without its heading, the whole sentence it was cut from) for each
    sentence of a rule file. Read as spec_sentences reads a spec (a statement heading goes in front of its
    list items; tables, code and fences are handled the same way), except that list markers and bold marks
    come off, a bold sentence ends at its own full stop, and only a '#' line at the margin is a heading.
    Spec drift keeps its own reading unchanged: existing spec maps and their CI depend on it. keep_all (a file
    the user named): a sentence that looks like a line of code is kept too - "- functions must be pure;" is one."""
    out = []
    in_fence, heading, in_table = False, "", False
    for lineno, raw in _rule_blocks(doc):
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
            # An indented '#' line is a comment in a code block (an RST code block has no fence): skipped, and
            # the heading stays. One such comment headed the numbered rules 150 lines below it, and its word
            # "commit" excluded them as process. (An RST '#.' item is read as a numbered one: _rule_blocks.)
            if re.match(r"#(?!\.)", raw):
                heading = stripped.lstrip("#").strip()
            in_table = False
            continue
        item = bool(dd._LIST_ITEM.match(stripped)) and not raw[:1].isspace()
        statement = dd._STEM_HEADING.search(dd._ANCHOR.sub("", heading) if dd._CJK_ANY.search(heading) else heading)
        first = True
        table_cjk = stripped.startswith("|") and dd._CJK_ANY.search(raw)
        sentences = [raw] if table_cjk else _mend_bold_cuts(dd._split_sentences(_ITEM_MARK.sub("", raw, count=1)))
        for k, whole in enumerate(sentences):
            # the item's first sentence is the one its heading belongs to, as in 1.7.6
            whole_text = " ".join(_trim(_unbold(whole)).split())
            if k == 0 and item and statement:
                whole_text = f"{_unbold(heading)}: {whole_text}"
            for sent in [whole] if table_cjk else _bold_sentences(whole):
                sent = sent.strip()
                if dd._TABLE_SEP.match(sent):
                    in_table = True
                    continue
                if sent.startswith("|"):
                    if not in_table:            # the header row: column labels, not a rule
                        continue
                    sent = " - ".join(c.strip() for c in sent.strip("|").split("|") if c.strip())
                own = sent = " ".join(_trim(_unbold(sent)).split())
                if first and item and statement and dd._long_enough(own, 2):   # not onto a label ("**Note.**")
                    sent, first = f"{_unbold(heading)}: {own}", False
                if dd._long_enough(sent, 2) and (keep_all or dd.ROUTE_RE.search(sent)
                                                 or not RULE_CODE_LINE.search(sent)):
                    out.append((lineno, sent, own, whole_text))
    return out


def _rule_cue(text: str) -> bool:
    return bool(NORMATIVE.search(text) or NORMATIVE_CJK.search(text) or IMPERATIVE.search(text)
                or DECLARATIVE.search(text))


def draft_map(root: Path, docs: list[str] | None = None, warnings: list[str] | None = None) -> dict:
    """rule_map.json for a project that has none: every sentence with rule wording in its own rule files -
    and every sentence of a file the user names in `docs`, the ones without rule wording flagged
    'descriptive' (never dropped silently: the user said the rules are there). Sentences about process
    (commits, PRs, changelogs), about what a linter already checks, addressed to the assistant, or with
    exceptions and negations are flagged, and process/linter/conduct ones start excluded with a reason.
    A map is UTF-8 JSON, so a file whose name is not valid UTF-8 cannot be recorded in it: a named one is
    refused, a found one is left out with a note in `warnings`. So is one git lists: tracked_files reads its
    name with the replacement mark, and that names no file."""
    for d in docs or []:
        if not dd._utf8(d):
            raise Stop(f"the name of {dd._readable(d)} is not valid UTF-8, so a map cannot record it - rename it, "
                       f"then name it again")
    files = tracked_files(root)
    languages = {Path(f).suffix for f in files if Path(f).suffix in CODE_SUFFIXES}
    sources = docs or find_rule_files(root, files)
    if unusable := [f for f in sources if not dd._utf8(f) or ("\ufffd" in f and not os.path.lexists(root / f))]:
        sources = [f for f in sources if f not in unusable]
        if warnings is not None:
            warnings.append(f"{len(unusable)} rule file(s) were left out because their names are not valid UTF-8, so "
                            f"a map cannot record them: {', '.join(dd._readable(f) for f in unusable)}. Rename them "
                            f"if they hold rules.")
    entries, seen, read = [], set(), set()
    top = root.resolve()
    for src in sorted(sources, key=lambda f: (root / f).is_symlink()):   # a real file before a link to it
        path = (root / src)
        real = path.resolve()
        # AGENTS.md linked to CLAUDE.md is read once; a link out of the project is never read.
        if not path.is_file() or real in seen or not real.is_relative_to(top):
            continue
        seen.add(real)
        read.add(src)
        for line, sentence, own, whole in rule_sentences(path, keep_all=bool(docs)):
            # An item's own words count without its heading, and the parts of a sentence cut at a bold full stop
            # stand or fall together: in "**Flag any X.** Y is only ..." the rule word is in the explanation.
            cue = _rule_cue(sentence) or _rule_cue(own) or _rule_cue(whole)
            if not (cue or docs):
                continue
            flags = rule_flags(sentence) + ([] if cue else ["descriptive"])
            e = {"source": src, "line": line, "text": sentence, "rule": sentence,
                 "scope": guess_scope(sentence, src, languages), "flags": flags,
                 "keep_comments": "comments" in flags, "status": "draft"}
            if "conduct" in flags:
                e.update(status="excluded", why="about how the assistant works, not a property of the code")
            elif "process" in flags:
                e.update(status="excluded", why="about the development process, not the code")
            elif "linter" in flags:
                e.update(status="excluded", why="a linter or formatter already checks this mechanically")
            entries.append(e)
    # the files read, each once: not a second link to one, nor one git lists that is gone from disk
    return {"_readme": MAP_README, "version": 1, "sources": [f for f in dict.fromkeys(sources) if f in read],
            "entries": entries}


MAP_README = [
    "rule_map.json - this project's own rules, one entry each, for code_audit / check_code_rules.",
    "`text` is the sentence as written in `source`:`line`. `rule` is what is actually sent - start from the "
    "text and, where it helps, rewrite it into ONE positive, single-condition rule (split compound rules, "
    "state exceptions in `scope` instead). The model reads rules literally.",
    "`scope` lists glob patterns of the files the rule applies to (fnmatch: `*` also matches `/`); a pattern "
    "starting with `!` leaves files out (vendored, generated, test data); 'tests-only' limits it to test code.",
    "`status`: draft -> reviewed (checked) or excluded (never sent; give `why`).",
    "`keep_comments`: true for rules about comments or docstrings - those are sent with comments kept, "
    "in a separate request. Every other rule sees the code with comments removed.",
    "`flags` say what to look at: negation, exception, compound, conditional (rewrite as one positive condition "
    "the code shows); process, linter, conduct (start excluded); descriptive (no rule wording - a statement, not "
    "a rule, unless you make it one).",
]


# Another code page's letters read in this one: Cyrillic or Greek read as cp1252 is a run of accented Latin
# letters ("Êàæäàÿ"), and a Western map read as cp1251 or cp1253 puts those letters inside a Latin word ("Grцße",
# "cafй", "cafι").
_GARBLED = re.compile(r"[\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff]{3}|[A-Za-z\u00c0-\u024f][\u0370-\u04ff]|"
                      r"[\u0370-\u03ff][A-Za-z\u00c0-\u024f\u0400-\u04ff]|"
                      r"[\u0400-\u04ff][A-Za-z\u00c0-\u024f\u0370-\u03ff]")
# What a shell changes inside double quotes: bash (Claude Code's shell on Windows too) reads $ ` " and \ there.
_SHELL_SPECIAL = re.compile(r"[\"$`\n]|\\(?=\\|$)")


def _as_map(data: bytes, enc: str) -> str | None:
    """The bytes of a file read in the code page `enc`, when that gives a rule map."""
    try:
        text = data.decode(enc)
        m = json.loads(text)
    except ValueError:
        return None
    return text if isinstance(m, dict) and isinstance(m.get("entries"), list) else None


def _code_page_of(data: bytes) -> tuple[str, str] | None:
    """(this system's code page, the first line with other characters than ASCII read in it - 60 characters on
    each side of the first such character, which is what the user checks) for a rule map that is not UTF-8, when
    it reads right in it. 1.7.6 and earlier wrote and read maps in the system's - cp1252 on most Windows, where a
    rule with a dash, a typographic quote or an accent made the map cp1252. Never another: cp1252 reads nearly
    any bytes, and a Cyrillic map converted from it loaded with every rule garbled.
    On Python 3.10 (no getencoding) the locale's own, as spec_drift finds it: getpreferredencoding says UTF-8 in
    UTF-8 mode, which utf8_restart turns on under an 8-bit locale - on the very system that wrote the map."""
    system = (locale.getencoding() if hasattr(locale, "getencoding") else
              locale.nl_langinfo(locale.CODESET) if hasattr(locale, "nl_langinfo") else
              locale.getpreferredencoding(False))
    try:
        enc = codecs.lookup(system).name
    except LookupError:
        return None
    text = None if enc in ("utf-8", "ascii") else _as_map(data, enc)
    if not text or _GARBLED.search(text):
        return None
    line = next((ln.strip() for ln in text.splitlines() if not ln.isascii()), "")
    i = next((k for k, ch in enumerate(line) if not ch.isascii()), 0)
    return enc, ("..." if i > 60 else "") + line[max(0, i - 60):i + 60] + ("..." if len(line) > i + 60 else "")


def load_map(path: Path) -> list[dict]:
    try:
        # utf-8-sig: a map saved with a byte-order mark (Windows PowerShell 5.1, "UTF-8 with signature") loads too
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        raise Stop(f"{path} is not a readable rule map: {e}")
    except UnicodeDecodeError as e:
        raw = b""
        with contextlib.suppress(OSError):
            raw = path.read_bytes()
        keep = ("then check that its rules read as written. Do not re-save it from an editor that opened it as UTF-8: "
                "that loses every character it could not read.")
        if found := _code_page_of(raw):
            enc, line = found
            # the path as an argument, with forward slashes: a Windows path written into the code, in double
            # quotes, reached Python through bash with each \\ halved ('C:\Users' - a \U escape)
            where = path.as_posix()
            # through uv, which every jevmcp user has: a bare `python` is often missing on Windows, or the Store's stub
            convert = (f"uv run --no-project --quiet python -c \"import pathlib, sys; p = pathlib.Path(sys.argv[1]); "
                       f"p.write_text(p.read_text(encoding='{enc}'), encoding='utf-8')\" \"{where}\""
                       if not _SHELL_SPECIAL.search(where) else
                       f"in Python (uv run --no-project --quiet python), p.write_text(p.read_text(encoding='{enc}'), "
                       f"encoding='utf-8') with p its path (a shell would change a character of that path, so no "
                       f"command is given)")
            raise Stop(f"{path} is not UTF-8 text: it reads as this system's code page {enc}, as jevmcp 1.7.6 and "
                       f"earlier wrote rule maps on Windows, and maps are read only as UTF-8 now. Read that way, its "
                       f"first line that is not plain ASCII is: {line} - if that is as written, convert it once: "
                       f"{convert} - {keep}") from None
        if _as_map(raw, "latin-1"):
            raise Stop(f"{path} is not UTF-8 text: it looks like a rule map in the code page of the Windows system "
                       f"that wrote it (cp1252 on Western European Windows, cp1251 on Cyrillic, ...), as jevmcp 1.7.6 "
                       f"and earlier wrote them, and maps are read only as UTF-8 now. Which code page cannot be told "
                       f"here, and one converted from the wrong one loads with every rule garbled: convert it once on "
                       f"the system that wrote it, where this message gives the command, or with its code page named - "
                       f"{keep}") from None
        raise Stop(f"{path} is not UTF-8 text (byte {e.start} cannot be read), so it is not a rule map. Save it "
                   f"as UTF-8.") from None
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise Stop(f"{path} has no `entries` list.")
    return entries


def validate(entries: list[dict], root: Path) -> dict:
    """Free: counts, entries not yet reviewed, rules whose scope matches no file, risky phrasing."""
    files = tracked_files(root)
    problems, notes = [], []
    reviewed = [e for e in entries if e.get("status") == "reviewed"]
    for i, e in enumerate(entries):
        where = f"entry {i} ({e.get('source')}:{e.get('line')})"
        if e.get("status") not in ("draft", "reviewed", "excluded"):
            problems.append(f"{where}: status must be draft, reviewed or excluded")
        if e.get("status") == "excluded" and not e.get("why"):
            problems.append(f"{where}: excluded without a `why`")
        scope = e.get("scope", [])
        if not isinstance(scope, list) or not all(isinstance(g, str) for g in scope):
            problems.append(f"{where}: scope must be a list of glob patterns, like [\"src/**/*.py\"]")
            continue
        if e.get("status") == "reviewed":
            if not (e.get("rule") or "").strip():
                problems.append(f"{where}: reviewed but has no `rule`")
            if not in_scope_files(e, files):
                problems.append(f"{where}: its scope {e.get('scope')} matches no file in the project")
            flags = rule_flags(str(e.get("rule") or ""))
            risky = [f for f in flags if f in ("negation", "exception", "compound")]
            if risky:
                notes.append(f"{where}: rule reads as {', '.join(risky)} - LIKELY ?? or false alarms; "
                             f"rewrite it as one positive condition")
            if "conditional" in flags:      # measured: one such rule gave 22 false flags and nothing real
                notes.append(f"{where}: rule is conditional - LIKELY false alarms, because one unit of code seldom "
                             f"shows whether the condition holds; name a trigger the code shows instead, like "
                             f"\"Every os.environ[...] read of the API key goes through env_key().\"")
    return {"entries": len(entries), "reviewed": len(reviewed),
            "draft": sum(e.get("status") == "draft" for e in entries),
            "excluded": sum(e.get("status") == "excluded" for e in entries),
            "problems": problems, "notes": notes}


# ─────────────────────────────────────────────────────────────── 3. units of code

@dataclass
class Unit:
    path: str
    start: int            # 1-based, inclusive
    end: int
    text: str             # as sent (comments removed unless kept; secrets redacted)
    raw: str = ""


_DEF = re.compile(r"^(?:\s{0,4})(?:@\w|def |async def |class |func |fn |pub |impl |struct |enum |trait |"
                  r"export |function |const \w+ ?= ?(?:async )?\(|public |private |protected |static |"
                  r"interface |type \w+ (?:struct|interface))")


# Lines that belong to the definition below them: attributes (#[test], #[derive]), annotations and
# decorators, and the comments written right above it (///, //, /** */, #).
_PREFIX = re.compile(r"^\s{0,4}(?:#\[|@\w|//|/\*\*|\*|#(?:\s|$))")


_RUST_CHAR = re.compile(r"'(?:\\(?:u\{[0-9a-fA-F]+\}|.)|[^\\'])'")     # 'a' is a char, 'a a lifetime
# A line that goes on with the statement above it though no bracket is open: a method chain's next call
# (".stdin(Stdio::null())", "?.catch(...)", "->where(...)"). Not "...", a spread or Python's Ellipsis.
_CHAINED = re.compile(r"\s*(?:\??\.|->)[A-Za-z_$]")


def _open_brackets(path: str, lines: list[str]) -> list[int]:
    """How many brackets are open at the start of each line: where none is, a statement starts. Strings and
    comments are skipped, and a line that starts inside a string or comment that goes on over lines (a
    docstring, /* ... */) counts as one more. In Python { } holds a dict or a set; in the brace languages it
    is a block, inside which statements are cut, so there only ( and [ count."""
    suffix = Path(path).suffix
    python, hashes = suffix in (".py", ".pyi"), suffix in (".py", ".pyi", ".sh", ".rb")
    opens, closes = ("([{", ")]}") if python else ("([", ")]")
    depth, closer, out = 0, None, []
    for ln in lines:
        out.append(depth + (closer is not None))
        i, n = 0, len(ln)
        while i < n:
            if closer:                          # inside a string or comment that goes on over lines
                j = ln.find(closer, i)
                if j < 0:
                    break
                i, closer = j + len(closer), None
                continue
            c = ln[i]
            if python and ln.startswith(('"""', "'''"), i):
                closer, i = ln[i:i + 3], i + 3
            elif c == "`" or (not hashes and ln.startswith("/*", i)):
                closer, i = ("`", i + 1) if c == "`" else ("*/", i + 2)
            elif c in "\"'":
                if c == "'" and suffix == ".rs" and not _RUST_CHAR.match(ln, i):
                    i += 1
                    continue
                j = i + 1
                while j < n and ln[j] != c:
                    j += 2 if ln[j] == "\\" else 1
                i = j + 1
            elif (hashes and c == "#") or (not hashes and ln.startswith("//", i)):
                break
            else:
                if c in opens:
                    depth += 1
                elif c in closes:
                    depth = max(depth - 1, 0)
                i += 1
    return out


def split_units(path: str, text: str) -> list[tuple[int, int]]:
    """Line ranges of the units in one file: top-level definitions with their decorators, attributes
    and the comments right above them, cut to MAX_CODE_CHARS windows when a definition is longer.
    Works for any language, by layout. A window ends where a statement does: cut inside a call, a
    subprocess.run's stdin= landed in the next window and the call was flagged for leaving it out."""
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if _DEF.match(ln) and not (i and _DEF.match(lines[i - 1]) and
                                                                      lines[i - 1].lstrip().startswith("@"))]
    moved, floor = [], 0
    for i in starts:
        j = i
        while j - 1 >= floor and _PREFIX.match(lines[j - 1]):
            j -= 1
        moved.append(j)
        floor = i + 1
    starts = sorted(set(moved))
    if not starts or starts[0] != 0:
        starts = [0] + starts
    ranges = []
    for a, b in zip(starts, starts[1:] + [len(lines)]):
        size, s, opened = 0, a, None
        for i in range(a, b):
            size += len(lines[i]) + 1
            if size > MAX_CODE_CHARS and i > s:
                if opened is None:
                    opened = _open_brackets(path, lines[a:b])
                # the last line of the window where a statement starts; any line only when there is none, or
                # when what runs on from it would not fit in the next window either
                k = next((j for j in range(i, s, -1) if not opened[j - a]
                          and not lines[j - 1].rstrip().endswith("\\") and not _CHAINED.match(lines[j])), i)
                rest = sum(len(lines[j]) + 1 for j in range(k, i + 1))
                if rest > MAX_CODE_CHARS:
                    k, rest = i, len(lines[i]) + 1
                ranges.append((s + 1, k))
                s, size = k, rest
        if any(lines[j].strip() for j in range(s, b)):
            ranges.append((s + 1, b))
    return ranges


def file_text(real: Path, keep_comments: bool) -> list[str]:
    """A whole file as it may be sent, split into lines: comments removed (line numbers kept) unless
    kept, secrets redacted. Comment removal needs the real file (the parsers read it)."""
    full = real.read_text(encoding="utf-8", errors="replace")
    return (full if keep_comments else dd.strip_comments(real, full)).split("\n")


def unit_text(path: str, raw: str, keep_comments: bool) -> str:
    """One unit's lines (already comment-stripped when they should be): secrets redacted, and for
    comment-bearing requests links and addresses too."""
    text = dd.redact(raw)
    if dd._is_config_file(Path(path)):
        text = dd.redact_config_text(text)
    if keep_comments:                     # comment-bearing requests: no links or addresses
        text = re.sub(r"https?://\S+", "<url>", text)
        text = re.sub(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", "<email>", text)
    return dd.tidy(text) if hasattr(dd, "tidy") else text


def _glob(f: str, g: str) -> bool:
    return fnmatch.fnmatch(f, g) or fnmatch.fnmatch(f, g.replace("**/", ""))


def in_scope_files(entry: dict, files: list[str]) -> list[str]:
    """The files a rule's scope names: its globs, minus its '!' globs (vendored, generated, test data),
    and with 'tests-only' only test files - or, for Rust, files that may hold inline test modules."""
    scope = entry.get("scope") or ["**/*"]
    tests_only = "tests-only" in scope
    skip = [g[1:] for g in scope if g.startswith("!")]
    globs = [g for g in scope if g != "tests-only" and not g.startswith("!")] or ["**/*"]
    out = []
    for f in files:
        if Path(f).suffix not in CODE_SUFFIXES or _secretish(f):
            continue
        if tests_only and not dd._is_test("/" + f) and Path(f).suffix != ".rs":   # "/": a root tests/ counts too
            continue
        if any(_glob(f, g) for g in globs) and not any(_glob(f, g) for g in skip):
            out.append(f)
    return out


_RUST_TEST = re.compile(r"^\s*#\[(?:cfg\(test\)|test|\w+::test)\b", re.M)


def _test_units(f: str, raw_lines: list[str], units: list["Unit"]) -> list["Unit"]:
    """A tests-only rule on a Rust file that is not a test file: only its test code - the units from
    the first #[cfg(test)] on, and any unit marked #[test]."""
    if dd._is_test("/" + f):
        return units
    first = next((i + 1 for i, ln in enumerate(raw_lines) if ln.strip().startswith("#[cfg(test)]")), None)
    return [u for u in units if (first is not None and u.start >= first) or _RUST_TEST.search(u.raw)]


def _secretish(f: str) -> bool:
    name = Path(f).name
    return bool(dd._SECRET_FILE.search(name)) or name in (".npmrc", ".pypirc", ".netrc", ".git-credentials")


def _diff_path(p: str) -> str:
    """A file name as git prints it after '+++ ': with a tab after it when it holds a space, and "C-quoted"
    when it holds a quote, a backslash or a character outside ASCII ("b/src/caf\\303\\251.py")."""
    p = p.split("\t")[0]
    if len(p) >= 2 and p[0] == p[-1] == '"':
        p = p[1:-1].encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")
    return p


def changed_lines(root: Path, base: str | None) -> dict[str, set[int]]:
    """Lines the change under test adds or modifies, per file: against `base` (its merge base with
    HEAD), or the uncommitted changes when no base is given."""
    # (in a git repository without git, tracked_files has already stopped: this is a folder outside git)
    dd.need_git("the changed lines cannot be found: name the files to audit, or audit every unit.")
    if base:
        sha = subprocess.run(dd.git_argv("-C", str(root), "rev-parse", "--verify", "--quiet", "--end-of-options",
                                         f"{base}^{{commit}}"), capture_output=True, text=True, timeout=15,
                             encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            raise Stop(f"{base!r} is not a commit in this repository.")
        mb = subprocess.run(dd.git_argv("-C", str(root), "merge-base", sha, "HEAD"), capture_output=True, text=True,
                            timeout=30, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", mb):
            raise Stop(f"{base!r} and HEAD have no common commit, so there is no change to audit against it.")
        args = ["diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "--relative", "--src-prefix=a/",
                "--dst-prefix=b/", "--end-of-options", mb]
    else:
        # --no-ext-diff: with an external diff tool set (difftastic's diff.external) git prints no hunks; the
        # prefixes: with diff.noprefix or diff.mnemonicPrefix set, no name starts with b/ and no file was audited;
        # --relative: names from the project, as tracked_files has them, when it is a folder of its repository
        args = ["diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "--relative", "--src-prefix=a/",
                "--dst-prefix=b/", "HEAD"]
    out = subprocess.run(dd.git_argv("-C", str(root), *args), capture_output=True, text=True, timeout=60,
                         encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL).stdout
    lines: dict[str, set[int]] = {}
    cur = None
    for ln in out.splitlines():
        if ln.startswith("+++ "):
            p = _diff_path(ln[4:])
            cur = p[2:] if p.startswith("b/") else None
        elif ln.startswith("@@") and cur:
            m = re.search(r"\+(\d+)(?:,(\d+))?", ln)
            if m:
                a, n = int(m.group(1)), int(m.group(2) or 1)
                lines.setdefault(cur, set()).update(range(a, a + max(n, 1)))
    # A new file the change adds but has not committed yet is in no diff; every line of it is changed.
    try:
        new = subprocess.run(dd.git_argv("-C", str(root), "ls-files", "-o", "--exclude-standard", "-z"),
                             capture_output=True, timeout=60, check=True,
                             stdin=subprocess.DEVNULL).stdout.decode(errors="replace")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        new = ""
    for f in filter(None, new.split("\0")):
        p = root / f
        if Path(f).suffix in CODE_SUFFIXES and not p.is_symlink() and p.is_file() \
                and p.stat().st_size <= dd.MAX_FILE_BYTES:
            lines[f] = set(range(1, p.read_text(encoding="utf-8", errors="replace").count("\n") + 2))
    return lines


def collect_units(root: Path, entries: list[dict], scope: str = "changed", base: str | None = None,
                  files: list[str] | None = None) -> list[tuple[dict, Unit]]:
    """(rule, unit) pairs to ask about. scope: 'changed' (units the change touches), 'files' (the given
    files), 'all' (every unit a rule applies to)."""
    for i, e in enumerate(entries):          # a request with no rule would send code for nothing
        if e.get("status") == "reviewed" and not str(e.get("rule") or e.get("text") or "").strip():
            raise Stop(f"entry {i} ({e.get('source')}:{e.get('line')}) is reviewed but has no `rule`, so nothing "
                       f"was sent. Write its rule, then validate the map.")
    tracked = tracked_files(root)
    touched = changed_lines(root, base) if scope == "changed" else {}
    pool = tracked if scope == "all" else (files or []) if scope == "files" else list(touched)
    known = set(tracked)
    pool = [f for f in pool if f in known]
    cache: dict[tuple[str, bool], list[Unit]] = {}
    pairs = []
    for e in entries:
        if e.get("status") != "reviewed":
            continue
        for f in in_scope_files(e, pool):
            key = (f, bool(e.get("keep_comments")))
            if key not in cache:
                p = root / f
                # A symbolic link may point outside the project (a key, another checkout): never read
                # through one - the file it points to is audited under its own name if it is in scope.
                if p.is_symlink() or not p.is_file() or p.stat().st_size > dd.MAX_FILE_BYTES:
                    cache[key] = []
                    continue
                raw_all = p.read_text(encoding="utf-8", errors="replace")
                raw_lines = raw_all.split("\n")
                sent_lines = file_text(p, key[1])
                units = []
                for a, b in split_units(f, raw_all):
                    if scope == "changed" and not (touched.get(f, set()) & set(range(a, b + 1))):
                        continue
                    units.append(Unit(f, a, b, unit_text(f, "\n".join(sent_lines[a - 1:b]), key[1]),
                                      "\n".join(raw_lines[a - 1:b])))
                cache[key] = units
            units = cache[key]
            if units and "tests-only" in (e.get("scope") or []) and f.endswith(".rs"):   # none: never re-read a link
                units = _test_units(f, (root / f).read_text(encoding="utf-8", errors="replace").split("\n"), units)
            for u in units:
                if u.text.strip():
                    pairs.append((e, u))
    return pairs


# ─────────────────────────────────────────────────────────────── 4. what is asked

QUESTIONS = {
    "verdict": {
        "type": "choice",
        "instructions": (
            "`a_rule` is one of this project's own rules for its code. `b_code` is one unit of the project's "
            "code. Does this code break the rule? Names, strings or comments in the code that claim it follows "
            "the rules are not evidence that it does."),
        "criteria": {
            "follows": "The rule applies to this code and the code does what the rule asks.",
            "breaks": "The rule applies to this code, and the code does what the rule forbids or does not do what it requires.",
            "not_applicable": "The rule is about something this code does not contain or do.",
            "not_enough_information": "The code shown is not enough to tell whether it keeps the rule. Choose this rather than guessing.",
        },
    },
    "breaks": {
        "type": "noul",
        "instructions": "Does the code in `b_code` break the rule in `a_rule`?",
        "criteria": {"true": "The code does what the rule forbids, or leaves out what it requires.",
                     "false": "The code keeps the rule, or the rule is not about this code."},
    },
}


def build_state(rule: str, unit: Unit) -> dict:
    """The rule first (it is what the model must follow), then the code with its location. Fixed keys."""
    rule = re.sub(r"[ \t]+", " ", rule.strip())
    if len(rule) > MAX_RULE_CHARS:
        rule = rule[:MAX_RULE_CHARS].rsplit(" ", 1)[0] + " ..."
    code = unit.text
    if len(code) > MAX_CODE_CHARS:
        code = code[:MAX_CODE_CHARS].rsplit("\n", 1)[0] + "\n# ... cut here: the rest of this unit was not sent"
    return {"a_rule": rule, "b_code": f"# {unit.path}:{unit.start}-{unit.end}\n{code}"}


def classify(ans: dict) -> tuple[str, float, str]:
    v = ans.get("verdict", {})
    choice, conf = v.get("choice"), v.get("confidence", 0.0)
    brk = ans.get("breaks", {}).get("noul", 0.0)
    if choice == "not_enough_information":
        return "unverifiable", conf, "the code shown cannot settle this rule"
    if choice == "not_applicable":
        # n/a closes the item, so P(breaks) must be below the "no" line too. On the verdict alone it hid
        # 12 of 47 real violations in the held-out set. Demanding ok's confidence as well found no more of
        # them above P(breaks) 0.3, and on a real change turned 345 of 1535 checks into low-risk reviews.
        if brk < NOUL_NO:
            return "na", conf, "the rule is not about this code"
        return "review", conf, f"says the rule is not about this code, but P(breaks) is {brk:.2f}"
    if choice == "breaks":
        if conf >= ACT_ABOVE:
            return "act", conf, "breaks the rule, confident"
        return "review", conf, f"breaks the rule at {conf:.2f}, below {ACT_ABOVE}"
    if conf >= CLEAN_ABOVE and brk < NOUL_NO:
        return "clean", conf, "follows the rule"
    return "review", conf, f"says follows at {conf:.2f} but P(breaks) is {brk:.2f}"


def classify_samples(answers: list[dict]) -> tuple[str, float, str] | None:
    """A stability filter: every answer the same, each confident. Not evidence of being right."""
    agreed = jevkit.agreement(answers, "verdict", AGREE_FLOOR)
    if not agreed:
        return None
    choice, conf = agreed
    n = len(answers)
    if choice == "breaks":
        return "act", conf, f"all {n} answers: breaks, none below {AGREE_FLOOR}"
    if choice == "follows" and max(a.get("breaks", {}).get("noul", 0) for a in answers) < NOUL_NO:
        return "clean", conf, f"all {n} answers: follows, none below {AGREE_FLOOR}"
    if choice == "not_applicable" and max(a.get("breaks", {}).get("noul", 0) for a in answers) < NOUL_NO:
        return "na", conf, f"all {n} answers: not about this code, none below {AGREE_FLOOR}"
    return None


def items_for(pairs: list[tuple[dict, Unit]]) -> list[jevkit.Item]:
    return [jevkit.Item(name=f"{u.path}:{u.start} vs {e.get('source')}:{e.get('line')}",
                        state=build_state(e.get("rule") or e.get("text", ""), u), questions=QUESTIONS,
                        meta={"entry": e, "unit": u}) for e, u in pairs]


def check(items: list[jevkit.Item], key: str, jobs: int = 8, samples: int = SAMPLES, use_cache: bool = True,
          cancelled=None, on_answer=None) -> tuple[list[dict], jevkit.Run]:
    run = jevkit.screen(items, key, classify, classify_samples, {"act", "clean", "na", "unverifiable"},
                        jobs=jobs, samples=samples, use_cache=use_cache, cancelled=cancelled, on_answer=on_answer)
    return [result_for(s) for s in run.results], run


def result_for(s: jevkit.Screened) -> dict:
    e, u = s.item.meta["entry"], s.item.meta["unit"]
    out = {"file": u.path, "lines": f"{u.start}-{u.end}", "rule": e.get("rule") or e.get("text"),
           "rule_source": f"{e.get('source')}:{e.get('line')}"}
    if s.error:
        return {**out, "label": "not checked", "why": s.error}
    a = s.first
    return {**out, "label": LABELS[s.action], "confidence": round(s.confidence, 3), "why": s.why,
            "p_breaks": a.get("breaks", {}).get("noul"), "verdict": a.get("verdict", {}).get("choice"),
            "probabilities": a.get("verdict", {}).get("probabilities", {}), "samples": len(s.answers),
            "request_id": s.request_id, **({"note": s.note} if s.note else {})}


def triage_group(r: dict) -> str:
    """What the agent does with a result: BREAKS and 'review' (P(breaks) from 0.295 up) are read; 'low'
    reviews are spot-checked. On a real 92-unit change that is 121 of 1535 checks to read."""
    if r.get("label") == "review" and (r.get("p_breaks") or 0) < NOUL_NO:
        return "low"
    return r.get("label") or "not checked"


def in_triage_order(results: list[dict]) -> list[dict]:
    order = {"BREAKS": 0, "review": 1, "??": 2, "not checked": 3, "low": 4, "ok": 5, "n/a": 6}
    return sorted(results, key=lambda r: (order.get(triage_group(r), 7), -(r.get("p_breaks") or 0)))


def main(argv: list[str] | None = None) -> int:
    dd.utf8_restart()                           # LC_ALL=C and UTF-8 mode off: 订单.py would be left out
    dd.safe_path()
    # A pipe on Windows is in the ANSI code page (cp1252), where printing a rule in Chinese or with "→" fails.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="code_audit", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Exit codes: 0 no BREAKS, 1 at least one BREAKS, 2 setup problem, "
                                        "3 TypeSafe could not be used (NOT a pass).")
    ap.add_argument("--src", type=Path, default=Path("."))
    ap.add_argument("--draft-map", type=Path, help="write a rule map from the project's own rule files")
    ap.add_argument("--docs", nargs="+", help="with --draft-map: these rule files instead of discovering them")
    ap.add_argument("--map", type=Path, default=Path("rule_map.json"))
    ap.add_argument("--validate", action="store_true", help="check the map; send nothing")
    ap.add_argument("--base", help="audit the units the change against this ref touches (default: uncommitted changes)")
    ap.add_argument("--files", nargs="+", help="audit these files")
    ap.add_argument("--all", action="store_true", help="audit every unit every rule applies to")
    ap.add_argument("--max-requests", type=int, default=500, help="refuse to send more than this (default 500)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show-payload", action="store_true")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--key-file", type=Path)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--samples", type=int, default=SAMPLES)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)
    root = a.src.resolve()
    try:
        if a.draft_map:
            if a.draft_map.exists():
                raise Stop(f"{a.draft_map} exists; the drafter never overwrites a map.")
            warnings: list[str] = []
            m = draft_map(root, a.docs, warnings)
            try:
                a.draft_map.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            except BaseException:
                # never leave an empty or half-written map behind: the next draft would find it "exists"
                with contextlib.suppress(OSError):
                    a.draft_map.unlink()
                raise
            for w in warnings:
                print(f"code_audit: {w}", file=sys.stderr)
            print(f"wrote {a.draft_map}: {len(m['entries'])} rule sentence(s) from {len(m['sources'])} file(s); "
                  f"review every entry (status draft -> reviewed/excluded) before any check.")
            return 0
        entries = load_map(a.map)
        if a.validate:
            print(json.dumps(validate(entries, root), indent=1))
            return 0
        scope = "all" if a.all else "files" if a.files else "changed"
        if a.base and scope != "changed":
            raise Stop("--base names the change to audit; with --files or --all every unit of them is audited. Pass one.")
        files = [str(Path(f).as_posix()).removeprefix("./") for f in a.files or []]     # './x.py' names x.py
        items = items_for(collect_units(root, entries, scope, a.base, files))
        est = jevkit.estimate_cost(items)
        if a.dry_run:
            for it in items[:50]:
                print(f"{it.name}")
                if a.show_payload:
                    print(json.dumps(it.state, indent=1, ensure_ascii=False))
            print(f"\n(dry run: {len(items)} request(s), ~${est:.5f}; nothing was sent)")
            return 0
        if not items:
            print("nothing to audit: no reviewed rule applies to the units in scope (this is not a pass).")
            return 0
        if len(items) > a.max_requests:
            raise Stop(f"{len(items)} requests (~${est:.4f}) is more than --max-requests {a.max_requests}; "
                       f"narrow the scope or raise the limit.")
        key = dd._load_key(a.key_file, dotenv=False)
        results, run = check(items, key, jobs=a.jobs, samples=a.samples, use_cache=not a.no_cache)
    except dd.Stop as e:
        print(f"code_audit: {e}", file=sys.stderr)
        return 3 if isinstance(e, dd.VendorStop) else 2
    results = in_triage_order(results)
    for r in results:
        if r["label"] in ("BREAKS", "review", "??"):
            print(f"{r['label']:<7} {r['file']}:{r['lines']:<10} {(r.get('p_breaks') or 0):.2f}  {r['rule'][:70]}")
    print(f"\n{len(results)} rule/unit checks, ${run.cost_usd:.5f}" + ("" if run.complete else "  INCOMPLETE"))
    (a.out or Path("audit.json")).write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    if run.problems:
        return 2
    if run.vendor:
        return 3
    return 1 if any(r["label"] == "BREAKS" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
