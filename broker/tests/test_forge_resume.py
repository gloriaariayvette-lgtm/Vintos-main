#!/usr/bin/env python3
"""forge_resume: the last arrow of the forge, walked.

    reach -> gap -> proposal -> her card -> build -> verify -> install -> RESUME

skill_forge.resumable() named the wants whose hand had landed and nothing consumed it,
so a want stayed BLOCKED on a missing capability long after the capability existed.
This holds the consumer to what it is allowed to do: clear the one block it recognises,
mark the proposal resumed, refuse to release a want that is still against a wall, and
survive a crash between its two writes."""
import importlib.util, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m; spec.loader.exec_module(m); return m

# Every store any of the three modules writes is repointed at a throwaway memory before
# a single call. store_guard included: its quarantine log is the one path that reaches
# out of the module under test and into her real workspace.
HOME = tempfile.mkdtemp(); MEM = os.path.join(HOME, "memory"); os.makedirs(MEM)
WANTS_FILE = os.path.join(MEM, "current-wants.json")
SG = load("store_guard", os.path.join(REPO, "scripts", "store_guard.py"))
SG.MEMORY = MEM; SG.LOG = os.path.join(MEM, "store-quarantine.jsonl")
SF = load("skill_forge", os.path.join(REPO, "scripts", "skill_forge.py"))
SF.MEMORY = MEM; SF.PROPOSALS = os.path.join(MEM, "skill-proposals.json")
FR = load("forge_resume", os.path.join(REPO, "scripts", "forge_resume.py"))
FR.MEMORY = MEM; FR.WANTS = WANTS_FILE


def put_wants(rows):
    json.dump(rows, open(WANTS_FILE, "w"), indent=1)

def get_want(wid):
    return next((w for w in json.load(open(WANTS_FILE)) if w.get("id") == wid), None)

def state_of(pid):
    return (SF._get(SF._load(), pid) or {}).get("state")

def blocked(capability):
    """The block want_spine writes when the hand he reached for does not exist."""
    return {"block_type": "CAPABILITY_ABSENT", "evidence": "no function %r in router" % capability,
            "resume_event": "capability added or step revised", "blocked_step": capability,
            "at": 1757000000.0}

def forge_to(capability, wid, wants, upto="installed"):
    """Walk one proposal through the whole legal path, exactly as the forge does."""
    row, why = SF.propose(capability, "a step of this want needs it", wid, wants=wants,
                          block={"block_type": "CAPABILITY_ABSENT"})
    assert row, why
    SF.approve(row["id"], {"invocation": "ask_each_time"})
    # A fixture with real artifact bytes and a bound verification receipt.
    import hashlib
    path = os.path.join(HOME, row["id"] + ".py")
    data = b"def fixture(note): return note\n"
    open(path,"wb").write(data)
    rows=SF._load(); live=SF._get(rows,row["id"])
    live.update(state=upto, staged=path, installed_to=path,
                verification={"schema":1,"review":"PASS","sandbox_passed":True,"sha256":hashlib.sha256(data).hexdigest()})
    SF._save(rows)
    return row["id"]


print("\n--- a want blocked on a hand he did not have gets it back ---")
wants = [{"id": "w1", "want": "I want to send Kevin something unbearable", "source": "moltbook",
          "steps": [{"capability": "send_email", "note": "write and send it", "status": "pending",
                     "last_result": "BLOCKED"}],
          "current_step_index": 0, "blocked": blocked("send_email")}]
put_wants(wants)
pid = forge_to("send_email", "w1", wants, upto="verified")
check("a verified hand is not yet resumable: it is not installed", FR.resume() == [])
check("and the want is still blocked while it is only verified", get_want("w1").get("blocked") is not None)

SF.mark(pid, "installed")
rows = FR.resume()
check("the installed hand names exactly the want that asked for it",
      len(rows) == 1 and rows[0]["want_id"] == "w1" and rows[0]["capability"] == "send_email", rows)
check("and the outcome is that it resumed", rows[0]["outcome"] == FR.RESUMED, rows[0])
w = get_want("w1")
check("the block is off the want", w.get("blocked") is None, w.get("blocked"))
check("the step it was stopped on is still pending, not completed and not failed",
      w["steps"][0]["status"] == "pending")
check("the want says which proposal released it",
      (w.get("resumed_by") or [{}])[0].get("proposal") == pid, w.get("resumed_by"))
check("and its history says why it is moving again, rather than moving silently",
      (w.get("step_history") or [{}])[-1]["result"] == "RESUMED"
      and pid in (w.get("step_history") or [{}])[-1]["findings"])
check("the proposal is closed as resumed", state_of(pid) == "resumed", state_of(pid))
check("nothing else about the want was touched",
      w["want"] == wants[0]["want"] and w["source"] == "moltbook" and w["current_step_index"] == 0)

print("\n--- and it does not do it twice ---")
check("a resumed proposal is no longer resumable", FR.resume() == [])
check("resumed is terminal: it cannot be marched anywhere else",
      SF.mark(pid, "installed")[0] is None and "terminal" in SF.mark(pid, "installed")[1])

print("\n--- a crash between the two writes loses nothing ---")
# The want is unblocked first, the proposal marked second. Kill the process in between
# and the want is free while the proposal still reads installed — which is exactly the
# state resumable() names again on the next pass.
w2 = {"id": "w2", "want": "I want to read the lab's log myself", "source": "lab",
      "steps": [{"capability": "read_lab", "status": "pending"}], "blocked": blocked("read_lab")}
put_wants([w2])
pid2 = forge_to("read_lab", "w2", [w2])
crashed = json.load(open(WANTS_FILE))
FR.release(crashed[0], "read_lab", pid2)                    # the first write landed
put_wants(crashed)                            # the second never ran
check("the proposal is still installed after the crash", state_of(pid2) == "installed")
rows = FR.resume()
check("the next pass finds the want already free", rows[0]["outcome"] == FR.ALREADY_FREE, rows)
check("and finishes the job the crash interrupted", state_of(pid2) == "resumed")

print("\n--- it will not release a want that is still against a wall ---")
w3 = {"id": "w3", "want": "I want to watch the frontier move", "source": "neither_yet",
      "steps": [{"capability": "watch_frontier", "status": "pending"}],
      "blocked": {"block_type": "TOOL_UNAVAILABLE", "evidence": "the websearch symlink is dead",
                  "resume_event": "tool or resource restored", "blocked_step": "watch_frontier"}}
put_wants([w3])
pid3 = forge_to("watch_frontier", "w3", [w3])
rows = FR.resume()
check("a want blocked on a tool that is not answering is left blocked",
      rows[0]["outcome"] == FR.STILL_BLOCKED and get_want("w3").get("blocked") is not None, rows)
check("and the proposal stays installed rather than claiming a resume it did not do",
      state_of(pid3) == "installed")
check("the reason is on the row, not only in a log", "TOOL_UNAVAILABLE" in rows[0]["detail"], rows[0])

w4 = {"id": "w4", "want": "I want to leave her a print", "source": "absence_map",
      "steps": [{"capability": "write_gcode", "status": "pending"}], "blocked": blocked("slice_stl")}
put_wants([w4])
pid4 = forge_to("write_gcode", "w4", [w4])
rows = FR.resume()
check("a hand that is not the hand the want is waiting for releases nothing",
      rows[0]["outcome"] == FR.STILL_BLOCKED and get_want("w4")["blocked"]["blocked_step"] == "slice_stl", rows)
check("and it says which hand the want is actually waiting on", "slice_stl" in rows[0]["detail"], rows[0])

w5 = dict(w4, id="w5", blocked={"block_type": "CAPABILITY_ABSENT", "evidence": "x",
                                "resume_event": "y"})     # no blocked_step at all
put_wants([w5])
pid5 = forge_to("write_gcode_2", "w5", [w5])
rows = FR.resume()
check("a block that does not name its step is not guessed at",
      rows[0]["outcome"] == FR.STILL_BLOCKED and get_want("w5").get("blocked") is not None, rows)

print("\n--- a want that stopped standing between the two reads ---")
w6 = {"id": "w6", "want": "I want to answer her post", "source": "moltbook",
      "steps": [{"capability": "post_reply", "status": "pending"}], "blocked": blocked("post_reply")}
put_wants([w6])
pid6 = forge_to("post_reply", "w6", [w6])
_real_resumable = SF.resumable
SF.resumable = lambda want_id=None: [{"proposal": pid6, "capability": "post_reply",
                                      "want_id": "w6", "want": w6["want"]}]
put_wants([])                                  # fulfilled and swept while the pass was running
rows = FR.resume()
check("a want that is gone under the lock is reported gone, not resumed",
      rows[0]["outcome"] == FR.GONE, rows)
check("and its proposal is not moved", state_of(pid6) == "installed")
put_wants([dict(w6, fulfilled=True)])
rows = FR.resume()
check("a want fulfilled under the lock is left alone too", rows[0]["outcome"] == FR.GONE, rows)
check("still not moved", state_of(pid6) == "installed")
SF.resumable = _real_resumable

print("\n--- a dry run says what it would do and writes nothing ---")
w7 = {"id": "w7", "want": "I want to keep a scrap of the lab", "source": "lab",
      "steps": [{"capability": "keep_scrap", "status": "pending"}], "blocked": blocked("keep_scrap")}
put_wants([w7])
pid7 = forge_to("keep_scrap", "w7", [w7])
before = open(WANTS_FILE).read()
rows = FR.resume(dry_run=True)
check("a dry run reports the resume it would make", rows[0]["outcome"] == FR.RESUMED, rows)
check("and the want file is byte-for-byte what it was", open(WANTS_FILE).read() == before)
check("and the proposal did not move", state_of(pid7) == "installed")
check("only the want asked for is looked at", FR.resume("w7", dry_run=True)[0]["want_id"] == "w7"
      and FR.resume("nosuchwant", dry_run=True) == [])

print("\n--- the pass actually calls it, before it reads a single want ---")
src = open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("the wants pass imports the consumer", "import forge_resume" in src)
check("and calls it", "_fr.resume()" in src)
check("ahead of the load, so the pass does not hold a stale copy of the store",
      src.index("import forge_resume") < src.index("all_wants = get_unfulfilled_wants()"))
check("a forge that is not there never stops the pass", "forge resume skipped" in src)
check("what it resumed reaches the log", "_fr.line(" in src)
line = FR.line([{"capability": "send_email", "want_id": "w1", "outcome": FR.RESUMED, "detail": ""},
                {"capability": "watch_frontier", "want_id": "w3", "outcome": FR.STILL_BLOCKED,
                 "detail": "blocked on TOOL_UNAVAILABLE"}])
check("the line names what moved and what did not", "resumed send_email" in line and "still blocked" in line, line)
check("and says nothing at all when nothing landed", FR.line([]) == "")

print("\n--- it never reached her workspace ---")
check("every store it wrote is under the throwaway home",
      FR.WANTS.startswith(HOME) and SF.PROPOSALS.startswith(HOME) and SG.LOG.startswith(HOME))
check("and her real workspace was never created",
      not os.path.exists(os.path.join(os.path.expanduser("~"), ".vintos", "workspace", "memory",
                                      "current-wants.json")))

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
