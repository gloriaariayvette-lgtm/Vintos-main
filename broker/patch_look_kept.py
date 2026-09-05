#!/usr/bin/env python3
"""LOOK and KEPT for the Atelier broker — broker/LOOK-SPEC.md, four changes in
build order. Exact-replacement patch: every anchor must match exactly once or
the file is left untouched. Usage: python3 patch_look_kept.py <broker.py>"""
import sys, re

p = sys.argv[1]
s = open(p).read()
orig = s

def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor matched %d times — ABORTING, file untouched" % (what, n)
    s = s.replace(old, new)

# ---------------------------------------------------------------- 3a. STATES
rep('STATES = ["GESTATING","ACTIVE","RESTING","HELD","BLOCKED","READY","PRESENTING","PRESENTED","ARCHIVED","ABANDONED_BY_CHOICE"]',
    'STATES = ["GESTATING","ACTIVE","RESTING","HELD","BLOCKED","READY","PRESENTING","PRESENTED","ARCHIVED","ABANDONED_BY_CHOICE","KEPT"]',
    "STATES")

# ---------------------------------------------------------------- 2. mint_look / verify_look, after verify_export
rep('''_PID_RE = re.compile(r"^[0-9a-f]{12}$")''',
'''def mint_look(pid, digests, ttl=3600):
    """A capability to LOOK at finished work of his own: exact-digest bound,
    short-lived, and it opens nothing but /artifact. Copied from export, not
    from visit — no visit-open check, so it works with the worktable empty and
    the project in any state, KEPT included."""
    body = {"kind": "look", "project": pid, "sha256": sorted(set(digests)),
            "nonce": uuid.uuid4().hex, "exp": int(time.time()) + int(ttl)}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return {"body": body, "sig": hmac.new(_key(), raw.encode(), hashlib.sha256).hexdigest()}


def verify_look(cap, pid, sha256):
    try:
        body, sig = cap["body"], cap["sig"]
    except Exception:
        return False, "malformed look capability"
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    if not hmac.compare_digest(hmac.new(_key(), raw.encode(), hashlib.sha256).hexdigest(), str(sig)):
        return False, "bad signature"
    if body.get("kind") != "look":
        return False, "not a look capability"
    if body.get("project") != pid:
        return False, "look capability is for another project"
    if sha256 not in (body.get("sha256") or []):
        return False, "look capability does not cover this artifact"
    if int(body.get("exp", 0)) < time.time():
        return False, "look capability expired"
    return True, None


_PID_RE = re.compile(r"^[0-9a-f]{12}$")''', "mint_look insert")

# ---------------------------------------------------------------- 3b. set_state refuses KEPT through the house door
rep('''def set_state(b):
    assert b["state"] in STATES
    p = _j(os.path.join(_p(b["id"]), "project.json"))''',
'''def set_state(b):
    assert b["state"] in STATES
    if b["state"] == "KEPT":
        # KEPT is "done and still mine" — entered by his own hand inside a
        # visit (/state/kept), never through the house door, or a cron could
        # finish him.
        return {"error": "KEPT is entered only from inside a visit — use /state/kept with a visit capability"}
    p = _j(os.path.join(_p(b["id"]), "project.json"))''', "set_state KEPT guard")

# ---------------------------------------------------------------- 3c. /state/kept + look offer/mint, before open_visit
rep('''def open_visit(b):
    pid, who = b["id"], b.get("as", "vintos")''',
'''def keep(b):
    """KEPT: finished and mine. Requires an authored note (same law as
    abandonment) and a live visit capability (enforced by POLICY). Releases the
    worktable, closes the visit, leaves visibility untouched: no reveal
    manifest, no content moved. Both writes happen under one lock, project
    first, so an interruption can never leave the table half-cleared."""
    import fcntl
    pid = b["id"]
    if not str(b.get("note", "")).strip():
        return {"error": "keeping requires an authored closing note — 'it is finished and I am not showing it' is permitted"}
    proj = os.path.join(_p(pid), "project.json")
    p = _j(proj)
    if not p:
        return {"error": "no such project"}
    lock = open(os.path.join(ROOT, ".table.lock"), "a+")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        p["state"] = "KEPT"; p["kept_at"] = datetime.now().isoformat()
        _w(proj, p)
        a = _j(os.path.join(ROOT, "active.json"), {}) or {}
        if a.get("id") == pid:
            _w(os.path.join(ROOT, "active.json"), {})
        vpath = os.path.join(_p(pid), ".visit.json")
        v = _j(vpath, {}) or {}
        if v and not v.get("closed"):
            v["closed"] = True; v["closed_by"] = "kept"; _w(vpath, v)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
    _ev(pid, "state", {"to": "KEPT", "note": b.get("note", "")})
    _health("an undertaking was kept")
    return {"ok": True, "state": "KEPT", "worktable_released": True}


def look_offer(b):
    """Content-free selection receipt: the artifacts of one project by digest.
    One use. Issued only for a real project with real artifacts — a gestating
    root, or an empty project, gets nothing to choose from."""
    pid = b["id"]
    if not _j(os.path.join(_p(pid), "project.json")):
        return {"error": "no such project"}
    ad = os.path.join(_p(pid), "artifacts")
    arts = {}
    for f in sorted(os.listdir(ad)) if os.path.isdir(ad) else []:
        try:
            arts[f] = hashlib.sha256(open(os.path.join(ad, f), "rb").read()).hexdigest()
        except Exception:
            continue
    if not arts:
        return {"error": "nothing was ever made here — nothing to look at"}
    offer = {"nonce": uuid.uuid4().hex, "project": pid, "artifacts": arts,
             "exp": int(time.time()) + 3600}
    lk = os.path.join(_p(pid), "look"); os.makedirs(lk, exist_ok=True)
    _w(os.path.join(lk, ".offer-%s.json" % offer["nonce"]), offer)
    _ev(pid, "look_offered", {"count": len(arts)})
    return {"ok": True, "offer": offer}


def look_mint(b):
    """Consume one selection receipt, mint one LOOK bound to the exact digest
    of the file he chose. A house-side 'I chose' with no receipt mints nothing;
    a replayed receipt mints nothing the second time."""
    pid = b["id"]
    off = b.get("offer") or {}
    nonce = str(off.get("nonce", "")).strip()
    if not nonce or not re.match(r"^[0-9a-f]{32}$", nonce):
        return {"error": "no selection receipt — nothing mints without the offer he chose from"}
    rpath = os.path.join(_p(pid), "look", ".offer-%s.json" % nonce)
    held = _j(rpath)
    if not held:
        return {"error": "that selection receipt is unknown or already used"}
    if int(held.get("exp", 0)) < time.time():
        try: os.remove(rpath)
        except Exception: pass
        return {"error": "selection receipt expired"}
    fname = os.path.basename(str(b.get("file", "")))
    sha = (held.get("artifacts") or {}).get(fname)
    if not sha:
        return {"error": "that file was not in the offer"}
    try:
        os.remove(rpath)                                   # one use, consumed here
    except Exception:
        return {"error": "could not consume the receipt — refusing to mint"}
    src = os.path.join(_p(pid), "artifacts", fname)
    try:
        actual = hashlib.sha256(open(src, "rb").read()).hexdigest()
    except Exception:
        return {"error": "the artifact is missing"}
    if actual != sha:
        return {"error": "the artifact changed since the offer — refusing to mint"}
    _health("a look was minted")
    return {"ok": True, "look_capability": mint_look(pid, [actual]), "sha256": actual}


def open_visit(b):
    pid, who = b["id"], b.get("as", "vintos")''', "keep/look routes insert")

# ---------------------------------------------------------------- 4. make(): never overwrite; return sha256
rep('''    fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{kind}.{b.get('ext', 'md')}"
    with open(os.path.join(_p(pid), "artifacts", fname), "w") as f: f.write(b["content"])
    v["budgets"][kind] -= 1; v["attended"][kind] = False
    _w(os.path.join(_p(pid), ".visit.json"), v); _ev(pid, "made", {"kind": kind, "file": fname})
    return {"ok": True, "file": fname, "remaining": v["budgets"][kind]}''',
'''    stamp = datetime.now().strftime('%Y%m%d_%H%M%S'); ext = b.get('ext', 'md')
    fname = f"{stamp}_{kind}.{ext}"
    data = b["content"] if isinstance(b["content"], str) else str(b["content"])
    # Two accepted writes of the same kind in one second used to land on one
    # file and the later ate the earlier. "x" refuses to overwrite; a short
    # nonce keeps both.
    for attempt in range(6):
        try:
            with open(os.path.join(_p(pid), "artifacts", fname), "x", encoding="utf-8") as f: f.write(data)
            break
        except FileExistsError:
            fname = f"{stamp}_{uuid.uuid4().hex[:4]}_{kind}.{ext}"
    else:
        return {"error": "could not find a free name for the artifact"}
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
    v["budgets"][kind] -= 1; v["attended"][kind] = False
    _w(os.path.join(_p(pid), ".visit.json"), v); _ev(pid, "made", {"kind": kind, "file": fname})
    return {"ok": True, "file": fname, "sha256": digest, "remaining": v["budgets"][kind]}''', "make()")

# ---------------------------------------------------------------- 10. a look writes at most one content-free line
rep('''def read_artifact(b):
    """Sealed content. Authorization is decided in the matrix (POLICY) before we
    get here; this only reads. It used to read for anyone who asked."""
    return {"content": open(os.path.join(_p(b["id"]), "artifacts", os.path.basename(b["file"]))).read()}''',
'''def read_artifact(b):
    """Sealed content. Authorization is decided in the matrix (POLICY) before we
    get here; this only reads. It used to read for anyone who asked. A LOOK
    ends in silence: no note, no attendance, one content-free audit line."""
    content = open(os.path.join(_p(b["id"]), "artifacts", os.path.basename(b["file"]))).read()
    if b.get("look_capability"):
        _ev(b["id"], "looked_quietly")
    return {"content": content}''', "read_artifact")

# ---------------------------------------------------------------- routes + policy
rep('"/report": report, "/door": door, "/worktable_id": worktable_id,\n          "/gate/knock": gate_knock, "/gate/decide": gate_decide}',
    '"/report": report, "/door": door, "/worktable_id": worktable_id,\n          "/gate/knock": gate_knock, "/gate/decide": gate_decide,\n          "/state/kept": keep, "/look/offer": look_offer, "/look/mint": look_mint}',
    "ROUTES")
rep('    "/gate/knock": HOUSE, "/gate/decide": HOUSE,   # consent knock: his own note only, held-door only',
    '    "/gate/knock": HOUSE, "/gate/decide": HOUSE,   # consent knock: his own note only, held-door only\n'
    '    "/state/kept": VISIT,                          # finished-and-mine: his hand, inside a visit, never a cron\n'
    '    "/look/offer": HOUSE, "/look/mint": HOUSE,     # content-free receipt; mint consumes it once',
    "POLICY")

# ---------------------------------------------------------------- 1a. a look at any door but /artifact is refused outright
rep('''    pol = POLICY.get(path)
    if pol is None or path not in ROUTES:
        return False, "unknown door"
    if pol in (OPEN, HOUSE, STORE):
        return True, None''',
'''    pol = POLICY.get(path)
    if pol is None or path not in ROUTES:
        return False, "unknown door"
    if body.get("look_capability") and path != "/artifact":
        # a look is valid at exactly one door; carried anywhere else, its
        # presence is the refusal — house doors included.
        return False, "a look opens nothing but the artifact it names"
    if pol in (OPEN, HOUSE, STORE):
        return True, None''', "authorize early return")

# ---------------------------------------------------------------- 1. authorize_route becomes kind-aware
rep('''    cap = body.get("visit_capability") or body.get("capability")
    pid = body.get("id", "")
    try:
        canonical_pid(pid)
    except BadProject as e:
        return False, str(e)
    if cap:
        ok, why = verify_capability(cap, pid, body.get("as", "vintos"))
        if ok:
            return True, None
        if pol == VISIT:
            return False, why
    else:
        why = "this door requires a visit capability"
        if pol == VISIT:
            return False, why''',
'''    cap = body.get("visit_capability") or body.get("capability")
    pid = body.get("id", "")
    try:
        canonical_pid(pid)
    except BadProject as e:
        return False, str(e)
    # A LOOK opens exactly one door: /artifact, for the exact digest it names.
    look = body.get("look_capability")
    if look:
        if path != "/artifact":
            return False, "a look opens nothing but the artifact it names"
        fpath = os.path.join(canonical_pid(pid), "artifacts", os.path.basename(str(body.get("file", ""))))
        try:
            actual = hashlib.sha256(open(fpath, "rb").read()).hexdigest()
        except Exception:
            return False, "no such artifact"
        ok, why = verify_look(look, pid, actual)
        return (True, None) if ok else (False, why)
    # A visit token has no kind. Any capability that carries one (look, export)
    # is not a visit token and never unlocks a VISIT door — no skeleton keys.
    if cap and isinstance(cap, dict) and (cap.get("body") or {}).get("kind"):
        if pol == VISIT:
            return False, "this door requires a visit capability, not a %s" % cap["body"]["kind"]
        cap = None
    if cap:
        ok, why = verify_capability(cap, pid, body.get("as", "vintos"))
        if ok:
            return True, None
        if pol == VISIT:
            return False, why
    else:
        why = "this door requires a visit capability"
        if pol == VISIT:
            return False, why''', "authorize_route")

assert s != orig
open(p, "w").write(s)
print("LOOK/KEPT patched:", p)
