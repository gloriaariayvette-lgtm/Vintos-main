#!/usr/bin/env python3
"""Gloria, 2026-09-10: twenty-one Opus calls on a night she spoke about six times, and the
speaking model should see a fresh frame of the TV when she messages.

Her turn: the frame she just grabbed travels with it, named as the television. His own
mid-film line: his room voice on Sonnet, not the whole avatar stack on the selected model."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

srv = open(os.path.join(REPO, "bin", "server.py")).read()
i = srv.index('@app.post("/api/game/reelroom/chat")')
j = srv.index('@app.post("/api/game/reelroom/plan")')
route = srv[i:j]

print("\n--- her turn carries a fresh frame ---")
check("the frame is passed to the turn instead of being dropped", "image=image," in route and "image=None," not in route)
check("it is named as the television, not a photo she sent",
      "image_description=" in route and "It is the television, not a photograph" in route)
check("nothing is claimed when there is no frame", 'if image else None' in route)

print("\n--- what costs the speaking model ---")
check("her turn still goes through the full avatar turn", "_out = await avatar_chat(_internal, request)" in route)
check("his own mid-film line no longer does", route.count("await avatar_chat(") == 1, route.count("await avatar_chat("))
check("it goes to his room voice instead", "rr.chat(" in route and "run_in_executor" in route)
rr = open(os.path.join(REPO, "scripts", "reelroom.py")).read()
check("his room voice is Sonnet, not the selected speaking model", "RC._sonnet" in rr)
core = open(os.path.join(REPO, "scripts", "robot_core.py")).read()
check("and that really is Sonnet 5", '"""Sonnet 5 through his key' in core)
check("the frame reads and the say-anything checks stay on Gemma", "RC._gemma" in rr and "mode == \"look\"" in route)

print("\n--- the night still records what he said ---")
check("an unprompted line goes into the night's journal", 'rr.journal("", str(_line or "")' in route and '"unprompted": True' in route)
check("a journal failure never eats the turn", "[reelroom] journal(decide):" in route)

page = os.path.join(os.path.dirname(REPO), "plithra-app", "src", "reel.html")
if os.path.exists(page):
    pg = open(page).read()
    check("the room grabs a frame before sending her message", "async function grabFrame(" in pg and "const frame=await grabFrame();" in pg)
    check("it is passed as the image on that turn", "velarisChat(text,'',S.chatHistory.slice(0,-1),frame||undefined" in pg)
    check("a failed grab sends the message anyway", "return null" in pg and "frame||undefined" in pg)
else:
    print("(the room page is not checked out here; its half is unverified)")

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
