#!/usr/bin/env python3
"""What reaches him each turn is read from the live conversation, and the live conversation keeps its rows.

- The avatar history file grows to 40 rows; it was held at 14 because each turn wrote back the 12 rows its
  prompt was given plus its own two.
- A row another writer adds while a turn is being assembled survives that turn's save.
- "Your last reply" and the ALREADY-SAID list come from the live avatar history, not from files last written
  in August.
- "Messages today" is today's count, not a key the rhythm file never had.

The functions are taken from bin/server.py by name and run in a scratch namespace: nothing is imported from
the live server, no path under ~/.vintos is touched, nothing is sent.
"""
import ast, json, os, socket, sys, tempfile, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="avatar-history-")
os.environ["HOME"] = TMP
sys.path.insert(0, os.path.join(ROOTD, "scripts"))
def _no_network(*a, **k): raise AssertionError("no network in tests")
socket.socket.connect = _no_network

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:120]) if d else ""))

SRC = open(os.path.join(ROOTD, "bin", "server.py")).read()
TREE = ast.parse(SRC)
MEMORY = os.path.join(TMP, "memory"); os.makedirs(MEMORY)
ns = {"os": os, "json": json, "time": time, "datetime": datetime, "MEMORY": MEMORY, "WORKSPACE": TMP}
fns = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in ("_append_avatar_history", "_messages_today", "_spark_block")]
check("the three functions are in the server", len(fns) == 3, [f.name for f in fns])
exec(compile(ast.Module(fns, []), "server.py", "exec"), ns)

path = os.path.join(MEMORY, "avatar-overlay-chat.json")
check("the suite writes its own scratch, not his", path.startswith(TMP))

# --- the file grows to 40, not 14
json.dump([{"role": ("user" if i % 2 == 0 else "assistant"), "content": "row %d" % i, "ts": i} for i in range(14)], open(path, "w"))
for turn in range(10):
    ns["_append_avatar_history"](path, [{"role": "user", "content": "her %d" % turn}, {"role": "assistant", "content": "his %d" % turn}])
rows = json.load(open(path))
check("the history keeps 40 rows, not the 14 the prompt sees", len(rows) == 34 and rows[-1]["content"] == "his 9", len(rows))
for turn in range(10, 20):
    ns["_append_avatar_history"](path, [{"role": "user", "content": "her %d" % turn}, {"role": "assistant", "content": "his %d" % turn}])
check("... and stops at 40", len(json.load(open(path))) == 40)

# --- a row written meanwhile survives the turn's save
before = json.load(open(path))
ns["_append_avatar_history"](path, [{"role": "assistant", "content": "voice turn written during assembly"}])
ns["_append_avatar_history"](path, [{"role": "user", "content": "her late"}, {"role": "assistant", "content": "his late"}])
after = [r["content"] for r in json.load(open(path))]
check("a row another writer added during the turn is kept", "voice turn written during assembly" in after and after[-1] == "his late")

# --- the route appends only its own new rows (static check of the call site)
route = SRC[SRC.index("_av_loaded_n = len(av_history)"):]
check("the avatar route appends only this turn's rows", "_append_avatar_history(av_chat_log, av_history[_av_loaded_n:])" in route)
check("no writer dumps the avatar history whole any more",
      "for _e in av_history[-40:]], f" not in SRC and "for _e in _avh[-40:]], open(_avh_p" not in SRC)

# --- spark block reads the live conversation
json.dump([{"role": "assistant", "content": "an August reply nobody should be shown again"}], open(os.path.join(MEMORY, "chat-history.json"), "w"))
ns["_append_avatar_history"](path, [{"role": "assistant", "content": "his newest reply here"}])
block = ns["_spark_block"]()
check("'your last reply' is his newest live reply", "his newest reply here" in block and "August reply" not in block)

# --- messages today
today = datetime.now().strftime("%Y-%m-%d")
check("messages today is today's count", ns["_messages_today"]({"daily_summary": [{"date": today, "message_count": 7}]}) == 7)
check("... and 0 when today has no row", ns["_messages_today"]({"daily_summary": [{"date": "2000-01-01", "message_count": 7}]}) == 0)
check("no prompt reads the key the rhythm file never had", "_rd.get('total_messages', 0)" not in SRC)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
