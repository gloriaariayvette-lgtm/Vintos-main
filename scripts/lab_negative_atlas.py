#!/usr/bin/env python3
"""An atlas of useful negative results: what he tested, under which conditions, and why it failed - kept apart from
what merely broke - so a later plan can vary a condition that matters instead of rerunning the same test or
writing the whole subject off.

Codex's proposal 12 (25 October 2026), the smallest proof it describes. The Lab already keeps the pieces: a frozen
measurement contract and its result (lab_measurement: supported / refuted / inconclusive / not_evaluated, with the
execution state beside it), a family panel's verdict (lab_family_panel), and a disagreement's verdict
(lab_disagreement). Prior-output reuse and repeat suppression stop identical operations; neither says whether a
negative was a scientific finding or an infrastructure failure, nor what it does and does not cover.

  classify   - every retained result that is not a support becomes one atlas entry, in one of three classes:
                 refuted           a clean measurement contradicted the prediction under its frozen terms
                 inconclusive      it was measured and the measurement could not decide
                 failed_execution  no measurement of the claim was made: the tool did not produce the output, or
                                   the output could not be measured under the frozen terms. It says nothing about
                                   the claim, and it is never counted as evidence against him.
               Each entry is scoped: the claim, the conditions it was measured under (variable, units, evaluator,
               comparator, tools, cohort, output digests), why it came out as it did, and its limits in words - what
               it does not cover. Derived on read from the stores above; the id is a digest of its source, so the
               same result is always the same entry. Nothing is stored for this but the reuses.
  reuse      - a later investigation plan may build on one exact negative: `builds_on_negative` {id, varies, to,
               why}. It must name a condition the entry was measured under and give it a different value. Same
               value is a rerun and is refused; a failed execution cannot be built on (it can only be retried); a
               reason that turns the negative into "the subject is impossible" is refused. The entry's limits are
               copied into the reuse, so the reuse carries them.
  show       - the investigation planner (local Gemma, through lab_measurement.planner_view, only where it fits) is
               shown at most two entries that share words with its question, each with its limits, and a warning
               when its own frozen contract would repeat a refuted one exactly.

The risk the proposal named - broad pessimistic generalization from a narrow negative - is answered in the record:
every entry says what it holds for and what it does not test, inconclusive is never shown as negative, a broken
tool is never shown as a negative at all, and the only way to build on a negative is to vary one of its conditions.

No model is asked, nothing is fetched, folded, run on the GPU, sent or paid for. It reads the measurement, panel and
disagreement stores, and appends to its one store, negative-reuses.jsonl. Nothing is gated: a refused reuse is
recorded as refused and the investigation plans on as it would have.

    python3 lab_negative_atlas.py show [N] | search <words> | entry <NEG-id> | reuses
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace")))
REUSES_NAME = "negative-reuses.jsonl"
PANEL_RESULTS_NAME = "family-results.jsonl"
PANELS_NAME = "family-panels.jsonl"

CLASSES = ("refuted", "inconclusive", "failed_execution")
BUILDABLE = ("refuted", "inconclusive")
# the conditions a later plan may vary; an entry offers only the ones it was actually measured under
VARIABLE_CONDITIONS = ("tool", "cohort", "threshold", "min_effect", "margin", "tolerance", "uncertainty", "unit",
                       "variable", "units", "independence", "comparator", "positions", "members", "feature")
REUSES_PER_DAY = 3
PLANNER_ENTRIES = 2
# a reuse that writes the subject off is not a reuse of a scoped negative
SWEEPING = re.compile(r"\b(impossible|never (?:works?|happens?|occurs?)|cannot (?:exist|happen|be (?:true|done))|"
                      r"no point|dead[- ]end|give up|abandon|rules? out (?:the )?(?:whole|entire|all)|"
                      r"proves? (?:that )?(?:no|nothing|it (?:is|cannot)))\b", re.I)
WORD = re.compile(r"[a-z0-9][a-z0-9_.-]{2,}")
STOP = set("the and for with that this from are was were has have had not but its into than then them they there "
           "their what which when where who why how does did done can could would should will may might also more "
           "most such only very per one two three under over between across about after before against loci locus "
           "share".split())
TRUTH = ("an index of his own retained results: each entry holds only under the conditions it lists; a refuted "
         "prediction is a computational measurement, not biological proof that the subject is closed")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lab_root():
    """The Lab's directory, resolved exactly as lab_measurement resolves it."""
    try:
        import lab_measurement
        return Path(lab_measurement._root())
    except Exception:
        return WS / "memory" / "chemistry-lab"


def reuses_path(): return lab_root() / REUSES_NAME


def append_ledger(name, row):
    """Append one row to this module's store, named by its file name in the Lab."""
    path = lab_root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@contextlib.contextmanager
def _locked():
    lab_root().mkdir(parents=True, exist_ok=True)
    with open(lab_root() / ".negative-atlas.lock", "a+") as f:
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
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        pass
    return out


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _squash(text, cap=400):
    return " ".join(str(text or "").split())[:cap]


def _id(source, key):
    return "NEG-" + _sha({"source": source, "key": key})[:10]


def _norm(value):
    """A condition value in a comparable form: numbers as numbers, words lowercased, lists sorted."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (list, tuple)):
        return sorted((_norm(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True, default=str))
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in sorted(value.items())}
    return _squash(value, 300).lower()


# ------------------------------------------------------------------ classification

def classify(measurement_state, execution_state):
    """refuted / inconclusive / failed_execution, or None for a support (not a negative)."""
    if measurement_state == "refuted" and execution_state == "completed":
        return "refuted"
    if measurement_state == "inconclusive" and execution_state == "completed":
        return "inconclusive"
    if measurement_state in ("not_evaluated", None) or execution_state != "completed":
        return "failed_execution"
    return None


def _contract_tools(contract):
    tools = []
    for key in ("case", "control", "measure", "reference"):
        sel = ((contract.get(key) or {}).get("select") or {}) if isinstance(contract.get(key), dict) else {}
        if sel.get("tool"):
            tools.append(str(sel["tool"]))
    return tools


def _comparator(contract):
    ev = contract.get("evaluator")
    if ev == "proportion_vs_control":
        return "case against %s" % _squash((contract.get("control") or {}).get("meaning") or "its control", 120)
    if ev == "structural_measure":
        return "%s %s" % (contract.get("predicts"), contract.get("threshold"))
    if ev == "reproducibility":
        ref = contract.get("reference") or {}
        return "reference %s" % (ref.get("citation") or ref.get("meaning") or ref.get("value"))
    return None


def _measurement_conditions(contract, result):
    cond = {"evaluator": contract.get("evaluator"), "predicts": contract.get("predicts"),
            "variable": contract.get("variable"), "units": contract.get("units"), "unit": contract.get("unit"),
            "comparator": _comparator(contract), "tool": _contract_tools(contract) or
            sorted({str(b.get("tool")) for b in result.get("bound") or [] if b.get("tool")}),
            "outputs": [str(b.get("output_sha256") or "")[:16] for b in result.get("bound") or []]}
    for key in ("threshold", "uncertainty", "min_effect", "margin", "tolerance", "independence"):
        if contract.get(key) is not None:
            cond[key] = contract.get(key)
    if contract.get("cohort_digest"):
        cond["cohort"] = contract.get("cohort_digest")
    return {k: v for k, v in cond.items() if v not in (None, "", [])}


def _held_for(cond):
    bits = []
    if cond.get("variable"):
        bits.append("%s%s" % (cond["variable"], " in %s" % cond["units"] if cond.get("units") else ""))
    if cond.get("tool"):
        tools = cond["tool"] if isinstance(cond["tool"], list) else [cond["tool"]]
        bits.append("measured by %s" % ", ".join(str(t) for t in tools))
    if cond.get("comparator"):
        bits.append("against %s" % cond["comparator"])
    if cond.get("cohort"):
        bits.append("on cohort %s" % str(cond["cohort"])[:16])
    if cond.get("outputs"):
        bits.append("on output %s" % ", ".join(cond["outputs"]))
    return "; ".join(bits) or "the single measurement recorded here"


def _limits(cls, cond, confirmatory=True, extra=()):
    held = _held_for(cond)
    if cls == "refuted":
        out = ["holds only for %s" % held,
               "does not test other tools, other cohorts, other thresholds or other units, and is not biological "
               "proof: the subject is not closed by it"]
        if not confirmatory:
            out.append("exploratory: measured on outputs that existed before its contract was frozen, so it could "
                       "have been fitted to them")
    elif cls == "inconclusive":
        out = ["undecided, not negative: the measurement of %s could not separate the prediction from its opposite"
               % held,
               "a narrower uncertainty, more units, or a better-separated variable could decide it; it is no evidence "
               "against the claim"]
    else:
        out = ["no measurement of the claim was made (%s); this says nothing about it either way" % held,
               "retrying the execution is not building on a negative"]
    return out + [str(x)[:300] for x in extra]


def _from_measurements():
    import lab_measurement
    contracts = lab_measurement.contracts()
    out = []
    for res in lab_measurement.results():
        cls = classify(res.get("measurement_state"), res.get("execution_state"))
        if cls is None:
            continue
        cid, rev = res.get("contract_id"), res.get("revision")
        row = next((c for c in contracts if c.get("contract_id") == cid and c.get("revision") == rev), {})
        contract = row.get("contract") or {}
        latest = lab_measurement.latest(cid, contracts) or {}
        cond = _measurement_conditions(contract, res)
        failure = None
        if cls == "failed_execution":
            failure = "tool" if res.get("execution_state") != "completed" else "measurement"
        entry = {"id": _id("measurement", [cid, rev]), "class": cls, "source": "measurement",
                 "source_ref": {"contract_id": cid, "revision": rev}, "at": res.get("at"),
                 "claim": _squash(res.get("hypothesis") or contract.get("hypothesis")),
                 "investigation": res.get("investigation"), "line_id": res.get("line_id"),
                 "plan_id": res.get("plan_id"), "conditions": cond, "why": _squash(res.get("why")),
                 "estimate": res.get("estimate"), "confirmatory": bool(res.get("confirmatory")),
                 "measurement_state": res.get("measurement_state"), "execution_state": res.get("execution_state"),
                 "limits": _limits(cls, cond, bool(res.get("confirmatory"))),
                 "signature": signature(contract)}
        if failure:
            entry["failure"] = failure
        if res.get("disagreement"):
            entry["disagreement"] = res["disagreement"]
        if latest and latest.get("revision") != rev:
            entry["superseded_by_revision"] = latest.get("revision")
        out.append(entry)
    return out


def _from_panels():
    root = lab_root()
    panels = {p.get("panel_id"): p for p in _rows(root / PANELS_NAME)}
    out = []
    for res in _rows(root / PANEL_RESULTS_NAME):
        state = res.get("measurement_state")
        if state not in ("refuted", "inconclusive"):
            continue
        p = panels.get(res.get("panel_id"), {})
        members = [m.get("name") for m in res.get("members") or []]
        comparator = p.get("comparator") or next((m.get("name") for m in res.get("members") or []
                                                  if m.get("role") == "comparator"), None)
        cond = {"evaluator": "family_panel", "variable": "a feature at residue positions in %s numbering"
                % res.get("anchor"), "feature": res.get("feature"), "positions": p.get("positions") or
                [x.get("position") for x in res.get("positions") or []], "members": members,
                "comparator": comparator, "tool": ["lab_family_panel"],
                "outputs": [str(m.get("sha256") or "")[:16] for m in res.get("members") or []]}
        cond = {k: v for k, v in cond.items() if v not in (None, "", [])}
        why = "; ".join("position %s: %s" % (x.get("position"), x.get("state")) for x in res.get("positions") or [])
        out.append({"id": _id("family_panel", [res.get("panel_id"), res.get("measured_at")]), "class": state,
                    "source": "family_panel", "source_ref": {"panel_id": res.get("panel_id"),
                                                             "measured_at": res.get("measured_at")},
                    "at": res.get("measured_at"), "claim": _squash(res.get("question")), "investigation": None,
                    "conditions": cond, "why": _squash(why), "confirmatory": True, "measurement_state": state,
                    "execution_state": "completed",
                    "limits": _limits(state, cond, True, ["only for these members, this comparator and these "
                                                          "positions"] + list(res.get("warnings") or [])[:3])})
    return out


def _from_disagreements():
    try:
        import lab_disagreement
        rows = lab_disagreement.verdicts()
    except Exception:
        return []
    out = []
    for v in rows:
        verdict = v.get("verdict")
        if verdict == "supports_neither":
            cls = "refuted"
        elif verdict == "inconclusive":
            cls = "inconclusive"
        elif verdict == "not_evaluated":
            cls = "failed_execution"
        else:
            continue
        cond = {"evaluator": "disagreement", "variable": v.get("variable"), "units": v.get("units"),
                "comparator": "; ".join("%s predicts %s" % (k, d) for k, d in sorted((v.get("predictions") or {}).items())),
                "tool": sorted({str(b.get("tool")) for b in v.get("bound") or [] if b.get("tool")}),
                "outputs": [str(b.get("output_sha256") or "")[:16] for b in v.get("bound") or []]}
        cond = {k: val for k, val in cond.items() if val not in (None, "", [])}
        entry = {"id": _id("disagreement", [v.get("disagreement_id"), v.get("contract_id"), v.get("revision")]),
                 "class": cls, "source": "disagreement",
                 "source_ref": {"disagreement_id": v.get("disagreement_id"), "contract_id": v.get("contract_id"),
                                "revision": v.get("revision")},
                 "at": v.get("at"), "claim": _squash(v.get("hypothesis") or "two readers' predictions of %s"
                                                      % v.get("variable")),
                 "investigation": v.get("investigation"), "conditions": cond, "why": _squash(v.get("why")),
                 "estimate": v.get("measured"), "confirmatory": cls != "failed_execution",
                 "measurement_state": verdict, "execution_state": v.get("execution_state"),
                 "limits": _limits(cls, cond, True, ["both readers' frozen predictions were contradicted; it says "
                                                     "nothing about a third prediction"] if cls == "refuted" else [])}
        if cls == "failed_execution":
            entry["failure"] = "tool" if v.get("execution_state") != "completed" else "measurement"
        out.append(entry)
    return out


def entries(classes=CLASSES):
    """Every atlas entry, oldest first. Derived on read; never raises."""
    out = []
    for source in (_from_measurements, _from_panels, _from_disagreements):
        try:
            out += source()
        except Exception:
            continue
    seen, uniq = set(), []
    for e in out:
        if e["id"] in seen or e["class"] not in classes:
            continue
        seen.add(e["id"])
        uniq.append(e)
    uniq.sort(key=lambda e: str(e.get("at") or ""))
    return uniq


def entry(neg_id):
    ident = str(neg_id or "").strip()
    for e in entries():
        if e["id"] == ident:
            return e
    raise ValueError("no atlas entry %r" % ident[:40])


def counts():
    out = {c: 0 for c in CLASSES}
    for e in entries():
        out[e["class"]] += 1
    return out


# ------------------------------------------------------------------ searching

def _words(text):
    return {w.strip(".-_") for w in WORD.findall(str(text or "").lower())} - STOP - {""}


def _entry_words(e):
    c = e.get("conditions") or {}
    return _words(" ".join([str(e.get("claim") or ""), str(c.get("variable") or ""), " ".join(c.get("tool") or [])
                            if isinstance(c.get("tool"), list) else str(c.get("tool") or "")]))


def search(query, classes=CLASSES, limit=10):
    """Entries sharing words with the query, most shared first, then newest."""
    want = _words(query)
    if not want:
        return []
    scored = []
    for i, e in enumerate(entries(classes)):
        n = len(want & _entry_words(e))
        if n:
            scored.append((n, i, e))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return [e for _, _, e in scored[:limit]]


# ------------------------------------------------------------------ rerun detection

def signature(contract):
    """What a contract measures, without who froze it or when: two contracts with one signature are one test."""
    contract = contract or {}
    if not contract.get("evaluator"):
        return None
    keys = ("evaluator", "predicts", "variable", "units", "threshold", "min_effect", "margin", "tolerance",
            "independence", "cohort_digest")
    return _sha({"c": {k: _norm(contract.get(k)) for k in keys}, "tools": _norm(_contract_tools(contract))})[:16]


def rerun_of(contract, exclude_investigation=None):
    """The refuted entry this contract would repeat exactly, or None."""
    sig = signature(contract)
    if not sig:
        return None
    for e in reversed(entries(("refuted",))):
        if e.get("signature") == sig and e.get("investigation") != exclude_investigation:
            return e
    return None


# ------------------------------------------------------------------ reuse: a later plan builds on one negative

def reuses(neg_id=None):
    rows = _rows(reuses_path())
    return [r for r in rows if r.get("negative_id") == neg_id] if neg_id else rows


def _value_of(e, key):
    return (e.get("conditions") or {}).get(key)


def reuse(raw, investigation, *, today=None, now=None):
    """Record a plan building on one exact negative. Returns the stored row; refusals are stored too, with the
    reason, and nothing about the investigation is blocked."""
    inv_id = (investigation or {}).get("id")
    base = {"kind": "negative_reuse", "at": now or _now(), "investigation": inv_id,
            "line_id": (investigation or {}).get("line_id"), "question": _squash((investigation or {}).get("question"))}
    raw = raw if isinstance(raw, dict) else {}
    neg_id = _squash(raw.get("id"), 20)
    varies = _squash(raw.get("varies"), 40).lower()
    to = raw.get("to")
    why = _squash(raw.get("why"), 400)
    row = dict(base, negative_id=neg_id, varies=varies, to=to, why=why)

    def refused(reason):
        out = dict(row, state="refused", refused=reason)
        for r in reuses():          # the planner returns its plan every step: one refusal is kept once
            if r.get("state") == "refused" and all(r.get(k) == out.get(k) for k in
                                                   ("investigation", "negative_id", "varies", "to", "refused")):
                return r
        append_ledger(REUSES_NAME, out)
        return out
    with _locked():
        day = str(today or (now or _now())[:10])
        mine = reuses()
        already = [r for r in mine if inv_id and r.get("investigation") == inv_id
                   and r.get("negative_id") == neg_id and r.get("state") == "reused"]
        if already:                          # one investigation builds on one negative once
            return already[-1]
        if len([r for r in mine if str(r.get("at") or "")[:10] == day and r.get("state") == "reused"]) \
                >= REUSES_PER_DAY:
            return refused("%d negatives are built on today already" % REUSES_PER_DAY)
        try:
            e = entry(neg_id)
        except ValueError as exc:
            return refused(str(exc))
        row.update(negative_class=e["class"], claim=e.get("claim"), limits=e.get("limits"))
        if e["class"] not in BUILDABLE:
            return refused("a failed execution is not a negative result: it measured nothing, so it can only be "
                           "retried, not built on")
        if e.get("investigation") and e.get("investigation") == inv_id:
            return refused("this investigation produced that result; building on it is the next investigation's")
        offered = [k for k in VARIABLE_CONDITIONS if _value_of(e, k) not in (None, "", [])]
        if varies not in offered:
            return refused("vary one of the conditions this negative was measured under: %s" % ", ".join(offered))
        if to is None or _squash(to) == "":
            return refused("say what %s becomes: the same test under a changed condition" % varies)
        before = _value_of(e, varies)
        if _norm(to) == _norm(before) or (isinstance(before, list) and len(before) == 1
                                          and _norm(to) == _norm(before[0])):
            return refused("%s is unchanged (%s): that is a rerun of the negative, not a use of it"
                           % (varies, json.dumps(before, default=str)[:80]))
        if len(why) < 12:
            return refused("say why changing %s could change the outcome" % varies)
        if SWEEPING.search(why):
            return refused("a negative holds only under its conditions; it does not make the subject impossible")
        out = dict(row, state="reused", varied={"condition": varies, "from": before, "to": to},
                   scope="this negative holds only under the conditions it lists; the plan changes %s" % varies,
                   truth_status=TRUTH)
        append_ledger(REUSES_NAME, out)
        return out


def outcome(reuse_row):
    """What the reusing investigation has measured since, if anything: its own contract results."""
    try:
        import lab_measurement
        return [lab_measurement._brief(r) for r in lab_measurement.results()
                if reuse_row.get("investigation") and r.get("investigation") == reuse_row["investigation"]]
    except Exception:
        return []


# ------------------------------------------------------------------ what the planner is shown

HOW = ("Your own earlier results that did not support a prediction. Each holds only for what it lists; none closes "
       "the subject or tests another tool, cohort or threshold. Refuted is a real result; inconclusive is undecided, "
       "not negative. Do not rerun one unchanged. To build on one, add to your JSON builds_on_negative: {id, varies "
       "(one of can_vary), to (its new value), why (why that could change the outcome)}.")


def _brief(e):
    """Short: it rides in the local planner's prompt, which drops the whole measurement view when it is too long."""
    c = e.get("conditions") or {}
    return {"id": e["id"], "class": e["class"], "claim": str(e.get("claim") or "")[:160],
            "why": str(e.get("why") or "")[:120], "holds_only_for": _held_for(c)[:220],
            "can_vary": [k for k in VARIABLE_CONDITIONS if c.get(k) not in (None, "", [])][:6],
            **({"exploratory": True} if e["class"] == "refuted" and not e.get("confirmatory") else {})}


def for_planner(investigation, contract=None):
    """At most two entries related to this investigation, with their limits; and a warning when its own frozen
    contract would repeat a refuted one exactly. None when there is nothing to show. Never raises."""
    try:
        inv = investigation or {}
        text = " ".join(str(x or "") for x in (inv.get("question"), inv.get("prediction"),
                                                (inv.get("line_context") or {}).get("question")))
        related = [e for e in search(text, BUILDABLE, limit=8)
                   if e.get("investigation") != inv.get("id") and not e.get("superseded_by_revision")]
        view = {}
        if related:
            view["entries"] = [_brief(e) for e in related[:PLANNER_ENTRIES]]
            view["how"] = HOW
        if contract:
            again = rerun_of(contract, exclude_investigation=inv.get("id"))
            if again:
                view["rerun_warning"] = ("your frozen contract repeats %s exactly (%s), which was refuted: vary a "
                                         "condition it lists, or say why repeating it is a replication"
                                         % (again["id"], str(again.get("why") or "")[:120]))
        return view or None
    except Exception:
        return None


def from_planner(investigation, value, now=None):
    """Record a builds_on_negative the planner returned, if any. Never raises."""
    try:
        raw = value.get("builds_on_negative") if isinstance(value, dict) else None
        if not isinstance(raw, dict) or not raw:
            return None
        return reuse(raw, investigation, now=now)
    except Exception:
        return None


# ------------------------------------------------------------------ CLI

def display(e):
    lines = ["%s  %s  (%s, %s)" % (e["id"], e["class"].upper(), e["source"], str(e.get("at") or "")[:19]),
             "  from: %s" % json.dumps(e.get("source_ref"), ensure_ascii=False, default=str),
             "  claim: %s" % e.get("claim"),
             "  why: %s" % e.get("why")]
    for k, v in sorted((e.get("conditions") or {}).items()):
        lines.append("  %s: %s" % (k, json.dumps(v, ensure_ascii=False, default=str)[:160]))
    for lim in e.get("limits") or []:
        lines.append("  limit: %s" % lim)
    if e.get("superseded_by_revision"):
        lines.append("  superseded by contract revision %s" % e["superseded_by_revision"])
    for r in reuses(e["id"]):
        lines.append("  reused by %s (%s): %s" % (r.get("investigation"), r.get("state"),
                                                  r.get("refused") or r.get("scope")))
    return lines


def _cli(argv):
    cmd = argv[0] if argv else "show"
    if cmd == "show":
        n = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 20
        print(json.dumps(counts()))
        for e in entries()[-n:]:
            print("\n".join(display(e)))
        return 0
    if cmd == "search" and len(argv) > 1:
        for e in search(" ".join(argv[1:])):
            print("\n".join(display(e)))
        return 0
    if cmd == "entry" and len(argv) == 2:
        print(json.dumps(entry(argv[1]), indent=1, ensure_ascii=False, default=str))
        return 0
    if cmd == "reuses":
        print(json.dumps(reuses(), indent=1, ensure_ascii=False, default=str))
        return 0
    print("usage: lab_negative_atlas.py show [N] | search <words> | entry <NEG-id> | reuses")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
