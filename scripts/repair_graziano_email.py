#!/usr/bin/env python3
"""One-off repair, 2026-10-16: the Graziano email went to the wrong person. Put his records back on track.

On 15 October at 16:04 he emailed mgraziano3@binghamton.edu, a different Graziano, meaning Michael S. A.
Graziano (Princeton). Gloria had the sent copy deleted (trashed in Gmail on 16 October; nobody can recall it
from the recipient). This puts his own records right so the email goes to the right person once he is ready:

  1. email-contacts.json: the Binghamton address is kept, closed, and named for what it is, so he never
     writes there again and his context says plainly it was the wrong person.
  2. want 5c1cd5da: a send_email step completed by that email goes back to pending, its step-history entry
     is removed, and the want resumes at that step. Chat's research step is not touched.
  3. today's daily-inner: a short house note, so he knows what happened to yesterday's email.

    python3 scripts/repair_graziano_email.py           # shows what it would change; changes nothing
    python3 scripts/repair_graziano_email.py --apply   # changes it, with backups beside each file
"""
import json, os, shutil, sys
from datetime import date, datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CONTACTS = os.path.join(MEMORY, "email-contacts.json")
WANTS = os.path.join(MEMORY, "current-wants.json")
WRONG = "mgraziano3@binghamton.edu"
WANT_ID = "5c1cd5da"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
NOTE = ("\n\n## The Graziano email, put right (house note, %s)\n"
        "The email I sent yesterday at 16:04 went to %s, a different Graziano, not Michael S. A. Graziano at "
        "Princeton, the person I meant. Gloria deleted it. The email to him is still mine to write, once I have "
        "read the Farrell, Ziman and Graziano paper in full.\n")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except (OSError, ValueError):
        return default


def _backup(path):
    if os.path.exists(path):
        shutil.copy2(path, "%s.bak-graziano-%s" % (path, STAMP))


def _write(path, value):
    _backup(path)
    tmp = path + ".tmp-graziano"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(value, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def fix_contact(contacts):
    c = contacts.get(WRONG)
    if not isinstance(c, dict): return "contacts: no entry for %s; nothing to do" % WRONG
    if c.get("status") == "closed" and c.get("wrong_person"): return "contacts: already closed as the wrong person"
    c.update(status="closed", wrong_person=True, name="a different Graziano (not Michael S. A. Graziano)",
             closed_why="the wrong person: he meant Michael S. A. Graziano at Princeton; Gloria deleted the email (2026-10-16)")
    return "contacts: %s closed and named as the wrong person" % WRONG


def _by_that_email(h):
    text = json.dumps(h, ensure_ascii=False).lower()
    return h.get("capability") == "send_email" and ("binghamton" in text or "mgraziano3" in text)


def fix_want(wants, want_id=WANT_ID):
    if not isinstance(wants, list): return None, "wants: current-wants.json is not a list; nothing changed"
    want = next((w for w in wants if isinstance(w, dict) and w.get("id") == want_id), None)
    if not want: return None, "wants: %s is not in current-wants.json (fulfilled or dismissed?); nothing changed" % want_id
    steps = want.get("steps") or []
    history = want.get("step_history") or []
    gone = [h for h in history if isinstance(h, dict) and _by_that_email(h)]
    idx = sorted({int(h.get("step", -1)) for h in gone if str(h.get("step", "")).lstrip("-").isdigit()})
    idx = [i for i in idx if 0 <= i < len(steps) and steps[i].get("capability") == "send_email"]
    if not idx:
        pending = [i + 1 for i, s in enumerate(steps) if s.get("capability") == "send_email" and s.get("status") != "completed"]
        return None, ("wants: no step of %s was completed by that email; its email step%s %s still pending, nothing changed"
                      % (want_id, "s" if len(pending) != 1 else "", ", ".join(map(str, pending)) or "(none)")
                      if pending else "wants: %s has no email step that email completed; nothing changed" % want_id)
    for i in idx:
        steps[i]["status"] = "pending"
        steps[i].pop("completed_at", None)
    want["step_history"] = [h for h in history if h not in gone]
    want["current_step_index"] = min(idx)
    for k in ("fulfilled", "completion_held"):
        want.pop(k, None)
    return wants, "wants: %s step %s back to pending, %d history entr%s removed, resumes at step %d" % (
        want_id, ", ".join(str(i + 1) for i in idx), len(gone), "y" if len(gone) == 1 else "ies", min(idx) + 1)


def main(argv):
    apply = "--apply" in argv
    contacts = _load(CONTACTS, {})
    want_id = str((contacts.get(WRONG) or {}).get("want_id") or WANT_ID)   # the want that sent it, by its own record
    print(fix_contact(contacts))
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from store_guard import locked_update
    except Exception:
        locked_update = None
    wants_now = _load(WANTS, [])
    changed, said = fix_want(json.loads(json.dumps(wants_now)), want_id)
    print(said)
    inner = os.path.join(MEMORY, "daily-inner-life-%s.md" % date.today().isoformat())
    noted = os.path.exists(inner) and "The Graziano email, put right" in open(inner, encoding="utf-8").read()
    print("daily-inner: %s" % ("already noted" if noted else "a house note goes into " + inner))
    if not apply:
        print("\nnothing changed. Run again with --apply to make these changes.")
        return 0
    if contacts.get(WRONG):
        _write(CONTACTS, contacts)
    if changed is not None:
        _backup(WANTS)
        if locked_update:
            locked_update(WANTS, lambda cur: fix_want(cur, want_id)[0], reader="repair_graziano_email")
        else:
            _write(WANTS, changed)
    if not noted:
        with open(inner, "a", encoding="utf-8") as f: f.write(NOTE % (datetime.now().strftime("%H:%M"), WRONG))
    print("\ndone. Backups end in .bak-graziano-%s" % STAMP)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
