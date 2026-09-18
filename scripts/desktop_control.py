#!/usr/bin/env python3
"""A chat command may lend him the desktop; spending still requires her later receipt.

``/desktop-control to ...`` starts reversible work after his ordinary chat reply.  A
commerce task stops with a visible cart and writes one factual follow-up into the same
chat.  Only ``/desktop-control approve [id]`` grants one matching purchase click.  The
grant is consumed before the click, so an uncertain checkout is never retried.
"""
from __future__ import annotations

import fcntl, hashlib, json, os, re, subprocess, sys, time, uuid
from datetime import datetime
from pathlib import Path
from urllib import request as urlrequest

WORKSPACE = os.path.expanduser(os.environ.get("SPARK_WORKSPACE", "~/.vintos/workspace"))
MEMORY = os.path.join(WORKSPACE, "memory")
ROOT = os.path.join(MEMORY, "desktop-control")
STORE = os.path.join(ROOT, "requests.json")
EVENTS = os.path.join(ROOT, "events.jsonl")
LOCK = os.path.join(ROOT, ".lock")
CHAT = os.path.join(MEMORY, "chat-history.json")
CANON = os.path.join(MEMORY, "chat-canonical.jsonl")
CHAT_LOCK = os.path.join(MEMORY, ".chat-history.lock")
MODEL_URL = os.environ.get("VINTOS_DESKTOP_MODEL_URL", "http://100.79.177.103:1234/v1/chat/completions")
MODEL_NAME = os.environ.get("VINTOS_GEMMA_MODEL", "")
WATCH_SECONDS = int(os.environ.get("VINTOS_DESKTOP_WATCH_SECONDS", "1800"))

RUNNER = subprocess.Popen
HTTP = urlrequest.urlopen

COMMAND = re.compile(r"^\s*/desktop-control(?:\s+to)?\s+(.+?)\s*$", re.I | re.S)
COMMERCE = re.compile(r"\b(?:order|buy|purchase|checkout|cart|doordash|restaurant|delivery)\b", re.I)
APPROVE = re.compile(r"^approve(?:\s+([a-z0-9-]{4,40}))?$", re.I)


def _now(): return datetime.now().astimezone().isoformat(timespec="seconds")
def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
def _append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush(); os.fsync(f.fileno())
def _locked(path=LOCK):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path, "a+"); fcntl.flock(f, fcntl.LOCK_EX); return f
def _load():
    try:
        value = json.load(open(STORE, encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception: return {}
def _event(kind, rid="", **extra):
    row = {"at": _now(), "event": kind, "request_id": rid, "truth_status": "execution_receipt"}
    row.update(extra); _append(EVENTS, row); return row


def parse_command(text):
    m = COMMAND.match(text or "")
    if not m: return None
    body = " ".join(m.group(1).split())[:1800]
    if body.lower() in ("stop", "cancel", "abort"): return {"kind": "stop"}
    a = APPROVE.match(body)
    if a: return {"kind": "approve", "request_id": (a.group(1) or "").lower()}
    return {"kind": "start", "task": body, "commerce": bool(COMMERCE.search(body))}


def prompt_block(command):
    if not command: return ""
    if command["kind"] == "start":
        return ("[DESKTOP CONTROL — Gloria explicitly invoked it]\n"
                "Reply to her normally, in your own voice, before the work begins. Say what you are about "
                "to do, but do not claim it is already complete and do not emit [DESKTOP:] tags. The house "
                "will start the task after this delivered reply and will let you double-text the observed outcome.")
    if command["kind"] == "approve":
        return ("[DESKTOP CONTROL APPROVAL]\nGloria is explicitly approving the newest prepared desktop "
                "purchase named by this command. A one-use receipt will decide whether checkout may proceed. "
                "Reply to her normally; do not claim the order has completed before the desktop confirms it.")
    return "[DESKTOP CONTROL]\nShe asked you to stop the current desktop work. Acknowledge her normally."


def _wrapped_task(task, commerce=False):
    base = ("Gloria asked from Vintos chat: %s\nWork through the ordinary visible desktop and verify the result. "
            "Never invent a page state." % task)
    if not commerce: return base
    return base + ("\nThis is PREPARATION ONLY. Choose one restaurant and one or two requested items, add them "
        "to the cart, then stop before every Place order, Confirm order, Pay now, Buy now, or equivalent "
        "purchase control. Do not purchase. Finish only when the page visibly provides the restaurant, "
        "exact selected items, delivery estimate, and complete order total. Put all four facts verbatim in "
        "the done summary so Gloria can approve them from chat.")


def _spawn_watch(rid):
    log = open(os.path.join(ROOT, "watcher.log"), "ab", buffering=0)
    try:
        RUNNER([sys.executable, str(Path(__file__).resolve()), "watch", "--request-id", rid],
               stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
               start_new_session=True, close_fds=True)
    finally: log.close()


def _latest_open(db, requested=""):
    rows = [r for r in db.values() if r.get("state") == "awaiting_approval"]
    if requested:
        rows = [r for r in rows if r.get("id") == requested or r.get("id", "").startswith(requested)]
    return sorted(rows, key=lambda r: r.get("created_at", ""))[-1] if rows else None


def start_from_chat(user_text, reply="", surface="chat/full", turn_id=""):
    command = parse_command(user_text)
    if not command: return {"state": "not_requested"}
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import desktop_agent as da
    if command["kind"] == "stop":
        state = da.request_stop(); _event("stop_requested", job_id=state.get("job_id", "")); return state
    if command["kind"] == "approve":
        lock = _locked()
        try:
            db = _load(); rec = _latest_open(db, command.get("request_id", ""))
            if not rec: return {"state": "refused", "reason": "no prepared desktop purchase is awaiting approval"}
            rec["state"] = "approval_granted"; rec["approved_at"] = _now(); rec["approval_consumed"] = False
            db[rec["id"]] = rec; _atomic(STORE, db)
        finally: lock.close()
        task = ("Gloria explicitly approved desktop proposal %s. Re-read the current cart. It must still show "
                "the same restaurant, every selected item, and total recorded in this receipt: %s. If any are "
                "absent or changed, stop without purchasing. If they match, activate the final purchase control "
                "exactly once. Never retry it. Finish only when the page visibly confirms the order or gives an "
                "order number; if the outcome is unclear, report it as unknown." %
                (rec["id"], json.dumps(rec.get("quote") or {}, ensure_ascii=False)))
        out = da.start_task(task, extra_env={"VINTOS_DESKTOP_APPROVAL_ID": rec["id"]})
        _bind_job(rec["id"], out, phase="checkout")
        if out.get("accepted"): _spawn_watch(rec["id"])
        else: settle(rec["id"], terminal=out.get("state") or {"status":"failed", "reason":out.get("reason", "did not start")})
        return out
    rid = "desk-" + uuid.uuid4().hex[:10]
    out = da.start_task(_wrapped_task(command["task"], command["commerce"]))
    rec = {"id": rid, "state": "working" if out.get("accepted") else "failed",
           "created_at": _now(), "surface": surface, "turn_id": turn_id, "task": command["task"],
           "commerce": command["commerce"], "job_id": out.get("job_id", ""),
           "initial_reply": str(reply)[:1000], "truth_status": "desktop_job_started_not_completed"}
    lock = _locked()
    try: db = _load(); db[rid] = rec; _atomic(STORE, db)
    finally: lock.close()
    _event("started", rid, job_id=rec["job_id"], commerce=rec["commerce"], accepted=bool(out.get("accepted")))
    if out.get("accepted"): _spawn_watch(rid)
    else: settle(rid, terminal=out.get("state") or {"status":"failed", "reason":out.get("reason", "did not start")})
    return {**out, "request_id": rid}


def _bind_job(rid, outcome, phase):
    lock = _locked()
    try:
        db = _load(); rec = db[rid]; rec.update({"state": "checking_out" if outcome.get("accepted") else "failed",
            "job_id": outcome.get("job_id", ""), "phase": phase, "truth_status": "approved_one_attempt_not_completed"})
        db[rid] = rec; _atomic(STORE, db)
    finally: lock.close()
    _event("checkout_started", rid, job_id=outcome.get("job_id", ""), accepted=bool(outcome.get("accepted")))


def _json_object(text):
    text = (text or "").replace("```json", "").replace("```", "")
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a: raise ValueError("no JSON object")
    return json.loads(text[a:b + 1])


def _model(prompt, max_tokens=300):
    body = {"messages": [{"role":"system", "content":"Return only the requested JSON. Never invent missing facts."},
                          {"role":"user", "content":prompt}], "max_tokens":max_tokens, "temperature":0.2}
    if MODEL_NAME: body["model"] = MODEL_NAME
    req = urlrequest.Request(MODEL_URL, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    raw = json.loads(HTTP(req, timeout=45).read().decode())
    return raw["choices"][0]["message"]["content"]


def _page_text():
    try:
        import browser_winpy
        if not browser_winpy.available(): return ""
        value = browser_winpy.EdgeBrowser().text()
        return str(value.get("text") or "")[:24000]
    except Exception: return ""


def _quote(reason, page):
    prompt = ("Extract the prepared delivery cart. Return JSON exactly as "
              "{\"restaurant\":\"\",\"items\":[\"\"],\"eta\":\"\",\"total\":\"\",\"note\":\"\"}. "
              "Use empty values when absent. The total must include currency.\nDESKTOP SUMMARY:\n%s\nPAGE TEXT:\n%s" %
              (reason[:1200], page[:18000]))
    try: q = _json_object(_model(prompt, 260))
    except Exception: q = {}
    clean = {"restaurant": str(q.get("restaurant") or "")[:160],
             "items": [str(x)[:180] for x in (q.get("items") or [])[:6] if str(x).strip()],
             "eta": str(q.get("eta") or "")[:120], "total": str(q.get("total") or "")[:80],
             "note": str(q.get("note") or "")[:240]}
    return clean


def _followup(rec, terminal, page=""):
    status, reason = str(terminal.get("status") or "unknown"), str(terminal.get("reason") or "")[:1200]
    if rec.get("phase") == "checkout":
        if status == "completed": return "Done — the desktop shows the order was submitted. " + reason
        return "I couldn't confirm checkout, so I did not retry it. The outcome is %s: %s" % (status, reason or "no confirmation appeared")
    if rec.get("commerce") and status == "completed":
        q = _quote(reason, page)
        if q["restaurant"] and q["items"] and q["eta"] and q["total"]:
            rec["quote"] = q; rec["quote_fingerprint"] = hashlib.sha256(json.dumps(q, sort_keys=True).encode()).hexdigest()
            rec["state"] = "awaiting_approval"; rec["truth_status"] = "visible_cart_quoted_not_approved"
            return ("I picked %s: %s. Delivery: %s. Order total: %s. %s\n\n"
                    "The cart is ready, but I have not placed the order. Reply `/desktop-control approve %s` "
                    "and I can make the one checkout attempt." %
                    (q["restaurant"], ", ".join(q["items"]), q["eta"], q["total"], q["note"], rec["id"]))
        rec["state"] = "needs_review"; rec["truth_status"] = "cart_may_exist_quote_incomplete"
        return "I reached the cart but couldn't verify every approval fact, so I stopped without ordering. " + reason
    rec["state"] = "completed" if status == "completed" else status
    rec["truth_status"] = "desktop_completion_report" if status == "completed" else "typed_desktop_failure"
    return ("Desktop work finished: " if status == "completed" else "Desktop work stopped: ") + (reason or status)


def _write_chat(text, rid):
    row = {"role":"assistant", "content":str(text)[:4000], "timestamp":_now(),
           "source":"desktop-control", "desktop_request_id":rid}
    lock = _locked(CHAT_LOCK)
    try:
        try: history = json.load(open(CHAT, encoding="utf-8"))
        except Exception: history = []
        if not any(x.get("desktop_request_id") == rid and x.get("content") == row["content"] for x in history if isinstance(x, dict)):
            history.append(row); _atomic(CHAT, history[-50:]); _append(CANON, dict(row, surface="chat/full"))
    finally: lock.close()
    return row


def settle(rid, terminal=None):
    lock = _locked()
    try: db = _load(); rec = db.get(rid)
    finally: lock.close()
    if not rec: return {"state":"gone"}
    if rec.get("followup_at"): return rec
    if terminal is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import desktop_agent as da
        terminal = da.read_state()
    text = _followup(rec, terminal, _page_text())
    _write_chat(text, rid)
    rec["followup_at"] = _now(); rec["desktop_status"] = terminal.get("status"); rec["desktop_reason"] = str(terminal.get("reason") or "")[:1200]
    lock = _locked()
    try: db = _load(); db[rid] = rec; _atomic(STORE, db)
    finally: lock.close()
    _event("followup_written", rid, state=rec.get("state"), desktop_status=rec.get("desktop_status"))
    return rec


def watch(rid):
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import desktop_agent as da
    started = time.time(); wanted = (_load().get(rid) or {}).get("job_id", "")
    while time.time() - started < WATCH_SECONDS:
        state = da.read_state()
        if state.get("job_id") == wanted and state.get("status") not in ("starting", "running", "stopping"):
            settle(rid, state); return 0
        time.sleep(2)
    settle(rid, {"status":"timed_out", "reason":"desktop task did not finish before its watcher expired"}); return 1


def authorize_purchase_click(rid, label, page_text):
    """Consume one approval before an irreversible click; current page must still carry the quote."""
    lock = _locked()
    try:
        db = _load(); rec = db.get(str(rid) or "")
        if not rec or rec.get("state") not in ("approval_granted", "checking_out") or rec.get("approval_consumed"):
            return False, "no unused chat approval matches this purchase"
        q = rec.get("quote") or {}; hay = " ".join(str(page_text or "").lower().split())
        required = [q.get("restaurant"), q.get("total")] + list(q.get("items") or [])
        missing = [str(x) for x in required if str(x).strip() and " ".join(str(x).lower().split()) not in hay]
        if missing: return False, "the current page no longer shows the approved quote: " + ", ".join(missing[:4])
        rec["approval_consumed"] = True; rec["approval_consumed_at"] = _now(); rec["approval_control"] = str(label)[:100]
        rec["state"] = "approval_consumed_outcome_unknown"; db[rec["id"]] = rec; _atomic(STORE, db)
    finally: lock.close()
    _event("purchase_click_authorized", rid, control=str(label)[:100])
    return True, "one quote-bound click authorized"


def main():
    import argparse
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd", required=True)
    w=sub.add_parser("watch"); w.add_argument("--request-id", required=True)
    a=p.parse_args(); return watch(a.request_id) if a.cmd == "watch" else 2


if __name__ == "__main__": raise SystemExit(main())
