#!/usr/bin/env python3
"""A scientific claim with a way to fail: a frozen measurement contract beside the execution receipt.

A line plan's `done` means the operation completed and its output was retained; it never meant the prediction was
right, and it must not start meaning that. A finding's appraisal reads titles; it is not a measurement. What was
missing is a typed record of what observation would count against his prediction, measured by his own instrument,
kept whichever way it came out.

  contract   - frozen before the output it judges exists: hypothesis, experimental unit, measured variable and its
               units, the comparator, independence and missingness rules, cohort digest, what would support and what
               would oppose. Revision and freeze time; the steps that already existed are listed, and none of them
               can confirm it. "exploratory" is an honest mode with no confirmatory claim, never a failure.
  evaluate   - three deterministic evaluators, no code and no expression from a model is ever run:
                 proportion_vs_control  counts or records with a positive rule, against a matched control (Newcombe
                                        interval on the difference, Fisher exact p)
                 structural_measure     one aligned measurement against a threshold, with its uncertainty
                 reproducibility        a value against a rerun or a cited reference, within a stated tolerance
               Every criterion names a real output field (a path) and what it means.
  result     - four separate facts: execution_state, measurement_state (supported / refuted / inconclusive /
               not_evaluated), novelty_state and truth_status, bound to the output digests, plan id and contract
               revision. A broken tool is not_evaluated, never evidence against him. A clean contradiction is refuted
               with execution completed, and it is kept: `negatives()` returns it and the planner is shown it.

Stores (beside the Lab's other records): measurement-contracts.jsonl (append-only revisions) and
measurement-results.jsonl. No model is asked here, nothing is sent, nothing is gated.

    python3 lab_measurement.py [show [N] | negatives [N] | settle]
"""
from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
LAB = os.path.join(WS, "memory", "chemistry-lab")
CONTRACTS_NAME = "measurement-contracts.jsonl"
RESULTS_NAME = "measurement-results.jsonl"

EVALUATORS = ("proportion_vs_control", "structural_measure", "reproducibility")
PREDICTS = {"proportion_vs_control": ("case_higher", "case_lower", "no_difference"),
            "structural_measure": ("above", "below"),
            "reproducibility": ("reproduces", "differs")}
MODES = ("confirmatory", "exploratory")
INDEPENDENCE = ("records", "one_per_unit")
MISSING = ("not_evaluated", "exclude")
MEASUREMENT_STATES = ("supported", "refuted", "inconclusive", "not_evaluated")
RETRIEVAL_ROUTES = ("source", "pubmed", "ncbi", "literature", "uniprot", "pdb", "interpro", "atlas")
INSPECTION_ROUTES = ("read_output", "schema", "reflect", "genome_reflect")
COMPUTE_ROUTES = ("instrument", "experiment", "genome", "representation", "regulatory_genome", "campaign", "native")
MAX_REVISIONS = 3
MAX_PATH = 8
MAX_CONTRACT_CHARS = 3000
FISHER_MAX_TOTAL = 20000
Z95 = 1.959963984540054
TRUTH = ("a computational measurement by his own instrument under a frozen contract; not experimental "
         "biological validation")
NOVELTY_NOTE = ("candidate only: what was searched is listed with the finding; a zero-hit title search is not a "
                "novelty certificate")

# What the planner and the frontier are told a contract is. Kept short: it rides in a local prompt and a paid one.
SPEC = ("measurement (optional, set it before measuring): a frozen contract for how your prediction will be judged. "
        "{mode:'confirmatory'|'exploratory', hypothesis, unit (the experimental unit), variable, units, "
        "evaluator:'proportion_vs_control'|'structural_measure'|'reproducibility', predicts "
        "(proportion: case_higher|case_lower|no_difference; structural: above|below; reproducibility: "
        "reproduces|differs), min_effect or margin (proportion), threshold and uncertainty (structural), tolerance "
        "and relative (reproducibility), independence:'records'|'one_per_unit' (with unit_key), missing:"
        "'not_evaluated'|'exclude', supports, opposes, and roles case+control (proportion) or measure (+reference). "
        "A role: {select:{tool, nth} or {plan_step}, meaning, and hits+total (paths) or records (path) with "
        "positive:{field (path), equals|at_least|is_true}, or value (path) with optional unit_field, "
        "uncertainty_field}. A path is a list of exact output keys/indices. Numbers only; never code. A reference "
        "may be {value, citation}. Outputs you already have can never confirm it.")
EXAMPLE = {"mode": "confirmatory", "hypothesis": "array-adjacent RTs are commoner in phage loci than in matched "
           "background loci", "unit": "locus", "variable": "share of loci with a CRISPR array within 12 kb",
           "units": "proportion", "evaluator": "proportion_vs_control", "predicts": "case_higher", "min_effect": 0.1,
           "independence": "one_per_unit", "unit_key": ["votu"], "missing": "not_evaluated",
           "supports": "case share exceeds control by at least 0.1", "opposes": "the interval rules out a 0.1 excess",
           "case": {"select": {"tool": "rt_locus_screen", "nth": 1}, "records": ["result", "loci"],
                    "positive": {"field": ["beside_crispr_array"], "is_true": True}, "meaning": "phage loci screened"},
           "control": {"select": {"tool": "rt_locus_screen", "nth": 2}, "records": ["result", "loci"],
                       "positive": {"field": ["beside_crispr_array"], "is_true": True},
                       "meaning": "matched background loci"}}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _root():
    """The Lab's own directory: the one chemistry_lab is using when it is loaded, else this workspace's."""
    lab = sys.modules.get("chemistry_lab")
    return getattr(lab, "ROOT", None) or LAB


def contracts_path(): return os.path.join(_root(), CONTRACTS_NAME)
def results_path(): return os.path.join(_root(), RESULTS_NAME)


@contextlib.contextmanager
def _locked():
    os.makedirs(_root(), exist_ok=True)
    with open(os.path.join(_root(), ".measurement.lock"), "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _rows(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try: out.append(json.loads(line))
                except ValueError: continue
    except OSError:
        pass
    return out


def _append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# --- The contract: typed, bounded, frozen ---------------------------------------------------------------------------

def _text(value, cap=300):
    return str(value or "").strip()[:cap]


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _path(value):
    if not isinstance(value, list) or not 0 < len(value) <= MAX_PATH:
        return None
    out = []
    for key in value:
        if isinstance(key, bool) or not isinstance(key, (str, int)) or (isinstance(key, str) and not key.strip()):
            return None
        out.append(key if isinstance(key, int) else key.strip()[:80])
    return out


def _selector(value, errors, role):
    sel = value if isinstance(value, dict) else {}
    if "plan_step" in sel:
        n = sel.get("plan_step")
        if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 8:
            return {"plan_step": n}
        errors.append("%s: plan_step must be a step number 1-8" % role)
        return None
    if "step" in sel and _text(sel.get("step"), 40):
        return {"step": _text(sel.get("step"), 40)}
    tool = _text(sel.get("tool"), 80)
    nth = sel.get("nth", 1)
    if tool and isinstance(nth, int) and not isinstance(nth, bool) and 1 <= nth <= 20:
        return {"tool": tool, "nth": nth}
    return {} if not sel else (errors.append("%s: select needs a tool (and nth 1-20), a plan_step or a step" % role)
                               or None)


def _role(value, kind, errors, name):
    if not isinstance(value, dict):
        errors.append("%s: missing" % name)
        return None
    role = {"meaning": _text(value.get("meaning"), 200)}
    if not role["meaning"]:
        errors.append("%s: a criterion must say what its output field means" % name)
    sel = _selector(value.get("select"), errors, name)
    if sel is None:
        return None
    role["select"] = sel
    for opt in ("cohort_field", "unit_field", "uncertainty_field"):
        if value.get(opt) is not None:
            p = _path(value.get(opt))
            if p is None: errors.append("%s: %s must be a path of exact keys" % (name, opt))
            else: role[opt] = p
    if kind == "proportion":
        if value.get("records") is not None:
            p = _path(value.get("records"))
            pos = value.get("positive") if isinstance(value.get("positive"), dict) else {}
            field = _path(pos.get("field"))
            rule = {k: pos[k] for k in ("equals", "at_least", "is_true") if k in pos}
            if p is None or field is None or len(rule) != 1:
                errors.append("%s: records needs a path and positive {field, one of equals|at_least|is_true}" % name)
                return None
            (rk, rv), = rule.items()
            if rk == "at_least" and _number(rv) is None:
                errors.append("%s: at_least must be a number" % name); return None
            if rk == "equals" and not (isinstance(rv, (str, int, float, bool)) or rv is None):
                errors.append("%s: equals must be a plain value" % name); return None
            if rk == "is_true" and rv is not True:
                errors.append("%s: is_true must be true" % name); return None
            role.update(records=p, positive={"field": field, rk: rv})
        else:
            hits, total = _path(value.get("hits")), _path(value.get("total"))
            if hits is None or total is None:
                errors.append("%s: give hits and total paths, or records with a positive rule" % name)
                return None
            role.update(hits=hits, total=total)
    else:
        p = _path(value.get("value"))
        if p is None:
            errors.append("%s: value must be a path of exact output keys" % name)
            return None
        role["value"] = p
    return role


def _disagreement_id(value):
    """DIS- and ten lowercase hex digits: the id lab_disagreement.declare gives."""
    return len(value) == 14 and value.startswith("DIS-") and all(ch in "0123456789abcdef" for ch in value[4:])


def normalize(raw):
    """(contract, errors). The contract holds only typed, bounded fields; anything else is dropped."""
    errors = []
    if not isinstance(raw, dict):
        return None, ["not a contract object"]
    if len(json.dumps(raw, default=str)) > MAX_CONTRACT_CHARS:
        return None, ["contract longer than %d characters" % MAX_CONTRACT_CHARS]
    mode = _text(raw.get("mode") or "confirmatory", 20).lower()
    if mode not in MODES:
        errors.append("mode must be confirmatory or exploratory")
        mode = "confirmatory"
    c = {"mode": mode, "hypothesis": _text(raw.get("hypothesis"), 400), "unit": _text(raw.get("unit"), 120),
         "variable": _text(raw.get("variable"), 200), "units": _text(raw.get("units"), 40),
         "supports": _text(raw.get("supports"), 300), "opposes": _text(raw.get("opposes"), 300)}
    if not c["hypothesis"]:
        errors.append("a contract states its hypothesis")
    # a measurement chosen to separate two readers' frozen predictions (lab_disagreement) names that disagreement;
    # it is kept only in its exact form, so a contract without it is byte-for-byte what it was before
    dis = _text(raw.get("disagreement"), 20)
    if dis:
        if _disagreement_id(dis): c["disagreement"] = dis
        else: errors.append("disagreement must be a declared id like DIS-0123456789")
    if mode == "exploratory":
        return c, errors
    for key in ("unit", "variable", "units", "supports", "opposes"):
        if not c[key]:
            errors.append("a confirmatory contract names its %s" % key)
    ev = _text(raw.get("evaluator"), 40)
    if ev not in EVALUATORS:
        errors.append("evaluator must be one of " + ", ".join(EVALUATORS))
        return c, errors
    c["evaluator"] = ev
    predicts = _text(raw.get("predicts"), 30)
    if predicts not in PREDICTS[ev]:
        errors.append("predicts must be one of " + ", ".join(PREDICTS[ev]))
    c["predicts"] = predicts
    if raw.get("cohort_digest") is not None:
        c["cohort_digest"] = _text(raw.get("cohort_digest"), 128)
    missing = _text(raw.get("missing") or "not_evaluated", 20)
    if missing not in MISSING:
        errors.append("missing must be not_evaluated or exclude")
    c["missing"] = missing
    if ev == "proportion_vs_control":
        indep = _text(raw.get("independence") or "records", 20)
        if indep not in INDEPENDENCE:
            errors.append("independence must be records or one_per_unit")
        c["independence"] = indep
        if indep == "one_per_unit":
            key = _path(raw.get("unit_key"))
            if key is None: errors.append("one_per_unit needs unit_key, a path inside each record")
            else: c["unit_key"] = key
        if predicts == "no_difference":
            m = _number(raw.get("margin"))
            if m is None or not 0 < m < 1: errors.append("no_difference needs a margin between 0 and 1")
            c["margin"] = m
        else:
            m = _number(raw.get("min_effect", 0))
            if m is None or not 0 <= m < 1: errors.append("min_effect must be between 0 and 1")
            c["min_effect"] = m
        if "control" not in raw:
            errors.append("a proportion has no meaning without its comparator: name the control")
        c["case"] = _role(raw.get("case"), "proportion", errors, "case")
        c["control"] = _role(raw.get("control"), "proportion", errors, "control")
    elif ev == "structural_measure":
        t, u = _number(raw.get("threshold")), _number(raw.get("uncertainty", 0))
        if t is None: errors.append("structural_measure needs a numeric threshold (the comparator)")
        if u is None or u < 0: errors.append("uncertainty must be a number >= 0")
        c.update(threshold=t, uncertainty=u)
        c["measure"] = _role(raw.get("measure"), "value", errors, "measure")
    else:
        tol = _number(raw.get("tolerance"))
        if tol is None or tol < 0: errors.append("reproducibility needs a tolerance >= 0")
        c.update(tolerance=tol, relative=bool(raw.get("relative")))
        c["measure"] = _role(raw.get("measure"), "value", errors, "measure")
        ref = raw.get("reference")
        if isinstance(ref, dict) and "select" not in ref:
            v = _number(ref.get("value"))
            if v is None or not _text(ref.get("citation"), 300):
                errors.append("a declared reference needs a numeric value and its citation")
            c["reference"] = {"value": v, "citation": _text(ref.get("citation"), 300)}
        else:
            if ref is None: errors.append("reproducibility needs a reference: a rerun or a cited value")
            c["reference"] = _role(ref, "value", errors, "reference")
    return c, errors


def contracts():
    return _rows(contracts_path())


def results():
    return _rows(results_path())


def latest(contract_id, rows=None):
    found = None
    for row in rows if rows is not None else contracts():
        if row.get("contract_id") == contract_id:
            found = row
    return found


def _binding_id(investigation_id, plan_id, step_index):
    return "MC-" + hashlib.sha256(("%s|%s|%s" % (investigation_id or "", plan_id or "",
                                                  "" if step_index is None else step_index)).encode()).hexdigest()[:12]


def freeze(raw, *, by, investigation_id=None, line_id=None, plan_id=None, step_index=None, existing_steps=(),
           now=None):
    """Freeze a contract (a new revision when it differs from the last). Returns the stored row, or the unchanged
    current row when nothing differs. A contract that fails validation is stored as refused, with its reasons: the
    investigation goes on exploratory, nothing is blocked."""
    contract, errors = normalize(raw)
    cid = _binding_id(investigation_id, plan_id, step_index)
    with _locked():
        rows = contracts()
        current = latest(cid, rows)
        if current and contract is not None and current.get("contract") == contract and not errors:
            return current
        revision = int((current or {}).get("revision") or 0) + 1
        if revision > MAX_REVISIONS:
            return dict(current, refused_revision="at most %d revisions; a new question is a new investigation"
                        % MAX_REVISIONS)
        status = ("refused" if errors and (contract or {}).get("mode") != "exploratory"
                  else "exploratory" if (contract or {}).get("mode") == "exploratory" else "frozen")
        if status == "refused" and current and current.get("status") == "frozen":
            # an invalid restatement never displaces a valid frozen contract
            return dict(current, refused_revision="; ".join(errors)[:300])
        prior_results = [r for r in results() if r.get("contract_id") == cid]
        row = {"kind": "measurement_contract", "contract_id": cid, "revision": revision, "status": status,
               "frozen_at": now or _now(), "by": _text(by, 60), "investigation": investigation_id,
               "line_id": line_id, "plan_id": plan_id, "step_index": step_index,
               "frozen_after_steps": [str(s) for s in existing_steps][:200],
               "contract": contract, "errors": errors[:12],
               **({"supersedes": current.get("revision")} if current else {}),
               **({"post_hoc": "revised after revision %s was measured; outputs that existed then cannot confirm it"
                               % prior_results[-1].get("revision")} if prior_results else {})}
        row["contract_sha256"] = _sha(contract)
        _append(contracts_path(), row)
        return row


# --- Reading an output: exact paths, hashes checked ---------------------------------------------------------------

class _Missing(Exception):
    pass


def _get(payload, path):
    out = payload
    for key in path:
        try:
            out = out[int(key)] if isinstance(out, list) else out[key]
        except (KeyError, IndexError, TypeError, ValueError):
            raise _Missing("field %s is not in the output" % json.dumps(path))
    return out


def _tool_matches(step, tool):
    have = str(step.get("tool") or "")
    return bool(tool) and (have == tool or have.split(":", 1)[-1] == tool or have.endswith("." + tool)
                           or have.endswith(":" + tool))


def _origin(step, by_id):
    """The step whose execution produced this output: a repeat points back to it."""
    seen = 0
    while step.get("reused_from") and step["reused_from"] in by_id and seen < 10:
        step, seen = by_id[step["reused_from"]], seen + 1
    return step


def _select(sel, steps, row):
    """(chosen step or None, attempted steps). Only steps after the freeze are candidates for tool/plan selection."""
    before = set(row.get("frozen_after_steps") or [])
    if "step" in sel:
        chosen = [s for s in steps if s.get("id") == sel["step"]]
        return (chosen[0] if chosen and chosen[0].get("state") == "completed" else None), chosen
    if "plan_step" in sel:
        cands = [s for s in steps if (s.get("plan_ref") or {}).get("plan_id") == row.get("plan_id")
                 and (s.get("plan_ref") or {}).get("step_index") == sel["plan_step"] - 1]
        done = [s for s in cands if s.get("state") == "completed"]
        return (done[0] if done else None), cands
    if "tool" in sel:
        cands = [s for s in steps if s.get("id") not in before and _tool_matches(s, sel["tool"])]
        done = [s for s in cands if s.get("state") == "completed"]
        n = sel.get("nth", 1)
        return (done[n - 1] if len(done) >= n else None), cands
    return None, []


def _default_select(row):
    if row.get("plan_id") and row.get("step_index") is not None:
        return {"plan_step": int(row["step_index"]) + 1}
    return {}


def _roles(contract):
    ev = contract.get("evaluator")
    if ev == "proportion_vs_control":
        return {"case": contract.get("case"), "control": contract.get("control")}
    out = {"measure": contract.get("measure")}
    ref = contract.get("reference")
    if isinstance(ref, dict) and "select" in ref:
        out["reference"] = ref
    return out


def _route_kind(step):
    route = str(step.get("route") or "")
    tool = str(step.get("tool") or "")
    if route in COMPUTE_ROUTES:
        return "new_computation"
    if route in RETRIEVAL_ROUTES or tool.startswith("source:"):
        return "source_retrieval"
    if route in INSPECTION_ROUTES:
        return "inspection"
    if route == "plugin":
        return "connector"
    return "other"


def _counts(role, payload, contract, name):
    """(hits, total, excluded, detail) for one proportion role."""
    if "hits" in role:
        if contract.get("independence") == "one_per_unit":
            raise ValueError("%s: the contract counts one per %s, and bare counts cannot show which records are "
                             "related" % (name, json.dumps(contract.get("unit_key"))))
        hits, total = _get(payload, role["hits"]), _get(payload, role["total"])
        for v in (hits, total):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v != int(v):
                raise ValueError("%s: a count must be a whole number >= 0, got %r" % (name, v))
        hits, total = int(hits), int(total)
        if total == 0 or hits > total:
            raise ValueError("%s: %d of %d is not a proportion" % (name, hits, total))
        return hits, total, 0, {"hits": hits, "total": total}
    records = _get(payload, role["records"])
    if not isinstance(records, list):
        raise ValueError("%s: records field is not a list" % name)
    pos = role["positive"]
    groups, order, excluded = {}, [], 0
    for i, rec in enumerate(records):
        try:
            value = _get(rec, pos["field"])
        except _Missing:
            if contract.get("missing") == "exclude":
                excluded += 1
                continue
            raise ValueError("%s: record %d lacks %s and the contract does not exclude missing values"
                             % (name, i, json.dumps(pos["field"])))
        if "at_least" in pos:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("%s: record %d has a non-numeric %r" % (name, i, value))
            positive = value >= pos["at_least"]
        elif "is_true" in pos:
            if not isinstance(value, bool):
                raise ValueError("%s: record %d has %r where true/false was declared" % (name, i, value))
            positive = value
        else:
            positive = value == pos["equals"]
        if contract.get("independence") == "one_per_unit":
            try:
                key = json.dumps(_get(rec, contract["unit_key"]), sort_keys=True)
            except _Missing:
                raise ValueError("%s: record %d has no %s, so its independence is unknown"
                                 % (name, i, json.dumps(contract["unit_key"])))
        else:
            key = "#%d" % i
        if key not in groups:
            order.append(key)
        groups[key] = groups.get(key, False) or bool(positive)   # a group counts once: positive if any member is
    total = len(order)
    hits = sum(1 for k in order if groups[k])
    if total == 0:
        raise ValueError("%s: no units left to count" % name)
    return hits, total, excluded, {"hits": hits, "total": total, "records": len(records), "excluded": excluded,
                                   "units_counted": total}


def _wilson(k, n):
    p = k / n
    den = 1 + Z95 ** 2 / n
    centre = (p + Z95 ** 2 / (2 * n)) / den
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95 ** 2 / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def newcombe(k1, n1, k2, n2):
    """Difference p1 - p2 with the Newcombe hybrid score 95% interval."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = _wilson(k1, n1)
    l2, u2 = _wilson(k2, n2)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, lo, hi


def fisher_p(k1, n1, k2, n2):
    """Two-sided Fisher exact p for a 2x2 table; None past FISHER_MAX_TOTAL."""
    n = n1 + n2
    if n > FISHER_MAX_TOTAL:
        return None
    k = k1 + k2
    lo, hi = max(0, k - n2), min(k, n1)
    def logp(x):
        return (math.lgamma(n1 + 1) - math.lgamma(x + 1) - math.lgamma(n1 - x + 1) + math.lgamma(n2 + 1)
                - math.lgamma(k - x + 1) - math.lgamma(n2 - k + x + 1) - math.lgamma(n + 1) + math.lgamma(k + 1)
                + math.lgamma(n - k + 1))
    observed = logp(k1)
    total = sum(math.exp(logp(x)) for x in range(lo, hi + 1) if logp(x) <= observed + 1e-7)
    return min(1.0, total)


def _value(role, payload, contract, name):
    v = _get(payload, role["value"])
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("%s: %r is not a finite number" % (name, v))
    if role.get("unit_field"):
        have = str(_get(payload, role["unit_field"]) or "").strip().lower()
        if have != str(contract.get("units") or "").strip().lower():
            raise ValueError("%s: the output is in %r and the contract in %r" % (name, have, contract.get("units")))
    unc = None
    if role.get("uncertainty_field"):
        unc = _get(payload, role["uncertainty_field"])
        if isinstance(unc, bool) or not isinstance(unc, (int, float)) or not math.isfinite(unc) or unc < 0:
            raise ValueError("%s: uncertainty %r is not a number >= 0" % (name, unc))
    return float(v), unc


def _judge(contract, data):
    """(measurement_state, estimate, why). Deterministic; nothing a model wrote is executed."""
    ev, predicts = contract["evaluator"], contract["predicts"]
    if ev == "proportion_vs_control":
        (k1, n1, _, c_detail), (k2, n2, _, k_detail) = data["case"], data["control"]
        d, lo, hi = newcombe(k1, n1, k2, n2)
        est = {"case": c_detail, "control": k_detail, "case_share": round(k1 / n1, 4),
               "control_share": round(k2 / n2, 4), "difference": round(d, 4), "ci95": [round(lo, 4), round(hi, 4)],
               "fisher_p": (lambda p: None if p is None else round(p, 6))(fisher_p(k1, n1, k2, n2)),
               "interval": "Newcombe hybrid score, 95%"}
        if predicts == "no_difference":
            m = contract["margin"]
            if -m < lo and hi < m:
                return "supported", est, "the whole interval lies within ±%g" % m
            if (lo > 0 or hi < 0) and abs(d) >= m:
                return "refuted", est, "a difference of %+.3g, interval excluding zero and beyond the ±%g margin" % (d, m)
            return "inconclusive", est, "the interval neither fits inside nor excludes the ±%g margin" % m
        sign = 1 if predicts == "case_higher" else -1
        m = contract.get("min_effect") or 0.0
        slo, shi = (lo, hi) if sign == 1 else (-hi, -lo)
        if slo > 0 and sign * d >= m:
            return "supported", est, "the interval excludes no difference in the predicted direction"
        if shi < m:
            return "refuted", est, ("the interval rules out an effect of %g in the predicted direction" % m if m
                                    else "the interval excludes zero in the opposite direction")
        return "inconclusive", est, "the interval is too wide to decide"
    if ev == "structural_measure":
        v, unc = data["measure"]
        u = unc if unc is not None else (contract.get("uncertainty") or 0.0)
        t = contract["threshold"]
        est = {"value": v, "uncertainty": u, "threshold": t, "units": contract.get("units")}
        if predicts == "below":
            if v + u < t: return "supported", est, "%g ± %g lies below %g" % (v, u, t)
            if v - u >= t: return "refuted", est, "%g ± %g is not below %g" % (v, u, t)
        else:
            if v - u > t: return "supported", est, "%g ± %g lies above %g" % (v, u, t)
            if v + u <= t: return "refuted", est, "%g ± %g is not above %g" % (v, u, t)
        return "inconclusive", est, "the uncertainty straddles the threshold"
    v, _ = data["measure"]
    ref = data.get("reference")
    if ref is None:
        ref = (contract["reference"]["value"], None)
    r = ref[0]
    tol = contract["tolerance"] * (abs(r) if contract.get("relative") else 1.0)
    within = abs(v - r) <= tol
    est = {"value": v, "reference": r, "difference": v - r, "tolerance": tol, "units": contract.get("units")}
    if predicts == "reproduces":
        return ("supported", est, "within tolerance") if within else ("refuted", est, "outside the stated tolerance")
    return ("supported", est, "outside the stated tolerance") if not within else ("refuted", est, "within tolerance")


def _load_output(step, root):
    path = os.path.join(root, str(step.get("output_file") or ""))
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if _sha(payload) != step.get("output_sha256"):
        raise ValueError("output %s changed after it was retained" % step.get("id"))
    return payload


def evaluate(row, steps, *, final=False, load=None, now=None):
    """One contract revision against an investigation's steps. Returns a result row, or None while the outputs it
    names have not been produced yet (and final is False). Never raises."""
    load = load or (lambda s: _load_output(s, _root()))
    contract = row.get("contract") or {}
    base = {"at": now or _now(), "kind": "measurement_result", "contract_id": row.get("contract_id"),
            "revision": row.get("revision"), "contract_sha256": row.get("contract_sha256"),
            "investigation": row.get("investigation"), "line_id": row.get("line_id"), "plan_id": row.get("plan_id"),
            "step_index": row.get("step_index"), "hypothesis": contract.get("hypothesis"),
            "evaluator": contract.get("evaluator"), "predicts": contract.get("predicts"),
            "execution_state": "not_run", "measurement_state": "not_evaluated", "novelty_state": "not_assessed",
            "truth_status": TRUTH, "confirmatory": False, "bound": [],
            **({"disagreement": contract["disagreement"]} if contract.get("disagreement") else {})}

    def done(state, why, **extra):
        return dict(base, measurement_state=state, why=str(why)[:400], **extra)

    try:
        if _sha(contract) != row.get("contract_sha256"):
            return done("not_evaluated", "the contract changed after it was frozen; it judges nothing")
        if row.get("status") != "frozen":
            return None
        by_id = {s.get("id"): s for s in steps}
        data, bound, attempts, kinds = {}, [], [], []
        for name, role in _roles(contract).items():
            sel = role.get("select") or _default_select(row)
            if not sel:
                return done("not_evaluated", "%s names no step to measure" % name)
            chosen, tried = _select(sel, steps, row)
            attempts += tried
            if chosen is None:
                failed = [s for s in tried if s.get("state") in ("failed", "outcome_unknown")]
                if failed and final:
                    base["execution_state"] = failed[-1]["state"]
                    return done("not_evaluated", "the tool did not produce the %s output (%s); this says nothing "
                                "about the hypothesis" % (name, str(failed[-1].get("error") or "")[:160]))
                if not final:
                    return None
                return done("not_evaluated", "no completed output for %s was produced" % name)
            payload = load(chosen)
            origin = _origin(chosen, by_id)
            bound.append({"role": name, "step": chosen.get("id"), "origin_step": origin.get("id"),
                          "tool": chosen.get("tool"), "route": chosen.get("route"),
                          "output_sha256": chosen.get("output_sha256")})
            kinds.append(_route_kind(origin))
            base["bound"] = bound
            base["execution_state"] = "completed"
            if contract.get("cohort_digest"):
                if not role.get("cohort_field"):
                    return done("not_evaluated", "%s: the contract names a cohort and the role does not say where "
                                "the output records its cohort" % name)
                have = _get(payload, role["cohort_field"])
                if have != contract["cohort_digest"]:
                    return done("not_evaluated", "%s was measured on a different cohort (%s, not %s)"
                                % (name, str(have)[:24], contract["cohort_digest"][:24]))
            data[name] = (_counts(role, payload, contract, name) if contract["evaluator"] == "proportion_vs_control"
                          else _value(role, payload, contract, name))
        state, est, why = _judge(contract, data)
        before = set(row.get("frozen_after_steps") or [])
        pre = [b["step"] for b in bound if b["step"] in before or b["origin_step"] in before]
        # a revision measured on a fresh holdout can confirm; nothing measured on outputs it had seen can
        confirmatory = contract.get("mode") == "confirmatory" and not pre
        known = (contract.get("evaluator") == "reproducibility" and isinstance(contract.get("reference"), dict)
                 and contract["reference"].get("citation") and state == "supported"
                 and contract.get("predicts") == "reproduces")
        if known:
            novelty = "reproduced_known_result"
        elif kinds and all(k == "source_retrieval" for k in kinds):
            novelty = "source_retrieval"
        elif state == "supported" and "new_computation" in kinds:
            novelty = "candidate_computational_finding"
        elif state == "refuted":
            novelty = "negative_result"
        else:
            novelty = "not_assessed"
        return done(state, why, estimate=est, confirmatory=confirmatory, novelty_state=novelty,
                    negative=state == "refuted",
                    **({"confirmatory_why": "measured on outputs that existed before the contract was frozen: %s"
                        % ", ".join(pre)} if pre else {}),
                    **({"post_hoc": row["post_hoc"]} if row.get("post_hoc") else {}),
                    **({"novelty_note": NOVELTY_NOTE} if novelty == "candidate_computational_finding" else {}))
    except (_Missing, ValueError) as exc:
        return done("not_evaluated", exc)
    except (OSError, TypeError, KeyError) as exc:
        return done("not_evaluated", "the output could not be read: %s" % str(exc)[:200])


def verify(result, steps, load=None):
    """Whether a stored result still stands: every bound output still hashes to what it was measured on."""
    load = load or (lambda s: _load_output(s, _root()))
    by_id = {s.get("id"): s for s in steps}
    for b in result.get("bound") or []:
        step = by_id.get(b.get("step"))
        if step is None or step.get("output_sha256") != b.get("output_sha256"):
            return False
        try: load(step)
        except Exception: return False
    return True


# --- Settling: evaluate what can be evaluated, once per revision --------------------------------------------------

def _active(rows):
    last = {}
    for row in rows:
        last[row.get("contract_id")] = row
    return list(last.values())


def _concerns(row, investigation):
    if row.get("investigation") and row["investigation"] == investigation.get("id"):
        return True
    return bool(row.get("plan_id")) and any((s.get("plan_ref") or {}).get("plan_id") == row["plan_id"]
                                            for s in investigation.get("steps") or [])


def settle(investigation, now=None):
    """Evaluate the frozen contracts this investigation's steps bear on. Final when it is no longer open."""
    out = []
    final = investigation.get("state") not in (None, "open")
    with _locked():
        settled = {(r.get("contract_id"), r.get("revision")) for r in results()}
        for row in _active(contracts()):
            if row.get("status") != "frozen" or (row.get("contract_id"), row.get("revision")) in settled:
                continue
            if not _concerns(row, investigation):
                continue
            res = evaluate(row, investigation.get("steps") or [], final=final, now=now)
            if res is not None:
                res["investigation"] = res.get("investigation") or investigation.get("id")
                _append(results_path(), res)
                out.append(res)
    if any(r.get("disagreement") for r in out):
        try:    # a measurement that was chosen to separate two predictions is judged against them now
            import lab_disagreement
            lab_disagreement.settle()
        except Exception:
            pass
    return out


def settle_closed(load_investigations=None, now=None):
    """Settle frozen contracts whose investigations have closed since; reads the investigations store only when one
    is waiting."""
    settled = {(r.get("contract_id"), r.get("revision")) for r in results()}
    waiting = [r for r in _active(contracts()) if r.get("status") == "frozen"
               and (r.get("contract_id"), r.get("revision")) not in settled]
    if not waiting:
        return []
    if load_investigations is None:
        def load_investigations():
            try:
                with open(os.path.join(_root(), "investigations.json"), encoding="utf-8") as f:
                    return json.load(f).get("investigations") or []
            except (OSError, ValueError):
                return []
    out = []
    for inv in load_investigations():
        if inv.get("state") != "open" and any(_concerns(r, inv) for r in waiting):
            out += settle(inv, now)
    return out


# --- What he and the Lab are shown ----------------------------------------------------------------------------------

def _brief(res):
    return {k: res.get(k) for k in ("contract_id", "revision", "hypothesis", "measurement_state", "execution_state",
                                     "novelty_state", "confirmatory", "why", "estimate") if res.get(k) is not None}


def negatives(limit=5):
    """His kept negative results: clean measurements that contradicted the prediction."""
    return [r for r in results() if r.get("measurement_state") == "refuted"][-limit:]


def for_investigation(investigation):
    ids = {investigation.get("id")}
    plans = {(s.get("plan_ref") or {}).get("plan_id") for s in investigation.get("steps") or []} - {None}
    return [r for r in results() if r.get("investigation") in ids or (r.get("plan_id") and r["plan_id"] in plans)]


def planner_view(investigation, now=None):
    """What the investigation planner is shown: the frozen contract and its result, or how to state one; and his
    recent negative results. None when there is nothing to show. Never raises."""
    try:
        if not (investigation.get("steps") or []):
            settle_closed(now=now)
        settle(investigation, now)
        mine = [r for r in _active(contracts()) if r.get("investigation") == investigation.get("id")]
        view = {}
        if mine:
            row = mine[-1]
            c = row.get("contract") or {}
            view["contract"] = {"revision": row.get("revision"), "status": row.get("status"),
                                "hypothesis": c.get("hypothesis"), "evaluator": c.get("evaluator"),
                                "predicts": c.get("predicts"), "supports": c.get("supports"),
                                "opposes": c.get("opposes"),
                                **({"errors": row.get("errors")} if row.get("errors") else {})}
            res = [r for r in results() if r.get("contract_id") == row.get("contract_id")]
            if res:
                view["result"] = _brief(res[-1])
            view["rule"] = ("frozen: a revised prediction is a new revision, and outputs you already have cannot "
                            "confirm it. A refuted prediction is a result, not a failure.")
        elif len(investigation.get("steps") or []) < 3:
            view["how"] = SPEC
        neg = [_brief(r) for r in negatives(4) if r.get("investigation") != investigation.get("id")][-2:]
        if neg:
            view["your_negative_results"] = neg
        try:    # two of his readings that predicted incompatible values, and how to measure between them
            import lab_disagreement
            lab_disagreement.settle()
            dis = lab_disagreement.for_planner()
            if dis:
                view["disagreements"] = dis
                if "how" not in view and "contract" not in view:
                    view["how"] = SPEC
        except Exception:
            pass
        return view or None
    except Exception:
        return None


def from_planner(investigation, value, now=None):
    """Freeze the contract the planner returned with its prediction, if any. Never raises."""
    try:
        raw = (value or {}).get("measurement") if isinstance(value, dict) else None
        if not isinstance(raw, dict) or not raw:
            return None
        return freeze(raw, by="gemma", investigation_id=investigation.get("id"), line_id=investigation.get("line_id"),
                      existing_steps=[s.get("id") for s in investigation.get("steps") or []], now=now)
    except Exception:
        return None


def from_plan(line_id, plan_id, plan, by, now=None):
    """Freeze the contracts a frontier plan's steps carry, bound to that plan id and step. Never raises."""
    out = []
    for i, step in enumerate(plan or []):
        raw = step.get("measurement") if isinstance(step, dict) else None
        if isinstance(raw, dict) and raw:
            try:
                out.append(freeze(raw, by="frontier:%s" % by, line_id=line_id, plan_id=plan_id, step_index=i,
                                  now=now))
            except Exception:
                continue
    return out


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "show"
    n = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 10
    if cmd == "settle":
        print(json.dumps([_brief(r) for r in settle_closed()], indent=1, ensure_ascii=False))
    elif cmd == "negatives":
        print(json.dumps([_brief(r) for r in negatives(n)], indent=1, ensure_ascii=False))
    else:
        rows = _active(contracts())[-n:]
        res = {(r.get("contract_id"), r.get("revision")): r for r in results()}
        for row in rows:
            r = res.get((row.get("contract_id"), row.get("revision")))
            print(json.dumps({"contract_id": row.get("contract_id"), "revision": row.get("revision"),
                              "status": row.get("status"), "by": row.get("by"), "frozen_at": row.get("frozen_at"),
                              "contract": row.get("contract"), "errors": row.get("errors"),
                              "result": _brief(r) if r else "not yet measured"}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
