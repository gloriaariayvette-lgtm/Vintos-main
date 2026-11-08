"""Request-local shadow capture with an explicit private scratch sink; no sends.

Provider hooks must explicitly label observed identity; configured names alone
are unknown. A handler selects the raw result before postprocessing, then binds
the receipt to its exact final return text. Persistence is a separate caller.
"""
from copy import deepcopy
import json
import os
import sys
from pathlib import Path
import uuid
from witness_receipts import digest, instant, receipt, source_node
_UNSPECIFIED = object()


def _fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


class Invocation:
    """One handler invocation, including its returned root and observed stages.

    This is not a wire-request or complete provider-retry ledger. In particular,
    an unobserved internal fallback stays unobserved, not an invented attempt.
    """
    def __init__(self, capture, request_id):
        self.capture, self.request_id = capture, request_id
        self.returned_attempt_id = None
        self.observed = False
        self.clock = None

    def observe(self, result):
        if self.observed:
            self.returned_attempt_id = None
            raise ValueError("one result per invocation")
        self.observed = True
        self.returned_attempt_id = self.capture.observe(result, self.request_id,
                                                       self.clock() if self.clock else None)


def prepare_shadow(capture, system, messages, params, reason, at):
    """Observation failure never prevents routing; no endpoint/auth enters a receipt."""
    if capture is None:
        return None, {}
    try:
        invocation = capture.request(system, messages, params, reason, at() if callable(at) else at)
        invocation.clock = at if callable(at) else None
        return invocation, {"observer": invocation.observe}
    except Exception:
        return None, {}


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
        self._requests = []
        self._nodes = []
        self._input_bindings = []
        self._finalization_nodes = []

    def bind_counterpart_input(self, original_text, message, slot):
        """Bind an explicitly marked original fragment to one exact input version.

        The caller must supply the authenticated request's original_text field,
        never a fallback to composed message text. Locate it only within the
        supplied current-message slot; role or a matching historical quote does
        not establish origin. Ambiguous/missing spans establish nothing.
        """
        if self._closed or self._requests or self._input_bindings:
            raise ValueError("bind current input once, before routing")
        if not isinstance(original_text, str) or not original_text.strip():
            return False
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            return False
        if not isinstance(message, dict) or message.get("role") != "user":
            return False
        content = message.get("content")
        if isinstance(content, str):
            parts = [(None, content)]
        elif isinstance(content, list):
            parts = [(i, part["text"]) for i, part in enumerate(content)
                     if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)]
        else:
            return False
        spans = []
        for index, text in parts:
            start = text.find(original_text)
            if start < 0:
                continue
            if text.find(original_text, start + 1) >= 0:
                return False
            spans.append({"part": index, "start": start, "end": start + len(original_text),
                          "unit": "unicode_codepoints"})
        if len(spans) != 1:
            return False
        node = source_node(self.context_id + ":counterpart", "counterpart_verbatim",
                           self.started_at, original_text)
        binding = {"source_id": node["id"], "slot": slot, "message_sha256": _fingerprint(message),
                   "span": spans[0], "basis": "explicit_original_text"}
        self._nodes.append(node)
        self._input_bindings.append(binding)
        return True

    def context_selection(self, value):
        """Retain the existing offered-input receipt, never claim offers were admitted."""
        if self._closed or not isinstance(value, dict):
            raise ValueError("invalid selection")
        at = instant(value["ts"])
        if at > self.started_at or not isinstance(value.get("selection_id"), str):
            raise ValueError("invalid selection clock or identity")
        offers = value.get("offers")
        if not isinstance(offers, dict):
            raise ValueError("invalid offers")
        observed = []
        for name, offer in sorted(offers.items()):
            if not isinstance(name, str) or not isinstance(offer, dict):
                raise ValueError("invalid offer")
            observed.append({"organ": name, "state": offer.get("state", "unknown"),
                             "influence_id": offer.get("influence_id"), "source_hash": offer.get("source_hash")})
        self._nodes.append({"id": self.context_id + ":selection", "kind": "context", "at": at,
                            "complete": False, "parents": [], "observation": "context_selection",
                            "scope": "offers_not_admission", "selection_id": value["selection_id"],
                            "selection_version": value.get("selection_version"), "offers": deepcopy(observed)})

    def request(self, system, messages, params, reason, at):
        """Bind exact handler arguments and their ordered dependencies before routing.

        A digest says what was read, not where it originated. All assembled
        prompt/history entries remain unknown until their producers supply
        complete ancestry. Even role=user is not evidence of external origin.
        """
        at = instant(at)
        if self._closed or self._finalization_nodes or at < max([self.started_at] + [n["at"] for n in self._nodes]):
            raise ValueError("invalid request lifecycle")
        if not isinstance(system, str) or not isinstance(messages, list) or not isinstance(params, dict):
            raise ValueError("invalid handler request")
        request_id = "request-%d" % (len(self._requests) + 1)
        node_id = self.context_id + ":" + request_id
        body = {"system": system, "messages": messages, "params": params, "reason": reason}
        fingerprint = _fingerprint(body)
        inputs = [{"role": "system", "content": system}] + messages
        nodes, parents = [], []
        for index, item in enumerate(inputs):
            key = node_id + ":input-%d" % index
            parents.append(key)
            version = _fingerprint(item)
            bindings = [b for b in self._input_bindings if index == b["slot"] + 1
                        and version == b["message_sha256"]]
            nodes.append({"id": key, "kind": "context", "at": at, "complete": False,
                          "parents": [b["source_id"] for b in bindings],
                          "source_bindings": deepcopy(bindings), "origin": "unknown", "input_sha256": version,
                          "slot": index, "role": item.get("role", "unknown") if isinstance(item, dict) else "unknown"})
        # A retry is conditional on earlier calls and their results. Retain those
        # edges even if their text did not enter the next prompt explicitly.
        parents += [r["context_receipt_id"] for r in self._requests]
        parents += [n["id"] for n in self._nodes if n.get("observation") == "router_result"]
        nodes.append({"id": node_id, "kind": "context", "at": at, "complete": False,
                      "parents": parents, "input_sha256": fingerprint, "request_id": request_id})
        record = {"request_id": request_id, "at": at, "context_receipt_id": node_id,
                  "input_sha256": fingerprint, "scope": "handler_arguments",
                  "input_count": len(inputs), "provider_attempts_complete": False}
        self._nodes.extend(nodes)
        self._requests.append(record)
        return Invocation(self, request_id)

    def observe(self, result, request_id=None, observed_at=None):
        """Copy metadata only; never retain provider text, tool calls or reason text.

        Stage lists sometimes contain their enclosing result. Walk one level,
        deduplicate by object identity, and never recurse through that cycle.
        """
        if self._closed or self._finalization_nodes:
            raise ValueError("observation must precede finalization boundaries")
        if not isinstance(result, dict):
            raise ValueError("generation result must be an object")
        stages = result.get("stages", [])
        if not isinstance(stages, list):
            raise ValueError("stages must be a list")
        seen = set()
        returned = None
        request = next((r for r in self._requests if r["request_id"] == request_id), None)
        if request_id is not None and request is None:
            raise ValueError("unknown request")
        if observed_at is not None:
            observed_at = instant(observed_at)
            if request is None or observed_at < request["at"]:
                raise ValueError("invalid result clock")
        for stage in list(stages) + [result]:
            if not isinstance(stage, dict) or id(stage) in seen:
                continue
            seen.add(id(stage))
            usable = stage.get("status") in ("valid", "truncated") and bool(stage.get("text"))
            evidence = stage.get("identity_evidence", "unknown")
            actual = stage.get("observed_model") if evidence in ("response_metadata", "runtime_receipt") else None
            attempt = {
                "attempt_id": "attempt-%d" % (len(self._attempts) + 1),
                "outcome": "discarded" if usable else "failed",
                "requested_model": stage.get("requested_model"),
                "served_model": actual,
                "served_revision": stage.get("observed_revision") if actual else None,
                "identity_evidence": evidence if actual else "unknown",
                "_claimed_model": stage.get("claimed_model") if evidence == "claimed" else None,
                "_raw_sha256": digest(stage["text"]) if usable and isinstance(stage["text"], str) else None}
            if request is not None:
                attempt.update(request_id=request_id, input_sha256=request["input_sha256"])
            self._attempts.append(attempt)
            if stage is result and usable:
                returned = attempt["attempt_id"]
            if request is not None:
                self._nodes.append({"id": self.context_id + ":" + attempt["attempt_id"],
                                    "kind": "context", "at": observed_at if observed_at is not None else request["at"],
                                    "time_basis": "observed" if observed_at is not None else "request_start_lower_bound",
                                    "complete": False,
                                    "parents": [request["context_receipt_id"]],
                                    "observation": "router_result", "origin": "unknown",
                                    "attempt_id": attempt["attempt_id"],
                                    "response_sha256": attempt["_raw_sha256"]})
        return returned

    def select(self, raw_reply, request=_UNSPECIFIED):
        """Explicit handler selection after fallback/repeat decisions, before edits."""
        if self._closed or self._finalization_nodes:
            raise ValueError("selection must precede finalization boundaries")
        fingerprint = digest(raw_reply) if isinstance(raw_reply, str) and raw_reply else None
        matches = [a for a in self._attempts if fingerprint and a["_raw_sha256"] == fingerprint]
        if request is not _UNSPECIFIED:
            matches = [a for a in matches if isinstance(request, Invocation) and request.capture is self
                       and a.get("request_id") == request.request_id
                       and a["attempt_id"] == request.returned_attempt_id]
        # Equal text is not an attempt identity. In particular, an observed
        # retry may be discarded by the handler. Until it supplies an explicit
        # attempt ID, ambiguous matches must not guess the served generator.
        self._selected = matches[0]["attempt_id"] if len(matches) == 1 else None

    def before_final_guard(self, text, at):
        """Hash the actual pre-guard version; do not claim its editors are known."""
        if self._finalization_nodes:
            raise ValueError("pre-guard boundary already recorded")
        self._record_finalization("before_final_guard", text, at)

    def _record_finalization(self, boundary, text, at):
        at = instant(at)
        if self._closed or not isinstance(text, str) or at < max(
                [self.started_at] + [n["at"] for n in self._nodes]):
            raise ValueError("invalid finalization boundary")
        selected = next((a for a in self._attempts if a["attempt_id"] == self._selected), None)
        previous = self._finalization_nodes[-1] if self._finalization_nodes else None
        before = previous["response_sha256"] if previous else selected["_raw_sha256"] if selected else None
        parent = previous["id"] if previous else (
            self.context_id + ":" + selected["attempt_id"] if selected else None)
        node = {"id": self.context_id + ":finalization-" + boundary,
                "kind": "context", "at": at, "complete": False,
                "parents": [parent] if parent else [], "observation": "finalization_boundary",
                "boundary": boundary, "origin": "unknown",
                "before_sha256": before, "response_sha256": digest(text),
                "changed": before != digest(text) if before else None}
        self._nodes.append(node)
        self._finalization_nodes.append(node)

    def finalize(self, final_text, finalized_at, transport="unknown"):
        """No delivery inference. Initial context ancestry is explicitly incomplete."""
        if self._closed:
            raise ValueError("capture already finalized")
        if transport not in ("unknown", "handed_to_framework", "failed"):
            raise ValueError("capture cannot attest delivery")
        final = instant(finalized_at)
        if not isinstance(final_text, str) or final < max([self.started_at] + [n["at"] for n in self._nodes]):
            raise ValueError("invalid finalization")
        self._record_finalization("handler_return", final_text, finalized_at)
        self._closed = True
        attempts = [{k: v for k, v in a.items() if not k.startswith("_")} for a in self._attempts]
        for attempt in attempts:
            if attempt["attempt_id"] == self._selected:
                attempt["outcome"] = "selected"
        r = receipt(self.turn_id, self.surface, self.started_at, finalized_at, final_text,
                    self.context_id, attempts, self._selected, delivery="unknown")
        selected = next((a for a in self._attempts if a["attempt_id"] == self._selected), None)
        return deepcopy({"schema": "witness-capture-v1", "turn_id": self.turn_id,
                         "surface": self.surface, "witness_receipt": r,
                         "witness_final_text": final_text, "witness_final_sha256": digest(final_text),
                         "transport": transport, "attempt_history_complete": False,
                         "requests": self._requests,
                         "observed_attempts": attempts,
                         "finalization": {"selected_raw_sha256": selected["_raw_sha256"] if selected else None,
                                          "final_sha256": digest(final_text), "scope": "handler_postprocessing",
                                          "changed": selected["_raw_sha256"] != digest(final_text) if selected else None,
                                          "boundary_ids": [n["id"] for n in self._finalization_nodes]},
                         "identity_claims": [{"attempt_id": a["attempt_id"], "claimed_model": a["_claimed_model"],
                                              "evidence": "relay_claim"} for a in self._attempts
                                             if isinstance(a["_claimed_model"], str) and a["_claimed_model"]],
                         "lineage": [{"id": self.context_id, "kind": "context", "at": final,
                                      "complete": False, "parents": [n["id"] for n in self._nodes
                                          if n.get("request_id") or n.get("observation") in
                                          ("router_result", "context_selection", "finalization_boundary")]}] + self._nodes,
                         "reply_node": {"id": "reply:" + self.turn_id, "kind": "reply",
                             "turn_id": self.turn_id, "at": instant(finalized_at), "complete": False,
                             "response_sha256": digest(final_text),
                             "context_receipt_id": self.context_id,
                             "parents": [self.context_id, self._finalization_nodes[-1]["id"]],
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


def begin_shadow(turn_id, surface, started_at, *, original_text=None, input_message=None, input_slot=None):
    """Disabled unless scratch and workspace explicitly name the same private root."""
    location = os.environ.get("JUDGES_CAPTURE_SCRATCH")
    if not location:
        return None
    root = _private_root(location)
    capture = Capture(turn_id, surface, started_at)
    capture._scratch_root = root
    try:
        capture.bind_counterpart_input(original_text, input_message, input_slot)
    except Exception:
        pass
    # Do not import a live organ just to observe it, nor read its on-disk store.
    # A context-local offer receipt is supplementary; a cached/stale one cannot
    # establish which material actually reached the provider.
    try:
        module = sys.modules.get("inner_context")
        value = module.current_selection() if module is not None else None
        if value is not None:
            capture.context_selection(value)
    except Exception:
        pass
    return capture


def _shadow_provenance(value, turn_id):
    """Do not let legacy coercions manufacture explicit shadow evidence."""
    from evidence_provenance import normalize
    unknown = {"turn_id": turn_id, "output_provenance": "unknown", "may_witness": False,
               "envelope_state": "malformed"}
    try:
        result = normalize(value if isinstance(value, dict) else unknown)
    except (TypeError, ValueError, KeyError, OverflowError):
        result = normalize(unknown)
    explicit = (isinstance(value, dict) and isinstance(value.get("turn_id"), str)
                and value["turn_id"] == turn_id and type(value.get("may_witness")) is bool
                and value.get("envelope_state", "present") == "present")
    if not explicit:
        result.update(may_witness=False, envelope_state="malformed")
    # A malformed envelope does not erase a separately explicit influence marker.
    if isinstance(value, dict) and value.get("output_provenance") == "stratagem_influenced":
        result.update(output_provenance="stratagem_influenced", may_witness=False)
    return result


def finish_shadow(capture, final_text, finalized_at, provenance=None, test_mode=False):
    """Write one private packet after the final guard, never to a live store.

    The handler still has no transport receipt: attempted return to the framework
    is recorded separately from delivery. Caller catches observation failures.
    """
    if capture is None:
        return False
    root = _private_root(capture._scratch_root)
    packet = capture.finalize(final_text, finalized_at, "handed_to_framework")
    p = _shadow_provenance(provenance, capture.turn_id)
    packet["generation_provenance"] = p
    packet["content"] = final_text
    packet["role"] = "assistant"
    packet["test_mode"] = bool(test_mode)
    if p.get("output_provenance") == "stratagem_influenced":
        packet["reply_node"]["influence"] = "influenced"
        packet["reply_node"]["tactical"] = True
        effect_id = "effect:" + capture.turn_id
        packet["lineage"].append({"id": effect_id, "kind": "tactical", "at": instant(finalized_at),
                                  "complete": False, "parents": [], "origin": "generation_provenance"})
        packet["reply_node"]["parents"].append(effect_id)
    # Write an invisible temporary name, then atomically publish a complete file.
    # link (rather than replacing rename) also refuses an existing final name.
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = None
    try:
        info = os.fstat(directory)
        if info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError("scratch permissions changed")
        name = "capture-" + uuid.uuid4().hex + ".json"
        candidate = "." + name + ".tmp"
        fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        temporary = candidate
        with os.fdopen(fd, "w") as f:
            json.dump(packet, f, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
    finally:
        try:
            if temporary is not None:
                os.unlink(temporary, dir_fd=directory)
        finally:
            os.close(directory)
    return True
