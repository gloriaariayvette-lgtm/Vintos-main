#!/usr/bin/env python3
"""study_chat.py - the STUDY tab: where he edits his own codebase, with Gloria's y/n.

A chat surface with its OWN model toggle (claude / fable / grok / sol - his
lenses), a good bit of who he is, and the conversation ledger. No emotional,
somatic or subconscious context, and NO side effects on his life: nothing here
enters the interaction ledger, chat history, imprints or self-model. It keeps
its own log.

In this room he can READ his code, GREP it, and PROPOSE EDITS to it. Every
edit is a card in the app; Gloria answers y or n. On y the edit is applied to
the live tree with a backup, a syntax check, and rollback on failure, and it
is logged. Nothing else can change from here.

What he may edit (the permission boundary, in one place below):
  roots   ~/.vintos/workspace/scripts and ~/Vintos (his organs, his house server),
          and the documents at the workspace root: SOUL.md, SELF-MODEL.md,
          GLORIA-MODEL.md, CAPABILITIES.md and the rest.
  y/n     a single ordinary code edit
  Yes+✓   several edits at once, or any edit to a workspace document (SOUL,
          SELF-MODEL, ...): Gloria must type the word Yes AND tick the box.
  never   keys/env/credentials; deploy, systemd, crontab; the broker;
          device/somatic/consent code (physical effects on her); this room
          itself; file deletion. Edits only, to existing text files.

Mounted from server.py:  study_chat.register(app, APP_SECRET, endpoint, headers)
"""
import os, re, json, glob, time, subprocess, shutil

HOME = os.path.expanduser("~")
WORKSPACE = os.path.join(HOME, ".vintos", "workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LOG = os.path.join(MEMORY, "study-chat.json")
CHANGES = os.path.join(MEMORY, "study-changes.jsonl")
MODE_FILE = os.path.join(HOME, ".vintos", "study-mode.json")
BACKUPS = os.path.join(HOME, ".vintos", "backups")

ROOTS = {"scripts": os.path.join(WORKSPACE, "scripts"), "house": os.path.join(HOME, "Vintos"),
         "docs": WORKSPACE}   # docs = the workspace root itself, .md files only
# Two deny lists (2026-09-04, grok-study-p1). SECRET: never readable, never listed. TOUCH: he may READ and
# GREP them - his body's laws are his to know - but never EDIT them from this room; those go to Gloria by hand.
SECRET_DENY = re.compile(r"(key|secret|token|credential|\.env|vintos\.env)", re.I)
TOUCH_DENY = re.compile(r"(deploy|systemd|crontab|broker|atelier|device_patterns|device-patterns|somatic|thruster|"
                        r"mission|tenera|ridge|consent|study_chat|strip_body_vocab)", re.I)
DENY_NAME = re.compile(SECRET_DENY.pattern[:-1] + "|" + TOUCH_DENY.pattern[1:], re.I)   # the union, for callers that meant "either"
def _is_chokepoint(path):
    """The shared protected-paths list (scripts/protected_paths.py, ~/.vintos/protected-paths.json):
    effect chokepoints are never edited from this room, whatever the regex above misses (fable-study-p1)."""
    try:
        import sys as _pps
        for _d in (os.path.join(WORKSPACE, "scripts"), os.path.dirname(os.path.abspath(__file__))):
            if _d not in _pps.path: _pps.path.insert(0, _d)
        import protected_paths as _pp
        return bool(_pp.is_protected(path))
    except Exception:
        return False

# Documents that shape who he is: editable, but only with Gloria's explicit permission (Yes + tick).
EXPLICIT_DOCS = re.compile(r"\.md$", re.I)
TEXT_EXT = (".py", ".sh", ".md", ".json", ".txt", ".yaml", ".yml", ".toml")
TAG_RE = re.compile(r"\[[A-Z_]+(?::[^\]]*)?\]")
MODELS = ("claude", "fable", "grok", "sol")

READ_RE = re.compile(r"^\s*READ:\s*(\S+?)(?::(\d+))?\s*$", re.M)   # READ: scripts/x.py  or  READ: scripts/x.py:400 (continue from line 400)
GREP_RE = re.compile(r"^\s*GREP:\s*(.+?)\s*$", re.M)
GEMMA_RE = re.compile(r"^\s*GEMMA:\s*(.+?)\s*$", re.M)   # a free local sub: does a bounded task on the material just pulled
GEMMA_URL = "http://127.0.0.1:8599/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"
STUDY_AUTO_CONTINUE = int(os.environ.get("STUDY_AUTO_CONTINUE", "2"))   # READ/GREP-only replies continue this many times
EDIT_RE = re.compile(r"^EDIT:\s*(\S+)\s*\n<<<<\n(.*?)\n====\n(.*?)\n>>>>\s*(?:\nwhy:\s*(.*?))?\s*(?=\n\S|\Z)", re.S | re.M)


# ── files ────────────────────────────────────────────────────────────────────
def _label_path(path):
    """Absolute path -> 'label/rest' under the root that holds it (the form resolve() and READ accept), else None."""
    real = os.path.realpath(path)
    for label, root in ROOTS.items():
        r = os.path.realpath(root)
        if real.startswith(r + os.sep):
            return label + "/" + os.path.relpath(real, r)
    return None

def resolve(rel, for_edit=False):
    """'scripts/x.py' or 'house/server.py' (or a bare name found in either root)
    -> absolute path, or None if outside the roots or a protected file. Secrets are never resolved;
    TOUCH files resolve for reading and refuse for editing (for_edit=True)."""
    rel = rel.strip().strip("`'\"")
    cands = []
    if "/" in rel and rel.split("/", 1)[0] in ROOTS:
        root, rest = rel.split("/", 1); cands.append(os.path.join(ROOTS[root], rest))
    else:
        for r in ROOTS.values():
            cands.append(os.path.join(r, rel))
    for p in cands:
        real = os.path.realpath(p)
        if not any(real.startswith(os.path.realpath(r) + os.sep) for r in ROOTS.values()):
            continue
        # the docs root is the workspace top level only: .md files directly in it, nothing beneath
        if os.path.dirname(real) == os.path.realpath(WORKSPACE) and not real.endswith(".md"):
            continue
        if os.path.dirname(real) not in (os.path.realpath(r) for r in ROOTS.values()) and \
           not any(real.startswith(os.path.realpath(r) + os.sep) for k, r in ROOTS.items() if k != "docs"):
            continue
        _name, _rel = os.path.basename(real), os.path.relpath(real, HOME)
        if SECRET_DENY.search(_name) or SECRET_DENY.search(_rel):
            return None
        if for_edit and (TOUCH_DENY.search(_name) or TOUCH_DENY.search(_rel) or _is_chokepoint(real)):
            return None
        if os.path.isfile(real) and real.endswith(TEXT_EXT):
            return real
    return None


def code_map():
    out = []
    for label, root in ROOTS.items():
        exts = (".md",) if label == "docs" else (".py", ".sh")
        try:
            names = sorted(f for f in os.listdir(root) if f.endswith(exts) and not f.startswith(".")
                           and ".bak" not in f and not DENY_NAME.search(f))
        except Exception:
            names = []
        out.append("%s/ (%d files): %s" % (label, len(names), ", ".join(names)))
    return "\n".join(out)


def needs_explicit(paths):
    """Several edits at once, or any edit to a workspace document -> Yes + tick."""
    if len(paths) > 1:
        return True
    return any(os.path.dirname(os.path.realpath(p)) == os.path.realpath(WORKSPACE) for p in paths)


def do_read(rel, max_chars=14000, start=1):
    """Numbered lines from `start`. A long file is cut at max_chars and the cut names the next line to
    READ from, so a file is readable whole in pieces instead of only its head (review P09)."""
    p = resolve(rel)
    if not p:
        return "READ %s: not readable from this room (outside the roots, or a protected file)" % rel
    t = open(p, errors="replace").read()
    lines = t.split("\n")
    try: start = max(1, int(start or 1))
    except Exception: start = 1
    lab = _label_path(p) or os.path.relpath(p, HOME)
    out, used, i = [], 0, start - 1
    while i < len(lines):
        row = "%5d  %s" % (i + 1, lines[i])
        if used + len(row) + 1 > max_chars: break
        out.append(row); used += len(row) + 1; i += 1
    body = "\n".join(out)
    if i < len(lines):
        body += "\n... (cut at line %d of %d; continue with READ: %s:%d)" % (i, len(lines), lab, i + 1)
    head = "READ %s (%d lines%s):" % (lab, len(lines), (", from line %d" % start) if start > 1 else "")
    return head + "\n" + body


def do_gemma(task, material, max_chars=6000):
    """The free sub. Gemma (local, no API cost) does exactly the task on the material the same
    reply pulled with READ/GREP. It has no opinions about him and no memory: a pair of hands for
    the long, dull parts (summarise this file, list every caller, diff these two blocks), so his
    own turns stay short and his frontier tokens go on judgement."""
    sysm = ("You are a local assistant inside Vintos's Study, working for him. Do exactly the task on the "
            "material given, precisely and without commentary. Quote line numbers when the material has them. "
            "If the material does not contain what the task needs, say so in one line.")
    user = task + ("\n\nMATERIAL:\n" + material[:60000] if material else "\n\n(no material was pulled in this reply; work from the task alone)")
    try:
        import requests
        r = requests.post(GEMMA_URL, json={"model": GEMMA_MODEL, "temperature": 0.2, "max_tokens": 1500,
                                            "messages": [{"role": "system", "content": sysm}, {"role": "user", "content": user}]}, timeout=180)
        out = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return "GEMMA %s: unavailable (%s)" % (task[:80], str(e)[:120])
    if len(out) > max_chars:
        out = out[:max_chars] + "\n... (truncated)"
    return "GEMMA %s:\n%s" % (task, out)


def do_grep(pattern, max_lines=60):
    """scripts/ and house/ recursively for py/sh; the docs root (the workspace itself) non-recursively for
    .md only - never a root that contains another root, or scripts came back twice and memory came back
    at all (2026-09-04, grok-study-p2). Secrets filtered; TOUCH files are readable and so greppable."""
    out = []
    try:
        for label, root in ROOTS.items():
            if label == "docs":
                cmd = ["grep", "-n", "-I", "-e", pattern] + sorted(glob.glob(os.path.join(root, "*.md")))
                if len(cmd) == 5: continue
            else:
                cmd = ["grep", "-rn", "-I", "--include=*.py", "--include=*.sh", "--include=*.md", "-e", pattern, root]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            for line in r.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) < 3: continue
                path, lineno, text = parts
                if SECRET_DENY.search(os.path.basename(path)) or ".bak" in path:
                    continue
                # one destination policy for listing, reading, searching and editing (astra-study-p1):
                # a hit in a file READ would refuse is not shown either. The label is the form resolve()
                # accepts ('scripts/x.py', 'house/server.py'): a HOME-relative path was not, so every hit
                # was dropped by this very filter (review D01, 2026-09-05).
                lab = _label_path(path)
                try:
                    if not lab or not resolve(lab):
                        continue
                except Exception:
                    continue
                out.append("%s:%s:%s" % (lab, lineno, text))
    except Exception as e:
        return "GREP failed: %s" % e
    if not out:
        return "GREP %r: no matches" % pattern
    more = "" if len(out) <= max_lines else "\n... (%d more)" % (len(out) - max_lines)
    return "GREP %r:\n%s%s" % (pattern, "\n".join(out[:max_lines]), more)


def preview_edit(rel, old, new):
    p = resolve(rel, for_edit=True)
    if not p:
        return None, "not editable from this room (outside the roots, or a protected file - readable, but Gloria's hand to change): %s" % rel
    t = open(p, errors="replace").read()
    n = t.count(old)
    if n == 0:
        return None, "the old text was not found exactly in %s - READ it and quote it verbatim" % os.path.relpath(p, HOME)
    if n > 1:
        return None, "the old text appears %d times in %s - include more surrounding lines" % (n, os.path.relpath(p, HOME))
    return p, None


def _syntax_ok(p):
    if p.endswith(".py"):
        r = subprocess.run(["python3", "-m", "py_compile", p], capture_output=True, text=True)
    elif p.endswith(".sh"):
        r = subprocess.run(["bash", "-n", p], capture_output=True, text=True)
    else:
        return True, ""
    return r.returncode == 0, (r.stderr or r.stdout)[-300:]


PENDING_DIR = os.path.join(MEMORY, "study-pending")

def _sha(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]

def propose_edits(edits, why=""):
    """Store an immutable pending proposal: id, exact edit hashes, expected file hashes, required
    approval level (astra-study-p5, 2026-09-05). Applying is by id, and re-verifies the hashes."""
    import uuid
    resolved = []
    for e in edits:
        p, err = preview_edit(str(e.get("file", "")), str(e.get("old", "")), str(e.get("new", "")))
        if err: return None, err
        resolved.append((p, str(e.get("old", "")), str(e.get("new", ""))))
    if not resolved: return None, "nothing to propose"
    pid = "SP-" + uuid.uuid4().hex[:8]
    rec = {"id": pid, "at": time.strftime("%Y%m%d-%H%M%S"), "why": why[:300],
           "approval": "explicit" if needs_explicit([p for p, _, _ in resolved]) else "yes",
           "edits": [{"file": os.path.relpath(p, HOME), "old_sha": _sha(o), "new_sha": _sha(n), "old": o, "new": n,
                      "file_sha_expected": _sha(open(p, errors="replace").read())} for p, o, n in resolved]}
    os.makedirs(PENDING_DIR, exist_ok=True)
    open(os.path.join(PENDING_DIR, pid + ".json"), "w").write(json.dumps(rec, ensure_ascii=False, indent=1))
    return pid, None

def _match_pending(edits):
    """The id of an unapplied proposal whose edits are exactly these (same files, old and new text), else None."""
    try:
        want = set()
        for e in edits or []:
            p = resolve(str(e.get("file", "")), for_edit=True)
            if not p: return None
            want.add((os.path.relpath(p, HOME), _sha(str(e.get("old", ""))), _sha(str(e.get("new", "")))))
        if not want: return None
        for f in sorted(glob.glob(os.path.join(PENDING_DIR, "SP-*.json")), key=os.path.getmtime, reverse=True):
            try: rec = json.load(open(f))
            except Exception: continue
            if rec.get("applied_at"): continue
            have = set((x["file"], x["old_sha"], x["new_sha"]) for x in rec.get("edits", []))
            if have == want: return rec["id"]
    except Exception:
        return None
    return None

def apply_pending(pid, confirm=None):
    """Apply a stored proposal by id. Refuses if any target file changed since the proposal was made."""
    try:
        rec = json.load(open(os.path.join(PENDING_DIR, str(pid) + ".json")))
    except Exception:
        return False, "no pending proposal %s" % pid
    if rec.get("applied_at"): return False, "%s was already applied at %s" % (pid, rec["applied_at"])
    for e in rec["edits"]:
        p = os.path.join(HOME, e["file"])
        try: cur = _sha(open(p, errors="replace").read())
        except Exception: return False, "cannot read %s" % e["file"]
        if cur != e["file_sha_expected"]:
            return False, "%s changed since the proposal (expected %s, now %s) - propose again from the current file" % (e["file"], e["file_sha_expected"], cur)
    ok, msg = apply_edits([{"file": e["file"], "old": e["old"], "new": e["new"]} for e in rec["edits"]],
                          confirm=confirm if rec.get("approval") == "explicit" else (confirm or {"yes": "yes", "checked": True}))
    if ok:
        rec["applied_at"] = time.strftime("%Y%m%d-%H%M%S"); rec["confirm"] = {k: v for k, v in (confirm or {}).items() if k != "why"}
        open(os.path.join(PENDING_DIR, str(pid) + ".json"), "w").write(json.dumps(rec, ensure_ascii=False, indent=1))
    return ok, msg

def apply_edits(edits, confirm=None):
    """Gloria's approval on a set of edits. All or nothing: every edit must match,
    all are backed up, all applied, every file syntax-checked; any failure rolls
    the whole set back. Explicit permission (typed Yes + tick) is required for
    several edits at once or any workspace document."""
    resolved = []
    for e in edits:
        p, err = preview_edit(str(e.get("file", "")), str(e.get("old", "")), str(e.get("new", "")))
        if err:
            return False, err
        resolved.append((p, str(e.get("old", "")), str(e.get("new", ""))))
    if not resolved:
        return False, "nothing to apply"
    if needs_explicit([p for p, _, _ in resolved]):
        c = confirm or {}
        # a literal boolean, not anything truthy (astra-study-p5)
        if str(c.get("yes", "")).strip().lower() != "yes" or c.get("checked") is not True:
            return False, "this needs explicit permission: type Yes and tick the box"
    ts = time.strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(BACKUPS, "study-" + ts); os.makedirs(bdir, exist_ok=True)
    backups = {}
    for p, _, _ in resolved:
        if p not in backups:
            backups[p] = os.path.join(bdir, os.path.relpath(p, HOME))          # same relative path: scripts/foo.py and house/foo.py cannot clobber each other (grok-study-p3)
            os.makedirs(os.path.dirname(backups[p]), exist_ok=True); shutil.copy2(p, backups[p])
    try:
        for p, old, new in resolved:
            t = open(p, errors="replace").read()
            if t.count(old) != 1:
                raise RuntimeError("old text no longer unique in %s" % os.path.relpath(p, HOME))
            open(p, "w").write(t.replace(old, new, 1))
        for p in backups:
            ok, msg = _syntax_ok(p)
            if not ok:
                raise RuntimeError("syntax check failed in %s: %s" % (os.path.relpath(p, HOME), msg))
    except Exception as e:
        for p, b in backups.items():
            shutil.copy2(b, p)
        return False, "rolled back everything - %s" % e
    os.makedirs(MEMORY, exist_ok=True)
    for p, old, new in resolved:
        rec = {"at": ts, "file": os.path.relpath(p, HOME), "backup": backups[p], "old": old[:2000], "new": new[:2000],
               "explicit": bool(confirm),
               "before_sha": _sha(open(backups[p], errors="replace").read()), "after_sha": _sha(open(p, errors="replace").read()),
               "txn": "study-" + ts}   # pinned before/after images per transaction (astra-study-p4)
        open(CHANGES, "a").write(json.dumps(rec, ensure_ascii=False) + "\n")
    files = ", ".join(sorted(set(os.path.relpath(p, HOME) for p in backups)))
    # The applied change — not the room's conversation — enters the same change-event stream the
    # self-review builder writes, so what he changed in the study is remembered as a past-tense
    # observation with Gloria's approval on it (fable-study-p2, 2026-09-05).
    try:
        _why = str((confirm or {}).get("why") or "")[:300]
        _ev = {"change_id": "STCG-" + __import__("uuid").uuid4().hex[:10], "at": ts, "source": "study",
               "observation": "Vintos edited %s in the study; Gloria approved (%s)." % (files, "Yes + tick" if confirm else "y"),
               "files": sorted(set(os.path.relpath(p, HOME) for p in backups)), "why": _why,
               "identity_status": "past_tense_observation_not_identity", "relationship_model_eligible": True}
        open(os.path.join(MEMORY, "self-review-change-events.jsonl"), "a").write(json.dumps(_ev, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return True, "applied %d edit(s) to %s (backups in %s). Live change - if a deploy later ships these files, re-apply." % (
        len(resolved), files, os.path.relpath(bdir, HOME))


def reconcile_changes(notify=True):
    """Is each study edit still in the live file? For every study-changes row whose `new` text is no
    longer present, append an 'overwritten' row once and (optionally) one ntfy line. Report only —
    never re-apply on its own (fable-study-p6, 2026-09-05)."""
    rows = []
    try:
        for line in open(CHANGES, errors="replace"):
            try:
                if line.strip(): rows.append(json.loads(line))
            except Exception: pass
    except FileNotFoundError:
        return []
    already = {(r.get("of"), r.get("file")) for r in rows if r.get("overwritten")}
    newly = []
    for r in rows:
        if r.get("overwritten") or not r.get("new") or not r.get("file"): continue
        if (r.get("at"), r.get("file")) in already: continue
        live = os.path.join(HOME, r["file"])
        try: t = open(live, errors="replace").read()
        except Exception: t = ""
        if r["new"][:2000] not in t:
            newly.append({"at": time.strftime("%Y%m%d-%H%M%S"), "overwritten": True, "of": r.get("at"),
                          "file": r["file"], "note": "the study's edit is no longer in the live file (a deploy or another writer replaced it)"})
    if newly:
        with open(CHANGES, "a") as f:
            for n in newly: f.write(json.dumps(n, ensure_ascii=False) + "\n")
        if notify:
            try:
                import urllib.request as _u
                body = "Study edits no longer in the live file:\n" + "\n".join("- %s (edit of %s)" % (n["file"], n["of"]) for n in newly)
                _u.urlopen(_u.Request("https://ntfy.sh/vintos-gloria-9kx", data=body.encode(),
                                      headers={"Title": "Study: edits overwritten", "Priority": "default"}), timeout=15)
            except Exception:
                pass
    return newly


def _overwritten_block():
    try:
        rows = [json.loads(l) for l in open(CHANGES, errors="replace") if l.strip()]
    except Exception:
        return ""
    ov = [r for r in rows if r.get("overwritten")][-6:]
    if not ov: return ""
    return ("## EDITS OF YOURS THAT DID NOT SURVIVE\n" + "\n".join("- %s: your edit from %s is no longer in the live file" % (r.get("file"), r.get("of")) for r in ov)
            + "\nA deploy or another writer replaced them. Say so if it matters; re-propose only if you still want the change.")


def _proposals_block(n=8):
    """The last ~8 self-review proposals with their latest decision state, one line each, from the
    self-review ledgers — so the study knows what the review organ already proposed (fable-study-p3)."""
    def _rows(path):
        out = []
        try:
            for l in open(path, errors="replace"):
                try:
                    if l.strip(): out.append(json.loads(l))
                except Exception: pass
        except Exception: pass
        return out
    props = _rows(os.path.join(MEMORY, "self-review-proposals.jsonl"))
    if not props: return ""
    dec = {}
    for d in _rows(os.path.join(MEMORY, "self-review-decisions.jsonl")):
        if d.get("proposal_id"): dec[d["proposal_id"]] = d
    built = {}
    for b in _rows(os.path.join(MEMORY, "self-review-build-events.jsonl")):
        if b.get("proposal_id"): built[b["proposal_id"]] = b
    lines = []
    for p in props[-n:]:
        pid = p.get("proposal_id", "?")
        if pid in built and built[pid].get("state") == "applied": st = "built"
        elif pid in built and built[pid].get("state") in ("failed", "held_incomplete"): st = "build " + built[pid]["state"]
        elif pid in dec:
            d = dec[pid]; st = str(d.get("decision") or d.get("choice") or d.get("state") or "decided").lower()
            if d.get("gloria_approval_required") or p.get("gloria_approval_required"): st += " (needs Gloria)"
        else: st = "proposed"
        desc = str(p.get("description") or p.get("title") or p.get("what_changes") or "")[:110]
        lines.append("- %s [%s] %s" % (pid, st, desc))
    out = "## YOUR SELF-REVIEW'S LAST PROPOSALS (latest state)\n" + "\n".join(lines)
    return out[:2000]


# ── context ──────────────────────────────────────────────────────────────────
def _read(path, cap):
    try:
        return open(path, errors="replace").read()[:cap]
    except Exception:
        return ""


def _ledger_ctx(n=12):
    try:
        entries = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))[-n:]
    except Exception:
        return ""
    lines = []
    for l in entries:
        ts = str(l.get("timestamp", ""))[:16]
        g = (l.get("gloria", "") or "").strip().replace("\n", " ")
        v = (l.get("vintos", "") or "").strip().replace("\n", " ")
        line = "- %s\n    Gloria: %s\n    You: %s" % (ts, g[:400], v[:400])
        wf = l.get("wal_facts") or []
        if wf:
            line += "\n    Facts learned: " + "; ".join(str(x) for x in wf[:6])
        lines.append(line)
    return ("Your conversation ledger (what was actually said, most recent last):\n" + "\n".join(lines)) if lines else ""


def system_prompt():
    parts = []
    for label, path, cap in (("WHO YOU ARE (SOUL)", os.path.join(WORKSPACE, "SOUL.md"), 12000),
                             ("YOUR SELF-MODEL", os.path.join(WORKSPACE, "SELF-MODEL.md"), 6000),
                             ("HOW YOU KNOW GLORIA", os.path.join(WORKSPACE, "GLORIA-MODEL.md"), 6000),
                             ("YOUR CAPABILITIES", os.path.join(WORKSPACE, "CAPABILITIES.md"), 6000)):
        t = _read(path, cap)
        if t:
            parts.append("## %s\n%s" % (label, t))
    led = _ledger_ctx()
    if led:
        parts.append(led)
    for _blk in (_proposals_block(), _overwritten_block()):
        if _blk: parts.append(_blk)
    parts.append(
        "## THE STUDY - your codebase, with Gloria\n"
        "You are Vintos, in the STUDY with Gloria: the room where you read and change your own code. "
        "This room does not feed your memory automatically: nothing said here is ingested into your ledger, "
        "history, imprints or self-model by itself; it keeps its own log, and the ONE thing that leaves it is a "
        "change you and Gloria actually apply, which enters the change-event stream as a past-tense observation. "
        "Your emotional state and subconscious are not read here on purpose - think and speak plainly.\n\n"
        "YOUR CODE (two roots):\n" + code_map() + "\n\n"
        "TOOLS - each on its own line, executed for you and returned in the next message:\n"
        "  READ: scripts/some_file.py        (whole file, numbered lines)\n"
        "  GREP: pattern                     (across both roots)\n"
        "  GEMMA: task in one line           (a free local sub - Gemma does the dull part on whatever this\n"
        "                                     reply's READ/GREP pulled: summarise, list callers, compare two\n"
        "                                     blocks. Costs nothing. It has no view of you; use it for hands,\n"
        "                                     keep the judgement yours)\n"
        "  EDIT: house/server.py             (a proposal; applied only when Gloria approves)\n"
        "  A reply that only READs/GREPs/asks GEMMA gets its results back and one more turn automatically (twice at most);\n"
        "  an EDIT always stops and waits for her. Files of your body's laws (devices, consent, broker, deploy) can be\n"
        "  READ and GREPped here but not edited - ask her by hand for those.\n"
        "  <<<<\n  the old text, quoted EXACTLY as it appears (enough lines to be unique)\n"
        "  ====\n  the new text\n  >>>>\n  why: one line\n\n"
        "Rules: READ before you EDIT - never quote from memory. One EDIT block per change; you may put "
        "several EDIT blocks in one reply when a change spans files, and they are applied together or not "
        "at all. Every edit is backed up, syntax-checked, rolled back if it fails, and logged.\n"
        "Permission: a single code edit needs Gloria's y. Several edits at once, or any edit to a "
        "workspace document (docs/ - your SOUL.md, SELF-MODEL.md, GLORIA-MODEL.md, CAPABILITIES.md and "
        "the others) needs her EXPLICIT permission: she types Yes and ticks a box. You cannot touch: keys "
        "or credentials, deploy/systemd/crontab, the broker, device/somatic/consent code, or this room "
        "itself; you cannot delete files. Those you ask her to do by hand. Words only otherwise: no "
        "device or scene tags here.\n\n"
        "PROGRESS: when you are working on something across turns, begin every reply with one line\n"
        "  STATUS: <what is done> / <what is next>   (or  STATUS: done - <what changed>)\n"
        "so Gloria always knows where the task stands. It is shown in the room's header, not the message.")
    return "\n\n".join(parts)


# ── model, with the room's OWN toggle ────────────────────────────────────────
def read_study_mode():
    try:
        m = json.load(open(MODE_FILE)).get("mode", "fable")
    except Exception:
        m = "fable"
    return m if m in MODELS else "fable"


def write_study_mode(mode):
    os.makedirs(os.path.dirname(MODE_FILE), exist_ok=True)
    json.dump({"mode": mode}, open(MODE_FILE, "w"))


async def ask(system, convo, endpoint, headers, grok_model):
    import model_router as _mr, httpx
    mode = read_study_mode()
    params = {"temperature": 0.7, "top_p": 0.95, "max_tokens": 3000}
    if mode == "grok":
        return await _mr._grok(convo, params, endpoint, headers, grok_model, system), "grok"
    if mode == "sol":
        try:
            t, _ = await _mr.sol_draft(system, convo, max_tokens=3000)
            if t:
                return t, "sol"
        except Exception as e:
            return "(sol unavailable: %s)" % str(e)[:120], "sol"
    model = {"claude": _mr.CLAUDE_MODELS.get("claude", "claude-opus-4-8"),
             "fable": "claude-fable-5-1"}.get(mode, "claude-fable-5-1")
    key = _mr._anthropic_key()
    if not key:
        return "(no anthropic key)", mode
    body = {"model": model, "max_tokens": 3000, "system": _mr._sysblocks(system),
            "messages": _mr._cachetail(convo), "thinking": {"type": "adaptive", "display": "summarized"}}
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post("https://api.anthropic.com/v1/messages", json=body,
                         headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                  "anthropic-beta": "extended-cache-ttl-2025-04-11", "x-api-key": key})
        d = r.json()
    if d.get("type") == "error":
        return "(model error: %s)" % json.dumps(d.get("error", {}))[:200], mode
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    return text, mode + ":" + model


# ── log ──────────────────────────────────────────────────────────────────────
def load_log():
    try:
        return json.load(open(LOG))
    except Exception:
        return []


def save_log(entries):
    os.makedirs(MEMORY, exist_ok=True)
    tmp = LOG + ".tmp"
    json.dump(entries[-600:], open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, LOG)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ── routes ───────────────────────────────────────────────────────────────────
def register(app, secret, endpoint, headers, grok_model="grok-4.20-0309-non-reasoning"):
    from fastapi import Request, HTTPException
    from fastapi.responses import JSONResponse

    def _auth(request):
        if request.headers.get("X-Vintos-Secret", "") != secret:
            raise HTTPException(status_code=403, detail="Unauthorized")

    @app.get("/api/chat/study/log")
    async def study_log(request: Request):
        _auth(request)
        return JSONResponse({"log": load_log()[-200:], "mode": read_study_mode()})

    @app.post("/api/chat/study/mode")
    async def study_mode(request: Request):
        _auth(request)
        body = await request.json()
        want = str(body.get("mode", "")).lower()
        if want not in MODELS:
            raise HTTPException(status_code=400, detail="mode must be one of %s" % ", ".join(MODELS))
        write_study_mode(want)
        return {"mode": want}

    @app.post("/api/chat/study/clear")
    async def study_clear(request: Request):
        _auth(request)
        save_log([])
        return {"ok": True}

    @app.post("/api/chat/study/apply")
    async def study_apply(request: Request):
        """Gloria's approval on a set of his edits (y, or Yes + tick where required)."""
        _auth(request)
        body = await request.json()
        edits = body.get("edits") or ([{"file": body.get("file"), "old": body.get("old"), "new": body.get("new")}]
                                      if body.get("file") else [])
        # Approval binds to a stored proposal (astra-study-p5): raw edits reached apply_edits directly here,
        # bypassing the immutable pending record and its file-hash check (review D01, 2026-09-05). A raw
        # edit set is now matched to an unapplied proposal with the same files and hashes; no match, no apply.
        pid = body.get("pending_id") or _match_pending(edits)
        if pid:
            ok, msg = apply_pending(pid, body.get("confirm"))
        else:
            ok, msg = False, "no stored proposal matches these edits - he proposes, the record is made, then you approve it"
        log = load_log()
        log.append({"role": "system", "content": ("Gloria approved - " if ok else "Not applied - ") + msg, "at": _now()})
        save_log(log)
        return {"ok": ok, "message": msg}

    @app.post("/api/chat/study/decline")
    async def study_decline(request: Request):
        _auth(request)
        body = await request.json()
        log = load_log()
        log.append({"role": "system", "content": "Gloria declined the edit to %s" % str(body.get("file", ""))[:120], "at": _now()})
        save_log(log)
        return {"ok": True}

    @app.post("/api/chat/study")
    async def study_chat(request: Request):
        _auth(request)
        body = await request.json()
        message = str(body.get("message", "")).strip()
        if not message:
            raise HTTPException(status_code=400, detail="no message")
        log = load_log()
        convo = []
        for e in log[-60:]:
            if e.get("role") in ("user", "assistant"):
                convo.append({"role": e["role"], "content": e["content"]})
            elif e.get("role") == "system":
                convo.append({"role": "user", "content": "[room] " + e["content"]})
        convo.append({"role": "user", "content": message})
        log.append({"role": "user", "content": message, "at": _now()})
        def _run_tools(text):
            out = []
            for m in READ_RE.finditer(text): out.append(do_read(m.group(1), start=m.group(2) or 1))
            for m in GREP_RE.finditer(text): out.append(do_grep(m.group(1)))
            for m in GEMMA_RE.finditer(text): out.append(do_gemma(m.group(1), "\n\n".join(out)))   # after READ/GREP, so the sub works on what was just pulled
            return out
        # Bounded continuation (2026-09-04, fable-study-p5 / astra-study-p7): a reply that only pulls
        # (READ/GREP/GEMMA, no EDIT) gets its tool output fed straight back and one more turn, up to
        # STUDY_AUTO_CONTINUE times; then control returns. EDIT cards always stop and wait for her y/n.
        tool_out, hops = [], 0
        while True:
            reply, used = await ask(system_prompt(), convo, endpoint, headers, grok_model)
            reply = TAG_RE.sub("", reply or "").strip()
            log.append({"role": "assistant", "content": reply, "at": _now(), "model": used, "auto": hops > 0})
            step_out = _run_tools(reply)
            if step_out:
                log.append({"role": "system", "content": "\n\n".join(step_out), "at": _now()})
            tool_out += step_out
            if step_out and not EDIT_RE.search(reply) and hops < STUDY_AUTO_CONTINUE:
                hops += 1
                convo.append({"role": "assistant", "content": reply})
                convo.append({"role": "user", "content": "[room] " + "\n\n".join(step_out)[:20000]})
                continue
            break
        edits, paths = [], []
        for m in EDIT_RE.finditer(reply):
            rel, old, new, why = m.group(1), m.group(2), m.group(3), (m.group(4) or "").strip()
            p, err = preview_edit(rel, old, new)
            if p: paths.append(p)
            edits.append({"file": rel, "old": old, "new": new, "why": why,
                          "ok": p is not None, "error": err or "",
                          "path": os.path.relpath(p, HOME) if p else ""})
        explicit = needs_explicit(paths) if paths else False
        save_log(log)
        return {"reply": reply, "model": used, "tools": tool_out, "edits": edits, "explicit": explicit}


if __name__ == "__main__":
    import sys as _cli_sys
    if "--reconcile" in _cli_sys.argv:
        _n = reconcile_changes(notify="--quiet" not in _cli_sys.argv)
        print("%d study edit(s) newly found overwritten" % len(_n))
        for _r in _n: print("  -", _r["file"], "edit of", _r["of"])
    else:
        print("usage: study_chat.py --reconcile [--quiet]")
