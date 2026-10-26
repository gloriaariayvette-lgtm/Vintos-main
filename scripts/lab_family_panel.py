#!/usr/bin/env python3
"""Compare a family across instruments: does a feature persist in homologs and go missing in a matched relative?

Codex's proposal 10 (25 October 2026), the smallest proof it describes: three sourced homologs plus one
comparator, each read from artifacts the Lab has already retained, joined by residue position, and judged
against a question frozen before the readings are looked at.

This is the coregistration layer of the open-work note applied across proteins rather than inside one. Each
member's readings are kept as a *coregistered record, not a synthesised vector*: the per-residue confidence
of the folding model and the per-residue secondary structure of the geometry reader stay separate numbers
hung on the same residue, and nothing here fuses them into one learned vector no model produced.

What it adds to a single compare is the family-level question, and a way for it to fail:

  declare    - frozen first: the question in words, the three family members, the one comparator, which
               member's numbering the positions are given in, the positions, and the feature as up to two
               clauses, each naming one instrument's reading and a threshold. Every artifact it will read is
               digested at declaration, so a structure that changes underneath the panel is refused rather
               than quietly re-measured.
  evaluate   - per member and position: where the position lands in that member by sequence alignment, how
               trustworthy that correspondence is, the readings there, and whether the feature holds. A
               position no alignment places confidently is undecidable, never "the feature is absent".
               Per position: persists / not_family_specific / not_shared_in_family / inconclusive. For the
               panel: supported / refuted / inconclusive, in the Lab's measurement vocabulary.

Honesty, and the three risks the proposal named:

  wrong residue correspondence - the mapping comes from the sequences themselves, and each position carries
      the identity and gap state of the window around it. Below the floors it is undecidable.
  domain and chains mixed      - a structure with more than one chain is refused; the member must be one
      chain's artifact. The sequence identity of every member to the anchor is reported, and a comparator
      closer to the anchor than a family member is called out: then "family" is not what is being compared.
  low confidence mistaken for  - confidence is a reading of the folding model only. A confidence clause on an
      meaningful flexibility     observed structure is refused outright (a deposited file's B-factor is a
      temperature factor, not pLDDT), and no verdict here means flexibility, function or biology.

Nothing is folded, fetched or paid for: it reads retained artifacts with his own readers, in his own Python.
A member with no retained structure is refused with that said plainly; commissioning a fold is hers.

    python3 lab_family_panel.py show | evaluate <FAM-id> | declare   (declare reads one JSON object on stdin)
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace")))
LAB = WS / "memory" / "chemistry-lab"
ARTIFACTS = LAB / "artifacts"
MODELS = ARTIFACTS / "esmfold"
PANELS = LAB / "family-panels.jsonl"
PANEL_RESULTS = LAB / "family-results.jsonl"

FAMILY_SIZE = 3             # "three sourced homologs"
MAX_POSITIONS = 12
MAX_CLAUSES = 2
MAX_ALIGN = 1200            # residues a side; the panel is a small comparison, not an alignment service
PANELS_PER_DAY = 2
WINDOW = 3                  # residues each side of a position that must line up for it to be decidable
WINDOW_IDENTITY = 0.5       # of the aligned window
MIN_IDENTITY = 0.25         # to the anchor, for a member to be treated as a relative at all
MIN_ALIGNED = 0.5           # share of the anchor's residues that must align to the member
READINGS = {"confidence": "folding model (pLDDT, per residue)",
            "secondary_structure": "geometry reader (CA assignment, per residue)"}
SS_LETTERS = ("H", "E", "-")
PREDICTED = ("artifacts/esmfold/", "artifacts/esmfold-derived/")
ACCESSION = re.compile(r"[A-Z0-9]{6,10}(?:-[1-9][0-9]*)?")
PANEL_ID = re.compile(r"FAM-[0-9a-f]{10}")
POSITION_STATES = ("persists", "not_family_specific", "not_shared_in_family", "inconclusive")
MEASUREMENT_STATES = ("supported", "refuted", "inconclusive")
TRUTH = ("a cross-protein comparison of his own retained readings, joined by residue position; not experimental "
         "evidence, not a statement about function, stability or flexibility")


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _inside(path, root):
    try:
        return os.path.commonpath((str(root.resolve()), str(Path(path).resolve()))) == str(root.resolve())
    except (OSError, ValueError):
        return False


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def append_ledger(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _rows(path):
    out = []
    if not Path(path).is_file():
        return out
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def panels():
    return _rows(PANELS)


def results(panel_id=None):
    rows = _rows(PANEL_RESULTS)
    return [r for r in rows if r.get("panel_id") == panel_id] if panel_id else rows


def panel(panel_id):
    ident = str(panel_id or "").strip()
    for row in panels():
        if row.get("panel_id") == ident:
            return row
    raise ValueError("no declared panel %r" % ident[:40])


# ------------------------------------------------------------------ the artifacts a member is read from

def member_structure(name):
    """The retained structure for a member, as a path relative to the Lab: an accession's newest ESMFold model,
    or an explicit .pdb under the Lab's artifacts. Nothing is folded or fetched here."""
    name = str(name or "").strip()
    if not name:
        raise ValueError("a panel member needs an accession or a retained structure")
    if ACCESSION.fullmatch(name.upper()) and not name.lower().endswith(".pdb"):
        found = sorted(MODELS.glob(name.upper() + "-*.pdb"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not found:
            raise ValueError("no retained structure of %s in the Lab. This panel reads what is already there; "
                             "folding it is a separate bounded run to commission." % name.upper())
        return str(found[0].relative_to(LAB))
    path = LAB / name
    if not name.lower().endswith(".pdb") or not path.is_file() or not _inside(path, ARTIFACTS):
        raise ValueError("a member is an accession the Lab has a model of, or a .pdb under its artifacts; got %r"
                         % name[:60])
    return str(path.relative_to(LAB))


def _kind(rel):
    return "prediction" if str(rel).startswith(PREDICTED) else "observed"


def _chains(text):
    return {line[21:22] for line in str(text).splitlines()
            if line.startswith("ATOM") and len(line) >= 54 and line[12:16].strip() == "CA"}


def read_member(rel):
    """One member's coregistered readings: residue number -> {one-letter, confidence, secondary_structure}.

    The sequence and the chain discipline come from the derived-sequence reader, the per-residue confidence and
    the secondary structure from the fold reader. Two instruments, one residue index, no fusion.
    """
    import chemistry_fold_read as fold_read
    import lab_derived_sequences as derived
    path = LAB / rel
    text = path.read_text(encoding="utf-8", errors="replace")
    chains = _chains(text)
    if len(chains) > 1:
        raise ValueError("%s holds %d chains (%s); this panel reads one chain, so give one chain's artifact "
                         "rather than letting chains be mixed" % (rel, len(chains), ",".join(sorted(chains))))
    trace = derived.structure_sequence(text)
    if len(trace) < 2 * WINDOW + 1:
        raise ValueError("%s has too few C-alpha residues to compare" % rel)
    read = fold_read.read_pdb(text)
    confidence = {number: round(float(plddt), 1) for number, _, _, plddt in read["residues"]}
    letters = {number: read["ss"][index] for index, (number, _, _, _) in enumerate(read["residues"])}
    residues = []
    for number, aa, _ in trace:
        residues.append({"number": number, "amino_acid": aa,
                         "confidence": confidence.get(number),
                         "secondary_structure": letters.get(number)})
    return {"structure": rel, "kind": _kind(rel), "sha256": _sha256(path),
            "chain": sorted(chains)[0] if chains else None, "residues": residues,
            "sequence": "".join(r["amino_acid"] for r in residues),
            "numbers": [r["number"] for r in residues]}


# ------------------------------------------------------------------ residue correspondence, and how sure it is

def align(a, b):
    """[(index in a, index in b)] from a global alignment of two sequences, in his own Python (no dependency)."""
    if len(a) > MAX_ALIGN or len(b) > MAX_ALIGN:
        raise ValueError("a panel aligns at most %d residues a side" % MAX_ALIGN)
    if not a or not b:
        raise ValueError("nothing to align")
    match, mismatch, gap = 2, -1, -2
    previous = [j * gap for j in range(len(b) + 1)]
    pointers = []
    for i in range(1, len(a) + 1):
        current = [i * gap] + [0] * len(b)
        row = bytearray(len(b) + 1)
        row[0] = 2
        here = a[i - 1]
        for j in range(1, len(b) + 1):
            best, direction = previous[j - 1] + (match if here == b[j - 1] else mismatch), 1
            up = previous[j] + gap
            if up > best:
                best, direction = up, 2
            left = current[j - 1] + gap
            if left > best:
                best, direction = left, 3
            current[j], row[j] = best, direction
        pointers.append(row)
        previous = current
    i, j, pairs = len(a), len(b), []
    while i > 0 and j > 0:
        direction = pointers[i - 1][j]
        if direction == 1:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif direction == 2:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def correspondence(anchor, member):
    """How the anchor's residue numbers map onto the member's, and how much of it can be trusted."""
    pairs = align(anchor["sequence"], member["sequence"])
    mapping = {anchor["numbers"][i]: member["numbers"][j] for i, j in pairs}
    identical = sum(anchor["sequence"][i] == member["sequence"][j] for i, j in pairs)
    identity = round(identical / len(pairs), 3) if pairs else 0.0
    aligned = round(len(pairs) / len(anchor["numbers"]), 3)
    return {"mapping": mapping, "identity_to_anchor": identity, "aligned_fraction": aligned,
            "aligned_residues": len(pairs),
            "homologous_enough": identity >= MIN_IDENTITY and aligned >= MIN_ALIGNED,
            "method": "global sequence alignment of the two retained structures' own residues; no offset is "
                      "assumed and no numbering is relabelled"}


def _window(anchor, member, corr, position):
    """(mapped number or None, the window's state): a position is only decidable where its neighbourhood lines up."""
    mapping = corr["mapping"]
    wanted = [n for n in range(position - WINDOW, position + WINDOW + 1)]
    present = [n for n in wanted if n in set(anchor["numbers"])]
    mapped = [n for n in present if n in mapping]
    anchor_aa = {r["number"]: r["amino_acid"] for r in anchor["residues"]}
    member_aa = {r["number"]: r["amino_acid"] for r in member["residues"]}
    same = sum(anchor_aa[n] == member_aa.get(mapping[n]) for n in mapped)
    window_identity = round(same / len(mapped), 3) if mapped else 0.0
    contiguous = all(mapping[b] - mapping[a] == b - a for a, b in zip(mapped, mapped[1:]))
    gap_free = len(mapped) == len(wanted) and contiguous
    decidable = (position in mapping and corr["homologous_enough"] and gap_free
                 and window_identity >= WINDOW_IDENTITY)
    return (mapping.get(position) if decidable else None,
            {"window": [position - WINDOW, position + WINDOW], "window_aligned": len(mapped),
             "window_identity": window_identity, "window_gap_free": gap_free, "decidable": bool(decidable)})


# ------------------------------------------------------------------ the feature, frozen before it is measured

def normalize_feature(raw):
    """Up to two clauses, each one instrument's reading against a threshold; anything else is refused."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CLAUSES:
        raise ValueError("feature must be a list of 1 to %d clauses" % MAX_CLAUSES)
    out = []
    for clause in raw:
        if not isinstance(clause, dict):
            raise ValueError("each feature clause must be an object")
        reading = str(clause.get("reading") or "")
        if reading not in READINGS:
            raise ValueError("a feature clause reads one of: %s" % ", ".join(sorted(READINGS)))
        if reading == "secondary_structure":
            is_ = str(clause.get("is") or "")
            if is_ not in SS_LETTERS:
                raise ValueError("secondary_structure is one of %s" % ", ".join(SS_LETTERS))
            out.append({"reading": reading, "is": is_})
            continue
        below, above = clause.get("below"), clause.get("above")
        given = [v for v in (below, above) if v is not None]
        if len(given) != 1 or isinstance(given[0], bool) or not isinstance(given[0], (int, float)):
            raise ValueError("a confidence clause gives exactly one of below / above, a number")
        if not 0 <= float(given[0]) <= 100:
            raise ValueError("confidence is a pLDDT, 0 to 100")
        out.append({"reading": reading, "below": float(below)} if below is not None
                   else {"reading": reading, "above": float(above)})
    if len({c["reading"] for c in out}) != len(out):
        raise ValueError("two clauses on the same reading say nothing more than one")
    return out


def holds(clause, residue):
    """True / False / None (the reading is missing) for one clause at one residue."""
    value = residue.get(clause["reading"])
    if value is None:
        return None
    if clause["reading"] == "secondary_structure":
        return value == clause["is"]
    if "below" in clause:
        return float(value) < clause["below"]
    return float(value) >= clause["above"]


def declare(raw, *, today=None):
    """Freeze a family-level question before its readings are looked at. Same question, same panel id."""
    if not isinstance(raw, dict):
        raise ValueError("a panel declaration must be an object")
    question = str(raw.get("question") or "").strip()
    if len(question) < 20:
        raise ValueError("say in words what this panel asks of the family (at least 20 characters)")
    family = [str(x).strip() for x in (raw.get("family") or []) if str(x).strip()]
    if len(family) != FAMILY_SIZE or len(set(family)) != FAMILY_SIZE:
        raise ValueError("a panel is %d distinct family members" % FAMILY_SIZE)
    comparator = str(raw.get("comparator") or "").strip()
    if not comparator:
        raise ValueError("a panel needs one comparator: a matched relative the feature is expected to be absent in")
    if comparator in family:
        raise ValueError("the comparator cannot also be a family member")
    anchor = str(raw.get("anchor") or family[0]).strip()
    if anchor not in family:
        raise ValueError("the anchor is the family member whose numbering the positions are given in")
    positions = raw.get("positions")
    if not (isinstance(positions, list) and positions and len(positions) <= MAX_POSITIONS
            and all(isinstance(p, int) and not isinstance(p, bool) and p > 0 for p in positions)
            and len(set(positions)) == len(positions)):
        raise ValueError("positions is 1 to %d distinct residue numbers in the anchor's numbering" % MAX_POSITIONS)
    feature = normalize_feature(raw.get("feature"))
    members = [{"name": name, "role": "family", "structure": member_structure(name)} for name in family]
    members.append({"name": comparator, "role": "comparator", "structure": member_structure(comparator)})
    for member in members:
        path = LAB / member["structure"]
        member["sha256"] = _sha256(path)
        member["kind"] = _kind(member["structure"])
        member["is_anchor"] = member["name"] == anchor and member["role"] == "family"
    for member in members:                      # readable, one chain, long enough - before the question is frozen
        read_member(member["structure"])
    if any(c["reading"] == "confidence" for c in feature) and any(m["kind"] != "prediction" for m in members):
        raise ValueError("a confidence clause reads the folding model's pLDDT. %s is an observed structure, whose "
                         "B-factor is a temperature factor and not a confidence: drop the clause or drop the member"
                         % next(m["structure"] for m in members if m["kind"] != "prediction"))
    frozen = {"question": question[:600], "family": family, "comparator": comparator, "anchor": anchor,
              "positions": sorted(positions), "feature": feature,
              "members": [{k: m[k] for k in ("name", "role", "structure", "sha256", "kind", "is_anchor")}
                          for m in members]}
    panel_id = "FAM-" + hashlib.sha256(
        json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    for row in panels():
        if row.get("panel_id") == panel_id:
            return row
    day = str(today or _now()[:10])
    if len([r for r in panels() if r.get("date") == day]) >= PANELS_PER_DAY:
        raise PermissionError("%d panels are declared today already; a panel is a question to sit with" % PANELS_PER_DAY)
    row = dict(frozen, panel_id=panel_id, declared_at=_now(), date=day,
               supports="the feature holds at every declared position in all %d family members and in none of them "
                        "in the comparator" % FAMILY_SIZE,
               opposes="the comparator carries it too (not family-specific), or a family member does not (not shared)",
               reading_sources=dict(READINGS), truth_status=TRUTH)
    append_ledger(PANELS, row)
    return row


# ------------------------------------------------------------------ the measurement

def _position_state(family_states, comparator_state):
    if comparator_state is None or any(s is None for s in family_states):
        return "inconclusive"
    if all(family_states) and not comparator_state:
        return "persists"
    if all(family_states) and comparator_state:
        return "not_family_specific"
    return "not_shared_in_family"


def _feature_at(feature, residue):
    clauses = [{"clause": c, "holds": holds(c, residue)} for c in feature]
    if any(c["holds"] is None for c in clauses):
        return None, clauses
    return all(c["holds"] for c in clauses), clauses


def evaluate(panel_id):
    """Measure a declared panel against the artifacts it froze. Supported, refuted or inconclusive, and kept."""
    row = panel(panel_id)
    members = {}
    for member in row["members"]:
        path = LAB / member["structure"]
        if not path.is_file():
            raise ValueError("%s is no longer in the Lab's artifacts" % member["structure"])
        if _sha256(path) != member["sha256"]:
            raise ValueError("%s has changed since this panel was declared; declare a new panel rather than "
                             "re-measuring a question against a different structure" % member["structure"])
        read = read_member(member["structure"])
        read.update({"name": member["name"], "role": member["role"], "is_anchor": member["is_anchor"]})
        members[member["name"]] = read
    anchor = members[row["anchor"]]
    others = [m for name, m in members.items() if name != row["anchor"]]
    for member in others:
        member["correspondence"] = correspondence(anchor, member)
    anchor["correspondence"] = {"mapping": {n: n for n in anchor["numbers"]}, "identity_to_anchor": 1.0,
                                "aligned_fraction": 1.0, "aligned_residues": len(anchor["numbers"]),
                                "homologous_enough": True, "method": "the anchor, in its own numbering"}
    order = [members[name] for name in row["family"]] + [members[row["comparator"]]]
    positions = []
    for position in row["positions"]:
        at = []
        for member in order:
            mapped, window = ((position if position in set(anchor["numbers"]) else None),
                              {"window": [position, position], "window_aligned": 1, "window_identity": 1.0,
                               "window_gap_free": True, "decidable": position in set(anchor["numbers"])}) \
                if member is anchor else _window(anchor, member, member["correspondence"], position)
            residue = next((r for r in member["residues"] if r["number"] == mapped), None) if mapped else None
            present, clauses = (_feature_at(row["feature"], residue) if residue else (None, []))
            at.append({"name": member["name"], "role": member["role"], "structure": member["structure"],
                       "kind": member["kind"], "mapped_position": mapped, "correspondence": window,
                       "readings": {k: residue.get(k) for k in READINGS} if residue else None,
                       "clauses": clauses, "feature": present})
        family_states = [a["feature"] for a in at if a["role"] == "family"]
        comparator_state = next(a["feature"] for a in at if a["role"] == "comparator")
        positions.append({"position": position, "state": _position_state(family_states, comparator_state),
                          "members": at})
    states = [p["state"] for p in positions]
    if any(s in ("not_family_specific", "not_shared_in_family") for s in states):
        measurement_state = "refuted"
    elif "inconclusive" in states:
        measurement_state = "inconclusive"
    else:
        measurement_state = "supported"
    identities = {m["name"]: m["correspondence"]["identity_to_anchor"] for m in order}
    family_floor = min(identities[name] for name in row["family"] if name != row["anchor"])
    warnings = []
    if identities[row["comparator"]] > family_floor:
        warnings.append("the comparator is closer to the anchor by sequence (%.0f%%) than the most distant family "
                        "member is (%.0f%%): this panel is not comparing a family against an outsider"
                        % (identities[row["comparator"]] * 100, family_floor * 100))
    for member in order:
        if not member["correspondence"]["homologous_enough"]:
            warnings.append("%s aligns to the anchor over %.0f%% of it at %.0f%% identity, below the floors; every "
                            "position in it is undecidable" % (member["name"],
                                                               member["correspondence"]["aligned_fraction"] * 100,
                                                               member["correspondence"]["identity_to_anchor"] * 100))
    if any(m["kind"] != "prediction" for m in order):
        warnings.append("this panel mixes predicted and observed structures; a difference between them can be the "
                        "difference between a model and an experiment, not between the proteins")
    result = {"panel_id": row["panel_id"], "measured_at": _now(), "question": row["question"],
              "anchor": row["anchor"], "feature": row["feature"], "measurement_state": measurement_state,
              "positions": positions, "identity_to_anchor": identities, "warnings": warnings,
              "members": [{"name": m["name"], "role": m["role"], "structure": m["structure"], "kind": m["kind"],
                           "sha256": m["sha256"], "chain": m["chain"], "residues": len(m["residues"]),
                           "correspondence": {k: v for k, v in m["correspondence"].items() if k != "mapping"}}
                          for m in order],
              "method": "retained readings joined by residue position: per-residue confidence from the folding "
                        "model and per-residue secondary structure from the geometry reader, kept as separate "
                        "readings on one residue index and never fused",
              "truth_status": TRUTH}
    result["display"] = display(row, result)
    append_ledger(PANEL_RESULTS, {k: v for k, v in result.items() if k != "display"})
    return {"ok": True, "result": result}


def describe(feature):
    out = []
    for clause in feature:
        if clause["reading"] == "secondary_structure":
            out.append("secondary structure is %s" % clause["is"])
        elif "below" in clause:
            out.append("confidence below %g" % clause["below"])
        else:
            out.append("confidence at or above %g" % clause["above"])
    return " and ".join(out)


def display(row, result):
    lines = ["panel %s: %s" % (row["panel_id"], row["question"]),
             "family %s against %s, positions in %s's numbering: %s" % (
                 ", ".join(row["family"]), row["comparator"], row["anchor"],
                 ", ".join(str(p) for p in row["positions"])),
             "feature: %s" % describe(row["feature"]),
             "verdict: %s (%s)" % (result["measurement_state"],
                                   "; ".join("%d %s" % (sum(1 for p in result["positions"] if p["state"] == s), s)
                                             for s in POSITION_STATES
                                             if any(p["state"] == s for p in result["positions"])))]
    for name, identity in result["identity_to_anchor"].items():
        member = next(m for m in result["members"] if m["name"] == name)
        lines.append("%s (%s, %s, %d residues): %.0f%% identical to the anchor over %.0f%% of it" % (
            name, member["role"], member["kind"], member["residues"], identity * 100,
            member["correspondence"]["aligned_fraction"] * 100))
    for entry in result["positions"]:
        lines.append("position %d: %s" % (entry["position"], entry["state"]))
        for at in entry["members"]:
            if at["mapped_position"] is None:
                lines.append("  %s (%s): no trustworthy correspondence here (%d of %d residues in the window "
                             "aligned, %.0f%% identical) - undecidable, not absent" % (
                                 at["name"], at["role"], at["correspondence"]["window_aligned"],
                                 2 * WINDOW + 1, at["correspondence"]["window_identity"] * 100))
                continue
            readings = at["readings"] or {}
            lines.append("  %s (%s): residue %d, confidence %s, secondary structure %s -> %s" % (
                at["name"], at["role"], at["mapped_position"],
                "n/a" if readings.get("confidence") is None else "%.1f" % readings["confidence"],
                readings.get("secondary_structure") or "n/a",
                "feature present" if at["feature"] else ("undecidable" if at["feature"] is None else "absent")))
    for warning in result["warnings"]:
        lines.append("caution: " + warning)
    lines.append("what this is: his own retained readings compared across proteins. Not experimental evidence, and "
                 "no claim about function, stability or flexibility.")
    return lines


def ready():
    """Declared panels whose frozen artifacts are all still there, unchanged: the ones an instrument may run."""
    out = []
    for row in panels():
        try:
            if all((LAB / m["structure"]).is_file() and _sha256(LAB / m["structure"]) == m["sha256"]
                   for m in row.get("members") or []):
                out.append(row)
        except OSError:
            continue
    return out


def _cli(argv):
    if argv[:1] == ["show"]:
        for row in panels():
            measured = results(row["panel_id"])
            print("%s  %s  family %s vs %s  %d position(s)  %s" % (
                row["panel_id"], row.get("date", row["declared_at"][:10]), ",".join(row["family"]), row["comparator"],
                len(row["positions"]), measured[-1]["measurement_state"] if measured else "not measured"))
        return 0
    if argv[:1] == ["evaluate"] and len(argv) == 2:
        print("\n".join(evaluate(argv[1])["result"]["display"]))
        return 0
    if argv[:1] == ["declare"] and len(argv) == 1:
        import sys
        print(json.dumps(declare(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
        return 0
    print("usage: lab_family_panel.py show | evaluate <FAM-id> | declare  (declare reads JSON on stdin)")
    return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
