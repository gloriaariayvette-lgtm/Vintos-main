#!/usr/bin/env python3
"""When Gemma writes, compose() leaves out the oldest whole messages of the conversation until each call should fit
Gemma's 32,000-token window (F-7e73896373, 22 October: his draft overflowed it at 12:50 and 18:27 and Grok wrote both
turns). The message he answers, the thread, the work and his steering are never left out; every other lens gets the
prompt as given. The Gemma here is a character-counting stub: this checks the shedding, not a real tokenizer. Scratch
HOME set before import; every model is a stub; nothing reaches the network."""
import os, re, socket, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="gemma-window-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)

def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
socket.socket.connect = no_network
sys.path.insert(0, os.path.join(REPO, "scripts"))
import failure_watch as FW
import dot_channel as D

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

check("failures and state are written only under the scratch HOME", FW.FAILURES.startswith(HOME) and D.STATE.startswith(HOME))

# his context sized like 22 October's: the system argument of every call is 81,690 characters
D.recall_block = lambda: ""
rest = len(str(D.for_claude("", "\n\n---\n\n", D.rules_for(None), "")))
D.his_context = lambda: "H" * (81690 - rest)
D.use_tools = lambda asks, **k: "L" * 6000          # a lookup that brings back 6,000 characters

ROWS = ["ROW%02d %s" % (i, "r" * 740) for i in range(60)]
TAIL = ("\n\nTHE THREAD: the thread block\n\nGloria just said: the message he answers\n\nYour reply, as yourself."
        "\n\nWORK BOARD: the work\n\nSTEERING: how he is steered")
def render(k=0):
    return "THE CONVERSATION SO FAR (most recent last):\n" + "\n".join(ROWS[k:]) + TAIL
WHOLE = render()
check("the prompt is sized like the 12:50 overflow (about 45,000 characters)", 44000 < len(WHOLE) < 46000, len(WHOLE))

def overflow(requested):
    return RuntimeError('LM Studio gave no reply: Engine protocol predict request returned 400: {"error":{"code":400,'
                        '"message":"request (%d tokens) exceeds the available context size (32000 tokens)"}}' % requested)

def gemma(answers):
    """A Gemma that counts 3.6 characters a token, as 22 October's overflows did, and overflows past its window."""
    seen, it = [], iter(answers)
    def think(system, user):
        if system == D.EDITOR: return "KEEP"
        n = int((len(str(system)) + len(str(user))) / 3.6) + D.GEMMA_REPLY
        seen.append(str(user))
        if n > D.GEMMA_WINDOW: raise overflow(n)
        return next(it, "a plain reply")
    return think, seen

def rows_in(user):
    return [int(m) for m in re.findall(r"^ROW(\d\d) ", user, re.M)]

print("--- before: with nothing to shed, the 12:50 prompt overflows and Grok would write ---")
think, seen = gemma(["a plain reply"])
text, who = D.compose(WHOLE, think, lambda s, u: "", {"fable": 0}, "2026-10-23")
check("without shed the draft overflows, as at 12:50", text is None and "context overflow" in who, who)

print("\n--- after: the draft sheds the oldest whole messages and Gemma answers ---")
think, seen = gemma(["a plain reply"])
text, who = D.compose(WHOLE, think, lambda s, u: "", {"fable": 0}, "2026-10-23", shed=(len(ROWS), render))
check("Gemma answers the turn", text == "a plain reply" and who == "gemma", (text, who))
draft = seen[0]
kept = rows_in(draft)
check("some history was left out, not all of it", 0 < len(kept) < len(ROWS), len(kept))
check("only the oldest were left out, whole and in order", kept == list(range(60 - len(kept), 60)), kept[:5])
check("no message is cut part way", all(("ROW%02d %s" % (i, "r" * 740)) in draft for i in kept))
check("the thread, the message he answers, the work and his steering are there exactly",
      draft.count(TAIL) == 1 and TAIL in draft, draft[-300:])
check("the call that was made should fit by the estimate", D.gemma_fits("H" * 81690, draft))

print("\n--- a lookup's growth sheds further at the lookup write ---")
think, seen = gemma(["SEARCH: load cells", "a plain reply"])
text, who = D.compose(WHOLE, think, lambda s, u: "", {"fable": 0}, "2026-10-23", shed=(len(ROWS), render))
check("Gemma answers after its lookup", text == "a plain reply", (text, who))
check("the lookup call left out more history than the draft", len(rows_in(seen[1])) < len(rows_in(seen[0])),
      (len(rows_in(seen[0])), len(rows_in(seen[1]))))
check("the lookup call still has what he looked up and the whole tail", "L" * 6000 in seen[1] and TAIL in seen[1])

print("\n--- nothing left to shed and still too large: the overflow is told as before ---")
huge_tail = TAIL + "\n\n" + "W" * 60000
think, seen = gemma(["a plain reply"])
prompt = "THE CONVERSATION SO FAR (most recent last):\n" + "\n".join(ROWS) + huge_tail
text, who = D.compose(prompt, think, lambda s, u: "", {"fable": 0}, "2026-10-23",
                      shed=(len(ROWS), lambda k: "THE CONVERSATION SO FAR (most recent last):\n" + "\n".join(ROWS[k:]) + huge_tail))
check("it still overflows and says so, so Grok can write", text is None and who.startswith(D.LABELS["gemma"] + " could not answer"), who)
check("every message was left out before giving up, and the work was not", rows_in(seen[-1]) == [] and "W" * 60000 in seen[-1])

print("\n--- every other lens gets the prompt exactly as given ---")
got = []
def grok(system, user): got.append(str(user)); return "grok's reply"
text, who = D.compose(WHOLE, think, lambda s, u: "", {"fable": 0}, "2026-10-23", lenses={"grok": grok}, lens="grok",
                      shed=(len(ROWS), render))
check("Grok writes", text == "grok's reply" and who == "grok", (text, who))
check("Grok's prompt is byte-identical to the whole prompt", got and got[0] == WHOLE, len(got[0]) if got else None)

print("\n--- the pass keeps the whole prompt for its fallbacks and builds the history from whole rows ---")
src = open(os.path.join(REPO, "scripts", "dot_channel.py"), encoding="utf-8").read()
check("the conversation is rendered from the rows, not parsed back out of text",
      "_conversation(convo[k:])" in src and "history = (len(convo), answer_prompt)" in src)
check("both fallbacks still get the caller's whole prompt",
      src.count('text, who = compose(prompt, think, fable, state, today, search=search, room=room, atelier=in_thread_atelier,') >= 2)
check("the sent-back and Atelier retries keep their own additions in what may be shed",
      "shed=shed(held_note)" in src and "shed=shed(chose)" in src)
check("the editor still reads what was heard, never the shortened prompt", "heard_from.startswith(base)" in src)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
