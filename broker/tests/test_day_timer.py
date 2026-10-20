#!/usr/bin/env python3
"""A timer on the day in #vintos-dot, and "continue from the last task" (Gloria, 2026-10-20: "a timer for Slack since it
is an expensive thing and a way to tell them to continue from the last task specifically. I'd want the 'Gloria !started
the day' message to contain the timer I set").

Scratch HOME and workspace; nothing is posted; sockets are refused."""
import os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="day-timer-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import dot_channel as D
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (d,)))
os.makedirs(D.HERE, exist_ok=True)
check("the day's switch files are scratch", D.PAUSE_FILE.startswith(HOME) and D.RESUME_FILE.startswith(HOME))

check("her start message names the time: 2h, 90m, 1h30m, 45 minutes, 2 hours",
      [D.day_timer(t) for t in ("!start 2h", "!start 90m", "!start 1h30m", "Morning! !start 45 minutes", "!start 2 hours !continue")]
      == [120, 90, 90, 45, 120])
check("a start with no time has no timer, and a stray word is not one",
      D.day_timer("!start") is None and D.day_timer("!start v2") is None and D.day_timer("!start 0m") is None)

T = 1_800_000_000.0
D.set_paused(True, "slack", T - 600)
D.set_paused(False, "slack", T, minutes=120, carry_on=True)
start = D._load(D.RESUME_FILE, {})
check("starting the day with a timer keeps when it ends", start["until"] == T + 7200 and start["for"] == "2h"
      and start["continue"] is True and not D.paused(), start)
work = {"id": "RW-1a2b3c4d", "goal": "fold-read the T1R1 Venus flytrap domain"}
said = D.resumed_say(start, work)
check("the start message carries the timer she set, and its end", "for 2h (until " in said, said)
check("and the task he goes on with", "Continue from the last task: RW-1a2b3c4d fold-read the T1R1" in said, said)
check("a start with no timer and no continue says only that the day started",
      D.resumed_say({"at": T}, work) == D.RESUMED_SAY)

check("before the time is up the day goes on", D.timer_up(T + 7199) is None and not D.paused())
ended = D.timer_up(T + 7200)
check("when it is up the day is paused, by the timer", ended and D.paused() and D.paused().get("by") == "timer", D.paused())
check("and it says how long she had set", "(2h) is up" in D.TIMER_UP_SAY % ended["for"])
check("it pauses once: after she starts again with no timer, it does not fire again",
      not D.set_paused(False, "slack", T + 9000) and D.timer_up(T + 99999) is None and not D.paused())

src = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("her !start in the channel sets the timer and the continue", "minutes=None if stopping else day_timer(r[\"text\"])" in src
      and "carry_on=not stopping and bool(words & set(CONTINUE_WORDS))" in src)
check("the timer is checked every pass, before the pause is read", src.index("ended = timer_up(now)") < src.index("    is_paused = paused()\n    started ="))
check("his first message after a continue takes his last task's next step, not a new direction",
      "Gloria asked you to continue from your last task" in src and "carry_on = kickoff and bool(state.pop(\"continue_from\", None))" in src)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the app's day switch takes the same timer and continue", '_start.update(until=_start["at"] + 60 * _min' in srv
      and '_start["continue"] = True' in srv)
check("the app's status says the timer while it runs", '"until": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(float(st["until"])))' in srv
      and '**({"timer": timer} if timer else {})' in srv)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
