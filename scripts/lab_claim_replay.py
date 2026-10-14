#!/usr/bin/env python3
"""A fixed set of Lab questions that failed, audited, and reviewed again with full-text evidence for their open
claims, to show whether that evidence helps (T-17420bd6, 2026-10-14). The questions are never rewritten.

    python3 scripts/lab_claim_replay.py pick [N]    fix the set: the last N reviews that did not answer (default 20);
                                                    kept as it is until --force
    python3 scripts/lab_claim_replay.py audit       what each one is: a flawed premise, a wrong target, a Lab failure,
                                                    or a question missing evidence (no network, no model)
    python3 scripts/lab_claim_replay.py recheck     each question's target fetched again from UniProt (read-only) and run
                                                    through today's checks: identity, premise, coordinate route
    python3 scripts/lab_claim_replay.py overflow     what is actually oversized in the requests that did not fit:
                                                    question, instructions, or one evidence item (read-only)
    python3 scripts/lab_claim_replay.py live [ISO]  the live Lab's review outcomes since ISO; with no time, since the
                                                    last deploy, so a change is never read off reviews that predate
                                                    it (14 October: it was, twice). Read-only.
    python3 scripts/lab_claim_replay.py run         for the ones missing evidence: search Europe PMC full text for the
                                                    open claims and run the same coverage check on the whole question,
                                                    with the quotes it already had carried forward

It reads the notebook and writes only under memory/chemistry-lab/claim-replay/: its own fixed set, its own search
ledger and its report. It writes nothing to the notebook, the holds or the live claim ledger (a question
too large for the checker leaves the Lab's usual coverage-deferred snapshot). The checker is the
Lab's own model (local Gemma); Europe PMC is read-only.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lab_claim_evidence as LCE

DIR = os.path.join(LCE.ROOT, "claim-replay")
SET = os.path.join(DIR, "fixed-set.json")
LEDGER = os.path.join(DIR, "replay-ledger.json")
REPORT = os.path.join(DIR, "report.json")
NOTEBOOK = os.path.join(LCE.ROOT, "notebook.jsonl")


def _rows(path=NOTEBOOK):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("kind") == "reflection":
                out.append(row)
    return out


def pick(n=20, force=False, notebook=NOTEBOOK, path=SET):
    if os.path.exists(path) and not force:
        return json.load(open(path))
    chosen = []
    for row in reversed(_rows(notebook)):
        status, why = LCE.outcome(row)
        if status == "answered":
            continue
        inquiry = row.get("inquiry") if isinstance(row.get("inquiry"), dict) else {}
        if not inquiry.get("question"):
            continue
        if any(c["inquiry"]["question"] == inquiry["question"] for c in chosen):
            continue
        cov = row.get("coverage_check") if isinstance(row.get("coverage_check"), dict) else {}
        chosen.append({"at": row.get("at"), "inquiry": inquiry, "outcome": status, "why": why[:400],
                       "coverage_check": {k: cov.get(k) for k in ("answered", "missing", "supports",
                                                                  "assessment_status", "validation_failure")} if cov else {},
                       "entity_context_check": row.get("entity_context_check") or {},
                       "assessment_status": row.get("assessment_status"), "evidence_status": row.get("evidence_status"),
                       "coverage_deferred": row.get("coverage_deferred"),
                       "answers_question": row.get("answers_question")})
        if len(chosen) >= n:
            break
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(chosen, open(path, "w"), ensure_ascii=False, indent=1)
    return chosen


def audit(items):
    """Each question's kind of failure. More papers cannot rescue a flawed premise or a wrong target."""
    lines = []
    for i, item in enumerate(items, 1):
        status, why = LCE.outcome(item)
        kind = ("missing evidence" if status in LCE.SEARCHABLE else
                "question or target" if status in LCE.QUESTION else
                "Lab failure, not judged" if status in LCE.SOFTWARE else status)
        lines.append({"n": i, "question": item["inquiry"]["question"], "outcome": status, "kind": kind,
                      "why": why[:300], "open_claims": LCE.claims(item),
                      "full_text_could_help": status in LCE.SEARCHABLE})
    return lines


def recheck(items, browse=None):
    """What today's checks make of each fixed question, from its target's record, before any review."""
    import chemistry_lab as C
    from lab_sources import question_entity_context
    browse = browse or (lambda query: (C._browse(query, 4) or {}).get("records") or [])
    out = []
    for item in items:
        stored = dict(item["inquiry"])
        q = stored.get("question", "")
        row = {"question": q, "before": LCE.outcome(item)[0]}
        try:   # planned as today's Lab would plan it: every named gene fetched, coordinates routed; question unchanged
            inquiry = dict(C._inquiry(stored), question=q)
        except Exception as exc:
            inquiry = stored; row["planning_note"] = "replanning failed: %s" % exc
        route = inquiry.get("source_query") or {}
        if route.get("operation") == "structure_evidence":
            row.update(now="coordinate_read", why="reads the coordinates of PDB %s%s" % (
                route.get("entry_id"), " (as it already did)" if (stored.get("source_query") or {}).get("operation") == "structure_evidence" else ""))
            out.append(row); continue
        try:
            rows = browse(inquiry.get("uniprot_query") or "") if inquiry.get("uniprot_query") else []
        except Exception as exc:
            row.update(now="unassessed", why="UniProt not read: %s" % exc); out.append(row); continue
        entity = question_entity_context(inquiry, rows)
        if entity.get("issues"):
            joined = "; ".join(entity["issues"])
            row.update(now="contradicted_premise" if "as one protein" in joined else "wrong_target", why=joined[:300])
            out.append(row); continue
        chosen = [r for r in rows if not entity.get("selected_accessions") or r.get("accession") in entity["selected_accessions"]]
        premise = C._premise_issues(q, chosen)
        if premise:
            row.update(now="unverified_premise", why="; ".join(premise)[:300])
        else:
            seen = [name for name, asked, shown in C.PREMISES if __import__("re").search(asked, q, __import__("re").I)]
            row.update(now="reviewable", why="target %s established%s" % (
                ",".join(str(r.get("accession")) for r in chosen),
                ("; its record shows what the question assumes: " + ", ".join(seen)) if seen else
                "; the question assumes nothing this check knows to look for"))
        out.append(row)
    return out


def run(items, fetch=None, coverage=None, ledger_path=LEDGER):
    """Before and after, per question. coverage(inquiry, observations) is the Lab's own checker."""
    if coverage is None:
        import chemistry_lab
        coverage = chemistry_lab._coverage_check
    results = []
    for item in items:
        status, why = LCE.outcome(item)
        before = item.get("coverage_check") or {}
        row = {"question": item["inquiry"]["question"], "before": status,
               "supports_before": len(before.get("supports") or []), "open_before": len(before.get("missing") or [])}
        if status not in LCE.SEARCHABLE:
            row.update(after=status, note="not searched: " + why[:200])
            results.append(row); continue
        gathered = LCE.gather(item["inquiry"], item, None, fetch=fetch, ledger_path=ledger_path)
        row.update(searches=len(gathered["searches"]), reused=len(gathered["reused"]),
                   passages=len(gathered["FULLTEXT"]), failures=gathered["failures"][:4])
        if not gathered["FULLTEXT"]:
            row.update(after=status, note=gathered.get("skipped") or "no full-text passage matched the open claims")
            results.append(row); continue
        prior = [{"requirement": s.get("requirement"), "quote": s.get("quote"), "source_citation": s.get("source_citation")}
                 for s in before.get("supports") or [] if isinstance(s, dict) and s.get("quote")]
        observations = {"records": [], "LITERATURE": [], "prior_validated_evidence": prior, "FULLTEXT": gathered["FULLTEXT"]}
        try:
            result = coverage(item["inquiry"], observations)
        except Exception as exc:
            result = {"assessment_status": "incomplete", "validation_failure": "%s: %s" % (type(exc).__name__, exc)}
        after_status, after_why = LCE.outcome({"coverage_check": result} if result else {})
        if result and result.get("coverage_deferred"):
            after_status, after_why = "context_overflow", str(result.get("missing_evidence") or "")
        row.update(after=after_status, after_why=after_why[:300],
                   supports_after=len((result or {}).get("supports") or []),
                   open_after=len((result or {}).get("missing") or []),
                   still_open=[str(x)[:200] for x in (result or {}).get("missing") or []],
                   cited=[s.get("source_citation") for s in (result or {}).get("supports") or [] if isinstance(s, dict)])
        results.append(row)
    return results


def last_deploy(root=None):
    """When the newest release record was written, or "" when there is none."""
    import datetime, glob
    rows = glob.glob(os.path.join(root or os.path.expanduser("~/.vintos/deploy/releases"), "*.json"))
    if not rows:
        return ""
    newest = max(rows, key=os.path.getmtime)
    return datetime.datetime.fromtimestamp(os.path.getmtime(newest), datetime.timezone.utc).isoformat()


def live(since=None, notebook=NOTEBOOK, releases=None):
    """Outcome counts of the live Lab's reviews since `since`, with one example question each. With no time given
    it starts at the last deploy: counting from a fixed window read a change off reviews that ran before it."""
    import datetime
    deployed = last_deploy(releases)
    not_given = since is None
    since = since or deployed or (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=12)).isoformat()
    counts, examples, total = {}, {}, 0
    # Attempts and distinct questions are counted apart: repeated attempts at one question inflate whichever
    # class it keeps landing in, and the counts alone cannot show that (Chat's review, 2026-10-14).
    by_question, question_counts = {}, {}
    for row in _rows(notebook):
        if str(row.get("at") or "") < since: continue
        status = row.get("review_outcome") or LCE.outcome(row)[0]
        total += 1; counts[status] = counts.get(status, 0) + 1
        q = str((row.get("inquiry") or {}).get("question") or "")
        by_question.setdefault(q, []).append(status)
        examples.setdefault(status, (q[:120], str(row.get("review_outcome_why") or LCE.outcome(row)[1])[:160]))
    for q, seen in by_question.items():
        best = next((x for x in ("answered", "partially_supported") if x in seen), seen[-1])
        question_counts[best] = question_counts.get(best, 0) + 1
    repeated = sorted(((len(v), k) for k, v in by_question.items() if len(v) > 1), reverse=True)[:5]
    return {"since": since, "from_deploy": bool(not_given and deployed), "deployed_at": deployed,
            "reviews": total, "counts": counts, "examples": examples,
            "questions": len(by_question), "question_counts": question_counts,
            "most_repeated": [{"attempts": n, "question": q[:110]} for n, q in repeated]}


def overflow(limit=12, root=None):
    """The size breakdown of the coverage requests that did not fit. Which part is oversized decides the repair,
    and the counts alone cannot say (Chat's review, 2026-10-14): a question, the standing instructions, one
    indivisible evidence item and the combining request are four different defects."""
    import chemistry_lab as C
    directory = os.path.join(root or C.ROOT, "coverage-deferred")
    out = []
    try:
        names = sorted(os.listdir(directory), key=lambda n: -os.path.getmtime(os.path.join(directory, n)))
    except OSError:
        return out
    for name in names[:limit]:
        try:
            payload = json.load(open(os.path.join(directory, name)))
        except (OSError, ValueError):
            continue
        evidence = payload.get("coverage_evidence") or {}
        items = []
        def walk(value, path):
            if isinstance(value, str):
                items.append((path, len(value)))
            elif isinstance(value, dict):
                for k, v in value.items(): walk(v, path + "." + str(k))
            elif isinstance(value, list):
                for i, v in enumerate(value): walk(v, path + "." + str(i))
        walk(evidence, "evidence")
        items.sort(key=lambda kv: -kv[1])
        total = sum(n for _, n in items)
        question = len(str((payload.get("inquiry") or {}).get("question") or ""))
        prepared = None
        try:
            prepared = C._coverage_request(payload.get("inquiry") or {}, payload.get("observations") or {})
        except Exception:
            pass
        instructions = len(prepared[3][0]) + len(prepared[3][1]) - total if prepared else None
        out.append({"snapshot": name, "question_chars": question, "evidence_chars": total,
                    "evidence_items": len(items), "request_chars_minus_evidence": instructions,
                    "largest": [{"path": p, "chars": n} for p, n in items[:5]],
                    "largest_share": round(items[0][1] / total, 3) if items and total else None})
    return out


def summary(results):
    searched = [r for r in results if r["before"] in LCE.SEARCHABLE]
    better = [r for r in searched if r.get("after") == "answered"
              or r.get("supports_after", 0) > r["supports_before"]]
    return {"questions": len(results), "missing_evidence": len(searched),
            "answered_after": sum(1 for r in searched if r.get("after") == "answered"),
            "more_supported_after": len(better),
            "checker_failed_after": sum(1 for r in searched if r.get("after") in LCE.SOFTWARE),
            "not_searchable": len(results) - len(searched)}


def main(argv):
    cmd = argv[0] if argv else "audit"
    if cmd == "pick":
        n = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 20
        items = pick(n, force="--force" in argv)
        print("fixed set: %d questions -> %s" % (len(items), SET)); return 0
    if cmd == "overflow":
        rows = overflow()
        if not rows:
            print("no deferred coverage snapshots"); return 0
        for r in rows:
            print("- %s\n    question %d chars · evidence %d chars in %d items · request minus evidence %s"
                  % (r["snapshot"][:12], r["question_chars"], r["evidence_chars"], r["evidence_items"],
                     r["request_chars_minus_evidence"]))
            for item in r["largest"]:
                print("      %7d  %s" % (item["chars"], item["path"]))
            print("      largest single item is %s of the evidence" %
                  ("%.0f%%" % (100 * r["largest_share"]) if r["largest_share"] is not None else "?"))
        return 0
    if cmd == "live":
        got = live(argv[1] if len(argv) > 1 else None)
        print("since %s%s: %d reviews of %d distinct questions"
              % (got["since"], " (the last deploy)" if got.get("from_deploy") else "", got["reviews"], got["questions"]))
        if got["reviews"] < 20:
            print("  — too few to read a change from; let it run and ask again")
        print("by attempt:")
        for status, n in sorted(got["counts"].items(), key=lambda kv: -kv[1]):
            q, why = got["examples"][status]
            print("  %3d %s\n      e.g. %s\n      %s" % (n, status, q, why))
        print("by distinct question (its best outcome):")
        for status, n in sorted(got["question_counts"].items(), key=lambda kv: -kv[1]):
            print("  %3d %s" % (n, status))
        if got["most_repeated"]:
            print("most repeated:")
            for row in got["most_repeated"]:
                print("  %2dx %s" % (row["attempts"], row["question"]))
        return 0
    if not os.path.exists(SET):
        print("no fixed set yet: run  python3 scripts/lab_claim_replay.py pick"); return 1
    items = json.load(open(SET))
    if cmd == "audit":
        for a in audit(items):
            print("%2d. [%s] %s\n    %s\n    %s" % (a["n"], a["outcome"], a["question"][:150], a["kind"], a["why"][:200]))
        return 0
    if cmd == "recheck":
        rows = recheck(items)
        for r in rows:
            print("- %s\n    %s -> %s | %s" % (r["question"][:140], r["before"], r["now"], r["why"][:220]))
        counts = {}
        for r in rows: counts[r["now"]] = counts.get(r["now"], 0) + 1
        print("now:", json.dumps(counts))
        return 0
    if cmd == "run":
        results = run(items, fetch=LCE.live_fetch())
        report = {"summary": summary(results), "results": results}
        json.dump(report, open(REPORT, "w"), ensure_ascii=False, indent=1)
        for r in results:
            print("- %s\n    %s -> %s | supports %s -> %s | searches %s new, %s reused | passages %s%s" % (
                r["question"][:140], r["before"], r.get("after"), r["supports_before"], r.get("supports_after", "-"),
                r.get("searches", 0), r.get("reused", 0), r.get("passages", 0),
                ("\n    note: " + r["note"]) if r.get("note") else ""))
        print("summary:", json.dumps(report["summary"]))
        print("report:", REPORT)
        return 0
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
