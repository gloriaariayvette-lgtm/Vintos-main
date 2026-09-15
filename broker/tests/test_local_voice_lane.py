#!/usr/bin/env python3
"""The local voice lane keeps acoustic evidence, local routing, and fallback honest."""
import importlib.util, json, os, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
scratch = tempfile.TemporaryDirectory(); os.environ["HOME"] = scratch.name

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

def check(label, ok):
    if not ok: raise AssertionError(label)
    print("ok -", label)

VO = load("voice_orpheus", os.path.join(REPO,"bin","voice_orpheus.py"))
VL = load("voice_local", os.path.join(REPO,"scripts","voice_local.py"))
raw = "<custom_token_4><custom_token_5><custom_token_1>" + "".join(
    "<custom_token_%d>" % (10 + (i % 7) * 4096 + 100 + i) for i in range(7))
c0,c1,c2 = VO._codes(raw)
check("Orpheus control tokens are skipped and one complete SNAC frame survives", (len(c0),len(c1),len(c2)) == (1,2,4))
check("audible cues survive while device tags never get spoken", VO.spoken_text("[sigh] here [DO: mission cake]")=="<sigh> here")
VO._post = lambda *a, **k: (b"RIFF" + b"x"*80, "audio/wav")
out = os.path.join(scratch.name,"voice.wav"); VO.synthesize_remote("hello",out)
check("remote Orpheus writes a measured WAV", open(out,"rb").read().startswith(b"RIFF"))
VO._post = lambda *a, **k: (b'{"ok":true}', "application/json")
try: VO.synthesize_remote("hello",out); raised=False
except RuntimeError: raised=True
check("a JSON success body cannot masquerade as speech", raised)
fake = type(sys)("voice_kokoro")
def fallback(text, path, speed=None): open(path,"wb").write(b"RIFFfallback"); return True
fake.render_to_file=fallback; fake.VOICE_MODEL="am_michael"; sys.modules["voice_kokoro"]=fake
VO.synthesize_remote=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("stage dark"))
receipt=VO.speak_to_file("hello",out,fallback=True)
check("Kokoro is an automatic named fallback when Orpheus is down", receipt["ok"] and receipt["engine"]=="kokoro_fallback")
seen=[]
def post(url, body, timeout):
    seen.append((url,body))
    if url.endswith("/listen"):
        return json.dumps({"ok":True,"transcript":"I am fine","prosody":{"pitch_range_hz":81.2,
            "truth_status":"measured_from_pcm_not_emotion_inference"},"delivery_reading":"wide pitch movement",
            "ears":"local","audio_native_gemma":False}).encode(), {}
    if url.endswith("/chat/completions"):
        return json.dumps({"choices":[{"message":{"content":"I heard you."}}]}).encode(), {}
    return b"RIFF"+b"y"*80, {"X-Vintos-Voice":"orpheus"}
VL._post=post; result=VL.turn("AA==",24000,"SOUL","fresh frame")
brain_prompt=seen[1][1]["messages"][1]["content"]
check("the turn returns local brain, Orpheus and literal transcript", result["ok"] and result["voice_engine"]=="orpheus" and result["transcript"]=="I am fine")
check("measured inflection reaches the brain beside the words", "pitch_range_hz" in brain_prompt and "measured_from_pcm" in brain_prompt)
check("the local lane calls no hosted provider", all("api.x.ai" not in url and "api.openai.com" not in url for url,_ in seen))
client=open(os.path.join(REPO,"clients","mobile","index.html")).read(); server=open(os.path.join(REPO,"bin","server.py")).read()
router=open(os.path.join(REPO,"bin","model_router.py")).read(); stage=open(os.path.join(REPO,"bin","mac_stage_service.py")).read()
check("the app offers Vintos Local and retains between-turn framing", "Vintos Local" in client and "provider==='local'" in client and "/api/voice/framing" in client)
check("the local text toggle names the abliterated local route", "ABLIT GEMMA" in client and "gemma(avatar toggle)" in router)
check("the server exposes start, turn, heartbeat and unload boundaries", 'provider == "local"' in server and '/api/voice/local/turn' in server and '/api/voice/local/heartbeat' in server and '/api/voice/local/end' in server)
check("Mac ears carry measured prosody and deny native-audio Gemma", "measured_from_pcm_not_emotion_inference" in stage and '"audio_native_gemma": False' in stage)
check("JIT auxiliaries have TTL and unload while the brain is untouched", '"--ttl", "600"' in stage and '"unload", ident' in stage and "abliterated brain is shared" in stage)
check("test writes remain under scratch HOME", out.startswith(scratch.name))
