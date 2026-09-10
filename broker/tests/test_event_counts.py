#!/usr/bin/env python3
"""Review item 386 (2026-09-10): after a known number of turns through the one post-turn, the
records count exactly, every background writer launched exactly once per turn, and no forbidden
effect happened - zero device sends, zero provider calls, zero files outside the scratch tree.
The post-turn is the real function from bin/server.py, extracted by AST like the P02 suite does."""
import os, sys, ast, json, types, tempfile, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-counts-")
os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

def snapshot(root):
    out = {}
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x not in (".git", "__pycache__")]
        for f in fs:
            p = os.path.join(d, f)
            try: out[p] = os.path.getmtime(p)
            except OSError: continue          # dangling symlink
    return out

src = open(os.path.join(REPO, "bin", "server.py"), errors="replace").read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_post_turn")
code = ast.get_source_segment(src, fn)

launched, device_sends, provider_calls = [], [], []
class FakePopen:
    def __init__(self, argv, **kw):
        launched.append((os.path.basename(argv[1]) if len(argv) > 1 else "?", kw.get("env", {}).get("VINTOS_TURN_ID")))
_orig = subprocess.Popen; subprocess.Popen = FakePopen
# forbidden effects: a device send or a provider call reached from the post-turn would land here
fake_tl = types.ModuleType("toy_link"); fake_tl.parse_and_send = lambda *a, **k: device_sends.append(a); fake_tl.send = lambda *a, **k: device_sends.append(a)
fake_rq = types.ModuleType("requests"); fake_rq.post = lambda *a, **k: provider_calls.append(a); fake_rq.get = lambda *a, **k: provider_calls.append(a)
sys.modules["toy_link"] = fake_tl; sys.modules["requests"] = fake_rq
ns = {"os": os, "WORKSPACE": WS, "MEMORY": MEM, "_test_mode_active": lambda: False, "print": lambda *a, **k: None}
exec(code, ns)
for f in ("self-prediction.py", "wal-extract.py", "imprint.py", "interaction-ledger.py", "voice-coherence.py"):
    open(os.path.join(WS, "scripts", f), "w").write("")

outside_before = snapshot(REPO)
N = 5
SKIP = ("nudge_gloria", "compare", "direction", "curiosity", "predict", "adopt", "marks")
for i in range(N):
    ns["_post_turn"]("chat", "hello there, turn %d" % i, "a reply for turn %d" % i, skip=SKIP,
                     writer_env={"VINTOS_TURN_ID": "T%d" % i}, test_mode=False)
subprocess.Popen = _orig

print("\n--- expected completed-event counts ---")
recs = [json.loads(l) for l in open(os.path.join(MEM, "post-turn-record.jsonl"))]
check("exactly %d post-turn records" % N, len(recs) == N, len(recs))
check("each record carries its own turn id, in order", [r.get("turn_id") for r in recs] == ["T%d" % i for i in range(N)], [r.get("turn_id") for r in recs])
per_turn = {}
for name, tid in launched:
    per_turn.setdefault(tid, []).append(name)
check("every turn launched the same writer set", len(per_turn) == N and len({tuple(sorted(v)) for v in per_turn.values()}) == 1, per_turn)
writers = sorted(per_turn.get("T0", []))
check("the background writers launched once each per turn", writers and len(writers) == len(set(writers)), writers)
check("the record's launched count matches the launches", all(len(r.get("launched", [])) == len(per_turn.get(r.get("turn_id"), [])) for r in recs), [(r.get("turn_id"), r.get("launched"), per_turn.get(r.get("turn_id"))) for r in recs[:2]])
check("skipped items are declared by name", all(set(SKIP) <= set(x.split(":")[0] for x in r.get("skipped", [])) for r in recs), recs[0].get("skipped"))

print("\n--- absence of forbidden effects ---")
check("zero device sends", device_sends == [], device_sends)
check("zero provider calls", provider_calls == [], provider_calls)
outside_after = snapshot(REPO)
changed = [p for p, m in outside_after.items() if outside_before.get(p) != m] + [p for p in outside_before if p not in outside_after]
check("no file outside the scratch tree changed", not changed, changed[:5])
written = snapshot(MEM)
check("the only memory file written is the post-turn record", set(os.path.basename(p) for p in written) == {"post-turn-record.jsonl"}, sorted(os.path.basename(p) for p in written))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
