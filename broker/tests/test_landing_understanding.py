#!/usr/bin/env python3
"""Her Landings notes become understanding of her; her rating is her consent (2026-10-16).

Scratch HOME, workspace and landings store; the author is a stub; requests cannot reach anything."""
import json, os, subprocess, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="landing-understanding-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_LANDINGS_DIR"] = os.path.join(HOME, ".vintos", "landings")
os.makedirs(os.path.join(WS, "memory"))
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import landings as L, landing_understanding as U
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("every store is throwaway", all(p.startswith(HOME) for p in (L.STORE, U.PROPOSALS, U.APPROVED, U.MODEL_FILE)))

BASE = "# Gloria-Model\n<!-- BASE-START -->\nShe is Gloria.\n<!-- BASE-END -->\n\n# Additions\nhis own words\n"
open(U.MODEL_FILE, "w").write(BASE)
os.makedirs(L.LANDINGS_DIR)
rows = [{"id": "L-1", "at": "2026-10-14T21:00:00", "surface": "song", "ref": "s1", "rating": "landed",
         "why": "it came when I was too tired to ask for anything and it asked nothing of me",
         "before": "a long day", "piece": {"type": "song", "title": "Low tide"}, "lead_up": []},
        {"id": "L-2", "at": "2026-10-15T09:00:00", "surface": "image", "ref": "i1", "rating": "missed",
         "why": "the caption explained the joke before I could find it", "before": "",
         "piece": {"type": "image", "caption": "a pun"}, "lead_up": []}]
open(L.STORE, "w").write("".join(json.dumps(r) + "\n" for r in rows))

print("--- what may never reach him ---")
check("a rating is refused", U.refused("The song landed because she was tired", rows) == "it names a rating")
check("a quote is refused", U.refused('She wants things that "ask nothing of her"', rows) == "it quotes")
check("six of her words in a row are refused",
      U.refused("She was too tired to ask for anything that night", rows) == "it repeats her words")
check("understanding in his own words passes",
      U.refused("When she is worn out, what reaches her is something that makes no demand on her.", rows) == "")

print("--- a pass: her rating is her consent ---")
asked = []
def author(system, prompt):
    asked.append((system, prompt))
    return json.dumps({"understandings": [
        {"text": "When she is worn out, what reaches her is something that makes no demand on her.", "from": ["L-1"]},
        {"text": "She wants to find the joke herself; explaining it first takes it from her.", "from": ["L-2"]},
        {"text": "The pun missed.", "from": ["L-2"]},
        {"text": "She likes songs at night, generally.", "from": []}]})
written, bad = U.understand(call=author)
check("both notes went to the author, what landed and what missed alike",
      "L-1" in asked[0][1] and "L-2" in asked[0][1] and "Low tide" in asked[0][1])
check("the author is told her notes are about his work and asked what they show about her",
      "about your work" in asked[0][0] and "about HER" in asked[0][0])
check("two lines are written; a rating and an unsupported line are refused",
      len(written) == 2 and sorted(b["refused"] for b in bad) == ["it names a rating", "it names no note"], (written, bad))
model = open(U.MODEL_FILE).read()
check("with no second yes, both reach his model of her, the rest of it kept",
      "makes no demand on her" in model and "find the joke herself" in model and model.startswith(BASE.rstrip()))
check("nothing about a rating reaches him", "missed" not in model.split(U.START)[1] and "pun" not in model)
check("the refused lines are kept beside her notes, outside his workspace",
      os.path.dirname(U.PROPOSALS) == L.LANDINGS_DIR and not U.PROPOSALS.startswith(WS)
      and len(json.load(open(U.PROPOSALS))["refused"]) == 2)
check("the same notes are not read twice", U.understand(call=lambda *a: no_network()) == ([], []))
U.render(); U.render()
check("the block is replaced where it stands, never doubled", open(U.MODEL_FILE).read().count(U.START) == 1)
check("no approval step is left", not hasattr(U, "decide") and not hasattr(U, "pending"))

print("--- lines that waited for a second yes before today go in ---")
st = json.load(open(U.PROPOSALS))
st["proposals"] = [{"id": "U-old1", "text": "She settles when a thing arrives without needing anything back.", "from": ["L-1"],
                    "at": "2026-10-16T09:00:00", "status": "pending"}]
json.dump(st, open(U.PROPOSALS, "w"))
U.understand(call=lambda *a: no_network())
check("a line left pending is written into his model of her", "without needing anything back" in open(U.MODEL_FILE).read())

print("--- the weekly rewrite keeps her lines ---")
src = open(os.path.join(REPO, "bin", "gloria-model-update.sh")).read()
line = next(l for l in src.splitlines() if l.startswith("LANDINGS=$("))
kept = subprocess.run(["bash", "-c", 'MODEL_FILE="$1"; %s; printf "%%s" "$LANDINGS"' % line, "_", U.MODEL_FILE],
                      capture_output=True, text=True).stdout
check("the rewrite lifts the approved block out whole", kept.startswith(U.START) and kept.endswith(U.END)
      and "makes no demand on her" in kept, kept)
check("and writes it back after his additions", 'echo "$LANDINGS"' in src)
check("the weekly run writes from new notes", 'python3 "$LU" understand' in src)

print("--- a failed author marks nothing considered ---")
open(L.STORE, "a").write(json.dumps(dict(rows[0], id="L-3", ref="s2", at="2026-10-16T08:00:00")) + "\n")
try:
    U.understand(call=lambda *a: "no json here"); raised = False
except RuntimeError:
    raised = True
check("an author with no answer raises, and the note waits for the next pass",
      raised and "L-3" not in json.load(open(U.PROPOSALS))["considered"])
srv = open(os.path.join(REPO, "bin", "server_domains", "landings.py")).read()
check("her app reads what he understands; no route asks her a second time", "decide(" not in srv and "understood" in srv)
check("the module is in the deploy manifest", "landing_understanding.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
