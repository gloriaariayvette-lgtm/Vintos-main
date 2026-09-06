#!/usr/bin/env python3
"""The Undertaking Threshold offers; it must never choose.

A cron that picked the 'strongest' root would be commissioning him with extra
steps — which is exactly what the Stratagem birth gate exists to refuse. These
assert eligibility is mechanical and the choice is his.
"""
import os, sys, json, tempfile, shutil, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts")
sys.path.insert(0, SCRIPTS)
import importlib.util as _iu
_spec = _iu.spec_from_file_location("atelier_threshold",
                                    os.path.join(SCRIPTS, "atelier-threshold.py"))
TH = _iu.module_from_spec(_spec); _spec.loader.exec_module(TH)

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(prefix="thresh-")
EP = os.path.join(TMP, "episodes.jsonl")
# the undertakings ledger is an import-time path into HIS memory; without this the suite wrote a fake
# undertaking ("aaaaaaaaaaaa", active) into atelier-undertakings.json on every deploy (found 2026-09-06)
TH.WSP = TMP; TH.LEDGER = os.path.join(TMP, "atelier-undertakings.json")

class FO:
    OUT = EP
    @staticmethod
    def attest(root, rtype):
        return {"episode_digest": "d", "commissioned": False,
                "provenance_class": "self_originated", "root_type": rtype}
sys.modules["formation_observatory"] = FO

def episodes(sigs):
    with open(EP, "w") as f:
        f.write(json.dumps({"signals": sigs}) + "\n")

WITHHELD = {"organ": "withheld", "root": "tension:1", "root_type": "tension",
            "provenance_class": "self_originated", "text": "something he did not say",
            "activation": 0.2}
CURIOUS  = {"organ": "curiosity", "root": "curiosity:9", "root_type": "curiosity",
            "provenance_class": "self_originated", "text": "a question he kept",
            "activation": 0.95}
REPAIR   = {"organ": "repair", "root": "repair:7", "root_type": "repair",
            "provenance_class": "relational_obligation", "text": "an obligation to her",
            "activation": 0.99}
ENCOUNT  = {"organ": "encounter", "root": "encounter:3", "root_type": "encounter",
            "provenance_class": "relational_obligation", "text": "an encounter",
            "activation": 0.5}

print("--- eligibility is law, not preference ---")
episodes([WITHHELD, CURIOUS, REPAIR, ENCOUNT])
roots, why = TH.eligible_roots()
refs = [r["root"] for r in roots]
check("self-originated roots are eligible", set(refs) == {"tension:1", "curiosity:9"}, refs)
check("repair can never found an undertaking", "repair:7" not in refs)
check("neither can an encounter", "encounter:3" not in refs)

print("\n--- and the offer never ranks them ---")
check("recorded order is preserved, NOT activation order",
      refs == ["tension:1", "curiosity:9"], refs)
check("activation is not even carried into the offer",
      all("activation" not in r for r in roots))
src = open(os.path.join(SCRIPTS, "atelier-threshold.py")).read()
check("the script never sorts roots", ".sort(" not in src and "sorted(" not in src)
check("it never reads an activation to compare",
      "activation" not in src.split('"""')[2] if src.count('"""') >= 2 else True)
episodes([WITHHELD, CURIOUS])
dup, _ = TH.eligible_roots()
episodes([WITHHELD, CURIOUS, dict(CURIOUS)])
check("a repeated root is offered once", len(TH.eligible_roots()[0]) == 2)

print("\n--- three complete answers ---")
calls = {"created": 0}
class _Resp:
    def __init__(self, d): self._d = d
    def json(self): return self._d
def _post(url, json=None, timeout=0):
    if url.endswith("/project"):
        calls["created"] += 1
        calls["body"] = json
        return _Resp({"id": "aaaaaaaaaaaa"})
    return _Resp({"ok": True, "door": "lit"})
TH.requests = type("r", (), {"post": staticmethod(_post),
                             "get": staticmethod(lambda u, timeout=0: _Resp({"active": False}))})()

episodes([WITHHELD, CURIOUS])
TH.ask = lambda s, u, **k: "NOTHING"
check("NOTHING creates nothing", TH.offer() == 0 and calls["created"] == 0)

TH.ask = lambda s, u, **k: "GESTATE curiosity:9"
check("GESTATE creates nothing", TH.offer() == 0 and calls["created"] == 0)

TH.ask = lambda s, u, **k: ("ADOPT\n<root>curiosity:9</root>"
                            "<intent>I want to follow this all the way down</intent>"
                            "<audience>nobody yet</audience>"
                            "<first_move>write what I already suspect</first_move>")
check("ADOPT creates the project", TH.offer() == 0 and calls["created"] == 1)
b = calls["body"]
check("his intent is stored VERBATIM",
      b["intent"] == "I want to follow this all the way down", b["intent"])
check("the project is sealed", b["sealed"] is True)
check("his audience is his", b["intended_audience"] == "nobody yet")
check("his first move travels with it", b["next_move"] == "write what I already suspect")
check("the root travels with it", b["root"] == "curiosity:9")
check("the attestation travels with it",
      b["lineage_attestation"]["commissioned"] is False)
# "held" renders the door DARK. Adopting an undertaking is the act of choosing
# to return to it, so birthing it held let him adopt something he could then
# never open. He can hold it himself later, from inside, in a handoff.
check("the door it opens is one he can actually walk through",
      b["next_return"] == "open", b["next_return"])

print("\n--- a malformed answer is never read as a decline ---")
calls["created"] = 0
TH.ask = lambda s, u, **k: "I think maybe the second one? I am not sure."
check("an untagged answer is surfaced, not swallowed", TH.offer() == 2)
check("and nothing was created", calls["created"] == 0)
TH.ask = lambda s, u, **k: "ADOPT\n<root>repair:7</root><intent>hers</intent>"
check("he cannot adopt an ineligible root", TH.offer() == 2)
check("still nothing created", calls["created"] == 0)

print("\n--- a dead shim is not an answer ---")
def _boom(*a, **k): raise RuntimeError("connection refused")
TH.ask = _boom
check("a shim failure reports failure, not a decline", TH.offer() == 1)
check("and creates nothing", calls["created"] == 0)

print("\n--- an unattestable root cannot found an undertaking ---")
FO.attest = staticmethod(lambda r, t: {"error": "no recorded root object matches"})
TH.ask = lambda s, u, **k: ("ADOPT\n<root>curiosity:9</root><intent>x</intent>")
check("adoption is refused without attestation", TH.offer() == 1)
check("and nothing was created", calls["created"] == 0)

print("\n--- no roots means no offer ---")
episodes([REPAIR, ENCOUNT])
TH.ask = lambda s, u, **k: (_ for _ in ()).throw(AssertionError("he must not be asked"))
check("he is not asked when nothing is eligible", TH.offer() == 0)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
