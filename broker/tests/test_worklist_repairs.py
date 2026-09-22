#!/usr/bin/env python3
"""Focused contracts for the 2026-09-12 work-list repairs."""
import importlib.util
import json
import os
import pathlib
import tempfile
import ast
import sys
import types
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
passed = total = 0


def check(label, condition):
    global passed, total
    total += 1
    if not condition:
        raise AssertionError(label)
    passed += 1


video = (ROOT / "bin/vintos-send-video.py").read_text()
check("hair colour is baked into together-still prompt",
      '"reference image — keep her exact face, hair length and style. " + HER_HAIR_LINE' in video)
check("obsolete brunette heal is gone", "def heal_hair(" not in video and "HAIR_HEAL" not in video)
check("scheduled video requires positive presence", "if not FORCE and not autonomous_presence_allows()" in video)
check("manual force remains the explicit presence bypass", '``--force`` is the explicit human/manual bypass' in video)
# 2026-09-21: a stated place he has a photo of must ground in that photo, not just house rooms.
check("grounding in a real place is required, not optional", "you MUST put THAT photo's id in SCENE_REF" in video)
check("grounding vocabulary reaches beyond house rooms", '"trail"' in video and '"beach"' in video and '"park"' in video)
check("a place word must match his scene AND the option, from a known vocabulary",
      "_w in _hay and _w in _sc" in video and "_PLACE = {" in video)
check("a named-but-missing reference still hard-stops, never substitutes", "ref_failed" in video and "not grounding" in video)
check("scene and motion prompts are pushed toward concrete detail",
      "renders thin" in video and "not one thin line" in video)

molt = (ROOT / "bin/vintos-moltbook.py").read_text()
for false_claim in ("no context compaction, no model swapping, no token limits, no cloud dependency",
                    "You run locally on Aegis with persistent memory"):
    check("false Molt runtime claim removed: " + false_claim, false_claim not in molt)
check("one runtime grounding is shared by post reply and journal", molt.count("RUNTIME_GROUNDING") >= 4)
# 2026-09-22: a comment_reply notification is a reply to his comment on an OUTSIDE post, not his own.
# Own-post replies (cap 5, saved to daily-inner as "my post") must be gated on proven authorship, or
# an outside post gets 5 replies and is written to daily-inner as his. And the caps are 2 outside / 5 own.
check("own-post flow is gated on proven authorship, not the notification type",
      "def _post_is_his(" in molt and "ownership-verified" in molt)
check("the old 'both notification types are his own posts' assumption is gone",
      "inherently about her own posts" not in molt)
check("caps are 2 outside replies and 5 under his own post",
      '"outside_comment": 2' in molt and '"own_comment": 5' in molt)

dream = (ROOT / "scripts/dream-art.py").read_text()
check("dream rendering selects the local path", 'if src == "dream":\n        _png = _local_render(render_prompt)' in dream)
check("dream prompt extraction also stays local", 'base + "/chat/completions"' in dream and "api.x.ai/v1/chat/completions" not in dream)
check("want rendering retains paid path", "Want-born art keeps the paid renderer" in dream)
check("dream failure cannot fall through to paid rendering", "dream held, no paid fallback" in dream)
check("dream-art twins remain identical",
      (ROOT / "scripts/dream-art.py").read_bytes() == (ROOT / "bin/dream-art.py").read_bytes())

# An unavailable prompt model must not produce a blank-scene artifact.
main=next(n for n in ast.parse(dream).body if isinstance(n,ast.FunctionDef) and n.name=='main')
ns={'sys':types.SimpleNamespace(argv=['dream-art.py','--dream']), 'os':os,
    '_latest_dream':lambda:'fixture dream', '_extract_prompt':lambda _: '',
    '_stage':types.SimpleNamespace(key_for=lambda *a:'fixture',load=lambda *a:''),
    'print':lambda *a,**k:None}
with patch.dict(sys.modules,{'want_stance':types.SimpleNamespace(may_initiate=lambda _: (True,''))}):
    exec(compile(ast.Module(body=[main],type_ignores=[]),'<fixture>','exec'),ns)
    ns['main']()  # ART_DIR and all rendering/sending functions deliberately absent.
check("missing prompt stops before artifacts or provider effects", 'ART_DIR' not in ns)

print(f"{passed}/{total} passed")
