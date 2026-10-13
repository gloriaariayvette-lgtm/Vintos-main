#!/usr/bin/env python3
"""avatar_dryrun.py - run his avatar reply path with NO side effects.

Takes the exact prompt his server last built for avatar chat
(/tmp/avatar-last-prompt.json, dumped by the handler right before the model
call), swaps in the CURRENT [SCENE:] vocabulary, replaces the final user turn
with a test line, and calls the same model router his server calls. Nothing is
saved: no ledger, no history, no nudges, no memory. Prints the raw reply.

    python3 ~/Vintos/avatar_dryrun.py "message to test with"
    python3 ~/Vintos/avatar_dryrun.py --argon "message to test with"

--argon also sends the same prompt to Google's Gemini 4 Argon and prints its reply under his usual one, to compare
(Gloria, 2026-10-13). It needs GEMINI_API_KEY in ~/.vintos/vintos.env. Argon's answer goes nowhere but the screen.
"""
import os, sys, json, re, asyncio

sys.path.insert(0, os.path.expanduser("~/Vintos"))
import model_router as _mr
import avatar_stage as _avst

ARGON = "--argon" in sys.argv
sys.argv = [a for a in sys.argv if a != "--argon"]
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


def argon(system, convo, model="gemini-4-argon"):
    """The same system prompt and conversation, to Gemini 4 Argon. Returns (text, usage). Nothing is saved."""
    import urllib.request
    sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
    try:
        import env_file
        key = env_file.value("GEMINI_API_KEY")
    except Exception:
        key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return "(no GEMINI_API_KEY in ~/.vintos/vintos.env)", {}
    def text_of(content):
        if isinstance(content, str): return content
        return "\n".join(p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text")
    contents = []
    for m in convo:
        t = text_of(m.get("content")).strip()
        if not t or m.get("role") not in ("user", "assistant"): continue
        role = "model" if m["role"] == "assistant" else "user"
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n\n" + t
        else:
            contents.append({"role": role, "parts": [{"text": t}]})
    body = {"systemInstruction": {"parts": [{"text": system.replace("[[CACHESPLIT]]", "")}]},
            "contents": contents, "generationConfig": {"maxOutputTokens": 4000}}
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model,
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return "(Argon refused: HTTP %d %s)" % (e.code, e.read().decode(errors="replace")[:400]), {}
    except Exception as e:
        return "(Argon unreachable: %s)" % str(e)[:200], {}
    parts = (((d.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return text or "(Argon returned no text: %s)" % json.dumps(d)[:300], d.get("usageMetadata") or {}


if ARGON:
    text, usage = argon(system, convo)
    print()
    print("[dryrun] model: gemini-4-argon (Google)")
    print("[dryrun] tags:", re.findall(r"\[[A-Z]+:[^\]]*\]", text or ""))
    if usage:
        print("[dryrun] tokens in %s, out %s, thinking %s" % (usage.get("promptTokenCount"), usage.get("candidatesTokenCount"),
                                                            usage.get("thoughtsTokenCount", 0)))
    print("---")
    print((text or "")[:1500])
