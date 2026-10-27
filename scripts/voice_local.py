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
BRAIN = os.environ.get("VINTOS_LOCAL_BRAIN", "gemma-4-26b-a4b-it-uncensored")

# This call, for the media index (media_embed.py): a label only, so the turns of one call can be found together.
# Opened when the call's models are loaded (or by its first turn), closed by the call's end route.
_CALL = {"id": None}


def call_id():
    if not _CALL["id"]:
        import time
        _CALL["id"] = "lc-%d-%d" % (int(time.time() * 1000), os.getpid())
    return _CALL["id"]


def _hold_audio(audio, speaker, turn_id, sample_rate=24000, test=False):
    """Hand one side of this turn to the media index (EmbeddingGemma 2, Gloria 26 October: both voices). The bytes
    wait in a private 0700 directory and are deleted when the batch after the call embeds them; nothing is
    embedded here, so the turn is not slowed. Never raises."""
    try:
        import media_embed
        media_embed.hold_call_audio(audio, speaker, turn_id=turn_id, session_id=call_id(),
                                    sample_rate=sample_rate, test=test)
    except Exception as exc:
        print("[voice-local/media-embed]", str(exc)[:200], flush=True)


def end_call():
    """The call is over: close its label and start the batch that embeds its held audio (then deletes it)."""
    _CALL["id"] = None
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
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as exc:
        raise RuntimeError("%s: %s" % (exc.code, exc.read().decode(errors="replace")[:300]))


def models(active, evict_ears=False):
    if active:
        _CALL["id"] = None
        call_id()
    raw, _ = _post(STAGE + "/voice/models", {"active": bool(active),
        "evict_ears": bool(evict_ears)}, 100)
    return json.loads(raw)


def _display_text(text):
    """The house copy cannot assume the Mac module is importable."""
    import re
    out = re.sub(r"\[[^\]\n]{1,240}\]", " ", str(text or ""))
    out = re.sub(r"</?[A-Za-z][^>\n]{0,80}>", " ", out)
    out = re.sub(r"\*+", "", out)
    return " ".join(out.split())


def turn(audio_b64, sample_rate, instructions, framing=""):
    heard_raw, _ = _post(STAGE + "/listen", {"audio": audio_b64,
        "sample_rate": int(sample_rate or 24000)}, 180)
    heard = json.loads(heard_raw)
    if not heard.get("ok") or not heard.get("transcript"):
        return {"ok":False,"stage":"ears","error":heard.get("error","no words heard"),"hearing":heard}
    evidence = {"reading":heard.get("audio_reading"), "pipeline":heard.get("ears"),
                "audio_native_gemma":bool(heard.get("audio_native_gemma"))}
    user = ("Gloria said aloud:\n" + heard["transcript"] +
            "\n\n[AUDIO-NATIVE READING — Gemma 3n received the recording itself:]\n" +
            json.dumps(evidence, ensure_ascii=False))
    from stratagem_turn import Interaction, control
    command = control(heard["transcript"])
    if command is not None:
        return {"ok": True, "transcript": heard["transcript"], "reply": command, "audio": "", "audio_format": "wav"}
    interaction = Interaction(heard["transcript"], "voice")
    if interaction.turn.duplicate_event:
        return {"ok": True, "reply": "", "duplicate": True, "transcript": heard["transcript"]}
    try:   # proposal 17: how it sounded, kept as an attributed observation; the audio itself is not kept
        from auditory_memory import record as _remember_heard
        _remember_heard(audio_b64, sample_rate, heard, turn_id=interaction.turn.turn_id,
                        test_mode=bool(getattr(interaction.turn, "test_mode", False)))
    except Exception as exc:
        print("[voice-local/auditory-memory]", str(exc)[:200], flush=True)
    _test_turn = bool(getattr(interaction.turn, "test_mode", False))
    _hold_audio(audio_b64, "gloria", interaction.turn.turn_id, sample_rate, test=_test_turn)
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
    brain_raw, _ = _post(LM + "/v1/chat/completions", {"model":BRAIN,
        "messages":[{"role":"system","content":system},{"role":"user","content":user}],
        "temperature":.85,"max_tokens":180}, 180)
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
    _hold_audio(voice_raw, "vintos", interaction.turn.turn_id, test=_test_turn)   # what she will hear
    if intent_target:
        from intent_engine import record_delivery
        record_delivery(reply, "voice", interaction.turn.turn_id, target=intent_target,
                        input_text=heard["transcript"])
    return {"ok":True,"transcript":heard["transcript"],
            "audio_reading":heard.get("audio_reading"),"reply":reply,
            "audio":base64.b64encode(voice_raw).decode(),"audio_format":"wav",
            "voice_engine":headers.get("X-Vintos-Voice","unknown"),"model":BRAIN}


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
    brain_raw, _ = _post(LM + "/v1/chat/completions", {"model": BRAIN,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": "[The call you placed has just connected. She is listening. Speak first.]"}],
        "temperature": .85, "max_tokens": 200}, 180)
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
            "audio_format": "wav", "voice_engine": headers.get("X-Vintos-Voice", "unknown"), "model": BRAIN}
