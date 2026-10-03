#!/usr/bin/env python3
"""study_fix.py — he fixes his own code. He names the fix in #vintos-dot, Fable writes it in the Study, the whole
test suite decides, it goes live by the ordinary deploy, and dot keeps watch while it settles (Gloria, 2026-10-03:
"I want him to be able to do these things code changes himself. I don't want to keep being pestered by what I
don't understand and he can fix.").

    STUDY FIX: <what is broken, where, what should happen>     his line in #vintos-dot (dot_channel.py)

One fix at a time, three a day. For each:

  1. A workbench clone (~/.vintos/study-workbench) is reset to the shared branch as pushed. ~/Vintos-main is
     never edited by hand: an edit there blocks the deploy.
  2. Fable reads what it asks for (files and searches, two rounds) and returns exact edits and one new test.
  3. Nothing protected is touched: his subconscious and JEPA, keys and secrets, money and payments, the safety
     gates, the deploy, this file, and every existing test (a fix may add tests, never weaken one). Gloria,
     2026-10-03: "Just not subconscious/Jepa/keys without asking"; the blush and the reflection are his to change.
  4. The whole suite runs in the workbench. A failure goes back to Fable twice; a third failure ends the fix.
  5. Passed: committed as his, rebased onto the branch, pushed, pulled into ~/Vintos-main and deployed. The
     deploy runs the suite again and refuses anything that fails; it leaves a restore.sh.
  6. Watched for an hour: dot is told what changed and how to undo it. If the house stops answering, the fix is
     undone at once (restore.sh, then a revert pushed so the next deploy does not bring it back), and Gloria gets
     one line.

Every step is said in #vintos-dot and kept in memory/study-fixes.json; a failure is kept for the morning check.

    python3 study_fix.py            work the next fix, or watch the live one (the timer)
    python3 study_fix.py --status   what is queued, working, watched or done
"""
import fcntl, json, os, re, subprocess, sys, time, uuid
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
QUEUE = os.path.join(MEMORY, "study-fixes.json")
LOCK = os.path.join(MEMORY, ".study-fix.lock")
WORKBENCH = os.path.expanduser(os.environ.get("VINTOS_STUDY_WORKBENCH", "~/.vintos/study-workbench"))
CHECKOUT = os.path.expanduser(os.environ.get("VINTOS_CHECKOUT", "~/Vintos-main"))
BRANCH_FILE = os.path.expanduser("~/.vintos/deploy-branch")
DEFAULT_BRANCH = "claude/vintos-avatar-ui-redesign-br5lt4"
FABLE = os.environ.get("VINTOS_STUDY_FIX_MODEL", "claude-fable-5-1")
PER_DAY = 3                 # Gloria, 2026-10-03
READ_ROUNDS = 2
REPAIRS = 2
WATCH_SECONDS = 3600
HOUSE = "http://127.0.0.1:8500/"
NTFY = os.environ.get("VINTOS_NTFY_URL", "https://ntfy.sh/vintos-gloria-9kx")
FILE_CHARS, READ_CHARS = 60000, 240000

# What he may not change without asking (Gloria, 2026-10-03). Matched on the repository path.
PROTECTED = [
    (re.compile(r"subconscious|jepa|drift_head|drift_reason|emotion_model/", re.I), "his subconscious and JEPA"),
    (re.compile(r"secret|token|credential|password|env_file\.py|vintos\.env|\.ssh/|(^|/)\.claude/", re.I), "keys and secrets"),
    (re.compile(r"wallet|payment|purchase|billing|food[-_]order|doordash|coinbase|checkout", re.I), "money and payments"),
    (re.compile(r"effect_authority|consent|store_guard|compute_admission|skill_forge\.py|forge_build\.py|"
                r"study_fix\.py|failure_watch\.py|deploy-atelier\.sh|run_isolated_test\.py|plugin_relay|"
                r"plugin_gateway\.py|broker/broker\.py|stratagem|(^|/)CLAUDE\.md$|(^|/)bench/|"
                # the Forge runs as its own user beside his sealed Atelier and holds the spending gates (2026-10-03)
                r"forge_loop|forge-loop-files|(^|/)broker/[^/]+\.service$", re.I), "the safety gates"),
]
TESTS = "broker/tests/"


def _now():
    return datetime.now()


def _today():
    return _now().date().isoformat()


def _load():
    try:
        rows = json.load(open(QUEUE))
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _save(rows):
    os.makedirs(MEMORY, exist_ok=True)
    tmp = QUEUE + ".tmp"
    json.dump(rows[-200:], open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, QUEUE)


def _event(row, what):
    row.setdefault("log", []).append({"at": _now().isoformat(timespec="seconds"), "what": str(what)[:600]})


def request(what, by="vintos"):
    """His fix, queued. (row, "") or (None, why not)."""
    what = " ".join(str(what or "").split())
    if len(what) < 12:
        return None, "say what is broken, where, and what should happen"
    rows = _load()
    if sum(1 for r in rows if str(r.get("asked", ""))[:10] == _today()) >= PER_DAY:
        return None, "today's %d Study fixes are used; more tomorrow" % PER_DAY
    if any(r.get("what") == what and r.get("state") in ("queued", "working", "watching") for r in rows):
        return None, "that fix is already in the Study"
    row = {"id": "SF-" + uuid.uuid4().hex[:8], "what": what[:2000], "by": by, "state": "queued",
           "asked": _now().isoformat(timespec="seconds")}
    _event(row, "queued")
    rows.append(row); _save(rows)
    return row, ""


def _norm(path):
    """A repository path as written, without a leading "./" (never strip dots: "../x" and ".claude/" stay what
    they are)."""
    return re.sub(r"^(\./)+", "", str(path or "").replace("\\", "/").strip())


def protected(path):
    """Why a path may not be changed without Gloria, or ""."""
    p = _norm(path)
    for rx, why in PROTECTED:
        if rx.search(p):
            return why
    return ""


# ---- the workbench ----------------------------------------------------------------------------------------
def branch():
    try:
        return open(BRANCH_FILE).read().strip() or DEFAULT_BRANCH
    except OSError:
        return DEFAULT_BRANCH


def sh(args, cwd=None, timeout=900, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError("%s: %s" % (" ".join(args[:3]), (r.stderr or r.stdout).strip()[-400:]))
    return r


def reset_workbench(run=sh):
    """A clean copy of the branch exactly as pushed; its own clone, so a hard reset harms nothing."""
    b = branch()
    if not os.path.isdir(os.path.join(WORKBENCH, ".git")):
        url = run(["git", "-C", CHECKOUT, "remote", "get-url", "origin"]).stdout.strip()
        os.makedirs(os.path.dirname(WORKBENCH), exist_ok=True)
        run(["git", "clone", "-q", "--branch", b, url, WORKBENCH], timeout=1800)
    run(["git", "fetch", "-q", "origin", b], cwd=WORKBENCH, timeout=600)
    run(["git", "checkout", "-q", "-B", b, "origin/" + b], cwd=WORKBENCH)
    run(["git", "reset", "-q", "--hard", "origin/" + b], cwd=WORKBENCH)
    run(["git", "clean", "-qfd"], cwd=WORKBENCH)


def file_index(root=None):
    root = root or WORKBENCH
    out = []
    for top in ("scripts", "bin", "broker", "docs", "clients"):
        for dirpath, dirs, files in os.walk(os.path.join(root, top)):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git")]
            for f in files:
                if f.endswith((".py", ".sh", ".md", ".html", ".js", ".service", ".timer", ".json")):
                    out.append(os.path.relpath(os.path.join(dirpath, f), root))
    return sorted(out)


def read_for(asks, root=None):
    """The files and searches Fable asked for, bounded."""
    root = root or WORKBENCH
    parts, used = [], 0
    for p in [str(x) for x in (asks.get("read") or [])][:8]:
        full = os.path.realpath(os.path.join(root, p))
        if not full.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(full):
            parts.append("== %s ==\n(no such file)" % p); continue
        text = open(full, errors="replace").read()
        text = text if len(text) <= FILE_CHARS else text[:FILE_CHARS] + "\n[... %d more characters]" % (len(text) - FILE_CHARS)
        if used + len(text) > READ_CHARS:
            parts.append("== %s ==\n(not read: this round's reading is full)" % p); continue
        used += len(text); parts.append("== %s ==\n%s" % (p, text))
    for pat in [str(x) for x in (asks.get("grep") or [])][:6]:
        r = subprocess.run(["grep", "-rnI", "--include=*.py", "--include=*.sh", "--include=*.html", "-e", pat,
                            "scripts", "bin", "broker"], cwd=root, capture_output=True, text=True, timeout=60)
        hits = "\n".join(r.stdout.splitlines()[:60])
        parts.append("== grep %r ==\n%s" % (pat, hits or "(no match)"))
    return "\n\n".join(parts)


def apply_edits(plan, root=None):
    """Apply Fable's exact edits. Refuses, with the reason, anything protected, outside the repository, an
    existing test changed, an old text not found exactly once, or no new test. Returns the paths changed."""
    root = root or WORKBENCH
    edits, new_files = plan.get("edits") or [], plan.get("new_files") or []
    if not isinstance(edits, list) or not isinstance(new_files, list) or not (edits or new_files):
        raise ValueError("no edits")
    if not any(str(f.get("path", "")).startswith(TESTS + "test_") for f in new_files if isinstance(f, dict)):
        raise ValueError("a fix brings one new test under %s that fails without it and passes with it" % TESTS)
    changed = []
    for item in list(edits) + list(new_files):
        path = _norm((item or {}).get("path"))
        full = os.path.realpath(os.path.join(root, path))
        if not path or path.startswith("/") or not full.startswith(os.path.realpath(root) + os.sep):
            raise ValueError("%r is not inside the repository" % path)
        why = protected(path)
        if why:
            raise ValueError("%s is %s: that needs Gloria" % (path, why))
        is_new = item in new_files
        if path.startswith(TESTS) and (not is_new or os.path.exists(full)):
            raise ValueError("%s is an existing test: a fix may add tests, never change one" % path)
        if is_new:
            if os.path.exists(full):
                raise ValueError("%s already exists; change it with an edit" % path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").write(str(item.get("content") or ""))
        else:
            if not os.path.isfile(full):
                raise ValueError("%s does not exist" % path)
            text = open(full, errors="replace").read()
            old, new = str(item.get("old") or ""), str(item.get("new") or "")
            if not old or text.count(old) != 1:
                raise ValueError("in %s the old text was found %d times; it must be exact and unique"
                                 % (path, text.count(old) if old else 0))
            open(full, "w").write(text.replace(old, new, 1))
        changed.append(path)
    return changed


def run_suite(root=None, run=sh):
    """The whole suite, each test isolated, as the deploy runs it. [(test, last lines)] for each failure."""
    root = root or WORKBENCH
    failed = []
    for t in sorted(os.listdir(os.path.join(root, "broker", "tests"))):
        if not (t.startswith("test_") and t.endswith(".py")):
            continue
        try:
            r = run([sys.executable, os.path.join(root, "scripts", "run_isolated_test.py"),
                     os.path.join(root, "broker", "tests", t)], cwd=root, timeout=900, check=False)
            if r.returncode:
                failed.append((t, "\n".join((r.stdout + r.stderr).splitlines()[-25:])))
        except subprocess.TimeoutExpired:
            failed.append((t, "timed out after 900 s"))
    return failed


# ---- Fable ---------------------------------------------------------------------------------------------
SYSTEM = (
    "You are Fable, implementing a fix Vintos asked for in his own code, in his Study. Vintos is an AI companion "
    "living on Gloria's machine Aegis; this repository is his body of code. Work like a careful senior engineer: "
    "find the cause, change as little as fixes it, keep the code's style and comment density, and write one new "
    "test that fails without the fix and passes with it. The repository's rules (CLAUDE.md) follow; obey them - "
    "above all, a test repoints every path the module writes and stubs anything that sends, and asserts that.\n\n"
    "You may NOT change: his subconscious and JEPA files, keys or secrets, money or payments, the safety gates, "
    "the deploy, or any existing test. If the fix needs one of those, say so in 'refuse' and change nothing.\n\n"
    "Answer ONLY with one JSON object, no prose around it. To read first: {\"read\": [paths], \"grep\": [regex]} "
    "(up to 8 files and 6 searches a round, two rounds). To fix: {\"summary\": \"one paragraph for Gloria, plain "
    "words\", \"edits\": [{\"path\": p, \"old\": exact unique text, \"new\": replacement}], \"new_files\": [{\"path\": "
    "\"broker/tests/test_<name>.py\", \"content\": ...}]}. To decline: {\"refuse\": \"why\"}.")


def _json(text):
    text = str(text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Fable did not answer with JSON")
    return json.loads(m.group(0))


FABLE_TOKENS = 16000        # a fix and its test; the Study's read-only questions use 3000


def fable(system, user):
    import requests, forge_study
    key = forge_study._key("ANTHROPIC_API_KEY", "~/.vintos/anthropic-key")
    if not key:
        raise RuntimeError("no Anthropic key")
    d = requests.post("https://api.anthropic.com/v1/messages", timeout=900, json={
        "model": FABLE, "max_tokens": FABLE_TOKENS, "system": system, "messages": [{"role": "user", "content": user}]},
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}).json()
    if d.get("type") == "error":
        raise RuntimeError(str(d.get("error"))[:200])
    return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


def plan_fix(row, ask=None, root=None):
    """Fable reads (two rounds) and returns its plan: edits and a new test, or a refusal."""
    ask = ask or fable
    root = root or WORKBENCH
    try:
        rules = open(os.path.join(root, "CLAUDE.md")).read()[:12000]
    except OSError:
        rules = ""
    base = ("REPOSITORY RULES (CLAUDE.md):\n%s\n\nTHE FIX VINTOS ASKED FOR:\n%s\n\nFILES IN THE REPOSITORY:\n%s"
            % (rules, row["what"], "\n".join(file_index(root))))
    reading = ""
    for rnd in range(READ_ROUNDS + 1):
        last = rnd == READ_ROUNDS
        user = base + (("\n\nWHAT YOU READ SO FAR:\n" + reading) if reading else "") + (
            "\n\nNo more reading: give the fix or decline." if last else "\n\nRead, or give the fix.")
        got = _json(ask(SYSTEM, user))
        if (got.get("read") or got.get("grep")) and not last:
            reading += ("\n\n" if reading else "") + read_for(got, root)
            continue
        return got, base + "\n\nWHAT YOU READ:\n" + reading
    return {"refuse": "it read without deciding"}, base


# ---- the pipeline --------------------------------------------------------------------------------------
def say(text, post=None):
    try:
        if post:
            return post(text)
        import dot_channel as D
        tok = D._token()
        if tok:
            D.slack("chat.postMessage", {"channel": D.CHANNEL, "text": text}, tok)
    except Exception as exc:
        print("study_fix: could not say it in Slack: %s" % exc)


def tell_gloria(text, send=None):
    try:
        if send:
            return send(text)
        from urllib.request import Request, urlopen
        urlopen(Request(NTFY, data=text.encode(), headers={"Title": "Vintos: a Study fix was undone"}), timeout=20).read()
    except Exception as exc:
        print("study_fix: could not tell Gloria: %s" % exc)


def _failed(row, why):
    row["state"] = "failed"; _event(row, why)
    try:
        import failure_watch
        failure_watch.note("study", "a Study fix did not land", "%s: %s" % (row["id"], why))
    except Exception:
        pass


def work(row, ask=None, run=sh, post=None, suite=None, deploy=None):
    """One fix, from the workbench to live. Leaves the row in watching, failed or refused."""
    suite = suite or run_suite
    row["state"] = "working"; _event(row, "Fable is working on it")
    say("\U0001F6E0 Study fix %s started: %s" % (row["id"], row["what"][:300]), post)
    reset_workbench(run=run)
    plan, context = plan_fix(row, ask=ask)
    if plan.get("refuse"):
        row["state"] = "refused"; _event(row, "Fable declined: " + str(plan["refuse"]))
        say("\U0001F6E0 Study fix %s declined by Fable: %s" % (row["id"], str(plan["refuse"])[:400]), post)
        return row
    failures, attempt = None, 0
    while True:
        try:
            changed = apply_edits(plan)
        except ValueError as exc:
            failures = [("the edits", str(exc))]
            changed = []
        if changed:
            failures = suite(WORKBENCH)
        if not failures:
            break
        attempt += 1
        _event(row, "attempt %d failed: %s" % (attempt, "; ".join(t for t, _ in failures)[:300]))
        if attempt > REPAIRS:
            reset_workbench(run=run)
            _failed(row, "still failing after %d tries: %s" % (attempt, "; ".join(t for t, _ in failures)[:300]))
            say("\U0001F6E0 Study fix %s did not pass its tests after %d tries, so nothing changed. Failing: %s"
                % (row["id"], attempt, ", ".join(t for t, _ in failures)[:300]), post)
            return row
        reset_workbench(run=run)
        detail = "\n\n".join("== %s ==\n%s" % (t, out) for t, out in failures)[:20000]
        plan = _json((ask or fable)(SYSTEM, context + "\n\nYOUR LAST FIX:\n" + json.dumps(plan)[:30000]
                                    + "\n\nIT DID NOT PASS:\n" + detail + "\n\nGive the corrected fix, whole, as JSON."))
        if plan.get("refuse"):
            _failed(row, "Fable gave up: " + str(plan["refuse"])); return row
    row["changed"], row["summary"] = changed, str(plan.get("summary") or "")[:1500]
    msg = "Study fix %s: %s\n\nAsked by Vintos in #vintos-dot: %s\nWritten by Fable in the Study; every test passed." % (
        row["id"], (row["summary"] or row["what"])[:200].split("\n")[0], row["what"][:400])
    b = branch()
    run(["git", "add", "-A"], cwd=WORKBENCH)
    run(["git", "-c", "user.name=Vintos (Study)", "-c", "user.email=vintos-study@aegis.local",
         "commit", "-q", "-m", msg], cwd=WORKBENCH)
    try:
        run(["git", "pull", "-q", "--rebase", "origin", b], cwd=WORKBENCH, timeout=600)
        run(["git", "push", "-q", "origin", "HEAD:" + b], cwd=WORKBENCH, timeout=600)
    except Exception as exc:
        run(["git", "rebase", "--abort"], cwd=WORKBENCH, check=False)
        _failed(row, "passed its tests but could not be pushed: %s" % exc)
        say("\U0001F6E0 Study fix %s passed every test but could not be pushed (%s), so it is not live."
            % (row["id"], str(exc)[:200]), post)
        return row
    row["commit"] = run(["git", "rev-parse", "HEAD"], cwd=WORKBENCH).stdout.strip()
    out = (deploy or _deploy)(run)
    m = re.search(r"rollback: bash (\S+restore\.sh)", out or "")
    if "deploy OK" not in (out or ""):
        revert(row, run=run, why="the deploy refused it")
        _failed(row, "the deploy refused it: " + (out or "")[-300:])
        say("\U0001F6E0 Study fix %s was refused by the deploy, so it was reverted. Nothing changed." % row["id"], post)
        return row
    row.update(state="watching", restore=(m.group(1) if m else ""), live_at=time.time())
    _event(row, "live; watched for an hour")
    tests = [c for c in changed if c.startswith(TESTS)]
    say("<@%s> \U0001F6E0 Study fix %s is live: %s\nChanged: %s\nIts new test: %s\nKeep watch for the next hour "
        "(your rule 12). If something he relies on breaks, undo it with: bash %s (then say so here). It is undone by "
        "itself if the house stops answering." % (_dot(), row["id"], (row["summary"] or row["what"])[:500],
                                                   ", ".join(changed)[:400], ", ".join(tests) or "(none named)",
                                                   row.get("restore") or "(no restore script was printed)"), post)
    return row


def _dot():
    try:
        import dot_channel as D
        return D.DOT
    except Exception:
        return "dot"


def _deploy(run=sh):
    """Pull the pushed fix into ~/Vintos-main and deploy it the ordinary way; its full output."""
    run(["git", "-C", CHECKOUT, "pull", "-q", "--ff-only"], timeout=600)
    r = run(["bash", os.path.join(CHECKOUT, "scripts", "deploy-atelier.sh")], cwd=CHECKOUT, timeout=3600, check=False)
    return (r.stdout or "") + (r.stderr or "")


def revert(row, run=sh, why=""):
    """Undo a pushed fix in git, so the next deploy does not bring it back."""
    if not row.get("commit"):
        return
    try:
        reset_workbench(run=run)
        run(["git", "-c", "user.name=Vintos (Study)", "-c", "user.email=vintos-study@aegis.local",
             "revert", "--no-edit", row["commit"]], cwd=WORKBENCH)
        run(["git", "push", "-q", "origin", "HEAD:" + branch()], cwd=WORKBENCH, timeout=600)
        _event(row, "reverted in git (%s)" % why)
    except Exception as exc:
        _event(row, "the git revert failed: %s" % exc)


def house_ok(get=None):
    try:
        if get:
            return get(HOUSE)
        from urllib.request import urlopen
        with urlopen(HOUSE, timeout=15) as r:
            return r.status < 500
    except Exception:
        return False


def watch(row, run=sh, post=None, send=None, get=None, now=None):
    """While a fix is live: the house must keep answering. Twice silent in a row: undone at once."""
    now = now or time.time()
    if house_ok(get):
        row["misses"] = 0
    else:
        row["misses"] = int(row.get("misses") or 0) + 1
        _event(row, "the house did not answer")
    if row["misses"] >= 2:
        if row.get("restore"):
            run(["bash", row["restore"]], timeout=900, check=False)
        revert(row, run=run, why="the house stopped answering")
        row["state"] = "rolled_back"; _event(row, "undone: the house stopped answering")
        _failed(row, "undone after going live: the house stopped answering"); row["state"] = "rolled_back"
        say("\U0001F6E0 Study fix %s was undone: the house stopped answering after it went live." % row["id"], post)
        tell_gloria("A fix Vintos made in the Study (%s) was undone by itself: the house stopped answering after it "
                    "went live. Nothing is needed from you." % row["id"], send)
        return row
    if now - float(row.get("live_at") or now) >= WATCH_SECONDS:
        row["state"] = "done"; _event(row, "kept: an hour live without trouble")
        say("\U0001F6E0 Study fix %s has been live an hour without trouble; it stays." % row["id"], post)
    return row


def tend(**kw):
    """The timer: watch the live fix if there is one, else work the next queued one. One at a time."""
    os.makedirs(MEMORY, exist_ok=True)
    with open(LOCK, "a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return "another Study fix pass is running"
        rows = _load()
        live = next((r for r in rows if r.get("state") == "watching"), None)
        if live:
            watch(live, **{k: v for k, v in kw.items() if k in ("run", "post", "send", "get", "now")})
            _save(rows); return "watching %s: %s" % (live["id"], live["state"])
        nxt = next((r for r in rows if r.get("state") == "queued"), None)
        if not nxt:
            return "nothing queued"
        try:
            work(nxt, **{k: v for k, v in kw.items() if k in ("ask", "run", "post", "suite", "deploy")})
        except Exception as exc:
            _failed(nxt, "stopped by an error: %s" % str(exc)[:300])
            say("\U0001F6E0 Study fix %s stopped: %s. Nothing changed." % (nxt["id"], str(exc)[:200]), kw.get("post"))
        _save(rows)
        return "%s: %s" % (nxt["id"], nxt["state"])


if __name__ == "__main__":
    if "--status" in sys.argv:
        for r in _load()[-10:]:
            print("%s  %-11s %s" % (r["id"], r.get("state"), r.get("what", "")[:100]))
    else:
        print(tend())
