#!/usr/bin/env python3
"""One-off, 15 October 2026: finish what he wanted done today, then close the day so tomorrow starts clean.

Gloria, 16 October: "I'd rather you and I complete whatever he wanted to do today and mark what we can of his
tasks and Slack campaigns complete so that he starts off with a clean slate next time."

    python3 scripts/clean_slate_20261015.py finish          # the two things that waited only on an install
    python3 scripts/clean_slate_20261015.py close           # shows what would close, and how; changes nothing
    python3 scripts/clean_slate_20261015.py close --apply   # closes it (the dot-channel timer is held meanwhile)

finish (her running it is her approval; dot could not take his):
  - json_repair against the Lab's latest failure, 72f5b73e (dot already ran the strict parse and all eight
    recovery variants: every one failed at line 4, column 1). Installed into ~/.vintos/tools/json-repair/ only.
  - eliot-tree over the Lab's own Eliot logs (eliot was installed on 15 October). Into ~/.vintos/tools/eliot-tree/.
  Reports go to memory/reports/2026-10-15/, where he can read them. Nothing live is written; the raw file is copied.

close: each open thing is closed with what actually happened that day. Done only where something anyone could check
exists; everything else is "closed by Gloria", which does not settle the topic, so he can take it up fresh.
"""
import glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
LAB = os.path.join(MEMORY, "chemistry-lab")
RAW = os.path.join(LAB, "diagnostics", "72f5b73e8d754476a446382e778ca1ce.raw.txt")
OUT = os.path.join(MEMORY, "reports", "2026-10-15")
TOOLS = os.path.expanduser("~/.vintos/tools")
JR_REPORT = os.path.join(OUT, "json-repair-72f5b73e.md")
ET_REPORT = os.path.join(OUT, "eliot-tree.md")
DOT_72F5 = "C:/Users/glori/Documents/Codex/2026-10-08/task/json-parser-72f5b73e-20261016/report.md"
UNIT = "vintos-dot-channel"
# Questions on her phone that the day already answered (each pattern, and why it is moot).
MOOT = ((r"lab_intake_token_file", "the 403 was the Forge's capacity guard"),
        (r"403 Forbidden", "the 403s were the Forge's capacity guard (four_unfinished), not a key"),
        (r"lab_forge_consumer", "Study fix SF-7ff16979 handled it and is live"),
        (r"ValueMap LLM call errors on a missing 'choices'", "Study fix SF-c727a850 handled it and is live"),
        (r"install official Eliot", "eliot was installed in both of the Lab's interpreters on 15 October"))
SAID_CLEAN = "closed by Gloria for a clean slate (2026-10-15); not done, take it up fresh if it still matters"


# ---------------------------------------------------------------- finish
def _venv(name, package):
    root = os.path.join(TOOLS, name)
    py = os.path.join(root, "bin", "python")
    if not os.path.exists(py):
        subprocess.run([sys.executable, "-m", "venv", root], check=True)
    subprocess.run([py, "-m", "pip", "install", "--quiet", "--upgrade", package], check=True)
    return root, py


JR_PROBE = r'''
import json, re, sys
import json_repair
raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
try:
    from importlib.metadata import version as _v; ver = _v("json-repair")
except Exception:
    ver = getattr(json_repair, "__version__", "?")
out = {"version": ver}
try:
    json.loads(raw); out["strict"] = "parsed"
except ValueError as e:
    out["strict"] = "failed: %s" % e
body = re.sub(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", "", raw)
try:
    got = json_repair.repair_json(body, return_objects=True, logging=True)
    obj, log = got if isinstance(got, tuple) else (got, None)
except TypeError:
    obj, log = json_repair.repair_json(body, return_objects=True), None
out["repaired"] = obj
out["repaired_kind"] = type(obj).__name__
out["repair_log"] = log
s = body.rstrip()
out["ends_with"] = s[-80:]
out["open_braces"] = s.count("{") - s.count("}")
out["open_brackets"] = s.count("[") - s.count("]")
out["odd_quotes"] = (len(re.findall(r'(?<!\\)"', s)) % 2) == 1
print(json.dumps(out, ensure_ascii=False, default=str))
'''


def finish_json_repair():
    if not os.path.exists(RAW):
        return "json_repair: %s is not there; nothing ran" % RAW
    _, py = _venv("json-repair", "json-repair")
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, os.path.basename(RAW)); shutil.copy2(RAW, copy)
        probe = os.path.join(tmp, "probe.py"); open(probe, "w").write(JR_PROBE)
        done = subprocess.run([py, "-I", probe, copy], capture_output=True, text=True, timeout=120)
    if done.returncode:
        return "json_repair: the run failed: %s" % (done.stderr or done.stdout).strip()[-400:]
    r = json.loads(done.stdout.strip().splitlines()[-1])
    raw = open(RAW, encoding="utf-8", errors="replace").read()
    empty = r["repaired"] in ("", None, {}, [])
    truncated = r["open_braces"] > 0 or r["open_brackets"] > 0 or r["odd_quotes"]
    verdict = ("json_repair found no JSON object either: the reply held none to repair, so this is the prompt or the "
               "model's answer, not a cut-off" if empty and not truncated else
               "the text ends open (braces %d, brackets %d, odd quotes %s): truncation is likely, and json_repair's "
               "closing of it would hide that" % (r["open_braces"], r["open_brackets"], r["odd_quotes"]) if truncated else
               "json_repair returned an object where the Lab's parser returned none; every repair it made is listed below, "
               "and an object made this way is a guess, not the model's answer")
    os.makedirs(OUT, exist_ok=True)
    with open(JR_REPORT, "w", encoding="utf-8") as f:
        f.write("# json_repair against the Lab's 72f5b73e failure (15 October)\n\n"
                "Input: `%s` (%d bytes, sha256 %s), read from a copy; the original is untouched.\n"
                "Lab parser (dot's run, %s): the strict parse and all eight recovery variants failed at line 4, "
                "column 1 (character 101); only Markdown fences were removed; no JSON object.\n\n"
                "json_repair %s:\n- strict json.loads: %s\n- repaired to: %s `%s`\n- repairs it reports: %s\n"
                "- the text ends with: `%s`\n\n**What it shows:** %s.\n\nThe input itself:\n\n```\n%s\n```\n" % (
                    RAW, len(raw.encode()), hashlib.sha256(raw.encode()).hexdigest(), DOT_72F5, r["version"],
                    r["strict"], r["repaired_kind"], json.dumps(r["repaired"], ensure_ascii=False)[:1500],
                    json.dumps(r["repair_log"], ensure_ascii=False)[:2000] if r["repair_log"] is not None else
                    "(this version keeps no log)", r["ends_with"].replace("`", "'"), verdict, raw[:4000]))
    return "json_repair: report at %s (%s)" % (JR_REPORT, verdict.split(":")[0])


def finish_eliot_tree():
    logs = [p for p in (os.path.join(LAB, "eliot.jsonl"), os.path.join(LAB, "diagnostics", "eliot-esmfold.log"))
            if os.path.exists(p) and os.path.getsize(p) > 0]
    if not logs:
        return "eliot-tree: neither Eliot log has anything in it yet; nothing to draw (eliot is installed, so the next traced run fills it)"
    root, _ = _venv("eliot-tree", "eliot-tree")
    tool = os.path.join(root, "bin", "eliot-tree")
    os.makedirs(OUT, exist_ok=True)
    parts = []
    for log in logs:
        with tempfile.TemporaryDirectory() as tmp:
            tail = os.path.join(tmp, "tail.jsonl")
            lines = open(log, encoding="utf-8", errors="replace").read().splitlines()[-400:]
            open(tail, "w").write("\n".join(lines) + "\n")
            done = subprocess.run([tool, tail], capture_output=True, text=True, timeout=120)
        parts.append("## %s (last %d lines)\n\n```\n%s\n```\n" % (log, len(lines), (done.stdout or done.stderr).strip()[:12000]))
    with open(ET_REPORT, "w", encoding="utf-8") as f:
        f.write("# eliot-tree over the Lab's own Eliot logs (15 October)\n\n" + "\n".join(parts))
    nested = "└──" in open(ET_REPORT, encoding="utf-8").read() or "├──" in open(ET_REPORT, encoding="utf-8").read()
    return "eliot-tree: report at %s (%s)" % (ET_REPORT, "nested actions drawn" if nested else "drawn; check whether it nests")


# ---------------------------------------------------------------- close
def _has(path):
    return os.path.exists(path) and os.path.getsize(path) > 0


def outcome(text):
    """(state, said) for one open thing, from what the day actually produced."""
    t = str(text or "")
    if re.search(r"72f5b73e|route 3|RW-5b074682", t):
        return "done", ("72f5b73e: the strict parse and all eight recovery variants fail at line 4, column 1; no JSON "
                        "object; dot's report %s%s" % (DOT_72F5, ("; json_repair: " + JR_REPORT) if _has(JR_REPORT) else ""))
    if re.search(r"json[_ -]?repair|RW-ece5aa79|Firmicutes", t, re.I):
        return ("done", "json_repair compared on the latest real failure, 72f5b73e (the 10 October input is gone): " + JR_REPORT) \
            if _has(JR_REPORT) else ("closed by Gloria", "json_repair was never installed; the 10 October input is gone (FIND and GREP, 15 October)")
    if re.search(r"eliot|EC-26dfc8a4|RW-8f42cff7", t, re.I):
        return ("done", "eliot-tree drawn from the Lab's own logs: " + ET_REPORT) if _has(ET_REPORT) else \
            ("closed by Gloria", "eliot is installed in both of the Lab's interpreters (readiness OK, 15 October); no tree drawn yet")
    if re.search(r"8SGW|EC-45d55a56|TM-score", t, re.I):
        return "done", ("TM-score 0.934, RMSD 1.89 A over 127 residues: O43511-60e20d840671.pdb against 8SGW chain C "
                        "(535-729); 586-653 has no density in the entry")
    if re.search(r"403|forge.report|credential", t, re.I):
        return "done", ("the 403 was the Forge's capacity guard (four_unfinished, chemistry-lab/faults.jsonl:32080), not a "
                        "credential mismatch; nothing to fix in the credentials")
    if re.search(r"SF-217d86de|named.retrieval", t, re.I):
        return "done", ("the guard at chemistry_lab.py:1288 already holds and quarantines; no fix without the offending "
                        "saved request (dot, 15 October)")
    if re.search(r"RC-fd7ae830|467ae274", t, re.I):
        return "done", "467ae2741588407aae5a562f6915c838.raw.txt is gone from Aegis (FIND raw.txt, FIND and GREP of the ID, 15 October)"
    if re.search(r"Machine Girl", t, re.I):
        return "done", "asked; Gloria answered no (15 October)"
    return "closed by Gloria", SAID_CLEAN


def _timer(action):
    try:
        subprocess.run(["systemctl", "--user", action, UNIT + ".timer"], check=False, capture_output=True, timeout=30)
        if action == "stop":
            for _ in range(60):
                live = subprocess.run(["systemctl", "--user", "is-active", UNIT + ".service"], capture_output=True, text=True)
                if live.stdout.strip() not in ("active", "activating"): break
                time.sleep(5)
    except Exception:
        pass


def close(apply):
    import room_work, promise_keeper, email_commitments, gloria_asks
    import dot_channel as D
    now = time.time()
    lines = []
    if apply: _timer("stop")
    try:
        state = D._load(D.STATE, {})
        for w in room_work.open_items(state):
            word, said = outcome("%s %s" % (w.get("id"), w.get("goal")))
            lines.append("work %s [%s] %s -> %s: %s" % (w.get("id"), w.get("state", "open"), str(w.get("goal"))[:90], word, said[:140]))
            if apply and room_work._close(state, w, word, said, now) is None:
                lines.append("   (not closed: it is waiting on evidence the house tracks; left as it is)")
        g = room_work.goal(state)
        if g:
            word, said = outcome("%s %s %s" % (g.get("id"), g.get("goal"), json.dumps(g.get("routes", []))[-600:]))
            said = ("Reached: " if word == "done" else "") + said
            lines.append("campaign %s %s -> closed: %s" % (g.get("id"), str(g.get("goal"))[:90], said[:160]))
            if apply: room_work.gloria_drops_goal(state, now, "Gloria: " + said)
        lo = room_work.loose(state)
        if lo.get("asks") or lo.get("returns"):
            lines.append("loose asks: %d, returns: %d -> cleared" % (len(lo.get("asks", [])), len(lo.get("returns", []))))
            if apply: room_work.board(state)["loose"] = {"id": "loose", "goal": "", "asks": [], "returns": [], "steps": []}
        if apply: D._save(D.STATE, state)

        d = promise_keeper.load()
        for i in d.get("items", []):
            if i.get("state") == "open":
                word, said = outcome("%s %s" % (i.get("quote"), i.get("what")))
                st = "reshaped" if word == "done" else "dropped"
                lines.append("promise %s \u201c%s\u201d -> %s: %s" % (i["id"], str(i.get("quote"))[:70], st, said[:120]))
                if apply:
                    i.update(state=st, result=said[:1500], ended=datetime.now().isoformat(timespec="seconds"),
                             posted=True, held="closed in Gloria's clean slate; not sent to her")
        if apply: promise_keeper.save(d)

        rows = email_commitments._load()
        for r in rows:
            if r.get("state") in ("open", "in work"):
                word, said = outcome("%s %s %s" % (r.get("id"), r.get("quote"), r.get("evidence")))
                st = "done" if word == "done" else "dropped"
                lines.append("email promise %s \u201c%s\u201d -> %s: %s" % (r["id"], str(r.get("quote"))[:70], st, said[:120]))
                if apply: r.update(state=st, closed_said=said[:300], closed_at=datetime.now().isoformat(timespec="seconds"))
        if apply: email_commitments._save(rows)

        for a in gloria_asks.load():
            if a.get("state") == "asked":
                why = next((w for pat, w in MOOT if re.search(pat, json.dumps(a), re.I)), "")
                lines.append("ask %s \u201c%s\u201d -> %s" % (a.get("id"), str(a.get("question"))[:90],
                                                         ("answered no: moot, " + why) if why else "left for you"))
                if apply and why: gloria_asks.decide(a["id"], "no", how="her clean slate: moot, " + why)
    finally:
        if apply: _timer("start")
    print("\n".join(lines) or "nothing open")
    print("\n" + ("done." if apply else "nothing changed. Run again with --apply to close these."))


def main(argv):
    if argv[:1] == ["finish"]:
        for step in (finish_json_repair, finish_eliot_tree):
            try: print(step())
            except Exception as exc: print("%s: %s: %s" % (step.__name__, type(exc).__name__, exc))
        return 0
    if argv[:1] == ["close"]:
        close("--apply" in argv); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
