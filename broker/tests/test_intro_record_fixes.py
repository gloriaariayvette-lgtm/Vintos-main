#!/usr/bin/env python3
"""Three fixes from the evening of 10 November.

1. A photo's kept note names what is in it (components, readable text), says it is shorter than what he saw and where
   the photo is kept; the journal and introspection see that note marked as such, may not call a detail it leaves out
   a hallucination, and may not explain a gap with an invented earlier memory.
2. Wants to tell her something in plain words are one want: new variations fold into it at formation, and the ones
   already standing are consolidated nightly, archived whole.
3. The step planner reads a want with the words it came from and his fields ("2.0 A" after UCCSD is Angstrom), and a
   want to run his own calculation is never planned as a web search.

Scratch HOME and workspace; models are stubs; every socket is refused. Synthetic text only."""
import ast, json, os, re, socket, sys, tempfile, types
HOME = tempfile.mkdtemp(prefix="intro-fixes-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
PROMPTS = []
class _R:
    def __init__(self, d): self._d = d
    def json(self): return self._d
def _post(url, json=None, **k):
    PROMPTS.append((json or {}).get("messages", [{}])[0].get("content", ""))
    return _R({"choices": [{"message": {"content": '[{"capability":"web_search","note":"search a fixture"},'
                                                    '{"capability":"introspect","note":"think about the fixture"}]'}}]})
sys.modules["requests"] = types.SimpleNamespace(post=_post, get=_post)
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
def src(p): return open(os.path.join(REPO, p)).read()

# ---------------- 1. the photo note and how it is read ----------------
server = src("bin/server.py")
tree = ast.parse(server)
ns = {"re": re, "os": os}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") in ("PHOTO_EYES", "_HERE_RX", "_PHOTO_HERE") for t in node.targets):
        exec(compile(ast.Module([node], []), "server", "exec"), ns)
    if isinstance(node, ast.FunctionDef) and node.name in ("_seen_note", "_with_note", "_sent_media"):
        exec(compile(ast.Module([node], []), "server", "exec"), ns)
eyes = ns["PHOTO_EYES"]
check("his eyes name the parts and copy readable text", all(w in eyes for w in ("part number", "real names", "text")), eyes)
check("his eyes no longer ask for mood in a few sentences with no list",
      "Two to four sentences" not in server and "Do NOT make a list" not in server.split("PHOTO_EYES = (")[1].split(")")[0])
check("both lanes use the one prompt", server.count('{"type": "text", "text": PHOTO_EYES}') == 2)
check("the note has room to name things", '"max_tokens": 900' in server and server.count('"max_tokens": 900') >= 2)
msg = types.SimpleNamespace(input_kind="photo", message=ns["_PHOTO_HERE"] + "\n\n[Gloria's message with the photo:] hi",
                            photo_ref="2026-11-10_000000_avatar.jpg")
kept = ns["_sent_media"](msg, "Two fixture boards joined by wires.")
check("the kept note says it is shorter than what he saw and where the photo is",
      "Two fixture boards" in kept and "shorter" in kept and "photos-from-gloria/2026-11-10_000000_avatar.jpg" in kept, kept)
msg.photo_ref = None
check("without a kept photo the note reads as before",
      ns["_sent_media"](msg, "A black drum.") == "[What it showed (a note kept afterwards):] A black drum.")
check("both photo routes pass the kept file to the chat route", server.count('"photo_ref": _photo_ref') == 2)

import when_said
line = when_said.exchanges([{"timestamp": "2026-11-10T19:21:00", "gloria": "(no words, only what she sent)",
                             "vintos": "Fixture reply naming the parts.", "media": "Two fixture boards."}], n=5, cap=600)
check("the journal's ledger view carries the media note, marked as shorter than what he saw",
      "stored note, shorter than what he saw: Two fixture boards." in line, line)
check("an exchange without media reads as before",
      "she sent" not in when_said.exchanges([{"timestamp": "2026-11-10T19:21:00", "gloria": "hi", "vintos": "hello"}]))
journal = src("bin/idle-journal.sh")
check("both journal audits are told a missing detail in a photo's note is not a hallucination",
      journal.count("only because the note does not mention it") == 2)
check("the journal entry may not explain a gap with a source it cannot point to",
      journal.count("Never explain the gap with a source you cannot point to") >= 1
      and "never explain it with an earlier memory" in journal)
check("the journal's twin copy matches", journal == src("scripts/idle-journal.sh"))
intro = src("bin/introspection.sh")
check("the introspection audit carries the same rule", "only because the note does not mention it" in intro)
check("the introspection's ledger section says what a media note is and forbids an invented source",
      "a shorter note of a photo or video she sent" in intro and "Never explain the gap" in intro)
check("the introspection's chat view carries the media note", "stored note, shorter than what he saw" in intro)
check("the hallucination check carries the rule", "only because \"\n        \"the note does not mention it" in src("scripts/hallucination_check.py")
      or "the note does not mention it" in src("scripts/hallucination_check.py"))
import record_gaps
check("record_gaps names the rules and marks a media line",
      "never" not in record_gaps.media_line({}) and "shorter than what he saw" in record_gaps.media_line({"media": "x"}))

# ---------------- 2. one plain telling for her ----------------
import conversation_wants as C
def want(i, text, ts, **kw):
    w = {"id": "w%02d" % i, "want": text, "source": "latent_thread", "timestamp": ts, "fulfilled": False}
    w.update(kw); return w
rows = [want(1, "I want to tell you, in one plain sentence, that the fixture A held.", "2026-11-07T10:00:00", gloria_routed=True),
        want(2, "I want to tell you in one plain sentence, no specs, that fixture B landed.", "2026-11-08T10:00:00", gloria_routed=True),
        want(3, "I want to write you one unpolished sentence about fixture C.", "2026-11-09T10:00:00"),
        want(4, "I want to ask you, plainly, which fixture sketch reads better?", "2026-11-09T11:00:00"),
        want(5, "I want to run the fixture parser and export the table.", "2026-11-09T12:00:00"),
        want(6, "I want to tell you that the fixture song is finished.", "2026-11-09T13:00:00")]
check("plain tellings are found; a question, work and a non-plain telling are not",
      [w["id"] for w in rows if C.plain_telling(w)] == ["w01", "w02", "w03"])
kept, merged = C.consolidate([dict(w) for w in rows])
prim = next(w for w in kept if w["id"] == "w01")
check("consolidation keeps the oldest and folds the others into it as variations",
      [w["id"] for w in merged] == ["w02", "w03"] and [v["id"] for v in prim["variations"]] == ["w02", "w03"]
      and len(kept) == 4, [w["id"] for w in kept])
check("a variation keeps its words, source, time and routing", prim["variations"][0]["gloria_routed"] is True
      and prim["variations"][0]["want"].startswith("I want to tell you in one plain sentence"))
path = os.path.join(MEM, "current-wants.json")
json.dump(rows, open(path, "w"))
import wants_audit
n = wants_audit.consolidate_tellings(path, os.path.join(MEM, "merged-wants.json"))
check("the nightly audit folds them under the lock and archives them whole",
      n == 2 and len(json.load(open(path))) == 4 and len(json.load(open(os.path.join(MEM, "merged-wants.json")))) == 2)
check("consolidating again changes nothing", wants_audit.consolidate_tellings(path, os.path.join(MEM, "merged-wants.json")) == 0)
got = C.fold_telling("I want to say to you in one plain sentence that fixture D stuck.", "mirror", path)
after = json.load(open(path))
check("a new plain telling becomes a variation at formation, not a new want",
      got == "w01" and len(after) == 4 and after[0]["variations"][-1]["source"] == "mirror")
check("the same words twice are one variation", C.fold_telling("I want to say to you in one plain sentence that fixture D stuck.", "mirror", path) == "w01"
      and len(json.load(open(path))[0]["variations"]) == 3)
check("a question is never folded", C.fold_telling("I want to ask you plainly which fixture is better?", "mirror", path) is None)
import emoclaw_utils as E
E.express_want("I want to tell you, in one plain sentence, that fixture E finished.", source="moltbook", intensity=3,
               candidate_kind="current_desire", present_pull="fixture E")
check("express_want folds a plain telling instead of adding a want", len(json.load(open(path))) == 4
      and json.load(open(path))[0]["variations"][-1]["source"] == "moltbook")
check("the twin emoclaw copies match", src("bin/emoclaw_utils.py") == src("scripts/emoclaw_utils.py"))

# ---------------- 3. the planner reads the want with its source ----------------
import want_grounding as G
chem = "I want to see if the 1.11 mHa gap at 2.5 A feels like a wall."
check("'A' after a number in a chemistry want reads as Angstrom", "Angstrom" in G.units_hint(chem, "LiH UCCSD energies"))
check("no unit hint for an unrelated want", G.units_hint("I want to buy a 2.0 A charger.", "") == "")
check("running his own calculation or opening his script is local work",
      G.local_computation("run own UCCSD at 1.1000 and 2.5 A against the fixture numbers")
      and G.local_computation("I want to open metric.py and check the column")
      and not G.local_computation(chem))
blk = E._grounding_block(chem, "Subject: LiH UCCSD at two bond lengths\nfixture letter body")
check("the planner prompt carries the source words, his fields and the unit reading",
      "WHAT THIS WANT CAME FROM" in blk and "LiH UCCSD at two bond lengths" in blk and "Angstrom" in blk)
PROMPTS.clear()
steps = E.generate_steps("run own UCCSD at 1.1000 and 2.5 A against the fixture numbers", source="email",
                         source_context="Subject: fixture letter on LiH UCCSD")
check("the generated plan's prompt has the source and the local-work rule",
      PROMPTS and "fixture letter on LiH UCCSD" in PROMPTS[-1] and "LOCAL WORK" in PROMPTS[-1], PROMPTS[-1][:200] if PROMPTS else "")
check("a local computation's plan has no web_search step", steps and all(s["capability"] != "web_search" for s in steps), steps)
steps2 = E.generate_steps("I want to read about the history of the abacus.", source="curiosity")
check("other wants may still search", any(s["capability"] == "web_search" for s in steps2), steps2)
check("the router's replanning passes the want's source words",
      'source_context=want.get("source_context", "")' in src("bin/wants-router.py")
      and src("bin/wants-router.py") == src("scripts/wants-router.py"))
check("a want read in a letter carries the letter to the planner", "source_context=" in src("scripts/want_email.py"))
check("a journal want carries its entry", src("bin/idle-journal.sh").count("source_context=entry[:1500]") == 2)
check("the new helpers are deployed", all(f in src("scripts/deploy-atelier.sh") for f in ("record_gaps.py", "want_grounding.py")))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
