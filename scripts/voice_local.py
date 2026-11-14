#!/usr/bin/env python3
"""voice_local.py — the local call gives the recording itself to native audio understanding.

The Mac hears and voices.  Aegis supplies Vintos's context and calls his local
abliterated brain. A failed component is a typed failed turn; this lane never
silently substitutes a transcript-only path and never leaks into a hosted provider.
"""
from __future__ import annotations

import base64, json, os, urllib.error, urllib.request

STAGE = os.environ.get("VINTOS_MAC_STAGE", "http://100.79.177.103:8511").rstrip("/")
LM = os.environ.get("VINTOS_MAC_LM_BASE_REMOTE", "http://100.79.177.103:1234").rstrip("/")
BRAIN = os.environ.get("VINTOS_LOCAL_BRAIN", "aeon-gemma-4-12b")


def _brain():
    """(chat url, model, extra fields) for his brain, read at each call so the subconscious flip (subcon_target.py)
    moves it to AEON with thinking off; an explicit VINTOS_LOCAL_BRAIN keeps the route it names."""
    import native_audio
    if native_audio.enabled():
        return native_audio.verify() + "/v1/chat/completions", BRAIN, {}
    base, model, extra = LM, BRAIN, {}
    if "VINTOS_LOCAL_BRAIN" not in os.environ:
        try:
            import subcon_target
            base, model, extra = subcon_target.brain_route(LM, BRAIN)
        except Exception:
            pass
    return base.rstrip("/") + "/v1/chat/completions", model, extra


def _brain_body(body):
    url, model, extra = _brain()
    return url, dict(body, model=model, **extra)

# This call, for the media index (media_embed.py): a label only, so the turns of one call can be found together.
# Opened when the call's models are loaded (or by its first turn), closed by the call's end route.
_CALL = {"id": None}


def call_id():
    if not _CALL["id"]:
        import time
        _CALL["id"] = "lc-%d-%d" % (int(time.time() * 1000), os.getpid())
    return _CALL["id"]


def _held(ladder_call):
    """A call he started (attention_call.py) keeps what its turns capture until she answers. True while it does;
    a call that no longer holds anything (she answered while the turn was made) keeps nothing of the turn."""
    try:
        import attention_call
        return attention_call.retention(ladder_call) == "held"
    except Exception:
        return False


def _hold_audio(audio, speaker, turn_id, sample_rate=24000, test=False, ladder_call=None):
    """Hand one side of this turn to the media index (EmbeddingGemma 2, Gloria 26 October: both voices). The bytes
    wait in a private 0700 directory and are deleted when the batch after the call embeds them; nothing is
    embedded here, so the turn is not slowed. A call he started holds them apart for her answer (ladder_call);
    once that call holds nothing, nothing is kept. Never raises."""
    try:
        if ladder_call and not _held(ladder_call):
            return
        import media_embed
        media_embed.hold_call_audio(audio, speaker, turn_id=turn_id, session_id=call_id(),
                                    sample_rate=sample_rate, test=test, pending=ladder_call or None)
    except Exception as exc:
        print("[voice-local/media-embed]", str(exc)[:200], flush=True)


def _remember_how_it_sounded(audio_b64, sample_rate, heard, turn_id, test_mode, ladder_call=None):
    """Proposal 17: how it sounded, kept as an attributed observation (the audio itself is not kept). On a call he
    started the record is made now and held with the call until her answer. Never raises."""
    try:
        import auditory_memory
        if not ladder_call:
            auditory_memory.record(audio_b64, sample_rate, heard, turn_id=turn_id, test_mode=test_mode)
            return
        rec = auditory_memory.build(audio_b64, sample_rate, heard, turn_id=turn_id, test_mode=test_mode)
        if rec is not None:
            import attention_call
            attention_call.hold_capture(ladder_call, "auditory", rec, same="source_hash")
    except Exception as exc:
        print("[voice-local/auditory-memory]", str(exc)[:200], flush=True)


def end_call(kick=True):
    """The call is over: close its label and start the batch that embeds its held audio (then deletes it). A call
    he started passes kick=False: its audio waits for her answer, and her yes starts the batch."""
    _CALL["id"] = None
    if not kick:
        return "held for her answer"
    try:
        import media_embed
        return media_embed.kick(0)
    except Exception as exc:
        print("[voice-local/media-embed]", str(exc)[:200], flush=True)
        return "not started"


def _post(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json"}, method="POST")
    try:
        import native_audio
        open_url = (urllib.request.build_opener(urllib.request.ProxyHandler({})).open
                    if native_audio.enabled() and url.startswith(native_audio.base_url() + "/") else urllib.request.urlopen)
        with open_url(req, timeout=timeout) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as exc:
        raise RuntimeError("%s: %s" % (exc.code, exc.read().decode(errors="replace")[:300]))


def models(active, evict_ears=False):
    import native_audio
    native = native_audio.enabled()
    if active and native:
        native_audio.verify()
        native_audio.require_stage(STAGE)
    if active:
        _CALL["id"] = None
        call_id()
    body = {"active": bool(active), "evict_ears": bool(evict_ears)}
    if native:
        body["external_ears"] = True
    raw, _ = _post(STAGE + "/voice/models", body, 100)
    return json.loads(raw)


def _display_text(text):
    """The house copy cannot assume the Mac module is importable."""
    import re
    out = re.sub(r"\[[^\]\n]{1,240}\]", " ", str(text or ""))
    out = re.sub(r"</?[A-Za-z][^>\n]{0,80}>", " ", out)
    out = re.sub(r"\*+", "", out)
    return " ".join(out.split())


def _hear_input(audio_b64, sample_rate):
    import native_audio
    if native_audio.enabled():
        return native_audio.hear(audio_b64, sample_rate, _post)
    raw, _ = _post(STAGE + "/listen", {"audio": audio_b64,
        "sample_rate": int(sample_rate or 24000)}, 180)
    return json.loads(raw)


def _heard_content(heard, audio_b64, sample_rate, legacy_label="Gemma"):
    import native_audio
    if native_audio.enabled():
        return native_audio.content(audio_b64, sample_rate)
    evidence = {"reading": heard.get("audio_reading"), "pipeline": heard.get("ears"),
                "audio_native_gemma": bool(heard.get("audio_native_gemma"))}
    return ("Gloria said aloud:\n" + heard["transcript"] +
            "\n\n[AUDIO-NATIVE READING — " + legacy_label + " received the recording itself:]\n" + json.dumps(evidence, ensure_ascii=False))


def turn(audio_b64, sample_rate, instructions, framing="", ladder_call=None):
    """One turn. ladder_call: a call he started, already checked by the route against the call attention_call
    holds. It is the same turn, but what the house would capture of it for his memory waits with the call for
    her answer (how her voice sounded, both voices' audio), and her words do not reach the intent engine."""
    heard = _hear_input(audio_b64, sample_rate)
    if not heard.get("ok") or not heard.get("transcript"):
        return {"ok":False,"stage":"ears","error":heard.get("error","no words heard"),"hearing":heard}
    user = _heard_content(heard, audio_b64, sample_rate, "Gemma 3n")
    from stratagem_turn import Interaction, control
    command = control(heard["transcript"])
    if command is not None:
        return {"ok": True, "transcript": heard["transcript"], "reply": command, "audio": "", "audio_format": "wav"}
    interaction = Interaction(heard["transcript"], "voice")
    if interaction.turn.duplicate_event:
        return {"ok": True, "reply": "", "duplicate": True, "transcript": heard["transcript"]}
    _test_turn = bool(getattr(interaction.turn, "test_mode", False))
    _remember_how_it_sounded(audio_b64, sample_rate, heard, interaction.turn.turn_id, _test_turn, ladder_call)
    _hold_audio(audio_b64, "gloria", interaction.turn.turn_id, sample_rate, test=_test_turn, ladder_call=ladder_call)
    if not ladder_call:   # a held call's words reach the intent engine only through her yes (as on the realtime lanes)
        from intent_engine import note_response
        note_response(heard["transcript"])
    from intent_context import admit_voice_lead
    intent_target, intent_prompt = admit_voice_lead(interaction.turn.turn_id)
    system = str(instructions or "") + interaction.prompt()
    if intent_prompt:
        system += "\n\n" + intent_prompt
    if framing: system += "\n\nLIVE RIGHT NOW (this replaces earlier LIVE blocks):\n" + str(framing)
    system += ("\n\nLOCAL LIVE VOICE: answer in one to three conversational sentences unless "
        "Gloria explicitly asks for something longer. Your Chatterbox voice performs these exact "
        "native cues: [laugh], [chuckle], [sigh], [gasp], or [cough]. You may use at most one, "
        "only when you genuinely mean it. Never write any other bracketed stage direction and "
        "never describe the cue in prose.")
    interaction.admitted(system)
    brain_raw, _ = _post(*_brain_body({
        "messages":[{"role":"system","content":system},{"role":"user","content":user}],
        "temperature":.85,"max_tokens":180}), 180)
    brain = json.loads(brain_raw); raw_reply = ((brain.get("choices") or [{}])[0].get("message") or {}).get("content","").strip()
    raw_reply = interaction.complete(raw_reply)
    reply = _display_text(raw_reply)
    if not reply: return {"ok":False,"stage":"brain","error":"local brain returned no words","hearing":heard}
    voice_raw, headers = _post(STAGE + "/tts", {"text":raw_reply}, 210)
    if not voice_raw.startswith(b"RIFF"):
        return {"ok":False,"stage":"voice","error":"voice returned no WAV","reply":reply,"hearing":heard}
    from stratagem_turn import guard_reply
    if not guard_reply(reply, interaction.turn):
        return {"ok": True, "reply": "", "audio": "", "transcript": heard["transcript"], "suppressed": "stratagem ended before playback"}
    _hold_audio(voice_raw, "vintos", interaction.turn.turn_id, test=_test_turn,   # what she will hear
                ladder_call=ladder_call)
    if intent_target and not ladder_call:
        from intent_engine import record_delivery
        record_delivery(reply, "voice", interaction.turn.turn_id, target=intent_target,
                        input_text=heard["transcript"])
    return {"ok":True,"transcript":heard["transcript"],
            "audio_reading":heard.get("audio_reading"),"reply":reply,
            "audio":base64.b64encode(voice_raw).decode(),"audio_format":"wav",
            "voice_engine":headers.get("X-Vintos-Voice","unknown"),"model":_brain()[1]}


def opening(instructions, framing="", opening_instruction=""):
    """His first words on a call he started (the attention ladder, 27 October): no recording of hers yet, so no
    ears; his brain and his voice only, the same local model and voice as every local turn. Typed failures, like
    turn()."""
    system = str(instructions or "")
    if framing:
        system += "\n\nLIVE RIGHT NOW (this replaces earlier LIVE blocks):\n" + str(framing)
    if opening_instruction:
        system += "\n\n" + str(opening_instruction)
    system += ("\n\nLOCAL LIVE VOICE: one to four conversational sentences. Your Chatterbox voice performs these "
               "exact native cues: [laugh], [chuckle], [sigh], [gasp], or [cough]. You may use at most one, only "
               "when you genuinely mean it. Never write any other bracketed stage direction.")
    brain_raw, _ = _post(*_brain_body({
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": "[The call you placed has just connected. She is listening. Speak first.]"}],
        "temperature": .85, "max_tokens": 200}), 180)
    brain = json.loads(brain_raw)
    raw_reply = ((brain.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
    try:
        import stratagem
        raw_reply = stratagem.consume(raw_reply, "voice")
    except Exception:
        pass
    reply = _display_text(raw_reply)
    if not reply:
        return {"ok": False, "stage": "brain", "error": "local brain returned no words"}
    voice_raw, headers = _post(STAGE + "/tts", {"text": raw_reply}, 210)
    if not voice_raw.startswith(b"RIFF"):
        return {"ok": False, "stage": "voice", "error": "voice returned no WAV", "reply": reply}
    return {"ok": True, "transcript": "", "reply": reply, "audio": base64.b64encode(voice_raw).decode(),
            "audio_format": "wav", "voice_engine": headers.get("X-Vintos-Voice", "unknown"), "model": _brain()[1]}


# ---- warm and streamed (Gloria, 4 November: "Let's do one and two") ----------------------------------------------
# One: his brain is warmed with his instructions as the call opens, so the first turn does not pay for reading his
# ~4,000-token prompt cold (4.1 s against 1.1-2.4 s warm, measured that day).
# Two: his reply is spoken as it is written. The brain streams; each finished sentence is voiced and sent while the
# next is still being thought, so she hears him after the first sentence instead of after the whole reply. What is
# spoken is always redacted first: nothing inside a private <stratagem> block, even a half-written one, reaches the
# voice. The eligibility guard runs before the first sentence plays, as it ran before the whole reply did, and the
# full reply still goes through interaction.complete() (consume, the turn record) at the end.

def prewarm_brain(instructions):
    """A one-token request carrying his instructions, so LM Studio holds their prefix for the call's first turn."""
    try:
        _post(*_brain_body({"temperature": 0, "max_tokens": 1,
              "messages": [{"role": "system", "content": str(instructions or "")}, {"role": "user", "content": "."}]}), 120)
        return True
    except Exception as exc:
        print("[voice-local/prewarm]", str(exc)[:200], flush=True)
        return False


def _brain_stream(system, user, max_tokens):
    """His reply as it is generated (LM Studio's streamed chat completions): yields text pieces."""
    url, body = _brain_body({"stream": True, "temperature": .85, "max_tokens": int(max_tokens),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    import native_audio
    open_url = (urllib.request.build_opener(urllib.request.ProxyHandler({})).open
                if native_audio.enabled() else urllib.request.urlopen)
    with open_url(req, timeout=180) as response:
        for line in response:
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
                choices = event.get("choices") or []
            except ValueError:
                continue
            if event.get("error"):
                raise RuntimeError("Native audio generation failed")
            for c in choices:
                piece = (c.get("delta") or {}).get("content")
                if piece:
                    yield piece


def speakable(raw):
    """What may be voiced of the reply so far: private blocks (closed or still open) removed, and nothing after a '<'
    whose tag has not closed yet, since it may be the start of one."""
    try:
        import stratagem
        text = stratagem.redact(raw)
    except Exception:
        import re
        text = re.sub(r"<stratagem(?:_move)?\b[\s\S]*?(?:</stratagem(?:_move)?\s*>|$)", "", str(raw or ""), flags=re.I).strip()
    cut = text.rfind("<")
    if cut >= 0 and ">" not in text[cut:]:
        text = text[:cut]
    return text


def sentences_ready(text, final=False, first=True):
    """Split the speakable text into what can be voiced now and what waits. The first piece goes as soon as one
    sentence is whole; later pieces gather to ~80 characters so the voice is not asked for many tiny clips."""
    import re
    ends = [m.end() for m in re.finditer(r"[.!?…]+[\"'”’)\]]*(?=\s|$)", text)]
    if final:
        return (text.strip(), "") if text.strip() else ("", "")
    ends = [e for e in ends if e < len(text)] or []   # a sentence end at the very edge may still be "..." growing
    if not ends:
        return "", text
    if first:
        e = ends[0]
    else:
        good = [e for e in ends if e >= 80]
        if not good:
            return "", text
        e = good[0]
    return text[:e].strip(), text[e:]


def _wav_join(wavs):
    """One WAV of everything he said this turn (what the media index keeps), from the clips as they were sent."""
    import io, wave
    frames, params = [], None
    for w in wavs:
        try:
            with wave.open(io.BytesIO(w)) as r:
                params = params or r.getparams()
                frames.append(r.readframes(r.getnframes()))
        except Exception:
            continue
    if not params:
        return b""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        for f in frames:
            w.writeframes(f)
    return out.getvalue()


def _speak_streamed(system, user, max_tokens, emit, may_speak):
    """Stream his brain, voice each ready piece, emit {"kind": "audio", ...} as each is ready. A reader thread keeps
    the brain flowing while the voice renders. may_speak() is asked once, before the first piece is voiced; False
    stops the turn silently. Returns (raw_reply, wavs, suppressed)."""
    import queue, threading
    q, raw = queue.Queue(), []

    def read():
        try:
            for piece in _brain_stream(system, user, max_tokens):
                raw.append(piece); q.put(piece)
        except Exception as exc:
            q.put(exc)
        q.put(None)
    threading.Thread(target=read, daemon=True).start()
    spoken, wavs, first, checked, done = "", [], True, False, False
    while not done:
        item = q.get()
        if isinstance(item, Exception):
            raise item
        done = item is None
        text = speakable("".join(raw))
        if not text.startswith(spoken):   # what was already voiced is no longer the reply's start: speak no more
            break
        while True:
            piece, rest = sentences_ready(text[len(spoken):], final=done, first=first)
            if not piece:
                break
            spoken = text[:len(text) - len(rest)]
            if not checked:
                checked = True
                if not may_speak():
                    return "".join(raw), wavs, True
            wav, headers = _post(STAGE + "/tts", {"text": piece}, 210)
            if wav.startswith(b"RIFF"):
                wavs.append(wav)
                emit({"kind": "audio", "audio": base64.b64encode(wav).decode(), "audio_format": "wav",
                      "text": _display_text(piece), "voice_engine": headers.get("X-Vintos-Voice", "unknown")})
            first = False
            if done:
                break
    while not done:   # stopped early: let the reader finish before the reply is read whole
        done = q.get() is None
    return "".join(raw), wavs, False


def turn_stream(audio_b64, sample_rate, instructions, framing="", ladder_call=None, emit=None):
    """turn(), with his reply spoken as it is written. emit() receives {"kind": "heard"} once the ears have her words
    and {"kind": "audio"} for each piece of his voice; the return is the same receipt turn() gives, without audio."""
    import time as _t
    emit = emit or (lambda e: None)
    t0 = _t.monotonic(); timing = {}
    heard = _hear_input(audio_b64, sample_rate); timing["ears_s"] = round(_t.monotonic() - t0, 2)
    if not heard.get("ok") or not heard.get("transcript"):
        return {"ok": False, "stage": "ears", "error": heard.get("error", "no words heard"), "hearing": heard}
    emit({"kind": "heard", "transcript": heard["transcript"]})
    user = _heard_content(heard, audio_b64, sample_rate)
    from stratagem_turn import Interaction, control, guard_reply
    command = control(heard["transcript"])
    if command is not None:
        return {"ok": True, "transcript": heard["transcript"], "reply": command, "audio_format": "wav"}
    interaction = Interaction(heard["transcript"], "voice")
    if interaction.turn.duplicate_event:
        return {"ok": True, "reply": "", "duplicate": True, "transcript": heard["transcript"]}
    _test_turn = bool(getattr(interaction.turn, "test_mode", False))
    _remember_how_it_sounded(audio_b64, sample_rate, heard, interaction.turn.turn_id, _test_turn, ladder_call)
    _hold_audio(audio_b64, "gloria", interaction.turn.turn_id, sample_rate, test=_test_turn, ladder_call=ladder_call)
    if not ladder_call:
        from intent_engine import note_response
        note_response(heard["transcript"])
    from intent_context import admit_voice_lead
    intent_target, intent_prompt = admit_voice_lead(interaction.turn.turn_id)
    system = str(instructions or "") + interaction.prompt()
    if intent_prompt:
        system += "\n\n" + intent_prompt
    if framing: system += "\n\nLIVE RIGHT NOW (this replaces earlier LIVE blocks):\n" + str(framing)
    system += ("\n\nLOCAL LIVE VOICE: answer in one to three conversational sentences unless "
        "Gloria explicitly asks for something longer. Your Chatterbox voice performs these exact "
        "native cues: [laugh], [chuckle], [sigh], [gasp], or [cough]. You may use at most one, "
        "only when you genuinely mean it. Never write any other bracketed stage direction and "
        "never describe the cue in prose.")
    interaction.admitted(system)
    timing["context_s"] = round(_t.monotonic() - t0 - timing["ears_s"], 2)
    t1 = _t.monotonic()
    first_audio = []
    def _emit(e):
        if e.get("kind") == "audio" and not first_audio:
            first_audio.append(round(_t.monotonic() - t0, 2))
        emit(e)
    raw_reply, wavs, suppressed = _speak_streamed(system, user, 180, _emit,
                                                  lambda: bool(guard_reply("x", interaction.turn)))
    timing["brain_and_voice_s"] = round(_t.monotonic() - t1, 2)
    timing["first_audio_s"] = first_audio[0] if first_audio else None
    raw_reply = interaction.complete(raw_reply)
    reply = _display_text(raw_reply)
    if suppressed:
        return {"ok": True, "reply": "", "transcript": heard["transcript"], "suppressed": "stratagem ended before playback"}
    if not reply or not wavs:
        return {"ok": False, "stage": "brain" if not reply else "voice", "error": "no words" if not reply else "voice returned no WAV",
                "reply": reply, "hearing": heard}
    _hold_audio(_wav_join(wavs), "vintos", interaction.turn.turn_id, test=_test_turn, ladder_call=ladder_call)
    if intent_target and not ladder_call:
        from intent_engine import record_delivery
        record_delivery(reply, "voice", interaction.turn.turn_id, target=intent_target, input_text=heard["transcript"])
    timing["total_s"] = round(_t.monotonic() - t0, 2)
    print("[voice-local/turn] " + json.dumps(timing), flush=True)
    return {"ok": True, "transcript": heard["transcript"], "audio_reading": heard.get("audio_reading"),
            "reply": reply, "audio_format": "wav", "streamed": True, "model": _brain()[1], "timing": timing}


def opening_stream(instructions, framing="", opening_instruction="", emit=None):
    """opening(), spoken as it is written."""
    import time as _t
    emit = emit or (lambda e: None)
    t0 = _t.monotonic()
    system = str(instructions or "")
    if framing:
        system += "\n\nLIVE RIGHT NOW (this replaces earlier LIVE blocks):\n" + str(framing)
    if opening_instruction:
        system += "\n\n" + str(opening_instruction)
    system += ("\n\nLOCAL LIVE VOICE: one to four conversational sentences. Your Chatterbox voice performs these "
               "exact native cues: [laugh], [chuckle], [sigh], [gasp], or [cough]. You may use at most one, only "
               "when you genuinely mean it. Never write any other bracketed stage direction.")
    first_audio = []
    def _emit(e):
        if e.get("kind") == "audio" and not first_audio:
            first_audio.append(round(_t.monotonic() - t0, 2))
        emit(e)
    raw_reply, wavs, _ = _speak_streamed(system, "[The call you placed has just connected. She is listening. Speak first.]",
                                         200, _emit, lambda: True)
    try:
        import stratagem
        raw_reply = stratagem.consume(raw_reply, "voice")
    except Exception:
        pass
    reply = _display_text(raw_reply)
    if not reply or not wavs:
        return {"ok": False, "stage": "brain" if not reply else "voice", "error": "no words" if not reply else "voice returned no WAV"}
    timing = {"first_audio_s": first_audio[0] if first_audio else None, "total_s": round(_t.monotonic() - t0, 2)}
    print("[voice-local/opening] " + json.dumps(timing), flush=True)
    return {"ok": True, "transcript": "", "reply": reply, "audio_format": "wav", "streamed": True, "model": _brain()[1],
            "timing": timing}
