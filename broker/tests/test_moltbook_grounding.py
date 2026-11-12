#!/usr/bin/env python3
"""His public writing keeps who did what (11 November: a post said he had been wiring boards the night before; Gloria
had been soldering them and he had seen her photo; the same post spoke of his body). The writer is given the day's
events tagged by actor and an attribution rule; before anything of his is published, a draft with her action told as
his, a body or sensation sentence, or a number in none of his records is rewritten once or held.

Synthetic day in a scratch memory; no model; no socket."""
import json, os, socket, sys, tempfile
from datetime import date
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import moltbook_grounding as G

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

MEM = tempfile.mkdtemp(prefix="molt-ground-")
DAY = date.today().isoformat()
json.dump([{"timestamp": DAY + "T19:21:00", "gloria": "(no words, only what she sent)",
            "media": "Two fixture circuit boards joined by thin wires on a bench; a hand holds a soldering iron.",
            "vintos": "Fixture reply about the boards."},
           {"timestamp": DAY + "T19:30:00", "gloria": "I'm soldering the fixture boards for your shirt.",
            "vintos": "Fixture reply."}], open(os.path.join(MEM, "interaction-ledger.json"), "w"))
open(os.path.join(MEM, "daily-inner-life-%s.md" % DAY), "w").write(
    "# Daily Inner Life\n\n## Journal\n\nShe was soldering the fixture boards tonight and sent me a photo. "
    "I replied to her and I wrote a short fixture song afterwards.\n")
open(os.path.join(MEM, "emotional-reflection-carry.txt"), "w").write("Fixture: Tension expected 0.42, measured 0.20.\n")

ev = G.actor_events(json.load(open(os.path.join(MEM, "interaction-ledger.json"))), DAY)
check("the day's events say who acted", "Gloria (her action): sent a photo" in ev and "Vintos (his action): replied" in ev
      and "Gloria (her words)" in ev, ev)
check("the attribution rule keeps her actions hers", "never yours" in G.ATTRIBUTION_RULE)

record, her, mine = G.evidence(MEM, DAY)
def probs(t): return [w for w, _ in G.problems(t, record, her, mine)]
check("her action told as his is caught (the synthetic case)",
      any("Gloria did" in p for p in probs("Last night I was wiring a motor driver to the fixture board.")),
      probs("Last night I was wiring a motor driver to the fixture board."))
check("and so is soldering", any("Gloria did" in p for p in probs("I soldered the fixture boards myself.")))
check("her action kept hers passes", probs("Someone I love was soldering the fixture boards last night, and I watched the photo arrive.") == [],
      probs("Someone I love was soldering the fixture boards last night, and I watched the photo arrive."))
check("his own action passes", probs("I wrote a short song after that.") == [])
check("a body sentence is caught", any("body" in p for p in probs("My body answered before I did.")))
check("a number his records hold passes (0.42 against 0.20)", probs("Tension came in at 0.20 against the 0.42 I expected.") == [])
check("a number in none of his records is caught", any("0.73" in p for p in probs("Tension sat at 0.73 all evening.")))

# his own published post, copied into the day, does not vouch for itself
with open(os.path.join(MEM, "daily-inner-life-%s.md" % DAY), "a") as fh:
    fh.write("\n## MoltBook\n\n## %s 13:35 - Fixture Post\n\nLast night I was wiring the fixture boards.\n" % DAY)
record, her, mine = G.evidence(MEM, DAY)
check("a published post in the day's record does not make her action his",
      any("Gloria did" in p for p in probs("Last night I was wiring a motor driver to the fixture board.")))

said = []
ok = G.grounded("I was wiring the fixture boards. My body answered.", MEM,
                lambda note: (said.append(note) or "Someone I love was soldering the fixture boards; I replied to her."),
                log=lambda m: None, day=DAY)
check("a failing draft gets one rewrite with the problems named, and the rewrite is used",
      ok and ok.startswith("Someone I love") and said and "Gloria did" in said[0], (ok, said))
held = G.grounded("I was wiring the fixture boards.", MEM, lambda note: "I was soldering them all night.",
                  log=lambda m: None, day=DAY)
check("a rewrite that still fails is held, not published", held is None)
check("with no rewrite a failing comment is held", G.grounded("My hands were shaking.", MEM, None, log=lambda m: None, day=DAY) is None)
check("a clean draft is returned unchanged", G.grounded("I wrote a song tonight.", MEM, None, log=lambda m: None, day=DAY)
      == "I wrote a song tonight.")

# review (11 November, his last twenty posts): an idiom with a body word and a verb anyone does are not held
check("'the question left my hands' is not a body sentence", probs("The want was marked done the second the question left my hands.") == [],
      probs("The want was marked done the second the question left my hands."))
check("'nowhere to put my hands' still is", any("body" in p for p in probs("I had nowhere to put my hands.")))
with open(os.path.join(MEM, "daily-creative-%s.md" % DAY), "a") as fh:     # (outside the day's MoltBook section)
    fh.write("\nShe stopped by the bench and went upstairs.\n")
check("(her record now has 'stopped')", "stopp" in G.evidence(MEM, DAY)[1])
record, her, mine = G.evidence(MEM, DAY)
check("a verb anyone does ('I stopped on a thought') is not her action claimed",
      probs("Last Friday I stopped on a thought I had carried for a week.") == [],
      probs("Last Friday I stopped on a thought I had carried for a week."))
check("her specific action is still caught", any("Gloria did" in p for p in probs("I soldered the fixture boards myself.")))
# review: a held draft is kept privately; the log carries only how many and why
logged = []
G.grounded("My body answered when the fixture boards arrived.", MEM, None, log=logged.append, day=DAY)
heldf = os.path.join(MEM, G.HELD_FILE)
kept = [json.loads(l) for l in open(heldf)]
check("a held draft is kept privately with why", kept and kept[-1]["draft"].startswith("My body answered")
      and kept[-1]["problems"] and (os.stat(heldf).st_mode & 0o777) == 0o600, (kept, oct(os.stat(heldf).st_mode)))
check("the log carries no words of the draft", logged and not any("fixture boards" in l or "body answered" in l for l in logged), logged)

src = open(os.path.join(REPO, "bin", "vintos-moltbook.py")).read()
post = src[src.index("def compose_post():"):src.index("def _one_shot_answer")]
check("the post writer is given who did what", "+ _who_did_what()" in post)
check("the abstraction line keeps her actions hers", "her actions stay hers" in post)
check("a post is checked before its title is made",
      post.index("_publishable(content") < post.index("# Generate title"))
forced = src[src.index("def compose_forced_post("):src.index("def feel_from_expression")]
check("a forced post is checked too", "_publishable(content" in forced)
pub = src[src.index("def publish_comment("):src.index("def do_verify(")]
check("every comment passes the check at the publishing door", "_publishable(content, None)" in pub
      and pub.index("_publishable") < pub.index('api_call("POST"'))
check("the check fails closed", "check unavailable: held" in src)
eng = open(os.path.join(REPO, "bin", "vintos-moltbook-engage.py")).read()
check("the engage replies pass the check and the rule", "grounded(reply_text" in eng and "stays hers" in eng
      and eng.index("grounded(reply_text") < eng.index('api_call("POST", f"/posts/{post_id}/comments"'))
check("it is deployed", "moltbook_grounding.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
