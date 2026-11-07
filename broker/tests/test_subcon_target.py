#!/usr/bin/env python3
"""The subconscious target flag (Gloria 2026-11-07): the 26B until flipped; AEON only for constructs that cleared
the 26B's own Pain-axis bar; the flip is refused while a model-level item is unmet; the two checkpoints never mix.

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

def write_flag(obj):
    os.makedirs(os.path.dirname(FLAG), exist_ok=True)
    with open(FLAG, "w") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))

print("--- the flag ---")
check("no flag -> the 26B", T.active() == "gemma26b" and T.receipt()["identity"] == "gemma-4-26b-a4b-it-uncensored")
write_flag("{not json")
check("an unreadable flag -> the 26B", T.active() == "gemma26b")
write_flag({"target": "llama"})
check("an unknown target -> the 26B", T.active() == "gemma26b")
write_flag({"target": "aeon"})
check("a hand-written AEON flag is ignored while the Pain model-level tests are unrun", T.active() == "gemma26b")
os.remove(FLAG)

try:
    T.set_target("aeon"); refused = False
except ValueError as e:
    refused = "pain_paper_protocol" in str(e) and "pain_prompt_variants" in str(e)
check("the flip to AEON is refused while the Pain model-level tests are unrun", refused and not os.path.exists(FLAG))
try:
    T.set_target("gpt"); unknown_refused = False
except ValueError:
    unknown_refused = True
check("an unknown target cannot be set", unknown_refused and not os.path.exists(FLAG))
check("the CLI refusal exits non-zero and writes nothing", T.main(["set", "aeon"]) == 2 and not os.path.exists(FLAG))

saved = dict(T.TARGETS["aeon"]["model_gates"])
T.TARGETS["aeon"]["model_gates"] = {k: "pass" for k in saved}
check("with the model-level tests passed, the flip is written", T.set_target("aeon") == "aeon" and T.active() == "aeon"
      and json.load(open(FLAG)) == {"target": "aeon"})
check("flipping back to the 26B is always allowed", T.set_target("gemma26b") == "gemma26b" and T.active() == "gemma26b")
T.TARGETS["aeon"]["model_gates"] = saved
PASSED_GATES = {k: "pass" for k in saved}   # stands in for the sealed Pain results in the sections below

print("--- admission ---")
aeon = T.TARGETS["aeon"]
check("every construct is one of the eleven", set(aeon["admitted"]) | set(aeon["blocked"]) == set(T.DIMENSIONS)
      and set(T.TARGETS["gemma26b"]["admitted"]) == set(T.DIMENSIONS))
check("admitted and blocked never overlap", not (set(aeon["admitted"]) & set(aeon["blocked"])))
check("AEON reads only the eight constructs that cleared the 26B bar",
      sorted(aeon["admitted"]) == ["Arousal", "Connection", "Curiosity", "Desire", "Dominance", "Playfulness", "Safety", "Tension"])
check("each blocked construct says why", all(len(v) > 20 for v in aeon["blocked"].values()))
check("every admitted direction is mean-pooled at a real layer",
      all(p == "mean" and isinstance(l, int) and 0 < l < 64 for t in T.TARGETS.values() for l, p in t["admitted"].values()))

reading = {"Arousal": 0.4, "Valence": 0.9, "Warmth": 0.3, "Tension": True, "Desire": float("nan"), "Safety": "x", "Curiosity": "0.2"}
got = T.admitted_readings(reading, "aeon", identity=aeon["identity"])
check("under AEON a blocked construct has no reading; bools, NaN and junk are dropped", got == {"Arousal": 0.4, "Curiosity": 0.2}, got)
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
    check("%s carries no address or host path" % rel, not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text) and "/Users/" not in text
          and "/home/" not in text)

print("--- shadow receipts name their instrument ---")
spec = importlib.util.spec_from_file_location("residual_shadow_subcon", os.path.join(REPO, "scripts", "residual_shadow.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
S.record(input_text="one exact line", source="exchange", turn_id="T-1", generated_deltas={"Warmth": .1})
row = S.pending()[-1]
check("a receipt under the 26B says so", row["residual_target"]["target"] == "gemma26b"
      and row["residual_target"]["sha256"] == T.TARGETS["gemma26b"]["sha256"], row.get("residual_target"))
write_flag({"target": "aeon"})
S.record(input_text="blocked line", source="exchange", turn_id="T-B", generated_deltas={"Warmth": .1})
check("an AEON flag before the Pain tests pass still records the 26B", S.pending()[-1]["residual_target"]["target"] == "gemma26b")
T.TARGETS["aeon"]["model_gates"] = dict(PASSED_GATES)
S.record(input_text="another exact line", source="exchange", turn_id="T-2", generated_deltas={"Warmth": .1})
row = S.pending()[-1]
check("after the flip a receipt names AEON and only its admitted constructs", row["residual_target"]["target"] == "aeon"
      and row["residual_target"]["admitted"] == sorted(aeon["admitted"]), row.get("residual_target"))
check("the receipt is still causally inert", row["causal_effect"] == "none_from_this_recorder")

print("--- the shim's /pool/subconscious ---")
import vintos_claude_shim as SH
os.remove(FLAG)
check("before the flip /pool/subconscious stays on the 26B",
      SH.provider_chain({}, "/pool/subconscious/v1/chat/completions") == ["pool:subconscious", "gemma"])
write_flag({"target": "aeon"})
chain = SH.provider_chain({}, "/pool/subconscious/v1/chat/completions")
check("after the flip it goes to AEON only, never the 26B", chain == ["pool:aeon", "aegis_gemma"] and "gemma" not in chain, chain)
check("other pool tasks are untouched by the flag",
      SH.provider_chain({}, "/pool/quick/v1/chat/completions") == ["pool:quick", "aegis_gemma", "gemma"])
T.TARGETS["aeon"]["model_gates"] = saved
check("with the Pain tests unrun the shim keeps the 26B even under an AEON flag",
      SH.provider_chain({}, "/pool/subconscious/v1/chat/completions") == ["pool:subconscious", "gemma"])
os.remove(FLAG)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
