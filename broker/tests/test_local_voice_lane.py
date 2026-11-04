#!/usr/bin/env python3
"""The local voice lane keeps acoustic evidence, local routing, and fallback honest."""
import importlib.util, json, os, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
scratch = tempfile.TemporaryDirectory(); os.environ["HOME"] = scratch.name
os.environ["SPARK_WORKSPACE"] = os.path.join(scratch.name, ".vintos", "workspace")

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

def check(label, ok):
    if not ok: raise AssertionError(label)
    print("ok -", label)

VO = load("voice_orpheus", os.path.join(REPO,"bin","voice_orpheus.py"))
VL = load("voice_local", os.path.join(REPO,"scripts","voice_local.py"))
MS = load("mac_stage_service", os.path.join(REPO,"bin","mac_stage_service.py"))
raw = "<custom_token_4><custom_token_5><custom_token_1>" + "".join(
    "<custom_token_%d>" % (10 + (i % 7) * 4096 + 100 + i) for i in range(7))
c0,c1,c2 = VO._codes(raw)
check("Orpheus control tokens are skipped and one complete SNAC frame survives", (len(c0),len(c1),len(c2)) == (1,2,4))
check("audible cues survive while stage prose and unsupported tags never get spoken",
      VO.spoken_text("[sigh] [A breath, closer] here <whisper>love</whisper> <laugh>yes</laugh> [DO: mission cake]")=="<sigh> here love <laugh>yes")
check("the displayed reply contains words rather than synthesis markup",
      VO.display_text("[A low laugh] <laugh> hello <pause>love</pause>")=="hello love")
check("the selected local voice has no destructive post-synthesis pitch shift",
      VO.VOICE=="dan" and VO.PITCH_STEPS==0.0)
check("Chatterbox preserves native cues and strips unsupported stage prose",
      MS._chatterbox_text("<sigh> here [A breath, closer] <laugh>yes</laugh> [pause] now") ==
      "[sigh] here [laugh] yes, now")
VO._post = lambda *a, **k: (b"RIFF" + b"x"*80, "audio/wav")
out = os.path.join(scratch.name,"voice.wav"); VO.synthesize_remote("hello",out)
check("remote Orpheus writes a measured WAV", open(out,"rb").read().startswith(b"RIFF"))
VO._post = lambda *a, **k: (b'{"ok":true}', "application/json")
try: VO.synthesize_remote("hello",out); raised=False
except RuntimeError: raised=True
check("a JSON success body cannot masquerade as speech", raised)
heard=MS._heard_fields('**WORDS:** "Testing one two three."\n**SOUNDS:** a short laugh at the start; a pause after "two"\n**TONE:** amused, relaxed')
check("audio-native response preserves the words, the sounds and the tone separately",
      heard=={"WORDS":"Testing one two three.","SOUNDS":'a short laugh at the start; a pause after "two"',"TONE":"amused, relaxed"})
try: MS._heard_fields("I am unable to help with that."); raised=False
except ValueError: raised=True
check("a reading with no words line is refused, not passed on as words", raised)
check("Gemma 4's three unlabelled lines are read in order",
      MS._heard_fields("Oh my god stop it.\nNone\nShocked, incredulous") == {"WORDS": "Oh my god stop it.", "SOUNDS": "None", "TONE": "Shocked, incredulous"})
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
        return json.dumps({"ok":True,"transcript":"I am fine","audio_reading":"her emphasis rose on fine",
            "ears":"gemma3n-audio-native-mlx-vlm","audio_native_gemma":True}).encode(), {}
    if url.endswith("/chat/completions"):
        return json.dumps({"choices":[{"message":{"content":"I heard you."}}]}).encode(), {}
    return b"RIFF"+b"y"*80, {"X-Vintos-Voice":"chatterbox_turbo"}
sys.path.insert(0, os.path.join(REPO, "scripts"))
import stratagem as _sg_client, turn_coordinator as _sg_coordinator
_sg_client._post = lambda *a, **k: {}
_sg_coordinator._post = lambda *a, **k: {"ok": True}
assert _sg_client._post("/stratagem/inventory") == {}  # sender is stubbed
VL._post=post; result=VL.turn("AA==",24000,"SOUL","fresh frame")
brain_prompt=seen[1][1]["messages"][1]["content"]
check("the turn returns local brain, Chatterbox and literal transcript", result["ok"] and result["voice_engine"]=="chatterbox_turbo" and result["transcript"]=="I am fine")
check("audio-native inflection reaches the brain beside the words", "emphasis rose" in brain_prompt and '"audio_native_gemma": true' in brain_prompt)
check("the local reply shown to Gloria strips synthesis markup", result["reply"]=="I heard you.")
check("the local lane calls no hosted provider", all("api.x.ai" not in url and "api.openai.com" not in url for url,_ in seen))
client=open(os.path.join(REPO,"clients","mobile","index.html")).read(); server=open(os.path.join(REPO,"bin","server.py")).read()
router=open(os.path.join(REPO,"bin","model_router.py")).read(); stage=open(os.path.join(REPO,"bin","mac_stage_service.py")).read()
check("the app offers Vintos Local and retains between-turn framing", "Vintos Local" in client and "provider==='local'" in client and "/api/voice/framing" in client)
check("the local text toggle names the abliterated local route", "ABLIT GEMMA" in client and "gemma(avatar toggle)" in router)
check("the server exposes start, turn, heartbeat and unload boundaries", 'provider == "local"' in server and '/api/voice/local/turn' in server and '/api/voice/local/heartbeat' in server and '/api/voice/local/end' in server)
check("the live start receipt names the promoted voice", '"voice":"chatterbox-turbo-onyx"' in server)
check("Mac ears route the waveform itself through Gemma 4's audio encoder, the instruction first", '{"type": "text", "text": HEAR_REQUEST}, {"type": "audio", "audio": y}' in stage and 'google/gemma-4-E4B-it' in stage and '"audio_native_gemma": True' in stage and "mlx_whisper" not in stage)
check("the ears stay warm until a heavy bench explicitly evicts them", 'elif evict_ears: _ears_unload()' in stage and '"evict_ears": bool(evict_ears)' in open(os.path.join(REPO,"scripts","voice_local.py")).read())
check("the expressive MLX voice is call-scoped and Kokoro remains the outage fallback",
      "_chatterbox_load(); _chatterbox_call_active = True" in stage and
      "_chatterbox_call_active = False; _chatterbox_unload()" in stage and
      '"engine": "kokoro_fallback"' in stage)
check("one-off avatar speech cannot leave the live voice resident",
      "transient_voice = not _chatterbox_call_active" in stage and
      "if transient_voice: _chatterbox_unload()" in stage)
render_body=stage.split("def render(text, room):",1)[1].split("class Handler",1)[0]
check("avatar-video and ReelRoom speech use Chatterbox-Onyx rather than warming Orpheus",
      "chatterbox-onyx-v1" in render_body and "receipt = chatterbox_wav" in render_body
      and "receipt = orpheus_wav" not in render_body)
check("short live turns bound both language generations", '"max_tokens":180' in open(os.path.join(REPO,"scripts","voice_local.py")).read() and "max_new_tokens=160 if not attempt else 220" in stage and 'res_type="scipy"' in stage and "30 * 16000" in stage)
check("a malformed first ears reading gets one warm retry", "for attempt in range(2)" in stage)
check("the ears load and warm up off the start request; a turn waits on their lock, not on a half-loaded model",
      "threading.Thread(target=_bg, daemon=True).start()" in stage and "with _ears_lock:" in stage.split("def _ears_load():", 1)[1].split("def _ears_unload", 1)[0])
check("ending during a local turn preserves and finishes its late reply", "if(vc.busy){_avCallLit('thinking');return;}" in client and "if(session.closing)_finishLocalVoiceSession(session)" in client and "then(async d=>{if(window._vc!==session)return" not in client)
check("local calls stop listening throughout generation and playback",
      "_localMicEnabled(session,false)" in client and "_localMicEnabled(session,true)" in client and "session.busy||session.listening===false" in client)
check("the ears request carries no name list (given one, the model answers with the list; 4 November)",
      "VOICE_VOCAB" not in stage and "Velqan" not in MS.HEAR_REQUEST)
import numpy as np
_y = np.concatenate([np.full(8000, .3, "float32"), np.zeros(int(2.5 * 16000), "float32"), np.full(8000, .3, "float32")])
_y = _y * np.sin(np.arange(len(_y)) * 0.3).astype("float32")
_g = MS._pauses(_y)
check("pauses are measured from the waveform itself (a 2.5 s silence, to a frame)", len(_g) == 1 and abs(_g[0][0] - 2.5) < 0.15 and abs(_g[0][1] - 0.5) < 0.15)
check("test writes remain under scratch HOME", out.startswith(scratch.name))
