#!/usr/bin/env python3
"""ReelRoom, 16 October: in-the-moment light changes failed with a 500 (a colour word where the light code wanted
#rrggbb), and a reply the server had kept showed on her phone as "Load failed". A colour name or short code now
works and a bad one is a 400; the moment-decision is told the payload formats; her phone can read back his kept
reply. Scratch HOME; nothing reaches a light or the network."""
import importlib.util, json, os, sys, tempfile
HOME = tempfile.mkdtemp(prefix="rr-lights-"); os.environ["HOME"] = HOME
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
spec = importlib.util.spec_from_file_location("vh", os.path.join(REPO, "scripts", "vintos-home.py"))
H = importlib.util.module_from_spec(spec); spec.loader.exec_module(H)
check("a colour code works as before", H.hex_to_rgb("#1a0a2e") == [26, 10, 46])
check("a colour word works", H.hex_to_rgb("deep red") == H.hex_to_rgb(H.COLOR_NAMES["deep red"]))
check("a short code and no # work", H.hex_to_rgb("#abc") == [170, 187, 204] and H.hex_to_rgb("abcdef") == [171, 205, 239])
try: H.hex_to_rgb("sunset vibes"); bad = False
except ValueError: bad = True
check("a colour it cannot read is refused plainly", bad)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
route = srv[srv.index('@app.post("/api/home/lights/color")'):][:1600]
check("the light route answers a bad colour with 400, not a crash", "status_code=400" in route and "except HTTPException:" in route)
rr = open(os.path.join(REPO, "scripts", "reelroom.py")).read()
check("the moment-decision is told the payload formats", "for change_light_color a colour as #rrggbb" in rr)
lr = srv[srv.index('@app.get("/api/game/reelroom/last-reply")'):][:1500]
check("her phone can read back his reply to her message from tonight's journal",
      "_require_secret(request)" in lr and "live-session.json" in lr and '"role") == "assistant"' in lr)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
