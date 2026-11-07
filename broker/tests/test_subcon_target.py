#!/usr/bin/env python3
"""The subconscious target flag (Gloria 2026-11-07): the 26B until flipped; under AEON only the constructs that
cleared the 26B's own bar are read (tier B only when opted in); the two checkpoints never mix; the generated emotion
read and /pool/subconscious move to AEON together with the flag, with no 26B fallback.

No network, no model, no ~/.vintos: HOME is a tempdir.
"""
import importlib.util, json, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "bin"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
TMP = tempfile.mkdtemp(prefix="subcon-target-")
os.environ["HOME"] = TMP
WS = os.path.join(TMP, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
os.environ["XAI_API_KEY"] = "test-xai"

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:200]) if d and not ok else ""))

import subcon_target as T
FLAG = os.path.join(TMP, ".vintos", "subcon-target.json")
OLD_URL, OLD_MODEL = "http://old-route/v1/chat/completions", "gemma-4-26b-a4b-it-uncensored"

def write_flag(obj):
    os.makedirs(os.path.dirname(FLAG), exist_ok=True)
    with open(FLAG, "w") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))

def clear():
    if os.path.exists(FLAG): os.remove(FLAG)

print("--- the flag ---")
check("no flag -> the 26B", T.active() == "gemma26b" and T.receipt()["identity"] == "gemma-4-26b-a4b-it-uncensored")
check("no flag -> generated reads keep the caller's own 26B route", T.generative_route(OLD_URL, OLD_MODEL) == (OLD_URL, OLD_MODEL))
write_flag("{not json")
check("an unreadable flag -> the 26B", T.active() == "gemma26b")
write_flag({"target": "llama"})
check("an unknown target -> the 26B", T.active() == "gemma26b")
write_flag(["aeon"])
check("a flag that is not an object -> the 26B", T.active() == "gemma26b")
clear()
try:
    T.set_target("gpt"); unknown_refused = False
except ValueError:
    unknown_refused = True
check("an unknown target cannot be set", unknown_refused and not os.path.exists(FLAG))
check("the CLI refuses an unknown target", T.main(["set", "gpt"]) == 2 and not os.path.exists(FLAG))

notes = T.set_target("aeon")
check("the flip to AEON is written atomically", T.active() == "aeon" and json.load(open(FLAG)) == {"target": "aeon"})
check("the flip names the model-level Pain checks AEON has not run", any("pain_paper_protocol" in n for n in notes), notes)
check("tier B stays off unless asked", not T.tier_b_enabled() and "Valence" not in T.admitted())
T.set_target("aeon", include_tier_b=True)
check("--tier-b adds exactly Valence L41 and Groundedness L29",
      T.tier_b_enabled() and T.admitted()["Valence"][0] == 41 and T.admitted()["Groundedness"][0] == 29 and len(T.admitted()) == 11)
check("flipping back to the 26B drops the tier-B opt-in", T.set_target("gemma26b") and T.active() == "gemma26b"
      and json.load(open(FLAG)) == {"target": "gemma26b"} and not T.tier_b_enabled())
clear()

print("--- admission (from the sealed AEON readout handoff) ---")
aeon = T.TARGETS["aeon"]
check("every construct is one of the eleven, once", set(aeon["admitted"]) | set(aeon["tier_b"]) == set(T.DIMENSIONS)
      and not (set(aeon["admitted"]) & set(aeon["tier_b"])) and set(T.TARGETS["gemma26b"]["admitted"]) == set(T.DIMENSIONS))
check("AEON reads the nine that cleared every item of the 26B bar",
      sorted(aeon["admitted"]) == ["Arousal", "Connection", "Curiosity", "Desire", "Dominance", "Playfulness", "Safety", "Tension", "Warmth"])
check("the layers are the handoff's", {k: v[0] for k, v in aeon["admitted"].items()} ==
      {"Arousal": 37, "Connection": 29, "Curiosity": 30, "Desire": 36, "Dominance": 29, "Playfulness": 29,
       "Safety": 28, "Tension": 34, "Warmth": 37})
check("every AEON direction is mean-pooled and pinned by a sha256",
      all(v[1] == "mean" and re.fullmatch(r"[0-9a-f]{64}", v[2] or "") for v in list(aeon["admitted"].values()) + list(aeon["tier_b"].values())))
check("each tier-B construct says why", all(len(v[3]) > 20 for v in aeon["tier_b"].values()))

reading = {"Arousal": 0.4, "Valence": 0.9, "Warmth": 0.3, "Tension": True, "Desire": float("nan"), "Safety": "x",
           "Curiosity": "0.2", "Groundedness": -1.0}
got = T.admitted_readings(reading, "aeon", identity=aeon["identity"], include_tier_b=False)
check("under AEON tier B has no reading; bools, NaN and junk are dropped", got == {"Arousal": 0.4, "Warmth": 0.3, "Curiosity": 0.2}, got)
got_b = T.admitted_readings(reading, "aeon", identity=aeon["identity"], include_tier_b=True)
check("with tier B opted in, Valence and Groundedness are read", got_b.get("Valence") == 0.9 and got_b.get("Groundedness") == -1.0, got_b)
check("a reading made on the other checkpoint is refused whole, never pooled",
      T.admitted_readings(reading, "aeon", identity=T.TARGETS["gemma26b"]["identity"]) == {})
check("under the 26B every construct it passed is kept", set(T.admitted_readings({"Valence": .1, "Warmth": .2}, "gemma26b")) == {"Valence", "Warmth"})

print("--- locks and the public repo ---")
for name, t in T.TARGETS.items():
    lock = json.load(open(os.path.join(REPO, t["lock"])))
    check("%s lock matches the target's identity and hash" % name, lock["identity"] == t["identity"] and lock["sha256"] == t["sha256"])
aeon_lock = json.load(open(os.path.join(REPO, aeon["lock"])))
check("the AEON lock names the same extractor revision as the 26B lock",
      aeon_lock["llama_cpp_revision"] == json.load(open(os.path.join(REPO, T.TARGETS["gemma26b"]["lock"])))["llama_cpp_revision"])
for rel in ("scripts/subcon_target.py", aeon["lock"]):
    text = open(os.path.join(REPO, rel)).read()
    addrs = [a for a in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) if a != "127.0.0.1"]
    check("%s carries no address other than loopback, and no host path" % rel, not addrs and "/Users/" not in text
          and "/home/" not in text, addrs)

print("--- shadow receipts name their instrument ---")
spec = importlib.util.spec_from_file_location("residual_shadow_subcon", os.path.join(REPO, "scripts", "residual_shadow.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
S.record(input_text="one exact line", source="exchange", turn_id="T-1", generated_deltas={"Warmth": .1})
row = S.pending()[-1]
check("a receipt under the 26B says so", row["residual_target"]["target"] == "gemma26b"
      and row["residual_target"]["sha256"] == T.TARGETS["gemma26b"]["sha256"], row.get("residual_target"))
write_flag({"target": "aeon"})
S.record(input_text="another exact line", source="exchange", turn_id="T-2", generated_deltas={"Warmth": .1})
row = S.pending()[-1]
check("after the flip a receipt names AEON and only its admitted constructs", row["residual_target"]["target"] == "aeon"
      and row["residual_target"]["admitted"] == sorted(aeon["admitted"]), row.get("residual_target"))
check("the receipt is still causally inert", row["causal_effect"] == "none_from_this_recorder")

print("--- the generated emotion read ---")
check("after the flip generated reads go through the shim's subconscious lane",
      T.generative_route(OLD_URL, OLD_MODEL) == ("http://127.0.0.1:8599/pool/subconscious/v1/chat/completions", "aeon-gemma-4-12b"))
def load_reader(tag):
    sp = importlib.util.spec_from_file_location("emotion_read_" + tag, os.path.join(REPO, "scripts", "emotion_read.py"))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
er = load_reader("aeon")
check("emotion_read.py follows the flag (endpoint and model together)", er.LM_URL.endswith("/pool/subconscious/v1/chat/completions")
      and er.MODEL == "aeon-gemma-4-12b", (er.LM_URL, er.MODEL))
check("emotion_read.py keeps its eleven-key contract and cap", list(er.DIMS) == list(T.DIMENSIONS) and er.CAP == 0.10)
clear()
er = load_reader("26b")
check("without the flag emotion_read.py is exactly as before", er.MODEL == "gemma-4-26b-a4b-it-uncensored" and er.LM_URL.endswith(":1234/v1/chat/completions"))
srv = open(os.path.join(REPO, "bin", "server.py")).read()
fn = srv[srv.index("def nudge_emotions_from_text"):srv.index("def nudge_emotions_from_text") + 9000]
check("the server's live read takes its route from the flag", "generative_route(_emo_url, _model)" in fn and "_u.Request(_emo_url," in fn)

print("--- the shim's /pool/subconscious ---")
import vintos_claude_shim as SH
clear()
check("before the flip /pool/subconscious stays on the 26B",
      SH.provider_chain({}, "/pool/subconscious/v1/chat/completions") == ["pool:subconscious", "gemma"])
write_flag({"target": "aeon"})
chain = SH.provider_chain({}, "/pool/subconscious/v1/chat/completions")
check("after the flip it goes to AEON only, never the 26B", chain == ["pool:aeon", "aegis_gemma"] and "gemma" not in chain, chain)
check("other pool tasks are untouched by the flag",
      SH.provider_chain({}, "/pool/quick/v1/chat/completions") == ["pool:quick", "aegis_gemma", "gemma"])
clear()

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
