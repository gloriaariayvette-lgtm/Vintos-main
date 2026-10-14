#!/usr/bin/env python3
"""avatar_dryrun.py - run his avatar reply path with NO side effects.

Takes the exact prompt his server last built for avatar chat
(/tmp/avatar-last-prompt.json, dumped by the handler right before the model
call), swaps in the CURRENT [SCENE:] vocabulary, replaces the final user turn
with a test line, and calls the same model router his server calls. Nothing is
saved: no ledger, no history, no nudges, no memory. Prints the raw reply.

    python3 ~/Vintos/avatar_dryrun.py --argon      her last real message: his actual reply beside Argon's
    python3 ~/Vintos/avatar_dryrun.py --list       her last 30 messages, numbered (1 = the most recent)
    python3 ~/Vintos/avatar_dryrun.py --argon --turn 7   her 7th-last message, with the conversation before it
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
# --model NAME (repeatable): the same prompt to that model too. claude-* goes through his own router call
# (claude_draft), sol / gpt-* through sol_draft, gemini-* through argon(). --argon is --model gemini-4-argon.
CANDIDATES = ["gemini-4-argon"] if ARGON else []
while "--model" in sys.argv:
    _i = sys.argv.index("--model")
    if _i + 1 >= len(sys.argv): print("--model needs a model id, e.g. claude-opus-5-5"); sys.exit(1)
    CANDIDATES.append(sys.argv[_i + 1]); del sys.argv[_i:_i + 2]
ARGON = bool(CANDIDATES)
TURN = None
if "--turn" in sys.argv:
    _i = sys.argv.index("--turn")
    try: TURN = int(sys.argv[_i + 1])
    except Exception: print("--turn needs a number from --list"); sys.exit(1)
    del sys.argv[_i:_i + 2]
# Earlier turns come from his interaction ledger: 300 exchanges across his surfaces, where the avatar history keeps 40.
LEDGER_PATH = os.path.expanduser("~/.vintos/workspace/memory/interaction-ledger.json")
_MARK = re.compile(r"\n\n(?:tenera:|ridge:|ferri:)[\s\S]*$")   # the device pictures under his words, not his words

def _exchanges():
    rows = json.load(open(LEDGER_PATH))
    return [r for r in rows if isinstance(r, dict) and str(r.get("gloria") or "").strip()
            and not str(r.get("gloria")).startswith("[she spoke with her body")]

if "--list" in sys.argv:
    ex = _exchanges()
    for n, r in enumerate(reversed(ex[-30:]), 1):
        print("%3d  %s  %-8s %s" % (n, str(r.get("timestamp", ""))[5:16].replace("T", " "), str(r.get("surface") or "")[:8],
                                   " ".join(str(r.get("gloria")).split())[:100]))
    sys.exit(0)
msg = sys.argv[1] if len(sys.argv) > 1 else None
messages = None
for _cap in (os.environ.get("VINTOS_AVATAR_CAPTURE") or "/tmp/avatar-last-prompt.json",):   # override: tests only
    try:
        messages = json.load(open(_cap)); break
    except Exception:
        continue
if not messages:
    print("no captured avatar prompt in /tmp yet: the server writes it on his next avatar reply in ordinary use")
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
if TURN is not None and msg is None:
    # an earlier turn of hers: the conversation up to it from his avatar history (the server reads 15 exchanges),
    # her message, and the reply he actually gave. The system prompt is the latest captured one: today's room
    # and devices, not that night's.
    ex = _exchanges()
    if not 1 <= TURN <= len(ex): print("--turn %d: there are %d of her messages" % (TURN, len(ex))); sys.exit(1)
    i = len(ex) - TURN
    msg = str(ex[i].get("gloria")).strip()
    his_actual = _MARK.sub("", str(ex[i].get("vintos") or "")) or None
    # The ledger can hold the same exchange twice (written from two surfaces). An earlier copy of THIS exchange in
    # the history put his real reply in front of the candidate, and Argon copied it word for word (14 October).
    # Nothing in the history may be this message or this reply, and repeated exchanges are kept once.
    same = lambda a, b: " ".join(str(a or "").split())[:400] == " ".join(str(b or "").split())[:400]
    rows_before, this_turn, seen = [], [], set()
    for r in ex[:i]:
        g, v = str(r.get("gloria") or ""), _MARK.sub("", str(r.get("vintos") or ""))
        if same(g, msg) or (his_actual and same(v, his_actual)):
            this_turn.append(r); continue          # an earlier copy of this very exchange
        key = (" ".join(g.split())[:200], " ".join(v.split())[:200])
        if key in seen: continue
        seen.add(key); rows_before.append(r)
    rows_before = rows_before[-15:]
    before = []
    for r in rows_before:
        before += [{"role": "user", "content": str(r.get("gloria") or "")},
                   {"role": "assistant", "content": _MARK.sub("", str(r.get("vintos") or ""))}]
    # The system prompt is today's, and it carries his recent exchanges ("Your recent exchanges with Gloria"), which
    # include this turn's reply and everything after it: Argon copied his reply from there (14 October). That section
    # is rebuilt from the exchanges BEFORE this turn only, and any other line of the prompt that quotes this turn or a
    # later one is removed.
    def _ledger_block(rows):
        # each exchange marked with when it was said, as the server's own section is (when_said)
        try:
            sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
            import when_said as _ws
        except Exception:
            _ws = None
        lines = []
        for r in rows:
            g = " ".join(str(r.get("gloria") or "").split())[:400]
            v = " ".join(_MARK.sub("", str(r.get("vintos") or "")).split())[:400]
            when = ((_ws.ago(r.get("timestamp")) if _ws else "") or str(r.get("timestamp", ""))[:16])
            lines.append("- %s\n    Gloria: %s\n    You: %s" % (when, g, v))
        return ("Your recent exchanges with Gloria (what was actually said, most recent last). Each is marked with "
                "when it was said:\n" + "\n".join(lines)) if lines else ""
    _block = re.compile(r"Your recent exchanges with Gloria \(what was actually said.*?(?=\nYour current self-model|\Z)", re.S)
    system = _block.sub(lambda m: _ledger_block(rows_before), system, count=1)
    _later = []
    for r in this_turn + ex[i:]:
        for t in (str(r.get("gloria") or ""), _MARK.sub("", str(r.get("vintos") or ""))):
            t = " ".join(t.split())
            if len(t) >= 12:      # short lines too: "Give me the hand." is a whole reply
                _later += [t[:60], t[len(t) // 2:len(t) // 2 + 60]] if len(t) > 60 else [t]
    _kept = []
    for line in system.split("\n"):
        flat = " ".join(line.split())
        if not any(snip in flat for snip in _later):
            _kept.append(line)
    print("[dryrun] removed from the system prompt: %d line(s) quoting this turn or later ones" % (len(system.split("\n")) - len(_kept)))
    system = "\n".join(_kept)
    convo = [m for m in before if m["content"].strip()] + [{"role": "user", "content": msg}]
    print("[dryrun] her message (turn %d back):" % TURN, msg[:300])
    print("[dryrun] (system prompt: today's, minus every exchange from this turn on; his memory files and inner life are still today's)")
elif msg is None:
    # The captured prompt's last turn is what his model saw: her words wrapped in context the server adds (open
    # intentions and the like), so it is never matched as text. Her plain words and his actual reply come from his
    # avatar history: its last message from her and the reply after it. Argon still gets the captured prompt whole.
    msg = ""
    try:
        hist = json.load(open(os.path.expanduser("~/.vintos/workspace/memory/avatar-overlay-chat.json")))
        users = [i for i, h in enumerate(hist) if isinstance(h, dict) and h.get("role") == "user"]
        if users:
            i = users[-1]
            msg = _text(hist[i].get("content")).strip()
            nxt = next((x for x in hist[i + 1:] if isinstance(x, dict) and x.get("role") == "assistant"), None)
            if nxt: his_actual = _text(nxt.get("content"))
    except Exception:
        pass
    print("[dryrun] her last message:", (msg or "(not found in his avatar history)")[:300])
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
    print("[dryrun] his actual reply (from his %s)" % ("ledger" if TURN is not None else "avatar history"))
    print("---")
    print(his_actual or "(his reply to it was not found)")
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


def claude_candidate(system, convo, model):
    """The same prompt to a Claude model, through his router's own draft call. Its usage goes to the usage log, as
    every paid call's does; nothing goes to his memory."""
    try:
        text, _ = asyncio.run(_mr.claude_draft(system, convo, max_tokens=1500, model=model))
        return text or "(no text: refused or empty)"
    except Exception as e:
        return "(%s unavailable: %s)" % (model, str(e)[:200])


def sol_candidate(system, convo, model):
    """The same prompt to Sol (OpenAI), through his router's own Sol call."""
    try:
        text, _ = asyncio.run(_mr.sol_draft(system, convo, max_tokens=1500, model=model))
        return text or "(no text: refused or empty)"
    except Exception as e:
        return "(%s unavailable: %s)" % (model, str(e)[:200])


for cand in CANDIDATES:
    print()
    if cand.startswith("gemini-"):
        text, usage = argon(system, convo, model=cand)
        print("[dryrun] model: %s (Google)" % cand)
    elif cand == "sol" or cand.startswith("gpt-"):
        name = getattr(_mr, "SOL_MODEL", "") if cand == "sol" else cand   # "sol": the Sol he is configured with
        text, usage = sol_candidate(system, convo, name), {}
        print("[dryrun] model: %s (Sol, OpenAI)" % name)
    else:
        text, usage = claude_candidate(system, convo, cand), {}
        print("[dryrun] model: %s" % cand)
    print("[dryrun] tags:", re.findall(r"\[[A-Z]+:[^\]]*\]", text or ""))
    if usage:
        print("[dryrun] tokens in %s, out %s, thinking %s" % (usage.get("promptTokenCount"), usage.get("candidatesTokenCount"),
                                                            usage.get("thoughtsTokenCount", 0)))
    print("---")
    print(text or "")
