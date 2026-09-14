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
assert "_avAudioEl.src=url" in speak and "_avAudioEl.play()" in speak
assert "data:audio/wav;base64" in client and "data:audio/mp3;base64,SUQzBAAAAAAA" not in client

print("14/14 passed")
