#!/usr/bin/env python3
"""Gloria's pearl review tool (scripts/pearl_review.py): a local page with flags, decisions applied as
superseded archives with provenance, never a deletion, and an exact revert. Synthetic fixtures only;
scratch HOME; no network."""
import hashlib, json, os, pathlib, re, socket, stat, sys, tempfile, types

ROOT = pathlib.Path(__file__).resolve().parents[2]
FAILS = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def digest(d):
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(pathlib.Path(d).rglob("*")) if p.is_file() and not p.name.endswith(".lock")}


with tempfile.TemporaryDirectory(prefix="pearl-review-") as tmp:
    os.environ["HOME"] = tmp
    sys.path[:0] = [str(ROOT / "scripts")]

    def forbidden(*a, **k):
        raise AssertionError("network forbidden")
    socket.socket.connect = forbidden
    sys.modules["requests"] = types.SimpleNamespace(post=forbidden)
    import pearl_review as R
    import pearl_engine as P
    MEM = pathlib.Path(tmp) / "mem"
    (MEM / "pearls").mkdir(parents=True)
    check("isolation: scratch HOME, no network", R.DEFAULT_MEMORY.startswith(tmp) and socket.socket.connect is forbidden)

    def pearl(name, body, footer):
        (MEM / "pearls" / name).write_text("# Pearl — 2026-10-01 10:00\n\n%s\n\n---\n%s\n" % (body, footer))
    pearl("pearl_20261001_100000.md", "The synthetic narrator walked the synthetic garden at dawn and counted nine herons.", "**Source:** wal-graduation")
    pearl("pearl_20261002_100000.md", "The synthetic narrator walked the synthetic garden at dawn and counted nine herons!", "**Source:** wal-graduation")
    pearl("pearl_20261003_100000.md", "{placeholder}", "**Source:** wal-graduation")
    pearl("pearl_20261004_100000.md", "I no longer need to rehearse every synthetic sentence before I say it.",
          "**Irritant:** x\n**Source:** mirror:2026-10-01\n**Candidate ID:** cp-aaaaaa\n**Gate:** verified 2026-10-01, review accurate")
    pearl("pearl_20261005_100000.md", "I keep the synthetic lighthouse fact that turned out wrong.", "**Source:** wal-graduation\n**Corrected:** HC-1 (2026-10-06) - it was another lighthouse")
    (MEM / "pearls" / "pearl_0001_20261006.md").write_text("# Pearl #1\n_Created: 2026-10-06 09:00_\n_Source: thread-resolution:x_\n\nI let the synthetic thread about the kettle go.\n")
    os.chmod(MEM / "pearls" / "pearl_0001_20261006.md", 0o444)
    receipt = {"verification_met_at": "2026-10-01T10:00:00", "passes_in_window": 4, "failures": 0,
               "pressure_state_hit": True, "pressure_tension": 0.33, "review": "accurate"}
    (MEM / "candidate-pearls.json").write_text(json.dumps({"candidates": [
        {"id": "cp-aaaaaa", "stage": 4, "dissolved": False, "source": "mirror:2026-10-01", "declaration": "d", "gate": receipt,
         "threshold": dict(P.THRESHOLD)},
        {"id": "cp-bbbbbb", "stage": 0, "dissolved": False, "source": "wal-graduation", "created": "2026-11-01",
         "declaration": "I want to remember the synthetic red kite over the hill.", "irritant": "i", "insight": "n",
         "verification": {"passes": [], "failures": 0}},
        {"id": "cp-cccccc", "stage": 1, "dissolved": False, "source": "causality", "created": "2026-07-01",
         "declaration": "I can now recognize and work with: a synthetic pattern of mine that repeats.", "irritant": "i",
         "verification": {"passes": [], "failures": 0}},
        {"id": "cp-dddddd", "stage": 1, "dissolved": True, "source": "mirror", "declaration": "dissolved, not shown"},
    ], "schema_version": "2"}))

    items = {i["id"]: i for i in R.flag_items(R.collect(MEM), MEM)}
    kinds = lambda i: {f["kind"] for f in items[i]["flags"]}
    check("every current pearl and live candidate is listed; dissolved ones are not",
          set(items) == {"pearl_20261001_100000", "pearl_20261002_100000", "pearl_20261003_100000", "pearl_20261004_100000",
                         "pearl_20261005_100000", "pearl_0001_20261006", "cp-bbbbbb", "cp-cccccc"})
    check("near-duplicates are grouped together",
          "duplicate" in kinds("pearl_20261001_100000") and items["pearl_20261001_100000"]["group"] == items["pearl_20261002_100000"]["group"] != "")
    check("WAL and thread-resolution files are flagged as bypass; the gated one is not",
          "bypass" in kinds("pearl_20261001_100000") and "bypass" in kinds("pearl_0001_20261006")
          and items["pearl_20261004_100000"]["path"] == "gated" and "bypass" not in kinds("pearl_20261004_100000"))
    check("a candidate that entered trial without his adoption is flagged as bypass; a proposal is not",
          "bypass" in kinds("cp-cccccc") and "bypass" not in kinds("cp-bbbbbb"))
    check("template residue / too short is malformed", "malformed" in kinds("pearl_20261003_100000")
          and any("template" in f["why"] for f in items["pearl_20261003_100000"]["flags"]))
    check("a well-formed first-person pearl is not malformed", "malformed" not in kinds("pearl_20261004_100000"))
    check("a third-person event record is flagged as no insight",
          any("event record" in f["why"] for f in items["pearl_20261001_100000"]["flags"]))
    check("a corrected fact is flagged as contradicting a known fact", "contradiction" in kinds("pearl_20261005_100000"))
    check("created dates parse from both file shapes",
          items["pearl_0001_20261006"]["created"] == "2026-10-06" and items["pearl_20261001_100000"]["created"] == "2026-10-01")

    # ---- the page
    out = pathlib.Path(tmp) / "private" / "page.html"
    R.generate(MEM, out)
    page = out.read_text()
    check("page is mode 600 in a 700 directory", stat.S_IMODE(out.stat().st_mode) == 0o600
          and stat.S_IMODE(out.parent.stat().st_mode) == 0o700)
    check("page carries every full text, escaped", "counted nine herons!" in page and "{placeholder}" in page
          and "I let the synthetic thread about the kettle go." in page)
    check("page cannot reach the network (CSP, no external URL, no fetch)",
          "connect-src 'none'" in page and "default-src 'none'" in page and not re.search(r"(src|href)=\"https?:", page)
          and "fetch(" not in page and "XMLHttpRequest" not in page)
    check("every item has keep / archive / edit", page.count('value="keep"') == page.count('value="archive"') == page.count('value="edit"') == 8)
    repo_out = ROOT / "pearl-review-test.html"
    try:
        R.generate(MEM, repo_out); refused = False
    except SystemExit:
        refused = True
    check("refuses to write his text inside the repository", refused and not repo_out.exists())
    ws_out = pathlib.Path(tmp) / ".vintos" / "workspace" / "memory" / "page.html"
    try:
        R.generate(MEM, ws_out); refused = False
    except SystemExit:
        refused = True
    check("refuses to write the page into his workspace", refused and not ws_out.exists())

    # ---- apply: plan only changes nothing
    fp = {i: items[i]["fp"] for i in items}
    dec = pathlib.Path(tmp) / "decisions.json"
    dec.write_text(json.dumps({"decisions": [
        {"key": "file:pearl_20261002_100000.md", "kind": "file", "fp": fp["pearl_20261002_100000"], "action": "archive"},
        {"key": "file:pearl_0001_20261006.md", "kind": "file", "fp": fp["pearl_0001_20261006"], "action": "archive"},
        {"key": "file:pearl_20261003_100000.md", "kind": "file", "fp": fp["pearl_20261003_100000"], "action": "edit",
         "text": "I learned the synthetic placeholder was never mine."},
        {"key": "file:pearl_20261004_100000.md", "kind": "file", "fp": fp["pearl_20261004_100000"], "action": "keep"},
        {"key": "cand:cp-cccccc", "kind": "candidate", "fp": fp["cp-cccccc"], "action": "archive"},
        {"key": "cand:cp-bbbbbb", "kind": "candidate", "fp": "stale", "action": "archive"},
    ]}))
    before = digest(MEM)
    store_before = json.loads((MEM / "candidate-pearls.json").read_text())
    R.apply(dec, MEM, yes=False, backup_root=pathlib.Path(tmp) / "bk")
    check("apply without --yes changes nothing", digest(MEM) == before)

    manifest = R.apply(dec, MEM, yes=True, backup_root=pathlib.Path(tmp) / "bk")
    arch = MEM / "pearls-archive"
    a1 = arch / "pearl_20261002_100000.md"
    check("archive moves the file out of pearls/ with provenance, never deletes it",
          not (MEM / "pearls" / "pearl_20261002_100000.md").exists() and a1.exists()
          and re.search(r"\*\*Superseded:\*\* archived by Gloria, \d{4}-\d{2}-\d{2} \(pearl review\)", a1.read_text())
          and "counted nine herons!" in a1.read_text())
    check("a read-only (0444) pearl archives too", (arch / "pearl_0001_20261006.md").exists())
    e = (MEM / "pearls" / "pearl_20261003_100000.md").read_text()
    origs = list(arch.glob("pearl_20261003_100000.orig-*.md"))
    check("edit replaces the text in place and keeps the original as superseded",
          "never mine" in e and "{placeholder}" not in e and "**Edited:** by Gloria" in e
          and origs and "{placeholder}" in origs[0].read_text() and "**Superseded:** edited by Gloria" in origs[0].read_text())
    cs = {c["id"]: c for c in json.loads((MEM / "candidate-pearls.json").read_text())["candidates"]}
    check("a candidate is archived as dissolved and superseded with provenance, kept in the store",
          cs["cp-cccccc"]["dissolved"] and cs["cp-cccccc"]["dissolution_reason"].startswith("archived by Gloria, ")
          and cs["cp-cccccc"]["superseded"]["by"] == "Gloria" and cs["cp-cccccc"]["stage"] == 1)
    check("a decision whose text changed since the page was made is skipped", not cs["cp-bbbbbb"]["dissolved"])
    check("keep changes nothing", (MEM / "pearls" / "pearl_20261004_100000.md").exists())
    ledger = [json.loads(l) for l in (MEM / "pearl-review-ledger.jsonl").read_text().splitlines()]
    check("every applied decision is in the ledger", {l["key"] for l in ledger} >= {"file:pearl_20261002_100000.md", "cand:cp-cccccc", "file:pearl_20261004_100000.md"})
    check("the manifest is private", stat.S_IMODE(pathlib.Path(manifest).stat().st_mode) == 0o600)
    check("no pearl file anywhere was deleted (all text still exists)",
          all(any(t in p.read_text() for p in MEM.rglob("*.md")) for t in ("counted nine herons.", "counted nine herons!", "{placeholder}", "kettle")))

    # ---- revert puts back exactly what was there
    R.revert(manifest, MEM, yes=True)
    skip = lambda k: k.startswith("pearls-archive/") or k in ("pearl-review-ledger.jsonl", "candidate-pearls.json")
    after = {k: v for k, v in digest(MEM).items() if not skip(k)}
    check("revert restores every pearl file byte for byte", after == {k: v for k, v in before.items() if not skip(k)})
    check("revert restores every candidate record exactly",
          json.loads((MEM / "candidate-pearls.json").read_text())["candidates"] == store_before["candidates"])

    check("no network was ever reached", socket.socket.connect is forbidden)

if FAILS:
    print("%d FAILED" % len(FAILS))
    sys.exit(1)
print("PASS pearl review: local page, flags, superseded archives with provenance, exact revert")
