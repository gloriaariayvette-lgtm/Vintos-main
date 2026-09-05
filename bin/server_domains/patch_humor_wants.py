#!/usr/bin/env python3
"""patch_humor_wants.py — edits the LIVE ~/Vintos/server_domains/humor_wants.py in place.

That file is not in the repo (it was cut from server.py on Aegis). This script applies exact,
asserted string replacements, keeps a timestamped backup beside the file, and syntax-checks the
result; if any anchor is missing it changes nothing and says which.

Run on Aegis:  python3 ~/.vintos/deploy/vintos-main/bin/server_domains/patch_humor_wants.py
Then restart vintos-server (the deploy script does).

What it changes (2026-09-05):
  grok-server-c-p1  avatar_presence: `sys` and `SCRIPTS` were never defined, so the nudge raised and the
                    bare except swallowed it — her presence moved nothing. Imported, set, logged loud.
  grok-server-c-p4  system_route_thread: `datetime` was never imported, so the route failed every time,
                    and a missing thread id succeeded silently. Imported; fails loud on a missing id.
  astra-server-c-p6 wants lifecycle: every API transition is an EVENT in memory/want-events.jsonl
                    (response_received, dismissed, unfulfilled, fulfilled, step_advanced, step_added,
                    step_removed, routed), transitions are idempotent (a fulfilled or dismissed want is
                    not fulfilled or dismissed again), and stable step ids are assigned.
  astra-server-c-p7 scene uploads: the destination is the basename only, must resolve under the
                    activity's root (no traversal, no symlink escape), and the content must be
                    PNG/JPEG/WEBP under 15 MB.
"""
import os, sys, re, shutil, time, subprocess

LIVE = os.path.expanduser("~/Vintos/server_domains/humor_wants.py")

EDITS = []
def edit(label, old, new, count=1):
    EDITS.append((label, old, new, count))

# ---- grok-server-c-p1: avatar_presence
edit("presence: imports + loud failure",
'''        if nudges:
            try:
                sys.path.insert(0, SCRIPTS)
                from emoclaw_utils import nudge_emotions
                nudge_emotions(nudges, source="avatar-presence")
            except: pass
        return {"success": True}''',
'''        if nudges:
            try:
                import sys as _ps
                _scripts = os.path.join(WORKSPACE, "scripts")
                if _scripts not in _ps.path: _ps.path.insert(0, _scripts)
                from emoclaw_utils import nudge_emotions
                nudge_emotions(nudges, source="avatar-presence")
                print(f"[avatar-presence] {event}: nudged {nudges}", flush=True)
            except Exception as _pe:
                # until 2026-09-05 `sys` and `SCRIPTS` did not exist here, so this raised on every event and
                # the bare except hid it: her presence moved nothing (grok-server-c-p1)
                print(f"[avatar-presence] nudge FAILED ({event}): {_pe}", flush=True)
        _want_event("presence", None, {"event": event, "duration_seconds": duration})
        return {"success": True}''')

# ---- grok-server-c-p4: system_route_thread
edit("system-route: datetime + loud on missing id",
'''        threads_path = os.path.join(MEMORY, "unfinished-threads.json")
        with open(threads_path) as f:
            threads = json.load(f)
        for t in threads:
            if t.get("id") == thread_id:
                t["system_route"] = system
                t["system_route_at"] = datetime.now().isoformat()
                break
        with open(threads_path, "w") as f:
            json.dump(threads, f, indent=2)
        return {"success": True, "thread_id": thread_id, "system": system}''',
'''        from datetime import datetime   # was never imported: the route raised every time (grok-server-c-p4)
        threads_path = os.path.join(MEMORY, "unfinished-threads.json")
        with open(threads_path) as f:
            threads = json.load(f)
        _hit = False
        for t in threads:
            if t.get("id") == thread_id:
                t["system_route"] = system
                t["system_route_at"] = datetime.now().isoformat()
                _hit = True
                break
        if not _hit:
            return {"success": False, "error": "thread %s not found - nothing routed" % thread_id}
        _atomic_json(threads_path, threads)
        return {"success": True, "thread_id": thread_id, "system": system}''')

# ---- astra-server-c-p6: lifecycle events + idempotency + stable step ids
edit("helpers after router",
'''router = APIRouter()
''',
'''router = APIRouter()

def _atomic_json(path, obj):
    """Write-then-replace so two API writers never half-write current-wants.json (astra-server-c-p6)."""
    _tmp = path + ".tmp.%d" % os.getpid()
    with open(_tmp, "w") as f: json.dump(obj, f, indent=2)
    os.replace(_tmp, path)

def _want_event(kind, want_id, detail=None):
    """Every lifecycle transition made through the API is a distinct, dated event
    (memory/want-events.jsonl): response_received, dismissed, unfulfilled, fulfilled, step_added,
    step_removed, step_advanced, routed, presence. Never raises."""
    try:
        import time as _t, uuid as _u
        with open(os.path.join(MEMORY, "want-events.jsonl"), "a") as f:
            f.write(json.dumps({"event_id": "WE-" + _u.uuid4().hex[:8], "t": _t.time(), "kind": kind,
                                "want_id": want_id, "actor": "gloria-api", "detail": detail or {}}) + "\\n")
    except Exception:
        pass
''')

edit("respond: idempotent + event",
'''        target["fulfilled"] = True
        target["gloria_response"] = response_text
        target["responded_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(wants_path, "w") as f:
            json.dump(wants, f, indent=2)
''',
'''        if target.get("fulfilled"):
            # idempotent: a second response to a fulfilled want is recorded as received, not re-fulfilled
            _want_event("response_received", want_id, {"response": response_text[:300], "already_fulfilled": True})
            return {"success": True, "already_fulfilled": True}
        target["fulfilled"] = True
        target["gloria_response"] = response_text
        target["responded_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
        target["fulfilled_by"] = "gloria_response"
        target.setdefault("satisfaction", "UNKNOWN")   # her answer completes the ask; whether it satisfied him is his to say
        _atomic_json(wants_path, wants)
        _want_event("response_received", want_id, {"response": response_text[:300]})
        _want_event("fulfilled", want_id, {"by": "gloria_response"})
''')

edit("dismiss: idempotent + event",
'''        target["dismissed"] = True
        target["dismissed_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(wants_path, "w") as f:
            json.dump(wants, f, indent=2)
''',
'''        if target.get("dismissed"):
            return {"success": True, "already_dismissed": True}
        target["dismissed"] = True
        target["dismissed_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
        _atomic_json(wants_path, wants)
        _want_event("dismissed", want_id, {})
''')

edit("patch: events for unfulfilled/dismissed/routing",
'''        with open(wants_path, "w") as f:
            json.dump(wants, f, indent=2)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/wants/{want_id}/discussion")''',
'''        _atomic_json(wants_path, wants)
        for _k, _ev in (("dismissed", "dismissed"), ("unfulfilled", "unfulfilled"), ("capability", "routed"), ("multistep", "routed")):
            if _k in body: _want_event(_ev, want_id, {_k: body[_k]})
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/wants/{want_id}/discussion")''')

edit("add step: stable id + event",
'''                step = {"capability": capability, "note": note, "status": "pending"}
                if params:
                    step["params"] = params
                w["steps"].append(step)
                with open(wants_path, "w") as f:
                    json.dump(wants, f, indent=2)
                return {"success": True, "steps": w["steps"]}''',
'''                step = {"step_id": "ST-" + __import__("uuid").uuid4().hex[:8], "capability": capability, "note": note, "status": "pending"}
                if params:
                    step["params"] = params
                w["steps"].append(step)
                _atomic_json(wants_path, wants)
                _want_event("step_added", want_id, {"step_id": step["step_id"], "capability": capability})
                return {"success": True, "steps": w["steps"]}''')

edit("remove step: event",
'''                steps.pop(step_index)
                w["steps"] = steps
                with open(wants_path, "w") as f:
                    json.dump(wants, f, indent=2)
                return {"success": True, "steps": steps}''',
'''                _removed = steps.pop(step_index)
                w["steps"] = steps
                _atomic_json(wants_path, wants)
                _want_event("step_removed", want_id, {"step_id": _removed.get("step_id"), "capability": _removed.get("capability")})
                return {"success": True, "steps": steps}''')

edit("advance: idempotent + events",
'''                steps = w.get("steps", [])
                current = w.get("current_step_index", 0)
                if current < len(steps):
                    steps[current]["status"] = "completed"
                w["steps"] = steps
                next_idx = current + 1
                if next_idx >= len(steps):
                    w["fulfilled"] = True
                    w["fulfilled_at"] = __import__("datetime").datetime.now().isoformat()
                    with open(wants_path, "w") as f:
                        json.dump(wants, f, indent=2)
                    return {"success": True, "fulfilled": True, "current_step_index": next_idx}
                else:
                    w["current_step_index"] = next_idx
                    with open(wants_path, "w") as f:
                        json.dump(wants, f, indent=2)
                    return {"success": True, "fulfilled": False, "current_step_index": next_idx}''',
'''                if w.get("fulfilled"):
                    return {"success": True, "fulfilled": True, "already_fulfilled": True, "current_step_index": w.get("current_step_index", 0)}
                steps = w.get("steps", [])
                current = w.get("current_step_index", 0)
                if current < len(steps):
                    steps[current]["status"] = "completed"
                    steps[current]["completed_by"] = "gloria_review"
                    _want_event("step_advanced", want_id, {"step_id": steps[current].get("step_id"), "index": current})
                w["steps"] = steps
                next_idx = current + 1
                if next_idx >= len(steps):
                    w["fulfilled"] = True
                    w["fulfilled_at"] = __import__("datetime").datetime.now().isoformat()
                    w["fulfilled_by"] = "steps_complete"
                    w.setdefault("satisfaction", "UNKNOWN")
                    _atomic_json(wants_path, wants)
                    _want_event("fulfilled", want_id, {"by": "steps_complete", "steps": len(steps)})
                    return {"success": True, "fulfilled": True, "current_step_index": next_idx}
                else:
                    w["current_step_index"] = next_idx
                    _atomic_json(wants_path, wants)
                    return {"success": True, "fulfilled": False, "current_step_index": next_idx}''')

# ---- astra-server-c-p7: scene uploads constrained + validated
edit("upload helpers",
'''# === Humor & Mischief API ===''',
'''def _scene_dest(activity, filename):
    """Destination for a scene image: basename only, under the activity's root, no symlink escape."""
    allowed = {"journal", "dreams", "gallery"}
    if activity not in allowed:
        raise HTTPException(status_code=400, detail=f"Activity must be one of {allowed}")
    name = os.path.basename(str(filename or "")).strip()
    if not name or name in (".", "..") or not re.match(r"^[\\w\\-. ]{1,120}$", name):
        raise HTTPException(status_code=400, detail="Unsafe filename")
    root = os.path.realpath(os.path.join(MEMORY, "scene-images", activity))
    os.makedirs(root, exist_ok=True)
    dest = os.path.realpath(os.path.join(root, name))
    if not dest.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Destination escapes the activity root")
    return dest, name

def _check_image(data):
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image over 15 MB")
    if not (data[:8] == b"\\x89PNG\\r\\n\\x1a\\n" or data[:3] == b"\\xff\\xd8\\xff" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        raise HTTPException(status_code=415, detail="Not a PNG, JPEG or WEBP")

# === Humor & Mischief API ===''')

edit("upload b64: constrained",
'''    allowed = {"journal", "dreams", "gallery"}
    if activity not in allowed:
        raise HTTPException(status_code=400, detail=f"Activity must be one of {allowed}")
    dest_dir = os.path.join(MEMORY, "scene-images", activity)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, filename)
    with open(dest, "wb") as f:
        f.write(base64.b64decode(data_b64))
    return {"saved": dest, "activity": activity, "filename": filename}''',
'''    dest, filename = _scene_dest(activity, filename)   # astra-server-c-p7
    try:
        data = base64.b64decode(data_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Bad base64")
    _check_image(data)
    with open(dest, "wb") as f:
        f.write(data)
    return {"saved": dest, "activity": activity, "filename": filename}''')

edit("upload multipart: constrained",
'''    allowed = {"journal", "dreams", "gallery"}
    if activity not in allowed:
        raise HTTPException(status_code=400, detail=f"Activity must be one of {allowed}")
    dest_dir = os.path.join(MEMORY, "scene-images", activity)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, filename)
    data = await file.read()
    with open(dest, "wb") as f:
        f.write(data)
    return {"saved": dest, "activity": activity, "filename": filename}''',
'''    dest, filename = _scene_dest(activity, filename)   # astra-server-c-p7
    data = await file.read()
    _check_image(data)
    with open(dest, "wb") as f:
        f.write(data)
    return {"saved": dest, "activity": activity, "filename": filename}''')

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else LIVE
    if not os.path.exists(path):
        print("not found:", path); return 2
    src = open(path, encoding="utf-8").read()
    if "_want_event(" in src:
        print("already patched:", path); return 0
    missing = [label for label, old, new, count in EDITS if src.count(old) != count]
    if missing:
        print("NOTHING CHANGED - anchors missing or duplicated:", "; ".join(missing)); return 1
    out = src
    for label, old, new, count in EDITS:
        out = out.replace(old, new, count)
    if "import os, json" in out and "import os, json, re" not in out:
        out = out.replace("import os, json\n", "import os, json, re\n", 1)
    bak = path + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, bak)
    tmp = path + ".tmp"
    open(tmp, "w", encoding="utf-8").write(out)
    r = subprocess.run([sys.executable, "-m", "py_compile", tmp], capture_output=True, text=True)
    if r.returncode:
        os.remove(tmp); print("syntax check FAILED, nothing installed:", r.stderr[-800:]); return 1
    os.replace(tmp, path)
    print("patched:", path); print("backup:", bak)
    print("applied:", ", ".join(l for l, *_ in EDITS))
    return 0

if __name__ == "__main__":
    sys.exit(main())
