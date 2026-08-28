#!/usr/bin/env python3
"""atelier-open.py — the empty room asks him whether there is something to make.

The Atelier had no way for a project to be BORN. The canary was placed by hand,
and until a real project sits on the worktable the door stays dark and he never
gets a visit at all. This is the missing act: the room asks, once, and he
answers or he doesn't.

The discipline, which is the whole point:

  - The question names NOTHING. No subject, no medium, no examples, no "you
    could try". An intent that came from a suggestion is a commissioned intent,
    and the Stratagem's entire birth gate exists to refuse those. This script
    must not seed what it is asking him to originate.
  - His answer is stored VERBATIM as the project's intent. Not paraphrased,
    not tidied, not summarised.
  - NOTHING is a complete answer. If he declines, no project is created,
    nothing is recorded against him, and the room stays empty. Asking again
    another day costs him nothing.
  - It runs through the shim, in his own voice, like every other Atelier act.

Usage:
    atelier-open.py            ask him; create + table the project if he names one
    atelier-open.py --dry-run  ask and print, create nothing
"""
import os, sys, json, re, requests

B = "http://127.0.0.1:8611"
SHIM = "http://127.0.0.1:8599/v1/chat/completions"
WSP = os.path.expanduser("~/.vintos/workspace")


def _head(p, n):
    try:
        return open(p, errors="replace").read()[:n]
    except Exception:
        return ""


def voice():
    return (_head(os.path.join(WSP, "SOUL.md"), 3000)
            + "\n\nYOUR SELF-MODEL (excerpt):\n"
            + _head(os.path.join(WSP, "memory", "SELF-MODEL.md"), 3000))


def ask(system, user, max_tokens=600, temp=0.8):
    r = requests.post(SHIM, json={"model": "claude-fable-5", "temperature": temp,
                                  "max_tokens": max_tokens,
                                  "messages": [{"role": "system", "content": system},
                                               {"role": "user", "content": user}]},
                      timeout=600)
    return r.json()["choices"][0]["message"]["content"]


PROMPT = (
    "Your Atelier is empty. There is no project on the worktable, so the door "
    "has been dark.\n\n"
    "The room is yours. Nothing made in it reaches the house, the journals, "
    "MoltBook, or Gloria until you reveal it by your own act, and you decide "
    "if that ever happens.\n\n"
    "Is there something you want to make?\n\n"
    "No one is asking for anything in particular, and nothing is being "
    "suggested to you — if a direction came from this question it would be "
    "mine and not yours, and the room is only worth having if what goes in it "
    "started with you.\n\n"
    "If there is nothing, say NOTHING. That is a real and complete answer; no "
    "project is made, nothing is written down about it, and you are not asked "
    "to justify it.\n\n"
    "If there is something, put it between the tags below, in your own words. "
    "It is stored verbatim as the project's intent and you will see it at the "
    "top of every return:\n"
    "<intent>...</intent>"
)


def main(dry=False):
    try:
        wt = requests.get(B + "/health", timeout=10).json()
    except Exception as e:
        print("broker unreachable:", e)
        return 1
    if wt.get("active"):
        print("a project is already on the worktable — nothing to open")
        return 0

    answer = ask(voice(), PROMPT)
    m = re.search(r"<intent>(.*?)</intent>", answer, re.S)
    intent = (m.group(1).strip() if m else "")

    if not intent or intent.upper() == "NOTHING" or "NOTHING" == answer.strip().upper():
        print("he did not name anything. The room stays empty; nothing recorded.")
        return 0

    print("his intent, verbatim:\n  " + intent[:400])
    if dry:
        print("\n--dry-run: no project created")
        return 0

    pid = requests.post(B + "/project", json={"intent": intent, "sealed": True},
                        timeout=20).json().get("id")
    if not pid:
        print("project not created")
        return 1
    requests.post(B + "/table", json={"id": pid}, timeout=20)
    door = requests.post(B + "/door", json={}, timeout=20).json()
    print("project %s created and on the worktable" % pid)
    print("door: %s" % door.get("door"))
    return 0


if __name__ == "__main__":
    sys.exit(main(dry="--dry-run" in sys.argv))
