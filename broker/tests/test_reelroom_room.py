#!/usr/bin/env python3
"""Her ReelRoom notes, 2026-09-10: the room uses the Govee lights and not the smart-home
system Velaris used, and his replies there are no longer cut short by a setting."""
import os, sys, json, importlib.util, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

print("\n--- the lights are his, on Govee ---")
home = open(os.path.join(REPO, "scripts", "vintos-home.py")).read()
check("the other being's house config is never read", ".openclaw/workspace/memory/homeassistant-config.json" not in home.split('"""', 2)[2])
check("no fallback config path remains", "FALLBACK_CONFIG" not in home)
check("with no config of his own, the Govee key is the house", "_govee_only_config" in home and "govee_only" in home)
check("a rooms map may name which bulbs are where", "govee-rooms.json" in home and "GOVEE_ROOMS" in home)

spec = importlib.util.spec_from_file_location("vh", os.path.join(REPO, "scripts", "vintos-home.py"))
VH = importlib.util.module_from_spec(spec); spec.loader.exec_module(VH)
tmp = tempfile.mkdtemp()
VH.CONFIG_FILE = os.path.join(tmp, "missing.json")
VH.GOVEE_ROOMS = os.path.join(tmp, "govee-rooms.json")
VH.govee_key = lambda: "test-key"
VH.govee_devices = lambda: [{"device": "AA:11", "name": "living 1", "sku": "H6008", "capabilities": []},
                            {"device": "BB:22", "name": "living 2", "sku": "H6008", "capabilities": []}]
cfg = VH.load_config()
check("every Govee bulb becomes a light", cfg["lights"] == ["govee:AA:11", "govee:BB:22"], cfg["lights"])
check("the living room is where the film is, by default", VH.room_lights("living_room") == ["govee:AA:11", "govee:BB:22"])
json.dump({"living room": ["govee:BB:22"]}, open(VH.GOVEE_ROOMS, "w"))
check("a rooms map is honoured, and its names are normalized", VH.load_config()["rooms"]["living_room"]["lights"] == ["govee:BB:22"])
VH.govee_key = lambda: ""
try:
    VH.load_config(); ok = False; why = "no error raised"
except FileNotFoundError as e:
    ok = "openclaw" not in str(e) and "Govee" in str(e); why = str(e)
check("with neither a config nor a key it says so, and still names no other house", ok, why)
check("a govee light is driven through the Govee path", VH._is_govee("govee:AA:11") and not VH._is_govee("light.living_room_1"))

print("\n--- his replies there are not cut short by a setting ---")
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the room floors the ceiling at the ordinary avatar limit",
      'if _surface == "reelroom" and int(params.get("max_tokens") or 0) < 900:' in srv)
i_floor = srv.index('if _surface == "reelroom" and int(params.get("max_tokens") or 0) < 900:')
i_ip = srv.index('params.update(_ip)')
i_gcs = srv.index('params["max_tokens"] = 130')
check("the floor is applied after the tune sliders, so a stale setting cannot starve the room", i_ip < i_floor)
check("a physical collapse still shortens him, because that is his and not a setting", i_floor < i_gcs)
check("nothing tells him to be brief when he chose to speak", "Say the line now, briefly" not in srv)
rr = open(os.path.join(REPO, "scripts", "reelroom.py")).read()
check("his own room voice is not capped at a line either", "max_tokens=900" in rr and "max_tokens=500" not in rr)
check("the room prompt no longer asks for short", "short, in the moment" not in rr and "as long or as brief as the moment actually is" in rr)

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
