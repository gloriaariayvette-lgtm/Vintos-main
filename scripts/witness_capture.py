"""Request-local shadow capture with an explicit private scratch sink; no sends.

Provider hooks must explicitly label observed identity; configured names alone
are unknown. A handler selects the raw result before postprocessing, then binds
the receipt to its exact final return text. Persistence is a separate caller.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import uuid
from witness_receipts import digest, instant, receipt


class Capture:
    def __init__(self, turn_id, surface, started_at):
        if not isinstance(turn_id, str) or not turn_id or not isinstance(surface, str) or not surface:
            raise ValueError("capture needs an existing turn identity")
        self.turn_id, self.surface = turn_id, surface
        self.started_at = instant(started_at)
        self.context_id = "context:" + turn_id
        self._attempts = []
        self._selected = None
        self._closed = False
        self._scratch_root = None

    def observe(self, result):
        """Copy metadata only; never retain provider text, tool calls or reason text.

        Stage lists sometimes contain their enclosing result. Walk one level,
        deduplicate by object identity, and never recurse through that cycle.
        """
        if self._closed:
            raise ValueError("capture already finalized")
        if not isinstance(result, dict):
            raise ValueError("generation result must be an object")
        stages = result.get("stages", [])
        if not isinstance(stages, list):
            raise ValueError("stages must be a list")
        seen = set()
        for stage in list(stages) + [result]:
            if not isinstance(stage, dict) or id(stage) in seen:
                continue
            seen.add(id(stage))
            usable = stage.get("status") in ("valid", "truncated") and bool(stage.get("text"))
            evidence = stage.get("identity_evidence", "unknown")
            actual = stage.get("observed_model") if evidence in ("response_metadata", "runtime_receipt") else None
            self._attempts.append({
                "attempt_id": "attempt-%d" % (len(self._attempts) + 1),
                "outcome": "discarded" if usable else "failed",
                "requested_model": stage.get("requested_model"),
                "served_model": actual,
                "served_revision": stage.get("observed_revision") if actual else None,
                "identity_evidence": evidence if actual else "unknown",
                "_raw_sha256": digest(stage["text"]) if usable and isinstance(stage["text"], str) else None})

    def select(self, raw_reply):
        """Explicit handler selection after fallback/repeat decisions, before edits."""
        if self._closed:
            raise ValueError("capture already finalized")
        fingerprint = digest(raw_reply) if isinstance(raw_reply, str) and raw_reply else None
        matches = [a for a in self._attempts if fingerprint and a["_raw_sha256"] == fingerprint]
        # Equal text is not an attempt identity. In particular, an observed
        # retry may be discarded by the handler. Until it supplies an explicit
        # attempt ID, ambiguous matches must not guess the served generator.
        self._selected = matches[0]["attempt_id"] if len(matches) == 1 else None

    def finalize(self, final_text, finalized_at, transport="unknown"):
        """No delivery inference. Initial context ancestry is explicitly incomplete."""
        if self._closed:
            raise ValueError("capture already finalized")
        if transport not in ("unknown", "handed_to_framework", "failed"):
            raise ValueError("capture cannot attest delivery")
        if not isinstance(final_text, str) or instant(finalized_at) < self.started_at:
            raise ValueError("invalid finalization")
        self._closed = True
        attempts = [{k: v for k, v in a.items() if not k.startswith("_")} for a in self._attempts]
        for attempt in attempts:
            if attempt["attempt_id"] == self._selected:
                attempt["outcome"] = "selected"
        r = receipt(self.turn_id, self.surface, self.started_at, finalized_at, final_text,
                    self.context_id, attempts, self._selected, delivery="unknown")
        return deepcopy({"schema": "witness-capture-v1", "turn_id": self.turn_id,
                         "surface": self.surface, "witness_receipt": r,
                         "witness_final_text": final_text, "witness_final_sha256": digest(final_text),
                         "transport": transport, "attempt_history_complete": False,
                         "lineage": [{"id": self.context_id, "kind": "context", "at": self.started_at,
                                      "complete": False, "parents": []}],
                         "reply_node": {"id": "reply:" + self.turn_id, "kind": "reply",
                             "turn_id": self.turn_id, "at": instant(finalized_at), "complete": False,
                             "context_receipt_id": self.context_id, "parents": [self.context_id],
                             "influence": "unknown"}})


def _private_root(value):
    raw = Path(value).absolute()
    root = raw.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    if (raw != root or not root.is_dir() or root in (Path("/"), Path.home(), repo)
            or root in repo.parents or repo in root.parents
            or any(p in (".vintos", ".openclaw") for p in root.parts)
            or os.environ.get("SPARK_WORKSPACE") != str(root)
            or root.stat().st_mode & 0o077 or root.stat().st_uid != os.getuid()):
        raise ValueError("capture requires an explicit private scratch workspace")
    return root


def begin_shadow(turn_id, surface, started_at):
    """Disabled unless scratch and workspace explicitly name the same private root."""
    location = os.environ.get("JUDGES_CAPTURE_SCRATCH")
    if not location:
        return None
    root = _private_root(location)
    capture = Capture(turn_id, surface, started_at)
    capture._scratch_root = root
    return capture


def finish_shadow(capture, final_text, finalized_at, provenance=None, test_mode=False):
    """Write one private packet after the final guard, never to a live store.

    The handler still has no transport receipt: attempted return to the framework
    is recorded separately from delivery. Caller catches observation failures.
    """
    if capture is None:
        return False
    root = _private_root(capture._scratch_root)
    packet = capture.finalize(final_text, finalized_at, "handed_to_framework")
    from evidence_provenance import normalize
    p = normalize(provenance if isinstance(provenance, dict) else {
        "turn_id": capture.turn_id, "output_provenance": "unknown", "may_witness": False})
    packet["generation_provenance"] = p
    packet["content"] = final_text
    packet["role"] = "assistant"
    packet["test_mode"] = bool(test_mode)
    if p.get("output_provenance") == "stratagem_influenced":
        packet["reply_node"]["influence"] = "influenced"
        packet["reply_node"]["tactical"] = True
    # No replace/append: one new file, private permissions, directory descriptor
    # pinned while writing. A preexisting name or symlink can never be followed.
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        if info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError("scratch permissions changed")
        name = "capture-" + uuid.uuid4().hex + ".json"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "w") as f:
            json.dump(packet, f, allow_nan=False)
            f.write("\n")
    finally:
        os.close(directory)
    return True
