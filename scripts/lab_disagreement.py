#!/usr/bin/env python3
"""Turn a disagreement into the next experiment: two retained readings, their incompatible predictions frozen,
one local measurement that separates them, and which of them - if either - it supports.

Codex's proposal 11 (25 October 2026), the smallest proof it describes. The divergence mode already keeps several
independent readings of one preserved result, made from one identical prompt, and deliberately claims no consensus
(`chemistry_session._run_divergence`, `divergence.jsonl`). Collecting more opinions does not resolve a real
disagreement between them; a measurement does. This module adds the record between the two.

  declare     - from one retained divergence row, two lenses that both read. For each, a predicted observation on
                one named variable in one unit (below / above / between), and a basis: words that lens actually
                wrote, quoted verbatim from its retained reading. The two predictions must not overlap - a value
                that would satisfy both is no disagreement - and the two readings are digested, so a reading that
                changes underneath the record is refused rather than re-judged. Frozen before any measurement.
  bind        - nothing new: the ordinary investigation plan (local Gemma) chooses the measurement and freezes it
                as a lab_measurement contract carrying `disagreement: <DIS-id>`. Only a contract frozen after the
                disagreement, in the same units, measuring one value (structural_measure or reproducibility),
                can judge it.
  adjudicate  - deterministic, once the contract's result exists: the measured value with its uncertainty is an
                interval; per prediction, consistent (inside), contradicted (outside) or undecided (straddling).
                supports_one / supports_neither / inconclusive / not_evaluated. A broken tool says nothing about
                either reader. A result measured on outputs that existed before the contract was frozen cannot
                adjudicate. At most MAX_MEASUREMENTS measurements per disagreement: measuring until one side wins
                is not discrimination.

The two risks the proposal named, and the answer in the record:
  stylistic disagreement posing as competing hypotheses - each prediction is a typed range on one shared variable,
      grounded in a verbatim quote of what that lens wrote; two ranges that overlap are refused at declaration.
  a measurement both predictions accommodate - the verdict is inconclusive whenever the measured interval reaches
      into both ranges, and says so in those words.

No reader is called, nothing is enabled or expanded in the paid multi-reader mode, nothing is folded, fetched or
sent. It reads the divergence store and the measurement stores, and writes its own two append-only stores.

    python3 lab_disagreement.py pairs | show | settle | declare   (declare reads one JSON object on stdin)
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace")))
DIVERGENCE_NAME = "divergence.jsonl"
DISAGREEMENTS_NAME = "disagreements.jsonl"
VERDICTS_NAME = "disagreement-verdicts.jsonl"

READING_FIELDS = ("question", "why_this", "what_you_notice")
MIN_BASIS = 20                 # characters of a lens's own words a prediction must quote
MAX_BASIS = 400
PER_DAY = 2
MAX_MEASUREMENTS = 3
ONE_VALUE = ("structural_measure", "reproducibility")
VERDICTS = ("supports_one", "supports_neither", "inconclusive", "not_evaluated")
TRUTH = ("a local measurement chosen to separate two readers' frozen predictions: it says which prediction the "
         "measured value fits, not which reader is right in general; computational, not experimental validation")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lab_root():
    """The Lab's directory, resolved exactly as lab_measurement resolves it."""
    try:
        import lab_measurement
        return Path(lab_measurement._root())
    except Exception:
        return WS / "memory" / "chemistry-lab"


def divergence_path(): return lab_root() / DIVERGENCE_NAME
def disagreements_path(): return lab_root() / DISAGREEMENTS_NAME
def verdicts_path(): return lab_root() / VERDICTS_NAME


def append_ledger(name, row):
    """Append one row to one of this module's two stores, named by its file name in the Lab."""
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
    with open(lab_root() / ".disagreement.lock", "a+") as f:
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
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _squash(text):
    return " ".join(str(text or "").split())


# ------------------------------------------------------------------ the retained readings it starts from

def _read_lenses(row):
    return {r.get("lens"): r for r in row.get("readings") or []
            if isinstance(r, dict) and r.get("state") == "read"
            and any(_squash(r.get(k)) for k in READING_FIELDS)}


def pairs():
    """Retained divergence rows in which at least two lenses actually read: the material a disagreement is made of."""
    out = []
    for row in _rows(divergence_path()):
        lenses = _read_lenses(row)
        if len(lenses) >= 2:
            out.append({"divergence": row.get("session_id"), "at": row.get("at"), "read_of": row.get("read_of"),
                        "experiment": row.get("experiment"), "lenses": sorted(lenses),
                        "identical_prompt_sha256": row.get("identical_prompt_sha256")})
    return out


def _divergence(session_id):
    for row in _rows(divergence_path()):
        if row.get("session_id") == session_id:
            return row
    raise ValueError("no retained divergence reading %r" % str(session_id)[:40])


def _reading_digest(reading):
    return _sha({k: str(reading.get(k) or "") for k in ("lens",) + READING_FIELDS})


# ------------------------------------------------------------------ a prediction is a range on one variable

def normalize_prediction(raw):
    """{below: x} | {above: x} | {between: [lo, hi]} -> (canonical dict, (lo, hi)). Anything else is refused."""
    if not isinstance(raw, dict):
        raise ValueError("a predicted observation is an object: below, above or between")
    given = [k for k in ("below", "above", "between") if raw.get(k) is not None]
    if len(given) != 1:
        raise ValueError("a predicted observation gives exactly one of below / above / between")
    key = given[0]

    def num(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            raise ValueError("a predicted observation is in numbers, got %r" % (v,))
        return float(v)
    if key == "between":
        pair = raw["between"]
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("between is [low, high]")
        lo, hi = num(pair[0]), num(pair[1])
        if not lo < hi:
            raise ValueError("between needs low < high")
        return {"between": [lo, hi]}, (lo, hi)
    v = num(raw[key])
    return ({key: v}, (-math.inf, v) if key == "below" else (v, math.inf))


def overlap(a, b):
    """True when some value would satisfy both ranges (an open end at the same boundary does not count)."""
    return max(a[0], b[0]) < min(a[1], b[1])


def boundary(a, b):
    """The value between two disjoint ranges: where a threshold separates them."""
    first, second = sorted((a, b))
    return (first[1] + second[0]) / 2.0


def describe(pred):
    if "below" in pred:
        return "below %g" % pred["below"]
    if "above" in pred:
        return "above %g" % pred["above"]
    return "between %g and %g" % tuple(pred["between"])


def disagreements():
    return _rows(disagreements_path())


def verdicts(dis_id=None):
    rows = _rows(verdicts_path())
    return [r for r in rows if r.get("disagreement_id") == dis_id] if dis_id else rows


def disagreement(dis_id):
    ident = str(dis_id or "").strip()
    for row in disagreements():
        if row.get("disagreement_id") == ident:
            return row
    raise ValueError("no declared disagreement %r" % ident[:40])


def declare(raw, *, by="hand", today=None, now=None):
    """Freeze two readers' incompatible predictions before anything measures them. Same content, same id."""
    if not isinstance(raw, dict):
        raise ValueError("a disagreement declaration is an object")
    row = _divergence(str(raw.get("divergence") or "").strip())
    read = _read_lenses(row)
    variable = _squash(raw.get("variable"))[:200]
    units = _squash(raw.get("units"))[:40]
    if len(variable) < 8:
        raise ValueError("name the one variable both predictions are about")
    if not units:
        raise ValueError("name its units: two predictions in different units are not about the same observation")
    given = raw.get("predictions")
    if not isinstance(given, dict) or len(given) != 2:
        raise ValueError("a disagreement is between exactly two lenses")
    predictions, ranges = {}, {}
    for lens, entry in sorted(given.items()):
        if lens not in read:
            raise ValueError("%s did not read in %s; only a lens that actually read can disagree"
                             % (str(lens)[:20], row.get("session_id")))
        if not isinstance(entry, dict):
            raise ValueError("%s: a prediction is an object with predicts and basis" % lens)
        canon, rng = normalize_prediction(entry.get("predicts"))
        basis = _squash(entry.get("basis"))[:MAX_BASIS]
        if len(basis) < MIN_BASIS:
            raise ValueError("%s: quote at least %d characters of what this lens actually wrote" % (lens, MIN_BASIS))
        wrote = " ".join(_squash(read[lens].get(k)) for k in READING_FIELDS)
        if basis not in wrote:
            raise ValueError("%s: the basis is not in this lens's retained reading. A prediction is grounded in "
                             "what the reader wrote, not in what it might have meant" % lens)
        predictions[lens] = {"predicts": canon, "basis": basis, "reading_sha256": _reading_digest(read[lens])}
        ranges[lens] = rng
    a, b = sorted(predictions)
    if predictions[a]["basis"] == predictions[b]["basis"]:
        raise ValueError("both predictions quote the same words: that is one reading, not a disagreement")
    if overlap(ranges[a], ranges[b]):
        raise ValueError("%s (%s) and %s (%s) overlap: a value that satisfies both is no disagreement, and no "
                         "measurement could separate them" % (a, describe(predictions[a]["predicts"]),
                                                              b, describe(predictions[b]["predicts"])))
    frozen = {"divergence": row.get("session_id"), "read_of": row.get("read_of"),
              "experiment": row.get("experiment"), "identical_prompt_sha256": row.get("identical_prompt_sha256"),
              "variable": variable, "units": units, "predictions": predictions,
              "question": _squash(raw.get("question"))[:400] or "which of %s and %s does a measurement of %s support"
              % (a, b, variable)}
    dis_id = "DIS-" + _sha(frozen)[:10]
    for existing in disagreements():
        if existing.get("disagreement_id") == dis_id:
            return existing
    day = str(today or _now()[:10])
    if len([r for r in disagreements() if r.get("date") == day]) >= PER_DAY:
        raise PermissionError("%d disagreements are declared today already" % PER_DAY)
    out = dict(frozen, disagreement_id=dis_id, declared_at=now or _now(), date=day, by=_squash(by)[:60],
               threshold_between=round(boundary(ranges[a], ranges[b]), 6),
               supports="the measured value with its uncertainty lies inside one prediction and outside the other",
               opposes="it lies outside both (supports neither); inside both is impossible by construction",
               truth_status=TRUTH)
    append_ledger(DISAGREEMENTS_NAME, out)
    return out


# ------------------------------------------------------------------ adjudication

def _range(pred):
    return normalize_prediction(pred)[1]


def judge(value, uncertainty, predictions):
    """(verdict, supports lens or None, per-lens states, why). Deterministic; nothing a model wrote is run."""
    lo, hi = value - uncertainty, value + uncertainty
    states = {}
    for lens, entry in predictions.items():
        r = _range(entry["predicts"])
        if "below" in entry["predicts"]:        # open end: a value at the boundary is not below it
            inside, outside = hi < r[1], lo >= r[1]
        elif "above" in entry["predicts"]:
            inside, outside = lo > r[0], hi <= r[0]
        else:                                   # between is closed at both ends
            inside, outside = r[0] <= lo and hi <= r[1], hi < r[0] or lo > r[1]
        states[lens] = "consistent" if inside else "contradicted" if outside else "undecided"
    consistent = [k for k, s in states.items() if s == "consistent"]
    contradicted = [k for k, s in states.items() if s == "contradicted"]
    shown = "%g ± %g" % (value, uncertainty)
    if len(consistent) == 1 and len(contradicted) == 1:
        return "supports_one", consistent[0], states, "%s lies inside %s's prediction and outside the other's" % (
            shown, consistent[0])
    if len(contradicted) == 2:
        return "supports_neither", None, states, "%s lies outside both predictions" % shown
    if not contradicted:
        return "inconclusive", None, states, ("the measurement accommodates both: %s reaches into both predicted "
                                              "ranges" % shown)
    return "inconclusive", None, states, "%s straddles a predicted boundary; the uncertainty is too wide to decide" % shown


def _bindings(dis):
    """Frozen lab_measurement contracts (latest revision each) that name this disagreement."""
    import lab_measurement
    out = []
    for row in lab_measurement._active(lab_measurement.contracts()):
        c = row.get("contract") or {}
        if c.get("disagreement") == dis["disagreement_id"] and row.get("status") == "frozen":
            out.append(row)
    return out


def adjudicate(dis, contract_row, result, divergence_row=None):
    """One verdict row for one disagreement measured by one contract revision. Never raises."""
    c = contract_row.get("contract") or {}
    base = {"kind": "disagreement_verdict", "disagreement_id": dis.get("disagreement_id"), "at": _now(),
            "variable": dis.get("variable"), "units": dis.get("units"),
            "predictions": {k: describe(v["predicts"]) for k, v in (dis.get("predictions") or {}).items()},
            "contract_id": contract_row.get("contract_id"), "revision": contract_row.get("revision"),
            "contract_sha256": contract_row.get("contract_sha256"), "investigation": contract_row.get("investigation"),
            "hypothesis": c.get("hypothesis"), "bound": (result or {}).get("bound") or [],
            "execution_state": (result or {}).get("execution_state", "not_run"), "supports": None,
            "truth_status": TRUTH}

    def done(verdict, why, **extra):
        return dict(base, verdict=verdict, why=str(why)[:400], **extra)
    try:
        if divergence_row is not None:
            read = _read_lenses(divergence_row)
            for lens, entry in (dis.get("predictions") or {}).items():
                if lens not in read or _reading_digest(read[lens]) != entry.get("reading_sha256"):
                    return done("not_evaluated", "%s's retained reading changed since the disagreement was frozen; "
                                "it judges nothing" % lens)
        if str(contract_row.get("frozen_at") or "") < str(dis.get("declared_at") or ""):
            return done("not_evaluated", "the measurement was frozen before the disagreement was; it was not chosen "
                        "to separate these predictions")
        if c.get("evaluator") not in ONE_VALUE:
            return done("not_evaluated", "a disagreement is judged by one measured value (structural_measure or "
                        "reproducibility), not by %s" % c.get("evaluator"))
        if _squash(c.get("units")).lower() != _squash(dis.get("units")).lower():
            return done("not_evaluated", "the measurement is in %r and the predictions in %r"
                        % (c.get("units"), dis.get("units")))
        if result.get("execution_state") != "completed" or result.get("measurement_state") == "not_evaluated":
            return done("not_evaluated", "the measurement did not produce a value (%s); this says nothing about "
                        "either reader" % str(result.get("why") or "")[:160])
        if not result.get("confirmatory"):
            return done("not_evaluated", "measured on outputs that existed before the measurement was frozen (%s); "
                        "it cannot separate predictions it could have been fitted to"
                        % str(result.get("confirmatory_why") or "not confirmatory")[:160])
        est = result.get("estimate") or {}
        value = est.get("value")
        unc = est.get("uncertainty") or 0.0
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return done("not_evaluated", "the result carries no finite value")
        if isinstance(unc, bool) or not isinstance(unc, (int, float)) or not math.isfinite(unc) or unc < 0:
            return done("not_evaluated", "the result's uncertainty is not a number >= 0")
        verdict, lens, states, why = judge(float(value), float(unc), dis.get("predictions") or {})
        return done(verdict, why, supports=lens, states=states,
                    measured={"value": float(value), "uncertainty": float(unc), "units": c.get("units")})
    except Exception as exc:                       # noqa: BLE001 - a broken record is not a verdict
        return done("not_evaluated", "the record could not be read: %s" % str(exc)[:200])


def state(dis_id):
    """open, settled (a decisive verdict), or exhausted (MAX_MEASUREMENTS judged values, none decisive). A
    measurement that produced no usable value does not use up a turn: it says nothing either way."""
    rows = verdicts(dis_id)
    if any(r.get("verdict") in ("supports_one", "supports_neither") for r in rows):
        return "settled"
    if len([r for r in rows if r.get("verdict") != "not_evaluated"]) >= MAX_MEASUREMENTS:
        return "exhausted"
    return "open"


def settle():
    """Adjudicate every open disagreement whose binding measurement has a result. Once per contract revision."""
    out = []
    try:
        import lab_measurement
        results = {(r.get("contract_id"), r.get("revision")): r for r in lab_measurement.results()}
    except Exception:
        return out
    with _locked():
        divergence = {r.get("session_id"): r for r in _rows(divergence_path())}
        for dis in disagreements():
            ident = dis.get("disagreement_id")
            if state(ident) != "open":
                continue
            done = {(r.get("contract_id"), r.get("revision")) for r in verdicts(ident)}
            for row in _bindings(dis):
                key = (row.get("contract_id"), row.get("revision"))
                if key in done or key not in results:
                    continue
                if state(ident) != "open":
                    break
                verdict = adjudicate(dis, row, results[key], divergence.get(dis.get("divergence"), {}))
                append_ledger(VERDICTS_NAME, verdict)
                out.append(verdict)
    return out


# ------------------------------------------------------------------ what the investigation planner is shown

def for_planner(limit=2):
    """Open disagreements, short, with how to bind a measurement to one; and the latest verdict. None if nothing."""
    try:
        open_ = [d for d in disagreements() if state(d.get("disagreement_id")) == "open"][-limit:]
        view = {}
        if open_:
            view["open"] = [{"id": d["disagreement_id"], "variable": d.get("variable"), "units": d.get("units"),
                             "predictions": {k: describe(v["predicts"]) for k, v in d["predictions"].items()},
                             "separating_threshold": d.get("threshold_between"),
                             "measurements_left": MAX_MEASUREMENTS - len(
                                 [r for r in verdicts(d["disagreement_id"]) if r.get("verdict") != "not_evaluated"])}
                            for d in open_]
            view["how"] = ("Two of your readings predict incompatible values. To settle one, choose a local "
                           "operation (an instrument, native tool or read of a retained output; no fold) that "
                           "measures that variable, and with it return a confirmatory measurement contract, "
                           "evaluator structural_measure, in the same units, threshold the separating_threshold, "
                           "plus disagreement: the id. Freeze it before the step that measures. The verdict is "
                           "computed: one prediction, neither, or inconclusive.")
        last = [r for r in verdicts() if r.get("verdict") != "not_evaluated"][-1:]
        if last:
            r = last[0]
            view["last_verdict"] = {"id": r.get("disagreement_id"), "verdict": r.get("verdict"),
                                    "supports": r.get("supports"), "why": r.get("why")}
        return view or None
    except Exception:
        return None


def display(dis):
    lines = ["%s: %s" % (dis["disagreement_id"], dis.get("question")),
             "from divergence %s (read of %s); %s in %s" % (dis.get("divergence"), dis.get("read_of"),
                                                           dis.get("variable"), dis.get("units"))]
    for lens, entry in sorted((dis.get("predictions") or {}).items()):
        lines.append("  %s predicts %s, from its own words: \"%s\"" % (lens, describe(entry["predicts"]),
                                                                     entry["basis"][:160]))
    rows = verdicts(dis["disagreement_id"])
    for r in rows:
        lines.append("  measured by %s rev %s: %s%s - %s" % (r.get("contract_id"), r.get("revision"), r.get("verdict"),
                                                           " (%s)" % r["supports"] if r.get("supports") else "",
                                                           r.get("why")))
    lines.append("  state: %s" % state(dis["disagreement_id"]))
    return lines


def _cli(argv):
    if argv[:1] == ["pairs"]:
        print(json.dumps(pairs(), indent=1, ensure_ascii=False))
        return 0
    if argv[:1] == ["show"] or not argv:
        for dis in disagreements():
            print("\n".join(display(dis)))
        return 0
    if argv[:1] == ["settle"]:
        print(json.dumps(settle(), indent=1, ensure_ascii=False))
        return 0
    if argv[:1] == ["declare"] and len(argv) == 1:
        print(json.dumps(declare(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
        return 0
    print("usage: lab_disagreement.py pairs | show | settle | declare  (declare reads JSON on stdin)")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
