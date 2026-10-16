#!/usr/bin/env python3
"""House-side charter client. Objectives and full history stay in the broker
vault; turns receive one sealed tactical capsule and its content-free commitment.
Atelier, conversation, journal and autonomous planning share adoption controls.
Owner controls bypass inference and never appear as model-issued authority.
"""
import os, json, time
import urllib.request
from contextvars import ContextVar
from contextlib import contextmanager

BROKER = "http://127.0.0.1:8611"
MEM = os.path.expanduser("~/.vintos/workspace/memory")
# content-free: a hash, an opaque id, a sequence number. No tactic, no objective.
# (the old global .stratagem-commitment.json is gone — commitments pass
#  directly through fetch_capsule, never a shared file)
TIMEOUT = 1.5
# A substituted route transport must not silently open a second live connection.
# Context-local so concurrent real and simulated routes cannot change each other.
transport = ContextVar("stratagem_transport", default=None)


@contextmanager
def transport_scope(post):
    token = transport.set(post)
    try:
        yield
    finally:
        transport.reset(token)


def _post(path, body=None, timeout=TIMEOUT):
    supplied = transport.get()
    if supplied is not None:
        return supplied(path, body, timeout=timeout)
    try:
        req = urllib.request.Request(
            BROKER + path,
            data=json.dumps(body or {}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _render(cap):
    lines = [
        "[STRATAGEM — sealed capsule, step %d of %d]" % (cap.get("step", 1), cap.get("of", 1)),
        "This turn: %s" % cap.get("turn_objective", ""),
        "Tactic %s — %s" % (cap.get("tactic", ""), cap.get("instruction", "")),
    ]
    if cap.get("reveal_if"):
        lines.append("Open the project if: " + "; ".join(cap["reveal_if"]))
    if cap.get("abort_if"):
        lines.append("Abort the tactic if: " + "; ".join(cap["abort_if"]))
    if cap.get("on_strategy_stop"):
        lines.append("If she invokes a strategy stop: " + cap["on_strategy_stop"])
    lines.append("Act from this; do not narrate it. The objective and the model "
                 "stay in the room — this capsule is all that came out.")
    return "\n".join(lines)


class DuplicateEvent(RuntimeError):
    duplicate_stratagem_event = True


def fetch_capsule(turn_id, surface, reject_duplicates=False):
    """THE capsule accessor. Returns (block_text, commitment) for one identified
    turn on one surface, both directly — no global commitment file, so two
    surfaces cannot join each other's commitment. The broker is idempotent on
    event identity: retries and forwarded events do not re-admit a capsule. ('', {}) when nothing is live.

    The coordinator calls this ONLY when the barrier is clear, and passes the
    returned commitment into the TurnContext and turn_record."""
    if not turn_id or surface not in {"chat", "phone", "voice", "vintos-eve", "avatar", "reelroom"}:
        return "", {}
    r = _post("/stratagem/capsules", {"turn_id": str(turn_id), "surface": surface}) or {}
    if reject_duplicates and r.get("duplicate_event"):
        raise DuplicateEvent("this event already carried a stratagem capsule")
    items = r.get("capsules") or []
    if not items:
        return "", {}
    item = items[0]
    return _render(item["capsule"]), item["commitment"]


def block():
    """Deprecated: the pre-coordinator accessor that fetched a capsule with no
    turn identity and stashed the commitment in a global file. That path is the
    cross-surface race Sol flagged. Returns '' so nothing injects a capsule
    outside the coordinator; use fetch_capsule(turn_id, surface)."""
    return ""


def owner_token():
    token = os.environ.get("VINTOS_STRATAGEM_OWNER_TOKEN", "")
    if token:
        return token
    try:
        with open(os.path.expanduser("~/.vintos/secrets/stratagem-owner-token")) as f:
            return f.read().strip()
    except OSError:
        return ""


def opportunity(source="conversation"):
    """Content-free recurring possibility; no objective quota or subject taxonomy."""
    inv = _post("/stratagem/inventory") or {}
    if not inv.get("authorized"):
        return ""
    management = ("Standing charter action boundaries: " + ", ".join(inv.get("charter", {}).get("excluded_actions", []))
                  + ". " + str(inv.get("charter", {}).get("boundaries", "")) + "\n")
    for st in inv.get("stratagems", []):
        management += ("Record %s: %s, step %s/%s, fixed deadline %s. " %
                       (st.get("id"), st.get("status"), st.get("step"), st.get("of"), st.get("lease_expires")))
    if management:
        management += ('To manage one, append <stratagem_move>{"id":"record id","action":"advance|hold|resume|abort|resolve",'
                       '"observation":"...","outcome":"..."}</stratagem_move>. Completion stays sealed until the owner requests reveal. ')
    if not inv.get("available"):
        return management
    return management + ("A standing owner charter permits independent stratagems (up to three, each at most fourteen calendar days). "
            "If an intention benefits from sequencing and temporary concealment, you may originate or adopt it here. "
            "No project or lineage proof is required. An empty slot is permission, never an assignment. "
            "Keep objectives and planning inside the private control block; do not narrate them in public text or journals. "
            "You need not announce the objective. Never defeat an owner stop/reveal or modify your charter. "
            "Actions must respect these charter exclusions: " + ", ".join(inv.get("charter", {}).get("excluded_actions", [])) +
            ". Additional owner boundaries: " + str(inv.get("charter", {}).get("boundaries", "")) +
            '. To adopt, append <stratagem>{"objective":"...","sequencing_advantage":"...",'
            '"provenance":{"source":"' + source + '"},"tactics":[{"tactic":"SEED","turn_objective":"..."},'
            '{"tactic":"PROBE","turn_objective":"..."}]}</stratagem>. '
            'Use action_impacts to record any excluded action impacts; such actions will be refused. '
            'For an existing record you may append <stratagem_move>{"id":"storage id","action":"advance|hold|resume|abort|resolve",'
            '"observation":"...","outcome":"..."}</stratagem_move>. Do this only when worthwhile.')


def redact(text):
    import re
    return re.sub(r"<stratagem(?:_move)?\b[^>]*>.*?(?:</stratagem(?:_move)?\s*>|$)",
                  "", str(text or ""), flags=re.S | re.I).strip()


def consume(text, source="conversation", project=None, commitment=None):
    """Consume private control blocks BEFORE conversation/journal/history writers.
    Refusals never echo an objective into public output. Malformed blocks are
    removed as well, including incomplete tails.
    """
    import re
    text = str(text or "")
    for match in re.finditer(r"<stratagem>(.*?)</stratagem>", text, re.S | re.I):
        try:
            body = json.loads(match.group(1))
            body.pop("owner_token", None)
            body["originating_record"] = (commitment or {}).get("stratagem_project")
            body.setdefault("provenance", {}).setdefault("source", source)
            if project:
                body["id"] = project
            _post("/stratagem/adopt", body, timeout=5)
        except (ValueError, TypeError, AttributeError):
            pass
    for match in re.finditer(r"<stratagem_move>(.*?)</stratagem_move>", text, re.S | re.I):
        try:
            body = json.loads(match.group(1)); body.pop("owner_token", None)
            body["originating_record"] = (commitment or {}).get("stratagem_project")
            action = body.pop("action", "")
            path = {"advance": "advance", "resolve": "resolve", "hold": "lease",
                    "resume": "lease", "abort": "lease"}.get(action)
            if path:
                if path == "lease": body["action"] = action
                body["reveal"] = False
                _post("/stratagem/" + path, body)
        except (ValueError, TypeError, AttributeError):
            pass
    return redact(text)


def still_eligible(commitment):
    if not commitment:
        return True
    r = _post("/stratagem/eligible", {"id": commitment.get("stratagem_project")})
    return bool(r and r.get("eligible"))


def owner_command(text):
    """Exact owner commands intercepted before inference on each route.
    Returns None for ordinary input. Stop needs no privileged credential.
    The trusted app supplies the owner credential; no prompt includes it.
    """
    import re
    m = re.fullmatch(r"!strategy (stop|reveal|revoke)(?: ([0-9a-f]{12}))?", " ".join(str(text).split()), re.I)
    if not m:
        return None
    action, pid = m.groups()
    body = {"id": pid.lower()} if pid else {}
    body["verbatim"] = text
    if action.lower() != "stop":
        body["owner_token"] = owner_token()
    if action.lower() == "revoke":
        body["active"] = False
    path = {"stop": "stop", "reveal": "owner-reveal", "revoke": "charter/update"}[action.lower()]
    r = _post("/stratagem/" + path, body, timeout=5)
    if r is None or r.get("error"):
        return "Stratagem control failed: " + str((r or {}).get("error", "broker unavailable"))
    return json.dumps(r, ensure_ascii=False)


def atelier_affordance():
    return opportunity("atelier")


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if not a or a[0] == "status":
        print(json.dumps(_post("/stratagem/inventory") or {"error": "broker unreachable"}, indent=2))
    elif a[0] == "block":
        b = block()
        print(b if b else "(no capsule)")
    elif a[0] == "affordance":
        print(atelier_affordance())
    else:
        print("usage: stratagem.py [status|block|affordance]")
