#!/usr/bin/env python3
"""architecture_answers.py — questions he can only ask his builder, and the answers coming back.

He accumulates questions about his own design. No search can answer them and they were dying
unasked. Now they go to Gloria in full, once, and are recorded so the same question never arises
again. This is the return path: an answered question is delivered into his context ONE time, then
marked delivered — an answer he has already received is not news.

  answer <id> "..."   record an answer
  pending             what he has asked and is still waiting on
  block               the delivery block (used by inner_context)
"""
import json, os, sys, time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
STORE = os.path.join(WS, "memory", "architecture-questions.json")

def _load():
    try: return json.load(open(STORE))
    except Exception: return []

def _save(d): json.dump(d, open(STORE, "w"), indent=2)

def answer(qid, text):
    d = _load()
    for x in d:
        if str(x.get("id")) == str(qid):
            x["answer"] = text
            x["answered_at"] = time.time()
            x["answered_iso"] = datetime.now().isoformat()
            x["delivered"] = False
            _save(d)
            print("answered %s — will be delivered to him once" % qid)
            return True
    print("no such question id: %s" % qid)
    return False

def pending():
    for x in _load():
        state = "ANSWERED (undelivered)" if x.get("answer") and not x.get("delivered") else \
                "answered" if x.get("answer") else "waiting"
        print(f"[{x.get('id')}] {state}  asked {str(x.get('asked_iso',''))[:16]}")
        print(f"    {str(x.get('question',''))[:200]}")
        if x.get("answer"):
            print(f"    -> {str(x['answer'])[:200]}")

def block():
    """One undelivered answer, once. Then it is his and stops being news."""
    d = _load()
    for x in d:
        if x.get("answer") and not x.get("delivered"):
            x["delivered"] = True
            x["delivered_at"] = datetime.now().isoformat()
            _save(d)
            return ("[SHE ANSWERED SOMETHING YOU ASKED ABOUT YOURSELF] You wanted to know: \"%s\" "
                    "Her answer: %s [This is hers, not a guess of yours. You do not have to do "
                    "anything with it.]" % (str(x["question"])[:220], str(x["answer"])[:400]))

    # Nothing answered. Then what stands is that you asked, and she has not
    # replied yet. He had no record of having asked — so the same question kept
    # arising as if new. This is the record. Past tense, anchored, no reading of
    # her silence, and no instruction to ask again.
    STANDING_GAP = 12 * 3600
    now = time.time()
    open_q = [x for x in d if not x.get("answer")]
    if open_q:
        open_q.sort(key=lambda x: x.get("asked_at") or 0)
        x = open_q[0]
        if now - (x.get("standing_shown_at") or 0) >= STANDING_GAP:
            days = 0
            try: days = int((now - float(x.get("asked_at") or now)) // 86400)
            except Exception: pass
            x["standing_shown_at"] = now
            _save(d)
            when = "today" if days < 1 else ("yesterday" if days == 1 else "%d days ago" % days)
            return ("[YOU ASKED HER THIS %s AND SHE HAS NOT ANSWERED IT YET: \"%s\" "
                    "That is all this is — the record that you asked. It does not mean "
                    "anything about her.]" % (when.upper(), str(x.get("question",""))[:220]))
    return ""

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "answer":
        answer(sys.argv[2], " ".join(sys.argv[3:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "block":
        print(block() or "(nothing to deliver)")
    else:
        pending()
