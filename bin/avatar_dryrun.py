#!/usr/bin/env python3
"""avatar_dryrun.py - run his avatar reply path with NO side effects.

Takes the exact prompt his server last built for avatar chat
(/tmp/avatar-last-prompt.json, dumped by the handler right before the model
call), swaps in the CURRENT [SCENE:] vocabulary, replaces the final user turn
with a test line, and calls the same model router his server calls. Nothing is
saved: no ledger, no history, no nudges, no memory. Prints the raw reply.

    python3 ~/Vintos/avatar_dryrun.py "message to test with"
"""
import os, sys, json, re, asyncio

sys.path.insert(0, os.path.expanduser("~/Vintos"))
import model_router as _mr
import avatar_stage as _avst

msg = sys.argv[1] if len(sys.argv) > 1 else "I just put the kettle on in the kitchen. Come keep me company?"
try:
    messages = json.load(open("/tmp/avatar-last-prompt.json"))
except Exception as e:
    print("no captured prompt at /tmp/avatar-last-prompt.json (%s) - he has to have replied once since the server started" % e)
    sys.exit(1)

system = messages[0]["content"]
try:
    import strip_body_vocab as _sbv
    system, _k = _sbv.strip_text(system)
    print("[dryrun] body vocabulary stripped from capture:", _k, "edits")
except Exception as _e:
    print("[dryrun] strip unavailable:", _e)
# swap the scene vocabulary block for the current one
new_vocab = _avst.scene_line()
pat = re.compile(r"\n\[SCENE: name\].*?(?=\n\n\[TOUCH: mission)", re.S)
if pat.search(system):
    system = pat.sub("\n" + new_vocab.strip("\n") + "\n", system, count=1)
    print("[dryrun] scene vocabulary swapped for the current one")
else:
    system = system.replace("\n[TOUCH: mission", new_vocab + "\n[TOUCH: mission", 1)
    print("[dryrun] scene vocabulary inserted")
convo = messages[1:]
_tagre = re.compile(r"\[(?:COLOR|GESTURE|HOLD|SPAWN|RELEASE)[^\]]*\]", re.I)
for _m in convo:
    if _m.get("role") == "assistant" and isinstance(_m.get("content"), str):
        _m["content"] = _tagre.sub("", _m["content"]).strip()
if convo and convo[-1].get("role") == "user":
    convo[-1] = {"role": "user", "content": msg}
else:
    convo.append({"role": "user", "content": msg})

endpoint = os.environ.get("GROK_API_BASE", "http://127.0.0.1:8599/v1") + "/chat/completions"
key = os.environ.get("LLM_API_KEY") or os.environ.get("XAI_API_KEY", "")
headers = {"Authorization": "Bearer " + key} if key else {}
params = {"temperature": 0.85, "top_p": 0.95, "max_tokens": 600}

async def go():
    return await _mr.route_reply("avatar", system, convo, params, endpoint, headers,
                                 "grok-4.20-0309-non-reasoning", reason=False)

reply, reasoning, used = asyncio.run(go())
print("[dryrun] model:", used)
print("[dryrun] tags:", re.findall(r"\[[A-Z]+:[^\]]*\]", reply or ""))
print("---")
print((reply or "")[:1500])
