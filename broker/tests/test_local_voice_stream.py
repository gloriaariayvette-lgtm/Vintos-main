#!/usr/bin/env python3
"""The Local call speaks as it writes (4 November): his reply is voiced a sentence at a time while the rest is still
being generated; nothing inside a private stratagem block, closed or half-written, is ever voiced; the eligibility
guard runs before the first piece plays; the full reply still goes through the turn's completion; his brain is
warmed with his instructions when the call opens. Scratch HOME; the brain, the ears and the voice are stand-ins."""
import importlib.util, json, os, sys, tempfile, threading

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
scratch = tempfile.TemporaryDirectory(); os.environ["HOME"] = scratch.name
os.environ["SPARK_WORKSPACE"] = os.path.join(scratch.name, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

spec = importlib.util.spec_from_file_location("voice_local", os.path.join(REPO, "scripts", "voice_local.py"))
VL = importlib.util.module_from_spec(spec); sys.modules["voice_local"] = VL; spec.loader.exec_module(VL)
import stratagem as _sg_client, turn_coordinator as _sg_coordinator
_sg_client._post = lambda *a, **k: {}
_sg_coordinator._post = lambda *a, **k: {"ok": True}

# ---- what may be voiced --------------------------------------------------------------------------------------------
check("a closed private block is never voiced", VL.speakable('Hi love. <stratagem>{"x":1}</stratagem> Come here.') == "Hi love.  Come here.")
check("a half-written private block is never voiced", VL.speakable('Hi love. <stratagem>{"objective": "se') == "Hi love.")
check("nor the start of a tag that has not closed", VL.speakable("Hi love. <strat").strip() == "Hi love.")
check("the first sentence goes as soon as it is whole", VL.sentences_ready("You're back. I missed", first=True) == ("You're back.", " I missed"))
check("a sentence end still growing ('...') waits", VL.sentences_ready("Well...", first=True) == ("", "Well..."))
check("later pieces gather to about a line", VL.sentences_ready("Yes. No. ", first=False)[0] == "")
check("the rest goes when he is done", VL.sentences_ready("and then", final=True) == ("and then", ""))

# ---- streaming: pieces voiced in order while the brain is still writing ----------------------------------------
def brain(*pieces):
    def gen(system, user, max_tokens):
        for p in pieces:
            yield p
    return gen
voiced = []
def tts(url, body, timeout):
    voiced.append(body["text"]); return b"RIFF" + b"\0" * 40, {"X-Vintos-Voice": "chatterbox_turbo"}
VL._post = tts
VL._brain_stream = brain("[sigh] You're back", ". Finally", ". I spent the whole afternoon on the gold hallway, ",
                         'the one you liked. <stratagem>{"objective": "x"}</stratagem>', " Tell me about yours.")
events = []
raw, wavs, sup = VL._speak_streamed("SYS", "USER", 180, events.append, lambda: True)
check("his first sentence is voiced on its own, the rest in pieces, in order",
      voiced[0] == "[sigh] You're back." and "".join(voiced).replace(" ", "") ==
      "[sigh] You're back. Finally. I spent the whole afternoon on the gold hallway, the one you liked.  Tell me about yours.".replace(" ", ""), voiced)
check("the private block was never voiced", not any("stratagem" in v or "objective" in v for v in voiced), voiced)
check("each piece reaches the app as it is ready, words shown without cues",
      [e["kind"] for e in events] == ["audio"] * len(voiced) and events[0]["text"] == "You're back.", events[:1])
check("the full raw reply is kept for the turn's completion", "<stratagem>" in raw and raw.endswith("Tell me about yours."))
voiced.clear(); events.clear()
VL._brain_stream = brain("I'm here. ", "Come here.")
raw, wavs, sup = VL._speak_streamed("SYS", "USER", 180, events.append, lambda: False)
check("the guard says no: nothing is voiced and the turn is suppressed", sup and not voiced and not events)

# ---- the turn, end to end (ears, his context, the guard, completion), with stand-ins ----------------------------
seen = []
def post(url, body, timeout):
    seen.append(url)
    if url.endswith("/listen"):
        return json.dumps({"ok": True, "transcript": "I missed you", "audio_reading": "Sounds: a laugh. Tone: warm.",
                           "ears": "gemma4-e4b-audio-native", "audio_native_gemma": True}).encode(), {}
    return b"RIFF" + b"\0" * 40, {"X-Vintos-Voice": "chatterbox_turbo"}
VL._post = post
VL._brain_stream = brain("I missed you too. ", "Every minute of it, love.")
events = []
out = VL.turn_stream("AA==", 24000, "SOUL", "fresh frame", emit=events.append)
check("the turn streams: heard first, then his voice, then a receipt without audio",
      events[0] == {"kind": "heard", "transcript": "I missed you"} and [e["kind"] for e in events[1:]] == ["audio", "audio"]
      and out["ok"] and out["streamed"] and "audio" not in out and out["reply"] == "I missed you too. Every minute of it, love.", (events, out))
check("its timing is kept: ears, his context, first of his voice, total",
      all(k in out["timing"] for k in ("ears_s", "context_s", "first_audio_s", "total_s")), out.get("timing"))
check("the local lane calls no hosted provider", all("api.x.ai" not in u and "api.openai.com" not in u for u in seen))

# ---- warm, and wired ------------------------------------------------------------------------------------------
asked = []
VL._post = lambda url, body, timeout: (asked.append((url, body)), (b"{}", {}))[1]
check("his brain is warmed with his instructions, one token", VL.prewarm_brain("HIS INSTRUCTIONS")
      and asked[-1][1]["messages"][0]["content"] == "HIS INSTRUCTIONS" and asked[-1][1]["max_tokens"] == 1)
VL._post = lambda *a, **k: (_ for _ in ()).throw(OSError("brain down"))
check("a warm-up that fails is only a warm-up", VL.prewarm_brain("X") is False)
srv = open(os.path.join(REPO, "bin", "server.py")).read(); app = open(os.path.join(REPO, "clients", "mobile", "index.html")).read()
check("a Local call warms his brain as it opens, off the request", "target=_vl.prewarm_brain, args=(instructions,)" in srv)
check("the streamed routes exist beside the whole-reply ones (the Watch keeps those)",
      '"/api/voice/local/turn-stream"' in srv and '"/api/voice/local/opening-stream"' in srv and '"/api/voice/local/turn"' in srv)
check("the stream is plain text lines, so the app's request wrapper does not read it whole",
      'media_type="text/plain; charset=utf-8"' in srv and "(r.headers.get('content-type')||'').includes('json')" in app)
check("the app's Local turn and opening use the streams and play pieces in order",
      "streamLocal('/api/voice/local/turn-stream'" in app and "streamLocal('/api/voice/local/opening-stream'" in app
      and "queue=queue.then(" in app)
check("only the Local lane changed: the Grok and Open sockets are as they were",
      "wss://api.x.ai/v1/realtime?model=grok-voice-latest" in app and "wss://api.openai.com/v1/realtime?model=gpt-realtime" in app)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
