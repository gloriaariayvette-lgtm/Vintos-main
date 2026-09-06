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
        self.url = "about:blank"; self.title = ""; self.media = None; self.log = []; self.scrolled = 0; self.history = []
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
        if getattr(self, "popup", False):
            els = els + [{"kind": "button", "text": "No Thanks", "ontop": True, "popup": True}, {"kind": "popup", "text": "Would You Like to Send This Recipe to Yourself?", "marker": True, "popup": True}]
        return {"state": self._st(), "elements": els}
    def text(self): return {"state": self._st(), "text": f"{self.title}\nsome page text", "outline": [{"text": "Ingredients", "y": 900, "onscreen": self.scrolled < 500}, {"text": "Reviews", "y": 14000, "onscreen": self.scrolled >= 13000}]}
    def scrollto(self, text):
        for o in self.text()["outline"]:
            if text.lower() in o["text"].lower(): self.scrolled = o["y"] - 80; return {"ok": True, "found": o["text"], "state": self._st()}
        return {"ok": False, "found": None, "state": self._st()}
    def click(self, n):
        self.log.append(("click", n)); self.history.append((self.url, self.title, self.media))
        if "results" in self.url and n == 2:
            self.url = "https://www.youtube.com/watch?v=abc"; self.title = "Thug Cat knocks glass off table - YouTube"
            self.media = {"present": True, "paused": True, "ended": False, "currentTime": 0, "duration": 31}
        elif "results" in self.url and n == 1:
            self.url = "https://www.youtube.com/@dogchannel"; self.title = "Dog Channel - YouTube"; self.media = None
        else:
            self.history.pop(); return {"ok": True, "changed": False, "state": self._st()}
        return {"ok": True, "changed": True, "state": self._st()}
    def dismiss(self):
        self.popup = False; return {"ok": True, "how": "clicked 'No Thanks'", "state": self._st()}
    def back(self):
        if self.history: self.url, self.title, self.media = self.history.pop()
        return {"ok": True, "state": self._st()}
    def type(self, n, text, enter=False): self.log.append(("type", n, text)); return {"ok": True, "state": self._st()}
    def scroll(self, px): self.scrolled += px; return {"ok": True, "state": self._st()}
    def key(self, k): return {"ok": True, "state": self._st()}
    def play(self):
        if self.media: self.media.update(paused=False, currentTime=2, advancing=True)
        return {"ok": True, "result": "played", "state": self._st()}
    def shot(self): return b"jpeg"


def planner_from(script):
    it = iter(script); seen = []
    def plan(task, summary, step, last_result, recent, notes=""):
        seen.append({"step": step, "summary": summary, "last": last_result, "notes": notes}); return next(it)
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
pl = planner_from([{"action": "goto", "url": "javascript:alert(1)"}, {"action": "click", "n": 99}, {"action": "fail", "reason": "lost", "evidence": "some page text"}])
r = BA.run(TASK, fb, pl, max_steps=10, should_stop=lambda: False)
check("bad url and bad item number are errors fed back, not crashes; fail ends with the reason", r.status == "failed" and r.reason.startswith("lost")
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

fb = FakeBrowser()
pl = planner_from([{"action": "goto", "url": "https://www.youtube.com/results?search_query=x"},
                   {"action": "click", "n": 1, "notes": "item 1 was a channel, not a video"}, {"action": "back"}, {"action": "click", "n": 2}, {"action": "play"}])
r = BA.run(TASK, fb, pl, max_steps=10, should_stop=lambda: False)
check("wrong turn: a channel page is named as such, back returns to the results, the run completes",
      r.status == "completed" and "CHANNEL page" in pl.seen[2]["summary"] and "went back" in pl.seen[3]["last"] and "SEARCH RESULTS" in pl.seen[3]["summary"], (r, [x["last"] for x in pl.seen]))
check("the model's notes are carried to the next steps", "item 1 was a channel, not a video" in pl.seen[2]["notes"] and "item 1 was a channel" in pl.seen[4]["notes"], [x["notes"] for x in pl.seen])

fb = FakeBrowser()
pl = planner_from([{"action": "goto", "url": "https://www.youtube.com/results?search_query=x"}, {"action": "click", "n": 0}, {"action": "click", "n": 2}, {"action": "play"}])
r = BA.run(TASK, fb, pl, max_steps=10, should_stop=lambda: False)
check("an action that changed nothing is reported as NO CHANGE, and a different choice is not punished", r.status == "completed" and pl.seen[2]["last"].startswith("NO CHANGE"), (r, [x["last"] for x in pl.seen]))

st = {"title": "t", "media": {"present": True, "paused": False, "ended": False, "currentTime": 0, "duration": 45, "advancing": False}}
check("play pressed but the clock not moving is not playing", not BA.video_done(st, TASK)[0] and "clock" in BA.video_done(st, TASK)[1])
st["media"].update(currentTime=3, advancing=True)
check("a moving clock is playing", BA.video_done(st, TASK)[0])
check("page types from addresses", "CHANNEL" in BA.page_type("https://www.youtube.com/@x") and "WATCH" in BA.page_type("https://www.youtube.com/watch?v=1") and "SHORTS" in BA.page_type("https://www.youtube.com/shorts/1") and "SEARCH RESULTS" in BA.page_type("https://www.youtube.com/results?search_query=a"))

fb = FakeBrowser(); fb.popup = True
pl = planner_from([{"action": "dismiss"}, {"action": "goto", "url": "https://www.youtube.com/results?search_query=x"}, {"action": "click", "n": 2}, {"action": "play"}])
r = BA.run(TASK, fb, pl, max_steps=10, should_stop=lambda: False)
check("a pop-up is named as covering the page, its items are marked, dismiss clears it and numbering is unchanged",
      r.status == "completed" and "POP-UP COVERING THE PAGE" in pl.seen[0]["summary"] and "[pop-up]" in pl.seen[0]["summary"] and "No Thanks" in pl.seen[1]["last"] and "POP-UP" not in pl.seen[1]["summary"], (r, pl.seen[0]["summary"][:400]))

fb = FakeBrowser(); seen_ver = []
def ver2(task, claim, st, text, outline=None): seen_ver.append(outline); return (any(o["text"] == "Reviews" and o["onscreen"] for o in (outline or [])), "reviews heading on screen")
pl = planner_from([{"action": "goto", "url": "https://www.allrecipes.com/recipe/1/mug-cake"}, {"action": "scrollto", "text": "reviews"}, {"action": "done", "summary": "reviews on screen"}])
r = BA.run("open the recipe and scroll to the reviews section", fb, pl, max_steps=10, should_stop=lambda: False, verifier=ver2)
check("sections map: scrollto reaches a heading and the checker sees it ON SCREEN, completing without a done", r.status == "completed" and "completion check" in r.reason
      and fb.scrolled == 13920 and seen_ver and seen_ver[-1][1]["onscreen"] and "14000px            Reviews" in pl.seen[1]["summary"], (r, fb.scrolled, pl.seen[-1]["summary"][-400:]))

class ReviewSite(FakeBrowser):
    """A recipe page whose Submit stays disabled until a star is chosen; typing works only through the driver."""
    def __init__(self):
        super().__init__(); self.url = "https://www.allrecipes.com/recipe/1/mug-cake"; self.title = "Mug Cake Recipe"; self.star = 0; self.review = ""; self.submitted = False
    def elements(self):
        els = [{"kind": "field", "text": "My Review", "ontop": True, "value": self.review},
               {"kind": "star", "text": "Rate 1 star", "ontop": True, "selected": self.star == 1}, {"kind": "star", "text": "Rate 5 stars", "ontop": True, "selected": self.star == 5},
               {"kind": "button", "text": "SUBMIT", "ontop": True, "disabled": not (self.star and self.review)}]
        return {"state": self._st(), "elements": els}
    def text(self): return {"state": self._st(), "text": "Reviews (2,131)\n" + ("Thanks! Your review was submitted." if self.submitted else "My Review"), "outline": []}
    def click(self, n):
        self.log.append(("click", n))
        if n in (1, 2): self.star = 1 if n == 1 else 5; return {"ok": True, "changed": True, "state": self._st()}
        if n == 3 and self.star and self.review: self.submitted = True; return {"ok": True, "changed": True, "state": self._st()}
        return {"ok": True, "changed": False, "state": self._st()}
    def type(self, n, text, enter=False):
        self.log.append(("type", n, text)); self.review = text if n == 0 else self.review; return {"ok": True, "value": self.review, "state": self._st()}

class FakeReflector:
    def __init__(self): self.plans = 0; self.reflections = 0; self.blocked = ""
    def plan(self, task): self.plans += 1; return {"plan": ["1. choose a star rating", "2. type the review", "3. click SUBMIT"], "done_when": "the page thanks you", "avoid": []}
    def reflect(self, task, history, summary, plan, notes):
        self.reflections += 1; self.last_summary = summary
        return {"diagnosis": "SUBMIT is disabled because no star has been chosen.", "plan": ["1. click the 'Rate 1 star' item", "2. click SUBMIT"], "avoid": ["clicking a disabled button"], "blocked": self.blocked}

site = ReviewSite(); rf = FakeReflector(); vchecks = []
def ver3(task, claim, st, text, outline=None): vchecks.append(text); return ("submitted" in text, "thanks line present" if "submitted" in text else "no thanks line")
# the fast model types, then hammers the disabled Submit; after the re-plan it clicks the star and submits
pl = planner_from([{"action": "type", "n": 0, "text": "Rubbery and sad."}, {"action": "click", "n": 3}, {"action": "click", "n": 3}, {"action": "click", "n": 3},
                   {"action": "click", "n": 1}, {"action": "click", "n": 3}, {"action": "done", "summary": "review submitted"}])
r = BA.run("open the recipe and leave a 1 star review saying 'Rubbery and sad.'", site, pl, max_steps=12, should_stop=lambda: False, verifier=ver3, reflector=rf)
check("a plan is drawn up before step 1 and shown to the fast model", rf.plans == 1 and "PLAN (follow in order" in pl.seen[0]["notes"] and "choose a star rating" in pl.seen[0]["notes"], pl.seen[0]["notes"])
check("the page report shows the disabled button, the chosen star, and what the field holds",
      "SUBMIT (DISABLED" in pl.seen[1]["summary"] and 'My Review = "Rubbery and sad."' in pl.seen[1]["summary"] and "Rate 1 star (selected)" in pl.seen[5]["summary"], pl.seen[1]["summary"][-400:])
check("clicking a disabled button is refused with the reason, not sent to the page", any("is DISABLED" in x["last"] for x in pl.seen) and ("click", 3) not in site.log[:2], [x["last"][:100] for x in pl.seen])
check("stuck brings the slow thinker in, whose diagnosis and new plan reach the fast model", rf.reflections >= 1 and any("RE-PLANNED" in x["last"] and "no star has been chosen" in x["last"] for x in pl.seen)
      and any("click the 'Rate 1 star' item" in x["notes"] for x in pl.seen), [x["last"][:80] for x in pl.seen])
check("and the review goes through", r.status == "completed" and site.submitted and site.star == 1, r)

site = ReviewSite(); rf = FakeReflector(); rf.blocked = "the site demands a sign-in and there is no account"
pl = planner_from([{"action": "click", "n": 3}] * 8)
r = BA.run("leave a review", site, pl, max_steps=12, should_stop=lambda: False, verifier=ver3, reflector=rf)
check("the slow thinker can declare the task blocked, and the run ends saying why", r.status == "failed" and r.reason.startswith("blocked: the site demands a sign-in"), r)

site = ReviewSite(); rf = FakeReflector()
pl = planner_from([{"action": "fail", "reason": "The site requires a sign-in", "evidence": "Log in to continue"}, {"action": "type", "n": 0, "text": "Rubbery and sad."}, {"action": "click", "n": 1}, {"action": "click", "n": 3}, {"action": "done", "summary": "submitted"}])
r = BA.run("leave a 1 star review", site, pl, max_steps=12, should_stop=lambda: False, verifier=ver3, reflector=rf)
check("a fail with no such words on the page is rejected and the run goes on to finish", r.status == "completed" and "FAIL REJECTED" in pl.seen[1]["last"], (r, pl.seen[1]["last"]))

a = BA.parse_action('{"observed":"results","action":"click","n":2,"reason":"r"}\n{"action":"play"}')
check("parse: first object wins", a["action"] == "click" and a["n"] == 2)
import shutil; shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
