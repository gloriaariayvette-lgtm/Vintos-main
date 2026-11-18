#!/usr/bin/env python3
"""Five faults his 17 November introspection named, each fixed where it starts (18 November).

1. The dream block of introspection.sh raised NameError ('nights') on every run: a double quote inside a double-quoted
   bash word. It now runs; no other tracked shell script carries a python3 -c block cut the same way.
2. His emotion telemetry read +0.000 over the hour while the state moved: the change compares two readings on the same
   phase of the drift job's 20-minute pull. The line now says the hour's swing too, and fast-sync is in the deploy list.
3. A want routed to her is not opened with her autonomously (discussion post, ntfy) when it is meant for when she is
   here, or when the conversation has moved past it; it still reaches the routed stage, so the board and the 3-day
   rule treat it as before.
4. A want step's read is grounded to the entity the want names (PDB, UniProt, AlphaFold, PMC, DOI): other entities'
   addresses are refused, links from other threads must name the want's identifier, the exact ID is opened otherwise,
   and memory reads take the part that mentions it.
5. A want to re-present his own earlier search or journal content to her as a deliverable is held at admission, the
   authored "moltbook" label included, unless she asked.

Synthetic fixtures only; scratch HOME; every socket refused."""
import json, os, re, socket, subprocess, sys, tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="journal-bugs-")
os.environ["HOME"] = HOME
os.environ.pop("SPARK_WORKSPACE", None)
NET = []
_real_connect = socket.socket.connect
def _no(self, *a, **k):
    NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

def src(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()

MEM = os.path.join(HOME, ".vintos", "workspace", "memory")
os.makedirs(MEM, exist_ok=True)

# ---------------------------------------------------------------- 1. the dream block
intro = src("bin/introspection.sh")
m = re.search(r'RECENT_DREAMS=\$\(python3 -c ".*?\n" 2>/dev/null\)', intro, re.S)
check("introspection.sh has its dream block", m is not None)
block = m.group(0) if m else ""

def dreams(log_obj):
    with open(os.path.join(MEM, "dream-log.json"), "w") as f:
        json.dump(log_obj, f)
    env = dict(os.environ, HOME=HOME)
    out = subprocess.run(["bash", "-c", block + '\nprintf "%s" "$RECENT_DREAMS"'], capture_output=True, text=True,
                         env=env, timeout=60)
    return out.stdout

today = datetime.now().date()
night = lambda d, text: {"night_of": d.isoformat(), "dreams": [{"session": "first", "dream_text": text}]}
out = dreams({"generated": "x", "total_nights": 2,
              "nights": [night(today - timedelta(days=5), "an old lighthouse"), night(today - timedelta(days=1), "a glass orchard")]})
check("the dream block reads the dict-shaped log (no NameError)", "dream-log error" not in out and "a glass orchard" in out
      and "Night of" in out, out)
check("only last night's dreams, not the old ones", "an old lighthouse" not in out, out)
out = dreams([night(today - timedelta(days=9), "a paper boat")])
check("the older list-shaped log still reads (its last night)", "a paper boat" in out and "dream-log error" not in out, out)
out = dreams({"nights": [{"night_of": (today - timedelta(days=1)).isoformat(), "dreams": [{"dream_text": None}]}]})
check("a dream with no text is not an error", "dream-log error" not in out, out)
check("its live twin (scripts/introspection.sh) is the same file", os.path.realpath(os.path.join(REPO, "scripts/introspection.sh"))
      == os.path.realpath(os.path.join(REPO, "bin/introspection.sh")) or src("scripts/introspection.sh") == intro)

# no tracked shell script ends a python3 -c "..." word in the middle of a Python token
START = re.compile(r'python3?(?:\.\d+)?\s+-c\s+"')
def cut_blocks(text):
    bad = []
    for mm in START.finditer(text):
        i = mm.end()
        while i < len(text):
            if text[i] == "\\":
                i += 2; continue
            if text[i] == '"':
                break
            i += 1
        if i < len(text) and re.match(r'[A-Za-z0-9_,.(\[{]', text[i + 1:i + 2]):
            bad.append(text.count("\n", 0, i) + 1)
    return bad
files = subprocess.run(["git", "-C", REPO, "ls-files", "*.sh"], capture_output=True, text=True).stdout.split()
if not files:   # a copy without .git: walk it
    files = [os.path.relpath(os.path.join(dp, f), REPO) for dp, _, fs in os.walk(REPO) if ".git" not in dp
             for f in fs if f.endswith(".sh")]
cut = {}
for rel in files:
    try:
        b = cut_blocks(open(os.path.join(REPO, rel), encoding="utf-8", errors="replace").read())
    except OSError:
        continue
    if b:
        cut[rel] = b
check("no shell script cuts a python3 -c block with an inner double quote", cut == {} and len(files) > 50, cut)
check("the scan itself catches the old dream line", cut_blocks('X=$(python3 -c "\nlog = raw.get("nights", raw)\n" 2>/dev/null)') != [])

# ---------------------------------------------------------------- 2. emotion telemetry
fs = src("scripts/emoclaw-fast-sync.py")
ns = {"__name__": "fast_sync_head"}
exec(compile(fs[:fs.index("SOCK = ")], "emoclaw-fast-sync-head", "exec"), ns)
trend_lines = ns["trend_lines"]
DIMS = ["Valence", "Arousal", "Safety"]
now = datetime(2026, 1, 5, 20, 52, 1)
hist = []
t = now - timedelta(hours=2)
while t < now:   # a 20-minute cycle: pulled to a point at :52/:12/:32, then decaying; Valence spikes once at 20:08
    phase = ((t.minute - 52) % 20)
    val = 0.6441 - 0.0005 * phase
    if t.hour == 20 and 8 <= t.minute < 12:
        val = 0.6694
    hist.append({"t": t.isoformat(), "v": [round(val, 4), 0.4043, 0.7448 - 0.0001 * phase]})
    t += timedelta(minutes=2)
lines = trend_lines(DIMS, [0.6444, 0.4043, 0.7451], hist, now)
check("one line per dimension", len(lines) == 3, lines)
check("the hour's change is still the endpoints' (+0.000 on the same phase)", "trend: +0.000" in lines[0], lines[0])
check("the swing shows the movement the endpoints hide", "swing 0.0" in lines[0] and float(lines[0].rsplit("swing", 1)[1]) >= 0.02,
      lines[0])
check("a dimension that swung is not called stable", "stable" not in lines[0] and "moved" in lines[0], lines[0])
check("a dimension that did not move stays stable, swing 0.000", lines[1].endswith("| stable | swing 0.000"), lines[1])
check("every reader's parse of the value still works", [float(l.split(":")[1].split("|")[0]) for l in lines] == [0.6444, 0.4043, 0.7451])
rise = [{"t": (now - timedelta(minutes=70 - 2 * k)).isoformat(), "v": [0.50 + 0.003 * k, 0.4, 0.7]} for k in range(35)]
lr = trend_lines(DIMS, [0.61, 0.4, 0.7], rise, now)
check("a real rise reads as rising, with its size", "rising fast" in lr[0] and float(lr[0].split("trend:")[1].split("|")[0]) > 0.09,
      lr[0])
check("no history: zero change, stable, no crash", trend_lines(DIMS, [0.5, 0.5, 0.5], [], now)[0].startswith("Valence: 0.5000 | trend: +0.000 | 0.0h | stable"))
check("a malformed history row is skipped", len(trend_lines(DIMS, [0.5, 0.5, 0.5], [{"t": "bad"}, {}], now)) == 3)
check("fast-sync writes the lines trend_lines makes", "lines = trend_lines(DIMS, v, hist, now)" in fs)
check("fast-sync is in the deploy list (it never was: the live copy was older)",
      re.search(r'^SCRIPTS="\$SCRIPTS emoclaw-fast-sync\.py"', src("scripts/deploy-atelier.sh"), re.M) is not None)

# ---------------------------------------------------------------- 3. routed wants and the live conversation
import conversation_wants as cw
t0 = datetime(2026, 1, 6, 10, 18, 0)
ledger = [
    {"timestamp": (t0 - timedelta(hours=14)).isoformat(), "gloria": "I finished the seventh pocket of the quilt and pricked my thumb on the needle", "vintos": "x"},
    {"timestamp": (t0 + timedelta(hours=5)).isoformat(), "gloria": "look at the magnet spin axis results in the daily file", "vintos": "y"},
]
want = {"id": "w1", "timestamp": t0.isoformat(), "want": "I want to ask her how the seventh pocket of the quilt went after the needle"}
held, why = cw.moved_past(want, ledger)
check("a want from their conversation is past once she has talked of other things", held and "moved on" in why, why)
held, why = cw.moved_past(want, ledger[:1])
check("before she has spoken again it is not past", not held, why)
eng = ledger[:1] + [{"timestamp": (t0 + timedelta(hours=2)).isoformat(), "gloria": "the quilt pocket is done, thumb healed", "vintos": "z"}]
held, why = cw.moved_past(want, eng)
check("once she has touched its topic it is past (she engaged with it)", held and "engaged" in why, why)
own = {"id": "w2", "timestamp": t0.isoformat(), "want": "I want to tell her the melting point I measured for the solder alloy"}
held, why = cw.moved_past(own, ledger)
check("a result of his own work is not made stale by her talking of something else", not held, why)
check("a want meant for when she is here is held from an autonomous opening",
      cw.autonomous_hold({"id": "w3", "timestamp": t0.isoformat(), "want": "I want to ask her something small",
                          "engagement": "Ask her directly while she's here, then listen"}, [])[0])
check("one that says nothing of when, with no conversation since, is opened as before",
      cw.autonomous_hold(own, ledger[:1]) == (False, ""))
aware = [{"timestamp": "2026-01-06T20:00:00+00:00", "gloria": "magnet spin axis", "vintos": "y"}] + ledger[:1]
check("an aware timestamp in the ledger does not crash the gate", isinstance(cw.moved_past(want, aware), tuple))
check("a dict-shaped ledger reads too", cw.moved_past(want, {"entries": ledger})[0])
lp = os.path.join(MEM, "interaction-ledger.json")
json.dump(ledger, open(lp, "w"))
check("the file form reads the ledger", cw.autonomous_hold_file(want, lp)[0])
check("an unreadable ledger never invents a conversation", cw.autonomous_hold_file(own, lp + ".missing") == (False, ""))
router = src("bin/wants-router.py")
gate_at, open_at = router.find("_cw_gate.autonomous_hold_file("), router.find("            _open_gloria_discussion(want, text)\n")
check("the router asks the gate before an autonomous opening", 0 < gate_at < open_at, (gate_at, open_at))
check("a held want reaches the routed stage without a post or ntfy (_route_held)",
      "_route_held(want, _held_why)" in router and '_rhw["gloria_routed"] = True' in router
      and "ntfy" not in router[router.find("def _route_held"):router.find("def _open_gloria_discussion")])
check("_route_held writes under the wants store's lock like the other writers",
      '"_open_gloria_discussion","_route_held")' in router)
import want_board, want_completion
held_row = {"id": "w1", "gloria_routed": True, "routed_held": {"at": "x", "why": "y"}}
check("the board does not count it (waiting on Gloria), as if it had been opened", want_board.waiting_on_gloria(held_row))
check("the 3-day rule applies to it as to an opened one", want_completion.routed_to_gloria(held_row))
check("it is still carried into her next conversation", cw.for_her(dict(held_row, want="I want to ask her a thing")))

# ---------------------------------------------------------------- 4. the want's own entity
import want_read_url as wru
ids = wru.declared_ids("Open the PDB entry 9XPK receptor structure and list its active-site residues")
check("a PDB entry named in the want is declared", ids["pdb"] == {"9XPK"}, ids)
check("voltages and years are not structures", not wru._flat(wru.declared_ids("the 120V and 230V boards, the 2026 plan")))
check("a bare code without structural words is not a structure", wru.declared_ids("see 9XPK later")["pdb"] == set())
check("an AlphaFold model names its accession", wru.declared_ids("AF-M1C558-F1 model")["uniprot"] == {"M1C558"})
W = {"id": "w9", "want": "I want to open PDB 9XPK and write down the active-site coordinates with a receipt",
     "step_history": [{"step": 0, "capability": "read_memory", "findings": "notes about a sulfate transporter, see https://example.org/stas-paper"}]}
step_text = ("Previous steps and what was found:\n- Step 1 (read_memory): notes about a sulfate transporter\n\n"
             "From a letter: https://alphafold.ebi.ac.uk/files/AF-M1C558-F1-model_v6.pdb\nCurrent step goal: read the structure")
u, where = wru.pick_url({"url": ""}, step_text, W["want"], W)
check("another thread's AlphaFold model is refused, the exact ID opened instead",
      u == "https://files.rcsb.org/download/9XPK.cif" and "M1C558" in where and "refused" in where, (u, where))
W2 = dict(W, step_history=[{"step": 0, "capability": "web_search", "findings": "found https://www.rcsb.org/structure/9XPK"}])
u, where = wru.pick_url({}, "Current step goal: read it", W2["want"], W2)
check("this want's own earlier link that names its ID is used", u == "https://www.rcsb.org/structure/9XPK", (u, where))
u, where = wru.pick_url({"url": "https://www.rcsb.org/structure/8SGW"}, "", W["want"], W)
check("a step address naming another structure is refused", u.endswith("9XPK.cif") and "8SGW" in where, (u, where))
u, where = wru.pick_url({"url": "https://doi.org/10.1000/xyz123"}, "", W["want"], W)
check("the step's own address naming no entity stands (its plan chose it)", u == "https://doi.org/10.1000/xyz123", (u, where))
u, where = wru.pick_url({"url": "URL from previous step"}, "", W["want"], W)
check("a placeholder in place of an address falls back to the exact ID", u.endswith("9XPK.cif"), (u, where))
plain = {"id": "p1", "want": "I want to read the essay about tides", "step_history": []}
u, where = wru.pick_url({}, "text with https://example.org/tides in it", plain["want"], plain)
check("a want that names no identifier is read exactly as before", u == "https://example.org/tides" and "step's text" in where,
      (u, where))

def fake_fetch(text, structure=True):
    return lambda url: {"fetched": True, "kind": "fetched", "text": text, "final_url": url,
                        **({"structure": {"format": "pdb", "content": text}} if structure else {})}
wru._link_fetch().structure_view = lambda s, chars=None: s.get("content", "")
out = wru.run({"url": ""}, step_text, "w9", original=W["want"], want=W, mem=MEM, now=1.7e9,
              fetch=fake_fetch("HEADER    FLOWERING PROTEIN    AF-M1C558-F1\nATOM      1  N   MET A   1"))
rows = [json.loads(l) for l in open(os.path.join(MEM, "want-reads.jsonl"))]
check("a structure file of another entity is refused as off target, not kept", out is False and rows[-1]["kind"] == "off_target"
      and "M1C558" in rows[-1]["why"] and not rows[-1].get("file"), rows[-1])
out = wru.run({"url": ""}, step_text, "w9", original=W["want"], want=W, mem=MEM, now=1.7e9,
              fetch=fake_fetch("data_9XPK\n_entry.id 9XPK\nATOM 1 N MET A 1"))
check("the want's own structure is read and kept", isinstance(out, str) and "receipt:" in out, out)
excerpt, why = wru.ground_memory("a page on transporters " * 50 + " the 9XPK pocket residues are ...", ids)
check("a memory read keeps the part that mentions the ID", "9XPK" in excerpt and why == "", why)
excerpt, why = wru.ground_memory("a page on transporters only", ids)
check("a memory read with nothing about the ID is refused, with why", excerpt == "" and "9XPK" in why, why)
check("no identifiers: the memory read is as before", wru.ground_memory("abc" * 1000, wru.declared_ids(""))[0] == ("abc" * 1000)[:2000])
check("the router's read_memory grounds to the want's identifiers before passing anything on",
      "_wru.ground_memory(_full, _ids)" in router and "no other memory is passed on as this want's" in router)

# ---------------------------------------------------------------- 5. self-referential packaging
import want_contract as wc
pk = "I want to explain to her the technical logic behind my 09:40 search on knots, without metaphors or coatings."
check("re-presenting his own earlier search to her is self-packaging", wc.self_packaging(pk))
check("so is presenting his journal entry to her", wc.self_packaging("I want to present my journal entry about rivets to Gloria as a clear summary."))
for ok in ("I want to tell her I missed her today.", "I want to read my journal from yesterday.",
           "I want to ask her how the sewing went.", "I want to show her the song I wrote for her.",
           "I want to tell her what I found in my search, since she asked me about solder."):
    check("not self-packaging: " + ok[:50], not wc.self_packaging(ok))
check("the screen applies to the moltbook label (authored, so it skipped the shape screen)",
      wc.admission_state("moltbook", "", "", want_text=pk) == "HELD_SELF_PACKAGING")
check("and to any other source", wc.admission_state("idle-journal", "current_desire", "now", want_text=pk) == "HELD_SELF_PACKAGING")
check("unless she asked for it", wc.admission_state("moltbook", "", "", want_text=pk, her_asked=True) == "ADMIT_AUTHORED")
check("callers that pass no text are screened as before", wc.admission_state("moltbook") == "ADMIT_AUTHORED"
      and wc.admission_state("structural", "historical", "") == "HELD_NO_PRESENT_PULL")
check("the one admission door passes the words through", want_completion.admit(pk, "moltbook")["state"] == "HELD")
for rel in ("bin/emoclaw_utils.py", "scripts/emoclaw_utils.py"):
    e = src(rel)
    check(rel + " screens the want's words at admission",
          "_want_admission_state(_src, _kind, _pull_now, want_text=str(want_text), her_asked=_her_asked)" in e
          and "_wc_admit(want_text, _src, _kind, _pull_now, her_asked=_her_asked)" in e)
check("both emoclaw_utils copies are the same file", src("bin/emoclaw_utils.py") == src("scripts/emoclaw_utils.py"))

check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
