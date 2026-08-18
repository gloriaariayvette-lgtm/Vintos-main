#!/usr/bin/env python3
"""subsystem_audit.py — the audit Gloria kept asking for.
A subsystem passes ONLY if its state is (a) present, (b) non-bare, (c) fresh
within its own expected cadence. Existence is not life. Velaris entries marked
SPEC are systems her tree should have per the stack document; missing = red.
Weekly cron; writes memory/subsystem-audit.md per being and prints a summary."""
import os, json, time, glob
NOW = time.time()
V = os.path.expanduser("~/.vintos/workspace/memory")
O = os.path.expanduser("~/.openclaw/workspace/memory")
def bare(p):
    try:
        if os.path.getsize(p) < 25: return True
        d = json.load(open(p))
        if d in ([], {}, "", None): return True
        if isinstance(d, dict) and all(v in ([], {}, "", None, 0, 0.0) for v in d.values()): return True
    except Exception: return False
    return False
# (name, filename-or-glob, max age hours) — cadence from each system's own design
SPEC = [
    ("LivingTrajectory", "living-trajectory.json", 12),
    ("LatentPrep(cache)", "living-trajectory.json", 12),
    ("PredictionLedger", "gloria-prediction-history.json", 12),
    ("ConfigSpace", "configuration-space.json", 72),
    ("MutualMod(field)", "mutual-modification.json", 72),
    ("ReciprocalMod", "relationship-history.json", 6),
    ("MutualSimulation", "interaction-model.json", 30),
    ("DesiredDiff/MSub", "gloria-difference.json", 72),
    ("PressureLedger", "intent-pressure.json", -1),
    ("ThreadTemp", "latent-threads.json", 24),
    ("SparkPressure", "spark-pressure-events.json", -1),
    ("SelfPressure", "self-pressure.json", 30),
    ("RelationshipPressure", "relationship-pressure.json", 30),
    ("PressureGemma", "pressure.json", 30),
    ("WithheldHead", "withheld-history.json", 6),
    ("WithheldConfirm", "withheld-history.json", 30),
    ("EmotionalReflection", "reflection-history.json", 30),
    ("EmoOperators", "emotional-state.txt", 6),
    ("GravityWells", "gravity-wells.json", 200),
    ("ConvPressure/Session", "conversation-pressure.json", 48),
    ("TensionMap", "tension-questions.json", 30),
    ("CausalSelfModel", "causal-self-model.json", 200),
    ("SelfDrift", "self-drift.json", 72),
    ("CommitmentImprint", "commitment-imprints.json", -1),
    ("ScarMap", "want-scars.json|yearning-scars.json", 400),
    ("BeliefSediment", "belief-sediment.json", 800),
    ("WorldModel", "world-state.json", 6),
    ("CuriosityDebt", "curiosity-debt.json", 48),
    ("PatternSignatures", "pattern-signatures.json", 200),
    ("Counterfactual", "counterfactual-tendencies.json", 30),
    ("RelationalGeometry", "relational-geometry.json", 200),
    ("StructuralAbsence", "absence-map.json", 400),
    ("NarrativeIdentity", "narrative-identity.json", 400),
    ("Velqan", "velqan-utterances.md", 200),
    ("BIS(trials)", "trial-ledger.json", 72),
    ("RealityEBM", "*reality*", 72),
    ("GraphMAE", "graph-gaps.json", 30),
    ("ClaimHold(fight)", "claim-hold-trials.json", -1),
    ("WantsQueue", "current-wants.json", 24),
    ("Imprints", "imprints.json", 72),
    ("BlushLedger", "blush-ledger.json", 200),
]
def newest(base, sub):
    fs = glob.glob(os.path.join(base, sub))
    return max(fs, key=os.path.getmtime) if fs else None
def audit(being, M, dreams_glob, journal_glob):
    lines, red = [], 0
    for name, fn, maxh in SPEC:
        if "|" in fn:
            p = next((os.path.join(M, x) for x in fn.split("|") if os.path.exists(os.path.join(M, x))), os.path.join(M, fn.split("|")[0]))
        else:
            p = (newest(M, fn) if "*" in fn else os.path.join(M, fn))
        if not p or not os.path.exists(p):
            if maxh == -1:
                lines.append("green  %-22s quiet (fires only on events)" % name); continue
            lines.append("RED    %-22s missing" % name); red += 1; continue
        age = (NOW - os.path.getmtime(p)) / 3600
        if maxh == -1:
            lines.append("green  %-22s event-driven, last %.0fh" % (name, age)); continue
        if bare(p):
            lines.append("RED    %-22s bare (%db)" % (name, os.path.getsize(p))); red += 1
        elif age > maxh:
            lines.append("RED    %-22s stale %.0fh (expect <%dh)" % (name, age, maxh)); red += 1
        else:
            lines.append("green  %-22s %.1fh" % (name, age))
    out = "# Subsystem audit — %s — %s\n\n" % (being, time.strftime("%Y-%m-%d %H:%M")) + "\n".join(lines) + "\n"
    open(os.path.join(M, "subsystem-audit.md"), "w").write(out)
    print("=== %s: %d/%d red ===" % (being, red, len(SPEC)))
    for l in lines:
        if l.startswith("RED"): print(" ", l)
audit("VINTOS", V, "skills/dreaming/memory/dreams/*.md", "journal/*.md")
audit("VELARIS", O, "memory/dreams/*.md", "journal/*.md")
