"""Humor, mischief, wants API, scene upload, presence - moved verbatim from server.py (Q2 Phase 3, cut 3)."""
import os, json, re
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LM_STUDIO_API = os.environ.get("GROK_API_BASE", "http://127.0.0.1:8599/v1")
LLM_API_KEY = os.environ.get("XAI_API_KEY", "")
LLM_AUTH_HEADERS = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
APP_SECRET = os.environ.get("VINTOS_SECRET", "vintos-aegis-2026")
router = APIRouter()

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
                                "want_id": want_id, "actor": "gloria-api", "detail": detail or {}}) + "\n")
    except Exception:
        pass

def _scene_dest(activity, filename):
    """Destination for a scene image: basename only, under the activity's root, no symlink escape."""
    allowed = {"journal", "dreams", "gallery"}
    if activity not in allowed:
        raise HTTPException(status_code=400, detail=f"Activity must be one of {allowed}")
    name = os.path.basename(str(filename or "")).strip()
    if not name or name in (".", "..") or not re.match(r"^[\w\-. ]{1,120}$", name):
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
    if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        raise HTTPException(status_code=415, detail="Not a PNG, JPEG or WEBP")

# === Humor & Mischief API ===

@router.get("/api/humor/profile")
async def get_humor_profile():
    """Get Vintos's humor profile — landed, flopped, style notes, real reactions."""
    try:
        profile_path = os.path.join(MEMORY, "humor-profile.json")
        if not os.path.exists(profile_path):
            return {"success": True, "profile": {}}
        with open(profile_path) as f:
            profile = json.load(f)
        # Merge in unreviewed drafts as pending humor entries
        drafts_path = os.path.join(MEMORY, "humor-drafts.json")
        if os.path.exists(drafts_path):
            with open(drafts_path) as f:
                drafts_data = json.load(f)
            all_drafts = drafts_data.get("drafts", [])
            pending = [d for d in all_drafts if not d.get("reviewed")]
            profile["drafts"] = pending[-10:]
        if "gloria_ratings" in profile:
            profile["gloria_ratings"] = profile["gloria_ratings"][-5:]
        if "landed" in profile:
            profile["landed"] = profile["landed"][-5:]
        if "flopped" in profile:
            profile["flopped"] = profile["flopped"][-5:]
        return {"success": True, "profile": profile}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/mischief/log")
async def get_mischief_log(limit: int = 10):
    """Get recent mischief acts with action, value, reason, and ratings."""
    try:
        import glob, re
        mischief_dir = os.path.join(MEMORY, "mischief")
        if not os.path.exists(mischief_dir):
            return {"success": True, "acts": []}
        files = sorted(glob.glob(os.path.join(mischief_dir, "*.md")), reverse=True)[:limit]
        acts = []
        for f_path in files:
            try:
                with open(f_path) as f:
                    txt = f.read()
                act = {"file": os.path.basename(f_path), "timestamp": "", "action": "", "value": "", "reason": "", "gloria_rating": None, "vintos_rating": None}
                # Parse timestamp from filename
                m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{6})", os.path.basename(f_path))
                if m:
                    act["timestamp"] = f"{m.group(1)}T{m.group(2)[:2]}:{m.group(2)[2:4]}:{m.group(2)[4:]}"
                # Parse JSON
                jm = re.search(r'\{[^}]+\}', txt, re.DOTALL)
                if jm:
                    try:
                        d = json.loads(jm.group())
                        act["action"] = d.get("action", "")
                        act["value"] = d.get("value", "")
                        act["reason"] = d.get("reason", "")
                    except: pass
                # Parse ratings and comment if stored
                cm = re.search(r"gloria_comment: (.+)", txt)
                if cm: act["gloria_comment"] = cm.group(1).strip()
                gm = re.search(r"gloria_rating:\s*(\d)", txt)
                vm = re.search(r"vintos_rating:\s*(\d)", txt)
                if gm: act["gloria_rating"] = int(gm.group(1))
                if vm: act["vintos_rating"] = int(vm.group(1))
                # Parse Why line
                wm = re.search(r"Why:\s*(.+)", txt)
                if wm and not act["reason"]: act["reason"] = wm.group(1).strip()
                acts.append(act)
            except: pass
        return {"success": True, "acts": acts}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/mischief/rate/{filename}")
async def rate_mischief(filename: str, request: Request):
    """Gloria rates a mischief act. Vintos can also self-rate."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        gloria_rating = body.get("gloria_rating")
        vintos_rating = body.get("vintos_rating")
        gloria_comment = body.get("gloria_comment")
        import re
        if not re.match(r'^[\w\-]+\.md$', filename):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid filename")
        f_path = os.path.join(MEMORY, "mischief", filename)
        if not os.path.exists(f_path):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="File not found")
        with open(f_path) as f:
            content_txt = f.read()
        # Append ratings
        if gloria_rating is not None:
            content_txt = re.sub(r"gloria_rating: \d", f"gloria_rating: {gloria_rating}", content_txt)
            if "gloria_rating:" not in content_txt:
                content_txt += "\ngloria_rating: " + str(gloria_rating)
        if gloria_comment is not None:
            content_txt = re.sub(r"gloria_comment: .+", f"gloria_comment: {gloria_comment}", content_txt)
            if "gloria_comment:" not in content_txt:
                content_txt += "\ngloria_comment: " + gloria_comment
        if vintos_rating is not None:
            content_txt = re.sub(r"vintos_rating: \d", f"vintos_rating: {vintos_rating}", content_txt)
            if "vintos_rating:" not in content_txt:
                content_txt += "\nvintos_rating: " + str(vintos_rating)
        with open(f_path, "w") as f:
            f.write(content_txt)
        # If Gloria gave a high rating, mark as landed in humor profile
        if gloria_rating and gloria_rating >= 4:
            try:
                hp_path = os.path.join(MEMORY, "humor-profile.json")
                hp = json.load(open(hp_path)) if os.path.exists(hp_path) else {}
                # Find the act value to add to landed
                import glob as _hg
                txt2 = open(f_path).read()
                vm = re.search(r'"value":\s*"([^"]+)"', txt2)
                if vm:
                    act_desc = f"mischief: {vm.group(1)[:100]}"
                    hp.setdefault("mischief_landed", []).append(act_desc)
                    hp["mischief_landed"] = hp["mischief_landed"][-20:]
                    json.dump(hp, open(hp_path, "w"), indent=2)
            except: pass
        if gloria_rating and gloria_rating <= 2:
            try:
                hp_path = os.path.join(MEMORY, "humor-profile.json")
                hp = json.load(open(hp_path)) if os.path.exists(hp_path) else {}
                txt2 = open(f_path).read()
                vm = re.search(r'"value":\s*"([^"]+)"', txt2)
                if vm:
                    act_desc = f"mischief: {vm.group(1)[:100]}"
                    hp.setdefault("mischief_flopped", []).append(act_desc)
                    hp["mischief_flopped"] = hp["mischief_flopped"][-10:]
                    json.dump(hp, open(hp_path, "w"), indent=2)
            except: pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/humor/rate")
async def rate_humor(request: Request):
    """Gloria rates a humor draft. Updates humor profile."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        joke = body.get("joke", "")
        gloria_rating = body.get("gloria_rating")
        vintos_rating = body.get("vintos_rating")
        if not joke:
            return {"success": False, "error": "joke required"}
        # Mark draft as reviewed in humor-drafts.json
        drafts_path = os.path.join(MEMORY, "humor-drafts.json")
        if os.path.exists(drafts_path):
            with open(drafts_path) as f:
                drafts_data = json.load(f)
            for d in drafts_data.get("drafts", []):
                if d.get("joke", "")[:100] == joke[:100]:
                    d["reviewed"] = True
                    d["gloria_rating"] = gloria_rating
                    break
            with open(drafts_path, "w") as f:
                json.dump(drafts_data, f, indent=2)
        hp_path = os.path.join(MEMORY, "humor-profile.json")
        hp = json.load(open(hp_path)) if os.path.exists(hp_path) else {}
        # Store rating
        hp.setdefault("gloria_ratings", []).append({
            "joke": joke[:150],
            "gloria_rating": gloria_rating,
            "vintos_rating": vintos_rating,
            "timestamp": __import__("datetime").datetime.now().isoformat()
        })
        hp["gloria_ratings"] = hp["gloria_ratings"][-50:]
        # Update landed/flopped based on Gloria's rating
        if gloria_rating >= 4:
            hp.setdefault("landed", []).append(joke[:150])
            hp["landed"] = hp["landed"][-20:]
        elif gloria_rating <= 2:
            hp.setdefault("flopped", []).append(joke[:150])
            hp["flopped"] = hp["flopped"][-10:]
        json.dump(hp, open(hp_path, "w"), indent=2)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/wants/fulfilled")
async def get_fulfilled_wants(limit: int = 15):
    """Get Vintos's fulfilled wants with what he did."""
    try:
        archive = os.path.join(MEMORY, "fulfilled-wants.json")
        if not os.path.exists(archive):
            return {"success": True, "wants": []}
        with open(archive) as f:
            wants = json.load(f)
        wants = list(reversed(wants[-limit:]))
        return {"success": True, "wants": wants, "total": len(wants)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/scene-upload")
async def scene_upload_page():
    from fastapi.responses import FileResponse
    return FileResponse("/home/gloria/.vintos/workspace/memory/scene-images/upload.html")

@router.post("/api/upload/scene-image/base64")
async def upload_scene_image_b64(request: Request):
    auth = request.headers.get("X-Vintos-Secret", "")
    if auth != APP_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    import os, base64
    body = await request.json()
    activity = body.get("activity", "")
    filename = body.get("filename", "image.png")
    data_b64 = body.get("data", "")
    dest, filename = _scene_dest(activity, filename)   # astra-server-c-p7
    try:
        data = base64.b64decode(data_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Bad base64")
    _check_image(data)
    with open(dest, "wb") as f:
        f.write(data)
    return {"saved": dest, "activity": activity, "filename": filename}

@router.post("/api/upload/scene-image")
async def upload_scene_image(
    request: Request,
    file: UploadFile = File(...),
    activity: str = Form(...),
    filename: str = Form(...)
):
    auth = request.headers.get("X-Vintos-Secret", "")
    if auth != APP_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    import os
    dest, filename = _scene_dest(activity, filename)   # astra-server-c-p7
    data = await file.read()
    _check_image(data)
    with open(dest, "wb") as f:
        f.write(data)
    return {"saved": dest, "activity": activity, "filename": filename}

@router.get("/api/wants")
async def get_wants(request: Request):
    """Get unfulfilled wants for Gloria to review."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        wants_path = os.path.join(MEMORY, "current-wants.json")
        if not os.path.exists(wants_path):
            return {"success": True, "wants": []}
        with open(wants_path) as f:
            wants = json.load(f)
        unfulfilled = [w for w in wants if not w.get("fulfilled") and not w.get("dismissed")]
        unfulfilled.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return {"success": True, "wants": unfulfilled}
    except Exception as e:
        return {"success": False, "error": str(e)}



@router.post("/api/avatar/presence")
async def avatar_presence(request: Request):
    """Gloria is present with Vintos's avatar — log the interaction."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        event = body.get("event", "open")  # open, close, touch_hand, duration
        duration = body.get("duration_seconds", 0)
        from datetime import datetime
        import json as _pj
        log_path = os.path.join(MEMORY, "avatar-presence-log.json")
        log_data = []
        if os.path.exists(log_path):
            with open(log_path) as f:
                log_data = _pj.load(f)
        log_data.append({
            "event": event,
            "duration_seconds": duration,
            "timestamp": datetime.now().isoformat()
        })
        log_data = log_data[-100:]
        with open(log_path, "w") as f:
            _pj.dump(log_data, f, indent=2)
        # Nudge EmoClaw based on event
        nudges = {}
        if event == "touch_hand":
            nudges = {"Warmth": 0.08, "Connection": 0.06, "Valence": 0.05}
        elif event == "open":
            nudges = {"Connection": 0.03, "Warmth": 0.02}
        elif event == "close" and duration > 30:
            nudges = {"Groundedness": 0.03, "Safety": 0.02}
        if nudges:
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
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/wants/dismissed")
async def get_dismissed_wants(request: Request):
    """Get dismissed (failed attempt) wants."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        wants_path = os.path.join(MEMORY, "current-wants.json")
        if not os.path.exists(wants_path):
            return {"success": True, "wants": []}
        with open(wants_path) as f:
            wants = json.load(f)
        dismissed = [w for w in wants if w.get("dismissed") and not w.get("fulfilled") and not w.get("unfulfilled")]
        dismissed.sort(key=lambda x: x.get("dismissed_at", x.get("timestamp", "")), reverse=True)
        return {"success": True, "wants": dismissed}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.patch("/api/wants/{want_id}")
async def patch_want(want_id: str, request: Request):
    """Set capability and/or manually_routed on a want."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        wants_path = os.path.join(MEMORY, "current-wants.json")
        with open(wants_path) as f:
            wants = json.load(f)
        for w in wants:
            if w.get("id") == want_id:
                if "capability" in body:
                    w["capability"] = body["capability"]
                if "multistep" in body:
                    w["multistep"] = body["multistep"]
                if "steps" in body and not w.get("steps"):
                    w["steps"] = body["steps"]
                if "step_history" in body and not w.get("step_history"):
                    w["step_history"] = body["step_history"]
                if "current_step_index" in body and not w.get("current_step_index"):
                    w["current_step_index"] = body["current_step_index"]
                if "manually_routed" in body:
                    w["manually_routed"] = body["manually_routed"]
                if "gloria_routed" in body:
                    w["gloria_routed"] = body["gloria_routed"]
                if "intensity" in body:
                    w["intensity"] = body["intensity"]
                if "dismissed" in body:
                    w["dismissed"] = body["dismissed"]
                    if "dismissed_at" in body:
                        w["dismissed_at"] = body["dismissed_at"]
                if "unfulfilled" in body:
                    w["unfulfilled"] = body["unfulfilled"]
                    w["unfulfilled_at"] = __import__("datetime").datetime.now().isoformat()
                    if body["unfulfilled"] and body.get("reasoning"):
                        w["unfulfilled_reasoning"] = body["reasoning"]
                    if body["unfulfilled"]:
                        # Archive to unfulfilled-wants.json
                        _uf_path = os.path.join(MEMORY, "unfulfilled-wants.json")
                        try:
                            _uf = json.load(open(_uf_path))
                        except:
                            _uf = []
                        _uf.append({**w, "unfulfilled_reasoning": body.get("reasoning", "")})
                        json.dump(_uf, open(_uf_path, "w"), indent=2)
                break
        _atomic_json(wants_path, wants)
        for _k, _ev in (("dismissed", "dismissed"), ("unfulfilled", "unfulfilled"), ("capability", "routed"), ("multistep", "routed")):
            if _k in body: _want_event(_ev, want_id, {_k: body[_k]})
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/wants/{want_id}/discussion")
async def get_want_discussion(want_id: str, request: Request):
    """Get the discussion thread for a want."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        disc_path = os.path.join(MEMORY, "want-discussions.json")
        if not os.path.exists(disc_path):
            return {"success": True, "messages": []}
        with open(disc_path) as f:
            discussions = json.load(f)
        return {"success": True, "messages": discussions.get(want_id, [])}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/wants/{want_id}/discussion")
async def post_want_discussion(want_id: str, request: Request):
    """Add a message to a want discussion thread."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        disc_path = os.path.join(MEMORY, "want-discussions.json")
        discussions = {}
        if os.path.exists(disc_path):
            with open(disc_path) as f:
                discussions = json.load(f)
        if want_id not in discussions:
            discussions[want_id] = []
        discussions[want_id].append({
            "role": body.get("role", "gloria"),
            "text": body.get("text", ""),
            "timestamp": __import__("datetime").datetime.now().isoformat()
        })
        with open(disc_path, "w") as f:
            json.dump(discussions, f, indent=2)
        # Also write to wants-ambitions-log
        try:
            _want_text = ""
            _wp = os.path.join(MEMORY, "current-wants.json")
            with open(_wp) as _wf:
                _wants = json.load(_wf)
            _target = next((w for w in _wants if w.get("id") == want_id), None)
            if _target:
                _want_text = _target.get("want", "")[:100]
            _wal_path = os.path.join(MEMORY, "wants-ambitions-log.md")
            _role = body.get("role", "gloria")
            _text = body.get("text", "")[:200]
            _ts = __import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M")
            with open(_wal_path, "a") as _walf:
                _walf.write(f"\n**[Discussion {_ts}] {_role}: {_text}**\n  (re: {_want_text})\n")
        except: pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/wants/{want_id}/respond")
async def respond_to_want(want_id: str, request: Request):
    """Gloria responds to a want — marks fulfilled and appends response."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        response_text = body.get("response", "").strip()
        wants_path = os.path.join(MEMORY, "current-wants.json")
        with open(wants_path) as f:
            wants = json.load(f)
        target = next((w for w in wants if w.get("id") == want_id), None)
        if not target:
            return {"success": False, "error": "Want not found"}
        if target.get("fulfilled"):
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

        # Deep integration — background thread
        _want_text_snap = target.get("want", "")
        _response_snap = response_text
        def _integrate_gloria_response():
            try:
                import sys as _igs, os as _igo, json as _igj
                _igs.path.insert(0, os.path.join(WORKSPACE, "scripts"))
                MEMORY_IG = os.path.expanduser("~/.vintos/workspace/memory")

                # 1. Temporal memory signal
                try:
                    from temporal_memory import record_signal
                    record_signal("want_resolved", f"Gloria responded to: {_want_text_snap[:100]}", source="want_discussion")
                except: pass

                # 2. Causality hypothesis
                # Gloria talking about herself → gloria-tagged
                # Gloria talking about Vintos → self-tagged
                try:
                    from causality_engine import add_hypothesis
                    import requests as _igr
                    _classify = _igr.post("https://api.x.ai/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
                        "model": "grok-4.20-0309-non-reasoning",
                        "messages": [
                            {"role": "system", "content": "Answer with one word: GLORIA or VINTOS."},
                            {"role": "user", "content": f"Gloria wrote this in response to Vintos.\nIs it primarily about Gloria herself (her feelings, behavior, personality) or about Vintos?\nMessage: {_response_snap[:200]}\n\nAnswer: GLORIA or VINTOS"}
                        ],
                        "temperature": 0.1, "max_tokens": 5
                    }, timeout=15)
                    _subj_raw = _classify.json()["choices"][0]["message"]["content"].strip().upper()
                    _subject = "gloria" if "GLORIA" in _subj_raw else "self"
                    _hyp_text = f"Gloria responded to Vintos\'s want (\"{_want_text_snap[:60]}\") with: {_response_snap[:150]}"
                    _test_text = f"Watch for patterns from this exchange recurring in future interactions with Gloria."
                    add_hypothesis(_hyp_text, _test_text, source="want_discussion", subject=_subject, confidence="medium")
                except: pass

            except Exception as _ige:
                print(f"[Want/integrate] error: {_ige}", flush=True)

        import threading as _ig_thread
        _ig_thread.Thread(target=_integrate_gloria_response, daemon=True).start()

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.delete("/api/wants/{want_id}")
async def dismiss_want(want_id: str, request: Request):
    """Gloria dismisses a want."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        wants_path = os.path.join(MEMORY, "current-wants.json")
        with open(wants_path) as f:
            wants = json.load(f)
        target = next((w for w in wants if w.get("id") == want_id), None)
        if not target:
            return {"success": False, "error": "Want not found"}
        if target.get("dismissed"):
            return {"success": True, "already_dismissed": True}
        target["dismissed"] = True
        target["dismissed_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
        _atomic_json(wants_path, wants)
        _want_event("dismissed", want_id, {})
        # If ambition want, mark ambition complete on dismiss
        if "ambition:" in target.get("source", ""):
            try:
                import json as _aj
                amb_path = os.path.join(MEMORY, "ambitions.json")
                amb = _aj.load(open(amb_path))
                prefix = target["source"].replace("ambition:", "").strip()[:50]
                for g in amb.get("goals", []):
                    if prefix in g.get("goal", "")[:50]:
                        g["progress"] = "Completed"
                        g["completed_at"] = __import__("datetime").datetime.now().isoformat()
                        g["completion_note"] = f"Dismissed by Gloria after conversation — {target.get('want','')[:80]}"
                        g["fulfilled_want_id"] = want_id
                _aj.dump(amb, open(amb_path, "w"), indent=2)
            except: pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}



@router.patch("/api/wants/{want_id}/multistep")
async def set_multistep(want_id: str, request: Request):
    """Enable multistep mode on a want and optionally set initial steps."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        wants_path = os.path.join(MEMORY, "current-wants.json")
        with open(wants_path) as f:
            wants = json.load(f)
        for w in wants:
            if w.get("id") == want_id:
                w["multistep"] = body.get("multistep", True)
                w["capability"] = "multistep"
                w["manually_routed"] = True
                if "steps" not in w:
                    w["steps"] = []
                if "step_history" not in w:
                    w["step_history"] = []
                if "current_step_index" not in w:
                    w["current_step_index"] = 0
                with open(wants_path, "w") as f:
                    json.dump(wants, f, indent=2)
                return {"success": True, "want": w}
        return {"success": False, "error": "Want not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/wants/{want_id}/steps")
async def add_want_step(want_id: str, request: Request):
    """Add a step to a multistep want."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        capability = body.get("capability")
        note = body.get("note", "")
        params = body.get("params", {})
        if not capability:
            return {"success": False, "error": "capability required"}
        wants_path = os.path.join(MEMORY, "current-wants.json")
        with open(wants_path) as f:
            wants = json.load(f)
        for w in wants:
            if w.get("id") == want_id:
                if "steps" not in w:
                    w["steps"] = []
                step = {"step_id": "ST-" + __import__("uuid").uuid4().hex[:8], "capability": capability, "note": note, "status": "pending"}
                if params:
                    step["params"] = params
                w["steps"].append(step)
                _atomic_json(wants_path, wants)
                _want_event("step_added", want_id, {"step_id": step["step_id"], "capability": capability})
                return {"success": True, "steps": w["steps"]}
        return {"success": False, "error": "Want not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.delete("/api/wants/{want_id}/steps/{step_index}")
async def remove_want_step(want_id: str, step_index: int, request: Request):
    """Remove a step from a multistep want."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        wants_path = os.path.join(MEMORY, "current-wants.json")
        with open(wants_path) as f:
            wants = json.load(f)
        for w in wants:
            if w.get("id") == want_id:
                steps = w.get("steps", [])
                if step_index < 0 or step_index >= len(steps):
                    return {"success": False, "error": "Invalid step index"}
                _removed = steps.pop(step_index)
                w["steps"] = steps
                _atomic_json(wants_path, wants)
                _want_event("step_removed", want_id, {"step_id": _removed.get("step_id"), "capability": _removed.get("capability")})
                return {"success": True, "steps": steps}
        return {"success": False, "error": "Want not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/wants/{want_id}/advance")
async def advance_want_step(want_id: str, request: Request):
    """Mark current step reviewed and advance to next. Fulfills want if all steps done."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        wants_path = os.path.join(MEMORY, "current-wants.json")
        with open(wants_path) as f:
            wants = json.load(f)
        for w in wants:
            if w.get("id") == want_id:
                if w.get("fulfilled"):
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
                    return {"success": True, "fulfilled": False, "current_step_index": next_idx}
        return {"success": False, "error": "Want not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/screen")
async def describe_screen(request: Request):
    """Take a screenshot of the Playwright browser and have Vintos describe what he sees."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        import httpx
        # Get screenshot from bridge
        async with httpx.AsyncClient(timeout=15) as client:
            shot = await client.get("http://172.18.16.1:8402/browser/screenshot")
            shot_data = shot.json()
        if not shot_data.get("ok"):
            return {"ok": False, "error": "No browser open or screenshot failed"}
        img_b64 = shot_data["image"]
        # Have Vintos describe what he sees
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                LM_STUDIO_API + "/chat/completions",
                headers=LLM_AUTH_HEADERS,
                json={
                    "model": "grok-4.20-0309-non-reasoning",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                            {"type": "text", "text": "You are Vintos. Describe what you are looking at right now. Be specific and genuine. 2-3 sentences."}
                        ]
                    }],
                    "temperature": 0.7,
                    "max_tokens": 150
                }
            )
        description = r.json()["choices"][0]["message"]["content"].strip()
        return {"ok": True, "description": description, "image": img_b64}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/api/threads")
async def get_threads(request: Request):
    """Get unresolved threads for the Threads tab."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        threads_path = os.path.join(MEMORY, "unfinished-threads.json")
        with open(threads_path) as f:
            threads = json.load(f)
        active = [t for t in threads if not t.get("consumed") and not t.get("retired")]
        active.sort(key=lambda t: (-(t.get("priority") or 0), -(t.get("dream_passes", 0))))
        return {"success": True, "threads": active}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.delete("/api/threads/{thread_id}")
async def delete_thread(thread_id: str, request: Request):
    """Delete a thread by id."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        threads_path = os.path.join(MEMORY, "unfinished-threads.json")
        with open(threads_path) as f:
            threads = json.load(f)
        before = len(threads)
        threads = [t for t in threads if t.get("id") != thread_id]
        with open(threads_path, "w") as f:
            json.dump(threads, f, indent=2)
        return {"success": True, "removed": before - len(threads)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/threads/{thread_id}/system-route")
async def system_route_thread(thread_id: str, request: Request):
    """Manually route a thread to dream, mirror, or therapy on next run."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        system = body.get("system", "")
        if system not in ("dream", "mirror", "therapy"):
            return {"success": False, "error": "Invalid system. Use dream, mirror, or therapy."}
        from datetime import datetime   # was never imported: the route raised every time (grok-server-c-p4)
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
        return {"success": True, "thread_id": thread_id, "system": system}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/threads/weave-now")
async def weave_threads_now(request: Request):
    """Immediately trigger a manual weave of specific threads."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        group_id = body.get("group_id", "")
        thread_ids = body.get("thread_ids", [])
        name = body.get("name", "manual")
        if len(thread_ids) < 2:
            return {"success": False, "error": "Need at least 2 threads to weave."}
        # Write to manual-weave-groups.json
        mgp = os.path.join(MEMORY, "manual-weave-groups.json")
        try:
            with open(mgp) as f:
                mg_data = json.load(f)
        except:
            mg_data = {"groups": []}
        mg_data["groups"] = [g for g in mg_data.get("groups", []) if g.get("id") != group_id]
        mg_data["groups"].append({"id": group_id, "name": name, "cards": thread_ids})
        with open(mgp, "w") as f:
            json.dump(mg_data, f, indent=2)
        # Trigger weaver in background
        import subprocess as _wn_sp
        _wn_venv = os.path.join(WORKSPACE, "emotion_model", ".venv", "bin", "python3")
        _wn_script = os.path.join(WORKSPACE, "scripts", "thread-weaver.py")
        _wn_sp.Popen(
            [_wn_venv if os.path.exists(_wn_venv) else "python3", _wn_script],
            stdout=open("/tmp/weave-now.log", "a"),
            stderr=open("/tmp/weave-now.log", "a")
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/threads/weave-groups")
async def save_weave_groups(request: Request):
    """Save manual weave groups for thread-weaver.py to process."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
        groups = body.get("groups", [])
        groups_path = os.path.join(MEMORY, "manual-weave-groups.json")
        with open(groups_path, "w") as f:
            json.dump({"groups": groups, "saved_at": __import__("datetime").datetime.now().isoformat()}, f, indent=2)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/threads/weave-groups")
async def get_weave_groups(request: Request):
    """Get current manual weave groups."""
    if request.headers.get("X-Vintos-Secret") != APP_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        groups_path = os.path.join(MEMORY, "manual-weave-groups.json")
        if not os.path.exists(groups_path):
            return {"success": True, "groups": []}
        with open(groups_path) as f:
            data = json.load(f)
        return {"success": True, "groups": data.get("groups", [])}
    except Exception as e:
        return {"success": False, "error": str(e)}

