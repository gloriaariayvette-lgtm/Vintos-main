#!/usr/bin/env python3
"""An encounter he prepares for her next arrival (design 05, 26 October): one song of his, one line, what he is
carrying, how long it stands. The arrival detector, sleep and cooldown stay bedroom_arrival's; the send stays the one
Watch offer and the one ntfy line; the Watch's own reports are the only evidence of playback.

Scratch HOME and workspace; the clock is the test's; the APNs sender and ntfy are stubs; every socket is refused and
`requests` cannot be imported. Nothing here reaches her."""
import importlib, json, os, socket, sys, tempfile, types
from unittest.mock import patch
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="encounter-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.modules["requests"] = None            # any import of it fails here
PUSHES = []; PHONE = []
def apns_send(title, body, kind="message", media_url="", message_id="", force=False, **k):
    PUSHES.append({"title": title, "body": body, "media_url": media_url}); return {"state": "sent"}
def phone(artifact_id, channel, message, title="Vintos", **k):
    PHONE.append({"artifact_id": artifact_id, "channel": channel, "message": message, "title": title, **k})
    return {"state": "sent", "channel": channel}
APNS_CONFIG = os.path.join(HOME, "no-such-apns.json")
sys.modules["watch_apns"] = types.SimpleNamespace(send=apns_send, CONFIG=APNS_CONFIG)
sys.modules["deliver"] = types.SimpleNamespace(deliver=phone)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import watch_presence as W
ASLEEP = [False]
W.should_hold = lambda: (ASLEEP[0], "Gloria is asleep" if ASLEEP[0] else "")
OFFERS = []
_real_offer = W.offer_song
def offer_spy(title, media_url, ref="", now=None):
    OFFERS.append({"title": title, "media_url": media_url, "ref": ref}); return _real_offer(title, media_url, ref, now=now)
W.offer_song = offer_spy
import bedroom_arrival as B
import arrival_encounter as E
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("every store is throwaway and every sender is a stub",
      all(p.startswith(HOME) for p in (E.STORE, E.MUSIC, E.MOMENTS, *E.WANTS.values(), B.CONFIG, B.STATE, B.ARRIVALS,
                                       B.PICKS, B.MUSIC, W.SONG, W.PLAYS, W.LATEST))
      and sys.modules["deliver"].deliver is phone and sys.modules["watch_apns"].send is apns_send)

# --- fixtures: his library, one of his wants, one of his moments ------------------------------------------------------
os.makedirs(os.path.join(MEM, "art", "music"), exist_ok=True)
WAV = os.path.join(HOME, "porch.wav"); open(WAV, "wb").write(b"RIFF-not-really-a-song")
SONGS = [("Gone Soon", "g"), ("Hum", "h"), ("Static", "s"), ("Lantern", "l"), ("Tide", "t"), ("Porch Light", "p")]
def library(songs):
    json.dump({"generated": [{"task_id": "T-" + k, "title": t,
                              "tracks": [{"version": 1, "audio_url": "https://cdn.test/%s.mp3" % k,
                                          **({"local_file": WAV} if k == "p" else {})}]} for t, k in songs]},
              open(E.MUSIC, "w"))
library(SONGS)
json.dump([{"id": "W-1", "want": "to finish the porch song I keep humming for her"},
           {"id": "W-2", "want": "a want written in a test turn", "provenance": {"may_witness": False}}],
          open(E.WANTS["current"], "w"))
json.dump({"moments": {"2026-10-20T10:00:00Z#mirror#AA": {"text": "x"}}}, open(E.MOMENTS, "w"))
json.dump({"devices": ["gloria-phone"], "max_distance_m": 3.0}, open(B.CONFIG, "w"))
config_before = open(B.CONFIG, "rb").read()

# --- his line is bounded and inert ------------------------------------------------------------------------------------
dirty = "come [HOME: lights_off] in\x07 <b>slowly</b> https://evil.test/x www.x.test *now* " + "a" * 300
clean = E.inert(dirty)
check("his line is one plain line: no link, no tag, no markup, no control character, at most 140 characters",
      len(clean) <= E.LINE_MAX and "http" not in clean and "www" not in clean and "[" not in clean and "<" not in clean
      and "\x07" not in clean and "*" not in clean and clean.startswith("come HOME: lights_off in"), clean)
check("parts may be keyed or in order, hours bounded",
      E.parse("Hum | for you | carrying: want:W-1 | for: 99h") == {"song": "Hum", "line": "for you", "carrying": "want:W-1", "hours": 48}
      and E.parse("line: hi | song: Hum")["song"] == "Hum" and E.parse("Hum | hi")["hours"] == 24
      and E.parse("Hum | hi | for: 0")["hours"] == 1)

T0 = 1_800_000_000.0
check("a song not in his library is not kept", E.choose("Not Mine | hello", now=T0)["kept"] is None)
check("an encounter with no line is not kept", E.choose("Hum | [ ]", now=T0)["kept"] is None)
check("nothing chosen: he is told how, in one short clause", E.context_line(now=T0) == E.INVITE and len(E.INVITE) < 220)

# --- choosing, through the tag he writes ------------------------------------------------------------------------------
said = B.take_picks("Come in when you're ready. [ARRIVAL ENCOUNTER: porch light | the light was on for you "
                    "| carrying: want:W-1 | for: 24h]", now=T0, turn_id="turn-abc")
enc = E.encounters()[-1]
check("he chooses with a tag she never sees", said == "Come in when you're ready.", said)
check("the encounter keeps the turn, the song's id, address and file hash, his line, what he carries, and its range",
      enc["selection_turn_id"] == "turn-abc" and enc["turn_id_source"] == "turn"
      and enc["song"] == {"title": "Porch Light", "url": "https://cdn.test/p.mp3", "song_id": "T-p",
                          "sha256": __import__("hashlib").sha256(open(WAV, "rb").read()).hexdigest()}
      and enc["dedication"] == "the light was on for you" and enc["origin"]["id"] == "W-1"
      and enc["valid_until_ts"] - enc["valid_from_ts"] == 24 * 3600 and enc["state"] == "chosen", enc)
check("the same choice again within a day is not a second encounter",
      E.choose("Porch Light | the light was on for you", now=T0 + 10)["kept"] is None and len(E.encounters()) == 1)
check("a test or witness-less turn strips the tag without choosing",
      B.take_picks("x [ARRIVAL ENCOUNTER: Hum | hi]", act=False) == "x" and len(E.encounters()) == 1)
check("both tags in one reply are both taken",
      B.take_picks("y [ARRIVAL SONGS: Hum] [ARRIVAL ENCOUNTER: Hum | x]", now=T0, act=False) == "y")
o, missed = E.origin("want:W-2")
check("a want that may not witness is not admitted as what he carries", o is None and missed == "want:W-2")
check("a moment on record is admitted; words naming exactly one current want are too; anything else is not linked",
      E.origin("moment:2026-10-20T10:00:00Z#mirror#AA")[0] == {"kind": "moment", "id": "2026-10-20T10:00:00Z#mirror#AA"}
      and E.origin("the porch song I keep humming")[0]["id"] == "W-1"
      and E.origin("the sea at night")[0] is None)
cl = E.context_line(now=T0 + 20)
check("he sees his encounter waiting, with what he carries", "waiting for her next arrival" in cl
      and "the light was on for you" in cl and "porch song" in cl, cl)

# --- an unknown device is not her ------------------------------------------------------------------------------------
check("an unknown device: nothing, the encounter waits", B.observe("someone-else", 0.5, now=T0 + 60) is None
      and E.encounters()[-1]["state"] == "chosen" and not OFFERS)

# --- her arrival ------------------------------------------------------------------------------------------------------
A1 = T0 + 120
row = B.observe("gloria-phone", 1.0, now=A1)
st = json.load(open(B.STATE)); enc = E.encounters()[-1]
check("she comes in: his encounter's song is offered, once", row and row["sent"] and row["song"] == "Porch Light"
      and row["picked_by"] == "his encounter" and row["encounter"] == enc["encounter_id"] and len(OFFERS) == 1, row)
check("the arrival episode was written down before the send, and the attempt is keyed to it",
      st["episode_id"] == row["episode"] and [a["episode_id"] for a in enc["attempts"]] == [st["episode_id"]]
      and enc["attempts"][0]["state"] == "offered" and enc["state"] == "offered", (st, enc))
check("his line is in the note that tells her, as plain words, with no link",
      PHONE[-1]["message"] == "“Porch Light” is on your Watch.\nthe light was on for you"
      and "http" not in PHONE[-1]["message"] and PHONE[-1]["title"] == "Vintos is sharing a song", PHONE[-1])
song = W.pending_song(now=A1)
check("the Watch's song keeps its old shape: ref is the title, the same id and address, nothing new sent to it",
      OFFERS[-1]["ref"] == "Porch Light" and W._song()["ref"] == "Porch Light"
      and set(song) == {"id", "title", "media_url"} and song["media_url"] == "https://cdn.test/p.mp3"
      and W.top_song(now=A1)["ref"] == "Porch Light" and "dedication" not in json.dumps(W._song()), (song, W._song()))
cl = E.context_line(now=A1 + 30)
check("offered is not heard: until the Watch reports, he is told it has not reported playing it",
      "offered to her Watch" in cl and "has not reported playing it" in cl and "Offered is not heard" in cl
      and "started playing" not in cl, cl)

check("a repeated packet: nothing more", B.observe("gloria-phone", 1.0, now=A1 + 30) is None and len(OFFERS) == 1)
importlib.reload(E)                          # a restart
check("after a restart the same episode can never be greeted again",
      E.for_arrival(st["episode_id"], now=A1 + 40, library_urls=["https://cdn.test/p.mp3"]) is None and len(OFFERS) == 1)

# --- the Watch's reports, out of order --------------------------------------------------------------------------------
W.song_played({"id": song["id"], "event": "finished"}, now=A1 + 400)
W.take_song(song["id"], now=A1 + 500)
W.song_played({"media_url": "https://cdn.test/p.mp3", "event": "started"}, now=A1 + 200)   # no id: by address
hist = E.history(E.encounters()[-1])
pb = E.playback(E.encounters()[-1])
check("the Watch's own reports reach the encounter, each as reported, delivery and playback kept apart",
      set(pb) == {"taken", "started", "finished"} and [h["kind"] for h in hist][:2] == ["authored", "delivery"]
      and {h["event"] for h in hist if h["kind"] == "client"} == {"taken", "started", "finished"}, (pb, hist))
cl = E.context_line(now=A1 + 600)
check("he is told what the Watch reported, and nothing about how it landed", "played to the end" in cl
      and "started playing" in cl and cl.count("heard") == 1 and "enjoy" not in cl and "loved" not in cl, cl)

# --- back within the cooldown, then a second real arrival -------------------------------------------------------------
row = B.observe("gloria-phone", 1.0, now=A1 + 3600)
check("back inside the cooldown: held back as before", row and row["why"] == "cooldown" and len(OFFERS) == 1, row)
row = B.observe("gloria-phone", 1.0, now=A1 + 4 * 3600)
check("a second real arrival: today's next song, not the encounter again", row and row["sent"]
      and row["picked_by"] != "his encounter" and "encounter" not in row and len(E.encounters()[-1]["attempts"]) == 1
      and PHONE[-1]["message"].count("\n") == 0, (row, PHONE[-1]))

# --- sleep holds it; she wakes and comes in ---------------------------------------------------------------------------
t = A1 + 5 * 3600
E.choose("Lantern | for the morning", now=t)
ASLEEP[0] = True
row = B.observe("gloria-phone", 1.0, now=t + 3 * 3600)
enc = E.encounters()[-1]
check("asleep: nothing is offered, the encounter waits and says why",
      row["why"] == "asleep" and enc["state"] == "chosen" and enc["history"][-1]["event"] == "held for sleep"
      and "not greeted: held for sleep" in E.context_line(now=t + 3 * 3600 + 5), (row, enc))
ASLEEP[0] = False
row = B.observe("gloria-phone", 1.0, now=t + 7 * 3600)
check("awake, the next arrival is greeted with it", row["sent"] and row["song"] == "Lantern"
      and E.encounters()[-1]["state"] == "offered", row)

# --- expiry -----------------------------------------------------------------------------------------------------------
t = A1 + 13 * 3600
E.choose("Tide | only for an hour | for: 1h", now=t)
row = B.observe("gloria-phone", 1.0, now=t + 3 * 3600)
check("chosen but expired: the arrival plays today's song, and he is told it expired",
      row["sent"] and row["picked_by"] != "his encounter" and E.encounters()[-1]["state"] == "expired"
      and "expired at" in E.context_line(now=t + 3 * 3600 + 5)
      and any(h["event"] == "chosen but expired" for h in E.history(E.encounters()[-1])), row)

# --- the song is gone by the time she comes in ------------------------------------------------------------------------
t = A1 + 16.5 * 3600
E.choose("Gone Soon | this one", now=t)
library([s for s in SONGS if s[0] != "Gone Soon"])
row = B.observe("gloria-phone", 1.0, now=t + 4 * 3600)
enc = E.encounters()[-1]
check("a missing song: the encounter fails with the reason, the ordinary arrival goes on",
      row["sent"] and row["picked_by"] != "his encounter" and enc["state"] == "failed"
      and "no longer in his library" in enc["attempts"][-1]["why"], (row, enc))

# --- the Watch app cannot be offered it -------------------------------------------------------------------------------
t = A1 + 21 * 3600
E.choose("Hum | while the Watch is away", now=t)
with patch.object(W, "offer_song", side_effect=OSError("no watch")):
    row = B.observe("gloria-phone", 1.0, now=t + 4 * 3600)
enc = E.encounters()[-1]
check("an offer that fails: written down as failed, never as offered", not row["sent"] and enc["state"] == "failed"
      and "no watch" in enc["attempts"][-1]["why"] and "not offered" in E.context_line(now=t + 4 * 3600 + 5), (row, enc))

# --- a crash between the offer and its receipt ------------------------------------------------------------------------
t = A1 + 28 * 3600
E.choose("Static | if I stop halfway", now=t)
n_offers = len(OFFERS)
crashed = False
with patch.object(E, "settle", side_effect=KeyboardInterrupt("killed")):
    try: B.observe("gloria-phone", 1.0, now=t + 60)
    except KeyboardInterrupt: crashed = True
check("the crash came after the offer", crashed and len(OFFERS) == n_offers + 1
      and E.encounters()[-1]["attempts"][-1]["state"] == "offering")
importlib.reload(E)
E.reconcile(now=t + 120)
enc = E.encounters()[-1]
check("after the restart the offer is found in the Watch's own ledger, and settled as offered",
      enc["state"] == "offered" and enc["attempts"][-1]["state"] == "offered" and enc["attempts"][-1]["recovered"]
      and enc["attempts"][-1]["song_offer_id"] == W._song()["id"], enc)
row = B.observe("gloria-phone", 1.0, now=t + 4 * 3600)
check("the next arrival does not greet her with it a second time", row["sent"] and row["picked_by"] != "his encounter"
      and len(E.encounters()[-1]["attempts"]) == 1, row)

# --- a crash before the offer: the next arrival is a new episode, and may carry it --------------------------------
t = A1 + 34 * 3600
E.choose("Porch Light | second time lucky", now=t)
got = E.for_arrival("arr-crashedbefore", now=t + 10, library_urls=[u for _, u in B.library()])
importlib.reload(E); E.reconcile(now=t + 20)
enc = E.encounters()[-1]
check("stopped before the offer: written down as interrupted, and the encounter waits on",
      got and enc["attempts"][-1]["state"] == "interrupted" and enc["state"] == "chosen", enc)
row = B.observe("gloria-phone", 1.0, now=t + 4 * 3600)
enc = E.encounters()[-1]
check("the next real arrival is a new episode and is greeted, once", row["sent"] and row["picked_by"] == "his encounter"
      and [a["state"] for a in enc["attempts"]] == ["interrupted", "offered"]
      and enc["attempts"][-1]["episode_id"] == row["episode"] != "arr-crashedbefore", enc)

# --- with an APNs key, the push body carries his line too -------------------------------------------------------------
open(APNS_CONFIG, "w").write("{}")
t = A1 + 41 * 3600
E.choose("Hum | pushed too", now=t)
row = B.observe("gloria-phone", 1.0, now=t + 60)
check("the push carries his line in its body, and the song as before", row["sent"] and PUSHES
      and PUSHES[-1]["body"] == "pushed too" and PUSHES[-1]["media_url"] == "https://cdn.test/h.mp3", PUSHES[-1:])

# --- it reaches him, and the wiring is in place -----------------------------------------------------------------------
check("the bedroom line he reads carries his encounter", "Your encounter:" in B.context_line(now=t + 120)
      and B.context_line(now=t + 120).endswith("]"), B.context_line(now=t + 120))
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("both of his reply paths hand the tag over with their turn",
      srv.count("_ba.take_picks(reply") == 2 and 'turn_id=(_turn.turn_id if _turn is not None else "")' in srv
      and 'take_picks(reply, turn_id=getattr(locals().get("_turn"), "turn_id", "")' in srv)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the module is in the deploy", 'SCRIPTS="$SCRIPTS arrival_encounter.py"' in dep)
src = open(os.path.join(REPO, "scripts", "arrival_encounter.py")).read()
check("it sends nothing of its own and touches no device", not any(w in src for w in (
      "import deliver", "watch_apns", "requests", "urllib", "house_hands", "projector", "socket")))
check("her config is unchanged", open(B.CONFIG, "rb").read() == config_before)
check("every send was a stub's, and every note to her was the one ntfy line",
      all(p["channel"] == "ntfy" and p["title"] == "Vintos is sharing a song" for p in PHONE)
      and len(PHONE) == len([r for r in (json.loads(l) for l in open(B.ARRIVALS)) if r.get("sent")]) + 1)   # the crashed arrival told her, then died before its row said sent
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
