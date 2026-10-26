#!/usr/bin/env python3
"""Proposal 17: a heard utterance is kept as an attributed observation -- words, the ears' reading, a hash of the
recording and a few measurements -- with no audio kept and his later readings kept beside it, never in it.

Offline: scratch HOME and workspace, every sender stubbed, test audio synthesized here."""
import base64, hashlib, importlib.util, json, math, os, struct, sys, tempfile, time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
scratch = tempfile.TemporaryDirectory()
os.environ["HOME"] = scratch.name
os.environ["SPARK_WORKSPACE"] = os.path.join(scratch.name, ".vintos", "workspace")
MEM = os.path.join(os.environ["SPARK_WORKSPACE"], "memory")
os.makedirs(MEM, exist_ok=True)
sys.path.insert(0, os.path.join(REPO, "scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod; spec.loader.exec_module(mod); return mod


def check(label, ok, detail=""):
    if not ok:
        raise AssertionError(label + ((": " + str(detail)) if detail else ""))
    print("ok -", label)


AM = load("auditory_memory", os.path.join(REPO, "scripts", "auditory_memory.py"))
check("the store is in the scratch workspace, not hers",
      AM.STORE.startswith(scratch.name) and not AM.STORE.startswith(os.path.expanduser("~gloria")), AM.STORE)
src = open(os.path.join(REPO, "scripts", "auditory_memory.py")).read()
check("the organ has no way to send anything", not any(x in src for x in ("urllib", "requests", "socket", "http.client", "ntfy", "deliver(")))


def tone(seconds, rate=24000, amp=8000, freq=220.0, silence=0.0):
    """Synthesized test audio: a sine tone followed by digital silence. No real recording is used."""
    n_tone, n_sil = int(seconds * rate), int(silence * rate)
    samples = [int(amp * math.sin(2 * math.pi * freq * i / rate)) for i in range(n_tone)] + [0] * n_sil
    return struct.pack("<%dh" % len(samples), *samples)


pcm = tone(1.0, silence=1.0)
b64 = base64.b64encode(pcm).decode()
heard = {"ok": True, "transcript": "I finally finished the garden fence today",
         "audio_reading": "rising pace with a laugh near the end", "ears": "gemma3n-audio-native-mlx-vlm",
         "audio_native_gemma": True}

ac = AM.acoustics(pcm, 24000)
check("duration is measured from the samples", ac["seconds"] == 2.0, ac)
check("half tone, half silence reads as about half voiced", 0.45 <= ac["voiced_fraction"] <= 0.55, ac)
check("loudness is measured (a 8000-amplitude sine at about -15 dBFS RMS over half the clip)",
      -22 < ac["rms_dbfs"] < -14 and -13 < ac["peak_dbfs"] < -11, ac)
check("only non-identifying measurements are derived: no pitch, spectrum or embedding",
      set(ac) == {"seconds", "sample_rate", "rms_dbfs", "peak_dbfs", "voiced_fraction"}, sorted(ac))
check("silence and empty audio measure without error",
      AM.acoustics(b"", 24000)["seconds"] == 0.0 and AM.acoustics(tone(0, silence=0.5), 24000)["voiced_fraction"] == 0.0)

rec = AM.record(b64, 24000, heard, turn_id="t-abc")
stored = open(AM.STORE).read()
check("one heard utterance is kept with its turn id and time", rec and rec["turn_id"] == "t-abc" and rec["heard_at"], rec)
check("the source hash is the sha256 of the PCM Aegis received", rec["source_hash"] == "sha256:" + hashlib.sha256(pcm).hexdigest())
check("the recording itself is not kept: no audio key, no base64, no PCM", rec["audio_kept"] is False
      and "audio" not in rec and b64[:200] not in stored and base64.b64encode(pcm[:300]).decode()[:200] not in stored)
check("her words and the ears' reading are kept apart, verbatim",
      rec["transcript"] == heard["transcript"] and rec["observation"]["reading"] == heard["audio_reading"])
check("the reading names who made it and says it is an observation, not her mood",
      rec["observation"]["by"] == "gemma3n-audio-native-mlx-vlm" and rec["observation"]["audio_native"] is True
      and "not a fact about her mood" in rec["observation"]["kind"])
check("there are no interpretations until he makes one", rec["interpretations"] == [])

AM.record(b64, 24000, heard, turn_id="t-abc")
check("the same recording in the same turn is kept once", len(AM.memories()) == 1)
check("a turn without a reading keeps nothing", AM.record(b64, 24000, dict(heard, audio_reading=""), turn_id="t-x") is None)
check("a turn without words keeps nothing", AM.record(b64, 24000, dict(heard, transcript=""), turn_id="t-y") is None)
check("a test-mode turn keeps nothing", AM.record(b64, 24000, heard, turn_id="t-z", test_mode=True) is None)
open(AM.TEST_MODE_FLAG, "w").close()
check("the house test-mode flag keeps nothing", AM.record(b64, 24000, heard, turn_id="t-w") is None)
os.unlink(AM.TEST_MODE_FLAG)
check("nothing extra was written by the refused turns", len(AM.memories()) == 1)
long = AM.record(base64.b64encode(tone(0.2)).decode(), 24000, dict(heard, transcript="word " * 400), turn_id="t-long")
check("long words are cut at 1,200 characters and marked", long["transcript"].endswith(" [cut]") and len(long["transcript"]) <= 1206)

# Retrieval: the present conversation is not memory; later it is.
now = time.time()
check("an utterance from the last ten minutes is not recalled", AM.find("the garden fence is finished", now=now) is None)
later = now + 3600
found = AM.find("did I tell you the garden fence is finished", now=later)
check("an hour later, her matching words bring it back", found and found["id"] == rec["id"], found)
check("unrelated words bring nothing back", AM.find("what should we cook for dinner tonight", now=later) is None)
check("one word is not enough to recall anything", AM.find("garden", now=later) is None)

line = AM.render(found)
check("the line carries her words and the reading, each labelled",
      "she said \"I finally finished the garden fence today\"" in line and "rising pace with a laugh" in line
      and "an observation, not a fact about her mood" in line, line)
check("the line says the recording was not kept", "recording itself was not kept" in line)
check("the line carries a measurement, not a guess", "Measured: 2.0 s" in line, line)

before = json.dumps(rec["observation"], sort_keys=True)
AM.interpret(rec["id"], "she was proud, and wanted me to notice the work")
after = [r for r in AM.memories() if r["id"] == rec["id"]][0]
check("his later reading is appended beside the observation",
      after["interpretations"][-1]["meaning"].startswith("she was proud") and after["interpretations"][-1]["by"] == "vintos")
check("the observation is unchanged by his interpretation", json.dumps(after["observation"], sort_keys=True) == before)
check("an interpretation of an unknown id changes nothing", AM.interpret("am-nope", "x") is None)
line2 = AM.render(after)
check("the line keeps his interpretation separate and labelled as his",
      "You later read it as: \"she was proud" in line2 and "(your interpretation," in line2, line2)

# recall_explain carries it beside, not inside, the durable record.
RE = load("recall_explain", os.path.join(REPO, "scripts", "recall_explain.py")); RE.MEMORY = MEM
ex = RE.explain("the garden fence I finally finished")
check("explain carries the heard utterance apart from supported_by", ex["heard"] and ex["supported_by"] is None
      and ex["heard"]["her_words"] == heard["transcript"], ex.get("heard"))
check("explain keeps observation and interpretation apart",
      ex["heard"]["observation"]["reading"] == heard["audio_reading"]
      and ex["heard"]["interpretations"][-1]["kind"] == "his later interpretation")
r = RE.render(ex)
check("render says HEARD / HOW IT SOUNDED / HE LATER READ IT AS",
      "HEARD " in r and "HOW IT SOUNDED (the ears' observation at the time, not her mood)" in r and "HE LATER READ IT AS" in r, r)
check("an unsupported statement still says so",
      RE.render(RE.explain("the lighthouse we never visited")).startswith("[RECALL: no occurrence supports"))

# The local voice lane keeps it, and a failure to keep it never costs the turn.
VL = load("voice_local", os.path.join(REPO, "scripts", "voice_local.py"))
import stratagem as _sg_client, turn_coordinator as _sg_coordinator
_sg_client._post = lambda *a, **k: {}
_sg_coordinator._post = lambda *a, **k: {"ok": True}
seen = []


def post(url, body, timeout):
    seen.append(url)
    if url.endswith("/listen"):
        return json.dumps({"ok": True, "transcript": "the swallows came back to the eaves",
                           "audio_reading": "soft and slow, a long breath before eaves",
                           "ears": "gemma3n-audio-native-mlx-vlm", "audio_native_gemma": True}).encode(), {}
    if url.endswith("/chat/completions"):
        return json.dumps({"choices": [{"message": {"content": "They always find their way."}}]}).encode(), {}
    return b"RIFF" + b"y" * 80, {"X-Vintos-Voice": "chatterbox_turbo"}


VL._post = post
check("every sender in the voice lane is a stub", VL._post is post and _sg_client._post("/x") == {})
voice_pcm = tone(0.5)
result = VL.turn(base64.b64encode(voice_pcm).decode(), 24000, "SOUL", "")
kept = [m for m in AM.memories() if m["transcript"] == "the swallows came back to the eaves"]
check("the voice turn still answers", result["ok"] and result["reply"] == "They always find their way.", result)
check("the voice turn keeps the heard utterance with the turn's id and the recording's hash",
      len(kept) == 1 and kept[0]["turn_id"] and kept[0]["turn_id"].startswith("t-")
      and kept[0]["source_hash"] == "sha256:" + hashlib.sha256(voice_pcm).hexdigest(), kept)
check("the voice lane reached nothing but its stubs", all("api." not in u for u in seen))
AM.record = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
result2 = VL.turn(base64.b64encode(tone(0.3, freq=330)).decode(), 24000, "SOUL", "")
check("a failure to keep it never costs the turn", result2["ok"] and result2["reply"])

server = open(os.path.join(REPO, "bin", "server.py")).read()
door = server[server.index("def _durable_context("):server.index("def _avatar_scene_admit(")]
check("the chat door carries the heard line beside the durable memory", "auditory_memory import context_line" in door
      and "_dm_cb(" in door)
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy manifest names the organ", "auditory_memory.py" in deploy)
print("all auditory memory checks passed")
