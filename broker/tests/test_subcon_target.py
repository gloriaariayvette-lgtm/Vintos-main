#!/usr/bin/env python3
"""The subconscious target flag (Gloria 2026-11-07: "IT HAS TO ALL PASS"). The 26B until flipped. The flip to AEON
is refused while any item of the 26B's full bar is unmet, and the refusal names each one; it is allowed only by a
complete, valid, pinned pass record; malformed or tampered records are refused; there is no partial switch.

No network, no model, no ~/.vintos: HOME is a tempdir.
"""
import copy, hashlib, importlib.util, json, os, re, sys, tempfile

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
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

import subcon_target as T
FLAG = os.path.join(TMP, ".vintos", "subcon-target.json")
OLD_URL, OLD_MODEL = "http://old-route/v1/chat/completions", "gemma-4-26b-a4b-it-uncensored"
REAL_RECORD, REAL_PIN = T.RECORD, T.RECORD_SHA256

def write_flag(obj):
    os.makedirs(os.path.dirname(FLAG), exist_ok=True)
    with open(FLAG, "w") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))

def clear():
    if os.path.exists(FLAG): os.remove(FLAG)

def use_record(rec_or_text, pin=True):
    """Point the module at a scratch record; pin its hash unless pin=False (then the pin stays stale)."""
    p = os.path.join(TMP, "record-%d.json" % len(R))
    raw = (rec_or_text if isinstance(rec_or_text, str) else json.dumps(rec_or_text)).encode()
    open(p, "wb").write(raw)
    T.RECORD = p
    if pin: T.RECORD_SHA256 = hashlib.sha256(raw).hexdigest()
    return p

def refused(name="aeon"):
    try:
        T.set_target(name); return None
    except ValueError as e:
        return str(e)

print("--- the real pinned record (the Codex's sealed results as of 2026-11-07) ---")
real, problems = T.load_record()
check("the shipped record matches its pinned sha256 and schema", real is not None and not problems, problems)
missing = T.unmet()
check("it names exactly what has not passed: Pain (both), Valence and Groundedness semantic review",
      missing == ["Pain paper protocol: not_run", "Pain prompt ablations: not_run",
                  "Valence: semantic review failed", "Groundedness: semantic review failed"], missing)
msg = refused()
check("so the flip is refused, listing every unmet item", msg and all(m in msg for m in missing) and not os.path.exists(FLAG), msg)
check("the CLI refusal exits non-zero and writes nothing", T.main(["set", "aeon"]) == 2 and not os.path.exists(FLAG))
write_flag({"target": "aeon"})
check("a hand-written AEON flag is ignored while anything is unmet", T.active() == "gemma26b"
      and T.generative_route(OLD_URL, OLD_MODEL) == (OLD_URL, OLD_MODEL))
check("no partial switch: under the unmet record AEON reads nothing at all", T.constructs("aeon") == {})
clear()
check("no flag -> the 26B", T.active() == "gemma26b" and T.receipt()["identity"] == "gemma-4-26b-a4b-it-uncensored")
for bad in ("{not json", json.dumps({"target": "llama"}), json.dumps(["aeon"])):
    write_flag(bad)
    check("a bad flag -> the 26B (%s)" % bad[:12], T.active() == "gemma26b")
clear()
check("an unknown target cannot be set", refused("gpt") is not None and not os.path.exists(FLAG))

print("--- a complete, valid pass record ---")
GOOD = copy.deepcopy(real)
GOOD["pain"] = {"paper_protocol_auc": 0.9, "prompt_variant_aucs": [0.9] * 6, "status": "passed"}
for c in GOOD["constructs"].values():
    c["semantic_review"] = "passed"
use_record(GOOD)
check("a complete passing record has nothing unmet", T.unmet() == [], T.unmet())
check("the flip is then allowed and written", T.set_target("aeon") == "aeon" and T.active() == "aeon"
      and json.load(open(FLAG)) == {"target": "aeon"})
check("under AEON all eleven constructs are read, at the record's layers",
      sorted(T.constructs()) == sorted(T.DIMENSIONS) and T.constructs()["Valence"] == (41, "mean"))
reading = {"Arousal": 0.4, "Tension": True, "Desire": float("nan"), "Safety": "x", "Curiosity": "0.2"}
check("readings keep only finite numbers", T.admitted_readings(reading) == {"Arousal": 0.4, "Curiosity": 0.2})
check("a reading set from the other checkpoint is refused whole",
      T.admitted_readings(reading, identity=T.TARGETS["gemma26b"]["identity"]) == {})
check("generated reads move to the shim's subconscious lane",
      T.generative_route(OLD_URL, OLD_MODEL) == (T.SHIM_SUBCONSCIOUS, "aeon-gemma-4-12b"))
check("flipping back to the 26B is always allowed", T.set_target("gemma26b") == "gemma26b" and T.active() == "gemma26b")

print("--- one unmet item blocks the whole flip ---")
cases = []
r = copy.deepcopy(GOOD); r["constructs"]["Warmth"]["nested_auc"] = 0.849; cases.append(("an AUC below .85", r, "Warmth: nested AUC"))
r = copy.deepcopy(GOOD); r["constructs"]["Safety"]["mean_variant_aucs"][2] = 0.84; cases.append(("one variant below .85", r, "Safety: mean-pooled prompt variants 5/6"))
r = copy.deepcopy(GOOD); r["constructs"]["Tension"]["mean_variant_aucs"] = [0.9] * 5; cases.append(("five variants, not six", r, "Tension: mean-pooled prompt variants"))
r = copy.deepcopy(GOOD); del r["constructs"]["Desire"]; cases.append(("a construct missing", r, "Desire: no result"))
r = copy.deepcopy(GOOD); r["constructs"]["Arousal"]["semantic_review"] = "pending"; cases.append(("a review pending", r, "Arousal: semantic review pending"))
r = copy.deepcopy(GOOD); r["max_abs_cosine"] = 0.31; cases.append(("orthogonality broken", r, "orthogonality"))
r = copy.deepcopy(GOOD); r["pain"]["paper_protocol_auc"] = 0.82; cases.append(("Pain below .85", r, "Pain paper protocol: 0.82"))
r = copy.deepcopy(GOOD); r["pain"]["prompt_variant_aucs"] = [0.9] * 5 + [None]; cases.append(("a Pain ablation missing", r, "Pain prompt ablations: 5/6"))
r = copy.deepcopy(GOOD); r["constructs"]["Connection"]["nested_auc"] = True; cases.append(("a boolean where a number belongs", r, "Connection: nested AUC"))
r = copy.deepcopy(GOOD); r["constructs"]["Curiosity"]["passed"] = True; r["constructs"]["Curiosity"]["nested_auc"] = 0.5
cases.append(("a 'passed' word does not override the number", r, "Curiosity: nested AUC"))
for label, rec, expect in cases:
    use_record(rec); clear()
    m = refused()
    check("refused: %s" % label, m is not None and expect in m and not os.path.exists(FLAG), m)

print("--- malformed or tampered records ---")
use_record(GOOD, pin=False); T.RECORD_SHA256 = "0" * 64
check("a record that does not match its pin is refused", "pinned sha256" in (refused() or ""))
p = use_record(GOOD); open(p, "a").write(" ")
check("a byte changed after pinning is refused", "pinned sha256" in (refused() or ""))
use_record("{ this is not json")
check("malformed JSON is refused", "not valid JSON" in (refused() or ""))
r = copy.deepcopy(GOOD); r["schema"] = "something-else/9"; use_record(r)
check("the wrong schema is refused", "wrong schema" in (refused() or ""))
r = copy.deepcopy(GOOD); r["model"]["sha256"] = "f" * 64; use_record(r)
check("a record for another checkpoint is refused", "different checkpoint" in (refused() or ""))
T.RECORD = os.path.join(TMP, "nope.json")
check("a missing record is refused", "missing" in (refused() or ""))
write_flag({"target": "aeon"})
check("with a bad record even an AEON flag on disk stays on the 26B", T.active() == "gemma26b")
clear()

print("--- locks and the public repo ---")
T.RECORD, T.RECORD_SHA256 = REAL_RECORD, REAL_PIN
for name, t in T.TARGETS.items():
    lock = json.load(open(os.path.join(REPO, t["lock"])))
    check("%s lock matches identity and hash" % name, lock["identity"] == t["identity"] and lock["sha256"] == t["sha256"])
for rel in ("scripts/subcon_target.py", "scripts/aeon-bar-record.json", T.TARGETS["aeon"]["lock"]):
    text = open(os.path.join(REPO, rel)).read()
    addrs = [a for a in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) if a != "127.0.0.1"]
    check("%s carries no address other than loopback, and no host path" % rel,
          not addrs and "/Users/" not in text and "/home/" not in text, addrs)

print("--- receipts, the live reads and the shim follow the gate ---")
spec = importlib.util.spec_from_file_location("residual_shadow_subcon", os.path.join(REPO, "scripts", "residual_shadow.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
write_flag({"target": "aeon"})
S.record(input_text="one exact line", source="exchange", turn_id="T-1", generated_deltas={"Warmth": .1})
check("under the real (unmet) record a receipt still names the 26B", S.pending()[-1]["residual_target"]["target"] == "gemma26b")
use_record(GOOD)
S.record(input_text="another exact line", source="exchange", turn_id="T-2", generated_deltas={"Warmth": .1})
row = S.pending()[-1]
check("once everything passes a receipt names AEON and all eleven", row["residual_target"]["target"] == "aeon"
      and row["residual_target"]["constructs"] == sorted(T.DIMENSIONS), row.get("residual_target"))

def load_reader(tag):
    sp = importlib.util.spec_from_file_location("emotion_read_" + tag, os.path.join(REPO, "scripts", "emotion_read.py"))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
er = load_reader("aeon")
check("emotion_read.py follows the flipped flag (endpoint and model together)",
      er.LM_URL == T.SHIM_SUBCONSCIOUS and er.MODEL == "aeon-gemma-4-12b", (er.LM_URL, er.MODEL))
check("emotion_read.py keeps its eleven-key contract and cap", list(er.DIMS) == list(T.DIMENSIONS) and er.CAP == 0.10)
import vintos_claude_shim as SH
chain = SH.provider_chain({}, "/pool/subconscious/v1/chat/completions")
check("the flipped shim lane is AEON only, never the 26B", chain == ["pool:aeon", "aegis_gemma"], chain)
T.RECORD, T.RECORD_SHA256 = REAL_RECORD, REAL_PIN
er = load_reader("26b")
check("with the real record emotion_read.py is exactly as before", er.MODEL == "gemma-4-26b-a4b-it-uncensored"
      and er.LM_URL.endswith(":1234/v1/chat/completions"))
check("with the real record the shim keeps the 26B",
      SH.provider_chain({}, "/pool/subconscious/v1/chat/completions") == ["pool:subconscious", "gemma"])
check("other pool tasks never follow the flag", SH.provider_chain({}, "/pool/quick/v1/chat/completions") == ["pool:quick", "aegis_gemma", "gemma"])
srv = open(os.path.join(REPO, "bin", "server.py")).read()
fn = srv[srv.index("def nudge_emotions_from_text"):srv.index("def nudge_emotions_from_text") + 9000]
check("the server's live read takes its route from the flag", "generative_route(_emo_url, _model)" in fn and "_u.Request(_emo_url," in fn)
clear()

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
