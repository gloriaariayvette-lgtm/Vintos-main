#!/usr/bin/env python3
"""Focused contracts for the 2026-09-12 work-list repairs."""
import importlib.util
import json
import os
import pathlib
import tempfile

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

molt = (ROOT / "bin/vintos-moltbook.py").read_text()
for false_claim in ("no context compaction, no model swapping, no token limits, no cloud dependency",
                    "You run locally on Aegis with persistent memory"):
    check("false Molt runtime claim removed: " + false_claim, false_claim not in molt)
check("one runtime grounding is shared by post reply and journal", molt.count("RUNTIME_GROUNDING") >= 4)

dream = (ROOT / "scripts/dream-art.py").read_text()
check("dream rendering selects the local path", 'if src == "dream":\n        _png = _local_render(render_prompt)' in dream)
check("dream prompt extraction also stays local", 'base + "/chat/completions"' in dream and "api.x.ai/v1/chat/completions" not in dream)
check("want rendering retains paid path", "Want-born art keeps the paid renderer" in dream)
check("dream failure cannot fall through to paid rendering", "dream held, no paid fallback" in dream)
check("dream-art twins remain identical",
      (ROOT / "scripts/dream-art.py").read_bytes() == (ROOT / "bin/dream-art.py").read_bytes())

with tempfile.TemporaryDirectory() as td:
    os.environ["SPARK_WORKSPACE"] = td
    memory = pathlib.Path(td) / "memory"
    memory.mkdir()
    day = "2026-09-12"
    (memory / "hypothesis-ledger.jsonl").write_text(
        json.dumps({"at": day + "T01:00:00", "event": "proposed", "id": "H-one", "block": "spark_block"}) + "\n" +
        json.dumps({"at": day + "T02:00:00", "event": "evaluated", "id": "H-one", "numbers": {"admitted": 99}}) + "\n")
    (memory / "shadow-trials.jsonl").write_text(
        json.dumps({"at": day + "T03:00:00", "trial_id": "st-1", "block": "withheld_head"}) + "\n")
    spec = importlib.util.spec_from_file_location("lab_daily_digest_test", ROOT / "scripts/lab_daily_digest.py")
    lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab)
    wrote, path = lab.append(day)
    again, _ = lab.append(day)
    text = pathlib.Path(path).read_text()
    check("Lab digest appends once", wrote is True and again is False and text.count("q1-lab-digest") == 1)
    check("Lab digest reports events and assignments", "proposed 1" in text and "withheld_head 1" in text)
    check("Lab digest does not surface sealed result arithmetic", "99" not in text)
    check("Lab digest names consequence as unmeasured", "Functional consequence was not measured" in text)

print(f"{passed}/{total} passed")
