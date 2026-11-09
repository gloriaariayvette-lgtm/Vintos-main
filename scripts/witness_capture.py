"""Request-local shadow capture with an explicit private scratch sink; no sends.

Provider hooks must explicitly label observed identity; configured names alone
are unknown. A handler selects the raw result before postprocessing, then binds
the receipt to its exact final return text. Persistence is a separate caller.
"""
from copy import deepcopy
import json
import os
import sys
import time
from pathlib import Path
from contextvars import ContextVar
import uuid
from witness_receipts import digest, instant, receipt, source_node
_UNSPECIFIED = object()
_value_map_stage = ContextVar("value_map_generation_stage", default=None)
_value_map_context = ContextVar("value_map_context_reads", default=None)
_self_forecast_scope = ContextVar("self_forecast_inputs", default=None)


def _fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def _resource_digest(resource):
    # Locator identity only: no stat, reopen, symlink resolution or origin claim.
    return digest(os.fsdecode(os.path.abspath(os.fspath(resource))))


def value_map_read(decoded, selected, at, resource=None):
    """Observe the existing newest-entry transform without reopening the source."""
    if not os.environ.get("JUDGES_CAPTURE_SCRATCH"):
        return None
    _private_root(os.environ["JUDGES_CAPTURE_SCRATCH"])
    if not isinstance(decoded, str) or len(decoded) > 4194304 or not isinstance(selected, str) or not selected:
        return None
    import re
    entry = re.split(r'\n(?=## \d{4}-\d{2}-\d{2})', "\n" + decoded)[-1].strip()
    if selected != entry[:1500]:
        return None
    observation = {"schema": "value-map-read-v1", "at": instant(at), "decoded_sha256": digest(decoded),
            "selected_sha256": digest(selected), "transform": "newest_entry_strip_first_1500_codepoints"}
    if resource is not None:
        observation.update(schema="value-map-read-v2", resource_sha256=_resource_digest(resource),
                           stripped_entry_sha256=digest(entry))
    return observation


def _guarded_reads(value):
    """Validate optional read metadata without admitting paths, text or origin claims."""
    if (not isinstance(value, dict) or set(value) != {"schema", "coverage", "reads", "truncated"}
            or value.get("schema") != "guarded-reads-v1" or value.get("coverage") != "guarded_json_only"
            or type(value.get("truncated")) is not bool or not isinstance(value.get("reads"), list)
            or len(value["reads"]) > 64):
        return None
    for item in value["reads"]:
        if (not isinstance(item, dict) or not {"resource_sha256", "state"} <= set(item)
                or set(item) - {"resource_sha256", "state", "decoded_sha256", "version_state"}
                or item["state"] not in ("loaded", "missing", "empty", "invalid", "unreadable")):
            return None
        for field in ("resource_sha256", "decoded_sha256"):
            if field not in item and field == "decoded_sha256":
                continue
            h = item.get(field)
            if not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
                return None
        if ("version_state" in item and item["version_state"] != "over_limit"
                or "version_state" in item and "decoded_sha256" in item
                or item["state"] in ("missing", "unreadable") and len(item) != 2
                or item["state"] in ("loaded", "empty") and not ("decoded_sha256" in item or "version_state" in item)):
            return None
    return deepcopy(value)


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
        self._rendered_fragments = []

    def bind_value_map(self, observation, fragment):
        """Bind the exact current-handler read to its offered block; ancestry stays unknown."""
        if self._closed or self._requests or any(n.get("observation") == "value_map_read" for n in self._nodes):
            raise ValueError("invalid value-map binding lifecycle")
        extra = {"resource_sha256", "stripped_entry_sha256"} if isinstance(observation, dict) and observation.get("schema") == "value-map-read-v2" else set()
        if (not isinstance(observation, dict)
                or set(observation) != {"schema", "at", "decoded_sha256", "selected_sha256", "transform"} | extra
                or observation.get("schema") not in ("value-map-read-v1", "value-map-read-v2")
                or observation.get("transform") != "newest_entry_strip_first_1500_codepoints"):
            return False
        prefix = "Your value map:\n"
        if (not isinstance(fragment, str) or not fragment.startswith(prefix)
                or not 0 < len(fragment) - len(prefix) <= 1500):
            return False
        for field in {"decoded_sha256", "selected_sha256"} | extra:
            h = observation.get(field)
            if not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
                return False
        at = instant(observation.get("at"))
        if at > self.started_at or digest(fragment[len(prefix):]) != observation["selected_sha256"]:
            return False
        key = self.context_id + ":value-map"
        read_key = key + ":read"
        self._nodes.append({"id": read_key, "kind": "context", "at": at, "complete": False,
                            "parents": [], "origin": "stored_unknown_ancestry", "observation": "value_map_read",
                            "decoded_sha256": observation["decoded_sha256"], "clock_basis": "read_completed",
                            **{field: observation[field] for field in extra}})
        self._nodes.append({"id": key, "kind": "value_map", "at": at, "complete": False,
                            "parents": [read_key], "origin": "generated_unknown_ancestry", "organ": "value_map",
                            "rendered_sha256": digest(fragment), "selected_sha256": observation["selected_sha256"],
                            "transform": observation["transform"]})
        self._rendered_fragments.append((key, "value_map", fragment))
        return True

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

    def rendered_selection(self, value):
        """Retain bounded ephemeral fragments from the exact observed selection."""
        if self._closed or self._requests or self._rendered_fragments or not isinstance(value, dict):
            raise ValueError("invalid rendered selection lifecycle")
        selections = [n for n in self._nodes if n.get("observation") == "context_selection"]
        if (len(selections) != 1 or value.get("schema") != "rendered-selection-v1"
                or value.get("selection_id") != selections[0]["selection_id"]
                or instant(value.get("ts")) != selections[0]["at"]):
            raise ValueError("rendered selection identity mismatch")
        fragments = value.get("fragments")
        if (not isinstance(fragments, dict) or len(fragments) > 64
                or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in fragments.items())
                or sum(len(v) for v in fragments.values()) > 262144):
            raise ValueError("invalid rendered selection fragments")
        offered = {o["organ"] for o in selections[0]["offers"] if o["state"] == "offered"}
        if not set(fragments) <= offered:
            raise ValueError("fragment lacks matching offer")
        nodes, retained = [], []
        read_manifests = value.get("reads", {})
        read_count = 0
        for i, (organ, text) in enumerate(sorted(fragments.items())):
            key = self.context_id + ":rendered-%d" % i
            node = {"id": key, "kind": "context", "at": selections[0]["at"],
                          "complete": False, "parents": [], "origin": "generated_unknown_ancestry",
                          "selection_id": value["selection_id"], "organ": organ,
                          "rendered_sha256": digest(text), "read_observation": "unavailable"}
            reads = _guarded_reads(read_manifests.get(organ)) if isinstance(read_manifests, dict) else None
            if reads is not None and read_count + len(reads["reads"]) <= 256:
                node.update(read_observation="partial", read_coverage=reads["coverage"],
                            reads_truncated=reads["truncated"])
                for j, observation in enumerate(reads["reads"]):
                    read_key = key + ":read-%d" % j
                    node["parents"].append(read_key)
                    nodes.append(dict(observation, id=read_key, kind="context", at=selections[0]["at"],
                                      complete=False, parents=[], origin="stored_unknown_ancestry",
                                      observation="guarded_json_read", clock_basis="selection_completed"))
                read_count += len(reads["reads"])
            nodes.append(node)
            retained.append((key, organ, text))
        self._nodes.extend(nodes)
        self._rendered_fragments = retained

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
        nodes, parents, fragment_observations = [], [], []
        rendered_bindings = []
        for key, organ, text in self._rendered_fragments:
            start = system.find(text)
            duplicate_offer = sum(other_text == text for _, _, other_text in self._rendered_fragments) > 1
            state = "not_found" if start < 0 else "ambiguous" if duplicate_offer or system.find(text, start + 1) >= 0 else "matched"
            observation = {"source_id": key, "organ": organ, "rendered_sha256": digest(text), "state": state}
            if state == "matched":
                binding = dict(observation, slot=0, input_sha256=_fingerprint(inputs[0]),
                               span={"start": start, "end": start + len(text), "unit": "unicode_codepoints"},
                               basis="exact_rendered_fragment")
                rendered_bindings.append(binding)
                observation = binding
            fragment_observations.append(observation)
        for index, item in enumerate(inputs):
            key = node_id + ":input-%d" % index
            parents.append(key)
            version = _fingerprint(item)
            bindings = [b for b in self._input_bindings if index == b["slot"] + 1
                        and version == b["message_sha256"]]
            nodes.append({"id": key, "kind": "context", "at": at, "complete": False,
                          "parents": [b["source_id"] for b in bindings] + ([b["source_id"] for b in rendered_bindings] if index == 0 else []),
                          "rendered_bindings": deepcopy(rendered_bindings) if index == 0 else [],
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
                  "input_count": len(inputs), "provider_attempts_complete": False,
                  "rendered_fragments": fragment_observations}
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
        self._rendered_fragments = []
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
            getter = getattr(module, "current_rendered_selection", None)
            if callable(getter):
                rendered = getter()
                if rendered is not None:
                    capture.rendered_selection(rendered)
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
    return _publish_private(root, packet, "capture-")


def begin_value_map_context(build):
    """Observe only instrumented direct reads during one existing assembly."""
    if build is None:
        return _value_map_context.set(None)
    if build["closed"]:
        raise ValueError("closed value-map build")
    build["context_entries"] = build.get("context_entries", 0) + 1
    build.pop("assembled_context", None)
    return _value_map_context.set((build, instant(time.time()), (), 0, False))


def observe_value_map_read(resource, decoded):
    current = _value_map_context.get()
    if current is None:
        return
    build, started, reads, chars, truncated = current
    if len(reads) >= 64:
        _value_map_context.set((build, started, reads, chars, True))
        return
    try:
        if not isinstance(decoded, str) or len(decoded) + chars > 4194304:
            _value_map_context.set((build, started, reads, chars, True))
            return
        record = {"resource_sha256": _resource_digest(resource), "decoded_sha256": digest(decoded),
                  "at": instant(time.time()), "complete": False, "origin": "stored_unknown_ancestry"}
        _value_map_context.set((build, started, reads + (record,), chars + len(decoded), truncated))
    except Exception:
        _value_map_context.set((build, started, reads, chars, True))


def observe_value_map_view(resource, lane, rows):
    """Observe the returned view, not raw bytes or a new eligibility decision."""
    current = _value_map_context.get()
    if current is None:
        return
    build, started, reads, chars, truncated = current
    if len(reads) >= 64:
        _value_map_context.set((build, started, reads, chars, True))
        return
    encoded_chars = 0
    try:
        if lane not in ("ledger_view", "history_view", "raw_fallback", "empty_fallback"):
            raise ValueError("invalid view lane")
        record = {"observation": "returned_view", "resource_sha256": _resource_digest(resource),
                  "lane": lane, "at": instant(time.time()), "complete": False,
                  "origin": "view_unknown_ancestry", "state": "unavailable"}
        if not isinstance(rows, list) or len(rows) > 4096:
            raise ValueError("unsupported view shape")
        import hashlib
        encoded_chars, version = 0, hashlib.sha256()
        for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(rows):
            encoded_chars += len(chunk)
            if chars + encoded_chars > 4194304:
                raise ValueError("view over limit")
            version.update(chunk.encode("utf-8"))
        # Preserve explicit returned markers as counts; never normalize a missing
        # envelope into permission or relabel the existing consumer's decision.
        standing = {key: 0 for key in ("eligible", "ineligible", "HELD", "unknown")}
        permission = {key: 0 for key in ("true", "false", "missing", "malformed")}
        withheld, influence_markers = 0, 0
        for row in rows:
            if not isinstance(row, dict):
                standing["unknown"] += 1; permission["malformed"] += 1
                continue
            status = row.get("evidence_standing")
            standing[status if isinstance(status, str) and status in standing else "unknown"] += 1
            env = row.get("generation_provenance", row.get("provenance"))
            influence_markers += (row.get("character_influenced") is True or row.get("tactical") is True
                                  or (isinstance(env, dict) and env.get("output_provenance") == "stratagem_influenced"))
            if "generation_provenance" not in row and "provenance" not in row:
                permission["missing"] += 1
            else:
                marker = env.get("may_witness") if isinstance(env, dict) else None
                permission["true" if marker is True else "false" if marker is False else "malformed"] += 1
            withheld += row.get("vintos_withheld") is True
        record.update(state="observed", view_sha256=version.hexdigest(), rows=len(rows),
                      standing_counts=standing, permission_counts=permission, withheld_rows=withheld,
                      known_influence_marker_rows=influence_markers,
                      hash_basis="canonical_returned_json", source_version="unobserved")
        _value_map_context.set((build, started, reads + (record,), chars + encoded_chars, truncated))
    except Exception:
        # Unsupported/malformed/oversized evidence must not change the caller's
        # result or erase already observed reads. No exception contents retained.
        if "record" in locals():
            _value_map_context.set((build, started, reads + (record,), min(4194304, chars + encoded_chars), True))
        else:
            _value_map_context.set((build, started, reads, chars, True))


def finish_value_map_context(token, build, rendered):
    if token is None:
        return
    current = _value_map_context.get()
    _value_map_context.reset(token)
    if current is None or build is None:
        return
    observed_build, started, reads, chars, truncated = current
    if observed_build is not build or build["closed"]:
        raise ValueError("invalid context assembly owner")
    if build.get("context_entries") != 1 or not isinstance(rendered, str) or not 0 < len(rendered) <= 60000:
        return
    ended = instant(time.time())
    if not build["started_at"] <= started <= ended or any(not started <= r["at"] <= ended for r in reads):
        return
    metadata = {"schema": "value-map-context-v1", "started_at": started, "ended_at": ended,
                "rendered_sha256": digest(rendered), "rendered_chars": len(rendered),
                "scope": "instrumented_reads_and_views_during_assembly", "contribution": "not_established",
                "upstream_complete": False, "reads": list(reads), "truncated": truncated}
    # Only this bounded string lives until the build returns; packets contain hashes.
    build["assembled_context"] = (rendered, metadata)


def begin_value_map_material(build, label):
    """A separate read scope for the existing identity or temporal reader."""
    if label not in ("system_identity", "temporal"):
        raise ValueError("invalid value-map material")
    if build is None:
        return (None, begin_value_map_context(None), None, label)
    if build["closed"]:
        raise ValueError("closed value-map build")
    counts = build.setdefault("material_entries", {})
    counts[label] = counts.get(label, 0) + 1
    build.setdefault("materials", {}).pop(label, None)
    scope = {"started_at": build["started_at"], "closed": False}
    return (scope, begin_value_map_context(scope), build, label)


def finish_value_map_material(observation, rendered):
    if observation is None:
        return
    scope, token, build, label = observation
    finish_value_map_context(token, scope, rendered)
    if build is None or build["closed"] or build["material_entries"][label] != 1:
        return
    assembly = scope.get("assembled_context")
    if assembly is not None:
        text, metadata = assembly
        metadata.update(scope="direct_reads_during_material", material=label,
                        read_state="observed" if metadata["reads"] else "unavailable")
        build["materials"][label] = (text, metadata)


def _value_map_context_binding(build, payload, at, slot=1):
    assembly = build.get("assembled_context")
    if build.get("context_entries") != 1 or assembly is None:
        return {"state": "unavailable"}
    rendered, metadata = assembly
    if metadata["ended_at"] > at:
        return {"state": "unavailable"}
    text = payload["messages"][slot]["content"]
    start = text.find(rendered)
    state = "not_found" if start < 0 else "ambiguous" if text.find(rendered, start + 1) >= 0 else "matched"
    result = {"state": state, "assembly": deepcopy(metadata)}
    if state == "matched":
        result.update(slot=slot, input_sha256=_fingerprint(payload["messages"][slot]),
                      span={"start": start, "end": start + len(rendered), "unit": "unicode_codepoints"})
    return result


def _value_map_material_bindings(build, payload, at):
    bindings = {}
    for label, slot in (("system_identity", 0), ("temporal", 1)):
        assembly = build.get("materials", {}).get(label)
        proxy = {"context_entries": build.get("material_entries", {}).get(label, 0), "assembled_context": assembly}
        bindings[label] = _value_map_context_binding(proxy, payload, at, slot)
    return bindings


def begin_value_map_call(payload):
    """Observe one existing HTTP invocation; this is not a chat witness or a build."""
    location = os.environ.get("JUDGES_CAPTURE_SCRATCH")
    if not location:
        return None
    root = _private_root(location)
    if (not isinstance(payload, dict) or set(payload) != {"model", "messages", "temperature", "max_tokens"}
            or not isinstance(payload["messages"], list) or len(payload["messages"]) != 2):
        raise ValueError("invalid value-map call")
    inputs = []
    for i, item in enumerate(payload["messages"]):
        if (not isinstance(item, dict) or set(item) != {"role", "content"}
                or item["role"] != ("system" if i == 0 else "user")
                or not isinstance(item["content"], str) or len(item["content"]) > 4194304):
            raise ValueError("invalid value-map input")
        inputs.append({"slot": i, "role": item["role"], "input_sha256": _fingerprint(item),
                       "complete": False, "origin": "generated_or_unknown"})
    configured = payload["model"]
    if not isinstance(configured, str) or not 0 < len(configured) <= 256:
        configured = None
    observation = {"root": root, "closed": False, "packet": {
        "schema": "value-map-call-v1", "request_id": uuid.uuid4().hex,
        "started_at": instant(time.time()), "input_sha256": _fingerprint(payload), "inputs": inputs,
        "configured_model": configured, "scope": "one_http_invocation",
        "upstream_complete": False, "internal_attempts_complete": False,
        "build_selection": "not_recorded", "stored_output_binding": "not_recorded"}}
    active = _value_map_stage.get()
    if active is not None:
        build, stage, parents = active
        if not build["closed"] and build["root"] == root and len(build["calls"]) < 8:
            observation["packet"].update(build_id=build["build_id"], stage=stage,
                                         assembled_context=_value_map_context_binding(build, payload, observation["packet"]["started_at"]),
                                         auxiliary_inputs=_value_map_material_bindings(build, payload, observation["packet"]["started_at"]),
                                         dependencies=[_map_dependency(build, k, v, observation["packet"]["started_at"])
                                                       for k, v in parents.items()])
            build["calls"].append(observation)
        elif not build["closed"] and build["root"] == root and len(build["calls"]) >= 8:
            build["calls_truncated"] = True
    return observation


def finish_value_map_call(observation, response, http_status, returned_text, outcome):
    """Publish hashes and direct response metadata only; failure text is never retained."""
    if observation is None:
        return False
    if observation["closed"]:
        return False
    observation["closed"] = True
    if outcome not in ("returned", "rejected", "failed"):
        raise ValueError("invalid value-map outcome")
    if outcome == "returned" and not isinstance(returned_text, str):
        raise ValueError("missing returned text")
    if outcome != "returned" and returned_text is not None:
        raise ValueError("unexpected returned text")
    packet = deepcopy(observation["packet"])
    ended = instant(time.time())
    if ended < packet["started_at"]:
        raise ValueError("invalid call clock")
    observed = response.get("model") if isinstance(response, dict) and outcome == "returned" else None
    if not isinstance(observed, str) or not observed.strip() or len(observed) > 256:
        observed = None
    packet.update(ended_at=ended, outcome=outcome,
                  served_model=observed, identity_evidence="response_metadata" if observed else "unknown",
                  http_status=http_status if type(http_status) is int and 100 <= http_status <= 599 else None,
                  response_sha256=_fingerprint(response) if response is not None else None,
                  returned_sha256=digest(returned_text) if returned_text is not None else None)
    observation["completed_packet"] = deepcopy(packet)
    published = _publish_private(_private_root(observation["root"]), packet, "value-map-call-")
    observation["published"] = published is True
    return published


def begin_value_map_build():
    location = os.environ.get("JUDGES_CAPTURE_SCRATCH")
    if not location:
        return None
    return {"root": _private_root(location), "build_id": uuid.uuid4().hex,
            "started_at": instant(time.time()), "closed": False, "calls": [],
            "stage_entries": {}, "calls_truncated": False}


def enter_value_map_stage(build, stage, parents=None):
    if build is None:
        return _value_map_stage.set(None)
    if build["closed"] or stage not in ("draft_a", "draft_b", "synthesis"):
        raise ValueError("invalid build stage")
    if parents is None:
        parents = {}
    if (not isinstance(parents, dict) or set(parents) != ({"draft_a", "draft_b"} if stage == "synthesis" else set())
            or any(not isinstance(v, str) or len(v) > 4194304 for v in parents.values())):
        raise ValueError("invalid stage dependencies")
    build["stage_entries"][stage] = build["stage_entries"].get(stage, 0) + 1
    return _value_map_stage.set((build, stage, {k: digest(v) for k, v in parents.items()}))


def leave_value_map_stage(token):
    if token is not None:
        _value_map_stage.reset(token)


def _map_dependency(build, stage, version, latest):
    calls = [c for c in build["calls"] if c["packet"].get("stage") == stage]
    matched = (not build["calls_truncated"] and build["stage_entries"].get(stage) == 1
               and len(calls) == 1 and calls[0].get("published") is True
               and calls[0].get("completed_packet", {}).get("outcome") == "returned"
               and build["started_at"] <= calls[0]["completed_packet"]["started_at"]
               and calls[0]["completed_packet"]["ended_at"] <= latest
               and calls[0]["completed_packet"].get("returned_sha256") == version)
    return {"stage": stage, "returned_sha256": version,
            "state": "bound" if matched else "unavailable",
            "request_id": calls[0]["packet"]["request_id"] if matched else None}


def finish_value_map_build(build, selected_stage, result, entry, mode, resource=None):
    """Observe the existing close boundary; never claim transactional or durable storage."""
    if build is None or build["closed"]:
        return False
    build["closed"] = True
    if (selected_stage not in ("draft_a", "draft_b", "synthesis") or mode not in ("a", "w")
            or not isinstance(result, str) or not result or not isinstance(entry, str)
            or len(entry) > 4194304 or not entry.endswith(result + "\n\n---\n")):
        raise ValueError("invalid written entry")
    prefix = entry[:len(entry) - len(result + "\n\n---\n")]
    import re
    if re.fullmatch(r"\n## \d{4}-\d{2}-\d{2} \d{2}:\d{2} — Value Map\n\n", prefix) is None:
        raise ValueError("invalid entry prefix")
    ended = instant(time.time())
    if ended < build["started_at"]:
        raise ValueError("invalid build clock")
    selection = _map_dependency(build, selected_stage, digest(result), ended)
    calls = [{"request_id": c["packet"]["request_id"], "stage": c["packet"]["stage"],
              "packet_published": c.get("published") is True,
              "outcome": c.get("completed_packet", {}).get("outcome", "unobserved")}
             for c in build["calls"]]
    packet = {"schema": "value-map-build-v1", "build_id": build["build_id"],
              "started_at": build["started_at"], "ended_at": ended, "calls": calls,
              "selection": selection, "stage_entries": dict(build["stage_entries"]),
              "calls_truncated": build["calls_truncated"],
              "upstream_complete": False, "attempt_coverage_complete": False,
              "write": {"scope": "entry_write_closed", "mode": "append" if mode == "a" else "replace",
                        "entry_sha256": digest(entry), "stripped_entry_sha256": digest(entry.strip()),
                        "entry_chars": len(entry), "durability": "unconfirmed", "whole_file": "unverified"}}
    if resource is not None:
        packet["schema"] = "value-map-build-v2"
        packet["write"]["resource_sha256"] = _resource_digest(resource)
    return _publish_private(_private_root(build["root"]), packet, "value-map-build-")


def _publish_private(root, packet, prefix):
    # Write an invisible temporary name, then atomically publish a complete file.
    # link (rather than replacing rename) also refuses an existing final name.
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = None
    try:
        info = os.fstat(directory)
        if info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError("scratch permissions changed")
        name = prefix + uuid.uuid4().hex + ".json"
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


def begin_self_forecast():
    """Scope one existing self forecast; no encoder/model/store work here."""
    location = os.environ.get("JUDGES_CAPTURE_SCRATCH")
    if not location:
        return None
    root = _private_root(location)
    return _self_forecast_scope.set({"root": str(root), "observations": 0, "inputs": None})


def self_exchange_clock(raw, parsed, rendered):
    """Retain explicit source time before legacy formatting, only in a scoped forecast."""
    if _self_forecast_scope.get() is None:
        return None
    try:
        epoch = instant(raw)
        if epoch != instant(parsed) or not isinstance(rendered, str) or len(rendered) > 128:
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    return {"schema": "self-exchange-clock-v1", "epoch": epoch,
            "raw_kind": "offset_iso" if isinstance(raw, str) else "numeric_epoch",
            "raw_clock_sha256": _fingerprint(raw), "rendered_clock_sha256": digest(rendered),
            "meaning": "source_exchange_time_not_reply_finalization"}


def _self_context_clock(exchange, at):
    value = exchange.get("_witness_clock")
    if (not isinstance(exchange.get("ts"), str) or not isinstance(value, dict)
            or set(value) != {"schema", "epoch", "raw_kind", "raw_clock_sha256",
                                                    "rendered_clock_sha256", "meaning"}
            or value["schema"] != "self-exchange-clock-v1"
            or value["raw_kind"] not in ("offset_iso", "numeric_epoch")
            or value["meaning"] != "source_exchange_time_not_reply_finalization"):
        return None
    try:
        if (instant(value["epoch"]) != instant(at) or instant(exchange["at"]) != instant(at)
                or value["rendered_clock_sha256"] != digest(exchange["ts"])):
            return None
        raw_hash = value["raw_clock_sha256"]
        if not isinstance(raw_hash, str) or len(raw_hash) != 64 or any(c not in "0123456789abcdef" for c in raw_hash):
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return deepcopy(value)


def observe_self_forecast(exchanges, own, as_of, forecast):
    """Record the actual readout's recent-own inputs, not its complete context.

    Exchange text has already been normalized/merged by the existing reader.
    Its IDs and clocks are observations, not finalized-reply origin evidence.
    """
    scope = _self_forecast_scope.get()
    if scope is None:
        return
    count = scope["observations"] + 1
    _self_forecast_scope.set(dict(scope, observations=count, inputs=None))
    if count != 1 or not isinstance(exchanges, list) or not isinstance(own, list):
        return
    selected = []
    for exchange in reversed(exchanges):
        if not isinstance(exchange, dict):
            return
        if exchange.get("his"):
            selected.append(exchange)
        if len(selected) == 6:
            break
    selected.reverse()
    if not selected or any(not isinstance(x["his"], str) or len(x["his"]) > 65536 for x in selected):
        return
    if own != [x["his"][:400] for x in selected]:
        return
    # Numeric exchange clocks are kept as such; never relabel them finalization.
    observed_at = instant(as_of)
    refs = []
    for x, text in zip(selected, own):
        at = instant(x["at"])
        if at > observed_at:
            return
        key = x.get("turn_id")
        key = key if isinstance(key, str) and key.strip() and len(key) <= 256 else None
        refs.append({"observed_turn_id": key, "exchange_at": at,
                     "normalized_reply_sha256": digest(x["his"]),
                     "encoder_input_sha256": digest(text), "encoder_input_chars": len(text)})
    inputs = {"scope": "recent_own_reply_feature_inputs", "as_of_exchange_at": observed_at,
              "transform": "normalized_exchange_his_first_400_codepoints",
              "selection": "last_six_nonempty_his_in_supplied_exchange_order", "reply_refs": refs,
              "source_identity": "unverified", "encoder_identity": "unobserved",
              "upstream_complete": False, "complete_forecast_context": False}
    payload = {"her_key": forecast["her_key"], "self": {k: forecast[k] for k in
               ("source", "checkpoint_id", "context_last_ts", "confidence", "qualification", "coherence")}}
    payload["self"].update(mode="on_message", emb=[round(float(x), 4) for x in forecast["emb"]])
    if forecast.get("context_emb") is not None:
        payload["context_emb"] = forecast["context_emb"]
    _self_forecast_scope.set(dict(scope, observations=count, inputs=inputs,
                                 payload_sha256=_fingerprint(payload),
                                 context_clock=_self_context_clock(exchanges[-1], observed_at)))


def end_self_forecast(token):
    if token is None:
        return None
    scope = _self_forecast_scope.get()
    _self_forecast_scope.reset(token)
    return scope


def publish_self_forecast(scope, row):
    """Sidecar after the existing forecast-log close; leaves its row unchanged."""
    if scope is None:
        return None
    root = _private_root(scope["root"])
    if row.get("mode") != "on_message" or row.get("self", {}).get("mode") != "on_message":
        return None
    made, arrived = instant(row["ts"]), instant(row["arrived_at"])
    if made < arrived:
        return None
    payload = {"her_key": row["her_key"], "self": row["self"]}
    if "context_emb" in row:
        payload["context_emb"] = row["context_emb"]
    matched = (scope["observations"] == 1 and scope["inputs"] is not None
               and scope.get("payload_sha256") == _fingerprint(payload)
               and scope["inputs"]["as_of_exchange_at"] < arrived)
    # Exact row hash includes the already rounded prediction and all metadata.
    # No vectors, messages or private identifiers are copied into this hash field.
    packet = {"schema": "self-forecast-inputs-v1", "forecast_row_sha256": _fingerprint(row),
              "forecast_at": made, "arrived_at": arrived, "boundary": "forecast_log_close",
              "durability": "unconfirmed", "observations": scope["observations"],
              "state": "observed" if matched else "unavailable",
              "inputs": scope["inputs"] if matched else None, "complete_forecast_context": False}
    published = _publish_private(root, packet, "self-forecast-inputs-")
    if (matched and scope.get("context_clock") is not None
            and isinstance(row["self"].get("context_last_ts"), str)
            and digest(row["self"]["context_last_ts"]) == scope["context_clock"]["rendered_clock_sha256"]):
        clock_packet = {"schema": "self-forecast-clock-v1", "forecast_row_sha256": packet["forecast_row_sha256"],
                        "forecast_at": made, "arrived_at": arrived,
                        "context_clock": scope["context_clock"], "boundary": "forecast_log_close",
                        "durability": "unconfirmed", "source_identity": "unverified"}
        _publish_private(root, clock_packet, "self-forecast-clock-")
    return published
