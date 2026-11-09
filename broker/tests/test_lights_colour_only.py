"""Gloria, 8 November: "Make sure he doesn't change the strength of the lights, only the color."
Every light change goes through vintos-home._light_on; it must never send brightness, on either backend."""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "..", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location("vintos_home", os.path.join(SCRIPTS, "vintos-home.py"))
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)

FAIL = []
def check(name, cond, got=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  got: %r" % (got,)))
    if not cond: FAIL.append(name)

sent = []
h.govee_control = lambda dev, kind, inst, val: sent.append((dev, kind, inst, val)) or True
h.ha_request = lambda path, payload: sent.append((path, dict(payload))) or (200, {})

h._light_on("govee:AA", rgb=[10, 20, 30], brightness=254)
check("a Govee bulb gets its colour", any(x[2] == "colorRgb" for x in sent if len(x) == 4), sent)
check("a Govee bulb is never sent a brightness", not any(len(x) == 4 and x[2] == "brightness" for x in sent), sent)

sent.clear()
h._light_on("light.lamp", rgb=[10, 20, 30], brightness=10)
check("a Home Assistant light gets its colour", sent and sent[0][1].get("rgb_color") == [10, 20, 30], sent)
check("a Home Assistant light is never sent a brightness", sent and "brightness" not in sent[0][1], sent)

sent.clear()
h.room_lights = lambda room=None: ["govee:AA", "light.lamp"]
h._ensure_plugs = lambda lights: None
h.time.sleep = lambda s: None
h.flicker("bedroom"); h.set_room_color("#ff8800", brightness=30, room="bedroom")
check("flicker and room colour send no brightness at all",
      not any((len(x) == 4 and x[2] == "brightness") or (len(x) == 2 and "brightness" in x[1]) for x in sent), sent)

print("%d failed" % len(FAIL)); sys.exit(1 if FAIL else 0)
