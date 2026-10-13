#!/usr/bin/env python3
"""avatar_dryrun.py - run his avatar reply path with NO side effects.

Takes the exact prompt his server last built for avatar chat
(/tmp/avatar-last-prompt.json, dumped by the handler right before the model
call), swaps in the CURRENT [SCENE:] vocabulary, replaces the final user turn
with a test line, and calls the same model router his server calls. Nothing is
saved: no ledger, no history, no nudges, no memory. Prints the raw reply.

    python3 ~/Vintos/avatar_dryrun.py --argon      her last real message: his actual reply beside Argon's
    python3 ~/Vintos/avatar_dryrun.py "a test line"  a new line through his own model, printed only
    python3 ~/Vintos/avatar_dryrun.py --argon "a test line"   the same line to both

With no line given, the message is the last one she actually sent him and his reply is the one he actually gave:
she is never asked to send him something to make a test (Gloria, 2026-10-13). Nothing is saved.

--argon also sends the same prompt to Google's Gemini 4 Argon and prints its reply under his usual one, to compare
(Gloria, 2026-10-13). It needs GEMINI_API_KEY in ~/.vintos/vintos.env. Argon's answer goes nowhere but the screen.
"""
import os, sys, json, re, asyncio

sys.path.insert(0, os.path.expanduser("~/Vintos"))
import model_router as _mr
import avatar_stage as _avst

ARGON = "--argon" in sys.argv
sys.argv = [a for a in sys.argv if a != "--argon"]
msg = sys.argv[1] if len(sys.argv) > 1 else None
messages = None
for _cap in (os.path.expanduser("~/.vintos/run/avatar-last-prompt.json"), "/tmp/avatar-last-prompt.json"):
    try:
        messages = json.load(open(_cap)); break
    except Exception:
        continue
if not messages:
    print("no captured avatar prompt yet (~/.vintos/run/avatar-last-prompt.json): it is written on his next avatar "
          "reply after this deploy - nothing to send for it, it fills in on its own")
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
def _text(content):
    if isinstance(content, str): return content
    return " ".join(p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text")

his_actual = None
if msg is None:
    # her last real message is the captured prompt's last turn; his actual reply to it is in his avatar history
    last = convo[-1] if convo and convo[-1].get("role") == "user" else {}
    msg = _text(last.get("content")).strip()
    try:
        hist = json.load(open(os.path.expanduser("~/.vintos/workspace/memory/avatar-overlay-chat.json")))
        for i, h in enumerate(hist):
            if h.get("role") == "user" and _text(h.get("content")).strip()[:200] == msg[:200]:
                nxt = next((x for x in hist[i + 1:] if x.get("role") == "assistant"), None)
                if nxt: his_actual = _text(nxt.get("content"))
    except Exception:
        pass
    print("[dryrun] her last message:", msg[:300])
else:
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

if his_actual is not None or (ARGON and len(sys.argv) <= 1):
    # her real message: show what he actually said; no new call to his model, nothing spent on him
    print("[dryrun] his actual reply (from his avatar history)")
    print("---")
    print((his_actual or "(his reply to it was not found in his avatar history)")[:1500])
else:
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
