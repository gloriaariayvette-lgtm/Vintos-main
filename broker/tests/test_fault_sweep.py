#!/usr/bin/env python3
"""The fault sweep hears every failure where it already lands, and posts each new one once (Gloria, 19 October:
"I'm hardly ever alerted to failures and yet something is clearly failing all the time").

Scratch HOME: every store the sweep reads or writes is throwaway. Slack is a stub, systemctl is a stub, and every
socket is refused - a test of a thing that posts to her Slack must never be able to."""
import json, os, socket, sys, tempfile, time, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="fault-sweep-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SLACK_TOKEN_FILE"] = os.path.join(HOME, "no-token")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import fault_sweep as F
F.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no real Slack call"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (d,)))

POSTS = []
def slack(channel, text): POSTS.append((channel, text)); return "1700000000.%06d" % len(POSTS)
FAILED = []
def systemctl(cmd, **k):
    if "is-active" in cmd: return types.SimpleNamespace(stdout="active\n")
    return types.SimpleNamespace(stdout="".join("%s loaded failed failed X\n" % u for u in FAILED))
def append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f: f.write(json.dumps(row) + "\n")
def iso(t): return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(t))

check("every store is throwaway and Slack and systemd are stubs",
      all(p.startswith(HOME) for p in (F.CONFIG, F.STATE, F.ORGANS, F.LAB_FAULTS, F.LAB_NOTEBOOK,
                                       F.WATCH_RECEIPTS, F.MUSIC, F.TOKEN_FILE)))

NOW = time.time()
# 18 October, as it was: one held question waiting every four minutes
for i in range(96):
    append(F.LAB_NOTEBOOK, {"kind": "evidence_wait", "at": iso(NOW - 5 * 3600 + i * 150),
                            "inquiry": {"question": "What are the residues of the GSDMD β1-β2 loop?"}})
append(F.LAB_NOTEBOOK, {"kind": "reflection", "at": iso(NOW - 600)})
append(F.WATCH_RECEIPTS, {"state": "failed", "at": iso(NOW - 300),
                          "results": [{"status": 0, "response": "Unexpected HTTP/1.x request: POST /3/device/abc"}]})
append(F.LAB_FAULTS, {"kind": "source_query_unavailable", "error": "HTTPError 429 for P09601 at 02:14",
                      "at": iso(NOW - 200)})
append(F.LAB_FAULTS, {"kind": "source_query_unavailable", "error": "HTTPError 429 for Q9NY35 at 03:51",
                      "at": iso(NOW - 100)})
append(F.ORGANS, {"organ": "slack", "what": "lens_failed", "why": "token xoxb-12345-abcdef revoked",
                  "at": iso(NOW - 50)})
FAILED.append("vintos-chemistry-session.service")

got = F.tend(now=NOW, run=systemctl, sender=slack, lab_active=True)
state = json.load(open(F.STATE))
kinds = sorted((r["part"], r["kind"]) for r in state["faults"].values())
check("it finds each kind of failure where it already lands",
      ("chemistry-lab", "loop") in kinds and ("watch-push", "delivery_failed") in kinds
      and ("chemistry-lab", "source_query_unavailable") in kinds and ("slack", "lens_failed") in kinds
      and ("vintos-chemistry-session.service", "unit_failed") in kinds, kinds)
check("the 96-wait loop is one fault that knows it happened 96 times",
      [r["count"] for r in state["faults"].values() if r["kind"] == "loop"] == [96], state["faults"])
check("two 429s on different proteins at different times are one fault, not two",
      [r["count"] for r in state["faults"].values() if r["kind"] == "source_query_unavailable"] == [2])
check("with no channel set, it records everything and posts nothing", POSTS == [] and got["posted"] == []
      and got["waiting"] == len(state["faults"]), got)

json.dump({"channel": "C0FAULTS"}, open(F.CONFIG, "w"))
got = F.tend(now=NOW + 900, run=systemctl, sender=slack, lab_active=True)
check("once the channel is set, the waiting faults go out, worst first, a few per sweep",
      len(POSTS) == F.POSTS_PER_SWEEP and all(c == "C0FAULTS" for c, _ in POSTS)
      and "loop" in POSTS[0][1], [t[:60] for _, t in POSTS])
check("each post says what it is, that he does not read it, and where the fix happens",
      all(t.startswith("[fault sweep] *F-") and "Not read by Vintos" in t and "docs/fault-loop.md" in t
          for _, t in POSTS))
check("a credential in an error never reaches the channel",
      not any("xoxb-12345" in t for _, t in POSTS) and any("[redacted]" in r["why"]
              for r in json.load(open(F.STATE))["faults"].values()))
n = len(POSTS)
F.tend(now=NOW + 1800, run=systemctl, sender=slack, lab_active=True)
check("re-reading the same window every sweep does not count the same waits again",
      [r["count"] for r in json.load(open(F.STATE))["faults"].values() if r["kind"] == "loop"] == [96]
      and [r["count"] for r in json.load(open(F.STATE))["faults"].values() if r["kind"] == "unit_failed"] == [1])
check("the rest go out on the next sweep", len(POSTS) == len(json.load(open(F.STATE))["faults"]),
      (len(POSTS), n))
n = len(POSTS)
append(F.LAB_FAULTS, {"kind": "source_query_unavailable", "error": "HTTPError 429 for O43511 at 04:02",
                      "at": iso(NOW + 2000)})
F.tend(now=NOW + 2700, run=systemctl, sender=slack, lab_active=True)
check("a known fault happening again is counted, not posted again", len(POSTS) == n
      and [r["count"] for r in json.load(open(F.STATE))["faults"].values()
           if r["kind"] == "source_query_unavailable"] == [3])

def refuse(channel, text): raise RuntimeError("slack: not_in_channel")
append(F.ORGANS, {"organ": "atelier", "what": "render_failed", "why": "kie refused", "at": iso(NOW + 3000)})
F.tend(now=NOW + 3600, run=systemctl, sender=refuse, lab_active=True)
row = [r for r in json.load(open(F.STATE))["faults"].values() if r["part"] == "atelier"][0]
check("Slack refusing is written down and the fault waits, it is not lost",
      not row.get("posted") and "not_in_channel" in row.get("post_error", ""), row)
F.tend(now=NOW + 4500, run=systemctl, sender=slack, lab_active=True)
check("and it goes out when Slack takes it", any("atelier" in t for _, t in POSTS))

dry_before = open(F.STATE).read(); n = len(POSTS)
append(F.ORGANS, {"organ": "dot", "what": "lost", "why": "lost its way into WSL", "at": iso(NOW + 5000)})
dry = F.tend(now=NOW + 5400, dry=True, run=systemctl, sender=slack, lab_active=True)
check("--dry says what it would post and posts and saves nothing",
      len(POSTS) == n and open(F.STATE).read() == dry_before
      and any("lost its way into WSL" in t for t in dry["would_post"]), dry)

# Silence: the failure nobody writes down
os.makedirs(os.path.dirname(F.MUSIC), exist_ok=True)
json.dump({"generated": [{"title": "Light Left On", "at": iso(NOW - 50 * 3600)}]}, open(F.MUSIC, "w"))
found = F.silences(NOW, lab_active=False)
check("no new song for 50 hours is a fault, though nothing logged one",
      any(f["part"] == "music" and f["kind"] == "silent" for f in found), found)
check("a Lab that is not running is not called silent", not any(f["part"] == "chemistry-lab" for f in found))
check("a machine without systemd reports no unit faults, not a crash",
      F.failed_units(run=lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("systemctl"))) == [])

def broken(): raise ValueError("torn file")
orig = F.lab_faults; F.lab_faults = lambda since: broken()
found = F.sweep(now=NOW, run=systemctl, lab_active=False)
F.lab_faults = orig
check("one unreadable source is itself a fault and the sweep goes on",
      any(f["kind"] == "source_unreadable" and "torn file" in f["why"] for f in found)
      and any(f["kind"] == "unit_failed" for f in found), [f["kind"] for f in found])

check("an old fault unseen for a week is forgotten, so its return is posted again",
      F.merge([], {"faults": {"x": {"last": NOW - 8 * 86400}}}, NOW) == [] )

# --- the Lab's real fault shape (F-b5423625a3, 19 October): {at, stage, error, detail}, error only the class ---
LAB_REAL = os.path.join(HOME, "lab-real-faults.jsonl")
F.LAB_FAULTS = LAB_REAL
T0 = NOW + 10000
def lab_row(stage, error, detail, dt=0, **extra):
    row = {"at": iso(T0 + dt), "error": error, "detail": detail, **extra}
    if stage is not None: row["stage"] = stage
    append(LAB_REAL, row)
lab_row("forge_report_retry", "HTTPError", "HTTP Error 403: Forbidden (Forge guard: four_unfinished)")
lab_row("material", "HTTPError", "HTTP Error 429: Too Many Requests for P09601")
lab_row("material", "HTTPError", "HTTP Error 429: Too Many Requests for Q9NY35", dt=60)
got = F.lab_faults(T0 - 1)
sigs = {f["kind"]: F.signature(f) for f in got}
check("a fault in the Lab's real shape is named by its stage", sorted(sigs) == ["forge_report_retry", "material"], got)
check("two stages failing with the same error class are two faults, not one",
      sigs["forge_report_retry"] != sigs["material"])
check("its post says the class and the reason",
      any("HTTPError: HTTP Error 403: Forbidden (Forge guard: four_unfinished)" == f["why"] for f in got), got)
check("the same stage differing only in the protein and the time is one fault",
      len({F.signature(f) for f in got if f["kind"] == "material"}) == 1)

open(LAB_REAL, "w").close()
lab_row(None, "HTTPError", "", kind="legacy_kind")
lab_row("parser_evidence", "ValueError", None)
lab_row("detail_only", "", "the reason, with no class")
lab_row("", "", "", why="only a why")
lab_row(None, None, None)
got = F.lab_faults(T0 - 1)
check("missing stage falls back to kind, then to 'fault'", [f["kind"] for f in got] ==
      ["legacy_kind", "parser_evidence", "detail_only", "fault", "fault"], [f["kind"] for f in got])
check("a missing detail keeps the class; a missing class keeps the detail; neither keeps the why or the kind",
      [f["why"] for f in got] == ["HTTPError", "ValueError", "the reason, with no class", "only a why", "fault"],
      [f["why"] for f in got])

# Credentials Dot's review found the scrubber missed - checked in what is stored and in what is posted.
open(LAB_REAL, "w").close()
lab_row("material", "HTTPError", "GET https://api.example.org/v1/search?api_key=SYNTH_KEY_1&q=GSDMD 401")
lab_row("source_fetch", "URLError", "https://alice:SYNTH_PW_2@mirror.example.org/x unreachable")
lab_row("planner", "RuntimeError", "refused: token=SYNTH_TOK_3; password: \"SYNTH PW 4\"")
os.remove(F.STATE)
POSTS.clear()
F.tend(now=T0 + 100, run=systemctl, sender=slack, lab_active=False)
F.tend(now=T0 + 1000, run=systemctl, sender=slack, lab_active=False)
stored = open(F.STATE).read(); posted = json.dumps(POSTS)
check("no credential reaches the stored record", not any(x in stored for x in ("SYNTH_KEY_1", "SYNTH_PW_2", "SYNTH_TOK_3", "SYNTH PW 4")))
check("and none reaches the channel", POSTS and not any(x in posted for x in ("SYNTH_KEY_1", "SYNTH_PW_2", "SYNTH_TOK_3", "SYNTH PW 4")))
check("what is not a credential is still there to read", "api.example.org" in posted and "unreachable" in posted)
check("ordinary errors are left whole", F.clean("HTTP Error 403: Forbidden (Forge guard: four_unfinished)")
      == "HTTP Error 403: Forbidden (Forge guard: four_unfinished)")

# Dot's correction: rows already swept are not read again, so old faults are not posted twice; a new one is.
n = len(POSTS)
F.tend(now=T0 + 2000, run=systemctl, sender=slack, lab_active=False)
check("rows already swept are not posted again", len(POSTS) == n)
lab_row("forge_report_retry", "HTTPError", "HTTP Error 403: Forbidden (Forge guard: four_unfinished)", dt=2500)
F.tend(now=T0 + 3000, run=systemctl, sender=slack, lab_active=False)
check("a new occurrence after the sweep posts once, under its stage", len(POSTS) == n + 1
      and "forge_report_retry" in POSTS[-1][1] and "four_unfinished" in POSTS[-1][1], POSTS[-1:])

srv = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the sweep and its timer are in the deploy", " fault_sweep.py" in srv and 'SWEEP_UNIT_NAME="vintos-fault-sweep"' in srv
      and "== fault sweep (every 15 min) ==" in srv)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
