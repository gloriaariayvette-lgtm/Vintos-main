#!/usr/bin/env python3
"""codefix_worm.py - hand a fault or a Forge code-fix item to the code-fix worm; a fix comes back as a proposal.

The code-fix worm passed its sealed final on 11 November (checked repair: 7/58 one-shot -> 40/58, 0 regressions).
Gloria, 12 November: put the worms that passed into use now; training continues alongside in the worm's own loop.

What goes in: an item (where it came from: a fault-sweep fault F-..., a Forge engineering entry, or by hand), and a
request the worm can check - the issue in words, a worktree of his code with the FAILING TEST already written in it,
the test files and the source files the fix may change. Without a failing test there is nothing to check a fix
against, so the item is refused here and the worm is not called.

What comes out, and where it goes:
  fixed     the patch is QUEUED FOR REVIEW: memory/codefix-worm-proposals.json and codefix-worm-patches/<id>.patch.
            It is never applied to his code here or anywhere else; a fix reaches him only through a reviewed
            commit and Gloria's deploy, like any other change. The worm's profile also puts the verified episode
            in its own loop's pool (the nightly cycle adds it to the verified pool it trains on).
  unfixed   logged, with how many repair rounds were tried.
  rejected  logged with the reason (no failing test, his live code as the worktree, the nightly loop busy, the
            writer not reachable, a profile error).
Every call is counted (memory/codefix-worm-counts.json) and logged (memory/codefix-worm-calls.jsonl), whatever
the outcome.

    python3 codefix_worm.py hand item.json    one call; item.json = {"source", "ref", "issue", "worktree",
                                              "test_files", "source_files", optional "regression_tests", "max_rounds"}
    python3 codefix_worm.py --show            counts and the proposals waiting for review
    python3 codefix_worm.py --candidates      open Forge code-fix entries and known faults (each still needs a test)
"""
import fcntl, hashlib, json, os, subprocess, sys, tempfile, time

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
PROPOSALS = os.path.join(MEM, "codefix-worm-proposals.json")
PATCHES = os.path.join(MEM, "codefix-worm-patches")
CALLS = os.path.join(MEM, "codefix-worm-calls.jsonl")
COUNTS = os.path.join(MEM, "codefix-worm-counts.json")
FORGE_LIST = os.path.join(MEM, "forge-for-claude-code.json")
FAULTS = os.path.join(MEM, "fault-sweep-state.json")
PROFILE = os.path.expanduser(os.environ.get("VINTOS_CODEFIX_PROFILE",
                                            "~/repos/worm-jobs/wormjobs/loop/codefix_profile.py"))
# the nightly loop (cron 00:43) holds this with flock while it serves and uses the writer; a call waits for no one
LOCK = os.environ.get("VINTOS_CODEFIX_LOCK", "/tmp/codefix-nightly.lock")
TIMEOUT_S = int(os.environ.get("VINTOS_CODEFIX_TIMEOUT", str(3 * 3600)))
SOURCES = ("fault", "forge", "manual")


def _protected():
    """His live code and the deploy checkout: the worm reads a worktree but is never pointed at these.
    Both the HOME in the environment and the account's own home, so a changed HOME does not move them."""
    homes = {os.path.expanduser("~")}
    try:
        import pwd
        homes.add(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError):
        pass
    return sorted({os.path.realpath(os.path.join(h, p)) for h in homes for p in ("Vintos-main", "Vintos", ".vintos")})


def _inside(path, roots):
    for p in roots:
        if path == p or path.startswith(p + os.sep):
            return p
    return ""


def _git_env():
    """The caller's GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE never steer git to another repository."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git_common_dir(real):
    """The repository a worktree writes into (a linked worktree shares its main checkout's .git), or None."""
    try:
        out = subprocess.run(["git", "-C", real, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             capture_output=True, text=True, timeout=30, env=_git_env())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return os.path.realpath(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _count(source, status):
    c = _load(COUNTS, {})
    c["calls"] = c.get("calls", 0) + 1
    c[status] = c.get(status, 0) + 1
    by = c.setdefault("by_source", {}).setdefault(source, {})
    by[status] = by.get(status, 0) + 1
    c["last"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _atomic(COUNTS, c)
    return c


def refusal(item):
    """Why this item cannot be handed to the worm, or '' when it can."""
    if item.get("source") not in SOURCES:
        return "source must be one of %s" % ", ".join(SOURCES)
    if not str(item.get("issue") or "").strip():
        return "no issue text"
    if not item.get("test_files"):
        return "no failing test: write the test that shows the fault first; the worm's fix is checked against it"
    if not item.get("source_files"):
        return "no source files named for the fix"
    wt = item.get("worktree")
    if not wt or not os.path.isdir(wt):
        return "worktree missing"
    real = os.path.realpath(wt)      # symlinks, "..", trailing slashes and relative paths all end here
    protected = _protected()
    p = _inside(real, protected)
    if p:
        return "worktree is his live code or the deploy checkout (%s); use a review clone" % p
    common = _git_common_dir(real)
    if not common:
        return "worktree is not a git checkout"
    p = _inside(common, protected)
    if p:     # a linked worktree of the deploy checkout: the worm would write objects and worktrees into his repo
        return "worktree belongs to the repository of his live code or the deploy checkout (%s); use a review clone" % p
    return ""


def call_profile(request):
    """Run the worm's profile on one request; return its result dict. Any failure is a 'rejected' result."""
    if not os.path.isfile(PROFILE):
        return {"status": "rejected", "reason": "code-fix profile not found at %s" % PROFILE}
    fd, path = tempfile.mkstemp(prefix="codefix-req-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(request, f)
    try:
        out = subprocess.run([sys.executable, PROFILE, path], capture_output=True, text=True, timeout=TIMEOUT_S,
                             cwd=os.path.dirname(PROFILE), env=_git_env())
    except subprocess.TimeoutExpired:
        return {"status": "rejected", "reason": "profile timed out after %ds" % TIMEOUT_S}
    finally:
        os.unlink(path)
    res = parse_result(out.stdout)
    if res is None:
        return {"status": "rejected", "reason": "no result from profile (rc %s): %s" % (out.returncode, out.stderr.strip()[-400:])}
    return res


def parse_result(stdout):
    """The profile prints its result last, as an indented JSON object; the harness may print progress before it."""
    lines = (stdout or "").splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("{"):
            try:
                res = json.loads("\n".join(lines[i:]))
            except ValueError:
                continue
            if isinstance(res, dict) and res.get("status") in ("fixed", "unfixed", "rejected"):
                return res
    return None


def hand(item, runner=call_profile, now=None):
    """One call to the worm. Returns the row logged for it. A fixed result is queued for review, never applied."""
    if not isinstance(item, dict):
        item = {}
    now = now or time.time()
    at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
    source = item.get("source") if item.get("source") in SOURCES else "manual"
    cid = "CF-" + hashlib.sha1(("%s|%s|%s" % (source, item.get("ref"), now)).encode()).hexdigest()[:10]
    row = {"id": cid, "at": at, "source": source, "ref": item.get("ref"), "issue": str(item.get("issue") or "")[:600]}
    why = refusal(item)
    res = None
    lock = None
    if not why:
        try:
            lock = open(LOCK, "a")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            why = "busy: the code-fix worm's nightly loop is running (or its lock %s cannot be taken); hand it again later" % LOCK
    try:
        if why:
            res = {"status": "rejected", "reason": why}
        else:
            request = {k: item[k] for k in ("issue", "worktree", "test_files", "source_files", "regression_tests",
                                            "max_rounds") if k in item}
            # the path that was checked is the path the worm gets: the profile runs from its own directory, where a
            # relative path (or one through a symlink swapped since) would name another checkout
            request["worktree"] = os.path.realpath(item["worktree"])
            try:
                res = runner(request)
            except Exception as e:      # the worm failing is an outcome to count, not a crash of the caller
                res = {"status": "rejected", "reason": "%s: %s" % (type(e).__name__, str(e)[:300])}
    finally:
        if lock:
            lock.close()
    if not isinstance(res, dict):
        res = {"status": "rejected", "reason": "the worm returned no result"}
    with _store_lock():
        return _record(item, res, row, cid, at, source)


class _store_lock:
    """One writer at a time for the proposals, the call log and the counts."""
    def __enter__(self):
        os.makedirs(MEM, exist_ok=True)
        self.f = open(os.path.join(MEM, ".codefix-worm.lock"), "a")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        self.f.close()


def _record(item, res, row, cid, at, source):
    status = res.get("status") if res.get("status") in ("fixed", "unfixed", "rejected") else "rejected"
    if status == "fixed" and not str(res.get("patch") or "").strip():
        status, res = "rejected", dict(res, reason="worm said fixed but returned no patch")
    row.update(status=status, rounds=res.get("rounds"), task_id=res.get("task_id"),
               reason=res.get("reason", ""), checked=res.get("checked"))
    if status == "fixed":
        os.makedirs(PATCHES, exist_ok=True)
        patch_path = os.path.join(PATCHES, cid + ".patch")
        with open(patch_path, "w") as f:
            f.write(str(res["patch"]))
        props = _load(PROPOSALS, {})
        props[cid] = {"at": at, "source": source, "ref": item.get("ref"), "issue": row["issue"],
                      "patch_file": patch_path, "worktree": os.path.realpath(item["worktree"]),
                      "test_files": list(item.get("test_files") or []), "source_files": list(item.get("source_files") or []),
                      "rounds": res.get("rounds"), "task_id": res.get("task_id"), "checked": res.get("checked"),
                      "summary": str(res.get("summary") or "")[:1200], "writer_adapter": res.get("writer_adapter"),
                      "state": "proposed", "applied": False,
                      "note": "checked by the worm's checker; needs review, a commit and Gloria's deploy"}
        _atomic(PROPOSALS, props)
        row["patch_file"] = patch_path
    _append(CALLS, row)
    row["counts"] = _count(source, status)
    return row


def candidates():
    """What could be handed: open Forge code-fix entries and the faults the sweep knows. Each needs its test first."""
    out = []
    for pid, e in sorted(_load(FORGE_LIST, {}).items()):
        if isinstance(e, dict) and e.get("status", "open") == "open":
            out.append({"source": "forge", "ref": pid, "issue": e.get("title") or e.get("why", "")[:200],
                        "touches": e.get("touches") or [], "tests": e.get("tests", "")})
    faults = (_load(FAULTS, {}) or {}).get("faults") or {}
    for f in sorted(faults.values(), key=lambda f: -float(f.get("count") or 0)):
        if isinstance(f, dict):
            out.append({"source": "fault", "ref": f.get("id"), "issue": "%s %s: %s" % (f.get("part"), f.get("kind"), f.get("why")),
                        "count": f.get("count")})
    return out


def main(argv):
    if argv[:1] == ["hand"] and len(argv) == 2:
        try:
            with open(argv[1]) as f:
                item = json.load(f)
        except (OSError, ValueError) as e:     # still a call: refused and counted
            item = {"source": "manual", "ref": None, "issue": "unreadable item file (%s)" % type(e).__name__}
        row = hand(item)
        print(json.dumps(row, indent=1, sort_keys=True))
        return 0 if row["status"] != "rejected" else 2
    if argv == ["--show"]:
        props = {k: v for k, v in _load(PROPOSALS, {}).items() if v.get("state") == "proposed"}
        print(json.dumps({"counts": _load(COUNTS, {}), "proposed": props}, indent=1, sort_keys=True))
        return 0
    if argv == ["--candidates"]:
        print(json.dumps(candidates(), indent=1))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
