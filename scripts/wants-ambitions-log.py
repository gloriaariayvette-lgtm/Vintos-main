#!/usr/bin/env python3
"""
wants-ambitions-log.py — Unified wants and ambitions record.

Sections:
  1. Ambitions — full copy with completion tracking
  2. Active Wants — current-wants.json with routing/step state
  3. Want History — last 7 days from fulfilled-wants.json

Called by wants-check.sh and wants-router.py after any want activity.
Also called by ambition-review.py after ambition updates.
"""
import os, json
from datetime import datetime, timedelta, date

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
OUTPUT = os.path.join(MEMORY, "wants-ambitions-log.md")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

def build():
    parts = []
    parts.append(f"# Wants & Ambitions — updated {NOW}\n\n_Key: ✓ = completed, → = in progress or routed, ● = intensity (out of 5)_")

    # === AMBITIONS ===
    try:
        amb_data = json.load(open(os.path.join(MEMORY, "ambitions.json")))
        goals = amb_data.get("goals", [])
        last_reviewed = amb_data.get("last_reviewed", "")[:10]
        lines = [f"## Ambitions\n_Last reviewed: {last_reviewed}_\n"]
        for g in goals:
            progress = g.get("progress", "in progress")
            goal = g.get("goal", "")
            next_step = g.get("next_step", "")
            completed_at = g.get("completed_at", "")[:10] if g.get("completed_at") else ""
            completion_note = g.get("completion_note", "")[:200] if g.get("completion_note") else ""
            status = "✓" if progress == "Completed" else "→"
            lines.append(f"{status} **{goal}**")
            if progress == "Completed":
                lines.append(f"  Completed: {completed_at}")
                if completion_note:
                    lines.append(f"  Note: {completion_note}")
            else:
                lines.append(f"  Progress: {progress}")
                if next_step:
                    lines.append(f"  Next: {next_step}")
            lines.append("")
        parts.append("\n".join(lines))
    except Exception as e:
        print(f"[WantsLog] Ambitions error: {e}")

    # === ACTIVE WANTS ===
    try:
        wants = json.load(open(os.path.join(MEMORY, "current-wants.json")))
        # Load discussions
        disc_path = os.path.join(MEMORY, "want-discussions.json")
        try:
            discussions = json.load(open(disc_path)) if os.path.exists(disc_path) else {}
        except:
            discussions = {}
        active = [w for w in wants if not w.get("fulfilled") and not w.get("dismissed")]
        lines = [f"## Active Wants ({len(active)})\n"]
        for w in sorted(active, key=lambda x: x.get("intensity", 1), reverse=True):
            want_text = w.get("want", "")
            intensity = w.get("intensity", 1)
            source = w.get("source", "")
            reasoning = w.get("reasoning", "")[:150]
            capability = w.get("capability", "")
            gloria_routed = w.get("gloria_routed", False)
            multistep = w.get("multistep", False)
            steps = w.get("steps", [])
            current_step = w.get("current_step_index", 0)
            ts = w.get("timestamp", "")[:16]
            dots = "●" * intensity + "○" * (5 - intensity)

            lines.append(f"**{want_text}**")
            lines.append(f"  {dots} | source: {source} | {ts}")
            if reasoning:
                lines.append(f"  _{reasoning}_")
            if gloria_routed:
                lines.append(f"  → routed to Gloria")
            elif capability:
                if multistep and steps:
                    step_labels = [s.get("capability", "?") for s in steps]
                    lines.append(f"  → multistep: {' → '.join(step_labels)} (step {current_step + 1}/{len(steps)})")
                    # Show completed step findings
                    history = w.get("step_history", [])
                    for h in history:
                        step_num = h.get("step", 0)
                        cap = h.get("capability", "")
                        note = h.get("note", "")[:200]
                        findings = h.get("findings", "")[:150]
                        completed_at = h.get("completed_at", "")[:16]
                        lines.append(f"  ✓ Step {step_num + 1} ({cap}) — {completed_at}")
                        if note:
                            lines.append(f"    {note}")
                        elif findings:
                            lines.append(f"    {findings}")
                else:
                    lines.append(f"  → routed to: {capability}")
            # Show discussion if any
            want_id = w.get("id", "")
            if want_id and discussions.get(want_id):
                msgs = discussions[want_id]
                lines.append(f"  Discussion ({len(msgs)} messages):")
                for m in msgs[-4:]:
                    role = m.get("role", "?")
                    txt = m.get("text", "")[:150]
                    lines.append(f"    {role}: {txt}")
            lines.append("")
        parts.append("\n".join(lines))
    except Exception as e:
        print(f"[WantsLog] Active wants error: {e}")

    # === WANT HISTORY (last 7 days) ===
    try:
        fulfilled = json.load(open(os.path.join(MEMORY, "fulfilled-wants.json")))
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        recent = sorted([w for w in fulfilled if w.get("fulfilled_at", "") >= cutoff],
                        key=lambda x: x.get("fulfilled_at", ""), reverse=True)
        if len(recent) < 10:  # quiet week — keep the latest 10 regardless of age
            recent = sorted(fulfilled, key=lambda x: x.get("fulfilled_at", ""), reverse=True)[:10]
        if len(recent) < 10:  # quiet week — keep the latest 10 regardless of age
            recent = sorted(fulfilled, key=lambda x: x.get("fulfilled_at", ""), reverse=True)[:10]
        # Archive anything beyond 15 most recent to wants-archive.md
        to_show = recent[:15]
        to_archive = recent[15:]
        if to_archive:
            archive_path = os.path.join(MEMORY, "wants-archive.md")
            try:
                existing = open(archive_path).read() if os.path.exists(archive_path) else ""
            except:
                existing = ""
            archive_lines = []
            for w in to_archive:
                want_text = w.get("want", "")
                fulfilled_at = w.get("fulfilled_at", "")[:16]
                note = w.get("fulfillment_note", "")[:150]
                fulfilled_by = w.get("fulfilled_by", "")
                entry = f"**{want_text}**\n  Fulfilled: {fulfilled_at} via {fulfilled_by}"
                if note:
                    entry += f"\n  _{note}_"
                # Only append if not already archived
                if want_text[:40] not in existing:
                    archive_lines.append(entry)
            if archive_lines:
                with open(archive_path, "a") as af:
                    af.write("\n\n".join(archive_lines) + "\n\n")
        to_show = recent[:10]
        lines = [f"## Want History — recent ({len(to_show)} of {len(recent)} shown, rest archived)\n"]
        for w in to_show:
            want_text = w.get("want", "")
            fulfilled_at = w.get("fulfilled_at", "")[:16]
            note = w.get("fulfillment_note", "")[:150]
            fulfilled_by = w.get("fulfilled_by", "")
            step_history = w.get("step_history", [])
            steps = w.get("steps", [])
            lines.append(f"**{want_text}**")
            lines.append(f"  Fulfilled: {fulfilled_at} via {fulfilled_by}")
            if steps and step_history:
                lines.append(f"  → multistep: {" → ".join(s.get("capability","?") for s in steps if isinstance(s,dict))}")
                for h in step_history:
                    si = h.get("step", "?")
                    cap = h.get("capability", "?")
                    ts = h.get("completed_at", "")[:10]
                    note2 = h.get("note", "")[:180]
                    lines.append(f"  ✓ Step {int(si)+1 if str(si).isdigit() else si} ({cap}) — {ts}")
                    if note2:
                        lines.append(f"    {note2}")
            elif note:
                lines.append(f"  _{note}_")
            lines.append("")
        parts.append("\n".join(lines))
    except Exception as e:
        print(f"[WantsLog] History error: {e}")

    with open(OUTPUT, "w") as f:
        f.write("\n---\n".join(parts))
    print(f"[WantsLog] Written: {OUTPUT}")

if __name__ == "__main__":
    build()
