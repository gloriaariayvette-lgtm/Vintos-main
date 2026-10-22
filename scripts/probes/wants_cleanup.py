#!/usr/bin/env python3
"""The wants he already holds, put through the routes new wants now take (22 October, Gloria: "That's a meta want
and we made routes for those" / "something needs to be done about duplicates").

Without --apply it prints what it would do and writes nothing. With --apply:
  - a second-order want leaves his wants and goes to its route (wants_meta.route: a behavior becomes a
    self-requested trial, a stance on a want or feeling is recorded; one that cannot be enacted is dropped, no history)
  - a want that is the same desire as an older living one is merged into it (recurrence, recurrence_log), as
    express_want now does
  - a copy of the wants file as it was is kept in ~/.vintos/deploy/ so it can be put back
Agent-letter wants (source email) are kept like any other first-order want. Asks local Gemma only."""
import json, os, shutil, sys, time
from datetime import datetime

WS = os.path.expanduser("~/.vintos/workspace")
sys.path.insert(0, os.path.join(WS, "scripts"))
import wants_meta as M

APPLY = "--apply" in sys.argv
WANTS = os.path.join(WS, "memory", "current-wants.json")
MERGE = ("duplicate", "persistence", "continuation", "escalation")


def ask(prompt, tokens=120):
    import requests
    r = requests.post(M.LM, json={"model": M.MODEL, "temperature": 0.0, "max_tokens": tokens,
                                  "messages": [{"role": "user", "content": prompt}]}, timeout=60)
    return r.json()["choices"][0]["message"]["content"]


def relationship(text, kept):
    listing = "\n".join("[%s] %s" % (w.get("id", "?"), str(w.get("want", ""))[:100]) for w in kept[-30:])
    prompt = ("New candidate desire:\n%s\n\nLiving wants:\n%s\n\nWhat is the candidate's relationship to the living field?\n"
              "- duplicate: same want, no new information\n- continuation: extends or advances an existing want\n"
              "- persistence: the same underlying desire returning again\n"
              "- mutation: a repeated territory changing into something new\n- escalation: an existing want intensifying\n"
              "- novel: genuinely new territory\n"
              'Return ONLY JSON: {"relationship": "...", "id": "..."} - id of the related want, empty string if novel.'
              % (text, listing))
    try:
        raw = ask(prompt, 60)
        d = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        return str(d.get("relationship", "novel")).lower(), str(d.get("id", ""))
    except Exception as e:
        return "unjudged (%s)" % type(e).__name__, ""


wants = json.load(open(WANTS))
live = [w for w in wants if not w.get("fulfilled") and not w.get("dismissed")]
print("%d wants on file, %d living. %s\n" % (len(wants), len(live), "APPLYING" if APPLY else "DRY RUN - nothing is written"))

remove, kept, routed = set(), [], []
for w in sorted(live, key=lambda x: str(x.get("timestamp", ""))):
    text = str(w.get("want", ""))
    verdict = M.classify(text, ask=lambda p: ask(p))
    if verdict:
        what = ("trial (%s %s)" % (verdict["stance"], verdict["about"]) if verdict["target"] == "behavior" and verdict["fulfillable"]
                else "stance recorded" if verdict["fulfillable"] else "dropped, no history")
        print("SECOND-ORDER -> %s\n    [%s] %s" % (what, w.get("id"), text[:110]))
        remove.add(id(w)); routed.append((text, verdict, w.get("source", "")))
        continue
    rel, rid = relationship(text, kept) if kept else ("novel", "")
    target = next((k for k in kept if k.get("id") == rid), None)
    if rel in MERGE and target is not None:
        print("SAME WANT (%s) -> merged into [%s] %s\n    [%s] %s" % (rel, rid, str(target.get("want", ""))[:70], w.get("id"), text[:110]))
        target["recurrence"] = target.get("recurrence", 1) + w.get("recurrence", 1)
        if rel == "escalation":
            target["intensity"] = min(5, int(target.get("intensity", 3) or 3) + 1)
        log = target.setdefault("recurrence_log", [])
        log.extend(w.get("recurrence_log", []))
        log.append({"timestamp": w.get("timestamp", ""), "source": w.get("source", ""), "text": text[:120]})
        target["recurrence_log"] = log[-10:]
        remove.add(id(w))
        continue
    kept.append(w)

print("\n%d stay, %d go to second-order routes, %d merge into an older want."
      % (len(kept), len(routed), len(remove) - len(routed)))
if not APPLY:
    print("Nothing written. Add --apply to do this.")
    sys.exit(0)

backup = os.path.expanduser("~/.vintos/deploy/wants-before-cleanup-%s.json" % datetime.now().strftime("%Y%m%d-%H%M%S"))
os.makedirs(os.path.dirname(backup), exist_ok=True)
shutil.copy2(WANTS, backup)
for text, verdict, source in routed:
    print("route:", M.route(text, verdict, source=source), "-", text[:70])
# Re-read: his loop may have added a want while Gemma was judging. Only the wants judged above are changed.
gone = {w.get("id") for w in wants if id(w) in remove}
merged = {k.get("id"): k for k in kept if k.get("recurrence_log")}
fresh = json.load(open(WANTS))
out = [merged.get(w.get("id"), w) for w in fresh if w.get("id") not in gone]
with open(WANTS + ".tmp", "w") as f:
    json.dump(out, f, indent=2)
os.replace(WANTS + ".tmp", WANTS)
print("\nWritten: %d wants on file (was %d). To put it back: cp %s %s" % (len(out), len(fresh), backup, WANTS))
