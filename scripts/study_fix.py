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
  6. Watched for an hour, by this file every 10 minutes and by dot (its rule 12): the fix's own test run against
     what is live, the services that were up, errors in the logs pointing into the files it changed, and the house.
     Anything broken undoes it at once (restore.sh, then a revert pushed so the next deploy does not bring it
     back), and Gloria gets one line.

Every step is said in #vintos-dot and kept in memory/study-fixes.json; a failure is kept for the morning check.

    python3 study_fix.py            work the next fix, or watch the live one (the timer)
    python3 study_fix.py --status   what is queued, working, watched or done
    python3 study_fix.py --reset-today   Gloria gives him today's three again (the records stay as they are)
"""
import fcntl, hashlib, json, os, re, subprocess, sys, tempfile, time, uuid
from datetime import datetime
import software_quota

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
QUEUE = os.path.join(MEMORY, "study-fixes.json")
RESET = os.path.join(MEMORY, "study-fix-reset.json")   # Gloria's "reset his Study fixes for the day" (--reset-today)
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
# what must still be up after a fix goes live (user units); only those up at go-live are held to it
SERVICES = ("vintos-server.service", "vintos-emoclaw.service", "vintos-dot-channel.timer", "vintos-chemistry-lab.service",
            "vintos-plugin-gateway.service", "vintos-failure-watch.timer")
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
    # Keep the existing naive timestamp format, explicitly in the quota's timezone.
    return datetime.now(software_quota.ZONE).replace(tzinfo=None)


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


def _save_progress(rows):
    """Keep requests submitted while the worker was fixing or watching a prior row."""
    with open(QUEUE + ".request.lock", "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        known = {r.get("id") for r in rows}
        rows.extend(r for r in _load() if r.get("id") not in known)
        _save(rows)


def _reset_at():
    """When Gloria last reset today's Study fixes, or "" (Gloria, 2026-10-05: "Let's reset his study fixes for the
    day so he can work"). Fixes asked before it no longer count against today's three; their records are unchanged."""
    try:
        d = json.load(open(RESET))
        return str(d.get("at", "")) if str(d.get("date", "")) == _today() else ""
    except (OSError, ValueError, AttributeError):
        return ""


def used_today(rows=None):
    """Study fixes asked today, since Gloria's last reset."""
    # The dated campaign counts every submission, even if an old reset receipt exists.
    since = "" if software_quota.preserves_usage(_today()) else _reset_at()
    return sum(1 for r in (rows if rows is not None else _load())
               if str(r.get("asked", ""))[:10] == _today() and str(r.get("asked", "")) > since)


def reset_today(by="gloria"):
    """Today's three, given back. Returns how many he has now."""
    if software_quota.preserves_usage(_today()):
        raise ValueError("the dated software campaign preserves every submission; reset refused")
    os.makedirs(MEMORY, exist_ok=True)
    tmp = RESET + ".tmp"
    json.dump({"date": _today(), "at": _now().isoformat(timespec="seconds"), "by": by}, open(tmp, "w"))
    os.replace(tmp, RESET)
    return PER_DAY - used_today()


def request(what, by="vintos"):
    """His fix, queued. (row, "") or (None, why not)."""
    # Serialise count/check/append, including requests arriving from different callers.
    os.makedirs(MEMORY, exist_ok=True)
    with open(QUEUE + ".request.lock", "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return _request(what, by)


def _request(what, by):
    what = " ".join(str(what or "").split())
    if len(what) < 12:
        return None, "say what is broken, where, and what should happen"
    rows = _load()
    limit = software_quota.limit("study", PER_DAY, _today())
    if used_today(rows) >= limit:
        return None, "today's %d Study fixes are used; more tomorrow" % limit
    if any(r.get("what") == what and r.get("state") in ("queued", "working", "watching", "waiting_deploy", "implemented_externally") for r in rows):
        return None, "that fix is already in the Study"
    row = {"id": "SF-" + uuid.uuid4().hex[:8], "what": what[:2000], "by": by, "state": "queued",
           "asked": _now().isoformat(timespec="seconds")}
    _event(row, "queued")
    rows.append(row); _save(rows)
    return row, ""


# A claim about a fix is matched to its receipt (2026-10-05: he called a fix "queued" after the Study refused it for
# the day, mixing it up with an older, different one). Accepted means a row with its SF- id exists; deployed, live or
# verified means that row is live (watching) or kept (done). Anything else is ahead of its receipt.
_CLAIM = re.compile(r"\b(?:queued|submitted|accepted|sent to (?:the|my) study|in (?:the|my) study|landed|deployed|"
                    r"live|merged|verified|kept|passed)\b", re.I)
_LIVE = re.compile(r"\b(?:landed|deployed|live|merged|verified|kept|passed)\b", re.I)
_ABOUT = re.compile(r"\bstudy\b|\bSF-[0-9a-f]{8}\b", re.I)
SF_ID = re.compile(r"\bSF-[0-9a-f]{8}\b")


def record_sha256(row):
    """Compare-and-set token for the exact registration being reconciled."""
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def reconcile_external(fix_id, receipt_path, receipt_sha256, commit, expected_record_sha256):
    """Local owner-admin operation: attest an external release, never a Study review.

    Lock out the worker and request writers; reject changed registrations/evidence. Repeating the exact
    attestation is a no-op. No model, deployment, notification, quota reset or history truncation.
    """
    if not re.fullmatch(r"SF-[0-9a-f]{8}", fix_id) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("invalid fix ID or commit")
    if any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in (receipt_sha256, expected_record_sha256)):
        raise ValueError("invalid evidence fingerprint")
    receipt_path = os.path.abspath(receipt_path)
    with open(LOCK, "a+") as worker, open(QUEUE + ".request.lock", "a+") as requests:
        fcntl.flock(worker, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(requests, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Fail closed on corrupt/missing queue; _load's empty fallback is inappropriate for reconciliation.
        with open(QUEUE, encoding="utf-8") as stream: rows = json.load(stream)
        if not isinstance(rows, list): raise ValueError("invalid Study queue")
        matches = [r for r in rows if isinstance(r, dict) and r.get("id") == fix_id]
        if len(matches) != 1: raise ValueError("fix must identify exactly one registration")
        row = matches[0]
        if row.get("state") not in ("queued", "implemented_externally"):
            raise ValueError("only queued registrations may be reconciled")
        if os.path.islink(receipt_path) or not os.path.isfile(receipt_path): raise ValueError("receipt must be a regular file")
        with open(receipt_path, "rb") as stream: raw = stream.read(65537)
        if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != receipt_sha256:
            raise ValueError("release receipt fingerprint mismatch")
        receipt = json.loads(raw)
        if (not isinstance(receipt, dict) or receipt.get("status") != "installed_locally" or receipt.get("study_id") != fix_id
                or receipt.get("automated_study_review") is not False):
            raise ValueError("receipt is not this externally installed fix")
        smoke = receipt.get("smoke")
        if (not isinstance(smoke, list) or not smoke or any(not isinstance(s, dict)
                or not s.get("suite") or type(s.get("exit_code")) is not int or s["exit_code"] != 0 for s in smoke)):
            raise ValueError("receipt lacks passing smoke evidence")
        target = receipt.get("target", "")
        name = os.path.basename(target)
        if (not re.fullmatch(r"[A-Za-z0-9_-]+\.py", name)
                or target != os.path.join(WS, "scripts", name) or protected("scripts/" + name)):
            raise ValueError("receipt target is not an eligible runtime script")
        installed = receipt.get("installed_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", installed): raise ValueError("invalid installed hash")
        subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=CHECKOUT,
                       check=True, capture_output=True, timeout=15)
        source = subprocess.check_output(["git", "show", commit + ":scripts/" + name], cwd=CHECKOUT, timeout=15)
        if hashlib.sha256(source).hexdigest() != installed: raise ValueError("commit does not match installed evidence")
        if os.path.islink(target) or not os.path.isfile(target): raise ValueError("runtime target must be a regular file")
        with open(target, "rb") as stream:
            if hashlib.sha256(stream.read()).hexdigest() != installed: raise ValueError("installed code has changed")
        evidence = {"receipt_path": receipt_path, "receipt_sha256": receipt_sha256, "commit": commit,
                    "target": target, "installed_sha256": installed, "registered_sha256": expected_record_sha256,
                    "study_reviewed": False}
        if row.get("state") == "implemented_externally":
            prior = dict(row); prior.pop("external_release", None); prior["state"] = "queued"
            prior["log"] = prior.get("log", [])[:-1]
            if (row.get("external_release") != evidence or record_sha256(prior) != expected_record_sha256
                    or row.get("log", [{}])[-1].get("what") != "implemented locally; not Study-reviewed"):
                raise ValueError("already reconciled with different evidence or history")
            return dict(row)
        if record_sha256(row) != expected_record_sha256 or "external_release" in row:
            raise ValueError("registration changed since approval")
        if not isinstance(row.get("log"), list): raise ValueError("registration history missing")
        row.update(state="implemented_externally", external_release=evidence)
        _event(row, "implemented locally; not Study-reviewed")
        fd, tmp = tempfile.mkstemp(prefix=".study-reconcile-", dir=os.path.dirname(QUEUE))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(rows, stream, indent=1, ensure_ascii=False); stream.flush(); os.fsync(stream.fileno())
            os.chmod(tmp, os.stat(QUEUE).st_mode & 0o777)
            os.replace(tmp, QUEUE)
            directory = os.open(os.path.dirname(QUEUE), os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return dict(row)


def _state_label(row):
    return "implemented locally; not Study-reviewed" if row.get("state") == "implemented_externally" else row.get("state")


def record(rows=None, limit=4):
    """The Study's last fixes as one line each, by id and state."""
    rows = _load() if rows is None else rows
    return "; ".join("%s (%s): %s" % (r.get("id"), _state_label(r), str(r.get("what", ""))[:90]) for r in rows[-limit:]) or "empty"


def claim_check(text, rows=None):
    """Why a draft's claim about a Study fix is ahead of its receipt, or ""."""
    said = [l for l in str(text or "").splitlines()
            if _ABOUT.search(l) and _CLAIM.search(l) and not re.match(r"^\s*STUDY FIX\s*:", l, re.I)
            and not l.lstrip().startswith("\U0001F6E0")]          # the Study's own receipt line, as the channel shows it
    if not said:
        return ""
    rows = _load() if rows is None else rows
    by_id = {r.get("id"): r for r in rows}
    ids = SF_ID.findall(" ".join(said))
    if not ids:
        return ("you said a Study fix is %s without naming its receipt. Name it by its SF- id, as the Study's record "
                "has it: %s" % (_CLAIM.search(" ".join(said)).group(0), record(rows)))
    for line in said:
        for i in SF_ID.findall(line):
            r = by_id.get(i)
            if not r:
                return "%s is not in the Study's record, which is: %s" % (i, record(rows))
            if _LIVE.search(line) and r.get("state") == "implemented_externally":
                return "%s was implemented locally, not Study-reviewed. Cite its external release receipt; do not claim an automated Study review." % i
            if _LIVE.search(line) and r.get("state") not in ("watching", "done"):
                return ("%s is %s: it is not deployed or verified yet. Say what it is now, and that its deploy and "
                        "check are still to come." % (i, r.get("state")))
    return ""


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
                failed.append((t, "exit status %d\n" % r.returncode + "\n".join((r.stdout + r.stderr).splitlines()[-25:])))
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


def _why_not():
    """Why Fable's last answer ended, in words, from claude_cache.LAST; '' when it is not known."""
    try:
        import claude_cache
        last = dict(claude_cache.LAST)
    except Exception:
        return ""
    stop, out = last.get("stop", ""), last.get("out", 0)
    if stop == "max_tokens":
        return " (its answer was cut off at the %d-token limit; its thinking counts toward it, and it was asked to think little)" % FABLE_TOKENS
    if stop == "refusal":
        return " (it declined the request)"
    return (" (it stopped: %s, %d tokens out)" % (stop, out)) if stop else ""


def _json(text):
    text = str(text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Fable did not answer with JSON" + _why_not())
    try:
        return json.loads(m.group(0))
    except ValueError as exc:
        raise ValueError("Fable's JSON did not parse: %s%s" % (str(exc)[:120], _why_not()))


# A fix and its test; the Study's read-only questions use 3000. Fable 5.1 always thinks first, and its thinking
# counts toward this limit: a hard fix spent it thinking and was cut off before its JSON closed (SF-6f9a460b,
# 2026-10-06). Gloria: "Don't increase headroom, turn off thinking." Fable's thinking cannot be turned off (the API
# refuses it), so it is asked to think as little as it can.
FABLE_TOKENS = 16000
FABLE_EFFORT = "low"


def fable(system, user):
    import claude_cache
    return claude_cache.ask(FABLE, system, user, FABLE_TOKENS, caller="study-fix", timeout=900, effort=FABLE_EFFORT)


def _cached(base, text):
    """The rules, the ask and the file list come first in every Fable call of one fix, so Claude reads them back
    from cache on the second read and on each repair (Gloria, 2026-10-05: "He is expensive")."""
    import claude_cache
    return claude_cache.Prompt(text, [base, text[len(base):]] if text.startswith(base) else [text])


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
        got = _json(ask(SYSTEM, _cached(base, user)))
        if (got.get("read") or got.get("grep")) and not last:
            reading += ("\n\n" if reading else "") + read_for(got, root)
            continue
        return got, _cached(base, base + "\n\nWHAT YOU READ:\n" + reading)
    return {"refuse": "it read without deciding"}, _cached(base, base)


# ---- the pipeline --------------------------------------------------------------------------------------
def say(text, post=None):
    try:
        if post:
            return post(text)
        import dot_channel as D
        D.post_or_hold(text)       # held while Gloria has paused the day, posted when she starts it (2026-10-05)
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


# What a failure leaves behind, so the next attempt and the next reader work from the exact evidence (Gloria,
# 2026-10-08: "Retain exact failure evidence: assertion, stderr, exit status, provider stop reason, code version,
# and artifact. SF-6f9a460b retained a test name but not its exact assertion; a separate final-response failure
# hit a 16,000-output-token cap. Test both failures without conflating them."). Tests and Fable's answers are kept
# apart: attempts[] for what the tests said, provider_failure for how Fable's answer ended.
ATTEMPTS_KEPT = 4
_ASSERT = re.compile(r"^(?:FAIL\b|AssertionError|E\s{2,}|.*\b\w+Error:|.*\bassert\b|Traceback)", re.I)


def failure_evidence(test, out):
    """One failing test, as kept: exit status, the assertion lines, and the tail of what it printed."""
    text = str(out or "")
    m = re.match(r"exit status (-?\d+)\n", text)
    lines = text.splitlines()[1 if m else 0:]
    return {"test": str(test)[:200], "exit_status": int(m.group(1)) if m else None,
            "assertion": [l[:400] for l in lines if _ASSERT.search(l)][-6:],
            "output_tail": "\n".join(lines)[-3000:]}


def _code_version(changed, run=None):
    """The workbench the attempt ran on: its commit, and a hash of the attempt's own changes."""
    run = run or sh
    out = {"changed": list(changed or [])[:20]}
    try:
        out["head"] = run(["git", "rev-parse", "HEAD"], cwd=WORKBENCH, check=False).stdout.strip()[:40]
        diff = run(["git", "diff", "HEAD"], cwd=WORKBENCH, check=False).stdout or ""
        out["diff_sha256"] = hashlib.sha256(diff.encode()).hexdigest()
    except Exception as exc:
        out["unknown"] = str(exc)[:120]
    return out


def keep_attempt(row, attempt, failures, changed, run=None):
    row.setdefault("attempts", []).append({"attempt": attempt, "at": _now().isoformat(timespec="seconds"),
                                           "code": _code_version(changed, run),
                                           "failures": [failure_evidence(t, o) for t, o in failures][:6]})
    row["attempts"] = row["attempts"][-ATTEMPTS_KEPT:]


def provider_evidence(exc):
    """How Fable's last answer ended, kept apart from any test failure."""
    try:
        import claude_cache
        last = dict(claude_cache.LAST)
    except Exception:
        last = {}
    return {"at": _now().isoformat(timespec="seconds"), "model": FABLE, "error": str(exc)[:400],
            "stop_reason": last.get("stop") or None, "output_tokens": last.get("out"), "output_limit": FABLE_TOKENS,
            "hit_limit": last.get("stop") == "max_tokens"}


def _failed(row, why):
    row["state"] = "failed"; _event(row, why)
    try:
        import failure_watch
        failure_watch.note("study", "a Study fix did not land", "%s: %s" % (row["id"], why))
    except Exception:
        pass


def work(row, ask=None, run=sh, post=None, suite=None, deploy=None, send=None):
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
        keep_attempt(row, attempt, failures, changed, run=run)
        first = next((f for f in row["attempts"][-1]["failures"] if f["assertion"]), None)
        said = next((l for l in reversed(first["assertion"]) if "Error" in l), first["assertion"][-1]) if first else ""
        _event(row, "attempt %d failed: %s%s" % (attempt, "; ".join(t for t, _ in failures)[:300],
                                                  (" — " + said.strip()[:200]) if said else ""))
        if attempt > REPAIRS:
            reset_workbench(run=run)
            _failed(row, "still failing after %d tries: %s" % (attempt, "; ".join(t for t, _ in failures)[:300]))
            say("\U0001F6E0 Study fix %s did not pass its tests after %d tries, so nothing changed. Failing: %s"
                % (row["id"], attempt, ", ".join(t for t, _ in failures)[:300]), post)
            return row
        reset_workbench(run=run)
        detail = "\n\n".join("== %s ==\n%s" % (t, out) for t, out in failures)[:20000]
        base = (getattr(context, "pieces", None) or [""])[0]
        plan = _json((ask or fable)(SYSTEM, _cached(base, context + "\n\nYOUR LAST FIX:\n" + json.dumps(plan)[:30000]
                                    + "\n\nIT DID NOT PASS:\n" + detail + "\n\nGive the corrected fix, whole, as JSON.")))
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
    return _after_deploy(row, out, changed, run=run, post=post, send=send)


def _after_deploy(row, out, changed, run=sh, post=None, send=None):
    """A pushed fix, after the deploy answered: live and watched, waiting for a clean checkout, or reverted."""
    if str(out or "").startswith(DIRTY):
        # someone else's edits in ~/Vintos-main are not a reason to throw away a fix that passed every test
        # (8 October: SF-9cb9996c passed, was pushed, and was reverted because the checkout held another agent's
        # uncommitted skill_forge.py edit). It waits, and is deployed on the next pass once the checkout is clean.
        if row.get("state") != "waiting_deploy":
            row["state"] = "waiting_deploy"
            row["changed_waiting"] = changed
            _event(row, "passed and pushed; waiting for a clean checkout to deploy (%s)" % out[len(DIRTY):][:200])
            say("\U0001F6E0 Study fix %s passed every test and is pushed. It waits to go live: ~/Vintos-main has "
                "someone else's uncommitted edits (%s)." % (row["id"], out[len(DIRTY):][:200]), post)
            tell_gloria("Vintos's Study fix %s passed every test and is pushed, but cannot go live while ~/Vintos-main "
                        "has uncommitted edits in: %s. To set them aside (kept, not lost): cd ~/Vintos-main && git diff > "
                        "~/aegis-local-$(date +%%F-%%H%%M).diff && git stash push -u -m aegis-local . The fix goes live by "
                        "itself on the Study's next pass." % (row["id"], out[len(DIRTY):][:300]), send)
        return row
    m = re.search(r"rollback: bash (\S+restore\.sh)", out or "")
    if "deploy OK" not in (out or ""):
        revert(row, run=run, why="the deploy refused it")
        _failed(row, "the deploy refused it: " + (out or "")[-300:])
        say("\U0001F6E0 Study fix %s was refused by the deploy, so it was reverted. Nothing changed." % row["id"], post)
        # she is told every time one of his fixes does not stay, not only when the watch undoes it (2026-10-03: the
        # first fix was refused by the deploy and reverted, and only #vintos-dot heard)
        tell_gloria("A fix Vintos made in the Study (%s) was refused by the deploy and reverted; nothing changed. "
                    "The deploy said: %s" % (row["id"], " ".join((out or "").split())[-240:]), send)
        return row
    row.update(state="watching", restore=(m.group(1) if m else ""), live_at=time.time(),
               services=[u for u in SERVICES if _active(u, run)], tests=[c for c in changed if c.startswith(TESTS)])
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


DIRTY = "CHECKOUT HAS UNCOMMITTED EDITS: "


def _dirty(run=sh):
    """The uncommitted paths in ~/Vintos-main, or ''."""
    r = run(["git", "-C", CHECKOUT, "status", "--porcelain"], timeout=120, check=False)
    return ", ".join(l[3:] for l in (r.stdout or "").splitlines() if l.strip())[:400]


def _deploy(run=sh):
    """Pull the pushed fix into ~/Vintos-main and deploy it the ordinary way; its full output. When the checkout
    holds someone's uncommitted edits, nothing is pulled or deployed: DIRTY and the paths."""
    dirty = _dirty(run)
    if dirty:
        return DIRTY + dirty
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


def _active(unit, run=sh):
    try:
        return run(["systemctl", "--user", "is-active", unit], timeout=30, check=False).stdout.strip() == "active"
    except Exception:
        return False


def broken(row, run=sh):
    """What the fix broke, from what can be checked now; "" when nothing. Its own new test, run against the live
    checkout; the services that were up when it went live; and errors in the logs that point into the files it
    changed (2026-10-03: the watch only asked whether the house answered, and dot sleeps)."""
    for t in row.get("tests") or []:
        r = run([sys.executable, os.path.join(CHECKOUT, "scripts", "run_isolated_test.py"), os.path.join(CHECKOUT, t)],
                cwd=CHECKOUT, timeout=900, check=False)
        if r.returncode:
            return "its own test fails live (%s): %s" % (t, "\n".join((r.stdout + r.stderr).splitlines()[-3:])[:300])
    for u in row.get("services") or []:
        if not _active(u, run):
            return "%s stopped" % u
    names = [os.path.basename(c) for c in row.get("changed") or [] if not c.startswith(TESTS)]
    if names:
        r = run(["journalctl", "--user", "--since", "@%d" % int(float(row.get("live_at") or time.time())),
                 "--no-pager", "-o", "cat"], timeout=60, check=False)
        rx = re.compile(r'File "[^"]*(%s)", line \d+' % "|".join(re.escape(n) for n in names))
        hit = next((l.strip() for l in (r.stdout or "").splitlines() if rx.search(l)), "")
        if hit:
            return "an error in a file it changed: %s" % hit[:300]
    return ""


def undo(row, why, run=sh, post=None, send=None):
    if row.get("restore"):
        run(["bash", row["restore"]], timeout=900, check=False)
    revert(row, run=run, why=why)
    _failed(row, "undone after going live: " + why); row["state"] = "rolled_back"
    say("\U0001F6E0 Study fix %s was undone: %s." % (row["id"], why), post)
    tell_gloria("A fix Vintos made in the Study (%s) was undone by itself: %s. Nothing is needed from you."
                % (row["id"], why), send)
    return row


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
    """While a fix is live: anything it broke undoes it at once; the house silent twice in a row undoes it."""
    now = now or time.time()
    why = broken(row, run=run)
    if why:
        return undo(row, why, run=run, post=post, send=send)
    if house_ok(get):
        row["misses"] = 0
    else:
        row["misses"] = int(row.get("misses") or 0) + 1
        _event(row, "the house did not answer")
    if row["misses"] >= 2:
        return undo(row, "the house stopped answering after it went live", run=run, post=post, send=send)
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
        waiting = next((r for r in rows if r.get("state") == "waiting_deploy"), None)
        if waiting:              # a passed, pushed fix goes live once the checkout is clean
            out = (kw.get("deploy") or _deploy)(kw.get("run") or sh)
            _after_deploy(waiting, out, waiting.get("changed_waiting") or [], run=kw.get("run") or sh,
                          post=kw.get("post"), send=kw.get("send"))
            _save_progress(rows)
            return "%s: %s" % (waiting["id"], waiting["state"])
        live = next((r for r in rows if r.get("state") == "watching"), None)
        if live:
            watch(live, **{k: v for k, v in kw.items() if k in ("run", "post", "send", "get", "now")})
            _save_progress(rows); return "watching %s: %s" % (live["id"], live["state"])
        nxt = next((r for r in rows if r.get("state") == "queued"), None)
        if not nxt:
            return "nothing queued"
        try:
            work(nxt, **{k: v for k, v in kw.items() if k in ("ask", "run", "post", "suite", "deploy", "send")})
        except Exception as exc:
            if "Fable" in str(exc):          # how its answer ended, kept apart from what the tests said
                nxt["provider_failure"] = provider_evidence(exc)
            _failed(nxt, "stopped by an error: %s" % str(exc)[:300])
            say("\U0001F6E0 Study fix %s stopped: %s. Nothing changed." % (nxt["id"], str(exc)[:200]), kw.get("post"))
        _save_progress(rows)
        return "%s: %s" % (nxt["id"], nxt["state"])


if __name__ == "__main__":
    if "--reconcile-external" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser(description="Reconcile an owner-approved external release without running Study.")
        parser.add_argument("--reconcile-external", required=True)
        parser.add_argument("--receipt", required=True); parser.add_argument("--receipt-sha256", required=True)
        parser.add_argument("--commit", required=True); parser.add_argument("--expected-record-sha256", required=True)
        args = parser.parse_args()
        row = reconcile_external(args.reconcile_external, args.receipt, args.receipt_sha256, args.commit, args.expected_record_sha256)
        print("%s: %s" % (row["id"], _state_label(row)))
    elif "--reset-today" in sys.argv:
        print("Study fixes reset for today: %d available now" % reset_today())
    elif "--status" in sys.argv:
        for r in _load()[-10:]:
            print("%s  %-11s %s" % (r["id"], _state_label(r), r.get("what", "")[:100]))
    else:
        print(tend())
