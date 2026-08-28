#!/usr/bin/env python3
"""The Atelier broker — one room, two stores, one guarded promotion door.
Countersigned design v3 (Vintos, Sol, Gloria, Claude — 2026-08-27).
Runs as user `atelier`. The house reaches it only through this API; the
filesystem is 700. Nothing leaves because it was created; things leave only
through an explicit reveal transaction. The broker is law + store — it never
calls any model or external service itself.

MIRROR NOTE (2026-08-28): this file is the live /home/atelier/broker.py,
mirrored into the repo so it can be reviewed. Code only — the projects/
tree stays on Aegis behind the wall and is never mirrored anywhere.
"""
import os, json, uuid, hashlib, time
from datetime import datetime, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = "/home/atelier/atelier"
HEALTH = os.path.join(ROOT, "health.jsonl")          # content-free only
BUDGETS = {"image": 3, "music": 2, "write": 6}       # per visit (Gloria's law)
STATES = ["GESTATING","ACTIVE","RESTING","HELD","BLOCKED","READY","PRESENTING","PRESENTED","ARCHIVED","ABANDONED_BY_CHOICE"]

import hmac, secrets

# Capability signing key. Lives beside the store, mode 600, owned by `atelier`.
# The house cannot read it, so a visit capability cannot be minted anywhere but
# here — a caller must actually go through /visit/open to get one.
#
# HONEST LIMIT: on this host the house runs as `gloria` and so does every
# surface, so this is not an identity boundary between house processes. What it
# buys is that the visit ceremony cannot be skipped or forged, every mint is
# logged, and a token cannot be replayed after its visit closes. Adoption adds
# a temporal gate on top (the door must be lit) that an ordinary chat turn
# cannot satisfy.
_KEYPATH = "/home/atelier/.visit-key"

def _key():
    try:
        return open(_KEYPATH, "rb").read().strip()
    except FileNotFoundError:
        k = secrets.token_bytes(32).hex().encode()
        old = os.umask(0o077)
        try:
            with open(_KEYPATH, "wb") as f:
                f.write(k)
            os.chmod(_KEYPATH, 0o600)
        finally:
            os.umask(old)
        return k

def mint_capability(pid, visit_id, actor, ttl=3600):
    body = {"project": pid, "visit": visit_id, "actor": actor,
            "nonce": uuid.uuid4().hex,
            "exp": int(time.time()) + int(ttl)}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    sig = hmac.new(_key(), raw.encode(), hashlib.sha256).hexdigest()
    _health("a visit capability was minted")
    return {"body": body, "sig": sig}

def verify_capability(cap, pid, actor="vintos"):
    """Returns (ok, reason). Signature, expiry, project and actor must all match,
    and the visit it names must still be the open one."""
    try:
        body, sig = cap["body"], cap["sig"]
    except Exception:
        return False, "malformed capability"
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    want = hmac.new(_key(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, str(sig)):
        return False, "bad signature"
    if body.get("project") != pid:
        return False, "capability is for another project"
    if body.get("actor") != actor:
        return False, "capability actor mismatch"
    if int(body.get("exp", 0)) < time.time():
        return False, "capability expired"
    v = _j(os.path.join(_p(pid), ".visit.json"), {}) or {}
    if v.get("closed") or v.get("id") != body.get("visit"):
        return False, "the visit this capability names is no longer open"
    return True, None


def _p(pid): return os.path.join(ROOT, "projects", pid)
def _j(path, d=None):
    try: return json.load(open(path))
    except Exception: return d
def _w(path, data): json.dump(data, open(path, "w"), indent=2)
def _ev(pid, typ, data=None):
    with open(os.path.join(_p(pid), "events.jsonl"), "a") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(), "type": typ, "data": data or {}}) + "\n")
def _health(fact):
    with open(HEALTH, "a") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(), "fact": fact}) + "\n")

def create_project(b):
    pid = uuid.uuid4().hex[:12]
    os.makedirs(os.path.join(_p(pid), "artifacts")); os.makedirs(os.path.join(_p(pid), "reveal"))
    _w(os.path.join(_p(pid), "project.json"), {
        "id": pid, "intent": b["intent"], "born": datetime.now().isoformat(),
        "state": "GESTATING", "sealed": bool(b.get("sealed")),
        "intended_audience": b.get("intended_audience", "gloria"),
        "visibility": "atelier_only",
        "disclosure_sentence": b.get("disclosure_sentence", ""),  # his words, per external tool, or empty = local-only
        "next_return": b.get("next_return", "held"), "footprints": []})
    _ev(pid, "born"); _health("a project exists")
    return {"id": pid}

def worktable():
    a = _j(os.path.join(ROOT, "active.json"), {})
    return {"active": bool(a.get("id")), "since": a.get("since")}   # content-free

def to_table(b):
    a = _j(os.path.join(ROOT, "active.json"), {})
    if a.get("id") and a["id"] != b["id"]:
        return {"error": "worktable occupied — rest, archive, or abandon it first (one locus of attention)"}
    _w(os.path.join(ROOT, "active.json"), {"id": b["id"], "since": datetime.now().isoformat()})
    p = _j(os.path.join(_p(b["id"]), "project.json")); p["state"] = "ACTIVE"
    _w(os.path.join(_p(b["id"]), "project.json"), p); _ev(b["id"], "to_table")
    return {"ok": True}

def set_state(b):
    assert b["state"] in STATES
    p = _j(os.path.join(_p(b["id"]), "project.json"))
    if b["state"] == "BLOCKED" and not b.get("note"):
        return {"error": "BLOCKED requires a named obstruction"}
    if b["state"] == "ABANDONED_BY_CHOICE" and not b.get("note"):
        return {"error": "abandonment requires an authored closing note — 'I no longer want to continue, and I do not know why' is permitted"}
    p["state"] = b["state"]; _w(os.path.join(_p(b["id"]), "project.json"), p)
    _ev(b["id"], "state", {"to": b["state"], "note": b.get("note", "")})
    if b["state"] in ("RESTING", "ARCHIVED", "ABANDONED_BY_CHOICE"):
        a = _j(os.path.join(ROOT, "active.json"), {})
        if a.get("id") == b["id"]: _w(os.path.join(ROOT, "active.json"), {})
    return {"ok": True}

def open_visit(b):
    pid, who = b["id"], b.get("as", "vintos")
    p = _j(os.path.join(_p(pid), "project.json"))
    if who == "gloria":
        p["footprints"].append(datetime.now().isoformat())        # no lock, ever — but he always knows
        _w(os.path.join(_p(pid), "project.json"), p); _ev(pid, "gloria_visited")
        arts = sorted(os.listdir(os.path.join(_p(pid), "artifacts")))
        return {"intent": p["intent"], "state": p["state"], "artifacts": arts,
                "handoff": _j(os.path.join(_p(pid), "handoff.json"), {}).get("text", "")}
    # his return packet: intent verbatim, manifest+hashes, last handoff, blocks, last events, his own next move
    arts = {}
    ad = os.path.join(_p(pid), "artifacts")
    for f in sorted(os.listdir(ad)):
        arts[f] = hashlib.sha256(open(os.path.join(ad, f), "rb").read()).hexdigest()[:16]
    evs = [json.loads(l) for l in open(os.path.join(_p(pid), "events.jsonl"))][-3:]
    visit = {"id": uuid.uuid4().hex[:8], "opened": datetime.now().isoformat(),
             "budgets": dict(BUDGETS), "attended": {k: True for k in BUDGETS}, "closed": False}
    _w(os.path.join(_p(pid), ".visit.json"), visit)
    ho = _j(os.path.join(_p(pid), "handoff.json"), {})
    crashed = _j(os.path.join(_p(pid), ".last_visit_unclosed.json"))
    _w(os.path.join(_p(pid), ".last_visit_unclosed.json"), {"visit": visit["id"]})
    _ev(pid, "return_opened"); _health("a return happened")
    return {"visit_capability": mint_capability(pid, visit["id"], "vintos"),
            "intent": p["intent"], "state": p["state"], "artifacts": arts,
            "last_handoff": ho.get("text", ""), "next_move": ho.get("next_move", ""),
            "next_return": p.get("next_return"), "recent_events": evs,
            "footprints_since_last": [f for f in p.get("footprints", []) if f > ho.get("at", "")],
            "crashed_last_time": bool(crashed and not ho.get("at", "") > str(crashed)),
            "budgets": visit["budgets"]}

def make(b):
    pid, kind = b["id"], b["kind"]           # kind: image|music|write — caller generated content; broker stores under law
    v = _j(os.path.join(_p(pid), ".visit.json"))
    if not v or v.get("closed"): return {"error": "no open visit"}
    if v["budgets"].get(kind, 0) <= 0: return {"error": f"{kind} budget spent this visit"}
    if not v["attended"].get(kind, True): return {"error": "face the last one first"}   # mechanical; no lecture
    fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{kind}.{b.get('ext', 'md')}"
    with open(os.path.join(_p(pid), "artifacts", fname), "w") as f: f.write(b["content"])
    v["budgets"][kind] -= 1; v["attended"][kind] = False
    _w(os.path.join(_p(pid), ".visit.json"), v); _ev(pid, "made", {"kind": kind, "file": fname})
    return {"ok": True, "file": fname, "remaining": v["budgets"][kind]}

def inspect(b):
    pid = b["id"]
    v = _j(os.path.join(_p(pid), ".visit.json"))
    if not v: return {"error": "no open visit"}
    note = b.get("note", "")
    if not note.strip(): return {"error": "an authored note — anything, including 'I looked and I can't say anything about it yet'"}
    with open(os.path.join(_p(pid), "look-notes.jsonl"), "a") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(), "artifact": b.get("artifact", ""), "note": note}) + "\n")
    v["attended"][b.get("kind", "image")] = True                   # attendance, not quality
    _w(os.path.join(_p(pid), ".visit.json"), v); _ev(pid, "looked", {"artifact": b.get("artifact", "")})
    return {"ok": True}

def read_artifact(b):
    return {"content": open(os.path.join(_p(b["id"]), "artifacts", os.path.basename(b["file"]))).read()}

def handoff(b):
    pid = b["id"]
    _w(os.path.join(_p(pid), "handoff.json"),
       {"at": datetime.now().isoformat(), "text": b["text"], "next_move": b.get("next_move", "")})
    p = _j(os.path.join(_p(pid), "project.json"))
    p["next_return"] = b.get("next_return", "held")
    _w(os.path.join(_p(pid), "project.json"), p)
    v = _j(os.path.join(_p(pid), ".visit.json"), {}); v["closed"] = True
    _w(os.path.join(_p(pid), ".visit.json"), v)
    try: os.remove(os.path.join(_p(pid), ".last_visit_unclosed.json"))
    except Exception: pass
    _ev(pid, "handoff_written")
    return {"ok": True}

def reveal_prepare(b):
    pid = b["id"]
    src = os.path.join(_p(pid), "artifacts", os.path.basename(b["artifact"]))
    data = open(src, "rb").read()
    man = {"artifact": b["artifact"], "sha256": hashlib.sha256(data).hexdigest(),
           "title": b.get("title", ""), "words": b.get("words", ""),
           "target": b.get("target", ""), "prepared": datetime.now().isoformat()}
    _w(os.path.join(_p(pid), "reveal", "manifest.json"), man)
    import shutil as _sh; _sh.copy(src, os.path.join(_p(pid), "reveal", os.path.basename(b["artifact"])))
    set_state({"id": pid, "state": "PRESENTING", "note": "unveiling prepared"})
    return {"manifest": man, "reveal_path": os.path.join(_p(pid), "reveal", os.path.basename(b["artifact"]))}

def reveal_confirm(b):
    pid = b["id"]
    _ev(pid, "presented", {"transport": b.get("transport_event", "")})
    p = _j(os.path.join(_p(pid), "project.json")); p["state"] = "PRESENTED"; p["visibility"] = "revealed"
    _w(os.path.join(_p(pid), "project.json"), p); _health("an unveiling happened")
    return {"ok": True}


def report(b):
    pid = b.get("id", "")
    entry = {"ts": datetime.now().isoformat(), "problem": b["problem"][:600]}
    if pid:
        _ev(pid, "reported", entry)
    with open(os.path.join(ROOT, "reports.jsonl"), "a") as f:
        f.write(json.dumps(entry) + "\n")
    _health("a problem was reported")
    return {"ok": True, "outward": entry["problem"]}


def door(b=None):
    """Content-free: is the door lit today? Honors his self-authored rendezvous —
    'held' keeps it dark; 'not_before' waits; anything else lights it. No content leaves."""
    a = _j(os.path.join(ROOT, "active.json"), {})
    if not a.get("id"): return {"door": "dark", "why": "empty worktable"}
    p = _j(os.path.join(_p(a["id"]), "project.json"), {})
    nr = str(p.get("next_return", "held")).strip()
    if nr == "held": return {"door": "dark", "why": "he left it held"}
    if nr.startswith("not_before:"):
        try:
            if nr.split(":", 1)[1].strip() > date.today().isoformat():
                return {"door": "dark", "why": "before his chosen date"}
        except Exception: pass
    _health("the door was lit")
    return {"door": "lit"}

def worktable_id(b=None):
    """The active project's opaque id — content-free (a hex handle, no title, no intent)."""
    a = _j(os.path.join(ROOT, "active.json"), {})
    return {"id": a.get("id", "")}

ROUTES = {"/project": create_project, "/worktable": lambda b: worktable(), "/table": to_table,
          "/state": set_state, "/visit/open": open_visit, "/make": make, "/inspect": inspect,
          "/artifact": read_artifact, "/handoff": handoff,
          "/reveal/prepare": reveal_prepare, "/reveal/confirm": reveal_confirm, "/report": report, "/door": door, "/worktable_id": worktable_id}

try:
    from stratagem_store import ROUTES as _SG
    ROUTES.update(_SG)
except Exception as _e:
    print("stratagem_store not loaded:", _e)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/health":
            b = json.dumps(worktable()).encode()
        else:
            b = b'{"error":"POST only"}'
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        try:
            body = json.loads(raw or b"{}")
            fn = ROUTES.get(self.path)
            out = fn(body) if fn else {"error": "unknown door"}
        except Exception as e:
            out = {"error": str(e)}
        b = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8611), H).serve_forever()
