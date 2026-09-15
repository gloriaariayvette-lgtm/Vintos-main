#!/usr/bin/env python3
"""Avatar replies commit their words before bounded, authority-free media work."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
client = (ROOT / "clients/mobile/index.html").read_text()
lifecycle = (ROOT / "clients/mobile/client_lifecycle.js").read_text()

# This suite writes nowhere and has no network/provider client to escape through.
assert not any(token in __file__ for token in ("~/.vintos", "/home/gloria"))
assert "async function auxiliary" in lifecycle
aux = lifecycle.split("async function auxiliary", 1)[1].split("function begin", 1)[0]
assert "AbortController" in aux and "12000" in aux
assert "X-Client-Turn-Id" not in aux, "auxiliary media must carry no conversational authority"

send = client.split("async function avSendChat()", 1)[1].split("// ── THREADS TAB", 1)[0]
requested = send.index("await VintosUI.request(API+'/api/avatar/chat'")
assert send.index("VintosUI.ack(inp,sentDraft)") < requested
assert send.index("_avLogMsg('user',text)") < requested
assert send.index("_avChatHistory.push({role:'user',content:text})") > requested
assert "history:historyForRequest" in send
visible = send.index("_avShowBubble(display)")
released = send.index("VintosUI.finish(turn); turnOpen=false")
media = send.index("_avStartReplyMedia(display,scenes)")
assert visible < released < media, "words first, release second, detached media last"
assert "if(scenes && scenes[0]) await _avStage.setRoom" not in send
assert "await _avStage.speak" not in send
assert "_avUnlockAudio();" in send

speak = client.split("speak: async function(text, requestedRoom)", 1)[1].split("\n  }\n};", 1)[0]
assert "const deadline=Date.now()+12000" in speak
assert "VintosUI.auxiliary" in speak and "muted:true" in speak
assert "lightweight:true" in speak, "speech must not start the blurred duplicate decoder"
assert "_avAudioEl.src=url" in speak and "_avAudioEl.play()" in speak
assert "data:audio/wav;base64" in client and "data:audio/mp3;base64,SUQzBAAAAAAA" not in client

stage_el = client.split("_el: function(i)", 1)[1].split("_fetchBlob:", 1)[0]
assert stage_el.count("pointer-events:none") >= 3, "stage media must never participate in touch hit-testing"
show = client.split("_show: async function(url, opts)", 1)[1].split("resolve: function(name)", 1)[0]
assert "lightweight=!!opts.lightweight" in show
assert "if(!lightweight)L.bg.play()" in show
assert "L.bg.removeAttribute('src')" in show
reply_media = client.split("function _avStartReplyMedia", 1)[1].split("let _avLastScreenshot", 1)[0]
assert "requestAnimationFrame" in reply_media and "setTimeout" in reply_media
drawer = client.split("function _avDrawerInit()", 1)[1].split("// ── STUDY tab", 1)[0]
assert "releasePointerCapture" in drawer and "lostpointercapture" in drawer
assert 'id="av-drawer"' in client and 'pointer-events:auto;' in client.split('id="av-drawer"', 1)[1].split('>', 1)[0]
assert 'id="av-chat-strip"' in client and 'pointer-events:auto;' in client.split('id="av-chat-strip"', 1)[1].split('>', 1)[0]

voice = client.split("function startVoiceCallWithToken", 1)[1].split("function endVintosCall", 1)[0]
transcript = voice.split("conversation.item.input_audio_transcription.updated", 1)[1].split("response.output_audio_transcript.done", 1)[0]
assert "response.gloria=session.gloriaTurn||''" in transcript
assert transcript.index("response.gloria=session.gloriaTurn||''") < transcript.index("_vcRefreshFraming()")

print("29/29 passed")
