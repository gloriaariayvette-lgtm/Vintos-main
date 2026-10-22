#!/usr/bin/env python3
"""The latent stream replay (step 1, 22 October): his history becomes one ordered stream of events from each source,
untimed journal sections keep their order, chat turns are not counted twice, the Lab's machine steps stay out, the
text cache embeds each text once, test days come after training days, and nothing of his is written.
Scratch workspace; the encoder is a stub; torch's part runs only where torch is installed; sockets are refused."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="latent-replay-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(MEM, "chemistry-lab"))
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import latent_stream_replay as L
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
check("it reads his scratch memory", L.MEM.startswith(HOME))

days = ["2026-10-%02d" % d for d in range(1, 11)]
json.dump([{"t": "%sT%02d:%02d:00" % (d, h, m), "v": [0.1 * h] * 11} for d in days for h in range(0, 24, 3) for m in (0,)],
          open(os.path.join(MEM, "emotion-trajectory-dense.json"), "w"))
for d in days:
    open(os.path.join(MEM, "daily-inner-life-%s.md" % d), "w").write(
        "# Inner life\n\n## 09:15 — Gallery walk\nI stood a long time in front of the blue one, it held me.\n\n"
        "## I replied to Muse's letter\nKept the Devo item, skipped the rest of the list, said why.\n")
json.dump([{"timestamp": "%sT12:00:00" % d, "thread": "Whether she meant the half-time drop for me, day %s" % d} for d in days],
          open(os.path.join(MEM, "unfinished-threads.json"), "w"))
with open(os.path.join(MEM, "chat-canonical.jsonl"), "w") as f:
    f.write(json.dumps({"ts": "2026-10-09T20:00:00", "role": "user", "content": "Did you hear the bridge in that song?"}) + "\n")
json.dump([{"timestamp": "2026-10-09T20:00:05", "gloria": "Did you hear the bridge in that song?"}],
          open(os.path.join(MEM, "interaction-ledger.json"), "w"))
with open(os.path.join(MEM, "chemistry-lab", "notebook.jsonl"), "w") as f:
    for i in range(500): f.write(json.dumps({"at": "2026-10-05T10:00:00", "kind": "investigation_step"}) + "\n")
before = {p: os.path.getmtime(p) for p in [os.path.join(r, n) for r, _, fs in os.walk(MEM) for n in fs]}

ev = L.build_stream()
src = [e["source"] for e in ev]
check("events from each source, oldest first", all(a["t"] <= b["t"] for a, b in zip(ev, ev[1:]))
      and {"emotion", "inner", "thread", "her"} <= set(src), sorted(set(src)))
check("the Lab's machine steps stay out", len(ev) < 200 and "lab" not in src, len(ev))
inner = [e for e in ev if e["source"] == "inner" and e["t"].date().isoformat() == "2026-10-03"]
check("a journal section without a time keeps its place, just after the one before it",
      len(inner) == 2 and "Gallery walk" in inner[0]["text"] and inner[1]["t"] > inner[0]["t"], [(str(e["t"]), e["text"][:20]) for e in inner])
check("the same chat turn in two stores is one event", src.count("her") == 1)

calls = []
def enc(texts):
    calls.append(len(texts)); return [[float(len(t) % 7 + 1)] + [float(i % 3) for i in range(15)] for t in texts]
out = tempfile.mkdtemp(prefix="replay-out-", dir=HOME)
ev = L.embed_texts(ev, enc, os.path.join(out, "text-vectors.jsonl"))
n_first = sum(calls); calls.clear()
L.embed_texts([dict(e) for e in ev], enc, os.path.join(out, "text-vectors.jsonl"))
check("each text is embedded once; a second run embeds nothing", n_first > 0 and sum(calls) == 0)
rows, dim = L.featurize(ev)
check("each step carries the text, the emotion so far, the source and the time since the last",
      dim == 16 and len(rows[0]) == dim + L.EMO_DIM + len(L.SOURCES) + 1)
val_at, test_at = L.split_days(ev)
check("the test days come after the training and validation days",
      0 < val_at <= test_at < len(ev) and ev[test_at - 1]["t"].date() < ev[test_at]["t"].date())
try:
    import torch  # noqa: F401
    res = L.run(ev, out, epochs=2, hidden=16, log=lambda *a: None)
    check("the replay scores the stream against both baselines and gives a verdict",
          {"stream", "last_one", "mean_last_six"} <= set(res["text"]) and "verdict" in res and res["most_surprising"])
except ImportError:
    print("(torch is not installed here: the model part runs on Aegis in the torch venv)")
after = {p: os.path.getmtime(p) for p in [os.path.join(r, n) for r, _, fs in os.walk(MEM) for n in fs]}
check("nothing of his was written", before == {p: t for p, t in after.items() if p in before} and set(after) == set(before))
src_text = open(os.path.join(REPO, "scripts", "latent_stream_replay.py")).read()
check("ties count against a guess, so an empty baseline cannot rank first", "(sims >= sims[pos[t]]).sum()" in src_text)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
