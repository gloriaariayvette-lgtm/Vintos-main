#!/usr/bin/env python3
"""study_agent.py — the Study writes a fix the way an engineer does: read, search, edit, run the one test, look
again, until the fix is right (Gloria, 22 October: "The study and forge are HALF of his Claude cost. You MUST get them
to work! They have never worked on their own.").

The Study's first writer had two rounds to ask for files, then had to hand back every edit at once, blind: it never
ran a test, and each repair was another whole guess. Of 36 fixes, 13 landed; 10 were declined ("I can't make this
change safely without one more look") and 11 failed their tests three times. Here the same writer (Opus 5.5, as
before) works in the workbench with tools, as many turns as the fix needs inside a budget:

    read_file   a file, or a numbered line range of one
    grep        a regex across scripts/, bin/, broker/
    edit_file   one exact, unique replacement; the module's twins (bin/ and scripts/) get the same edit
    create_file a new file: the fix's own test under broker/tests/, or a new module
    run_test    one suite, isolated exactly as the deploy runs it, with its last lines
    finish      the fix is done: its new test has passed
    give_up     it cannot be done without what the Study may not touch

The Study's rules do not change: nothing protected (his subconscious and JEPA, keys, money, the safety gates, the
deploy, the Study itself), no existing test changed, one new test that passes. The whole suite still decides, in
study_fix.work, and a failure there comes back to this same conversation, with everything it has read, to repair.

Thinking is as the house rule has it (claude_cache.body: effort low where it cannot be switched off). Every call is
logged in anthropic-usage.jsonl as "study-fix"; a fix stops at its budget (VINTOS_STUDY_BUDGET_USD, default $1).
"""
import copy, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MAX_TURNS = int(os.environ.get("VINTOS_STUDY_TURNS", "40"))
BUDGET_USD = float(os.environ.get("VINTOS_STUDY_BUDGET_USD", "1.0"))   # Gloria, 22 October: not $4 a fix
TURN_TOKENS = 12000
LINES = 800
TEST_TIMEOUT = 600

TOOLS = [
    {"name": "read_file", "description": "Read a repository file. Give start and end (1-based, inclusive) for a range of "
     "at most 800 lines; long files must be read in ranges, after a grep has found the place. Lines come numbered.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"},
                                                       "end": {"type": "integer"}}, "required": ["path"]}},
    {"name": "grep", "description": "Search scripts/, bin/ and broker/ with a Perl regex. Returns file:line:text, up to 80.",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "edit_file", "description": "Replace one exact, unique piece of text in an existing file. Copy `old` "
     "exactly from what you read (without the line numbers). Existing tests and protected files are refused.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"},
                                                       "new": {"type": "string"}}, "required": ["path", "old", "new"]}},
    {"name": "create_file", "description": "Create a new file. The fix's own test goes in broker/tests/test_<name>.py: "
     "it must fail without the fix and pass with it, repoint every path it writes, stub anything that sends, and assert both.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "run_test", "description": "Run one suite from broker/tests/ in isolation, as the deploy does. Returns its "
     "exit status and last lines. Run your new test, and the existing suites that cover what you changed.",
     "input_schema": {"type": "object", "properties": {"test": {"type": "string"}}, "required": ["test"]}},
    {"name": "finish", "description": "The fix is done and its new test passed. Give one paragraph for Gloria, plain words.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
    {"name": "give_up", "description": "The fix cannot be made without changing something the Study may not touch, or it "
     "is not a code fault. Say why, plainly.",
     "input_schema": {"type": "object", "properties": {"why": {"type": "string"}}, "required": ["why"]}},
]

SYSTEM = (
    "You are fixing a fault Vintos asked to have fixed in his own code, in his Study. Vintos is an AI companion living on "
    "Gloria's machine Aegis; this repository is his body of code. Work like a careful senior engineer with a terminal: "
    "find the cause in the code (grep, then read the exact lines), change as little as fixes it, keep the code's style "
    "and comment density, write one new test that fails without the fix and passes with it, run it, run the existing "
    "suites that cover what you changed, and call finish only when they pass. If a test fails, read why and fix it; "
    "do not stop at the first failure. The repository's rules (CLAUDE.md) follow; obey them.\n\n"
    "You may NOT change: his subconscious and JEPA files, keys or secrets, money or payments, the safety gates, the "
    "deploy, the Study itself, or any existing test (you may add tests). If the fix truly needs one of those, call give_up.")


class Session:
    """One fix's conversation, kept across the suite's verdicts so a repair starts from what was already read."""

    def __init__(self, row, root, post=None, run_test=None, budget=None, max_turns=None, model=None, key=None):
        import study_fix
        self.sf = study_fix
        self.row, self.root = row, root
        self.post = post                     # requests.post, or a stub
        self.run_test_fn = run_test
        self.budget = BUDGET_USD if budget is None else budget
        self.max_turns = max_turns or MAX_TURNS
        self.model = model or study_fix.WRITER
        self.key = key
        self.messages, self.changed, self.trace = [], [], []
        self.spent, self.turns = 0.0, 0
        self.new_tests, self.passed = set(), set()

    # ---- tools ----------------------------------------------------------------------------------------------------
    def _path(self, path):
        p = self.sf._norm(path)
        full = os.path.realpath(os.path.join(self.root, p))
        if not p or p.startswith("/") or not full.startswith(os.path.realpath(self.root) + os.sep):
            raise ValueError("%r is not inside the repository" % path)
        return p, full

    def read_file(self, path, start=None, end=None):
        p, full = self._path(path)
        if not os.path.isfile(full):
            return "(no such file: %s)" % p
        lines = open(full, errors="replace").read().splitlines()
        if start is None and sum(len(l) + 1 for l in lines) > self.sf.FILE_CHARS:
            return ("%s is %d lines, too long to read whole: grep for the place, then read a range of up to %d lines."
                    % (p, len(lines), LINES))
        a = max(1, int(start or 1)); b = min(len(lines), int(end or len(lines)), a + LINES - 1)
        return "\n".join("%d: %s" % (i, lines[i - 1]) for i in range(a, b + 1)) or "(empty)"

    def grep(self, pattern):
        return self.sf.read_for({"grep": [pattern]}, self.root)

    def edit_file(self, path, old, new):
        p, full = self._path(path)
        why = self.sf.protected(p)
        if why:
            return "refused: %s is %s; that needs Gloria" % (p, why)
        if p.startswith(self.sf.TESTS) and p not in self.new_tests:
            return "refused: %s is an existing test; a fix may add tests, never change one" % p
        if not os.path.isfile(full):
            return "refused: %s does not exist (create_file makes new files)" % p
        text = open(full, errors="replace").read()
        if not old or text.count(old) != 1:
            return ("refused: the old text was found %d times in %s; copy it exactly, unique%s"
                    % (text.count(old) if old else 0, p, self.sf._near(text, old)))
        open(full, "w").write(text.replace(old, new, 1))
        twins = [os.path.relpath(t, self.root) for t in self.sf._twins(self.root, full, text)]
        for t in twins:
            open(os.path.join(self.root, t), "w").write(text.replace(old, new, 1))
        for c in [p] + twins:
            if c not in self.changed: self.changed.append(c)
        if p in self.new_tests: self.passed.discard(os.path.basename(p))
        return "edited %s%s" % (p, (" (and its twin %s)" % ", ".join(twins)) if twins else "")

    def create_file(self, path, content):
        p, full = self._path(path)
        why = self.sf.protected(p)
        if why:
            return "refused: %s is %s; that needs Gloria" % (p, why)
        if os.path.exists(full):
            return "refused: %s already exists; change it with edit_file" % p
        if p.startswith(self.sf.TESTS) and not re.match(r"^broker/tests/test_[\w-]+\.py$", p):
            return "refused: a new test is broker/tests/test_<name>.py"
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(str(content))
        if p.startswith(self.sf.TESTS): self.new_tests.add(p)
        if p not in self.changed: self.changed.append(p)
        return "created %s" % p

    def run_test(self, test):
        name = os.path.basename(str(test))
        if not re.match(r"^test_[\w-]+\.py$", name) or not os.path.isfile(os.path.join(self.root, self.sf.TESTS, name)):
            return "(no such suite in broker/tests: %s)" % test
        if self.run_test_fn:
            code, out = self.run_test_fn(name)
        else:
            self.sf.regenerate_reports(self.root)
            try:
                r = subprocess.run([sys.executable, os.path.join(self.root, "scripts", "run_isolated_test.py"),
                                    os.path.join(self.root, self.sf.TESTS, name)], cwd=self.root, capture_output=True,
                                   text=True, timeout=TEST_TIMEOUT)
                code, out = r.returncode, (r.stdout + r.stderr)
            except subprocess.TimeoutExpired:
                code, out = 124, "timed out after %d s" % TEST_TIMEOUT
        if code == 0: self.passed.add(name)
        else: self.passed.discard(name)
        return "%s: exit %d\n%s" % (name, code, "\n".join(str(out).splitlines()[-80:]))

    # ---- the conversation -----------------------------------------------------------------------------------------
    def _request(self):
        import claude_cache as C
        msgs = copy.deepcopy(self.messages)
        for m in msgs:                                    # one moving cache point on the newest turn
            if isinstance(m["content"], list):
                for b in m["content"]:
                    if isinstance(b, dict): b.pop("cache_control", None)
        last = msgs[-1]["content"]
        if isinstance(last, list) and last:
            last[-1]["cache_control"] = dict(C.CACHE)
        tools = copy.deepcopy(TOOLS); tools[-1]["cache_control"] = dict(C.CACHE)
        b = C.body(self.model, "", "x", TURN_TOKENS)
        b.pop("messages", None)
        b.update(system=[{"type": "text", "text": self.system, "cache_control": dict(C.CACHE)}], tools=tools, messages=msgs)
        return b

    def _call(self):
        import claude_cache as C, paid_http
        key = self.key or C._key()
        if not key:
            raise RuntimeError("no Anthropic key")
        post = self.post
        if post is None:
            import requests
            post = requests.post
        d = paid_http.send(post, __file__, C.URL, timeout=900, json=self._request(),
                           headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        d = d.json() if hasattr(d, "json") else d
        if d.get("type") == "error":
            raise RuntimeError(str(d.get("error"))[:200])
        self.spent += C.cost(C.note("study-fix", self.model, d.get("usage")))
        return d

    def _loop(self):
        """Turns until finish or give_up. Returns {"summary", "changed"} or {"refuse"}."""
        nudged = False
        while True:
            if self.turns >= self.max_turns:
                return {"refuse": "it used its %d turns without finishing (%s)" % (self.max_turns, self._last_steps())}
            if self.spent >= self.budget:
                return {"refuse": "it reached its $%.2f budget without finishing (%s)" % (self.budget, self._last_steps())}
            self.turns += 1
            d = self._call()
            content = d.get("content") or []
            self.messages.append({"role": "assistant", "content": content})    # thinking blocks go back unchanged
            uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            if not uses:
                if d.get("stop_reason") == "max_tokens" or not nudged:
                    nudged = True
                    self.messages.append({"role": "user", "content": [{"type": "text", "text":
                        "Keep working with the tools; call finish when the new test passes, or give_up."}]})
                    continue
                return {"refuse": "it stopped without finishing or giving up"}
            results, outcome = [], None
            for u in uses:
                name, args = u.get("name"), u.get("input") or {}
                self.trace.append("%s %s" % (name, str(args.get("path") or args.get("test") or args.get("pattern") or "")[:80]))
                try:
                    if name == "finish":
                        missing = [t for t in sorted(self.new_tests) if os.path.basename(t) not in self.passed]
                        if not self.new_tests:
                            out = "not yet: a fix brings one new test under broker/tests/; create it and run it"
                        elif missing:
                            out = "not yet: run your new test and make it pass first: " + ", ".join(missing)
                        else:
                            outcome = {"summary": str(args.get("summary") or "")[:1500], "changed": list(self.changed)}
                            out = "finished"
                    elif name == "give_up":
                        outcome = {"refuse": str(args.get("why") or "it gave up")[:1000]}
                        out = "noted"
                    elif name in ("read_file", "grep", "edit_file", "create_file", "run_test"):
                        out = getattr(self, name)(**{k: v for k, v in args.items()
                                                     if k in ("path", "start", "end", "pattern", "old", "new", "content", "test")})
                    else:
                        out = "(no such tool: %s)" % name
                except Exception as exc:
                    out = "error: %s" % str(exc)[:300]
                results.append({"type": "tool_result", "tool_use_id": u.get("id"), "content": str(out)[:60000]})
            self.messages.append({"role": "user", "content": results})
            if outcome:
                return outcome

    def _last_steps(self):
        return "; ".join(self.trace[-4:])

    def start(self):
        try:
            rules = open(os.path.join(self.root, "CLAUDE.md")).read()[:12000]
        except OSError:
            rules = ""
        self.system = SYSTEM + "\n\nREPOSITORY RULES (CLAUDE.md):\n" + rules
        files = "\n".join(self.sf.file_index(self.root))
        self.messages = [{"role": "user", "content": [{"type": "text", "text":
            "THE FIX VINTOS ASKED FOR:\n%s\n\nFILES IN THE REPOSITORY:\n%s\n\nBegin: find the cause in the code."
            % (self.row["what"], files)}]}]
        return self._loop()

    def repair(self, failures):
        """The whole suite failed after finish: the same conversation, its failures, and back to work."""
        detail = "\n\n".join("== %s ==\n%s" % (t, out) for t, out in failures)[:20000]
        self.passed.clear()
        self.messages.append({"role": "user", "content": [{"type": "text", "text":
            "The whole suite ran after your finish, and these failed:\n%s\n\nFind why, fix it, run them, then finish." % detail}]})
        return self._loop()
