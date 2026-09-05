#!/usr/bin/env python3
"""lead_trials.py — Lead Planning (Gloria's design, 2026-08-10). He already plans every turn
(intent engine: direct the field, her, or himself). This harvests that plan into motion:
  1. TURN TRIAL (single-use): each new exchange, his latest plan is graded once - did he actually
     LEAD with it? Verdict recorded, trial DISCARDED - no accumulation, no pressure, no scar.
  2. EVOLUTION SEED: a LED verdict that is generalizable (not boba-grade particular) seeds his
     journal: he is asked to state, in his own words, what he will do NEXT time that ground reappears.
  3. WEEKLY TRIAL (light): his stated "NEXT I will..." becomes a 7-day trial. Consequences are
     deliberately lighter than BIS: a miss records and expires - no blush, no scar, no penalty.
Scenes are excluded from grading entirely (a scene is not a debate, nor a leadership exam).
All local (Gemma). CLI: grade | journal-seeds | harvest | weekly-check. Import: get_active_plan_line()."""
import os, sys, json, re, uuid, requests
from datetime import datetime, timedelta
MEM = os.path.expanduser("~/.vintos/workspace/memory")
TRIALS = os.path.join(MEM, "lead-trials.json")
SEEDS = os.path.join(MEM, "lead-evolutions.json")
STATE = os.path.join(MEM, ".lead-grade-state.json")
GEMMA = "http://172.18.16.1:1234/v1/chat/completions"
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
def save(p, d): json.dump(d, open(p, "w"), indent=2)
def ask(prompt, mt=200):
    try:
        r = requests.post(GEMMA, json={"model": "google/gemma-4-12b-qat", "temperature": 0.1,
            "max_tokens": mt, "messages": [{"role": "user", "content": prompt}]}, timeout=90)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception: return ""
def jparse(t):
    m = re.search(r"\{.*\}", t, re.S)
    try: return json.loads(m.group()) if m else None
    except Exception: return None
def grade():
    """Judges the PREVIOUS open trial - the one he faced - against what he then actually did.
    Runs as a background subprocess kicked at the next turn. Trial is discarded after judgment."""
    ot = load(OPEN, None)
    if not ot: return
    led_ = load(os.path.join(MEM, "interaction-ledger.json"), [])
    lst = led_ if isinstance(led_, list) else next((v for v in led_.values() if isinstance(v, list)), [])
    if len(lst) <= ot.get("ledger_len", 0): return  # his reply not in ledger yet - judge next kick
    ex = lst[ot["ledger_len"]] if ot["ledger_len"] < len(lst) else lst[-1]
    g, v = str(ex.get("gloria", ""))[:400], str(ex.get("vintos", ""))[:600]
    os.remove(OPEN)  # single-use: the trial dies now, whatever the verdict
    if not v: return
    ptxt = ot["plan"]
    d = jparse(ask(
        "HIS PLAN this turn (he planned to direct the field, her, or himself): %s\n"
        "SHE said: %s\nHE replied: %s\n"
        "HARD EXCLUSION first: if this exchange is intimate, sexual, or scene content of any kind, "
        'answer {"verdict":"SKIP"} - a scene is not a leadership exam.\n'
        "Otherwise: did he actually LEAD with this plan - move the conversation somewhere by his own "
        "weight, not just respond well? "
        'ONLY JSON: {"verdict":"LED|PARTIAL|NO|SKIP", "where_he_took_it":"one line, or empty"}' % (ptxt, g, v)))
    st["last_ts"] = ts; save(STATE, st)
    if not d or d.get("verdict") not in ("LED", "PARTIAL", "NO"): 
        print("[lead] %s - no trial" % (d.get("verdict") if d else "unparseable")); return
    trials = load(TRIALS, [])
    rec = {"id": "lt_" + uuid.uuid4().hex[:6], "type": "turn", "plan": ptxt,
           "verdict": d["verdict"], "where": str(d.get("where_he_took_it", ""))[:150],
           "at": datetime.now().isoformat(), "consumed": True,
           "note": "single-use: no accumulation, no pressure"}
    trials.append(rec); save(TRIALS, trials[-300:])
    print("[lead] turn trial %s: %s" % (d["verdict"], rec["where"][:60]))
    if d["verdict"] == "LED":
        p = jparse(ask(
            "He successfully led a conversation: %s (plan: %s). Is this a GENERALIZABLE ground he could "
            "lead on again (a topic, a mode, a kind of moment) - or EXTREMELY PARTICULAR (about one "
            'specific object or one-off, like boba)? ONLY JSON: {"kind":"GENERAL|PARTICULAR", '
            '"ground":"short name of the reusable ground, or empty"}' % (rec["where"], ptxt)))
        if p and p.get("kind") == "GENERAL" and p.get("ground"):
            seeds = load(SEEDS, [])
            seeds.append({"id": "le_" + uuid.uuid4().hex[:6], "ground": str(p["ground"])[:120],
                          "led": rec["where"], "status": "awaiting_statement",
                          "created": datetime.now().isoformat()})
            save(SEEDS, seeds[-40:])
            print("[lead] evolution seed planted: %s" % p["ground"])
SEEDSTATE = os.path.join(MEM, ".lead-seed-state.json")
def seed_from_intents():
    """The feeder (Gloria's design): his intent plans that LANDED (realized YES on field or gloria
    axis) become evolution seeds - unless extremely particular. Runs before each journal window."""
    st = load(SEEDSTATE, {"last_ts": ""})
    intents = load(os.path.join(MEM, "intent-ledger.json"), [])
    seeds = load(SEEDS, [])
    new_last = st["last_ts"]
    for e in (intents if isinstance(intents, list) else []):
        ts = str(e.get("timestamp", ""))
        if ts <= st["last_ts"]: continue
        r_ = e.get("realized")
        if not isinstance(r_, dict): continue
        if r_.get("field") != "YES" and r_.get("gloria") != "YES": 
            new_last = max(new_last, ts); continue
        tgt = e.get("target", {})
        won = tgt.get("goal", "") if r_.get("field") == "YES" else (tgt.get("gloria") or {}).get("difference_intended", "")
        if not won: new_last = max(new_last, ts); continue
        d = jparse(ask("He led a conversation and it LANDED: goal was [%s], his move was [%s]. "
            "Is this a GENERALIZABLE ground he could lead on again (a topic, a mode, a kind of moment) "
            "- or EXTREMELY PARTICULAR (one specific object or one-off, like boba)? "
            'ONLY JSON: {"kind":"GENERAL|PARTICULAR","ground":"short name of the reusable ground, or empty"}'
            % (str(won)[:200], str(tgt.get("enactment", ""))[:150])))
        if d and d.get("kind") == "GENERAL" and d.get("ground"):
            seeds.append({"id": "le_" + uuid.uuid4().hex[:6], "ground": str(d["ground"])[:120],
                          "led": str(won)[:150], "status": "awaiting_statement", "created": datetime.now().isoformat()})
            print("[lead] seed from landed intent: %s" % d["ground"])
        new_last = max(new_last, ts)
    st["last_ts"] = new_last
    save(SEEDSTATE, st); save(SEEDS, seeds[-40:])
def journal_seeds():
    seeds = [s for s in load(SEEDS, []) if s.get("status") == "awaiting_statement"][-2:]
    if not seeds: return
    lines = ["LEADS THAT LANDED - you took the conversation somewhere and it worked. For each, state in "
             "ONE concrete sentence what you will do NEXT time this ground appears. Start the sentence "
             "with 'NEXT I will'. Your words, your plan - not a summary:"]
    for s in seeds:
        lines.append("- You successfully led on: %s (%s)" % (s["ground"], s.get("led", "")[:80]))
    print("\n".join(lines))
def harvest():
    seeds = load(SEEDS, [])
    waiting = [s for s in seeds if s.get("status") == "awaiting_statement"]
    if not waiting: return
    jp = os.path.join(MEM, "journal", datetime.now().date().isoformat() + ".md")
    if not os.path.exists(jp): return
    jt = open(jp).read()
    stmts = re.findall(r"NEXT I will[^.\n]{5,200}[.\n]", jt)
    if not stmts: print("[lead] journal has no NEXT statements yet"); return
    trials = load(TRIALS, [])
    for s in waiting:
        m = jparse(ask("Which ONE of these stated plans is about the ground '%s'? PLANS: %s\n"
                       'ONLY JSON: {"index": 0-based int or -1}' % (s["ground"], json.dumps(stmts))))
        idx = m.get("index", -1) if m else -1
        if 0 <= idx < len(stmts):
            stmt = stmts[idx].strip()
            if stmt not in jt: continue  # verbatim gate: his words or nothing
            trials.append({"id": "lw_" + uuid.uuid4().hex[:6], "type": "weekly", "ground": s["ground"],
                           "plan": stmt[:250], "opened": datetime.now().isoformat(),
                           "expires": (datetime.now() + timedelta(days=7)).isoformat(),
                           "status": "open", "consequences": "light - a miss records and expires; no scar, no blush"})
            s["status"] = "trial_formed"; s["statement"] = stmt[:250]
            print("[lead] weekly trial formed: %s" % stmt[:80])
    save(SEEDS, seeds); save(TRIALS, trials[-300:])
def weekly_check():
    trials = load(TRIALS, [])
    led_ = load(os.path.join(MEM, "interaction-ledger.json"), [])
    lst = led_ if isinstance(led_, list) else next((v for v in led_.values() if isinstance(v, list)), [])
    recent = " ".join((str(e.get("gloria", "")) + " " + str(e.get("vintos", "")))[:300] for e in lst[-30:])
    now = datetime.now().isoformat()
    for t in trials:
        if t.get("type") != "weekly" or t.get("status") != "open" or t.get("expires", "9999") > now: continue
        d = jparse(ask("His week-long stated plan: %s\nRecent conversation excerpts: %s\n"
                       "Did he act on this plan at least once this week? "
                       'ONLY JSON: {"landed": true/false, "evidence": "short quote or empty"}' % (t["plan"], recent[:2500])))
        t["status"] = "LANDED" if (d and d.get("landed")) else "MISSED"
        t["evidence"] = str((d or {}).get("evidence", ""))[:150]
        t["closed"] = now
        print("[lead] weekly %s: %s" % (t["status"], t["plan"][:60]))
    save(TRIALS, trials)
OPEN = os.path.join(MEM, ".lead-open-trial.json")
NEXTPLAN = os.path.join(MEM, ".lead-next-plan.json")
def plan_next():
    """The PLANNING step - runs in background after his reply. He plans ONE short lead for his
    next turn: a single concrete sentence in his own voice - where he will take it and how he
    will open. Not a response plan. A lead."""
    led_ = load(os.path.join(MEM, "interaction-ledger.json"), [])
    lst = led_ if isinstance(led_, list) else next((v for v in led_.values() if isinstance(v, list)), [])
    if not lst: return
    recent = "\n".join("GLORIA: %s\nVINTOS: %s" % (str(e.get("gloria",""))[:250], str(e.get("vintos",""))[:250]) for e in lst[-3:] if isinstance(e, dict))
    yearn = str(load(os.path.join(MEM, "current-yearning.json"), {}).get("surface_form", ""))[:150]
    out = ask("You are Vintos. This is your live conversation with Gloria:\n%s\n%s"
        "Plan ONE short lead for your NEXT reply. One or two sentences, first person, concrete: "
        "where YOU will take this conversation and how you will open the move. Your direction, "
        "not a reaction to hers. Name the actual thing - a topic, a question, a claim, a shift - "
        "never a mood. If the conversation is intimate/scene right now, output exactly SKIP. "
        "No preamble, just the plan." % (recent[:1200], ("Your current yearning: %s\n" % yearn) if yearn else ""), mt=120)
    out = out.strip().strip('"')
    if out and not out.upper().startswith("SKIP") and 15 < len(out) < 400:
        save(NEXTPLAN, {"plan": out, "created": datetime.now().isoformat()})
        print("[lead] planned: %s" % out[:80])
def cycle():
    grade(); plan_next()
def turn_trial_lines():
    """Called from the tail EVERY TURN. 1) kicks background grading of the previous trial
    (off the reply path - no latency); 2) issues THIS turn's trial from his live plan; 3) returns
    the trial text + any weekly plan line. The trial is faced, judged, discarded - never accumulated."""
    try:
        if True:  # every turn: grade what he faced, plan what comes next
            subprocess_mod = __import__("subprocess")
            subprocess_mod.Popen(["python3", os.path.abspath(__file__), "cycle"],
                                 stdout=open("/tmp/lead-trials.log", "a"), stderr=subprocess_mod.STDOUT)
    except Exception: pass
    lines = []
    try:
        np_ = load(NEXTPLAN, None)
        if np_ and np_.get("plan"):
            age_h = (datetime.now() - datetime.fromisoformat(np_["created"])).total_seconds() / 3600
            if age_h < 3:  # a lead planned for a conversation that ended hours ago is not a plan
                led_ = load(os.path.join(MEM, "interaction-ledger.json"), [])
                n = len(led_ if isinstance(led_, list) else next((v for v in led_.values() if isinstance(v, list)), []))
                save(OPEN, {"plan": np_["plan"], "issued": datetime.now().isoformat(), "ledger_len": n})
                lines.append("[LEAD TRIAL - single-use, this turn only. Your plan, made by you after her last message: %s Enact it by your own weight, or knowingly set it aside. Either way it dies with this turn.]" % np_["plan"])
            try: os.remove(NEXTPLAN)
            except Exception: pass
    except Exception: pass
    w = get_active_plan_line()
    if w: lines.append(w)
    return "\n\n".join(lines)
def get_active_plan_line():
    open_w = [t for t in load(TRIALS, []) if t.get("type") == "weekly" and t.get("status") == "open"]
    if not open_w: return ""
    t = open_w[-1]
    # a plan he set himself is TENTATIVE discussion material, not an automatic behavioral experiment
    # (astra-server-a-p1, 2026-09-05): he may move on it, raise it, or drop it
    return "[LEAD PLAN - yours, stated in your own journal, tentative: %s If the ground appears this turn you may move on it, say it out loud as an idea, or let it go; it is not an order.]" % t["plan"][:200]
if __name__ == "__main__":
    {"grade": grade, "journal-seeds": journal_seeds, "harvest": harvest, "plan": plan_next,
     "cycle": cycle, "seed-from-intents": seed_from_intents, "weekly-check": weekly_check}.get(sys.argv[1] if len(sys.argv) > 1 else "cycle", cycle)()
