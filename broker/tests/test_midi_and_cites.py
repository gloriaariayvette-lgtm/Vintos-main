#!/usr/bin/env python3
"""Two Forge cards built directly (Gloria, 2026-10-05: "Give him the two ... yourself"): a MIDI file verified and
rendered (midi_check.py, "Isolated midi render and verify") and a paper's citation lineage (citation_trace.py,
"Citation graph traversal"), both as his tool lines in #vintos-dot.

Scratch workspace; OpenAlex is a stub that answers from this file; every socket is refused.
"""
import json, os, socket, struct, sys, tempfile, wave

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="midi-cites-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import midi_check as M
import citation_trace as C

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

WS = os.environ["SPARK_WORKSPACE"]
os.makedirs(os.path.join(WS, "memory", "art"), exist_ok=True)

def vlq(n):
    out = [n & 0x7F]; n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80); n >>= 7
    return bytes(out)
ev = []
def e(delta, b): ev.append(vlq(delta) + bytes(b))
e(0, [0xFF, 0x51, 3, 0x07, 0xA1, 0x20])           # 120 bpm
e(0, [0x90, 71, 90]); e(480, [0x80, 71, 0])       # B4, one beat
e(0, [0x90, 72, 90]); e(480, [0x90, 72, 0])       # C5 begins as B4 ends; released by a zero-velocity note-on
e(0, [0xFF, 0x51, 3, 0x0F, 0x42, 0x40])           # 60 bpm from here
e(0, [0x90, 74, 90]); e(480, [0x80, 74, 0])       # D5, one beat at the new tempo
e(0, [0x80, 60, 0])                               # a release with nothing sounding
e(0, [0x90, 76, 80])                              # E5, never released
e(0, [0xFF, 0x2F, 0])
trk = b"".join(ev)
mid = os.path.join(WS, "memory", "art", "phrase.mid")
open(mid, "wb").write(b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480) + b"MTrk" + struct.pack(">I", len(trk)) + trk)

div, events, tempos = M.read(mid)
timed, problems, coincident = M.verify(div, events, tempos)
check("every note is read with its exact time, through the tempo change",
      [(round(s, 3), round(e_, 3), M.name(p)) for s, e_, _, p, _ in timed] == [(0.0, 0.5, "B4"), (0.5, 1.0, "C5"), (1.0, 2.0, "D5")], timed)
check("a zero-velocity note-on is read as a release (running status, as the files write it)",
      any(M.name(p) == "C5" for _, _, _, p, _ in timed))
check("a release with nothing sounding is found", any("released at tick 1440 with nothing sounding" in p for p in problems), problems)
check("a note never released is found", any("E5" in p and "never released" in p for p in problems), problems)
check("coincident release and attack is named: B4 off / C5 on at tick 480",
      (480, 71, 72) in coincident and (960, 72, 74) in coincident, coincident)
report = M.check(mid, out_dir=os.path.join(WS, "memory", "art", "midi-checks"))
wav_path = os.path.join(WS, "memory", "art", "midi-checks", "phrase.check.wav")
check("it renders controlled piano audio to a WAV he can open", os.path.isfile(wav_path)
      and wave.open(wav_path).getframerate() == M.RATE and "Audio: " + wav_path in report, report)
check("the rendered attacks are found and timed against their schedule",
      "3 found for 3 scheduled onsets" in report and "within" in report and "ms of its schedule" in report, report)
check("the report says it all in plain lines", "tick 480: B4 off / C5 on (0.500 s)" in report and "never released" in report, report)
bad = os.path.join(WS, "memory", "art", "not.mid"); open(bad, "wb").write(b"hello")
check("a file that is not MIDI is said plainly, never raised", M.check(bad).startswith("MIDI check could not run") and "MThd" in M.check(bad))

# --- citation lineage, against an OpenAlex stub --------------------------------------------------------------------
def au(name, inst): return {"author": {"display_name": name}, "institutions": [{"id": inst}]}
PAPER = {"id": "https://openalex.org/W100", "display_name": "Retron reverse transcriptases beside CRISPR arrays",
         "publication_year": 2021, "cited_by_count": 40, "authorships": [au("Ana Smith", "I1"), au("Bo Li", "I2")],
         "referenced_works": ["https://openalex.org/W10", "https://openalex.org/W11"]}
ANC = [{"id": "https://openalex.org/W10", "display_name": "Retrons in bacterial immunity", "publication_year": 2019,
        "cited_by_count": 300, "authorships": [au("C Doe", "I3")]},
       {"id": "https://openalex.org/W11", "display_name": "CRISPR array census", "publication_year": 2018,
        "cited_by_count": 120, "authorships": [au("D Roe", "I4")]}]
KIDS = [{"id": "https://openalex.org/W201", "display_name": "Phage RTs at scale", "publication_year": 2023, "cited_by_count": 15,
         "authorships": [au("E Fox", "I5")], "referenced_works": ["https://openalex.org/W100", "https://openalex.org/W10"]},
        {"id": "https://openalex.org/W202", "display_name": "A note on array RTs", "publication_year": 2024, "cited_by_count": 2,
         "authorships": [au("F Gee", "I6")], "referenced_works": ["https://openalex.org/W100"]},
        {"id": "https://openalex.org/W203", "display_name": "Another follow-on", "publication_year": 2024, "cited_by_count": 1,
         "authorships": [au("G Hu", "I6")], "referenced_works": ["https://openalex.org/W100"]}]
ASKED = []
def openalex(url):
    ASKED.append(url)
    if "/works/doi:10.1234/retron.2021" in url: return PAPER
    if "filter=openalex%3AW10%7CW11" in url: return {"results": ANC}
    if "filter=cites%3AW100" in url: return {"results": KIDS}
    if "search=" in url: return {"results": [PAPER]}
    raise AssertionError("unexpected " + url)
out = C.trace("10.1234/retron.2021", fetch=openalex)
check("a DOI is found, with what it rests on and what rests on it", "Retron reverse transcriptases beside CRISPR arrays" in out
      and "Retrons in bacterial immunity" in out and "Phage RTs at scale" in out, out)
check("a descendant that cites this paper but none of its ground is marked",
      "A note on array RTs (Gee, 2024), cited 2  [cites this paper but none of its ground]" in out, out)
check("the reading says how much rests on this one result alone, and from how many institutions",
      "1 of the top 3 descendants also cite the paper's own ground" in out and "2 cite this paper alone" in out
      and "2 distinct institutions" in out and "rests on this one result" in out, out)
check("every call went to OpenAlex itself", all(u.startswith(C.API) for u in ASKED), ASKED)
check("a title works too", "Retron reverse transcriptases" in C.trace("retron RTs beside arrays", fetch=openalex))
check("nothing found, or OpenAlex down, is said plainly", C.trace("10.1/x", fetch=lambda u: (_ for _ in ()).throw(OSError("down"))).startswith("Citation lineage could not be traced"))

# --- his tool lines -------------------------------------------------------------------------------------------------
import dot_channel as D
C._get_real = C._get
C._get = lambda path, params=None, fetch=None: C._get_real(path, params, fetch=openalex)
got = D.use_tools([("MIDI", mid), ("CITES", "10.1234/retron.2021")])
check("MIDI: and CITES: are his tool lines in #vintos-dot", "B4 off / C5 on" in got and "rests on" in got, got[:600])
check("... and MIDI only reads inside his read roots", "outside the folders" in D.use_tools([("MIDI", "/etc/passwd")]))
check("his rules name both", "MIDI: a .mid file on Aegis" in D.RULES_HANDS and "CITES: a DOI" in D.RULES_HANDS)
check("the deploy installs both", " midi_check.py citation_trace.py " in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
