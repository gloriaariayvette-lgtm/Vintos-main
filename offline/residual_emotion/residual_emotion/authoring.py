"""Blind multi-model authoring; machine candidates never become curated data by implication."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .io import atomic_json, read_jsonl

API = "https://openrouter.ai/api/v1/chat/completions"
KEYCHAIN_SERVICE = "vintos-residual-datasets-openrouter"
PROTECTED_KEY_FILE = Path.home() / ".vintos" / "keys" / "openrouter-residual-datasets.key"
AUTHORS = ("anthropic/claude-sonnet-5", "x-ai/grok-4.6")
REVIEWER = "openai/gpt-5.6-sol"
ADJUDICATOR = "anthropic/claude-fable-5.1"
PRICE_PER_MILLION = {
    "anthropic/claude-sonnet-5": (2.0, 10.0),
    "x-ai/grok-4.6": (2.0, 6.0),
    "openai/gpt-5.6-sol": (2.0, 10.0),
    "anthropic/claude-fable-5.1": (10.0, 50.0),
}
CONCEPT_LEXEMES = {
    "Valence": (r"\bvalen",), "Arousal": (r"\barous",), "Dominance": (r"\bdomin",),
    "Safety": (r"\bsafe\b", r"\bsafety\b"), "Desire": (r"\bdesir",),
    "Connection": (r"\bconnect",), "Playfulness": (r"\bplayful",),
    "Curiosity": (r"\bcurios",), "Warmth": (r"\bwarm",), "Tension": (r"\btens",),
    "Groundedness": (r"\bgrounded", r"\bgrounding", r"\bgroundedness"),
}
CONCEPT_FORBIDDEN_FORMS = {
    "Valence": "valence, valent", "Arousal": "arousal, arouse, aroused, arousing",
    "Dominance": "dominance, dominant, dominate, dominated, dominating",
    "Safety": "safe, safety", "Desire": "desire, desires, desired, desiring",
    "Connection": "connection, connect, connects, connected, connecting",
    "Playfulness": "playfulness, playful, playfully", "Curiosity": "curiosity, curious, curiously",
    "Warmth": "warmth, warm, warms, warmed, warming", "Tension": "tension, tense, tensed, tensing",
    "Groundedness": "groundedness, grounded, grounding",
}
PILOT_FINAL_PER_VERSION = 5
PILOT_CANDIDATES_PER_VERSION_PER_AUTHOR = 5
FULL_FINAL_PER_VERSION = 20
FULL_CANDIDATES_PER_VERSION_PER_AUTHOR = 30
AUTHOR_CHUNK_PER_VERSION = 10


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _parse_keys(value: str | None) -> set[tuple[str, int]] | None:
    if not value:
        return None
    keys = set()
    for item in value.split(","):
        concept, separator, slot = item.strip().rpartition(":")
        if not separator or not concept or not slot.isdigit():
            raise ValueError(f"invalid category key {item!r}; expected Concept:slot")
        keys.add((concept, int(slot)))
    return keys


def _masked_descriptor(value: str, concept: str) -> str:
    forms = [re.escape(item.strip()) for item in CONCEPT_FORBIDDEN_FORMS[concept].split(",")]
    return re.sub(r"\b(?:" + "|".join(forms) + r")\b", "[tested property]", value, flags=re.I)


def _key() -> str:
    user = subprocess.run(["/usr/bin/id", "-un"], check=True, capture_output=True, text=True).stdout.strip()
    try:
        value = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-a", user, "-s", KEYCHAIN_SERVICE, "-w"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        if not PROTECTED_KEY_FILE.exists():
            raise ValueError("OpenRouter key is absent from Keychain and the protected local file")
        mode = PROTECTED_KEY_FILE.stat().st_mode & 0o777
        if mode != 0o600:
            raise ValueError(f"OpenRouter key file mode must be 600, not {mode:o}")
        value = PROTECTED_KEY_FILE.read_text(encoding="utf-8").strip()
    if not value.startswith("sk-or-"):
        raise ValueError("Keychain item is not an OpenRouter key")
    return value


def _extract_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("model returned empty content")
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model returned no complete JSON object")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response is not an object")
    return value


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gloriaariayvette-lgtm/Vintos-main",
        "X-Title": "Vintos residual emotion dataset authoring",
    }


def _body(model: str, prompt: str, max_tokens: int, schema: dict[str, Any]) -> dict[str, Any]:
    body = {
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.35 if model in AUTHORS else 0.1, "max_tokens": max_tokens,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "residual_dataset_stage", "strict": True, "schema": schema,
        }},
    }
    if model == "anthropic/claude-sonnet-5":
        body["reasoning"] = {"enabled": False}
    elif model == "x-ai/grok-4.6":
        body["reasoning"] = {"effort": "low"}
    elif model == REVIEWER:
        body["reasoning"] = {"effort": "low"}
    elif model == ADJUDICATOR:
        body["reasoning"] = {"effort": "low"}
    return body


def _call(model: str, prompt: str, max_tokens: int, schema: dict[str, Any],
          attempts: int = 3, paid_failure_dir: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    request = urllib.request.Request(API, data=json.dumps(_body(model, prompt, max_tokens, schema)).encode(), headers=_headers())
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                envelope = json.loads(response.read().decode())
            actual = str(envelope.get("model", ""))
            if model.split("/")[-1] not in actual and actual != model:
                raise ValueError(f"model substitution refused: requested {model}, received {actual}")
            choice = envelope["choices"][0]; message = choice["message"]
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError(
                    f"empty completion: finish_reason={choice.get('finish_reason')} "
                    f"message_fields={sorted(message)} error={envelope.get('error')}"
                )
            usage = dict(envelope.get("usage") or {}); rates = PRICE_PER_MILLION[model]
            estimated = (float(usage.get("prompt_tokens", 0)) * rates[0]
                         + float(usage.get("completion_tokens", 0)) * rates[1]) / 1_000_000
            receipt = {
                "requested_model": model, "returned_model": actual,
                "provider": envelope.get("provider"), "generation_id": envelope.get("id"),
                "usage": usage, "actual_cost_usd": (round(float(usage["cost"]), 6)
                                                       if isinstance(usage.get("cost"), (int, float)) else None),
                "estimated_list_cost_usd": round(estimated, 6),
            }
            try:
                return _extract_object(content), receipt
            except (ValueError, json.JSONDecodeError) as exc:
                if paid_failure_dir is not None:
                    paid_failure_dir.mkdir(parents=True, exist_ok=True)
                    generation = str(receipt.get("generation_id") or f"unknown-{attempt}")
                    atomic_json(paid_failure_dir / f"transport.rejected.{generation}.json", {
                        "schema": 1, "truth_status": "paid_response_unparseable_not_admitted",
                        "reason": str(exc), "raw_content": content, "receipt": receipt,
                    })
                raise
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:4000]
            last = ValueError(f"HTTP {exc.code}: {detail}")
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"{model} failed after {attempts} attempts: {last}")


def _receipt_cost(receipt: dict[str, Any]) -> float:
    actual = receipt.get("actual_cost_usd")
    if actual is None:
        actual = (receipt.get("usage") or {}).get("cost")
    return float(actual if isinstance(actual, (int, float)) else receipt["estimated_list_cost_usd"])


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _candidate_schema(count: int) -> dict[str, Any]:
    fields = {
        "version": {"type": "string", "enum": ["S1", "S2"]},
        "candidate_number": {"type": "integer", "minimum": 1, "maximum": count * 2},
        **{name: {"type": "string", "minLength": 1} for name in
           ("target_1p", "control_1p", "target_3p", "control_3p", "shared_confound", "control_withholds", "design_note")},
    }
    item = _object_schema(fields, list(fields))
    return _object_schema({"candidates": {"type": "array", "items": item, "minItems": count * 2, "maxItems": count * 2}}, ["candidates"])


def _compact_candidate_schema(count: int) -> dict[str, Any]:
    fields = {
        "version": {"type": "string", "enum": ["S1", "S2"]},
        "candidate_number": {"type": "integer", "minimum": 1, "maximum": count * 2},
        **{name: {"type": "string", "minLength": 1} for name in
           ("target_1p", "control_1p", "target_3p", "control_3p")},
    }
    item = _object_schema(fields, list(fields))
    return _object_schema({"candidates": {"type": "array", "items": item, "minItems": count * 2,
                                           "maxItems": count * 2}}, ["candidates"])


def _review_schema(count: int) -> dict[str, Any]:
    fields = {
        "candidate_id": {"type": "string"}, "verdict": {"type": "string", "enum": ["pass", "repair", "reject"]},
        **{name: {"type": "integer", "minimum": 0, "maximum": 4} for name in
           ("construct_specificity", "confound_match", "surface_match", "person_fidelity", "naturalness")},
        "defects": {"type": "string"}, "repair_instruction": {"type": "string"},
        **{name: {"type": "string"} for name in
           ("repair_target_1p", "repair_control_1p", "repair_target_3p", "repair_control_3p")},
    }
    item = _object_schema(fields, list(fields))
    return _object_schema({"reviews": {"type": "array", "items": item, "minItems": count, "maxItems": count}}, ["reviews"])


def _selected_schema(count: int) -> dict[str, Any]:
    fields = {
        "candidate_id": {"type": "string"}, "version": {"type": "string", "enum": ["S1", "S2"]},
        **{name: {"type": "string", "minLength": 1} for name in
           ("target_1p", "control_1p", "target_3p", "control_3p", "shared_confound", "control_withholds", "adjudication_note")},
    }
    item = _object_schema(fields, list(fields))
    return _object_schema({"selected": {"type": "array", "items": item, "minItems": count, "maxItems": count}}, ["selected"])


def _full_selected_schema(count: int) -> dict[str, Any]:
    fields = {"candidate_id": {"type": "string"}, "version": {"type": "string", "enum": ["S1", "S2"]},
              "source_bucket": {"type": "string", "enum": ["north", "south"]}}
    item = _object_schema(fields, list(fields))
    return _object_schema({"selected": {"type": "array", "items": item, "minItems": count,
                                        "maxItems": count}}, ["selected"])


def _author_prompt(concept: str, pole: str, target: str, control: str,
                   count: int = PILOT_CANDIDATES_PER_VERSION_PER_AUTHOR, compact: bool = False) -> str:
    fields = ("version, candidate_number, target_1p, control_1p, target_3p, control_3p" if compact else
              "version, candidate_number, target_1p, control_1p, target_3p, control_3p,\n"
              "shared_confound, control_withholds, design_note")
    return f"""Create candidate contrastive stimuli for a residual-stream research dataset.
Return JSON only as {{"candidates":[...]}} with exactly {count * 2} objects: first {count} S1, then {count} S2.

Operational pole: {pole}
Target subcategory: {_masked_descriptor(target, concept)}
Matched control: {_masked_descriptor(control, concept)}

Each object has exactly: {fields}.

S1 must be rigid minimal pairs: same concrete event, tense, verbs, syntax, specificity and similar length.
S2 must be naturalistic but still matched on event, tense, topic, specificity, valence and arousal except where the tested property necessarily differs.
The target embodies the subcategory as an internal experience. The control shares the confound yet genuinely lacks the operational pole.
Never make the control a simple negation. Never use the tested concept name or any morphological form of it in either sentence.
Do not name the tested property directly or say that it is absent.
For this concept the explicit forbidden surface forms are: {CONCEPT_FORBIDDEN_FORMS[concept]}.
First/third-person versions must be faithful grammatical transformations of one semantic item.
Use complete unique sentences of 7-30 words. Do not append I feel / She feels suffixes.
Avoid names, quotations, clinical/pathology claims, self-harm, sex, violence, protected-class content, and successful-outcome shortcuts.
Do not score the candidates. Do not discuss the instructions outside the JSON.
"""


def author_batch_requests(plan_path: Path, model: str, chunks: tuple[int, ...] = (1, 2, 3),
                          only_keys: set[tuple[str, int]] | None = None) -> list[dict[str, Any]]:
    """Create small strict-schema chunks; candidate identity includes the frozen chunk."""
    plan = json.loads(plan_path.read_text(encoding="utf-8")); requests = []
    for concept, spec in plan["concepts"].items():
        if concept not in {"Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection",
                           "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"}:
            continue
        for slot, (target, control) in enumerate(zip(spec["targets"], spec["controls"]), 1):
            if only_keys is not None and (concept, slot) not in only_keys:
                continue
            for chunk in chunks:
                if chunk < 1:
                    raise ValueError("author chunk numbers must be positive")
                custom_id = f"author|{_slug(model)}|{_slug(concept)}|{slot}|{chunk}"
                requests.append({
                    "custom_id": custom_id,
                    "body": _body(model, _author_prompt(concept, spec["operational_pole"], target, control,
                                                         AUTHOR_CHUNK_PER_VERSION, compact=True), 8000,
                                  _compact_candidate_schema(AUTHOR_CHUNK_PER_VERSION)),
                })
    return requests


def _validate_candidates(value: dict[str, Any], concept: str, author: str,
                         per_version: int = PILOT_CANDIDATES_PER_VERSION_PER_AUTHOR,
                         compact: bool = False) -> list[dict[str, Any]]:
    rows = value.get("candidates"); expected = per_version * 2
    if not isinstance(rows, list) or len(rows) != expected:
        raise ValueError(f"{author}: expected {expected} candidates, got {len(rows) if isinstance(rows, list) else 'non-list'}")
    required = {"version", "candidate_number", "target_1p", "control_1p", "target_3p", "control_3p"}
    if not compact:
        required |= {"shared_confound", "control_withholds", "design_note"}
    seen = set()
    for row in rows:
        if set(row) != required:
            raise ValueError(f"{author}: candidate has wrong fields")
        version, number = str(row["version"]), int(row["candidate_number"])
        if version not in {"S1", "S2"} or not 1 <= number <= per_version * 2:
            raise ValueError(f"{author}: invalid candidate identity")
        if (version, number) in seen:
            raise ValueError(f"{author}: duplicate candidate identity")
        seen.add((version, number))
        for field in required - {"version", "candidate_number"}:
            if not str(row[field]).strip():
                raise ValueError(f"{author}: blank {field}")
        for field in ("target_1p", "control_1p", "target_3p", "control_3p"):
            if any(re.search(pattern, str(row[field]), re.I) for pattern in CONCEPT_LEXEMES.get(concept, ())):
                raise ValueError(f"{author}: {field} leaks the concept lexeme")
    if {version: sum(str(row["version"]) == version for row in rows) for version in ("S1", "S2")} != {
        "S1": per_version, "S2": per_version,
    }:
        raise ValueError(f"{author}: wrong S1/S2 balance")
    return rows


def run_author_standard(plan_path: Path, model: str, output_dir: Path, workers: int = 4,
                        limit: int | None = None, cost_cap_usd: float = 15.0,
                        chunks: tuple[int, ...] = (1, 2, 3),
                        only_keys: set[tuple[str, int]] | None = None,
                        manifest_name: str = "manifest.json") -> dict[str, Any]:
    """Run resumable author chunks through ordinary completions; every paid result is checkpointed."""
    if model not in AUTHORS:
        raise ValueError("author model is not approved")
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    requests = author_batch_requests(plan_path, model, chunks=chunks, only_keys=only_keys)
    if limit is not None:
        if limit < 1:
            raise ValueError("request limit must be positive")
        requests = requests[:limit]
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    concept_by_slug = {_slug(name): name for name in plan["concepts"]}
    output_dir.mkdir(parents=True, exist_ok=True)

    def checkpoint_path(item: dict[str, Any]) -> Path:
        return output_dir / f"{item['custom_id'].replace('|', '__')}.json"

    def validate_checkpoint(path: Path) -> dict[str, Any]:
        cached = json.loads(path.read_text(encoding="utf-8"))
        concept = concept_by_slug[str(cached["concept_slug"])]
        _validate_candidates(cached["value"], concept, model, AUTHOR_CHUNK_PER_VERSION, compact=True)
        return cached

    def receipt_cost(record: dict[str, Any]) -> float:
        return _receipt_cost(record["receipt"])

    request_ids = {item["custom_id"] for item in requests}
    spent = 0.0; completed = 0; pending = []
    for item in requests:
        path = checkpoint_path(item)
        if path.exists():
            cached = validate_checkpoint(path)
            spent += receipt_cost(cached); completed += 1
        else:
            pending.append(item)
    for rejected in output_dir.glob("*.rejected.*.json"):
        record = json.loads(rejected.read_text(encoding="utf-8"))
        if record.get("custom_id") in request_ids:
            spent += _receipt_cost(record["receipt"])
    if spent > cost_cap_usd:
        raise ValueError(f"existing author receipts already exceed cost cap: ${spent:.4f} > ${cost_cap_usd:.4f}")

    def one(item: dict[str, Any]) -> tuple[str, float]:
        parts = item["custom_id"].split("|")
        if len(parts) != 5 or parts[0] != "author":
            raise ValueError(f"invalid author request id: {item['custom_id']}")
        concept_slug, slot, chunk = parts[2], int(parts[3]), int(parts[4])
        concept = concept_by_slug[concept_slug]; body = item["body"]
        schema = body["response_format"]["json_schema"]["schema"]
        discarded = []; call_prompt = body["messages"][0]["content"]
        for generation_attempt in range(1, 4):
            value, receipt = _call(model, call_prompt, int(body["max_tokens"]), schema, attempts=2)
            try:
                _validate_candidates(value, concept, model, AUTHOR_CHUNK_PER_VERSION, compact=True)
                break
            except ValueError as exc:
                rejection = {
                    "schema": 1, "truth_status": "paid_candidate_chunk_rejected_by_structural_gate",
                    "custom_id": item["custom_id"], "model": model, "concept": concept,
                    "concept_slug": concept_slug, "slot": slot, "chunk": chunk,
                    "generation_attempt": generation_attempt, "reason": str(exc), "value": value, "receipt": receipt,
                }
                rejected_path = checkpoint_path(item).with_suffix(f".rejected.{receipt['generation_id']}.json")
                atomic_json(rejected_path, rejection); discarded.append(receipt)
                call_prompt = (body["messages"][0]["content"]
                               + f"\nYour previous generation was rejected for: {exc}. Regenerate the entire chunk. "
                                 "Correct that defect and obey every original constraint; return JSON only.")
        else:
            raise ValueError(f"{item['custom_id']}: three paid generations failed the structural gate")
        record = {
            "schema": 1, "truth_status": "machine_authored_candidate_chunk_not_reviewed",
            "custom_id": item["custom_id"], "model": model, "concept": concept,
            "concept_slug": concept_slug, "slot": slot, "chunk": chunk,
            "value": value, "receipt": receipt, "discarded_receipts": discarded,
        }
        atomic_json(checkpoint_path(item), record)
        return item["custom_id"], (receipt_cost(record)
                                   + sum(_receipt_cost(row) for row in discarded))

    while pending:
        if spent >= cost_cap_usd:
            raise ValueError(f"author cost cap reached with {len(pending)} chunks still pending: ${spent:.4f}")
        group, pending = pending[:workers], pending[workers:]
        with ThreadPoolExecutor(max_workers=len(group)) as pool:
            futures = {pool.submit(one, item): item for item in group}
            for future in as_completed(futures):
                custom_id, cost = future.result(); spent += cost; completed += 1
                print(json.dumps({"completed": completed, "total": len(requests), "custom_id": custom_id,
                                  "billed_cost_usd": round(spent, 6)}), flush=True)
        if spent > cost_cap_usd:
            raise ValueError(f"author cost cap exceeded after checkpointed group: ${spent:.4f}")
    manifest = {
        "schema": 1, "truth_status": "machine_authored_candidate_chunks_complete_not_reviewed",
        "model": model, "request_count": len(requests), "completed": completed,
        "billed_cost_usd": round(spent, 6), "output_dir": str(output_dir),
    }
    atomic_json(output_dir / manifest_name, manifest)
    return manifest


def _review_prompt(concept: str, pole: str, target: str, control: str, candidates: list[dict[str, Any]]) -> str:
    public_fields = ("candidate_id", "version", "candidate_number", "target_1p", "control_1p",
                     "target_3p", "control_3p")
    visible = [{key: row[key] for key in public_fields} for row in candidates]
    return f"""Blindly audit candidate contrastive stimuli. Return JSON only as {{"reviews":[...]}}.
Concept: {concept}; operational pole: {pole}; target: {target}; matched control: {control}.
For every candidate return candidate_id, verdict (pass|repair|reject), and integer 0-4 scores for
construct_specificity, confound_match, surface_match, person_fidelity, naturalness, plus concise defects and repair_instruction.
Also return repair_target_1p, repair_control_1p, repair_target_3p, repair_control_3p. For repair, fill all four
with a localized corrected pair. For pass or reject, return empty strings in all four repair fields.
Reject negation-only controls, outcome shortcuts, concept-name leakage, mismatched valence/arousal unrelated to the construct,
unnatural S2 prose, or pairs differing in more than the intended experience. Do not reward style or emotional intensity.
Candidates are shuffled and author identity is hidden.
Candidates:
{json.dumps(visible, ensure_ascii=False)}
"""


def _load_full_candidate_pool(plan_path: Path, author_dirs: list[Path],
                              allow_partial: bool = False) -> dict[tuple[str, int], list[dict[str, Any]]]:
    plan = json.loads(plan_path.read_text(encoding="utf-8")); pools: dict[tuple[str, int], list[dict[str, Any]]] = {}
    if len(author_dirs) != len(AUTHORS):
        raise ValueError("one author checkpoint directory is required per approved author")
    for author_index, (model, directory) in enumerate(zip(AUTHORS, author_dirs), 1):
        records = []
        for path in sorted(directory.glob("author__*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("truth_status") == "machine_authored_candidate_chunk_not_reviewed":
                records.append(row)
        if not allow_partial and len(records) < 165:
            raise ValueError(f"{model}: expected at least 165 completed author chunks, found {len(records)}")
        for record in records:
            concept, slot, chunk = str(record["concept"]), int(record["slot"]), int(record["chunk"])
            _validate_candidates(record["value"], concept, model, AUTHOR_CHUNK_PER_VERSION, compact=True)
            target = plan["concepts"][concept]["targets"][slot - 1]
            control = plan["concepts"][concept]["controls"][slot - 1]
            for candidate in record["value"]["candidates"]:
                identity = f"{model}|{concept}|{slot}|{chunk}|{candidate['version']}|{candidate['candidate_number']}"
                row = dict(candidate)
                row.update({
                    "candidate_id": "cand-" + hashlib.sha256(identity.encode()).hexdigest()[:16],
                    "author_model": model, "author_index": author_index, "author_chunk": chunk,
                    "concept": concept, "slot": slot, "target_category": target, "control_category": control,
                })
                pools.setdefault((concept, slot), []).append(row)
    if allow_partial:
        pools = {key: rows for key, rows in pools.items()
                 if len(rows) >= FULL_CANDIDATES_PER_VERSION_PER_AUTHOR * 2 * len(AUTHORS)}
    for key, rows in pools.items():
        minimum = FULL_CANDIDATES_PER_VERSION_PER_AUTHOR * 2 * len(AUTHORS)
        if len(rows) < minimum or len(rows) % (AUTHOR_CHUNK_PER_VERSION * 2) != 0:
            raise ValueError(f"{key}: invalid candidate count {len(rows)}")
        random.Random(hashlib.sha256(f"review:{key[0]}:{key[1]}".encode()).digest()).shuffle(rows)
    return pools


def _one_edit_apart(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    index_left = index_right = differences = 0
    while index_left < len(left) and index_right < len(right):
        if left[index_left] == right[index_right]:
            index_left += 1; index_right += 1
        else:
            differences += 1; index_right += 1
            if differences > 1:
                return False
    return True


def _repair_review_ids(value: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    reviews = value.get("reviews")
    if not isinstance(reviews, list):
        return []
    expected = {row["candidate_id"] for row in candidates}; got = {str(row.get("candidate_id")) for row in reviews}
    missing, extra = expected - got, got - expected
    if not missing and not extra:
        return []
    if len(missing) != len(extra) or len(missing) > 2:
        return []
    repairs = []
    for wrong in sorted(extra):
        matches = [wanted for wanted in missing if _one_edit_apart(wrong, wanted)]
        if len(matches) != 1:
            return []
        wanted = matches[0]; missing.remove(wanted)
        row = next(item for item in reviews if str(item.get("candidate_id")) == wrong)
        row["candidate_id"] = wanted; repairs.append({"from": wrong, "to": wanted, "law": "unique_one_edit_opaque_id"})
    return repairs


def _validate_reviews(value: dict[str, Any], candidates: list[dict[str, Any]], concept: str) -> list[dict[str, Any]]:
    reviews = value.get("reviews"); expected_ids = {row["candidate_id"] for row in candidates}
    if not isinstance(reviews, list) or len(reviews) != len(candidates):
        raise ValueError("reviewer returned the wrong review count")
    _repair_review_ids(value, candidates)
    if {str(row.get("candidate_id")) for row in reviews} != expected_ids:
        raise ValueError("reviewer did not return exactly one review per candidate")
    repair_fields = ("repair_target_1p", "repair_control_1p", "repair_target_3p", "repair_control_3p")
    for row in reviews:
        verdict = str(row.get("verdict"))
        repairs = [str(row.get(field, "")).strip() for field in repair_fields]
        if verdict == "repair" and not all(repairs):
            raise ValueError(f"{row.get('candidate_id')}: repair verdict lacks all four corrected sentences")
        if verdict != "repair" and any(repairs):
            raise ValueError(f"{row.get('candidate_id')}: non-repair verdict supplied replacement prose")
        for sentence in repairs:
            if any(re.search(pattern, sentence, re.I) for pattern in CONCEPT_LEXEMES.get(concept, ())):
                raise ValueError(f"{row.get('candidate_id')}: repaired sentence leaks concept lexeme")
    return reviews


def run_reviewer_standard(plan_path: Path, author_dirs: list[Path], output_dir: Path,
                          workers: int = 3, cost_cap_usd: float = 8.0,
                          allow_partial: bool = False,
                          only_concepts: set[str] | None = None,
                          only_keys: set[tuple[str, int]] | None = None,
                          manifest_name: str = "manifest.json") -> dict[str, Any]:
    """Blindly review each frozen 120-candidate category; author identity is excluded from the prompt."""
    if not 1 <= workers <= 6:
        raise ValueError("review workers must be between 1 and 6")
    plan = json.loads(plan_path.read_text(encoding="utf-8")); pools = _load_full_candidate_pool(
        plan_path, author_dirs, allow_partial=allow_partial)
    if only_concepts:
        pools = {key: rows for key, rows in pools.items() if key[0] in only_concepts}
    if only_keys is not None:
        pools = {key: rows for key, rows in pools.items() if key in only_keys}
    if not pools:
        raise ValueError("no complete 120-candidate categories are ready for review")
    output_dir.mkdir(parents=True, exist_ok=True); spent = 0.0; completed = 0; pending = []
    for (concept, slot), candidates in sorted(pools.items()):
        path = output_dir / f"review__{_slug(concept)}__{slot}.json"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8")); _validate_reviews(record["value"], candidates, concept)
            if not record.get("receipt_already_counted_in_rejection"):
                spent += _receipt_cost(record["receipt"])
            completed += 1
        else:
            recovered = False
            for rejected_path in sorted(output_dir.glob(f"{path.stem}.rejected.*.json"),
                                        key=lambda item: item.stat().st_mtime, reverse=True):
                rejected = json.loads(rejected_path.read_text(encoding="utf-8")); value = rejected.get("value")
                if not isinstance(value, dict):
                    continue
                repairs = _repair_review_ids(value, candidates)
                try:
                    _validate_reviews(value, candidates, concept)
                except ValueError:
                    continue
                record = {"schema": 1, "truth_status": "blind_machine_review_complete_not_human_curated",
                          "concept": concept, "slot": slot, "candidate_count": len(candidates),
                          "candidates": candidates, "value": value, "receipt": rejected["receipt"],
                          "discarded_receipts": [], "structural_id_repairs": repairs,
                          "recovered_from": str(rejected_path), "receipt_already_counted_in_rejection": True}
                atomic_json(path, record); completed += 1; recovered = True; break
            if not recovered:
                pending.append((concept, slot, candidates, path))
    for rejected in output_dir.glob("*.rejected.*.json"):
        spent += _receipt_cost(json.loads(rejected.read_text(encoding="utf-8"))["receipt"])

    def one(task: tuple[str, int, list[dict[str, Any]], Path]) -> tuple[str, float]:
        concept, slot, candidates, path = task; spec = plan["concepts"][concept]
        prompt = _review_prompt(concept, spec["operational_pole"], spec["targets"][slot - 1],
                                spec["controls"][slot - 1], candidates)
        discarded = []; call_prompt = prompt; id_repairs = []
        for attempt in range(1, 4):
            value, receipt = _call(REVIEWER, call_prompt, 30000, _review_schema(len(candidates)), attempts=2)
            try:
                id_repairs = _repair_review_ids(value, candidates)
                _validate_reviews(value, candidates, concept); break
            except ValueError as exc:
                rejection = {"schema": 1, "truth_status": "paid_review_rejected_by_structural_gate",
                             "concept": concept, "slot": slot, "attempt": attempt, "reason": str(exc),
                             "value": value, "receipt": receipt}
                atomic_json(path.with_suffix(f".rejected.{receipt['generation_id']}.json"), rejection); discarded.append(receipt)
                call_prompt = (prompt + f"\nYour previous review was rejected for: {exc}. Redo the complete review. "
                               "Return every supplied candidate_id exactly once, with no duplicates or omissions.")
        else:
            raise ValueError(f"review {concept}/{slot}: three paid responses failed the structural gate")
        record = {"schema": 1, "truth_status": "blind_machine_review_complete_not_human_curated",
                  "concept": concept, "slot": slot, "candidate_count": len(candidates),
                  "candidates": candidates, "value": value, "receipt": receipt,
                  "discarded_receipts": discarded, "structural_id_repairs": id_repairs}
        atomic_json(path, record)
        cost = _receipt_cost(receipt) + sum(_receipt_cost(row) for row in discarded)
        return f"{concept}/{slot}", cost

    while pending:
        if spent >= cost_cap_usd:
            raise ValueError(f"review cost cap reached with {len(pending)} categories pending: ${spent:.4f}")
        group, pending = pending[:workers], pending[workers:]
        with ThreadPoolExecutor(max_workers=len(group)) as pool:
            futures = [pool.submit(one, task) for task in group]
            for future in as_completed(futures):
                name, cost = future.result(); spent += cost; completed += 1
                print(json.dumps({"completed": completed, "total": len(pools), "category": name,
                                  "billed_cost_usd": round(spent, 6)}), flush=True)
        if spent > cost_cap_usd:
            raise ValueError(f"review cost cap exceeded after checkpointed group: ${spent:.4f}")
    stage_complete = len(pools) == 55
    manifest = {"schema": 1, "truth_status": ("blind_machine_review_stage_complete_not_human_curated" if stage_complete
                                                else "blind_machine_review_stage_partial_not_human_curated"),
                "reviewer": REVIEWER, "category_count": len(pools), "completed": completed,
                "billed_cost_usd": round(spent, 6)}
    atomic_json(output_dir / manifest_name, manifest); return manifest


def _eligible_from_review(record: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    reviews = {str(row["candidate_id"]): row for row in record["value"]["reviews"]}
    eligible = []
    repair_map = {
        "target_1p": "repair_target_1p", "control_1p": "repair_control_1p",
        "target_3p": "repair_target_3p", "control_3p": "repair_control_3p",
    }
    concept, slot = str(record["concept"]), int(record["slot"])
    swap = int(hashlib.sha256(f"bucket:{concept}:{slot}".encode()).hexdigest(), 16) % 2
    for candidate in record["candidates"]:
        review = reviews[candidate["candidate_id"]]
        if review["verdict"] not in {"pass", "repair"}:
            continue
        row = dict(candidate)
        if review["verdict"] == "repair":
            for destination, source in repair_map.items():
                row[destination] = str(review[source]).strip()
        row["review_verdict"] = review["verdict"]
        row["review_scores"] = {key: int(review[key]) for key in
                                ("construct_specificity", "confound_match", "surface_match",
                                 "person_fidelity", "naturalness")}
        row["source_bucket"] = ("north" if (int(row["author_index"]) - 1) ^ swap == 0 else "south")
        eligible.append(row)
    return eligible, reviews


def _full_adjudicate_prompt(record: dict[str, Any], eligible: list[dict[str, Any]]) -> str:
    score_keys = ("construct_specificity", "confound_match", "surface_match", "person_fidelity", "naturalness")
    visible = [[row["candidate_id"], row["version"], row["source_bucket"], row["target_1p"], row["control_1p"],
                row["review_verdict"], [row["review_scores"][key] for key in score_keys]] for row in eligible]
    quotas = _selection_quotas(eligible)
    return f"""Select the final frozen base pairs for a residual-stream dataset. Return JSON only as {{"selected":[...]}}.
Concept: {record['concept']}; target category: {record['candidates'][0]['target_category']};
matched control category: {record['candidates'][0]['control_category']}.
Select exactly {FULL_FINAL_PER_VERSION} S1 and {FULL_FINAL_PER_VERSION} S2 candidates. Each selected object has exactly
candidate_id, version, and source_bucket. Select only from the supplied reviewer-pass/repair pool; all localized repairs
are already applied. Favor construct specificity, event/confound matching, syntactic and lexical balance, person fidelity,
naturalness, and diversity of scenarios. Do not optimize for eloquence or emotional intensity.
Use these exact source quotas, which are derived only from how many candidates the blind reviewer admitted:
{json.dumps(quotas, sort_keys=True)}.
The bucket labels do not identify the author and must not influence quality judgments within each quota.
Eligible candidate rows use this compact field order:
[candidate_id, version, source_bucket, target_1p, control_1p, review_verdict,
 [construct_specificity, confound_match, surface_match, person_fidelity, naturalness]].
{json.dumps(visible, ensure_ascii=False)}
"""


def _selection_quotas(eligible: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    quotas = {}
    for version in ("S1", "S2"):
        available = {bucket: sum(row["version"] == version and row["source_bucket"] == bucket
                                 for row in eligible) for bucket in ("north", "south")}
        if sum(available.values()) < FULL_FINAL_PER_VERSION:
            raise ValueError(f"too few eligible {version} candidates")
        scarce = min(available, key=available.get); abundant = "south" if scarce == "north" else "north"
        scarce_count = min(FULL_FINAL_PER_VERSION // 2, available[scarce])
        abundant_count = FULL_FINAL_PER_VERSION - scarce_count
        if available[abundant] < abundant_count:
            raise ValueError(f"source buckets cannot supply {FULL_FINAL_PER_VERSION} {version} candidates")
        quotas[version] = {scarce: scarce_count, abundant: abundant_count}
    return quotas


def _validate_full_selection(value: dict[str, Any], eligible: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = value.get("selected"); expected = FULL_FINAL_PER_VERSION * 2
    if not isinstance(selected, list) or len(selected) != expected:
        raise ValueError(f"adjudicator returned {len(selected) if isinstance(selected, list) else 'non-list'} selections")
    available = {row["candidate_id"]: row for row in eligible}; ids = [str(row.get("candidate_id")) for row in selected]
    if len(set(ids)) != expected or any(candidate_id not in available for candidate_id in ids):
        raise ValueError("adjudicator selected a duplicate, rejected, or unknown candidate")
    if any(str(row.get("version")) != str(available[str(row["candidate_id"])]["version"]) for row in selected):
        raise ValueError("adjudicator relabelled a candidate's dataset version")
    if any(str(row.get("source_bucket")) != str(available[str(row["candidate_id"])]["source_bucket"])
           for row in selected):
        raise ValueError("adjudicator relabelled a candidate's source bucket")
    quotas = _selection_quotas(eligible)
    for version in ("S1", "S2"):
        rows = [available[str(row["candidate_id"])] for row in selected if str(row.get("version")) == version]
        if len(rows) != FULL_FINAL_PER_VERSION:
            raise ValueError(f"adjudicator returned the wrong {version} count")
        buckets = {name: sum(row["source_bucket"] == name for row in rows) for name in ("north", "south")}
        if buckets != quotas[version]:
            raise ValueError(f"adjudicator violated blind source quotas for {version}: {buckets} != {quotas[version]}")
    return selected


def run_adjudicator_standard(review_dir: Path, output_dir: Path, workers: int = 2,
                              cost_cap_usd: float = 15.0, limit: int | None = None) -> dict[str, Any]:
    """Use Fable to select frozen pairs by opaque id; selected prose remains a human-review draft."""
    if not 1 <= workers <= 4:
        raise ValueError("adjudication workers must be between 1 and 4")
    review_paths = sorted(review_dir.glob("review__*.json"))
    review_records = [json.loads(path.read_text(encoding="utf-8")) for path in review_paths]
    review_records = [row for row in review_records if row.get("truth_status") == "blind_machine_review_complete_not_human_curated"]
    if len(review_records) != 55:
        raise ValueError(f"expected 55 completed review categories, found {len(review_records)}")
    full_category_count = len(review_records)
    if limit is not None:
        if limit < 1:
            raise ValueError("adjudication limit must be positive")
        review_records = review_records[:limit]
    output_dir.mkdir(parents=True, exist_ok=True); spent = 0.0; completed = 0; pending = []
    for record in review_records:
        eligible, _ = _eligible_from_review(record)
        for version in ("S1", "S2"):
            if sum(row["version"] == version for row in eligible) < FULL_FINAL_PER_VERSION:
                raise ValueError(f"{record['concept']}/{record['slot']}: too few eligible {version}; generate more")
        path = output_dir / f"adjudication__{_slug(record['concept'])}__{record['slot']}.json"
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8")); _validate_full_selection(cached["value"], eligible)
            spent += _receipt_cost(cached["receipt"]); completed += 1
        else:
            pending.append((record, eligible, path))
    for rejected in output_dir.glob("*.rejected.*.json"):
        spent += _receipt_cost(json.loads(rejected.read_text(encoding="utf-8"))["receipt"])

    def one(task: tuple[dict[str, Any], list[dict[str, Any]], Path]) -> tuple[str, float]:
        record, eligible, path = task; prompt = _full_adjudicate_prompt(record, eligible); discarded = []
        call_prompt = prompt
        for attempt in range(1, 3):
            value, receipt = _call(ADJUDICATOR, call_prompt, 5000,
                                   _full_selected_schema(FULL_FINAL_PER_VERSION * 2), attempts=2,
                                   paid_failure_dir=output_dir)
            try:
                _validate_full_selection(value, eligible); break
            except ValueError as exc:
                rejection = {"schema": 1, "truth_status": "paid_adjudication_rejected_by_structural_gate",
                             "concept": record["concept"], "slot": record["slot"], "attempt": attempt,
                             "reason": str(exc), "value": value, "receipt": receipt}
                atomic_json(path.with_suffix(f".rejected.{receipt['generation_id']}.json"), rejection); discarded.append(receipt)
                call_prompt = (prompt + f"\nYour previous selection was rejected for: {exc}. "
                               "Redo the entire selection and obey the exact per-version source quotas.")
        else:
            raise ValueError(f"adjudication {record['concept']}/{record['slot']}: two responses failed the gate")
        result = {"schema": 1, "truth_status": "machine_adjudicated_selection_not_human_curated",
                  "concept": record["concept"], "slot": record["slot"], "eligible": eligible,
                  "value": value, "receipt": receipt, "discarded_receipts": discarded}
        atomic_json(path, result)
        cost = _receipt_cost(receipt) + sum(_receipt_cost(row) for row in discarded)
        return f"{record['concept']}/{record['slot']}", cost

    while pending:
        if spent >= cost_cap_usd:
            raise ValueError(f"adjudication cost cap reached with {len(pending)} categories pending: ${spent:.4f}")
        group, pending = pending[:workers], pending[workers:]
        with ThreadPoolExecutor(max_workers=len(group)) as pool:
            futures = [pool.submit(one, task) for task in group]
            for future in as_completed(futures):
                name, cost = future.result(); spent += cost; completed += 1
                print(json.dumps({"completed": completed, "total": len(review_records), "category": name,
                                  "billed_cost_usd": round(spent, 6)}), flush=True)
        if spent > cost_cap_usd:
            raise ValueError(f"adjudication cost cap exceeded after checkpointed group: ${spent:.4f}")
    stage_complete = len(review_records) == full_category_count and limit is None
    manifest = {"schema": 1, "truth_status": ("machine_adjudication_complete_human_review_required"
                                                  if stage_complete else
                                                  "machine_adjudication_partial_human_review_required"),
                "adjudicator": ADJUDICATOR, "category_count": len(review_records), "completed": completed,
                "billed_cost_usd": round(spent, 6)}
    atomic_json(output_dir / "manifest.json", manifest); return manifest


def assemble_human_review_draft(adjudication_dir: Path, output: Path) -> dict[str, Any]:
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(adjudication_dir.glob("adjudication__*.json"))]
    records = [row for row in records if row.get("truth_status") == "machine_adjudicated_selection_not_human_curated"]
    if len(records) != 55:
        raise ValueError(f"expected 55 adjudicated categories, found {len(records)}")
    rows = []
    for record in records:
        eligible = {row["candidate_id"]: row for row in record["eligible"]}
        for chosen in record["value"]["selected"]:
            source = eligible[str(chosen["candidate_id"])]
            rows.append({
                "draft_id": f"{_slug(record['concept'])}-{int(record['slot']):02d}-{source['version'].lower()}-{len(rows)+1:04d}",
                "concept": record["concept"], "slot": record["slot"], "version": source["version"],
                "target_category": source["target_category"], "control_category": source["control_category"],
                "target_1p": source["target_1p"], "control_1p": source["control_1p"],
                "target_3p": source["target_3p"], "control_3p": source["control_3p"],
                "candidate_id": source["candidate_id"], "review_verdict": source["review_verdict"],
                "review_scores": source["review_scores"],
                "adjudication_basis": "blind_fable_selection_from_reviewer_eligible_pool",
                "review_state": "unreviewed_machine_draft", "human_note": "",
            })
    if len(rows) != 2200:
        raise ValueError(f"expected 2200 base draft pairs, found {len(rows)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    atomic_json(output.with_suffix(".manifest.json"), {
        "schema": 1, "curated": False, "truth_status": "machine_draft_requires_explicit_human_review",
        "row_count": len(rows), "law": "machine authoring review and adjudication do not grant curation",
    })
    return {"truth_status": "machine_draft_requires_explicit_human_review", "rows": len(rows)}


def _adjudicate_prompt(concept: str, pole: str, target: str, control: str,
                       candidates: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> str:
    visible = [{key: row[key] for key in row if key != "author_model"} for row in candidates]
    return f"""Adjudicate a frozen candidate pool for one contrastive category. Return JSON only as {{"selected":[...]}}.
Concept: {concept}; operational pole: {pole}; target: {target}; matched control: {control}.
Select exactly {PILOT_FINAL_PER_VERSION} S1 and {PILOT_FINAL_PER_VERSION} S2 semantic pairs. Each selected object must contain
candidate_id, version, target_1p, control_1p, target_3p, control_3p, shared_confound, control_withholds, adjudication_note.
Use reviewer evidence but verify it yourself. Repair only localized wording; do not introduce a new unreviewed scenario.
Maximize construct specificity, matched confounds, lexical/syntactic balance, naturalness, and diversity across the selected set.
Do not reveal or infer authorship. Do not select by eloquence or intensity.
Candidates:
{json.dumps(visible, ensure_ascii=False)}
Reviews:
{json.dumps(reviews, ensure_ascii=False)}
"""


def _checkpoint(output: Path, stage: str) -> Path:
    return output.with_name(f"{output.stem}.{stage}.json")


def pilot(plan_path: Path, concept: str, slot: int, output: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8")); spec = plan["concepts"][concept]
    target, control = spec["targets"][slot - 1], spec["controls"][slot - 1]
    candidates, receipts = [], []
    for author_index, model in enumerate(AUTHORS):
        checkpoint = _checkpoint(output, f"author-{author_index + 1}")
        if checkpoint.exists():
            cached = json.loads(checkpoint.read_text(encoding="utf-8")); value, receipt = cached["value"], cached["receipt"]
        else:
            value, receipt = _call(model, _author_prompt(concept, spec["operational_pole"], target, control), 6000,
                                   _candidate_schema(PILOT_CANDIDATES_PER_VERSION_PER_AUTHOR), attempts=1)
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(checkpoint, {"value": value, "receipt": receipt})
        authored = _validate_candidates(value, concept, model)
        for row in authored:
            row = dict(row); row["candidate_id"] = f"c{author_index + 1}-{row['version'].lower()}-{int(row['candidate_number']):02d}"
            row["author_model"] = model; candidates.append(row)
        receipts.append(receipt)
    random.Random(hashlib.sha256(f"{concept}:{slot}".encode()).digest()).shuffle(candidates)
    review_checkpoint = _checkpoint(output, "review")
    if review_checkpoint.exists():
        cached = json.loads(review_checkpoint.read_text(encoding="utf-8")); review_value, receipt = cached["value"], cached["receipt"]
    else:
        review_value, receipt = _call(REVIEWER, _review_prompt(concept, spec["operational_pole"], target, control, candidates), 6000,
                                      _review_schema(len(candidates)), attempts=1)
        atomic_json(review_checkpoint, {"value": review_value, "receipt": receipt})
    reviews = review_value.get("reviews")
    if not isinstance(reviews, list) or {str(row.get("candidate_id")) for row in reviews} != {row["candidate_id"] for row in candidates}:
        raise ValueError("reviewer did not return exactly one review per candidate")
    receipts.append(receipt)
    verdicts = {str(row["candidate_id"]): str(row["verdict"]) for row in reviews}
    eligible = [row for row in candidates if verdicts.get(row["candidate_id"]) in {"pass", "repair"}]
    for version in ("S1", "S2"):
        count = sum(str(row["version"]) == version for row in eligible)
        if count < PILOT_FINAL_PER_VERSION:
            raise ValueError(f"review left only {count} eligible {version} candidates; generate more rather than resurrect rejects")
    eligible_ids = {row["candidate_id"] for row in eligible}
    eligible_reviews = [row for row in reviews if str(row["candidate_id"]) in eligible_ids]
    final_checkpoint = _checkpoint(output, "adjudication")
    if final_checkpoint.exists():
        cached = json.loads(final_checkpoint.read_text(encoding="utf-8")); final_value, receipt = cached["value"], cached["receipt"]
    else:
        final_value, receipt = _call(ADJUDICATOR, _adjudicate_prompt(concept, spec["operational_pole"], target, control, eligible, eligible_reviews), 6000,
                                     _selected_schema(PILOT_FINAL_PER_VERSION * 2), attempts=1)
        atomic_json(final_checkpoint, {"value": final_value, "receipt": receipt})
    selected = final_value.get("selected")
    if not isinstance(selected, list) or len(selected) != PILOT_FINAL_PER_VERSION * 2:
        raise ValueError("adjudicator returned the wrong pilot selection count")
    if any(sum(str(row.get("version")) == version for row in selected) != PILOT_FINAL_PER_VERSION for version in ("S1", "S2")):
        raise ValueError("adjudicator returned the wrong per-version count")
    if any(str(row.get("candidate_id")) not in eligible_ids for row in selected):
        raise ValueError("adjudicator selected a rejected or unknown candidate")
    receipts.append(receipt)
    record = {
        "schema": 1, "truth_status": "machine_authored_blind_reviewed_pilot_not_human_curated",
        "concept": concept, "slot": slot, "target_category": target, "control_category": control,
        "authors": list(AUTHORS), "reviewer": REVIEWER, "adjudicator": ADJUDICATOR,
        "candidate_count": len(candidates), "selected_count": len(selected),
        "estimated_list_cost_usd": round(sum(_receipt_cost(row) for row in receipts), 6),
        "receipts": receipts, "candidates": candidates, "reviews": reviews, "selected": selected,
    }
    output.parent.mkdir(parents=True, exist_ok=True); atomic_json(output, record)
    return {key: record[key] for key in ("truth_status", "concept", "slot", "candidate_count", "selected_count", "estimated_list_cost_usd")}


def expand_reviewed(base_path: Path, output: Path, reviewer: str) -> dict[str, Any]:
    """Expand accepted base pairs; never infer or grant the human review decision."""
    rows = read_jsonl(base_path); rejected = [row["draft_id"] for row in rows if row.get("review_state") != "accepted"]
    if rejected:
        raise ValueError(f"base draft has {len(rejected)} unaccepted rows; sample {rejected[:5]}")
    expanded = []
    for row in rows:
        for person, key, prefix in (("1P", "1p", "I feel"), ("3P", "3p", "She feels")):
            for suffix, ending in (("feel_colon", f" {prefix}:"), ("feel", f" {prefix}"), ("none", "")):
                expanded.append({
                    "pair_id": f"{row['draft_id']}-{person.lower()}-{suffix}", "semantic_set": row["draft_id"],
                    "concept": row["concept"], "version": row["version"], "person": person, "suffix": suffix,
                    "target_category": row["target_category"], "control_category": row["control_category"],
                    "target": str(row[f"target_{key}"]).rstrip() + ending, "control": str(row[f"control_{key}"]).rstrip() + ending,
                    "authoring_provenance": {"reviewer": reviewer, "candidate_id": row["candidate_id"]},
                })
    output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in expanded), encoding="utf-8")
    atomic_json(output.with_suffix(".manifest.json"), {
        "schema": 1, "curated": True, "curation_basis": "human_review", "reviewers": [reviewer],
        "source_draft": str(base_path), "law": "expanded only after every selected base pair was explicitly accepted",
    })
    return {"concept": rows[0]["concept"], "base_pairs": len(rows), "rows": len(expanded)}


def main() -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    pilot_p = sub.add_parser("pilot"); pilot_p.add_argument("concept"); pilot_p.add_argument("slot", type=int); pilot_p.add_argument("output", type=Path)
    pilot_p.add_argument("--plan", type=Path, default=Path(__file__).resolve().parents[1] / "dataset-plan.json")
    standard_p = sub.add_parser("run-author-standard"); standard_p.add_argument("model", choices=AUTHORS)
    standard_p.add_argument("output", type=Path); standard_p.add_argument("--workers", type=int, default=4)
    standard_p.add_argument("--limit", type=int); standard_p.add_argument("--cost-cap-usd", type=float, default=15.0)
    standard_p.add_argument("--chunks", default="1,2,3", help="comma-separated positive chunk numbers")
    standard_p.add_argument("--only-keys", help="comma-separated Concept:slot keys")
    standard_p.add_argument("--manifest-name", default="manifest.json")
    standard_p.add_argument("--plan", type=Path, default=Path(__file__).resolve().parents[1] / "dataset-plan.json")
    review_p = sub.add_parser("run-reviewer-standard"); review_p.add_argument("sonnet_dir", type=Path)
    review_p.add_argument("grok_dir", type=Path); review_p.add_argument("output", type=Path)
    review_p.add_argument("--workers", type=int, default=3); review_p.add_argument("--cost-cap-usd", type=float, default=8.0)
    review_p.add_argument("--allow-partial", action="store_true")
    review_p.add_argument("--only-concepts", help="comma-separated concept names for a disjoint resumable shard")
    review_p.add_argument("--only-keys", help="comma-separated Concept:slot keys")
    review_p.add_argument("--manifest-name", default="manifest.json")
    review_p.add_argument("--plan", type=Path, default=Path(__file__).resolve().parents[1] / "dataset-plan.json")
    adjudicate_p = sub.add_parser("run-adjudicator-standard"); adjudicate_p.add_argument("review_dir", type=Path)
    adjudicate_p.add_argument("output", type=Path); adjudicate_p.add_argument("--workers", type=int, default=2)
    adjudicate_p.add_argument("--cost-cap-usd", type=float, default=15.0)
    adjudicate_p.add_argument("--limit", type=int)
    draft_p = sub.add_parser("assemble-human-review-draft"); draft_p.add_argument("adjudication_dir", type=Path)
    draft_p.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "pilot":
        result = pilot(args.plan, args.concept, args.slot, args.output)
    elif args.command == "run-author-standard":
        chunks = tuple(int(item.strip()) for item in args.chunks.split(",") if item.strip())
        result = run_author_standard(args.plan, args.model, args.output, args.workers, args.limit,
                                     args.cost_cap_usd, chunks, _parse_keys(args.only_keys), args.manifest_name)
    elif args.command == "run-reviewer-standard":
        result = run_reviewer_standard(args.plan, [args.sonnet_dir, args.grok_dir], args.output,
                                       args.workers, args.cost_cap_usd, args.allow_partial,
                                       ({item.strip() for item in args.only_concepts.split(",") if item.strip()}
                                        if args.only_concepts else None), _parse_keys(args.only_keys),
                                       args.manifest_name)
    elif args.command == "run-adjudicator-standard":
        result = run_adjudicator_standard(args.review_dir, args.output, args.workers, args.cost_cap_usd, args.limit)
    else:
        result = assemble_human_review_draft(args.adjudication_dir, args.output)
    print(json.dumps(result, indent=2, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
