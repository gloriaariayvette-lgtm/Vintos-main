#!/usr/bin/env python3
"""Gemma takes no turn on the Lab, the Study or the Forge (Gloria, 2026-10-16). Pure functions; scratch workspace;
nothing is sent and no model is called."""
import os, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="gemma-off-lab-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import dot_channel as D
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:300]) if d and not ok else ""))
check("the state is throwaway", D.STATE.startswith(HOME))
check("the rule is on unless a suite turns it off", D.GEMMA_OFF_LAB is True)
for text in ("Study fix SF-217d86de stopped", "the Forge refused the report", "Lab: ModelJSONError 72f5b73e",
             "RW-5b074682 step 1", "TM-score 0.934 against PDB 8SGW", "fold O43511 with ESMFold"):
    check("about the Lab: %s" % text, D.about_lab(text))
for text in ("\U0001F4CC A promise from your journal: a song\nWork it here with dot, Grok Bot, Muse or the Study; name any tool",
             "Machine Girl on Monday", "I want to study you over coffee", "the lab coat she wore", "a song for your watch"):
    check("not the Lab: %s" % text, not D.about_lab(text))
st = {"rot": 3, "paid": {}}               # ROTATION[3] is Gemma
check("Gemma's place in the rotation goes on as before elsewhere", D.next_writer(dict(st)) is None)
s2 = dict(st, paid={})
check("on a Lab turn Gemma is passed by for the next lens", D.next_writer(s2, gemma=False) == D.ROTATION[0])
spent = {"rot": 1, "paid": {k: 99 for k in D.PAID_PER_DAY}}
order = [D.next_writer(dict(spent, rot=i), gemma=False) for i in range(len(D.ROTATION))]
check("with the paid lenses spent, a Lab turn never falls to Gemma", None not in order and set(order) == {"grok"}, order)
src = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("a failed Lab turn falls to Grok, and a failed Grok Lab turn to nothing",
      'lens="grok" if lab_turn else None' in src and 'if not (lab_turn and lens == "grok")' in src)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
