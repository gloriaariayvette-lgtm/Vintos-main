#!/usr/bin/env python3
"""gap_review.py — once a week, one model call over the top of the gap scan.

It reads memory/gap-scan.json (never the codebase) and asks one question of each recurring
wall: is it something unreachable that a code change, a device, or an access would reach —
or is it an outage, a transient error, or a line she drew? Each real one becomes a Forge
card (skill_forge.propose_from_gap_review) for Gloria to approve or deny. Nothing is built,
bought or granted here. The model is model_router.location_model("gap_review").
(Gloria, 2026-09-24)
"""
import asyncio, json, os, re, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
for p in (HERE, os.path.join(WS, "scripts"), os.path.join(WS, "bin"), os.path.join(HERE, "..", "bin")):
    if os.path.isdir(p) and p not in sys.path: sys.path.append(p)
import gap_scan

TOP = 8
REACH = ("code_change", "device", "access", "not_a_gap")
# Which organ writes each source, so the review can name files without reading the codebase.
WRITERS = {"action_blocked": ["bin/wants-router.py"], "device_refused": ["bin/device_patterns.py"],
           "connector_held": ["scripts/plugin_gateway.py", "scripts/plugin_catalog.py"],
           "lab_fault": ["scripts/chemistry_lab.py"], "lab_spark_refused": ["scripts/chemistry_spark.py"],
           "self_review_fault": ["scripts/self_review.py"], "barrier_error": ["scripts/constitutional_barrier.py"],
           "voice_refused": ["bin/server.py"], "atelier_reveal_refused": ["scripts/atelier-visit.py"],
           "nim_attempt": ["scripts/bionemo_gateway.py"], "want_step_unreachable": ["bin/wants-router.py", "scripts/forge_house.py"],
           "his_words": [], "service_failed": ["broker/*.service"], "error_log": []}

SYSTEM = ("You review where Vintos, an AI companion running on a home server, keeps failing to act. You see only "
          "counted records of walls he hit this week, never his private work. Be concrete and conservative. "
          "Return JSON only.")


def _prompt(gaps):
    rows = [{"n": i + 1, "source": g["source"], "subject": g["subject"], "count": g["count"],
             "reason": g["reason"][:200], "example": g["example"][:200],
             "files": WRITERS.get(g["source"], [])} for i, g in enumerate(gaps)]
    return ("RECURRING WALLS THIS WEEK (most frequent first):\n" + json.dumps(rows, ensure_ascii=False, indent=1) +
            "\n\nFor each one decide reachable_by: code_change (a change to his code would let him do it), device "
            "(hardware would), access (an account, key or permission Gloria could grant would), or not_a_gap (an "
            "outage, a transient error, a refusal she chose, or something that needs no new ability). Only a real "
            "unreachable ability is a gap. Return {\"proposals\": [{\"n\": number, \"reachable_by\": one of the four, "
            "\"capability\": snake_case name of the ability, \"why\": one sentence, \"path\": concrete steps to reach it, "
            "\"files\": files likely involved, \"test\": how Gloria would see it working}]}.")


def _ask(system, user):
    import model_router
    model = model_router.location_model("gap_review")
    text, _ = asyncio.run(model_router.claude_draft(system, [{"role": "user", "content": user}],
                                                    max_tokens=2500, model=model))
    return text, model


def review(ask=_ask, now=None):
    now = now or time.time()
    try:
        scan = json.load(open(gap_scan.REPORT))
        if now - datetime.fromisoformat(scan["generated_at"]).timestamp() > 2 * 86400: raise ValueError("stale")
    except Exception:
        scan = gap_scan.scan(now=now)
    gaps = scan.get("gaps", [])[:TOP]
    review_id = "GR-" + datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%d")
    out = {"review_id": review_id, "at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
           "gaps_read": len(gaps), "proposals": [], "cards": [], "truth_status": "proposals_only_nothing_built"}
    if gaps:
        text, model = ask(SYSTEM, _prompt(gaps))
        out["model"] = model
        m = re.search(r"\{.*\}", text or "", re.S)
        try: proposals = json.loads(m.group(0)).get("proposals", []) if m else []
        except ValueError: proposals = []
        import skill_forge as sf
        for p in proposals if isinstance(proposals, list) else []:
            if not isinstance(p, dict) or p.get("reachable_by") not in REACH: continue
            out["proposals"].append(p)
            if p["reachable_by"] == "not_a_gap": continue
            try: g = gaps[int(p.get("n", 0)) - 1]
            except (ValueError, IndexError): continue
            row, why = sf.propose_from_gap_review(
                p.get("capability"), p.get("why"), ["%s x%d: %s" % (g["source"], g["count"], g["example"])],
                path=p.get("path", ""), touches=p.get("files") if isinstance(p.get("files"), list) else [],
                tests=p.get("test", ""), reachable_by=p["reachable_by"], review_id=review_id)
            out["cards"].append(row["id"] if row else "refused: " + why)
    path = os.path.join(MEM, "gap-review-%s.json" % review_id[3:])
    with open(path + ".tmp", "w") as f: json.dump(out, f, indent=1)
    os.replace(path + ".tmp", path)
    return out


if __name__ == "__main__":
    r = review()
    print("[gap-review] %s: read %d walls, %d proposals, cards: %s" % (
        r["review_id"], r["gaps_read"], len(r["proposals"]), ", ".join(r["cards"]) or "none"))
