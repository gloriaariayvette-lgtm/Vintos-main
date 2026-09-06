#!/usr/bin/env python3
"""His hands on the desktop, without a screen or a model: the loop takes one action per fresh screenshot, stops
on done/fail/stop/repetition, scales screenshot pixels to desktop pixels, refuses bad actions and coordinates,
keeps typed text out of the audit log, picks the Windows backend only on WSL, and turns key names into SendKeys.
Scratch state dir only; nothing of his is touched."""
import os, sys, json, tempfile, importlib
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(); os.environ["VINTOS_DESKTOP_STATE_DIR"] = TMP
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import desktop_agent as DA; import desktop_windows as DW
assert str(DA.STATE_DIR) == TMP
R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))


class FakeBackend:
    def __init__(self): self.done = []; self.n = 0
    def capture(self): self.n += 1; return (b"jpeg-%d" % self.n, (800, 450), (1600, 900))
    def describe(self): return {"desktop_size": [1600, 900], "mouse": [0, 0], "active_window": "x", "display": "fake"}
    def execute(self, action, image_size):
        self.done.append(action)
        if action["action"] == "press" and action.get("key") == "boom": raise RuntimeError("no such key")
        return action["action"]


def planner_from(script):
    it = iter(script); seen = []
    def plan(task, shot, image_size, desktop, step, last_result, recent):
        seen.append({"step": step, "shot": shot, "last": last_result})
        return next(it)
    plan.seen = seen
    return plan


# --- parse
a = DA.parse_action('```json\n{"action":"click","x":10,"y":20,"reason":"r"}\n```')
check("parse: fenced JSON", a["action"] == "click" and a["x"] == 10)
a = DA.parse_action('Sure. {"action":"done","summary":"it is open"} thanks')
check("parse: JSON inside prose", a["action"] == "done")
for bad in ('{"action":"shell","cmd":"rm"}', "no json here", '["click"]'):
    try: DA.parse_action(bad); check(f"parse refuses {bad[:20]!r}", False)
    except ValueError: check(f"parse refuses {bad[:20]!r}", True)

# --- loop
b = FakeBackend()
r = DA.run_loop("open x", b, planner_from([{"action": "click", "x": 1, "y": 1}, {"action": "type", "text": "hi"}, {"action": "done", "summary": "open"}]),
                max_steps=10, interval=0, should_stop=lambda: False)
check("loop: one action per fresh screenshot, done ends it", r.status == "completed" and r.steps == 3 and b.n >= 3 and len(b.done) == 2 and r.gemma_calls == 3, r)
b = FakeBackend()
r = DA.run_loop("t", b, planner_from([{"action": "fail", "reason": "no such app"}]), max_steps=10, interval=0, should_stop=lambda: False)
check("loop: fail ends with Gemma's reason", r.status == "failed" and r.reason == "no such app" and not b.done)
b = FakeBackend()
same = {"action": "click", "x": 5, "y": 5, "reason": "again"}
r = DA.run_loop("t", b, planner_from([dict(same, reason=str(i)) for i in range(8)]), max_steps=10, interval=0, should_stop=lambda: False)
check("loop: the same action four times ends as failed (reason ignored in the comparison)", r.status == "failed" and "repeated" in r.reason and len(b.done) == 3, (r, len(b.done)))
b = FakeBackend()
r = DA.run_loop("t", b, planner_from([{"action": "click", "x": 1, "y": 1}] * 5), max_steps=3, interval=0, should_stop=lambda: False)
check("loop: step cap", r.status == "failed" and "maximum 3" in r.reason and len(b.done) == 3)
calls = {"n": 0}
def stop_after_two(): calls["n"] += 1; return calls["n"] > 6
b = FakeBackend()
r = DA.run_loop("t", b, planner_from([{"action": "click", "x": 1, "y": 1}] * 9), max_steps=9, interval=0, should_stop=stop_after_two)
check("loop: stop is honoured between every phase", r.status == "stopped" and len(b.done) <= 2, (r, len(b.done)))
b = FakeBackend()
r = DA.run_loop("t", b, planner_from([{"action": "click", "x": 1, "y": 1}, {"action": "done", "summary": "s"}]), max_steps=5, interval=0, dry_run=True, should_stop=lambda: False)
check("loop: dry run decides but never acts", r.status == "dry_run" and not b.done)
b = FakeBackend()
pl = planner_from([{"action": "press", "key": "boom"}, {"action": "done", "summary": "s"}])
r = DA.run_loop("t", b, pl, max_steps=5, interval=0, should_stop=lambda: False)
check("loop: an action error is fed back to the model, not fatal", r.status == "completed" and pl.seen[1]["last"].startswith("ACTION ERROR"), pl.seen)

# --- done is verified against a fresh screenshot
b = FakeBackend()
verdicts = iter([(False, "Invalid input is showing"), (True, "19 is showing")])
seen_claims = []
def fake_verifier(task, claim, shot, size):
    if claim == "the task as stated is complete": return (False, "periodic check: not yet")   # the loop's own check, not a done claim
    seen_claims.append((claim, shot)); return next(verdicts)
pl = planner_from([{"action": "type", "text": "12+7"}, {"action": "done", "summary": "19 is shown"}, {"action": "press", "key": "enter"}, {"action": "done", "summary": "19 is shown"}])
r = DA.run_loop("calc", b, pl, max_steps=8, interval=0, should_stop=lambda: False, verifier=fake_verifier)
check("verify: a false done is rejected and fed back, a true one completes", r.status == "completed" and len(seen_claims) == 2
      and pl.seen[2]["last"].startswith("DONE REJECTED") and "Invalid input" in pl.seen[2]["last"] and len(b.done) == 2, (r, pl.seen, len(b.done)))
check("verify: the check looked at a fresh screenshot, not the one Gemma decided on", seen_claims[0][1] != pl.seen[1]["shot"])
vrows = [json.loads(l) for l in open(DA.LOG_FILE) if "verify" in l]
check("verify: both checks are in the audit", len(vrows) == 2 and vrows[0]["verify"]["confirmed"] is False and vrows[1]["verify"]["confirmed"] is True)

# --- audit never holds typed text
rows = [json.loads(l) for l in open(DA.LOG_FILE)]
typed = [x for x in rows if x.get("action", {}).get("action") == "type"]
check("audit: typed text replaced by length and hash", typed and "text" not in typed[0]["action"] and typed[0]["action"]["typed"]["chars"] == 2, typed[:1])
check("audit: screenshots stored as hashes only", all(len(x.get("screen", "0" * 16)) == 16 and "jpeg" not in json.dumps(x) for x in rows))

# --- scaling and guards (Windows backend maths, no PowerShell)
wb = DW.WindowsBackend.__new__(DW.WindowsBackend); wb._size = (2560, 1440); wb.max_image_width = 1600
x, y = wb._scaled({"x": 800, "y": 450}, (1600, 900), "x", "y")
check("scale: screenshot pixels -> desktop pixels", (x, y) == (1280, 720), (x, y))
try: wb._scaled({"x": 1700, "y": 10}, (1600, 900), "x", "y"); check("scale: outside the screenshot refused", False)
except ValueError: check("scale: outside the screenshot refused", True)

# --- SendKeys mapping
check("keys: ctrl+l", DW.sendkeys_sequence(["ctrl", "l"]) == "^l")
check("keys: alt+f4", DW.sendkeys_sequence(["alt", "f4"]) == "%{F4}")
check("keys: enter", DW.sendkeys_sequence(["enter"]) == "{ENTER}")
check("keys: ctrl+shift+t groups", DW.sendkeys_sequence(["ctrl", "shift", "t"]) == "^+t")
check("keys: special char escaped", DW.sendkeys_sequence(["+"]) == "{+}")
for bad in (["win", "r"], ["ctrl"], ["nope"], ["a;b"]):
    try: DW.sendkeys_sequence(bad); check(f"keys refuse {bad}", False)
    except ValueError: check(f"keys refuse {bad}", True)

# --- launch
a = DA.parse_action('{"action":"launch","app":"notepad"}')
check("parse: launch accepted", a["action"] == "launch")
wp = __import__("desktop_winpy").WindowsPythonBackend.__new__(__import__("desktop_winpy").WindowsPythonBackend); wp._size = (10, 10); wp.max_image_width = 1600
try: wp.execute({"action": "launch", "app": "cmd"}, (10, 10)); check("launch: app outside the list refused", False)
except ValueError: check("launch: app outside the list refused", True)
check("launch: names resolve to executables", DA.LAUNCHABLE["notepad"] == "notepad" and DA.LAUNCHABLE["browser"] == "msedge")
check("launch: every launchable app has a window title to wait for", all(DA.WINDOW_TITLES.get(v) for v in DA.LAUNCHABLE.values()), DA.LAUNCHABLE)
a = DA.parse_action('{"action":"focus","title":"Calculator"}'); check("parse: focus accepted", a["action"] == "focus")
try: wp.execute({"action": "focus", "title": "  "}, (10, 10)); check("focus: empty title refused", False)
except ValueError: check("focus: empty title refused", True)

# --- long tasks: open_url, positional scroll, scroll tolerance, settle
a = DA.parse_action('{"action":"open_url","url":"https://www.youtube.com/results?search_query=cats"}')
check("parse: open_url accepted", a["action"] == "open_url")
for bad in ("javascript:alert(1)", "file:///etc/passwd", "youtube.com"):
    try: wp.execute({"action": "open_url", "url": bad}, (10, 10)); check(f"open_url refuses {bad}", False)
    except ValueError: check(f"open_url refuses {bad}", True)
b = FakeBackend()
r = DA.run_loop("scroll a feed", b, planner_from([{"action": "scroll", "amount": -5, "reason": str(i)} for i in range(6)] + [{"action": "done", "summary": "seen"}]),
                max_steps=12, interval=0, should_stop=lambda: False)
check("loop: six identical scrolls are work, not a stall", r.status == "completed" and len(b.done) == 6, (r, len(b.done)))
b = FakeBackend()
r = DA.run_loop("scroll forever", b, planner_from([{"action": "scroll", "amount": -5} for i in range(12)]), max_steps=12, interval=0, should_stop=lambda: False)
check("loop: eight identical scrolls end the job", r.status == "failed" and "repeated 8" in r.reason, r)
class Settling(FakeBackend):
    def __init__(self): super().__init__(); self.seq = iter([b"a", b"b", b"c", b"c", b"c"])
    def capture(self): self.n += 1; return (next(self.seq, b"c"), (800, 450), (1600, 900))
sb = Settling(); t0 = __import__("time").time(); DA._settle(sb, lambda: False, max_wait=3.0, quiet=0.05)
check("settle: waits until two captures match, then returns", sb.n >= 3 and __import__("time").time() - t0 < 2.5, sb.n)
check("defaults: a long task budget", DA.DEFAULT_MAX_STEPS >= 60 and DA.HARD_MAX_STEPS >= DA.DEFAULT_MAX_STEPS)

# --- what the cat video taught: two JSONs, cycles, revisits, planner errors, periodic completion check
a = DA.parse_action('{"observed":"results page","action":"click","x":1,"y":2,"reason":"r"}\n{"action":"done","summary":"x"}')
check("parse: two objects -> the first one, not a crash", a["action"] == "click")
b = FakeBackend()
r = DA.run_loop("t", b, planner_from([{"action": "click", "x": 1, "y": 1}, {"action": "click", "x": 9, "y": 9}] * 4 + [{"action": "done", "summary": "s"}]),
                max_steps=20, interval=0, should_stop=lambda: False)
check("loop: an A-B-A-B cycle ends the job before the sixth action runs", r.status == "failed" and "cycling" in r.reason and len(b.done) == 5, (r, len(b.done)))
class TwoScreens(FakeBackend):
    def capture(self): self.n += 1; return (b"S%d" % (self.n % 2), (800, 450), (1600, 900))
tb = TwoScreens()
pl = planner_from([{"action": "click", "x": 1, "y": 1}, {"action": "click", "x": 2, "y": 2}, {"action": "done", "summary": "s"}])
DA.run_loop("t", tb, pl, max_steps=5, interval=0, should_stop=lambda: False)
check("loop: returning to a screen seen before is announced to the model", any("one you were on before" in x["last"] for x in pl.seen), [x["last"] for x in pl.seen])
def flaky(task, shot, image_size, desktop, step, last_result, recent):
    flaky.n = getattr(flaky, "n", 0) + 1
    if flaky.n == 1: raise ValueError("Extra data")
    return {"action": "done", "summary": "s"} if flaky.n >= 2 else None
b = FakeBackend()
r = DA.run_loop("t", b, flaky, max_steps=5, interval=0, should_stop=lambda: False)
check("loop: a planner error is fed back once, then the run continues", r.status == "completed" and r.steps == 2, r)
def always_bad(*a, **k): raise ValueError("garbage")
r = DA.run_loop("t", FakeBackend(), always_bad, max_steps=8, interval=0, should_stop=lambda: False)
check("loop: three unusable answers running end the job with the reason", r.status == "failed" and "three times" in r.reason and r.steps == 3, r)
b = FakeBackend()
checks = []
def completion_verifier(task, claim, shot, size): checks.append(claim); return (True, "the player is playing the cat video") if len(checks) >= 1 else (False, "no")
pl = planner_from([{"action": "scroll", "amount": -3, "reason": str(i)} for i in range(10)])
r = DA.run_loop("play the cat video", b, pl, max_steps=10, interval=0, should_stop=lambda: False, verifier=completion_verifier)
check("loop: the periodic completion check finishes a task the model never called done", r.status == "completed" and "completion check" in r.reason and r.steps == 3 and checks[0] == "the task as stated is complete", (r, checks))

# --- backend choice
check("backend: Windows only on WSL with powershell.exe", DW.available() is False or (os.path.exists("/proc/version") and "microsoft" in open("/proc/version").read().lower()))

# --- tag extraction
class FakeStart:
    calls = []
DA.start_task = lambda task, max_steps=40: (FakeStart.calls.append(task) or {"accepted": True, "job_id": "j1", "state": {}})
out = DA.extract_and_start("On it. [DESKTOP: open notepad] and also [DESKTOP: type hello]", "avatar")
check("tag: last tag wins, tags removed from the text", FakeStart.calls == ["type hello"] and "[DESKTOP" not in out and out.startswith("On it."), (FakeStart.calls, out))
check("tag: no tag, text untouched", DA.extract_and_start("plain words", "chat") == "plain words")
DA.start_task = lambda task, max_steps=40: {"accepted": False, "reason": "a desktop task is already active", "state": {}}
out = DA.extract_and_start("[DESKTOP: again]", "voice")
check("tag: refusal is visible in the text", "did not start" in out and "already active" in out, out)

import shutil; shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
