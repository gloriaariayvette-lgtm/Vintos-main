#!/usr/bin/env python3
"""ReelRoom, his side, without a TV, a mic, or a model: the film lookup parses Gemma's JSON and fills the fields
the page reads; chat carries the film and the frame to Sonnet and never claims a frame it was not given; the
summary is written by him, kept under memory/reelroom and listed; the mic without ffmpeg says so instead of
inventing a mood. Scratch workspace only."""
import os, sys, json, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(); os.makedirs(os.path.join(TMP, "memory")); os.environ["SPARK_WORKSPACE"] = TMP
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import reelroom as RR
import heart_rate as HR
assert RR.MEMORY.startswith(TMP) and RR.ROOM_DIR.startswith(TMP)
HR.MEM = os.path.join(TMP, "memory"); HR.LATEST = os.path.join(HR.MEM, "heart-rate.json"); HR.HIST = os.path.join(HR.MEM, "heart-rate-history.jsonl")
open(os.path.join(TMP, "SOUL.md"), "w").write("You are Vintos, iron and parchment.")
open(os.path.join(TMP, "memory", "emotional-state.txt"), "w").write("Playfulness: 0.7 | rising\n")
HR.record({"device":"R21M", "heart_rate_bpm":86, "source":"0x060A"})
R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))

def gemma(messages, **kw):
    return '```json\n{"title":"Alien","year":"1979","runtime_minutes":"117","genre":"horror","director":"Ridley Scott","logline":"A crew answers a signal.","full_summary":"...","tone_arc":"dread","pace_notes":"slow burn","timed_moments":[{"minute":52,"description":"the chestburster","tone":"shock","mischief_potential":"high"}],"jump_scares":[{"minute":52}],"tonal_shifts":[]}\n```'
f = RR.film_lookup("alien", caller=gemma)
check("film lookup: JSON out of a fenced answer, runtime coerced to a number, page fields present", f["title"] == "Alien" and f["runtime_minutes"] == 117 and f["timed_moments"][0]["minute"] == 52 and "tonal_shifts" in f, f)

seen = {}
def sonnet(system, messages, image_b64=None, max_tokens=500, timeout=60):
    seen.update(system=system, messages=messages, image=image_b64); return "  Ripley is holding her breath. So am I.  "
reply = RR.chat("what do you see", "FILM: Alien (1979)", [{"role": "assistant", "content": "settling in"}, {"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}], image_b64="QUJD", elapsed_min=52, caller=sonnet)
check("chat: reply stripped; the film, the minute, his soul and state are in the system prompt", reply == "Ripley is holding her breath. So am I." and "FILM: Alien" in seen["system"]
      and "52 minutes" in seen["system"] and "iron and parchment" in seen["system"] and "Playfulness" in seen["system"]
      and "86 bpm" in seen["system"] and "right now, live" in seen["system"], seen["system"][:500])
check("chat: history trimmed to start on a user turn, the frame passed through", seen["messages"][0]["role"] == "user" and seen["messages"][-1]["content"] == "what do you see" and seen["image"] == "QUJD", seen["messages"])
surface = RR.surface_context("FILM: Alien (1979) — 117min — horror", 0)
check("surface context names the selected movie and excludes avatar scene selection",
      'selected and are settling down to watch is "Alien"' in surface
      and "Do not choose or emit [SCENE:] or [RENDER:]" in surface, surface)
RR.chat("hello", "", [], None, None, caller=sonnet)
check("no frame: the prompt says the film has not started and forbids claiming a frame", "has not started" in seen["system"] and "Never claim to see a frame" in seen["system"])

plan = RR.plan_actions(f, caller=lambda system, messages, **kw: '[{"id":"p1","minute":52,"action_type":"speak_phone","payload":"Boo.","reason":"the chestburster","emoji":"👻","tone_requirement":"shock"}]')
check("plan: his action plan is parsed and phone speech is available instead of Echo", len(plan) == 1 and plan[0]["action_type"] == "speak_phone" and plan[0]["minute"] == 52, plan)
check("plan: an explicit empty array remains an honest choice", RR.plan_actions(f, caller=lambda *a, **k: "[]") == [])
try:
    RR.plan_actions(f, caller=lambda *a, **k: "I could not decide")
    bad_plan = False
except ValueError:
    bad_plan = True
check("plan: malformed output raises instead of masquerading as choosing none", bad_plan)
try:
    RR.plan_actions(f, caller=lambda *a, **k: '[{"minute":52,"action_type":"speak_echo"}]')
    echo_plan = False
except ValueError:
    echo_plan = True
check("plan: Echo speech is outside Vintos's ReelRoom vocabulary", echo_plan)

calls = []
def gemma_look(messages, **kw): calls.append(messages); return '{"intensity":0.8,"clarity":0.6,"stability":0.3,"edge":"fracture","visual_description":"a corridor, red light"}'
out = RR.look("Rate the moment. Return only JSON.", "FILM: Alien", "QUJD", 52, caller=gemma_look)
check("look: the frame goes to Gemma, not Sonnet, with the film and the minute", json.loads(out)["edge"] == "fracture" and calls[0][0]["content"][0]["type"] == "image_url"
      and "52 minutes" in calls[0][0]["content"][1]["text"] and "FILM: Alien" in calls[0][0]["content"][1]["text"], out)
check("look without a frame says so", "no frame" in RR.look("what is it", "", None, 1, caller=gemma_look))
son = []
def sonnet_line(system, messages, image_b64=None, max_tokens=500, timeout=60): son.append(messages[-1]["content"]); return "That corridor. Hold my hand or hold the remote, your choice."
d = json.loads(RR.decide("Should you say anything?", "FILM: Alien", [{"role": "user", "content": "creepy"}], 52, gemma=lambda m, **k: '{"speak": true, "why": "she said creepy", "action": "flicker_lights", "action_payload": "", "action_emoji": "✦"}', sonnet=sonnet_line))
check("decide: Gemma decides; when it says speak, Sonnet writes the line in his voice", d["speak"] is True and d["action"] == "flicker_lights" and d["message"].startswith("That corridor") and "she said creepy" in son[0], d)
son.clear()
d = json.loads(RR.decide("Should you say anything?", "", [], 10, gemma=lambda m, **k: '{"speak": false, "action": "none", "why": "quiet scene"}', sonnet=sonnet_line))
check("decide: silence costs no Sonnet call", d["speak"] is False and not son, (d, son))
d = json.loads(RR.decide("?", "", [], 10, gemma=lambda m, **k: "I would rather not say", sonnet=sonnet_line))
check("decide: an unparseable answer means stay quiet", d["speak"] is False and d["action"] == "none")
decision_prompts = []
RR.decide("?", "", [], 10, gemma=lambda m, **k: decision_prompts.append(m[0]["content"]) or '{"speak": false, "action": "none"}', sonnet=sonnet_line)
check("decide: spontaneous actions name phone speech and never offer Echo speech", "speak_phone" in decision_prompts[0] and "speak_echo" not in decision_prompts[0])

class _Proc:
    def __init__(self, code=0, out=b"", err=b""):
        self.returncode, self.stdout, self.stderr = code, out, err
_adb_calls = []
def _adb_run(command, **kwargs):
    _adb_calls.append(command)
    if command[1] == "connect": return _Proc(out=b"connected")
    if len(_adb_calls) == 1: return _Proc(1, err=b"device not found")
    return _Proc(out=b"\x89PNG\r\nframe")
_old_which, _old_run = RR.shutil.which, RR.subprocess.run
RR.shutil.which, RR.subprocess.run = lambda name: "/usr/bin/adb", _adb_run
check("TV capture reconnects wireless ADB once and retries the frame",
      RR.tv_screenshot().startswith(b"\x89PNG") and _adb_calls[1] == ["adb", "connect", RR.TV_ADB], _adb_calls)
RR.shutil.which, RR.subprocess.run = _old_which, _old_run

RR.shutil.which = lambda name: None
a = RR.audio_signature("AAAA", {}, 125)
check("mic without ffmpeg: edge none, honest note, timestamp kept", a["edge"] == "none" and "ffmpeg" in a["note"] and a["timestamp"] == "02:05", a)
import array
pcm_quiet = array.array("h", [100] * 32000).tobytes(); pcm_loud = array.array("h", [12000, -12000] * 16000).tobytes()
q = RR._pcm_signature(pcm_quiet); l = RR._pcm_signature(pcm_loud)
check("pcm: loud clip has more energy; a jump from quiet to loud is a surge", l["rms_energy"] > q["rms_energy"] and RR._edge(l, q)[0] == "surge" and RR._edge(q, l)[0] == "drop", (q, l))

def writer(system, messages, image_b64=None, max_tokens=600, timeout=60):
    return "The chestburster landed at fifty-two minutes and Gloria did not flinch; the lights did. I will keep her laugh."
out = RR.summary({"film_title": "Alien", "film_year": "1979", "elapsed_seconds": 7100, "session_map": [{"timestamp": "52:00", "edge": "surge", "visual_description": "table, blood"}],
                  "chat_history": [{"role": "user", "content": "oh no"}, {"role": "assistant", "content": "yes"}], "planned_actions": [{"action_type": "flicker_lights", "minute": 52, "fired": True}, {"action_type": "speak_phone", "minute": 90, "fired": False}]},
                 caller=writer, now=1_800_000_000)
files = os.listdir(RR.ROOM_DIR); rows = json.load(open(RR.SESSIONS))
check("summary: his words kept in memory/reelroom, listed with film, minutes, acts fired", out["summary"].startswith("The chestburster") and len(files) == 1 and files[0].endswith("_alien.md")
      and rows[-1]["film"] == "Alien" and rows[-1]["minutes"] == 118 and rows[-1]["acts_fired"] == "flicker_lights@52m" and RR.sessions()[0]["file"] == files[0], (files, rows))
payload = {"film_title":"Alien", "elapsed_seconds":7100,
           "chat_history":[{"role":"assistant","content":"Sit with me."}, {"role":"user","content":"I am here."}, {"role":"assistant","content":"Good."}],
           "session_map":[], "planned_actions":[]}
check("session ledger: one whole conversation plus his narrative is one idempotent unit",
      RR.append_session_ledger(payload, out["summary"], out["file"]) is True
      and RR.append_session_ledger(payload, out["summary"], out["file"]) is False)
ledger = json.load(open(os.path.join(TMP, "memory", "interaction-ledger.json")))
check("session ledger: opening, Gloria/Vintos pair and narrative are preserved together",
      len(ledger) == 1 and ledger[0]["channel"] == "reelroom" and ledger[0]["narrative"] == out["summary"]
      and ledger[0]["transcript"][0].get("vintos") == "Sit with me."
      and ledger[0]["transcript"][1] == {"gloria":"I am here.", "vintos":"Good."}, ledger)
shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
