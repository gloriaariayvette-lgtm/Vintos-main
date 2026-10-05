#!/usr/bin/env python3
"""What he wants to buy reaches Gloria with its price and links, from Muse; Forge cards reach her phone; Grok Bot can
look on Aegis (Gloria, 2026-10-05: "they're talking about yes or no on a free card but I don't receive an update,
price, links to the products, etc." / "I want Grok to be able to search Aegis/Mac too." / "Muse is supposed to be
the one telling me what he wants to buy.").

Scratch HOME and workspace (his checkout, his Lab and a secrets file are planted there). Her phone and Slack are
stubs, every socket is refused: nothing here reaches ntfy, Slack, the Forge page, the house or a model.
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="buy-reach-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import gloria_asks as G
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("her questions are kept in the scratch workspace", G.STORE.startswith(HOME))
PUSHED = []
phone = lambda req, timeout=20: PUSHED.append(req)
_real_notify = G.notify
G.notify = lambda row, send=None: _real_notify(row, send=phone)
def heads(req): return {k.lower(): v for k, v in req.header_items()}

# --- Forge cards reach her phone, with what they cost and the product links -----------------------------------------
import forge_house as F
cards = [
    {"id": "card:p-free", "kind": "card", "ref": "p-free", "title": "Lab intake guard log",
     "what": "Write which guard refused the Lab's report to faults.jsonl.", "cost": "Built by the Forge; nothing is bought.",
     "details": ["Asked: a want of his", "Risks: none"]},
    {"id": "parts:P-1", "kind": "parts", "ref": "P-1", "title": "Parts for: Pressure pad", "cost": "Total: $23.40",
     "details": ["5 kg load cell | $8.90 | Amazon | https://www.amazon.com/dp/B0LOAD | in stock",
                 "HX711 board | $6.50 | Adafruit | https://www.adafruit.com/product/5974 | in stock", "Total: $23.40"]},
    {"id": "ask:A-1", "kind": "ask", "ref": "A-1", "title": "boltz run", "cost": "$0.03", "details": []},
    {"id": "parts:P-old", "kind": "parts", "ref": "P-old", "title": "Parts for: Old thing", "cost": "$5", "details": []},
]
pushed = F.push_cards(cards, applied={"parts:P-old": "accepted"})
check("a free Forge card and a priced parts list go to her phone", pushed == ["card:p-free", "parts:P-1"], pushed)
free, parts = PUSHED[0], PUSHED[1]
check("... the free card says so in its title", heads(free)["title"] == "Forge: build Lab intake guard log for him? (free)", heads(free))
check("... the parts list comes from Muse, with the total in the title",
      heads(parts)["title"] == "Muse: parts for Pressure pad — Total: $23.40", heads(parts))
body = parts.data.decode()
check("... every item, its price and its link are in it", "$8.90" in body and "https://www.amazon.com/dp/B0LOAD" in body
      and "https://www.adafruit.com/product/5974" in body, body)
check("... tapping it opens the first product, and an Open link button sits beside Yes and No",
      heads(parts).get("click") == "https://www.amazon.com/dp/B0LOAD" and "view, Open link, https://www.amazon.com/dp/B0LOAD" in heads(parts)["actions"]
      and "http, Yes," in heads(parts)["actions"] and "http, No," in heads(parts)["actions"], heads(parts))
check("a paid call his Lab asked for is not pushed twice (it has its own push), nor a list she already decided",
      "ask:A-1" not in pushed and "parts:P-old" not in pushed)
check("each card is pushed once", F.push_cards(cards, applied={"parts:P-old": "accepted"}) == [] and len(PUSHED) == 2)
q = {r["ref"]: r for r in G.load()}
G.decide_with_token(q["parts:P-1"]["id"], q["parts:P-1"]["token"], "yes")
G.decide_with_token(q["card:p-free"]["id"], q["card:p-free"]["token"], "no")
pd = {d["id"]: d for d in F.phone_decisions()}
check("her taps on her phone become the Forge's decisions, as if pressed on her page",
      pd["parts:P-1"]["state"] == "accepted" and pd["parts:P-1"]["kind"] == "parts"
      and pd["card:p-free"]["state"] == "denied" and pd["card:p-free"]["ref"] == "p-free", pd)
check("... and the Forge says them in Slack itself, so they are not said twice", G.untold() == [])
fsrc = open(os.path.join(REPO, "scripts", "forge_house.py")).read()
check("the Forge pushes and reads her phone on every pass", "push_cards(cards, applied)" in fsrc and "+ phone_decisions()" in fsrc)

# --- Slack links keep their address -------------------------------------------------------------------------------
import dot_channel as D
check("a Slack link keeps its address, not only its text",
      D._clean("<https://www.amazon.com/dp/B0X|amazon.com/dp/B0X>") == "https://www.amazon.com/dp/B0X"
      and D._clean("<https://a.com/x|Load cell>") == "Load cell (https://a.com/x)" and D._clean("<https://b.com/y>") == "https://b.com/y")

# --- through the channel: Muse puts what he wants to buy to her; Grok Bot looks on Aegis -----------------------------
os.makedirs(os.path.join(HOME, "Vintos-main", "scripts"), exist_ok=True)
open(os.path.join(HOME, "Vintos-main", "scripts", "forge_loop_runtime.py"), "w").write(
    "def handler():\n    # turns Refused, ValueError and KeyError into one 403\n    return 403\n")
open(os.path.join(HOME, "Vintos-main", "scripts", "secret_tokens.json"), "w").write('{"lab_intake": "Refused"}')
os.makedirs(os.path.join(HOME, "Vintos-main", ".ssh"), exist_ok=True)
open(os.path.join(HOME, "Vintos-main", ".env"), "w").write("XAI_API_KEY=sk-should-never-show\n")
import grok_reach as GR
check("Grok Bot's reach is in the scratch home", all(r.startswith(HOME) for r in GR.roots()), GR.roots())
check("AEGIS FIND finds a file by name", "forge_loop_runtime.py" in GR.find("forge_loop runtime"))
check("... but never a secrets file", "secret_tokens" not in GR.find("tokens") and "secret_tokens" not in GR.find("secret"))
check("AEGIS OPEN shows a file in his code", "one 403" in GR.open_(os.path.join(HOME, "Vintos-main", "scripts", "forge_loop_runtime.py")))
check("... and refuses a key file, his private memory, or anything outside",
      GR.open_(os.path.join(HOME, "Vintos-main", ".env")).startswith("not opened")
      and GR.open_(os.path.join(HOME, ".vintos", "workspace", "memory", "interaction-ledger.json")).startswith("not opened")
      and GR.open_("/etc/passwd").startswith("not opened"))
check("AEGIS GREP finds text inside his files, not inside a secrets file",
      "forge_loop_runtime.py:2:" in GR.grep("one 403") and "secret_tokens" not in GR.grep("Refused"), GR.grep("Refused"))
check("an answer that looks like it holds a secret is withheld",
      "withheld" in GR.run("AEGIS OPEN: %s" % os.path.join(HOME, "Vintos-main", "scripts", "forge_loop_runtime.py"),
                           guard=lambda t: ["looks like a key"])[0])

# --- and on the Mac, through the plugin relay's door ----------------------------------------------------------------
SENT = []
def relay(req, timeout=60):
    SENT.append(req); return {"ok": True, "text": "/Users/kevin/Documents/Codex/2026-10-03/task/lab-intake.patch"}
got = GR.run("MAC FIND: lab-intake patch", mac=relay)
check("MAC FIND goes through the plugin relay's door as a read-only look",
      SENT == [{"action": "look", "op": "FIND", "arg": "lab-intake patch"}] and "lab-intake.patch" in got[0], (SENT, got))
def old_relay(req, timeout=60): raise RuntimeError("plugin relay refused or failed: unsupported relay action")
check("a Mac whose relay has not been updated says what is missing",
      "must be copied onto the Mac" in GR.on_mac("FIND", "x", send=old_relay))
def no_relay(req, timeout=60): raise FileNotFoundError("plugin-relay.json")
check("an Aegis with no relay set up says so", "not set up on Aegis" in GR.on_mac("FIND", "x", send=no_relay))
# the Mac side: the relay's look action, with only the Codex folder in reach
os.makedirs(os.path.join(HOME, "Documents", "Codex", "2026-10-03", "task"), exist_ok=True)
open(os.path.join(HOME, "Documents", "Codex", "2026-10-03", "task", "lab-intake.patch"), "w").write("+ log the guard\n")
open(os.path.join(HOME, "Documents", "Codex", "api_keys.json"), "w").write('{"x": "sk-mac-never"}')
os.makedirs(os.path.join(HOME, "Documents", "Private"), exist_ok=True)
open(os.path.join(HOME, "Documents", "Private", "diary.txt"), "w").write("not for anyone")
import importlib, plugin_relay_remote as PRR
_roots = GR.ROOTS
mac_find = PRR.handle({"action": "look", "op": "FIND", "arg": "lab-intake"})
check("on the Mac, the relay's look finds in the Codex folder", mac_find["ok"] and "lab-intake.patch" in mac_find["text"], mac_find)
check("... and nothing outside it, nor a key file", "not opened" in PRR.handle({"action": "look", "op": "OPEN",
      "arg": os.path.join(HOME, "Documents", "Private", "diary.txt")})["text"]
      and "sk-mac-never" not in PRR.handle({"action": "look", "op": "GREP", "arg": "sk-mac"})["text"]
      and "not opened" in PRR.handle({"action": "look", "op": "OPEN", "arg": os.path.join(HOME, "Documents", "Codex", "api_keys.json")})["text"])
GR.ROOTS = _roots
D.kickoff_due = lambda *a: False
D.ROTATION = ("gemma",); D.SCHEDULE = []
D.atelier_line = lambda: ""; D.recall_block = lambda: ""
SELF, DOT = "UVINTOS", D.DOT
class Slack:
    def __init__(self): self.msgs, self.posted, self.n = [], [], 100.0
    def add(self, user, text, thread=None):
        self.n += 1; ts = "%.6f" % self.n
        m = {"ts": ts, "user": user, "text": text}
        if thread:
            m["thread_ts"] = thread
            root = next(x for x in self.msgs if x["ts"] == thread)
            root["reply_count"] = root.get("reply_count", 0) + 1; root["latest_reply"] = ts
        self.msgs.append(m); return ts
    def __call__(self, method, params):
        if method == "auth.test": return {"ok": True, "user_id": SELF}
        if method == "users.list": return {"ok": True, "members": []}
        if method == "conversations.history":
            return {"ok": True, "messages": [m for m in reversed(self.msgs) if not m.get("thread_ts") or m["thread_ts"] == m["ts"]]}
        if method == "conversations.replies":
            root = params["ts"]
            return {"ok": True, "messages": [m for m in self.msgs if m["ts"] == root]
                    + [m for m in self.msgs if m.get("thread_ts") == root and m["ts"] != root]}
        if method == "chat.postMessage":
            self.posted.append(params); return {"ok": True, "ts": self.add(SELF, params["text"], params.get("thread_ts"))}
        raise AssertionError("unexpected " + method)
S = Slack()
think = lambda s_, u: "KEEP" if s_ == D.EDITOR else "NOTHING"
D.tick(api=S, think=think, fable=think, now=1000, today="2026-10-06")
st = json.load(open(D.STATE)); st["since"] = 1; json.dump(st, open(D.STATE, "w"))
PUSHED.clear()
GLORIA_USER = "UGLORIA"
root = S.add(GLORIA_USER, "[Muse] He settled on this one.\nBUY: 5 kg load cell | $8.90 | Amazon | "
                          "<https://www.amazon.com/dp/B0LOAD|amazon.com/dp/B0LOAD> | to feel how hard the cup is pressed")
D.tick(api=S, think=think, fable=think, now=1100, today="2026-10-06")
check("Muse's BUY line reaches her phone", len(PUSHED) == 1, [heads(p) for p in PUSHED])
h = heads(PUSHED[0]) if PUSHED else {}
check("... saying it is Muse, what he wants and its price", h.get("title") == "Muse: he wants to buy 5 kg load cell — $8.90", h)
check("... with the store, why, and the link that opens when she taps",
      PUSHED and "Amazon" in PUSHED[0].data.decode() and "cup is pressed" in PUSHED[0].data.decode()
      and h.get("click") == "https://www.amazon.com/dp/B0LOAD", PUSHED[0].data.decode() if PUSHED else "")
check("... and Muse's thread is told it went to her", any(p.get("thread_ts") == root and "Put to Gloria on her phone" in p["text"]
                                                         and "price and link" in p["text"] for p in S.posted), S.posted)
buy = [r for r in G.load() if r.get("kind") == "buy"][0]
G.decide_with_token(buy["id"], buy["token"], "yes")
n = len(S.posted)
D.tick(api=S, think=think, fable=think, now=1200, today="2026-10-06")
check("her Yes comes back in Muse's thread: she will buy it, at that price",
      any(p.get("thread_ts") == root and "Gloria said YES: she will buy 5 kg load cell ($8.90)" in p["text"] for p in S.posted[n:]), S.posted[n:])

g_root = S.add(GLORIA_USER, "[Grok Bot] Looking for the guard.\nAEGIS GREP: one 403\nAEGIS OPEN: %s" % os.path.join(HOME, "Vintos-main", ".env"))
n = len(S.posted)
D.tick(api=S, think=think, fable=think, now=1300, today="2026-10-06")
ans = [p for p in S.posted[n:] if p.get("thread_ts") == g_root]
check("Grok Bot's AEGIS lines are answered in its thread", ans and "forge_loop_runtime.py:2:" in ans[0]["text"], S.posted[n:])
check("... and a key file it asks for is refused, its contents never posted",
      ans and "not opened" in ans[0]["text"] and "sk-should-never-show" not in json.dumps(S.posted))

dsrc = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("he is told: buying goes to Muse, and Grok Bot can look on Aegis and the Mac",
      "a thing you want to buy goes to @Muse" in dsrc and "Grok Bot can now look on Aegis too" in dsrc and "MAC FIND:" in dsrc)
check("Muse, dot and Grok Bot are told", "BUY: item | price | store | link | why he wants it" in open(os.path.join(REPO, "docs", "muse", "vintos-skill.md")).read()
      and "## 14. Buying, and Grok Bot's reach" in open(os.path.join(REPO, "docs", "dot", "operating-rules.md")).read()
      and "AEGIS FIND:" in open(os.path.join(REPO, "docs", "grok-bot", "vintos-skill.md")).read())
check("the deploy installs Grok Bot's reach", " grok_reach.py " in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

import want_board as WB
check("the board parks a want the Forge marked blocked (its field is 'blocked', not only 'plan_block')",
      WB._blocked({"blocked": {"block_type": "CAPABILITY_ABSENT"}}) and WB._blocked({"plan_block": {"block_type": "X"}})
      and not WB._blocked({}))
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
