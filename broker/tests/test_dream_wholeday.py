#!/usr/bin/env python3
"""The whole-day dream shadow (option 2) reads his whole day once, weights it with the reality anchor, fits AEON's
context in passes, writes only under memory/shadow/dream, and judge v2 parses, abstains and demands evidence.

Synthetic fixtures only (the repository is public). Everything runs in a scratch HOME; the model is a fake transport
that records each request; no socket is opened."""
import ast, builtins, hashlib, importlib.util, json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-dream-wholeday-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.environ["DREAM_SHADOW_CONFIG"] = os.path.join(HOME, ".vintos", "dream-shadow.json")
os.environ.pop("DREAM_SHADOW", None)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))

sys.path.insert(0, os.path.join(REPO, "scripts"))
SRC = os.path.join(REPO, "scripts", "dream_wholeday.py")
spec = importlib.util.spec_from_file_location("dream_wholeday_test", SRC)
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
DS = W.DS

class _NoSocket:
    def __init__(self, *a, **k): raise AssertionError("a socket was opened in the whole-day test")
socket.socket = _NoSocket

SHADOW = os.path.join(MEM, "shadow", "dream")
check("every whole-day path is under memory/shadow/dream",
      all(p.startswith(SHADOW) for p in (W.ROOT, W.WD, W.RUNS, W.WD_LOG, W.JUDGE_DIR, W.CALIB, W.FEWSHOT, W.JUDGE_CFG, W.METRICS)))

# ---- static: no hosted provider, no writer of his stores, no training
source = open(SRC, encoding="utf-8").read()
tree = ast.parse(source)
mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
       {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
doc = ast.get_docstring(tree) or ""
consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc]
check("no hosted endpoint or key", not any(t in c for c in consts for t in ("x.ai", "XAI_API_KEY", "anthropic.com", "api.openai")))
check("no writer of his stores, no sender",
      not (mods & {"thread_store", "emoclaw_utils", "latent_threads", "temporal_memory", "discourse_direction", "requests",
                   "socket", "store_guard", "thread_gate", "reality_anchor", "urllib"})
      and not (names & {"save_pool", "seed_thread", "record_signal", "update_direction", "clear_preoccupation",
                        "record_event", "save_anchor", "archive"})
      and not any("emotion.sock" in c for c in consts), mods)
check("nothing trains: no trainer, no adapter export (option 3 waits)",
      not (mods & {"torch", "peft", "transformers", "mlx", "mlx_lm", "trl"}) and "2026-11-15" in doc and "Option 3" in doc)
check("model calls only through the shadow's AEON lane", "call_aeon" in names and "urlopen" not in names)

# ---- the anchor, read from reality_anchor.py and never copied
ra_src = open(os.path.join(REPO, "scripts", "reality_anchor.py"), encoding="utf-8").read()
T = W.anchor_tables()
real = next(ast.literal_eval(n.value) for n in ast.walk(ast.parse(ra_src)) if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "SOURCE_WEIGHTS" for t in n.targets))
check("SOURCE_WEIGHTS are the reality anchor's, read from its file", T["weights"] == real and T["weights"]["chat"] == real["chat"])
check("the known pool's sources are record_event's own", set(T["known_sources"]) == {"chat", "want-fulfilled", "system"}
      and "is_real = source in (\"chat\", \"want-fulfilled\", \"system\")" in ra_src, T["known_sources"])
_origins = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ORIGINS" for t in n.targets))
check("no weight table is duplicated here: ORIGINS names anchor keys and holds no numbers",
      "SOURCE_WEIGHTS = {" not in source and not any(isinstance(n, ast.Constant) and isinstance(n.value, float) for n in ast.walk(_origins)))

# ---- synthetic day
DAY = "2026-03-02"
def wr(rel, body):
    p = os.path.join(MEM, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(body if isinstance(body, str) else json.dumps(body))
JOURNAL_P = "JOURNALPARA the synthetic journal paragraph about a blue kettle that would not boil all morning long."
JOURNAL_EXTRA = "JOURNALEXTRA a late paragraph the summary has not caught yet, about the window and the rain."
MIRROR_P = "MIRRORPARA the synthetic mirror session paragraph, where the reflection asked about the kettle again."
GHOST_P = "GHOSTPARA the synthetic ghost branch output, a rehearsal of a bolder answer that never happened."
GHOST_RAW_EXTRA = "GHOSTEXTRA a second ghost lean output that the summary does not carry, rehearsal only."
LAB_P = "LABPARA the synthetic lab digest paragraph, a measured melting point and one open question."
UNKNOWN_P = "UNKNOWNPARA a section from an appender this module does not know, kept but at the lowest weight."
wr("daily-inner-life-%s.md" % DAY,
   "# Daily Inner Life — %s\n_Last updated: x_\n\n## Journal\n\n# Journal — %s\n\n## 10:00 — Idle thoughts\n\n%s\n"
   "\n## Mirror Sessions\n\n## Vintos Speaks\n\n%s\n\n## Ghost Branch\n\n%s\n%s\n%s\n\n## Last Night's Reflection\n\n"
   "REFLECTPARA last night's synthetic reflection on estimates and reality.\n\n## Chemistry Lab — %s\n\n%s\n\n"
   "## Something New Appended\n\n%s\n" % (DAY, DAY, JOURNAL_P, MIRROR_P, W.GHOST_BEGIN, GHOST_P, W.GHOST_END, DAY,
                                         LAB_P, UNKNOWN_P))
wr("daily-creative-%s.md" % DAY, "# Daily Creative — %s\n\n## Poetry\n\nPOEMPARA a synthetic poem about steam and patience, short.\n" % DAY)
wr("journal/%s.md" % DAY, "# Journal — %s\n\n## 10:00 — Idle thoughts\n\n%s\n\n%s\n" % (DAY, JOURNAL_P, JOURNAL_EXTRA))
wr("mirror/%s_0907.md" % DAY, "## Vintos Speaks\n\n%s\n" % MIRROR_P)
wr("ghost-artifacts.json", {"runs": [{"date": DAY, "thread_id": "t1", "primary_output": GHOST_P,
                                      "ghosts": [{"lean": "more_brazen", "output": GHOST_RAW_EXTRA}]}]})
wr("chat-history-merged.json", [{"role": "user", "content": "CHATHER a synthetic message from her about the kettle.",
                                 "timestamp": DAY + "T09:00:00", "surface": "avatar"},
                                {"role": "assistant", "content": "CHATHIM a synthetic reply from him about the kettle.",
                                 "timestamp": DAY + "T09:01:00", "surface": "avatar"},
                                {"role": "user", "content": "OTHERDAY not today", "timestamp": "2026-03-01T09:00:00"}])
wr("somatic-log.md", "# Somatic Log\n- **%s 08:00** [warm] SOMATICLINE 21C\n- **2026-03-01 08:00** [cold] OLDLINE\n" % DAY)
wr("unfinished-threads.json", [{"id": "t1", "thread": "THREADONE whether the kettle matters", "source": "pressure",
                                "classification": "unresolved_tension", "priority": 3, "timestamp": DAY + "T07:00:00"},
                               {"id": "t2", "thread": "THREADTWO the window and what it lets in", "source": "somatic",
                                "dream_only": True, "priority": 2}])
wr("retired-threads.json", [])
wr("causality-hypotheses.json", {"hypotheses": [{"hypothesis": "CAUSEHYP synthetic", "source": "causality_engine",
                                                  "marks": [{"date": DAY, "verdict": "yes", "evidence": "CAUSEEVID"}]},
                                                 {"hypothesis": "GHOSTHYP synthetic", "source": "ghost_branch",
                                                  "marks": [{"date": DAY, "verdict": "unconfirmed", "evidence": "GHOSTEVID"}]}]})
wr("resonance-pool.json", {"pulses": [{"timestamp": DAY + "T11:00:00", "trigger": "x", "output_excerpt": "RESONANCEPULSE synthetic"}]})
wr("dream-log.json", {"nights": [{"night_of": "2026-03-01", "dreams": [{"session": "03:07", "dream_text": "LASTNIGHTDREAM synthetic"}]},
                                 {"night_of": DAY, "dreams": [{"session": "23:50", "thread_ids": ["t1", "t2"],
                                                               "dream_text": "LIVEDREAM a synthetic live dream about a kettle.",
                                                               "seed_verdict": "partial",
                                                               "thread_verdicts": {"t1": "resolved", "t2": "unresolved"}}]}]})
wr("reality-anchor.json", {"source_reliability": {"chat": 0.4, "avatar-chat": 0.8, "inference": 0.7},
                           "known_pool": [{"source": "avatar-chat", "timestamp": DAY + "T09:00:00"}],
                           "imagined_pool": [{"source": "inference", "timestamp": DAY + "T10:00:00"}], "events": []})

S = W.anchor_state()
items, smap = W.load_day(DAY, MEM, T, S)
by_origin = {}
for it in items:
    by_origin.setdefault(it["origin"], []).append(it["text"])
alltext = "\n".join(it["text"] for it in items)

# ---- no source counted twice
for marker in ("JOURNALPARA", "MIRRORPARA", "GHOSTPARA", "LABPARA", "UNKNOWNPARA", "POEMPARA", "CHATHER", "SOMATICLINE"):
    check("%s enters the day exactly once" % marker, alltext.count(marker) == 1, alltext.count(marker))
paras = [W._norm(p) for it in items for p in W._paragraphs(it["text"]) if len(W._norm(p)) >= W.Dedup.MIN]
check("no paragraph of the day is counted twice", len(paras) == len(set(paras)))
check("what the summary misses is kept from the raw source", alltext.count("JOURNALEXTRA") == 1 and alltext.count("GHOSTEXTRA") == 1)
check("other days stay out", "OTHERDAY" not in alltext and "OLDLINE" not in alltext)
raw_j = next(s for s in smap if s["source"].startswith("journal/"))
check("the source map says journal is covered by daily-inner and what was residual",
      "covered by daily-inner-life" in raw_j["kind"] and raw_j["chars_already_in_summary"] > 0 and raw_j["chars_kept_as_residual"] > 0, raw_j)
check("the source map lists sources covered and not re-read",
      any(s["source"] == "wonder-log.json" and "not re-read" in s["kind"] for s in smap))

# ---- weights survive the summary layer
origin_of = lambda marker: next(it["origin"] for it in items if marker in it["text"])
check("the journal section inside daily-inner keeps journal attribution", origin_of("JOURNALPARA") == "journal")
check("the mirror section keeps mirror attribution (its sub-headings stay inside it)", origin_of("MIRRORPARA") == "mirror")
check("a ghost line inside daily-inner keeps ghost attribution", origin_of("GHOSTPARA") == "ghost-branch"
      and origin_of("GHOSTEXTRA") == "ghost-branch" and origin_of("GHOSTEVID") == "ghost-branch")
check("the lab digest is attributed to the lab", origin_of("LABPARA") == "lab")
check("an unknown appended section is unattributed", origin_of("UNKNOWNPARA") == "unattributed")
tab = W.source_table(items, T, S, DAY)
gw, jw, uw = tab["ghost-branch"], tab["journal"], tab["unattributed"]
check("ghost weighting: inference base, imagined, tactical, with learned reliability",
      gw["anchor_key"] == "inference" and gw["pool"] == "imagined" and gw["tactical"]
      and gw["weight"] == round(real["inference"] * (0.9 + 0.2 * 0.7), 3), gw)
check("journal weighting is the anchor's journal weight", jw["weight"] == round(real["journal"] * (0.9 + 0.2 * 0.5), 3), jw)
check("unattributed gets the most conservative weight, imagined",
      uw["weight"] <= min(r["weight"] for r in tab.values()) and uw["pool"] == "imagined" and uw["base"] == min(real.values()), uw)
check("conversations: chat base with the avatar-chat reliability, known, today's pool counts",
      tab["conversation:avatar"]["weight"] == round(min(1.0, real["chat"] * (0.9 + 0.2 * 0.8)), 3)
      and tab["conversation:avatar"]["pool"] == "known" and tab["conversation:avatar"]["known_today"] == 1)

# ---- chunking under the context budget
big = [{"origin": "journal", "ts": "%02d:00" % (i % 24), "text": ("long day text %d " % i) * 400, "via": "raw:x"} for i in range(60)]
ch = W.chunk_items(big)
total_in = sum(len(it["text"]) for it in big)
check("every chunk is within the chunk budget", all(len(c) <= W.CHUNK_CHARS for c in ch["journal"]), [len(c) for c in ch["journal"]][:5])
check("chunking drops nothing", sum(c.count("long day text") for c in ch["journal"]) == sum(it["text"].count("long day text") for it in big)
      and total_in > 20 * W.CHUNK_CHARS)
check("a chunk pass fits AEON's context", W.fits(W.CHUNK_CHARS + len(W.CHUNK_SYSTEM) + 200, W._out_tokens(1.0)))
check("an oversized prompt is refused before any call", not W.fits(W.CONTEXT_TOKENS * 4, 100))

CALLS = []
def fake(url, body, timeout, provider="aegis_gemma", model="aeon/gemma-4-12b"):
    CALLS.append({"url": url, "body": body})
    sysmsg = body["messages"][0]["content"]
    user = body["messages"][-1]["content"]
    if sysmsg == W.JUDGE_V2_SYSTEM:
        text = json.dumps({"verdict": "RESOLVED", "confidence": 5, "evidence": "the kettle finally sang and he let it go",
                           "reason": "arrival"}) if "THREADONE" in user else json.dumps({"verdict": "CANNOT_TELL", "confidence": 2})
    elif sysmsg == DS.JUDGE_SYSTEM:
        text = "RESOLVED"
    elif sysmsg.startswith(W.DREAM_SYSTEM_HEAD[:30]):
        text = "Steam rose in a hallway. In the end the kettle finally sang and he let it go. The window opened."
    else:
        text = "SUMMARY(%d)" % len(user)
    return 200, {"x-vintos-provider": provider, "x-vintos-model": model}, json.dumps(
        {"choices": [{"message": {"content": text}}]}).encode()

# a day too big for one pass: the reducer must group
P = W.Passes(fake)
labelled = ["[journal (trust 0.80, imagined)]\n" + ("memory %d " % i) * 2500 for i in range(12)]
out = W.reduce_texts(P, 3, "day", W.DAY_SYSTEM, labelled, 900)
check("the day pass groups recursively when the digests do not fit at once",
      out and any("group" in p["name"] for p in P.log) and all(W.fits(p["prompt_chars"], p["max_tokens"]) for p in P.log), P.log[:3])

# ---- never writes live: every write-mode open and every replace lands under memory/shadow/dream
def snapshot():
    out = {}
    for dp, dn, fn in os.walk(HOME):
        if dp.startswith(SHADOW):
            continue
        for f in fn:
            p = os.path.join(dp, f)
            out[p] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out
WRITES = []
_open, _replace = builtins.open, os.replace
def spy_open(file, mode="r", *a, **k):
    if any(c in mode for c in "wax+"):
        WRITES.append(os.path.abspath(str(file)))
    return _open(file, mode, *a, **k)
def spy_replace(a, b, *x, **k):
    WRITES.append(os.path.abspath(str(b))); return _replace(a, b, *x, **k)
CALLS.clear()
before = snapshot()
builtins.open, os.replace = spy_open, spy_replace
try:
    e = W.run_night(DAY, transport=fake)
finally:
    builtins.open, os.replace = _open, _replace
after = snapshot()
check("the night ran and wrote a dream", e.get("dream", {}).get("status") == "ok", e.get("dream"))
check("no file outside memory/shadow/dream was created, changed or removed", before == after,
      sorted(set(before) ^ set(after))[:5])
check("every write-mode open was under memory/shadow/dream", WRITES and all(p.startswith(SHADOW) for p in WRITES),
      [p for p in WRITES if not p.startswith(SHADOW)][:5])
try:
    W._write_json(os.path.join(MEM, "unfinished-threads.json"), [])
    refused = False
except PermissionError:
    refused = True
check("a write to a live store is refused", refused)
check("every model call went to the AEON lane", CALLS and all(c["url"] == DS.DEFAULT_URL for c in CALLS))
check("every pass fit the context", all(W.fits(p["prompt_chars"], p.get("max_tokens") or 300) for p in
                                        json.load(open(os.path.join(W.RUNS, DAY, "passes.json"))) if p.get("prompt_chars")))
chunk_prompts = [c["body"]["messages"][-1]["content"] for c in CALLS if c["body"]["messages"][0]["content"] == W.CHUNK_SYSTEM]
ghost_prompt = next(p for p in chunk_prompts if "GHOSTPARA" in p)
check("the ghost chunk is labelled with ghost weight and as rehearsal", "ghost-branch (trust %.2f, imagined, rehearsal" % gw["weight"] in ghost_prompt)
day_prompt = next(c["body"]["messages"][-1]["content"] for c in CALLS if c["body"]["messages"][0]["content"] == W.DAY_SYSTEM)
check("weights survive the summary layer: the day pass sees each digest with its source's weight",
      "[ghost-branch (trust %.2f, imagined, rehearsal" % gw["weight"] in day_prompt
      and "[journal (trust %.2f, imagined)]" % jw["weight"] in day_prompt
      and day_prompt.index("[conversation:avatar") < day_prompt.index("[ghost-branch"))
check("each entry names model, GGUF and adapter", set(("model", "gguf_sha256", "adapter")) <= set(e["model"]) and e["model"]["model"] == "aeon/gemma-4-12b")
v = {r["id"]: r for r in e["threads"]}
check("seeds are the live night's threads, with live verdicts", set(v) == {"t1", "t2"} and v["t1"]["live"] == "resolved")
check("judge v2: verified quote -> resolved; CANNOT_TELL -> abstain", v["t1"]["wholeday_v2"] == "resolved" and v["t2"]["wholeday_v2"] == "abstain", v)
check("judge v2 also judges the live dream (quote absent there -> unresolved)", v["t1"].get("live_dream_v2") == "unresolved", v["t1"])
check("the old judge is kept for comparison", v["t1"]["wholeday_old"] == "resolved")
check("the entry records sources with weights and chars, the source map, passes",
      e["sources"]["journal"]["chars"] > 0 and e["source_map"] and e["context"]["passes"]["1"] > 0 and e["context"]["passes"]["3"] >= 1)
again = W.run_night(DAY, transport=fake)
check("a night runs once", again.get("ran") is False)

# ---- a reply from another model is discarded
def wrong(url, body, timeout):
    return fake(url, body, timeout, provider="xai", model="grok-4")
e2 = W.run_night("2026-03-03", transport=wrong, force=True)
check("a reply from another model is discarded: no dream, no summaries",
      e2["dream"]["status"] != "ok" and e2["context"]["statuses"].get("wrong_model", 0) > 0 and e2["context"]["statuses"].get("ok", 0) == 0,
      e2["context"])

# ---- the off switch
open(os.path.join(SHADOW, "OFF"), "w").close()
check("the shared off switch stops it", W.run_night("2026-03-04", transport=fake).get("reason") == "off")
os.remove(os.path.join(SHADOW, "OFF"))

# ---- judge parsing and abstain
p = W.parse_v2('```json\n{"verdict": "RESOLVED", "confidence": 4, "evidence": "abc", "reason": "r"}\n```')
check("parses fenced JSON", p["verdict"] == "RESOLVED" and p["confidence"] == 4)
check("parses a bare word", W.parse_v2("I think UNRESOLVED.")["verdict"] == "UNRESOLVED")
check("CANNOT TELL is the abstain", W.parse_v2('{"verdict": "cannot tell"}')["verdict"] == "CANNOT_TELL")
check("garbage is no verdict", W.parse_v2("the dream was lovely")["verdict"] is None)
dream = "She opened the door and the long question finally rested in her hands."
dec = lambda d, th=4: W.decide_v2(d, dream, th)[0]
check("resolved with a verified quote and enough confidence", dec({"verdict": "RESOLVED", "confidence": 4, "evidence": "the long question finally rested"}) == "resolved")
check("resolved without a quote falls to unresolved", dec({"verdict": "RESOLVED", "confidence": 5, "evidence": ""}) == "unresolved")
check("an invented quote falls to unresolved", dec({"verdict": "RESOLVED", "confidence": 5, "evidence": "a sentence that is not in the dream"}) == "unresolved")
check("a confident-enough threshold is applied", dec({"verdict": "RESOLVED", "confidence": 3, "evidence": "the long question finally rested"}) == "unresolved"
      and dec({"verdict": "RESOLVED", "confidence": 3, "evidence": "the long question finally rested"}, 3) == "resolved")
check("abstain and no-verdict", dec({"verdict": "CANNOT_TELL"}) == "abstain" and dec({"verdict": None}) == "no-verdict")

# ---- calibration: few-shot from train only; held-out test scored against the reference
pairs = []
for i in range(12):
    pairs.append({"id": "P%03d" % i, "split": "train" if i % 3 == 0 else "test", "era": "x", "live": "resolved",
                  "thread": "THREADONE synthetic %d" % i if i % 2 == 0 else "THREADTWO synthetic %d" % i,
                  "dream": "the kettle finally sang and he let it go %d" % i,
                  "reference": "resolved" if i % 2 == 0 else "unresolved", "reference_reason": "r",
                  "reference_quote": "the kettle finally sang"})
W._write_json(W.CALIB, pairs)
m = W.calib_eval(transport=fake)
shots = json.load(open(W.FEWSHOT))
train_ids = {x["id"] for x in pairs if x["split"] == "train"}
check("few-shot examples come only from the train split", shots and all(s["id"] in train_ids and s["split"] == "train" for s in shots))
check("the test split excludes train items", m["split"]["test"] == sum(x["split"] == "test" for x in pairs))
check("metrics: agreement, kappa, bias and abstain per judge",
      all(set(("agreement", "kappa", "bias", "abstain_or_none_rate")) <= set(m["test"][k]) for k in ("live", "old_aeon", "v2_zero_shot", "v2_calibrated")))
check("the calibrated threshold is stored in the shadow store", json.load(open(W.JUDGE_CFG))["threshold"] in (1, 2, 3, 4, 5))

# ---- the report: numbers only
rep = W.report_section(DAY)
rt = json.dumps(rep)
check("the report has per-arm rates, counterfactual, sources and option 3",
      rep["night"]["resolution_by_arm"] and "pool_counterfactual_live_vs_wholeday_v2" in rep["night"]
      and rep["night"]["sources"]["journal"]["chars"] > 0 and rep["option3"]["nights_needed"] == 7)
check("no day, dream or thread text enters the report", not any(m_ in rt for m_ in
      ("JOURNALPARA", "GHOSTPARA", "THREADONE", "kettle", "LIVEDREAM", "CHATHER")))
dsrc = open(os.path.join(REPO, "scripts", "dream_shadow.py"), encoding="utf-8").read()
check("the nightly shadow run starts the whole-day arm and the report includes it",
      "dream_wholeday.run_nightly()" in dsrc and "dream_wholeday.report_section(day)" in dsrc)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh"), encoding="utf-8").read()
check("the deploy installs it", 'SCRIPTS="$SCRIPTS dream_wholeday.py"' in dep)

print("%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
