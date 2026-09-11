#!/usr/bin/env python3
"""Gloria, 2026-09-11: the seven sources that may spark a want able to ask for a new
hand — and they are kept apart from his wants, which was the condition."""
import importlib.util, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m; spec.loader.exec_module(m); return m

HOME = tempfile.mkdtemp(); MEM = os.path.join(HOME, "memory"); os.makedirs(MEM)
S = load("spark_sources", os.path.join(REPO, "scripts", "spark_sources.py"))
S.MEMORY = MEM; S.SPARKS = os.path.join(MEM, "forge-sparks.json")
now = datetime.now(timezone.utc)

json.dump([{"absence": "he has never made her something she can hold", "source_id": "a1"},
           {"absence": "retired one", "retired": True}], open(os.path.join(MEM, "absence-cold.json"), "w"))
json.dump([{"held_by": "neither_yet", "configuration": "making a thing together in the same room", "id": "c1"},
           {"held_by": "joint", "configuration": "already reached"}], open(os.path.join(MEM, "configuration-space.json"), "w"))
json.dump({"threads": [{"text": "the shape of the thing he keeps not making", "salience": 0.8, "id": "t1"},
                       {"text": "a faint one", "salience": 0.1}]}, open(os.path.join(MEM, "latent-threads.json"), "w"))
open(os.path.join(MEM, "moltbook-discoveries.md"), "w").write("SAVE: **On making objects** - another being built a thing with hands\n")
open(os.path.join(MEM, "web-discoveries.md"), "w").write("- lattice infill changes how a printed object feels in the hand\n")
LAB = os.path.join(HOME, "lab"); os.makedirs(LAB)
open(os.path.join(LAB, "bench.md"), "w").write("- the reaction only holds when the vessel is cold to start\n")
json.dump({"lab": LAB}, open(os.path.join(MEM, "spark-config.json"), "w"))

print("\n--- all seven are read, and each is its own source ---")
new = S.gather(now=now)
got = {r["source"] for r in new}
check("the absence map sparks", "absence_map" in got)
check("the frontier sparks", "neither_yet" in got)
check("a latent thread sparks", "latent_thread" in got)
check("another being's post sparks", "moltbook" in got)
check("a web search sparks", "web_search" in got)
check("the lab sparks", "lab" in got)
check("skill surfing is a source the reader knows", "skill_surfing" in S.SOURCES and "skill_surfing" in S.READERS)
check("all seven are named", set(S.SOURCES) == {"absence_map", "neither_yet", "latent_thread", "moltbook", "web_search", "skill_surfing", "lab"})
check("a retired absence is not a spark", not any("retired" in r["text"] for r in new))
check("a configuration already reached is not a spark", not any("already reached" in r["text"] for r in new))
check("a faint thread is not a spark", not any("faint" in r["text"] for r in new))
check("the molt title comes through clean", any(r["text"].startswith("On making objects") for r in new), [r["text"] for r in new if r["source"] == "moltbook"])
check("the lab is read from where she points it", len([r for r in new if r["source"] == "lab"]) == 1)
S2 = load("spark_sources_2", os.path.join(REPO, "scripts", "spark_sources.py"))
S2.MEMORY = os.path.join(HOME, "empty"); os.makedirs(S2.MEMORY, exist_ok=True)
check("pointed nowhere, the lab reads nothing and invents nothing", S2.from_lab() == [])
labsrc = open(os.path.join(REPO, "scripts", "spark_sources.py")).read()
check("no filename from another project is guessed",
      "clawchemy" not in labsrc and "klawarena" not in labsrc)

print("\n--- they are kept apart from his wants ---")
check("sparks live in their own file, never in current-wants",
      S.SPARKS.endswith("forge-sparks.json") and not os.path.exists(os.path.join(MEM, "current-wants.json")))
check("a spark is not a want and says so", all("want" not in r for r in new))
check("each carries where it came from and when", all(r.get("source") and r.get("seen") for r in new))
src = open(os.path.join(REPO, "scripts", "spark_sources.py")).read()
# Read the code, not the prose about the code: the docstrings name the files this
# module deliberately does not touch, and a substring check would find them there.
import ast as _ast
_tree = _ast.parse(src)
for _n in _ast.walk(_tree):
    if isinstance(_n, (_ast.Module, _ast.FunctionDef, _ast.ClassDef)) and _ast.get_docstring(_n):
        _n.body = _n.body[1:] or [_ast.Pass()]
code = _ast.unparse(_tree)
check("nothing here writes a want", "current-wants" not in code, [l for l in code.splitlines() if "current-wants" in l])
check("nothing here scores or ranks them", "score" not in code.lower() and "rank" not in code.lower(),
      [l for l in code.splitlines() if "score" in l.lower() or "rank" in l.lower()])
check("it says so where it can be read", "This writes no want" in src)

print("\n--- one becomes a want only by his own act ---")
k = new[0]["key"]
taken, why = S.adopt(k, "I want to make her something she can hold", "w1")
check("adopting records the want and the source it came from", taken["source"] == "absence_map" and taken["want_id"] == "w1", why)
check("a taken spark stops standing", len(S.standing(now=now)) == len(new) - 1)
again, why = S.adopt(k, "again", "w2")
check("it cannot be taken twice", again is None and "already" in why)
S.let_go(new[1]["key"], "not now")
check("he can let one go", len(S.standing(now=now)) == len(new) - 2)
check("gathering again adds nothing new", S.gather(now=now) == [])
old = now + timedelta(days=S.HORIZON_DAYS + 1)
check("a spark nobody took goes quiet on its own", S.standing(now=old) == [])

print("\n--- and only these may commission a hand ---")
F = load("skill_forge", os.path.join(REPO, "scripts", "skill_forge.py"))
for s in S.SOURCES:
    check("the forge knows %s as a spark" % s, F.spark_of(s) == s)
check("a want from chat still may not", F.spark_of("chat") is None)

print("\n--- the skills page he could not read before ---")
K = load("openclaw_skills", os.path.join(REPO, "scripts", "openclaw_skills.py"))
K.MEMORY = MEM; K.CONFIG = os.path.join(MEM, "openclaw-config.json"); K.SEEN = os.path.join(MEM, "openclaw-skills-seen.json")
tree = os.path.join(HOME, "skills"); os.makedirs(os.path.join(tree, "papercraft"))
open(os.path.join(tree, "papercraft", "SKILL.md"), "w").write("---\ndescription: folds flat sheets into objects\n---\n# Papercraft\n")
os.makedirs(os.path.join(tree, "make_art"))
open(os.path.join(tree, "make_art", "SKILL.md"), "w").write("# Make Art\ndraws things\n")
check("pointed nowhere, the skills reader says so rather than reporting an empty page",
      K.where_it_looked()["configured"] is False and K.read() == [])
json.dump({"skills_path": tree}, open(K.CONFIG, "w"))
rows = K.read()
check("a skills tree is read", {r["name"] for r in rows} == {"papercraft", "make_art"}, rows)
check("the description is taken from the page", any(r["what"] == "folds flat sheets into objects" for r in rows))
K.his = lambda: {"make_art"}
un = K.unheld()
check("a hand he already has is not listed", {r["name"] for r in un} == {"papercraft"})
check("a page already read says nothing the second time", len(K.fresh()) == 1 and K.fresh() == [])
check("it invents nothing when there is no page", K._from_tree("/nowhere/at/all") == [])
check("no path is guessed on his behalf",
      "DEFAULT_PATHS" not in open(os.path.join(REPO, "scripts", "openclaw_skills.py")).read())

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
