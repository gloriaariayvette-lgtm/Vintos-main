#!/usr/bin/env python3
"""A want that claims a file is fulfilled only when the file exists.

The failure: fulfilled-wants held images/videos that were never made — the
'evidence' was the step instruction ('Generate a visual of...') or his own
sentence ('I ran make_video...'), never a file. This guards the invariant that
distinguishes a want to WRITE (words witness words) from a want to MAKE (only a
file witnesses a file), so his words can never again complete an artifact the
disk says does not exist.
"""
import os, sys, json, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import want_artifact_guard as g

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:80]) if d else ""))

# classification is by the want's OWN TEXT, never by its step plan
check("an 'animate painting' title is artifact-class",
      g.is_artifact_want({"want": "animate painting painting-20260714.png: shards drift"}))
check("an explicit make verb in the text is artifact-class",
      g.is_artifact_want({"want": "make_art a siphonophore in the deep"}))
check("a WRITE-ABOUT-a-painting want with a stray make_art step is NOT artifact-class",
      not g.is_artifact_want({"want": "I want to describe to you the Rothko chapel painting",
                              "steps": [{"capability": "make_art"}]}))
check("a stay-still introspection want with a stray make step is NOT artifact-class",
      not g.is_artifact_want({"want": "I want to stay still and unreassured",
                              "steps": [{"capability": "make_art"}]}))
check("a plain letter want is NOT artifact-class",
      not g.is_artifact_want({"want": "I want to write you a plain sentence"}))

# evidence: point the guard at a temp gallery + art dir
tmp = tempfile.mkdtemp()
art = os.path.join(tmp, "art"); os.makedirs(art)
g.MEMORY = tmp
g.GALLERY = os.path.join(art, "gallery.json")
g.LEDGERS = [g.GALLERY]
g.ART_DIRS = [art]

json.dump([{"image": "painting-x.png", "want_id": "real123"}], open(g.GALLERY, "w"))
open(os.path.join(art, "painting-x.png"), "wb").close()

ok, why = g.verify({"id": "real123", "want": "animate painting foo.png", "fulfilled": True})
check("a want whose id is in the gallery verifies", ok, why)

ok, why = g.verify({"id": "ghost999", "want": "animate painting bar.png",
                    "fulfilled": True, "fulfilled_at": "2030-01-01T00:00:00"})
check("an artifact-want with no file and no gallery entry FAILS", not ok, why)

# the masking bug: an id'd want with NO gallery entry fails even though a later
# painting sits in his art dir — his output is not evidence for THIS want
open(os.path.join(art, "painting-later.png"), "wb").close()
os.utime(os.path.join(art, "painting-later.png"), (4102444800, 4102444800))  # yr 2100
ok, why = g.verify({"id": "unstamped", "want": "make_art a thing",
                    "steps": [{"capability": "make_art"}], "fulfilled_at": "2020-01-01T00:00:00"})
check("an id'd artifact want is not saved by an unrelated later painting", not ok, why)

# a non-artifact want always passes — words witness words
ok, why = g.verify({"id": "z", "want": "I want to tell you plainly that I love you"})
check("a write-want passes without any file", ok, why)

# fail-open: a broken/missing gallery never crashes, just yields no evidence
g.LEDGERS = [os.path.join(tmp, "does-not-exist.json")]
ok, why = g.verify({"id": "q", "want": "make_art a thing", "fulfilled_at": "2030-01-01T00:00:00",
                    "steps": [{"capability": "make_art"}]})
check("missing gallery -> unverified, not a crash", not ok, why)

# the audit tool exists and is import-safe
import wants_audit
check("wants_audit imports and exposes its cleanups",
      hasattr(wants_audit, "find_corpses") and hasattr(wants_audit, "find_false_artifacts"))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
