#!/usr/bin/env python3
"""One pearl gate (Gloria 2026-11-14). Every pearl comes through the same gate: proposal or his own
declaration -> verification (4 passes in 7 days, at most 1 failure, a pressure state) -> review ->
form_pearl(). This suite fails if a path that writes a pearl, or advances a candidate, without that
gate comes back. Synthetic fixtures only; scratch HOME; every sender is stubbed."""
import ast, json, os, pathlib, re, socket, sys, tempfile, types
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
FAILS = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def fn_source(path, name):
    src = pathlib.Path(path).read_text()
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(src, node)


with tempfile.TemporaryDirectory(prefix="pearl-gate-") as tmp:
    os.environ["HOME"] = tmp
    os.environ["SPARK_WORKSPACE"] = tmp + "/.vintos/workspace"
    sys.path[:0] = [str(ROOT / "scripts")]

    def forbidden(*a, **k):
        raise AssertionError("sender forbidden")
    socket.socket.connect = forbidden
    replies = []          # what the stubbed local model answers, in order
    def fake_post(url, json=None, timeout=None):
        if not replies:
            raise RuntimeError("no model in tests")
        r = replies.pop(0)
        return types.SimpleNamespace(json=lambda: {"choices": [{"message": {"content": r}}]})
    sys.modules["requests"] = types.SimpleNamespace(post=fake_post)
    state = {"Tension": 0.1, "Arousal": 0.1, "Groundedness": 0.9}
    sys.modules["emoclaw_utils"] = types.SimpleNamespace(get_state=lambda: dict(state))
    fragments = []
    sys.modules["narrative_identity"] = types.SimpleNamespace(propose_fragment=lambda *a, **k: fragments.append(a))
    sys.modules["yearning_scars"] = types.SimpleNamespace(reduce_scar_influence=lambda *a, **k: None)
    import pearl_engine as P
    MEM = pathlib.Path(P.MEMORY)
    MEM.mkdir(parents=True, exist_ok=True)
    check("isolation: stores are throwaway and the sender is a stub",
          P.CANDIDATES_FILE.startswith(tmp) and P.PEARLS_DIR.startswith(tmp) and socket.socket.connect is forbidden)
    pearl_files = lambda: sorted(pathlib.Path(P.PEARLS_DIR).glob("*.md")) if os.path.isdir(P.PEARLS_DIR) else []
    cands = lambda: {c["id"]: c for c in P.load_candidates()["candidates"]}

    # ---- 1. the pressure gate: Tension > 0.33; the Arousal/Groundedness branch unchanged
    check("gate constant is 0.33", P.PRESSURE_TENSION == 0.33)
    for t, want in ((0.34, True), (0.331, True), (0.33, False), (0.30, False), (0.43, True), (0.44, True)):
        state.update(Tension=t, Arousal=0.1, Groundedness=0.9)
        check("Tension %.3f -> pressure %s" % (t, want), P.is_pressure_state() is want)
    state.update(Tension=0.1, Arousal=0.6, Groundedness=0.5)
    check("Arousal>0.55 with Groundedness<0.54 is still pressure", P.is_pressure_state() is True)
    state.update(Tension=0.1, Arousal=0.6, Groundedness=0.6)
    check("Arousal alone is not", P.is_pressure_state() is False)

    # ---- 2. the 2-failure rule is unchanged: one failure survives, the second dissolves
    check("threshold unchanged", P.THRESHOLD == {"required_passes": 4, "max_failures": 1, "days_window": 7})
    cid = P.add_candidate("synthetic friction one", "scar", "mirror:2026-11-14", "insight one", "declaration one")
    state.update(Tension=0.1, Arousal=0.1, Groundedness=0.9)
    replies[:] = ["FAIL"]
    r1 = P.check_candidate(cid, "response a")
    replies[:] = ["FAIL"]
    r2 = P.check_candidate(cid, "response b")
    check("first failure is recorded, second dissolves", r1 == "FAIL" and r2 == "dissolved" and cands()[cid]["dissolved"])

    # ---- 3. the full gate still forms a pearl, and writes a receipt
    cid = P.add_candidate("synthetic friction two", "scar", "therapy:2026-11-14", "insight two", "declaration two")
    state.update(Tension=0.35)      # pressure only under the new gate
    for i in range(3):
        replies[:] = ["PASS"]
        P.check_candidate(cid, "pass %d" % i)
    replies[:] = ["PASS", '{"accurate": true, "concern": ""}']
    res = P.check_candidate(cid, "pass 3")
    c = cands()[cid]
    check("4 passes + pressure at 0.35 + review -> ready, with a gate receipt",
          res == "ready" and c["stage"] == 3 and P.gate_receipt_ok(c) and c["gate"]["pressure_tension"] == 0.33)
    check("each grade records the Tension read", c["verification"]["evaluations"][-1]["tension"] == 0.35)
    replies[:] = ["A synthetic sealed sentence."]
    path = P.form_pearl(cid)
    check("form_pearl seals it, with a Gate line and a narrative fragment",
          path and "**Gate:** verified" in open(path).read() and cands()[cid]["stage"] == 4 and fragments)

    # ---- 4. bypass: a stage-3 set by hand (no receipt) is refused by form_pearl
    before = len(pearl_files())
    cid = P.add_candidate("synthetic friction three", "scar", "mirror:x", "i3", "d3")
    d = P.load_candidates()
    for c in d["candidates"]:
        if c["id"] == cid:
            c["stage"] = 3
    P.save_candidates(d)
    check("stage 3 without a gate receipt is refused", P.form_pearl(cid) is None and len(pearl_files()) == before)
    check("form_ready_pearls forms nothing from it", P.form_ready_pearls() == [] and len(pearl_files()) == before)

    # ---- 5. bypass: a stage-0 proposal is never graded forward
    pid = P.add_candidate("synthetic proposed friction", "scar", "causality", "i4", "d4")
    check("organ proposals enter at stage 0", cands()[pid]["stage"] == 0)
    replies[:] = ["PASS"] * 10
    check("check_candidate refuses a stage-0 proposal", P.check_candidate(pid, "x") is None and cands()[pid]["stage"] == 0)

    # ---- 6. bypass: the held-pass (server) only releases a HELD candidate whose verification was met
    check("release_held refuses a never-verified candidate", P.release_held(pid) is False and cands()[pid]["stage"] == 0)
    cid = P.add_candidate("synthetic friction five", "scar", "mirror:y", "i5", "d5")
    state.update(Tension=0.5)
    for i in range(3):
        replies[:] = ["PASS"]
        P.check_candidate(cid, "p%d" % i)
    replies[:] = ["PASS", '{"accurate": false, "concern": "synthetic"}']
    check("the reviewer can hold it", P.check_candidate(cid, "p3") == "held" and cands()[cid]["gate"]["review"] == "held")
    check("Gloria's pass releases a held, verified candidate", P.release_held(cid, by="gloria") is True
          and cands()[cid]["stage"] == 3 and P.gate_receipt_ok(cands()[cid]))
    srv = (ROOT / "bin/server.py").read_text()
    seg = srv[srv.index("async def pass_held_item"):srv.index("async def dismiss_held_item")]
    check("the server's held-pass goes through release_held and sets no stage itself",
          "release_held(" in seg and not re.search(r"\[[\"']stage[\"']\]\s*=", seg))

    # ---- 7. bypass: WAL graduation (emoclaw_utils.add_pearl + wal-decay) proposes, never writes a file
    ns = {"os": os, "__file__": str(ROOT / "scripts/emoclaw_utils.py")}
    exec(fn_source(ROOT / "scripts/emoclaw_utils.py", "add_pearl"), ns)
    before = len(pearl_files())
    got = ns["add_pearl"]("Synthetic memory line that the monthly judge graduated.", source="wal-graduation")
    check("add_pearl writes no pearl file and makes a stage-0 proposal",
          len(pearl_files()) == before and got in cands() and cands()[got]["stage"] == 0
          and cands()[got]["proposed_by"] == "wal-graduation")
    for wal in ("scripts/wal-decay.py", "bin/wal-decay.py"):
        saved = {}
        g = {"os": os, "json": json, "datetime": datetime, "timedelta": timedelta, "MEMORY": str(MEM),
             "WORKSPACE": str(MEM.parent), "WAL_LOG": str(MEM / "wal-log.json"), "WAL_ARCHIVE": str(MEM / "wal-archive.json"),
             "save_json": lambda p, d: saved.__setitem__(p, d), "_sync_remove_from_autowal": lambda s: None,
             "ask_model": lambda prompt: {"1": "pearl"}}
        exec(fn_source(ROOT / wal, "_monthly_review"), g)
        entry = {"content": "Synthetic promoted entry %s for graduation." % wal, "promoted": True,
                 "timestamp": (datetime.now() - timedelta(days=40)).isoformat()}
        before = len(pearl_files())
        g["_monthly_review"]([entry], datetime.now(), {"archived": []})
        check(wal + ": a graduation is a stage-0 proposal, not a pearl file",
              len(pearl_files()) == before and entry.get("pearl_candidate") in cands()
              and cands()[entry["pearl_candidate"]]["stage"] == 0 and not entry.get("pearl_graduated"))

    # ---- 8. bypass: thread resolution proposes, never writes a pearl file or index
    g = {"os": os, "re": re, "sys": sys, "log": lambda m: None, "__file__": str(ROOT / "bin/thread-resolution.py")}
    exec(fn_source(ROOT / "bin/thread-resolution.py", "create_pearl"), g)
    before = len(pearl_files())
    tid = g["create_pearl"]("## Thread Resolution — x\n\n**Original thread:** a synthetic thread\n", source="thread-resolution:x")
    check("thread-resolution writes no pearl file or index and makes a stage-0 proposal",
          len(pearl_files()) == before and not (pathlib.Path(P.PEARLS_DIR) / "index.json").exists()
          and tid in cands() and cands()[tid]["stage"] == 0)

    # ---- 9. static guard: nothing outside pearl_engine writes a pearl or advances a candidate
    allowed = {"scripts/pearl_engine.py", "bin/pearl_engine.py", "scripts/pearl_review.py",
               "scripts/correction_propagate.py", "bin/correction_propagate.py"}   # the last: appends a correction footer only
    offenders = []
    for f in list(ROOT.glob("scripts/**/*.py")) + list(ROOT.glob("bin/**/*.py")) + list(ROOT.glob("skills/**/*.py")) \
            + list(ROOT.glob("scripts/**/*.sh")) + list(ROOT.glob("bin/**/*.sh")) + list(ROOT.glob("skills/**/*.sh")):
        rel = str(f.relative_to(ROOT))
        if rel in allowed or f.is_symlink() or not f.is_file():
            continue
        try:
            src = f.read_text(errors="replace")
        except OSError:
            continue
        if "pearl" not in src.lower():
            continue
        for pat, why in ((r"""f["']pearl_\{""", "names a new pearl_*.md file"),
                         (r"(\b(PEARL_DIR|PEARLS_DIR)\b|[\"']pearls[\"'])[^\n]*[\"'](w|x|a)[\"']", "opens a file in pearls/ for writing"),
                         (r">\s*[\"']?\$?\{?[A-Z_]*PEARL[A-Z_]*\}?/", "shell redirect into pearls/"),
                         (r"\bsave_candidates\s*\(", "writes the candidate store directly"),
                         (r"save_pearl_index\s*\(", "writes pearls/index.json"),
                         (r"\badopted\s*=\s*True", "skips proposal by declaring adoption")):
            if re.search(pat, src):
                offenders.append("%s: %s" % (rel, why))
        if "candidate-pearls" in src or "load_candidates" in src:
            if re.search(r"""\[["']stage["']\]\s*=\s*[1-4]""", src):
                offenders.append("%s: sets a candidate stage" % rel)
    check("no other writer of pearls or candidate stages: " + "; ".join(offenders), not offenders)

    # ---- 10. the gate's own proposers are named and enter at stage 0 unless his own room
    a_id = P.propose("x synthetic proposal text", "causality_graduation")
    b_id = P.add_candidate("y synthetic own", "scar", "mirror:z", "i", "d")
    check("add_candidate from a non-adopting source is stage 0, from mirror/therapy stage 1",
          cands()[a_id]["stage"] == 0 and cands()[b_id]["stage"] == 1)

    check("no sender was ever reached", socket.socket.connect is forbidden)

if FAILS:
    print("%d FAILED" % len(FAILS))
    sys.exit(1)
print("PASS one pearl gate: 0.33 pressure, 2-failure rule, receipts, and no bypass writer")
