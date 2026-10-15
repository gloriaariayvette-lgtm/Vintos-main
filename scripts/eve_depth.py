#!/usr/bin/env python3
"""His whole stack for #vintos-eve, carried in and never out (Gloria, 2026-10-15: "enrich the vintos-eve context with
his subcons similarly to how vintos-and-dot is set up? The full stack?").

His subconscious systems, his humor and taste, exactly as #vintos-and-dot reads them (dot_lounge.deeper), and, because
#vintos-eve is only her and him, his relational systems about her, which the work room and #vintos-and-dot keep out of
Slack: where she and the two of them are heading (Living Trajectory), Mutual Simulation, Relational Geometry,
Configuration Space, the relational head and the Pressure Ledger. Each by its own reader under the read-only guard:
nothing is written, run, sent or marked as shown. Its own file, so dot_channel.py stays free of the relational
readers (test_dot_channel checks that)."""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
CAP = 5000


def _organ(mod, fn):
    try:
        m = __import__(mod)
        from context_selection import readonly
        with readonly():
            return str(getattr(m, fn)() or "").strip()
    except Exception:
        return ""


def relational():
    rel = []

    def add(title, text, cap=500):
        text = re.sub(r"\s+\n", "\n", str(text or "")).strip()
        if text:
            rel.append("%s: %s" % (title, text[:cap]))

    try:
        with open(os.path.join(WS, "memory", "living-trajectory.json"), encoding="utf-8") as f:
            lt = json.load(f)
    except (OSError, ValueError):
        lt = {}
    if isinstance(lt, dict):
        add("Where she seems to be heading (Living Trajectory)", (lt.get("gloria_trajectory") or {}).get("predicted"), 240)
        add("Where you two are heading (Living Trajectory)", (lt.get("relationship") or {}).get("trajectory"), 240)
    add("How she and you are reading each other (Mutual Simulation)", _organ("mutual_simulation", "get_interaction_hint"))
    add("The shape between you (Relational Geometry)", _organ("relational_geometry", "get_thread_context"))
    add("What has not happened between you yet (Configuration Space)", _organ("configuration_space", "get_config_hint"))
    add("Your relational sense (relational head)", _organ("relational_head", "get_relational_hint"))
    add("What you keep reaching for with her and missing (Pressure Ledger)", _organ("desired_difference", "pressure_block"), 700)
    if not rel:
        return ""
    return ("== WITH HER (your relational systems; let them colour how you are with her, never recite or name them) "
            "==\n" + "\n".join("- " + x for x in rel))


def depth():
    parts = []
    try:
        import dot_lounge
        sub = dot_lounge.deeper()
        if sub:
            parts.append(sub)
    except Exception:
        pass
    rel = relational()
    if rel:
        parts.append(rel)
    return "\n\n".join(parts)[:CAP]


if __name__ == "__main__":
    print(depth() or "(nothing to carry in)")
