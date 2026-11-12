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

The writer is started only for a call (Gloria, 12 November: no always-on writer). Inside the nightly loop's lock,
and only when the Studio's train.lock is free, serve_writer2.sh starts it on the Studio; its PID is recorded in
memory/codefix-writer.json with the process's start time, and that PID - no other: same start time, the writer's own
command line - is stopped when the call ends, whatever the outcome (SIGTERM included). A writer
already serving that this call did not start is used and left running. A busy Studio is a refusal, never a wait.

The result goes back on the fault item the fault-fix Claude already works: a fault's own thread in #fault-fix,
under the sweep's post, labelled [code-fix worm] - "checked patch attached, tests pass" with the patch, or "couldn't
fix it", or why the worm was not run. That Claude reviews, applies it in its clone and runs every suite
(docs/fault-loop.md). The proposals file stays as the record behind the thread.

    python3 codefix_worm.py hand item.json    one call; item.json = {"source", "ref", "issue", "worktree",
                                              "test_files", "source_files", optional "regression_tests", "max_rounds"}
    python3 codefix_worm.py --show            counts and the proposals waiting for review
    python3 codefix_worm.py --candidates      open Forge code-fix entries and known faults (each still needs a test)
"""
import fcntl, hashlib, json, os, re, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # fault_sweep.py is installed beside this file

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
# the writer on demand: the worm's own Studio scripts, the PID this side started, the Studio's shared training lock
STUDIO_SCRIPTS = os.path.expanduser(os.environ.get("VINTOS_CODEFIX_STUDIO_SCRIPTS",
                                                   "~/repos/worm-jobs/wormjobs/cc_studio"))
WRITER_RECORD = os.path.join(MEM, "codefix-writer.json")
STUDIO_TRAIN_LOCK = "~/physics-lab/train.lock"
WRITER_MATCH = "qwen38-writer --host 127.0.0.1 --port 8871"    # serve_writer2.sh's own command line
SLACK_PATCH_CHARS = 3000      # a longer patch is named by its file on Aegis, its head shown
_LSTART = re.compile(r"[A-Za-z]{3} [A-Za-z]{3} \d{1,2} \d{2}:\d{2}:\d{2} \d{4}")    # ps -o lstart=, normalised
# credentials the sweep's own patterns miss: a whole private-key block (not just its BEGIN line), more token shapes,
# and a quoted literal assigned to a secret-sounding name (code like `self.token = token` keeps its shape)
_PEM_BLOCK = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S)
_MORE_TOKENS = re.compile(r"(?:xapp-[A-Za-z0-9-]{10,}|github_pat_[A-Za-z0-9_]{20,}|gh[opsur]_[A-Za-z0-9]{20,}|"
                          r"hf_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|glpat-[A-Za-z0-9_-]{20,}|"
                          r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}|npm_[A-Za-z0-9]{30,}|"
                          r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})")
_QUOTED_SECRET = re.compile(r"(?i)\b([a-z0-9_.-]*(?:api[_-]?key|access[_-]?key|secret|token|password|passwd|pwd|"
                            r"credential|auth)[a-z0-9_.-]*[\"']?\s*[:=]\s*)([\"'])[^\"'\s]{6,}\2")


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


# --- the writer, started for one call -------------------------------------------------------------------------------

class WriterUnavailable(RuntimeError):
    """The writer cannot be had for this call (the Studio training, unreachable, or the writer would not start)."""


def _ssh_studio(cmd, run, timeout=60):
    return run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "studio", cmd],
               capture_output=True, text=True, timeout=timeout)


def _adapters():
    """The adapter the worm's own config adopted (none today); served as serve_writer2.sh's nightly caller serves it."""
    cfg = _load(os.path.join(os.path.dirname(PROFILE), "config.json"), {})
    name = cfg.get("adopted_adapter") if isinstance(cfg, dict) else None
    return ["%s.gguf" % name] if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9._-]+", name) else []


class StudioWriter:
    """The writer for one call: started on the Studio by serve_writer2.sh only when train.lock is free, its PID
    recorded (memory/codefix-writer.json), and that PID stopped when the call ends. A writer this side did not start
    is used and left alone. A PID left recorded by a call that died before stopping it is stopped first."""

    def __init__(self, run=None):
        self.run = run or subprocess.run
        self.pid = None
        self.lstart = None          # the process's own start time on the Studio: a reused PID never matches it

    def __enter__(self):
        rec = _load(WRITER_RECORD, {})
        rec = rec if isinstance(rec, dict) else {}
        left, when = rec.get("pid"), rec.get("lstart")
        if isinstance(left, int) and not isinstance(left, bool) and left > 0:
            self.pid = left
            self.lstart = when if isinstance(when, str) and _LSTART.fullmatch(when) else None
            if self.lstart is None:
                # a record with no start time cannot prove the PID is still the process it named: never kill on it
                self.pid = None
                _atomic(WRITER_RECORD, {"pid": None, "left_unverified": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "last_pid": left})
            elif not self._stop():
                raise WriterUnavailable("a writer this side started earlier (PID %d) could not be stopped" % left)
        try:
            free = _ssh_studio("lockf -s -t 0 %s true" % STUDIO_TRAIN_LOCK, self.run)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise WriterUnavailable("the Studio is not reachable (%s)" % type(e).__name__)
        if free.returncode == 255:
            raise WriterUnavailable("the Studio is not reachable over ssh")
        if free.returncode != 0:
            raise WriterUnavailable("the Studio is training (train.lock is held); hand it again later")
        try:
            got = self.run(["bash", os.path.join(STUDIO_SCRIPTS, "serve_writer2.sh"), *_adapters()],
                           capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise WriterUnavailable("serve_writer2.sh did not finish (%s)" % type(e).__name__)
        out = got.stdout or ""
        started = re.search(r"^started (\d+)", out, re.M)
        if started:
            self.pid = int(started.group(1))
            self.lstart = self._started_at(self.pid)
            _atomic(WRITER_RECORD, {"pid": self.pid, "lstart": self.lstart,
                                    "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": "codefix_worm.py"})
            if not re.search(r"^healthy$", out, re.M):
                self._stop()
                raise WriterUnavailable("the writer started but never answered its health check; stopped again")
            return self
        if re.search(r"^already running \d+", out, re.M):
            return self             # someone else's writer: used for this call, left running
        tail = " ".join((out + " " + (got.stderr or "")).split())[-200:]
        raise WriterUnavailable("the writer could not be started: %s" % (tail or "rc %s" % got.returncode))

    def __exit__(self, *exc):
        if self.pid:
            self._stop()
        return False

    def _started_at(self, pid):
        """The Studio's start time for `pid` (ps lstart, whitespace-normalised), or None when it cannot be read."""
        try:
            got = _ssh_studio("ps -o lstart= -p %d" % int(pid), self.run)
        except (OSError, subprocess.TimeoutExpired):
            return None
        s = " ".join(str(got.stdout or "").split()) if got.returncode == 0 else ""
        return s if _LSTART.fullmatch(s) else None

    def _stop(self):
        """Stop the recorded PID, and only if it is still the writer this side started: same start time (when it
        was read) and the writer's own command line. True when it is gone."""
        pid = int(self.pid)
        same = ("set -- $(ps -o lstart= -p %d); [ \"$*\" = '%s' ] && " % (pid, self.lstart)) if self.lstart else ""
        try:
            got = _ssh_studio("%sps -o command= -p %d | grep -qF -- '%s' && kill %d" % (same, pid, WRITER_MATCH, pid),
                              self.run)
            gone = got.returncode != 255          # killed, or no longer the writer: either way not ours to keep
        except (OSError, subprocess.TimeoutExpired):
            gone = False
        if gone:
            self.pid = None
            _atomic(WRITER_RECORD, {"pid": None, "stopped": time.strftime("%Y-%m-%dT%H:%M:%S"), "last_pid": pid})
        else:
            _atomic(WRITER_RECORD, {"pid": pid, "lstart": self.lstart,
                                    "stop_failed": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": "codefix_worm.py"})
        return gone


WRITER = StudioWriter


# --- the result, on the fault item the fault-fix Claude works ------------------------------------------------------

def _scrub(text):
    """Anything that looks like a credential is taken out: the sweep's own patterns and the ones above."""
    import fault_sweep as FS
    t = _PEM_BLOCK.sub("[redacted private key]", str(text or ""))
    t = FS._SECRET.sub("[redacted]", t)
    t = _MORE_TOKENS.sub("[redacted]", t)
    t = FS._URL_USERINFO.sub(r"\1[redacted]@", t)
    t = FS._URL_QUERY_SECRET.sub(r"\1[redacted]", t)
    return _QUOTED_SECRET.sub(r"\1\2[redacted]\2", t)


def _redact(text):
    """A patch keeps its shape; anything that looks like a credential is taken out."""
    return _scrub(text).replace("```", "'''")


def handoff_text(row, patch=""):
    ref, status = row.get("ref"), row.get("status")
    if status == "fixed":
        body = _redact(patch)
        if len(body) > SLACK_PATCH_CHARS:
            body = body[:SLACK_PATCH_CHARS] + "\n... (cut here; the whole patch is in the file named above)"
        summary = " ".join(_redact(row.get("summary")).split())[:300]       # the worm's words are scrubbed too
        return ("[code-fix worm] *%s* - worm's checked patch attached, tests pass.\n"
                "The failing tests pass and every regression test that was green stays green (%s repair round%s). "
                "Not applied anywhere. Review it, apply it in your clone, run every suite, then the usual proposal, "
                "review and deploy messages (docs/fault-loop.md). Whole patch on Aegis: "
                "memory/codefix-worm-patches/%s.patch%s\n```\n%s\n```"
                % (ref, row.get("rounds"), "" if row.get("rounds") == 1 else "s", row["id"],
                   ("\nIn words: " + summary) if summary else "", body))
    if status == "unfixed":
        return ("[code-fix worm] *%s* - worm couldn't fix it: no checked patch after %s repair round%s. "
                "Fix it by hand as docs/fault-loop.md says." % (ref, row.get("rounds"), "" if row.get("rounds") == 1 else "s"))
    return ("[code-fix worm] *%s* - worm ran and gave no result: %s. Fix it by hand, or hand it again later."
            % (ref, " ".join(_redact(row.get("reason")).split())[:240]))


def post_to_fault(ref, text):
    """Reply in the fault's thread under the sweep's post, through the sweep's own channel and bot. A fault the sweep
    has not posted gets a message of its own in the channel, naming it."""
    import fault_sweep as FS
    channel = (_load(FS.CONFIG, {}) or {}).get("channel")
    if not channel:
        return {"error": "no #fault-fix channel in fault-sweep.json"}
    faults = (_load(FAULTS, {}) or {}).get("faults") or {}
    fault = next((f for f in faults.values() if isinstance(f, dict) and f.get("id") == ref), None)
    thread = (fault or {}).get("posted")
    ts = FS.post(channel, text, thread_ts=thread if isinstance(thread, str) and thread else None)
    return {"channel": channel, "thread": thread, "ts": ts}


NOTIFY = post_to_fault


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
    ran = False         # the worm was run (the writer was had); only then does the fault's thread hear of it
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
                with WRITER():          # started for this call and stopped by its PID, inside the nightly lock
                    ran = True
                    res = runner(request)
            except WriterUnavailable as e:      # a busy or unreachable Studio: the worm is not run, nobody waits
                res = {"status": "rejected", "reason": "writer: %s" % e}
            except Exception as e:      # the worm failing is an outcome to count, not a crash of the caller
                res = {"status": "rejected", "reason": "%s: %s" % (type(e).__name__, str(e)[:300])}
    finally:
        if lock:
            lock.close()
    if not isinstance(res, dict):
        res = {"status": "rejected", "reason": "the worm returned no result"}
    with _store_lock():
        return _record(item, res, row, cid, at, source, tell=ran and source == "fault")


class _store_lock:
    """One writer at a time for the proposals, the call log and the counts."""
    def __enter__(self):
        os.makedirs(MEM, exist_ok=True)
        self.f = open(os.path.join(MEM, ".codefix-worm.lock"), "a")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        self.f.close()


def _record(item, res, row, cid, at, source, tell=False):
    status = res.get("status") if res.get("status") in ("fixed", "unfixed", "rejected") else "rejected"
    if status == "fixed" and not str(res.get("patch") or "").strip():
        status, res = "rejected", dict(res, reason="worm said fixed but returned no patch")
    row.update(status=status, rounds=res.get("rounds"), task_id=res.get("task_id"),
               reason=res.get("reason", ""), checked=res.get("checked"))
    if tell:        # the result goes on the fault item itself, for the fault-fix Claude to review and apply
        try:
            row["handoff"] = NOTIFY(row.get("ref"), handoff_text(dict(row, summary=res.get("summary")),
                                                                  str(res.get("patch") or "")))
        except Exception as e:      # Slack refusing is recorded; the proposal and the call log still stand
            row["handoff"] = {"error": "%s: %s" % (type(e).__name__, str(e)[:200])}
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
                      "state": "proposed", "applied": False, "handoff": row.get("handoff"),
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
        # a caller's timeout (SIGTERM/SIGHUP) unwinds through the writer's `with`, so the PID it started is stopped
        # now rather than left serving until the next call
        import signal
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda signum, frame: sys.exit(128 + signum))
        row = hand(item)
        print(json.dumps(row, indent=1, sort_keys=True))
        return 0 if row["status"] != "rejected" else 2
    if argv == ["--show"]:
        props = {k: v for k, v in _load(PROPOSALS, {}).items() if v.get("state") == "proposed"}
        print(json.dumps({"counts": _load(COUNTS, {}), "proposed": props, "writer": _load(WRITER_RECORD, {})},
                         indent=1, sort_keys=True))
        return 0
    if argv == ["--candidates"]:
        print(json.dumps(candidates(), indent=1))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
