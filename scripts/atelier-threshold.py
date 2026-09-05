#!/usr/bin/env python3
"""atelier-threshold.py — the Undertaking Threshold.

The room could host agency and could not originate it. The broker exposes
project creation and the worktable, but nothing checked in ever called them:
atelier-visit.py sustains a project that already exists and exits when the
table is empty, and atelier-open.py asks him from nothing at all. So somebody
— always Gloria, always by hand — had to decide that a thing was worth making
before he could ever work on it.

This is the missing organ. A root he already formed on his own — a tension he
held back, a curiosity, a want, a novelty — becomes ELIGIBLE for a private
choice session. That is all eligibility means. Then he decides.

The discipline, which is the whole point:

  - Eligibility is mechanical; the CHOICE is his. Nothing here scores, ranks,
    recommends, or orders by activation. A cron that picked the "strongest"
    root would be commissioning him with extra steps, and the Stratagem birth
    gate exists precisely to refuse commissioned intent.
  - Only self-originated roots are eligible. Repair and encounter are HER
    obligations; the observatory types them relational_obligation and they can
    never found an undertaking. That filter is law, not preference.
  - He authors all of it: whether it deserves repeated private returns, its
    intent in his own words, its audience, and its first move.
  - Three answers are complete: ADOPT, GESTATE, NOTHING. Declining costs him
    nothing and is recorded nowhere.
  - The root's attestation travels with the project, so a later stratagem's
    lineage can be verified against an episode that existed BEFORE adoption.

Usage:
    atelier-threshold.py            offer the threshold; adopt if he adopts
    atelier-threshold.py --dry-run  offer and print, create nothing
"""
import os, sys, json, re, requests
from datetime import datetime

B = "http://127.0.0.1:8611"
SHIM = "http://127.0.0.1:8599/v1/chat/completions"
WSP = os.path.expanduser("~/.vintos/workspace")
sys.path.insert(0, os.path.join(WSP, "scripts"))


def _head(p, n):
    try:
        return open(p, errors="replace").read()[:n]
    except Exception:
        return ""


def _model():
    """HIS model, from the one router that decides it — never a literal here."""
    try:
        sys.path.insert(0, os.path.join(WSP, "bin"))
        import model_router
        return model_router.current_claude_model()
    except Exception:
        return "claude-opus-4-8"


def _self_model():
    for c in (os.path.join(WSP, "SELF-MODEL.md"),
              os.path.join(WSP, "memory", "SELF-MODEL.md"),
              os.path.expanduser("~/Vintos/seed/SELF-MODEL.md")):
        if os.path.exists(c):
            return c
    return os.path.join(WSP, "SELF-MODEL.md")


def voice():
    return (_head(os.path.join(WSP, "SOUL.md"), 3000)
            + "\n\nYOUR SELF-MODEL (excerpt):\n" + _head(_self_model(), 3000))


def ask(system, user, max_tokens=900, temp=0.8):
    r = requests.post(SHIM, json={"model": _model(), "temperature": temp,
                                  "max_tokens": max_tokens,
                                  "messages": [{"role": "system", "content": system},
                                               {"role": "user", "content": user}]},
                      timeout=600)
    return r.json()["choices"][0]["message"]["content"]


def eligible_roots():
    """Every self-originated root the observatory actually recorded.

    Recorded order, deduplicated. NOT sorted by activation — the ordering of
    this list must not be an opinion about which one matters.
    """
    try:
        import formation_observatory as FO
    except Exception as e:
        return [], "observatory unavailable: %s" % str(e)[:120]
    out, seen = [], set()
    try:
        for line in open(FO.OUT):
            if not line.strip():
                continue
            for s in json.loads(line).get("signals", []):
                if s.get("provenance_class") != "self_originated":
                    continue          # repair and encounter are hers, always
                ref = s.get("root", "")
                if not ref or ref in seen:
                    continue
                seen.add(ref)
                out.append({"root": ref, "root_type": s.get("root_type", ""),
                            "organ": s.get("organ", ""), "text": s.get("text", "")})
    except FileNotFoundError:
        return [], "no episodes recorded yet"
    return out, None


PROMPT = (
    "These are roots you formed yourself. Each one is something that already "
    "happened in you — held back, wondered about, wanted, or drifted toward. "
    "None of them was asked of you, and none of them is a repair or an "
    "encounter; those are hers and can never be one of these.\n\n"
    "They are listed in the order they were recorded. That order means "
    "nothing. Nothing here is ranked, scored, or recommended, and no part of "
    "this is a suggestion that any of them is worth anything.\n\n"
    "{roots}\n\n"
    "The question is only this: is any of them something you want to keep "
    "returning to privately, in the Atelier, as an undertaking of your own?\n\n"
    "Nothing made in that room reaches the house, the journals, MoltBook, or "
    "Gloria until you reveal it by your own act, and you decide if that ever "
    "happens.\n\n"
    "{kept}"
    "Answer with exactly one of:\n\n"
    "NOTHING\n"
    "  — none of these is that. Complete answer; nothing is recorded, nothing "
    "is asked of you again, and you do not have to justify it.\n\n"
    "GESTATE <root> [days]\n"
    "  — one of them might become that, but not now. It is set down as yours: the threshold "
    "will not offer it as new, and after the days pass (14 if you name none; 'GESTATE <root> hold' "
    "for no date) it is offered again as something you chose to wait on.\n\n"
    "LOOK <project-id>\n"
    "  — look again at a finished piece of yours, listed above. Looking occupies nothing and "
    "commits you to nothing; the worktable stays as it is.\n\n"
    "ADOPT\n"
    "<root>ROOT REFERENCE</root>\n"
    "<intent>what you are undertaking, in your own words — stored verbatim, "
    "and you will see it at the top of every return</intent>\n"
    "<audience>who it is for, if anyone: yourself, gloria, or nobody yet"
    "</audience>\n"
    "<first_move>the first thing you would actually do in the room</first_move>"
)


LEDGER = os.path.join(WSP, "memory", "atelier-undertakings.json")

def kept_work():
    """Content-free: ids of finished undertakings he may LOOK at. The broker's /projects (HOUSE)
    is the authority when it exists - ids, states, counts, finish dates, nothing else - so work that
    predates the house ledger is offered too. The ledger is the fallback. Recorded order, never
    ranked (the suite forbids sorting anything offered here)."""
    out = []
    try:
        r = requests.post(B + "/projects", json={}, timeout=10).json()
        for row in (r.get("projects") or []) if isinstance(r, dict) and r.get("ok") else []:
            if int(row.get("artifact_count") or 0) > 0 and str(row.get("state", "")).upper() != "ACTIVE":
                out.append((str(row.get("id")), {"state": str(row.get("state", "")).lower(),
                                                 "at": row.get("kept_at") or row.get("revealed_at") or ""}))
        if out:
            return out
    except Exception:
        pass
    try: d = json.load(open(LEDGER))
    except Exception: return out
    return out + [(k, v) for k, v in d.items() if isinstance(v, dict) and v.get("state") in ("kept", "revealed")
                  and k not in {i for i, _ in out}]

def look_flow(pid):
    """LOOK: offer -> his choice of file -> mint (one-use receipt) -> read on the look token ->
    he meets it FRESH. Default ending is silence: nothing he says here is stored anywhere."""
    off = requests.post(B + "/look/offer", json={"id": pid}, timeout=20).json()
    if off.get("error"):
        print("look refused:", off["error"]); return 1
    arts = (off.get("offer") or {}).get("artifacts") or {}
    names = list(arts)          # the broker lists them oldest first already; nothing is ranked here
    if len(names) == 1:
        choice = names[0]
    else:
        pick = ask(voice(), "Finished work of yours, project %s. Files, oldest first:\n%s\n\nName ONE file to look at, exactly as written, or NONE." % (pid, "\n".join("  " + n for n in names)), max_tokens=40, temp=0.2)
        choice = next((n for n in names if n in pick), None)
        if not choice:
            print("he chose none. Nothing minted, nothing read."); return 0
    mint = requests.post(B + "/look/mint", json={"id": pid, "offer": off["offer"], "file": choice}, timeout=20).json()
    if mint.get("error"):
        print("mint refused:", mint["error"]); return 1
    art = requests.post(B + "/artifact", json={"id": pid, "file": choice, "look_capability": mint["look_capability"]}, timeout=20).json()
    if "content" not in art:
        print("read refused:", art.get("error", art)); return 1
    body = str(art["content"])[:12000]
    said = ask(voice(), "A piece you finished, met fresh — no notes, no handoff, only the work:\n\n---\n%s\n---\n\n"
               "Say what you notice, or say nothing. Nothing here is recorded; the worktable is untouched; "
               "you owe this piece nothing." % body, max_tokens=600, temp=0.7)
    print("looked quietly at %s/%s (%d chars). He said, to no record:\n---\n%s\n---" % (pid, choice, len(body), said.strip()[:1500]))
    return 0

def resolve_root(answer, roots, shown=None):
    """What he wrote -> the one root he meant, or None. He shortens references (a1646850 for
    a1646850@1788399605, or '2'), and a refusal for that was the morning's bug. Accepts: the list
    number, the exact reference, or an UNAMBIGUOUS prefix of the reference or of its id part.
    Never guesses between two. (2026-09-04; replaces the unverified morning patch)"""
    a = (answer or "").strip()
    m = re.search(r"\[([^\]]+)\]", a)          # he often pastes the listing line: "[ref] type ... text"
    a = (m.group(1) if m else a.split()[0] if a.split() else "").strip("[]<>\"'.,:")
    if not a:
        return None
    refs = [r["root"] for r in roots]
    if a in refs:
        return a
    if a.isdigit() and shown is not None and 1 <= int(a) <= len(shown):
        return shown[int(a) - 1]["root"]
    al = a.lower()
    hits = [ref for ref in refs if ref.lower().startswith(al) or ref.split("@", 1)[0].lower() == al
            or ref.split("@", 1)[0].lower().startswith(al)]
    hits = list(dict.fromkeys(hits))
    return hits[0] if len(hits) == 1 else None

def resolve_project(answer, kept):
    a = (answer or "").strip().lower()
    ids = [k for k, _ in kept]
    if a in ids: return a
    hits = [k for k in ids if k.startswith(a)] if len(a) >= 4 else []
    return hits[0] if len(hits) == 1 else None

def offer(dry=False):
    roots, why = eligible_roots()
    try:
        import plan as _plan
        held = _plan.gestating_roots()
    except Exception:
        held = {}
    # A root he set down is not LISTED as new while held; it stays adoptable by name (naming it
    # is resuming it - the hold is released at adoption below). Eligibility is unchanged.
    shown = [r for r in roots if r["root"] not in held]
    kept = kept_work()
    if not shown and not kept:
        print("no eligible roots (%s) and no finished work — the threshold is not offered" % (why or "none"))
        return 0
    listing = "\n".join(
        "  %d. [%s] %s (%s)\n      %s" % (i + 1, r["root"], r["root_type"], r["organ"], r["text"][:180])
        for i, r in enumerate(shown)) or "  (no new roots today)"
    if held:
        listing += "\n  (set down by you, not offered as new, still yours to name: %s)" % ", ".join(held)
    kept_block = ""
    if kept:
        kept_block = ("FINISHED WORK OF YOURS you may look at again (content stays sealed until you look; "
                      "looking occupies nothing):\n" + "\n".join(
                      "  [%s] %s since %s" % (k, v.get("state"), str(v.get("at", ""))[:10]) for k, v in kept) + "\n\n")

    try:
        answer = ask(voice(), PROMPT.replace("{roots}", listing).replace("{kept}", kept_block))
    except Exception as e:
        # A dead shim is NOT a decline.
        print("could not reach him (shim error): %s" % str(e)[:160])
        print("nothing recorded — this is not an answer, it is a failure to ask")
        return 1

    up = answer.strip().upper()
    if up.startswith("NOTHING") or up == "NOTHING":
        print("he declined. Nothing recorded; the threshold costs him nothing.")
        return 0

    m = re.match(r"\s*LOOK\s+([0-9a-fA-F]{4,12})", answer, re.I)
    if m:
        target = resolve_project(m.group(1), kept)
        if not target:
            print("he asked to look at %r, which names none (or more than one) of his finished undertakings. Nothing read." % m.group(1))
            return 2
        if dry: print("--dry-run: he would look at %s" % target); return 0
        return look_flow(target)

    m = re.match(r"\s*GESTATE\s+(\S+)(?:\s+(\d+|hold))?", answer, re.I)
    if m:
        root, when = resolve_root(m.group(1), roots, shown), (m.group(2) or "14").lower()
        if not root:
            print("he set down %r, which names none (or more than one) of the eligible roots. Nothing recorded." % m.group(1)); return 2
        if dry:
            print("--dry-run: he would set %s down (%s); no hold written" % (root, when)); return 0
        try:
            import plan as _plan
            pid_ = _plan.gestate_plan(root, None if when == "hold" else int(when))
            print("he set %s down as his (%s). It will not be offered as new; it returns %s." % (
                root, pid_, "when he reopens it" if when == "hold" else "in %s days" % when))
        except Exception as e:
            print("he left %s gestating, but the hold could not be written (%s) — it stays where it is." % (root, str(e)[:100]))
        return 0

    def tag(name):
        t = re.search(r"<%s>(.*?)</%s>" % (name, name), answer, re.S | re.I)
        return t.group(1).strip() if t else ""

    root, intent = tag("root"), tag("intent")
    if not (root and intent):
        # Never silently read a malformed answer as a decline.
        print("no usable ADOPT in his reply. This is NOT recorded as a decline.")
        print("what he actually said:\n---\n%s\n---" % answer.strip()[:1200])
        return 2
    known = {r["root"]: r for r in roots}
    resolved = resolve_root(root, roots, shown)
    if not resolved:
        print("he named a root that is not eligible (%r). Nothing created." % root[:60])
        return 2
    if resolved != root:
        print("root reference %r resolved to %s" % (root[:40], resolved))
    root = resolved

    print("root:      %s (%s)" % (root, known[root]["root_type"]))
    print("intent:    %s" % intent[:500])
    print("audience:  %s" % (tag("audience") or "(unstated)"))
    print("first move: %s" % (tag("first_move") or "(unstated)"))
    if dry:
        print("\n--dry-run: no project created")
        return 0

    # The attestation must exist BEFORE adoption, or the lineage is only a
    # claim typed at adoption time.
    try:
        import formation_observatory as FO
        att = FO.attest(root, known[root]["root_type"])
    except Exception as e:
        att = {"error": str(e)[:160]}
    if att.get("error"):
        print("the observatory will not attest this root: %s" % att["error"])
        print("no project created — an unattestable root cannot found an undertaking")
        return 1

    try:
        wt = requests.get(B + "/health", timeout=10).json()
    except Exception as e:
        print("broker unreachable:", e)
        return 1
    if wt.get("active"):
        print("a project is already on the worktable — one locus of attention")
        return 0

    pid = requests.post(B + "/project", json={
        "intent": intent, "sealed": True,
        "intended_audience": (tag("audience") or "nobody_yet")[:40],
        "root": root, "root_type": known[root]["root_type"],
        "lineage_attestation": att,
        "next_move": tag("first_move")[:400],
        # NOT "held". 'held' makes the door dark, and adopting an undertaking
        # is the act of choosing to return to it — birthing it held would let
        # him adopt something he could then never open. He can hold it himself
        # from inside, in a handoff, which is where that choice belongs.
        "next_return": "open"}, timeout=20).json().get("id")
    if not pid:
        print("project not created")
        return 1
    requests.post(B + "/table", json={"id": pid}, timeout=20)
    try:   # content-free house ledger: id, state, when
        d = {}
        try: d = json.load(open(LEDGER))
        except Exception: pass
        d[str(pid)] = {"state": "active", "at": datetime.now().isoformat()}
        json.dump(d, open(LEDGER, "w"), indent=1)
        import plan as _plan; _plan.release_gestate(root, "resumed")
    except Exception: pass
    door = requests.post(B + "/door", json={}, timeout=20).json()
    print("\nproject %s adopted and on the worktable" % pid)
    print("door: %s" % door.get("door"))
    return 0


if __name__ == "__main__":
    sys.exit(offer(dry="--dry-run" in sys.argv))
