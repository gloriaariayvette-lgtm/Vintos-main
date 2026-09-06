#!/usr/bin/env python3
"""The browser agent without Edge or a model: Gemma chooses items by number from the page's own list; a video
task finishes on the <video> element's state, not on an opinion; a false done is rejected; stalls and cycles
end the job; web-looking tasks route to the browser, others to pixels. Scratch state only."""
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(); os.environ["VINTOS_DESKTOP_STATE_DIR"] = TMP
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import desktop_agent as DA; import browser_agent as BA
R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))


class FakeBrowser:
    """A tiny YouTube: a results page with three videos, a watch page whose video starts paused until play()."""
    def __init__(self):
        self.url = "about:blank"; self.title = ""; self.media = None; self.log = []; self.scrolled = 0
    def ensure(self): return {"ok": True}
    def activate(self): return {"ok": True}
    def _st(self): return {"url": self.url, "title": self.title, "media": self.media, "scrollY": self.scrolled, "height": 4000, "inner": 900}
    def goto(self, url):
        self.log.append(("goto", url)); self.url = url
        if "results" in url: self.title = "cat knocks glass - YouTube"; self.media = None
        return self._st()
    def elements(self):
        if "results" in self.url:
            els = [{"kind": "field", "text": "Search", "ontop": True}, {"kind": "video", "text": "Dog eats sofa", "ontop": True},
                   {"kind": "video", "text": "Thug Cat knocks glass off table", "ontop": True}, {"kind": "video", "text": "Cat compilation 2019", "ontop": False}]
        elif "watch" in self.url:
            els = [{"kind": "button", "text": "Play", "ontop": True}, {"kind": "link", "text": "Subscribe", "ontop": True}]
        else:
            els = [{"kind": "field", "text": "Search", "ontop": True}]
        return {"state": self._st(), "elements": els}
    def text(self): return {"state": self._st(), "text": f"{self.title}\nsome page text"}
    def click(self, n):
        self.log.append(("click", n))
        if "results" in self.url and n == 2:
            self.url = "https://www.youtube.com/watch?v=abc"; self.title = "Thug Cat knocks glass off table - YouTube"
            self.media = {"present": True, "paused": True, "ended": False, "currentTime": 0, "duration": 31}
        return {"ok": True, "state": self._st()}
    def type(self, n, text, enter=False): self.log.append(("type", n, text)); return {"ok": True, "state": self._st()}
    def scroll(self, px): self.scrolled += px; return {"ok": True, "state": self._st()}
    def key(self, k): return {"ok": True, "state": self._st()}
    def play(self):
        if self.media: self.media.update(paused=False, currentTime=2)
        return {"ok": True, "result": "played", "state": self._st()}
    def shot(self): return b"jpeg"


def planner_from(script):
    it = iter(script); seen = []
    def plan(task, summary, step, last_result, recent):
        seen.append({"step": step, "summary": summary, "last": last_result}); return next(it)
    plan.seen = seen; return plan

TASK = "search YouTube for cat knocks glass off table and play the first real one"
check("routing: a web task goes to the browser, a desktop task does not", BA.looks_like_web(TASK) and BA.looks_like_web("open the recipe website") and not BA.looks_like_web("open Calculator and add 12 and 7"))

fb = FakeBrowser()
pl = planner_from([{"action": "goto", "url": "https://www.youtube.com/results?search_query=cat+knocks+glass"},
                   {"action": "click", "n": 2}, {"action": "play"}, {"action": "done", "summary": "playing"}])
r = BA.run(TASK, fb, pl, max_steps=10, should_stop=lambda: False)
check("video task: goto, click the numbered item, play, finished on the video element's state - no done needed",
      r.status == "completed" and "video playing" in r.reason and ("click", 2) in fb.log and r.steps == 4, (r, fb.log))
check("the model saw the numbered list with labels and the video state", "[2] video: Thug Cat knocks glass off table" in pl.seen[1]["summary"] and "VIDEO ELEMENT: present but paused" in pl.seen[2]["summary"], pl.seen[2]["summary"][:300])

fb = FakeBrowser()
pl = planner_from([{"action": "goto", "url": "https://www.youtube.com/results?search_query=x"}, {"action": "done", "summary": "it is playing"}, {"action": "click", "n": 2}, {"action": "play"}])
r = BA.run(TASK, fb, pl, max_steps=10, should_stop=lambda: False)
check("video task: a false done is rejected by the fact, and the run continues to real completion", r.status == "completed" and any("DONE REJECTED" in x["last"] for x in pl.seen), [x["last"] for x in pl.seen])

fb = FakeBrowser()
pl = planner_from([{"action": "goto", "url": "javascript:alert(1)"}, {"action": "click", "n": 99}, {"action": "fail", "reason": "lost"}])
r = BA.run(TASK, fb, pl, max_steps=10, should_stop=lambda: False)
check("bad url and bad item number are errors fed back, not crashes; fail ends with the reason", r.status == "failed" and r.reason == "lost"
      and "ACTION ERROR" in pl.seen[1]["last"] and ("?" in pl.seen[2]["last"] or "ERROR" in pl.seen[2]["last"]), [x["last"] for x in pl.seen])

fb = FakeBrowser()
pl = planner_from([{"action": "click", "n": 0}] * 6)
r = BA.run("open the recipe website and leave a review", fb, pl, max_steps=10, should_stop=lambda: False)
check("a click repeated three times is a stall", r.status == "failed" and "repeated 3" in r.reason, r)

fb = FakeBrowser(); checks = []
def ver(task, claim, st, text): checks.append(claim); return (claim == "the task as stated is complete", "page shows the review posted")
pl = planner_from([{"action": "scroll", "px": 500, "reason": str(i)} for i in range(12)])
r = BA.run("open the recipe website and leave a review", fb, pl, max_steps=12, should_stop=lambda: False, verifier=ver)
check("non-video task: the periodic page check completes it", r.status == "completed" and "completion check" in r.reason, (r, checks))

a = BA.parse_action('{"observed":"results","action":"click","n":2,"reason":"r"}\n{"action":"play"}')
check("parse: first object wins", a["action"] == "click" and a["n"] == 2)
import shutil; shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
