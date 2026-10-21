#!/usr/bin/env python3
"""Read-only probe: why the Lab's reviews say no, and what its spent-subject refusals actually matched.

Reads, never writes: notebook.jsonl, spent-subjects.json, lines.json under the Lab's workspace.
Standard library only; imports nothing from the Lab, calls nothing, sends nothing.

    python3 -I lab_refusals_probe.py            # last 24 hours
    python3 -I lab_refusals_probe.py 48         # last 48 hours

What each section's answer means is printed beside it, and spelled out in docs/lab-refusals-review.md.
"""
import json, os, re, sys, time
from collections import Counter
from datetime import datetime

HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
LAB = os.path.join(WS, "memory", "chemistry-lab")
NOW = time.time(); SINCE = NOW - HOURS * 3600


def when(row):
    try: return datetime.fromisoformat(str(row.get("at", "")).replace("Z", "+00:00")).timestamp()
    except ValueError: return 0.0


def rows():
    with open(os.path.join(LAB, "notebook.jsonl"), encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"at"' not in line: continue
            try: row = json.loads(line)
            except ValueError: continue
            if isinstance(row, dict) and when(row) >= SINCE: yield row


# The three-claim shape the planner prompt (fa96b0a), _record_connection_question and _fresh_free_inquiry ask for.
STRUCT = re.compile(r"structur\w*|hallmark\w*|feature\w*|motif\w*|domain\w*", re.I)
FUNC = re.compile(r"function\w*|role\w*", re.I)
REL = re.compile(r"relationship\w*|relat\w+ (?:between|to)|connect\w*", re.I)
SECOND = re.compile(r"(?:,\s*|\s+)(?:and\s+(?:how|why|what|which|whether|do|does|did|is|are|can|could)\b"
                    r"|(?:as\s+)?compared\s+(?:to|with)\b)", re.I)


def shape(q):
    q = str(q or "")
    if STRUCT.search(q) and FUNC.search(q) and REL.search(q): return "three-claim"
    if STRUCT.search(q) and FUNC.search(q): return "structure+function"
    if SECOND.search(q): return "two-ask"
    return "one-ask"


def origin(inq):
    why = str((inq or {}).get("why_now") or "")
    if "source-grounded recovery" in why: return "sourced-record template"
    if "fresh source discovery" in why: return "fresh-protein list"
    if (inq or {}).get("line_id"): return "planner, on a line"
    return "planner, free"


def verdict(row):
    v = str(row.get("answers_question") or "").strip().lower()
    for k in ("yes", "no", "not assessed", "not established"):
        if v.startswith(k): return k
    return "other"


reviews, refused, waits = [], [], []
for row in rows():
    k = row.get("kind")
    if k in ("reflection", "genome_reflection") and "answers_question" in row: reviews.append(row)
    elif k == "inquiry_refused": refused.append(row)
    elif k == "evidence_wait": waits.append(row)

print("window: last %.0f h; %d reviews, %d refused, %d evidence_wait\n" % (HOURS, len(reviews), len(refused), len(waits)))

print("== A. Review verdicts by question shape ==")
table = {}
for r in reviews:
    s = shape((r.get("inquiry") or {}).get("question") or r.get("question"))
    table.setdefault(s, Counter())[verdict(r)] += 1
for s in ("three-claim", "structure+function", "two-ask", "one-ask"):
    c = table.get(s, Counter()); n = sum(c.values())
    print("  %-20s n=%4d  yes=%4d (%3.0f%%)  no=%4d  not-assessed=%3d" % (
        s, n, c["yes"], 100.0 * c["yes"] / n if n else 0, c["no"], c["not assessed"]))
print("  -> three-claim + structure+function a large share with ~0% yes, and one-ask yes well above 6%:\n"
      "     the question shape is the upstream cause. one-ask also near 6%: it is not; read B and C.\n")

print("== B. Where the reviewed questions come from ==")
by = {}
for r in reviews:
    inq = r.get("inquiry") or {}
    by.setdefault(origin(inq), Counter())[(shape(inq.get("question")), verdict(r) == "yes")] += 1
for o, c in sorted(by.items()):
    n = sum(c.values()); y = sum(v for (s, ok), v in c.items() if ok)
    three = sum(v for (s, ok), v in c.items() if s in ("three-claim", "structure+function"))
    print("  %-26s n=%4d  yes=%3d  multi-claim shape=%4d" % (o, n, y, three))
print()

print("== C. 'no' reviews: did evidence reach the checker? ==")
nos = [r for r in reviews if verdict(r) == "no"]
with_support = sum(1 for r in nos if (r.get("coverage_check") or {}).get("supports"))
missing = Counter()
for r in nos:
    for m in (r.get("coverage_check") or {}).get("missing") or []:
        t = str(m).lower()
        missing["relationship/connection" if REL.search(t) or "between" in t else
                "function/role" if FUNC.search(t) else
                "structure/feature" if STRUCT.search(t) else "identity/other"] += 1
print("  'no' with at least one quoted support: %d of %d" % (with_support, len(nos)))
print("  what the checker said was missing:", dict(missing.most_common()))
print("  -> supports present and 'relationship' leading the missing list: evidence arrives, the question asks for\n"
      "     a sentence no record has. supports mostly empty: evidence is not reaching the review (a different bug).\n")

print("== D. Spent-subject refusals: what the gate matched ==")
spent_rows = [r for r in refused + waits if "spent subject" in str(r.get("why"))]
path = Counter(); place = Counter(); subj = Counter()
for r in spent_rows:
    why = str(r.get("why")); inq = r.get("inquiry") or {}
    path[why.split(":")[0] if not why.startswith("spent subject") else "planner (first or re-plan)"] += 1
    names = re.findall(r"\(([^()]*)\)\s*$", why)
    names = [n.strip() for n in names[0].split(",")] if names else []
    sq = inq.get("source_query") or {}
    field = " ".join([str(inq.get("uniprot_query") or ""), str(sq.get("term") or ""), str(sq.get("query") or "")])
    for n in names:
        subj[n] += 1
        pat = r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])"
        place["in its query field (planner chose it)" if re.search(pat, field, re.I) else
              "only in question prose (broad match)"] += 1
print("  turns:", len(spent_rows), " by path:", dict(path))
print("  where the matched name sat:", dict(place))
print("  most-refused names:", subj.most_common(15))
print("  -> mostly 'query field': the planner chooses listed subjects despite the list.\n"
      "     mostly 'question prose': the gate matches words, not subjects (a different fix).\n")

print("== E. What the spent list is made of ==")
try: spent = json.load(open(os.path.join(LAB, "spent-subjects.json")))
except (OSError, ValueError): spent = {}
held = {k: v for k, v in spent.items() if isinstance(v, dict) and NOW - float(v.get("at", 0)) < 86400}
reviewed_text = " ".join(json.dumps(r.get("inquiry") or {}) for r in reviews)
asked_text = " ".join(json.dumps(r.get("inquiry") or {}) for r in refused + waits)
never_reviewed = [v["subject"] for v in held.values()
                  if not re.search(r"(?<![A-Za-z0-9])" + re.escape(str(v.get("subject"))) + r"(?![A-Za-z0-9])", reviewed_text, re.I)]
try: lines = json.load(open(os.path.join(LAB, "lines.json"))).get("lines", [])
except (OSError, ValueError): lines = []
open_text = " ".join(str(l.get("question", "")) for l in lines if l.get("state") == "open")
on_lines = [v["subject"] for v in held.values()
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(str(v.get("subject"))) + r"(?![A-Za-z0-9])", open_text, re.I)]
print("  held now: %d; never in a reviewed inquiry in this window: %d; named by an open line: %d" % (
    len(held), len(never_reviewed), len(on_lines)))
print("  sample never reviewed:", never_reviewed[:12])
print("  sample on open lines:", on_lines[:12])
print("  -> many held subjects never reviewed: refusals alone are spending subjects (dead_ends counts them).\n"
      "     many on open lines: the planner is being shown the subjects it is told not to choose.")
