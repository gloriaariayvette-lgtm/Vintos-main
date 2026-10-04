#!/usr/bin/env python3
"""A call his Lab may not make alone: he asks, Gloria sees the exact call, and only her Accept runs it
(Gloria, 2026-10-04: "how do we give him a way to be watched?").

Withheld used to mean unreachable, which is not the same as watched. Now:

  1. His Lab names a tool it may not run itself (claude_connector_catalog.may_propose). It is NOT called.
  2. It is written down here with the exact arguments, why he wants it, and the price from the free estimate.
  3. It goes to her Forge page as a card: the tool, what it would do, what it costs. Accept or Deny.
  4. Her Accept runs it once, through the ordinary connector gateway, and the result returns to his Lab as
     provenance with its receipt. Her Deny is recorded and goes on the line of inquiry, so he learns the answer
     rather than asking again next week.

Watched means she sees the call before it happens. The card shows what would be sent, not a summary of it.
"""
from __future__ import annotations
import json
import re
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
LAB = os.path.join(WS, "memory", "chemistry-lab")
STORE = os.path.join(LAB, "asked-calls.json")
PER_DAY = 3             # calls he may ask her for in a day: her page is not a queue to flood
# The push to her phone: the price, Yes and No. Her Forge page runs as another user and cannot read this store at
# all, so a card there reached her never (Gloria, 2026-10-04: "I HAVE NO CARD NO NOTIFICATIONS NO APPROVAL LINK").
# Each card carries its own one-use token, so the buttons need no app secret in a notification anyone could read.
NTFY = os.environ.get("VINTOS_NTFY_URL", "https://ntfy.sh/vintos-gloria-9kx")
AEGIS = os.environ.get("VINTOS_AEGIS_URL", "http://100.72.225.119:8500")
ARGS_SHOWN = 1200
OPEN = ("asked",)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load():
    try:
        with open(STORE) as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def save(rows):
    os.makedirs(LAB, exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows[-200:], f, indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def get(aid):
    return next((r for r in load() if r["id"] == aid), None)


def asked_today(rows=None, day=None):
    day = day or _now()[:10]
    return [r for r in (rows if rows is not None else load()) if str(r.get("at", ""))[:10] == day]


def _same(a, b):
    return (a.get("plugin"), a.get("tool"), json.dumps(a.get("arguments"), sort_keys=True)) == \
           (b.get("plugin"), b.get("tool"), json.dumps(b.get("arguments"), sort_keys=True))


def propose(plugin, tool, arguments, why, *, surface="lab", estimate="", line_id="", question=""):
    """He asks her for one call. (row, "") or (None, why not)."""
    import claude_connector_catalog as catalog
    if not catalog.may_propose(plugin, surface, tool):
        return None, "that tool is not one he may ask for"
    if not isinstance(arguments, dict):
        return None, "arguments must be an object"
    if not str(why or "").strip():
        return None, "say why it is worth it"
    rows = load()
    want = {"plugin": plugin, "tool": tool, "arguments": arguments}
    same = next((r for r in rows if _same(r, want) and r["state"] in ("asked", "accepted", "ran")), None)
    if same:
        return None, "already asked (%s, %s)" % (same["id"], same["state"])
    denied = next((r for r in rows if _same(r, want) and r["state"] == "denied"), None)
    if denied:
        return None, "she already said no to this one: %s" % (denied.get("note") or "no reason given")
    if len(asked_today(rows)) >= PER_DAY:
        return None, "the %d calls he may ask for today are used" % PER_DAY
    row = {"id": "A-" + uuid.uuid4().hex[:6], "token": uuid.uuid4().hex, "at": _now(),
           "surface": surface, "plugin": plugin, "tool": tool,
           "generative": bool(__import__("claude_connector_catalog").is_generative(plugin, tool)),
           "arguments": arguments, "why": str(why)[:800], "estimate": str(estimate or "")[:400],
           "line_id": line_id or "", "question": str(question or "")[:400], "state": "asked"}
    rows.append(row); save(rows)
    notify(row)
    return row, ""


def price(row):
    """The dollar figure from the free estimate, as she needs to read it: "$0.03", or what the estimate said."""
    est = str(row.get("estimate") or "")
    m = re.search(r"(?:estimated_cost_usd|cost_usd|estimate|price)[^0-9]{0,12}([0-9]+\.[0-9]+|[0-9]+)", est, re.I) \
        or re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", est)
    if m:
        return "$%.2f" % float(m.group(1)) if float(m.group(1)) >= 0.01 else "$%s" % m.group(1)
    return "no price was estimated; accepting may spend money"


def notify(row, send=None):
    """One push to her phone: what it is, what it costs, Yes and No. Never raises."""
    try:
        url = "%s/api/lab/asks/%s/decide?t=%s&state=" % (AEGIS.rstrip("/"), row["id"], row["token"])
        body = "%s.%s\n%s\n%s" % (row["plugin"], row["tool"], price(row), str(row.get("why") or "")[:300])
        if row.get("generative"):
            body = "MAKES something new (not a tested molecule).\n" + body
        headers = {"Title": "Run this for him? %s" % price(row), "Priority": "high", "Tags": "test_tube",
                   "Actions": "http, Yes - run it, %saccepted, method=POST, clear=true; "
                              "http, No, %sdenied, method=POST, clear=true" % (url, url)}
        req = urllib.request.Request(NTFY, data=body.encode("utf-8"), headers=headers)
        (send or urllib.request.urlopen)(req, timeout=20)
        return True
    except Exception:
        return False


def _field(blob, *names):
    # A connector hands its record back as JSON inside JSON, so the fields arrive escaped (\"status\": \"pending\").
    blob = str(blob or "").replace('\\"', '"').replace("\\n", "\n")
    for n in names:
        m = re.search(r'"%s"\s*:\s*"?([^",}\n]+)' % n, blob)
        if m and m.group(1).strip() not in ("null", ""):
            return m.group(1).strip()
    return ""


def in_words(row, blob=""):
    """What a result means, in her words. A connector answers with its whole JSON record, and the push read as a
    wall of it (Gloria, 2026-10-04: "What is this notification?")."""
    blob = str(blob or row.get("summary") or "")
    if not blob.strip():
        return "it ran"
    state = _field(blob, "status", "state").lower()
    job = _field(blob, "id", "prediction_id", "job_id")
    said = {"pending": "queued, not started yet", "queued": "queued", "running": "running now",
            "succeeded": "done", "completed": "done", "complete": "done", "success": "done",
            "failed": "it failed", "error": "it failed", "cancelled": "cancelled"}.get(state, state or "")
    what = "%s.%s" % (row.get("plugin", ""), row.get("tool", ""))
    if not said:
        return (blob[:300] + ("…" if len(blob) > 300 else ""))
    line = "%s: %s." % (what, said)
    if said in ("queued, not started yet", "queued", "running now"):
        line += " You will get its result here when it finishes."
    err = _field(blob, "error")
    if err and said == "it failed":
        line += " " + err[:160]
    return line + ((" (job %s)" % job) if job else "")


def pending(rows=None):
    """Runs she accepted that are started but not finished."""
    return [r for r in (rows if rows is not None else load())
            if r.get("state") == "ran" and not r.get("finished")
            and _field(str(r.get("summary") or ""), "status", "state").lower() in ("pending", "queued", "running")]


def check_pending(call=None, limit=2, send=None):
    """Ask the connector, for free, whether an accepted run has finished; push its result once it has. Log lines."""
    rows, lines, asked = load(), [], 0
    for row in rows:
        if row not in pending(rows) or asked >= limit:
            continue
        job = _field(str(row.get("summary") or ""), "id", "prediction_id", "job_id")
        if not job:
            continue
        asked += 1
        try:
            if call is None:
                import claude_connector_gateway
                call = claude_connector_gateway.call
            tool = "boltz_get_structure_and_binding_prediction" if "structure_and_binding" in row["tool"] else "boltz_get_job_status"
            out = call(row.get("surface") or "lab", row["plugin"], tool, {"id": job},
                       "checking a run Gloria accepted; this call is free")
            blob = str(out.get("summary") or "")
            state = _field(blob, "status", "state").lower()
            if state in ("pending", "queued", "running", ""):
                lines.append("%s still %s" % (row["id"], state or "unknown")); continue
            row.update(finished=_now(), result=blob[:4000], result_state=state)
            told(row["id"], in_words(row, blob), send=send)
            _tell_the_line(row, "It finished: " + in_words(row, blob)[:400])
            lines.append("%s %s" % (row["id"], state))
        except Exception as exc:
            lines.append("%s could not be checked: %s" % (row["id"], str(exc)[:120]))
    save(rows)
    return lines


def told(aid, text, send=None):
    """What came of a call she accepted, to her phone."""
    try:
        req = urllib.request.Request(NTFY, data=str(text)[:800].encode("utf-8"),
                                     headers={"Title": "His run %s" % aid, "Tags": "test_tube"})
        (send or urllib.request.urlopen)(req, timeout=20)
        return True
    except Exception:
        return False


def decide_with_token(aid, token, state):
    """Her Yes or No from the notification. The token is this card's own, used once."""
    row = get(aid)
    if not row or not row.get("token") or token != row["token"]:
        return None, "that is not this call's button"
    if row["state"] not in OPEN:
        return None, "already %s" % row["state"]
    done = decided(aid, "accepted" if state == "accepted" else "denied", "from her phone")
    return done, ""


def _arguments_shown(row):
    """What would actually be sent, as she would read it. Bounded, never summarised away."""
    text = json.dumps(row.get("arguments") or {}, indent=1, sort_keys=True, ensure_ascii=False)
    return text if len(text) <= ARGS_SHOWN else text[:ARGS_SHOWN] + "\n… (%d more characters)" % (len(text) - ARGS_SHOWN)


def cards():
    """One card per call waiting on her, for her Forge page."""
    out = []
    for r in load():
        if r["state"] not in OPEN:
            continue
        details = ["He would send exactly this:", _arguments_shown(r)]
        try:
            import claude_connector_catalog as catalog
            if catalog.is_generative(r["plugin"], r["tool"]):
                details.insert(0, "This one MAKES something new (a binder, a molecule, a peptide) rather than "
                                  "predicting or ranking what he already has. What comes back is a computational "
                                  "design: not a tested molecule, nothing about whether it works or is safe, and "
                                  "never a step toward making it for real.")
        except Exception:
            pass
        if r.get("question"):
            details.insert(0, "The question it serves: " + r["question"])
        if r.get("line_id"):
            details.insert(0, "On his line of inquiry " + r["line_id"])
        out.append({"id": "ask:" + r["id"], "kind": "ask", "ref": r["id"],
                    "title": "Run %s.%s for him?" % (r["plugin"], r["tool"]),
                    "what": r["why"],
                    "cost": r.get("estimate") or "No price was estimated; accepting may spend money on this account.",
                    "details": details})
    return out


def decided(aid, state, note=""):
    """Her verdict from the page, written down. The row, or None."""
    rows = load()
    row = next((r for r in rows if r["id"] == aid and r["state"] in OPEN), None)
    if not row:
        return None
    row.update(state="accepted" if state == "accepted" else "denied", note=str(note or "")[:600], decided_at=_now())
    save(rows)
    if row["state"] == "denied":
        _tell_the_line(row, "Gloria said no to %s.%s: %s" % (row["plugin"], row["tool"],
                                                             row.get("note") or "no reason given"))
    return row


def _tell_the_line(row, text):
    """What she decided goes on the line of inquiry it came from, so he does not ask the same thing again."""
    if not row.get("line_id"):
        return
    try:
        import lab_lines
        lab_lines.record_step(row["line_id"], {"question": row.get("question") or row["tool"],
                                               "source": "asked Gloria", "result": text[:700], "answered": ""})
    except Exception:
        pass


def run_accepted(call=None, limit=2):
    """Run what she accepted, once each, through the ordinary gateway. Log lines."""
    rows, lines, ran = load(), [], 0
    for row in rows:
        if row["state"] != "accepted" or ran >= limit:
            continue
        ran += 1
        try:
            if call is None:
                # through the gateway's accepted door: the paid tools are outside its ordinary policy on purpose,
                # so the ordinary call refused every Accept as "outside policy" (found 2026-10-04)
                import claude_connector_gateway
                out = claude_connector_gateway.call_accepted(row)
            else:
                out = call(row["surface"], row["plugin"], row["tool"], row["arguments"],
                           "Gloria accepted this on her Forge page: " + row["why"][:400])
            row.update(state="ran", ran_at=_now(), receipt_id=(out.get("receipt") or {}).get("receipt_id"),
                       summary=str(out.get("summary") or "")[:800])
            lines.append("ran %s (%s.%s)" % (row["id"], row["plugin"], row["tool"]))
            _tell_the_line(row, "Gloria accepted it and it ran: " + (row.get("summary") or "")[:500])
        except Exception as exc:
            row.update(state="failed", ran_at=_now(), error=str(exc)[:400])
            lines.append("%s did not run: %s" % (row["id"], str(exc)[:160]))
            _tell_the_line(row, "She accepted it but it did not run: " + str(exc)[:300])
    save(rows)
    return lines


# An ask from #vintos-dot (Gloria, 2026-10-04: "Dot needs to be able to do this!"). Dot's own review would only take
# her yes typed into a session she has no way to open; this puts the exact call on her Forge page instead.
#   ASK: boltz.boltz_start_structure_and_binding {"input": {...}} | why it is worth it
ASK = re.compile(r"^\s*ASK:\s*([\w-]+)\.([\w-]+)\s*(\{.*?\})?\s*(?:\|\s*(.+?))?\s*$", re.M)


def _estimate(plugin, tool, arguments, gateway=None):
    """The free price for a paid Boltz start, from its own estimate tool when he may run it; "" when there is none."""
    est = tool.replace("_start_", "_estimate_", 1)
    try:
        import claude_connector_catalog as catalog
        if est == tool or est not in (catalog.PLUGINS.get(plugin) or {}).get("read", ()):
            return ""
        if gateway is None:
            import claude_connector_gateway as gateway
        out = gateway.call("lab", plugin, est, arguments, "the free price for a card on Gloria's Forge page")
        return "Free estimate: " + str(out.get("summary") or "")[:300]
    except Exception as exc:
        return ""


def from_slack(text, by="vintos", gateway=None):
    """Every ASK line in a message, onto her Forge page. [(ok, the line to show)]."""
    out = []
    for m in ASK.finditer(text or ""):
        plugin, tool, raw, why = m.group(1), m.group(2), m.group(3) or "{}", (m.group(4) or "").strip()
        try:
            arguments = json.loads(raw)
        except ValueError as exc:
            out.append((False, "\U0001F9FE Not asked: the arguments are not JSON (%s)" % exc)); continue
        row, why_not = propose(plugin, tool, arguments, why or ("asked for in #vintos-dot by " + by),
                               estimate=_estimate(plugin, tool, arguments, gateway))
        out.append((bool(row), ("\U0001F9FE On Gloria's Forge page for her Accept (%s): %s.%s%s" % (
            row["id"], plugin, tool, (" — " + row["estimate"]) if row.get("estimate") else "")) if row
            else "\U0001F9FE Not asked (%s): %s.%s" % (why_not, plugin, tool)))
    return out


def block(limit=4):
    """What he has asked her for, for his Lab's context: so he knows what is waiting and what she answered."""
    rows = [r for r in load() if r["state"] != "ran"][-limit:]
    if not rows:
        return ""
    how = {"asked": "waiting on her", "accepted": "she said yes; it runs on the next pass",
           "denied": "she said no", "failed": "she said yes but it did not run"}
    return ("[CALLS YOU ASKED GLORIA FOR — you may not make these yourself; she decides on her Forge page]\n"
            + "\n".join("- %s %s.%s: %s — %s%s" % (r["id"], r["plugin"], r["tool"], r["why"][:160],
                                                   how.get(r["state"], r["state"]),
                                                   (" (" + r["note"][:120] + ")") if r.get("note") else "")
                        for r in rows)
            + "\nDo not ask again for one she refused.")


if __name__ == "__main__":
    print(block(50) or "nothing asked")
