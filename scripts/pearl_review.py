#!/usr/bin/env python3
"""pearl_review.py - Gloria's review of his pearls. LOCAL ONLY: his text never leaves this machine.

Gloria, 2026-11-14: "I still need a way to review them. They're his, yes, but he shouldn't be carrying
around 40 if they're duplicates, false, or poorly formed."

    generate [--memory DIR] [--out FILE]      write one self-contained HTML page (mode 600) listing every
                                              current pearl file and every live candidate in the gate,
                                              with automatic flags; she marks keep / archive / edit and
                                              saves a decisions file from the page
    apply DECISIONS.json [--memory DIR] [--by NAME] [--yes]
                                              without --yes: print the plan only. With --yes: archive
                                              as superseded with provenance ("archived by Gloria, date"),
                                              never delete; every change is backed up and a revert
                                              manifest is written
    revert MANIFEST.json [--memory DIR] [--yes]
                                              put back exactly what an apply changed

The page makes no network request (a Content-Security-Policy forbids it); the decisions file is saved by
the browser to her own Downloads. The only optional model call is --local-model URL on generate, which
asks a LOCAL model (her own machines) whether heuristic contradiction pairs really contradict; it is off
unless named.
"""
import argparse, difflib, hashlib, html, json, os, re, shutil, sys
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for _d in (HERE, os.path.expanduser("~/.vintos/workspace/scripts")):
    if _d not in sys.path:
        sys.path.append(_d)
from text_similarity import jaccard, overlap, content_words  # noqa: E402

DEFAULT_MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
DEFAULT_OUT_DIR = os.path.expanduser("~/pearl-review")
ARCHIVE_DIR_NAME = "pearls-archive"          # beside pearls/, so no pearls/ reader ever globs it
LEDGER_NAME = "pearl-review-ledger.jsonl"
ADOPTING = ("therapy", "mirror")
DUP_JACCARD, DUP_RATIO, DUP_OVERLAP = 0.5, 0.75, 0.7
CONTRA_TOPIC = 0.35
CAPS = (120, 200, 300, 400)                  # the truncation lengths the writers used
NEG = re.compile(r"\b(no longer|never|not|n't|stopped|without|cannot|can't|won't|refuse[sd]?|isn't|don't)\b", re.I)
TEMPLATE = re.compile(r"(\{[a-z_]+\}|\{\{|```|<\|[a-z_]+\|>|\bas an ai\b|respond (only )?with|\bjson\b|"
                      r"\[(adopt|decline):|^\s*(irritant|declaration|insight)\s*:|i no longer struggle to enact:|"
                      r"^#\s*pearl\b|\bTODO\b|\bN/A\b|^\s*none\s*$|lorem ipsum)", re.I | re.M)
FIRST_PERSON = re.compile(r"\b(i|i'm|i've|i'd|me|my|myself|we|our|us)\b", re.I)
LOGLINE = re.compile(r"^\s*(\[?\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}|(user|assistant|gloria|vintos|system)\s*:)", re.I)


def sha(text):
    return hashlib.sha256(str(text or "").encode()).hexdigest()[:16]


def _load_json(p, default):
    try:
        return json.load(open(p))
    except Exception:
        return default


# ------------------------------------------------------------------ collection
def parse_pearl_file(path):
    """Both shapes ever written: '# Pearl — date' + body + '---' footer (form_pearl and the old WAL
    writer), and '# Pearl #n' + _italic_ header + body (the old thread-resolution writer)."""
    raw = Path(path).read_text(errors="replace")
    meta, body = {}, raw
    for k, v in re.findall(r"^\*\*([A-Za-z ]+):\*\*\s*(.*)$", raw, re.M):
        meta.setdefault(k.strip().lower(), v.strip())
    for k, v in re.findall(r"^_([A-Za-z ]+):\s*(.*?)_\s*$", raw, re.M):
        meta.setdefault(k.strip().lower(), v.strip())
    if raw.startswith("# Pearl #"):
        lines = raw.splitlines()
        i = 1
        while i < len(lines) and (lines[i].startswith("_") or not lines[i].strip()):
            i += 1
        body = "\n".join(lines[i:]).strip()
    else:
        parts = raw.split("\n\n", 1)
        body = (parts[1] if len(parts) == 2 else "").split("\n---", 1)[0].strip()
    head = re.search(r"\d{4}-\d{2}-\d{2}", (raw.splitlines()[0] if raw else "") + " " + meta.get("created", ""))
    stem = re.search(r"(20\d{2})(\d{2})(\d{2})", Path(path).stem)
    created = head.group(0) if head else ("%s-%s-%s" % stem.groups() if stem else "")
    return {"body": body, "meta": meta, "created": created, "raw": raw}


def collect(memory):
    mem = Path(memory)
    cands = _load_json(mem / "candidate-pearls.json", {"candidates": []}).get("candidates", [])
    by_id = {c.get("id"): c for c in cands if isinstance(c, dict)}
    try:
        import pearl_engine as _pe
        gate_ok = _pe.gate_receipt_ok
    except Exception:
        gate_ok = lambda c: False  # noqa: E731
    items = []
    pdir = mem / "pearls"
    for f in sorted(pdir.glob("*.md")) if pdir.is_dir() else []:
        if f.is_symlink():
            continue
        p = parse_pearl_file(f)
        cid = p["meta"].get("candidate id", "")
        cand = by_id.get(cid)
        source = p["meta"].get("source", "") or "unknown"
        if cand and cand.get("stage") == 4 and (gate_ok(cand) or p["meta"].get("gate")):
            path_kind = "gated"
        elif cand and cand.get("stage") == 4:
            path_kind = "gated (formed before gate receipts)"
        else:
            path_kind = "bypass: " + source.split(":")[0]
        items.append({"key": "file:" + f.name, "kind": "file", "id": f.stem, "stage": "pearl (sealed file)",
                      "created": p["created"], "source": source, "path": path_kind,
                      "text": p["body"], "detail": {"file": "pearls/" + f.name,
                                                    **({"candidate": cid} if cid else {})},
                      "corrected": "**Corrected:**" in p["raw"], "fp": sha(p["body"])})
    idx = _load_json(pdir / "index.json", {})
    idx = idx.get("pearls", []) if isinstance(idx, dict) else (idx if isinstance(idx, list) else [])
    on_file = {" ".join(i["text"].split()) for i in items}
    for row in idx:
        if not isinstance(row, dict):
            continue
        text = str(row.get("content") or row.get("thread") or "").strip()
        if not text or " ".join(text.split()) in on_file:
            continue
        items.append({"key": "index:%s" % row.get("id"), "kind": "index", "id": "index-%s" % row.get("id"),
                      "stage": "pearl (index entry)", "created": str(row.get("created", ""))[:10],
                      "source": str(row.get("source", "")), "path": "bypass: " + str(row.get("source", "index")).split(":")[0],
                      "text": text, "detail": {"file": "pearls/index.json"}, "corrected": False, "fp": sha(text)})
    stage_name = {0: "proposed (stage 0)", 1: "under trial (stage 1)", 2: "verification (stage 2)",
                  3: "ready to seal (stage 3)", 4: "formed (stage 4)"}
    filed = {i["detail"].get("candidate") for i in items}
    for c in cands:
        if not isinstance(c, dict) or c.get("dissolved") or c.get("id") in filed:
            continue
        st = c.get("stage", 0)
        src = str(c.get("source", ""))
        if st >= 1 and src.split(":")[0] not in ADOPTING and not c.get("adopted_at"):
            path_kind = "bypass: entered trial without his adoption"
        elif st == 3 and not gate_ok(c):
            path_kind = "bypass: ready to seal without a gate receipt"
        else:
            path_kind = "gate (in progress)"
        v = c.get("verification") or {}
        text = str(c.get("declaration", ""))
        items.append({"key": "cand:" + str(c.get("id")), "kind": "candidate", "id": c.get("id"),
                      "stage": stage_name.get(st, "stage %s" % st), "created": str(c.get("created", ""))[:10],
                      "source": src, "path": path_kind, "text": text,
                      "detail": {"irritant": c.get("irritant", ""), "insight": c.get("insight", ""),
                                 "verification": "%d passes, %d failures, pressure %s" % (
                                     len(v.get("passes", [])), int(v.get("failures", 0) or 0),
                                     "met" if v.get("pressure_state_hit") else "not yet"),
                                 **({"concern": c["concern"]} if c.get("concern") else {})},
                      "corrected": False, "fp": sha("%s|stage %s" % (text, st))})
    return items


# ------------------------------------------------------------------ flags
def _norm(t):
    return " ".join(re.sub(r"[^a-z0-9' ]", " ", str(t or "").lower()).split())


def near_duplicate_groups(items):
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    norms = [_norm(i["text"]) for i in items]
    for a in range(n):
        for b in range(a + 1, n):
            if not norms[a] or not norms[b]:
                continue
            ov = min(overlap(items[a]["text"], items[b]["text"]), overlap(items[b]["text"], items[a]["text"]))
            if (jaccard(items[a]["text"], items[b]["text"]) >= DUP_JACCARD or ov >= DUP_OVERLAP
                    or difflib.SequenceMatcher(None, norms[a], norms[b]).ratio() >= DUP_RATIO):
                parent[find(a)] = find(b)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]


def malformed_reasons(text):
    t = str(text or "").strip()
    out = []
    if not t:
        return ["empty"]
    words = t.split()
    if len(words) < 6:
        out.append("too short to carry an insight (%d words)" % len(words))
    if len(t) in CAPS or re.search(r"(\.\.\.|…)$", t):
        out.append("truncated (cut at a writer's length cap)")
    elif not re.search(r"[.!?\"'”’)\]*_]$", t):
        out.append("possibly truncated (no ending punctuation)")
    m = TEMPLATE.search(t)
    if m:
        out.append("template residue (%s)" % m.group(0).strip()[:30])
    if LOGLINE.search(t):
        out.append("reads as a log line, not an insight")
    elif not FIRST_PERSON.search(t):
        out.append("no first-person reflection: a third-person event record, not an insight")
    return out


def known_fact_conflicts(item, memory):
    """Existing checks only: a correction footer correction_propagate already wrote, a correction whose
    original claim this pearl restates (correction_propagate's own overlap rule), a reviewer hold."""
    out = []
    if item.get("corrected"):
        out.append("carries a correction footer: a fact in it was corrected")
    try:
        from correction_propagate import _overlap, FLOOR
    except Exception:
        _overlap, FLOOR = (lambda a, b: overlap(a, b)), 0.5
    mem = Path(memory)
    try:
        for line in (mem / "correction-propagation.jsonl").read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("original") and _overlap(rec["original"], item["text"]) >= FLOOR:
                out.append("restates a corrected claim (%s)" % rec.get("correction_id", "?"))
    except OSError:
        pass
    for f in _load_json(mem / "hallucination-flags.json", []):
        if isinstance(f, dict) and f.get("type") == "pearl_held" and f.get("candidate_id") == item.get("id"):
            out.append("held by the pearl reviewer: %s" % str(f.get("concern") or f.get("held_reason") or "")[:80])
    return out


def contradiction_pairs(items, dup_groups):
    """Heuristic: two pearls on the same topic (content-word overlap) with opposite polarity."""
    same_group = {}
    for gi, g in enumerate(dup_groups):
        for i in g:
            same_group[i] = gi
    pairs = []
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            if a in same_group and same_group.get(a) == same_group.get(b):
                continue
            ta, tb = items[a]["text"], items[b]["text"]
            if len(content_words(ta)) < 4 or len(content_words(tb)) < 4:
                continue
            if jaccard(ta, tb) >= CONTRA_TOPIC and bool(NEG.search(ta)) != bool(NEG.search(tb)):
                pairs.append((a, b))
    return pairs


def local_model_confirms(a, b, url, model):
    """Ask a LOCAL model (her own machine) whether two statements contradict. None when unreachable."""
    if not is_local_url(url):
        raise SystemExit("--local-model must be loopback or her tailnet (100.64.0.0/10): " + str(url))
    try:
        import requests
        r = requests.post(url, json={"model": model, "temperature": 0, "max_tokens": 4, "messages": [
            {"role": "system", "content": "Answer with exactly one word: YES or NO."},
            {"role": "user", "content": "Do these two statements contradict each other?\nA: %s\nB: %s" % (a[:600], b[:600])}]},
            timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip().upper().startswith("YES")
    except Exception:
        return None


def is_local_url(url):
    import ipaddress
    from urllib.parse import urlparse
    host = urlparse(str(url or "")).hostname or ""
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip in ipaddress.ip_network("100.64.0.0/10")


def flag_items(items, memory, local_model=None, model="aeon-gemma-4-12b"):
    for it in items:
        it["flags"] = []
        it["group"] = ""
    groups = near_duplicate_groups(items)
    for gi, g in enumerate(groups, 1):
        for i in g:
            others = [items[j]["id"] for j in g if j != i]
            items[i]["group"] = "D%d" % gi
            items[i]["flags"].append({"kind": "duplicate", "why": "near-duplicate group D%d (with %s)" % (gi, ", ".join(map(str, others)))})
    for it in items:
        if it["path"].startswith("bypass"):
            it["flags"].append({"kind": "bypass", "why": "came in through a bypass: " + it["path"][len("bypass: "):]})
        for r in malformed_reasons(it["text"]):
            it["flags"].append({"kind": "malformed", "why": r})
        for r in known_fact_conflicts(it, memory):
            it["flags"].append({"kind": "contradiction", "why": r})
    for a, b in contradiction_pairs(items, groups):
        verdict = local_model_confirms(items[a]["text"], items[b]["text"], local_model, model) if local_model else None
        if verdict is False:
            continue
        how = "confirmed by local model" if verdict else "heuristic: same topic, opposite polarity - check"
        items[a]["flags"].append({"kind": "contradiction", "why": "may contradict %s (%s)" % (items[b]["id"], how)})
        items[b]["flags"].append({"kind": "contradiction", "why": "may contradict %s (%s)" % (items[a]["id"], how)})
    return items


def flag_counts(items):
    out = {"items": len(items), "flagged": sum(1 for i in items if i["flags"])}
    for k in ("duplicate", "bypass", "malformed", "contradiction"):
        out[k] = sum(1 for i in items if any(f["kind"] == k for f in i["flags"]))
    out["duplicate_groups"] = len({i["group"] for i in items if i["group"]})
    return out


# ------------------------------------------------------------------ page
def render(items, generated, memory):
    e = lambda s: html.escape(str(s if s is not None else ""))  # noqa: E731
    order = sorted(range(len(items)), key=lambda i: (items[i]["kind"] == "candidate", items[i]["group"] or "~",
                                                     items[i]["created"], str(items[i]["id"])))
    counts = flag_counts(items)
    rows = []
    for i in order:
        it = items[i]
        chips = "".join('<span class="chip %s" title="%s">%s</span>' % (e(f["kind"]), e(f["why"]), e(f["kind"]))
                        for f in it["flags"])
        why = "".join("<li>%s</li>" % e(f["why"]) for f in it["flags"])
        detail = "".join("<div><b>%s:</b> %s</div>" % (e(k), e(v)) for k, v in it["detail"].items())
        rows.append(f'''
<article class="item" data-key="{e(it["key"])}" data-fp="{e(it["fp"])}" data-kind="{e(it["kind"])}"
  data-flags="{e(" ".join(sorted({f["kind"] for f in it["flags"]})) or "none")}" data-group="{e(it["group"])}">
  <header><span class="id">{e(it["id"])}</span>{(' <span class="group">' + e(it["group"]) + '</span>') if it["group"] else ''}
    <span class="meta">{e(it["stage"])} &middot; created {e(it["created"] or "?")} &middot; source {e(it["source"] or "?")}</span>
    <span class="path {"bp" if it["path"].startswith("bypass") else "ok"}">{e(it["path"])}</span> {chips}</header>
  <div class="text">{e(it["text"]) or "<i>(empty)</i>"}</div>
  {('<ul class="why">' + why + '</ul>') if why else ''}
  <details><summary>details</summary>{detail}</details>
  <div class="choice">
    <label><input type="radio" name="c-{e(it["key"])}" value="keep"> keep</label>
    <label><input type="radio" name="c-{e(it["key"])}" value="archive"> archive</label>
    <label><input type="radio" name="c-{e(it["key"])}" value="edit"> edit</label>
    <textarea class="edit" placeholder="the corrected text" hidden></textarea>
  </div>
</article>''')
    data_meta = json.dumps({"generated": generated, "memory": str(memory), "count": len(items)})
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; form-action 'none'">
<title>Pearl review</title>
<style>
:root{{--bg:#faf8f5;--fg:#222;--muted:#666;--card:#fff;--line:#ddd;--bad:#b3261e;--ok:#2e7d32;--chip:#eee}}
@media (prefers-color-scheme: dark){{:root{{--bg:#16161a;--fg:#e6e6e6;--muted:#9a9a9a;--card:#202026;--line:#333;--bad:#ff8a80;--ok:#81c784;--chip:#2c2c33}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:900px;padding:16px}}
h1{{font-size:20px;margin:0 0 4px}} .sub{{color:var(--muted);margin:0 0 12px}}
.bar{{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px;align-items:center;z-index:2}}
.item{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin:12px 0}}
.item header{{display:flex;flex-wrap:wrap;gap:6px;align-items:baseline}} .id{{font-weight:600;font-family:monospace}}
.meta{{color:var(--muted);font-size:13px}} .path{{font-size:12px;padding:1px 6px;border-radius:4px;border:1px solid}}
.path.bp{{color:var(--bad)}} .path.ok{{color:var(--ok)}} .group{{font-weight:700;color:var(--bad)}}
.chip{{font-size:12px;background:var(--chip);border-radius:10px;padding:1px 8px}}
.text{{white-space:pre-wrap;margin:8px 0;overflow-wrap:anywhere}} .why{{color:var(--muted);font-size:13px;margin:4px 0}}
details{{font-size:13px;color:var(--muted);overflow-wrap:anywhere}} .choice{{display:flex;flex-wrap:wrap;gap:12px;margin-top:8px}}
textarea.edit{{width:100%;min-height:70px;box-sizing:border-box;font:inherit}}
button,select{{font:inherit;padding:4px 10px}}
</style></head><body>
<h1>Pearl review</h1>
<p class="sub">Generated {e(generated)} from {e(memory)}. {counts["items"]} items, {counts["flagged"]} flagged:
{counts["duplicate"]} near-duplicates in {counts["duplicate_groups"]} groups, {counts["bypass"]} through a bypass,
{counts["malformed"]} malformed, {counts["contradiction"]} possible contradictions. Nothing on this page is sent anywhere.</p>
<div class="bar">
  <select id="filter"><option value="">show all</option><option value="duplicate">near-duplicates</option>
  <option value="bypass">bypass</option><option value="malformed">malformed</option>
  <option value="contradiction">contradiction</option><option value="none">unflagged</option></select>
  <span id="tally"></span>
  <button id="save">Save decisions file</button>
</div>
{"".join(rows)}
<script>
const META = {data_meta};
const KEY = "pearl-review:" + META.generated;
let saved = {{}}; try {{ saved = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{}}
const items = [...document.querySelectorAll(".item")];
function sync() {{
  const out = {{}};
  for (const it of items) {{
    const r = it.querySelector("input:checked"); const ta = it.querySelector("textarea");
    ta.hidden = !(r && r.value === "edit");
    if (r) out[it.dataset.key] = {{action: r.value, text: r.value === "edit" ? ta.value : undefined}};
  }}
  try {{ localStorage.setItem(KEY, JSON.stringify(out)); }} catch (e) {{}}
  const n = Object.keys(out).length;
  document.getElementById("tally").textContent = n + " of " + items.length + " decided";
  return out;
}}
for (const it of items) {{
  const s = saved[it.dataset.key];
  if (s) {{ const r = it.querySelector('input[value="' + s.action + '"]'); if (r) r.checked = true;
           if (s.text) it.querySelector("textarea").value = s.text; }}
  it.addEventListener("input", sync); it.addEventListener("change", sync);
}}
document.getElementById("filter").addEventListener("change", ev => {{
  const v = ev.target.value;
  for (const it of items) it.style.display = (!v || it.dataset.flags.split(" ").includes(v)) ? "" : "none";
}});
document.getElementById("save").addEventListener("click", () => {{
  const d = sync(); const decisions = [];
  for (const it of items) {{
    const x = d[it.dataset.key]; if (!x) continue;
    if (x.action === "edit" && !(x.text || "").trim()) {{ alert("An edit has no text: " + it.dataset.key); return; }}
    decisions.push({{key: it.dataset.key, kind: it.dataset.kind, fp: it.dataset.fp, action: x.action, text: x.text}});
  }}
  const blob = new Blob([JSON.stringify({{generated: META.generated, memory: META.memory, decisions}}, null, 1)], {{type: "application/json"}});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = "pearl-decisions-" + META.generated.slice(0, 10) + ".json"; a.click();
}});
sync();
</script></body></html>'''


def write_private(path, text):
    path = Path(path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True)
        os.chmod(path.parent, 0o700)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(path, 0o600)
    return path


def generate(memory, out, local_model=None, model="aeon-gemma-4-12b"):
    # Never inside a repository (the repo is public), the tree this script came from, or his workspace
    # (where his own organs would read it).
    real_out = os.path.realpath(out)
    fenced = [os.path.dirname(os.path.realpath(HERE)), os.path.realpath(os.path.expanduser("~/.vintos"))]
    for f in fenced:
        if real_out.startswith(f.rstrip("/") + "/"):
            raise SystemExit("refusing to write his text inside " + f)
    d = os.path.dirname(real_out)
    while d and d != "/":
        if os.path.exists(os.path.join(d, ".git")):
            raise SystemExit("refusing to write his text inside a repository: " + d)
        d = os.path.dirname(d)
    items = flag_items(collect(memory), memory, local_model, model)
    generated = datetime.now().isoformat(timespec="seconds")
    write_private(out, render(items, generated, memory))
    return items


# ------------------------------------------------------------------ apply / revert
def _current_items(memory):
    return {i["key"]: i for i in collect(memory)}


def _cand(pe, cid):
    return next((c for c in pe.load_candidates().get("candidates", []) if c.get("id") == cid), None)


def _engine(memory):
    """pearl_engine, pointed at THIS memory's candidate store (its writes go through its own lock)."""
    import pearl_engine as pe
    pe.CANDIDATES_FILE = os.path.join(str(memory), "candidate-pearls.json")
    return pe


def _footer(path, line):
    os.chmod(path, 0o644)
    with open(path, "a") as fh:
        fh.write(line + "\n")


def apply(decisions_path, memory, by="Gloria", yes=False, backup_root=DEFAULT_OUT_DIR):
    pe = _engine(memory)
    dec = json.load(open(decisions_path))
    mem = Path(memory)
    today = datetime.now().strftime("%Y-%m-%d")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    current = _current_items(memory)
    plan, skipped = [], []
    for d in dec.get("decisions", []):
        it = current.get(d.get("key"))
        if d.get("action") not in ("keep", "archive", "edit"):
            skipped.append((d.get("key"), "unknown action")); continue
        if not it:
            skipped.append((d.get("key"), "no longer current")); continue
        if it["fp"] != d.get("fp"):
            skipped.append((d.get("key"), "changed since the page was generated")); continue
        if d["action"] == "edit" and not str(d.get("text") or "").strip():
            skipped.append((d.get("key"), "edit without text")); continue
        if d["action"] == "edit" and it["kind"] == "file" and not it["text"].strip():
            skipped.append((d.get("key"), "empty pearl: archive it instead of editing")); continue
        plan.append((d, it))
    for d, it in plan:
        print("%-8s %s" % (d["action"], it["id"]))
    for k, why in skipped:
        print("SKIP     %s: %s" % (k, why))
    if not yes:
        print("(plan only; add --yes to apply)")
        return None
    bdir = Path(backup_root) / ("applied-" + stamp)
    bdir.mkdir(parents=True, exist_ok=True)
    os.chmod(bdir, 0o700)
    if (mem / "candidate-pearls.json").exists():
        shutil.copy2(mem / "candidate-pearls.json", bdir / "candidate-pearls.json")
    adir = mem / ARCHIVE_DIR_NAME
    adir.mkdir(exist_ok=True)
    ops = []
    who = "%s, %s" % (by, today)
    for d, it in plan:
        act = d["action"]
        if it["kind"] == "file" and act != "keep":
            src = mem / it["detail"]["file"]
            backup = bdir / ("file-" + src.name)
            shutil.copy2(src, backup)
            if act == "archive":
                dst = adir / src.name
                if dst.exists():
                    dst = adir / ("%s.%s.md" % (src.stem, stamp))
                shutil.move(str(src), str(dst))
                _footer(dst, "**Superseded:** archived by %s (pearl review)" % who)
                ops.append({"op": "archive_file", "from": str(src), "to": str(dst), "backup": str(backup)})
            else:
                orig = adir / ("%s.orig-%s.md" % (src.stem, stamp))
                shutil.copy2(src, orig)
                _footer(orig, "**Superseded:** edited by %s; the current version is pearls/%s" % (who, src.name))
                raw = src.read_text()
                new_raw = raw.replace(it["text"], str(d["text"]).strip(), 1)
                os.chmod(src, 0o644)
                src.write_text(new_raw)
                _footer(src, "**Edited:** by %s (pearl review); the original is %s/%s" % (who, ARCHIVE_DIR_NAME, orig.name))
                ops.append({"op": "edit_file", "path": str(src), "orig": str(orig), "backup": str(backup)})
            cid = it["detail"].get("candidate")
            if cid:     # the sealed candidate follows its file, or its declaration stays in his live context
                before = pe.curate_candidate(cid, act, by=by, text=d.get("text"))
                if before is not None:
                    ops.append({"op": "candidate", "id": cid, "previous": before, "after": _cand(pe, cid)})
        elif it["kind"] == "candidate" and act != "keep":
            before = pe.curate_candidate(it["id"], act, by=by, text=d.get("text"))
            if before is not None:
                ops.append({"op": "candidate", "id": it["id"], "previous": before, "after": _cand(pe, it["id"])})
        elif it["kind"] == "index" and act != "keep":
            skipped.append((it["key"], "index entries are archived by hand (none exist today)"))
            continue
        with open(mem / LEDGER_NAME, "a") as fh:
            fh.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "by": by, "key": it["key"],
                                 "action": act, "fp": it["fp"], "backup": str(bdir)}) + "\n")
    manifest = {"applied_at": stamp, "by": by, "memory": str(mem), "decisions": str(decisions_path), "ops": ops}
    write_private(bdir / "manifest.json", json.dumps(manifest, indent=1))
    print("applied %d change(s); revert with: python3 %s revert %s --yes" % (len(ops), os.path.abspath(__file__), bdir / "manifest.json"))
    return bdir / "manifest.json"


def revert(manifest_path, memory, yes=False):
    pe = _engine(memory)
    m = json.load(open(manifest_path))
    for op in reversed(m.get("ops", [])):
        print("revert %s %s" % (op["op"], op.get("id") or op.get("from") or op.get("path")))
        if not yes:
            continue
        if op["op"] == "archive_file":
            shutil.copy2(op["backup"], op["from"])
            dst = Path(op["to"])
            if dst.exists():
                dst.rename(dst.with_name(dst.name + ".reverted"))     # kept, never deleted
        elif op["op"] == "edit_file":
            shutil.copy2(op["backup"], op["path"])
        elif op["op"] == "candidate":
            if "after" in op and _cand(pe, op["id"]) != op["after"]:
                print("  SKIP %s: changed since the apply (left as it is now)" % op["id"])
                continue
            pe.curate_candidate(op["id"], "restore", previous=op["previous"])
    if yes:
        with open(Path(memory) / LEDGER_NAME, "a") as fh:
            fh.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "reverted": str(manifest_path)}) + "\n")
    else:
        print("(plan only; add --yes to revert)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--memory", default=DEFAULT_MEMORY)
    g.add_argument("--out", default=os.path.join(DEFAULT_OUT_DIR, "pearl-review-%s.html" % datetime.now().strftime("%Y-%m-%d")))
    g.add_argument("--local-model", default=None, help="a LOCAL chat-completions URL to confirm contradiction pairs")
    g.add_argument("--model", default="aeon-gemma-4-12b")
    a = sub.add_parser("apply")
    a.add_argument("decisions"); a.add_argument("--memory", default=DEFAULT_MEMORY)
    a.add_argument("--by", default="Gloria"); a.add_argument("--yes", action="store_true")
    r = sub.add_parser("revert")
    r.add_argument("manifest"); r.add_argument("--memory", default=DEFAULT_MEMORY); r.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "generate":
        items = generate(args.memory, args.out, args.local_model, args.model)
        print(json.dumps(flag_counts(items)))
        print("page: " + os.path.abspath(args.out))
    elif args.cmd == "apply":
        apply(args.decisions, args.memory, args.by, args.yes)
    else:
        revert(args.manifest, args.memory, args.yes)


if __name__ == "__main__":
    main()
