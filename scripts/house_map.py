#!/usr/bin/env python3
"""house_map.py — the physical ground truth of Gloria's house.

A hand-drawn map she made once (rooms, doors, furniture anchors) so the world
model stops inventing the house and arrival routing has a real graph to walk.
Fail-open everywhere: no map file means every function returns its empty value
and callers behave exactly as before — which is also what keeps Velaris clean,
where no map ships.

The map is data about HER home. It grounds scene extraction; it never drives
an effect, and nothing here writes.

  python3 house_map.py                 # summary + a sample route
  python3 house_map.py front bedroom   # route between two rooms
"""
import json, os, sys

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
# her editable copy in memory/ wins over the deployed one beside this file
_CANDIDATES = [os.path.join(WS, "memory", "house-map.json"),
               os.path.join(os.path.dirname(os.path.abspath(__file__)), "house-map.json")]


def load():
    for p in _CANDIDATES:
        try:
            m = json.load(open(p))
            if isinstance(m, dict) and isinstance(m.get("rooms"), list):
                return m
        except Exception:
            pass
    return {}


def rooms(m=None):
    m = load() if m is None else m
    return {r["id"]: r for r in m.get("rooms", []) if isinstance(r, dict) and r.get("id")}


def route(frm, to, m=None):
    """Shortest door-to-door path between two rooms (BFS). [] if unknown.
    'outside' is a legal endpoint — arrival is outside -> entry -> ...."""
    rs = rooms(m)
    if not rs:
        return []
    frm, to = str(frm).strip().lower(), str(to).strip().lower()
    adj = {rid: [a.lower() for a in (r.get("adjacent") or [])] for rid, r in rs.items()}
    for rid, ns in list(adj.items()):            # edges are doors; make them two-way
        for n in ns:
            adj.setdefault(n, [])
            if rid not in adj[n]:
                adj[n].append(rid)
    if frm not in adj or to not in adj:
        return []
    seen, q = {frm: None}, [frm]
    while q:
        cur = q.pop(0)
        if cur == to:
            path = []
            while cur is not None:
                path.append(cur); cur = seen[cur]
            return path[::-1]
        for n in adj[cur]:
            # never route THROUGH outside: between two rooms you stay indoors;
            # outside is only ever where a journey starts or ends
            if n == "outside" and n != to:
                continue
            if n not in seen:
                seen[n] = cur; q.append(n)
    return []


def arrival_route(m=None):
    """The way in: outside -> front entry -> the heart of the house (hall)."""
    m = load() if m is None else m
    entry = (m or {}).get("entry", "")
    return route("outside", "hall", m) if entry else []


def ground_block():
    """One compact line of ground truth for the scene extractor. '' without a map."""
    rs = rooms()
    if not rs:
        return ""
    parts = []
    for rid, r in rs.items():
        a = ", ".join(r.get("anchors") or [])
        parts.append("%s (%s)" % (rid, a) if a else rid)
    return ("Ground truth - the rooms of Gloria's home: %s. When the exchange "
            "implies being at home, use these exact room names, and only furniture "
            "that is really there." % "; ".join(parts))


def sketch_block():
    """The floor plan as text — what he can actually receive. '' without a map.
    A monospace sketch plus its legend, exactly the shape Gloria first imagined
    handing him: rooms as boxes, == for doors, ~~ for the kitchen curtains."""
    m = load()
    lines = m.get("sketch") or []
    if not lines or not all(isinstance(x, str) for x in lines):
        return ""
    out = "\n".join(lines)
    leg = m.get("sketch_legend") or ""
    return out + ("\n(" + leg + ")" if leg else "")


def anchors_for(scene):
    """The real furniture of whatever room the scene names. [] if no match."""
    s = str(scene or "").strip().lower()
    if not s:
        return []
    for rid, r in rooms().items():
        if rid in s or s in rid:
            return list(r.get("anchors") or [])
    return []


if __name__ == "__main__":
    if "--sketch" in sys.argv:
        print(sketch_block() or "no house map"); sys.exit(0)
    m = load()
    if not m:
        print("no house map"); sys.exit(0)
    rs = rooms(m)
    print("%d rooms: %s" % (len(rs), ", ".join(sorted(rs))))
    a, b = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("outside", "bedroom")
    print("route %s -> %s: %s" % (a, b, " > ".join(route(a, b, m)) or "(none)"))
    print("arrival: %s" % (" > ".join(arrival_route(m)) or "(none)"))
