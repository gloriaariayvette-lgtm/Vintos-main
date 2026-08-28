#!/usr/bin/env python3
"""The house map must be honest geometry and must fail open.

Gloria drew her house once so she never has to again; this suite makes the
data keep meaning what the drawing meant: every door is two-way, interior
routes never pass through 'outside', an empty scene grounds to nothing, and
a missing map (Velaris) changes no behavior at all.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import house_map

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:80]) if d else ""))

m = house_map.load()
rs = house_map.rooms(m)
check("the map loads from the checkout", len(rs) >= 10, sorted(rs))
check("entry is a room that exists", m.get("entry") in rs, m.get("entry"))

# every adjacency points at a real room or outside — a typo'd door goes nowhere
names = set(rs) | {"outside"}
bad = [(rid, a) for rid, r in rs.items() for a in (r.get("adjacent") or []) if a.lower() not in names]
check("every door leads somewhere real", not bad, bad)

# routing
check("arrival is front door -> stairs -> hall",
      house_map.arrival_route(m) == ["outside", "stairs", "hall"], house_map.arrival_route(m))
p = house_map.route("outside", "bedroom", m)
check("outside reaches the bedroom", p and p[-1] == "bedroom", p)
p = house_map.route("balcony", "laundry", m)
check("interior routes stay indoors — never through outside",
      p and "outside" not in p[1:-1], p)
check("an unknown room routes nowhere, quietly", house_map.route("attic", "hall", m) == [])

# grounding
g = house_map.ground_block()
check("ground truth names the real furniture", "sofa" in g and "bed" in g and "desk" in g)
check("a matched scene yields that room's anchors", house_map.anchors_for("in the bedroom") == ["bed"])
check("an empty scene grounds to nothing", house_map.anchors_for("") == [] and house_map.anchors_for("  ") == [])

# fail-open: no map means empty everything (Velaris and any broken install)
check("no map -> no rooms, no route", house_map.rooms({}) == {} and house_map.route("a", "b", {}) == [])

# the world model consumes it fail-open too
wm = open(os.path.join(ROOT, "scripts", "world_model.py"), errors="replace").read()
check("world_model grounds its extractor through the map", "_house_ground" in wm and "house_map" in wm)
check("world_model survives the map's absence", "except Exception" in wm.split("def _house_ground", 1)[1].split("def ")[0])

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
