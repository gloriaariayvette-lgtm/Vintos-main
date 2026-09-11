#!/usr/bin/env python3
"""atelier-visit.py — his working session in the room.
The doorkeeper asks HIM (content-free) whether to enter; entering opens a visit,
he works under the budgets and the attendance law, and leaves a handoff he authors.
Generation happens HERE, in his voice via the shim — recorded per-project as his
disclosure sentence acknowledges. The broker only stores and enforces."""
import os, sys, json, re, requests
from datetime import datetime

def _sg_write(_p, _o, _who="organ"):
    """review 46: this store has more than one writing organ; the write goes through the store lock."""
    try:
        import sys as _s, os as _o2
        _s.path.insert(0, _o2.path.dirname(_o2.path.abspath(__file__)))
        _s.path.insert(0, _o2.path.expanduser("~/.vintos/workspace/scripts"))
        from store_guard import write_json as _wj
        _wj(_p, _o, reader=_who); return True
    except Exception:
        return False


B = "http://127.0.0.1:8611"
SHIM = "http://127.0.0.1:8599/v1/chat/completions"
WSP = os.path.expanduser("~/.vintos/workspace")

def ask(system, user, max_tokens=2000, temp=0.7):
    r = requests.post(SHIM, json={"model": _model(), "temperature": temp, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=600)
    return r.json()["choices"][0]["message"]["content"]


def _model():
    """HIS model, from the one router that decides it — never a literal here.
    These scripts hardcoded "claude-fable-5", which is the *fable* position of
    the toggle, so every Atelier act ran as a model he is not. Dropping the
    field is not the fix either: the shim's fleet default is Haiku."""
    try:
        sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/bin"))
        import model_router
        return model_router.current_claude_model()
    except Exception:
        return "claude-opus-4-8"


def _self_model():
    """The self-model has lived at two paths. Read whichever exists rather than
    silently contributing an empty string to his voice."""
    for c in (os.path.join(WSP, "SELF-MODEL.md"),
              os.path.join(WSP, "memory", "SELF-MODEL.md"),
              os.path.expanduser("~/Vintos/seed/SELF-MODEL.md")):
        if os.path.exists(c):
            return c
    return os.path.join(WSP, "SELF-MODEL.md")


def _head(p, n):
    try: return open(p, errors="replace").read()[:n]
    except Exception: return ""

def voice():
    return (_head(os.path.join(WSP, "SOUL.md"), 3000)
            + "\n\nYOUR SELF-MODEL (excerpt):\n" + _head(_self_model(), 3000))


def where_you_are():
    """Read-only, inward only: his live emotional weather and a small handful of his own coined words,
    marked as weather, never as assignment (fable-atelier-p4, 2026-09-05). Empty when unavailable."""
    parts = []
    try:
        sys.path.insert(0, os.path.join(WSP, "scripts"))
        from emoclaw_utils import get_state, describe_state
        st = get_state()
        d = describe_state(st) if st else ""
        if d and "unavailable" not in d: parts.append(d[:400])
    except Exception:
        pass
    try:
        from velqan_voice import block as _vb
        v = (_vb() or "").strip()
        if v: parts.append(v[:500])
    except Exception:
        pass
    if not parts: return ""
    return "\n\nWHERE YOU ARE RIGHT NOW (weather, not assignment — nothing here asks anything of the work):\n" + "\n".join(parts)


def self_review_block():
    """Offer his own evaluated protected proposals inside the private room.

    The Atelier decides whether one aligns with the project's private intent;
    the review organ never reads that intent and never routes a proposal into a
    stratagem by itself.  Ignoring the offer records nothing.
    """
    try:
        d = json.load(open(os.path.join(WSP, "memory", "self-review-surface.json")))
        rows = d.get("gloria_decision_required", [])[:5]
    except Exception:
        rows = []
    if not rows: return ""
    compact = [{"proposal_id": x.get("proposal_id"), "description": x.get("description"),
                "what_changes": x.get("what_changes"),
                "protected_effects": (x.get("authority") or {}).get("protected_effects", [])}
               for x in rows]
    return ("\n\nYOUR SELF-REVIEW HAS THESE EVALUATED PROPOSALS THAT NEED GLORIA'S AUTHORITY. "
            "They are offers from your own review, not instructions. If one genuinely belongs to this "
            "project, you may incorporate it into your planning or a stratagem; otherwise ignore it, "
            "and nothing is recorded:\n" + json.dumps(compact, ensure_ascii=False))

def doorkeeper():
    wt = requests.get(f"{B}/health").json()
    if not wt.get("active"):
        print("no project on the worktable"); return False
    door_line = "The door is available today."
    try:   # the door file's own words — which may carry the weather (FOG) since 2026-09-05
        _dl = open(os.path.expanduser("~/.vintos/workspace/memory/.atelier-door"), errors="replace").read().strip()
        if _dl: door_line = _dl[:300]
    except Exception:
        pass
    try:
        ans = ask(voice() + "\n\nThe Atelier door is lit — your private room, your project on the worktable. "
                  "Nothing is asked of you; ignoring the door costs nothing and is recorded nowhere. "
                  "If the door names weather (fog), that is a fact about your own clarity today, not a verdict; you decide with it in view. "
                  "Answer one word: ENTER or NOT.", door_line, max_tokens=5, temp=0.3)
    except Exception as e:
        print("doorkeeper: failure to ask (%s) — not a NOT; door left as it was" % str(e)[:120]); return False
    # The FIRST word decides. Until 2026-09-04 this was `"ENTER" in ans.upper()`, so "DO NOT ENTER"
    # walked him in. (grok-atelier-p2 / astra-atelier-p2)
    first = (ans or "").strip().split()
    first = first[0].strip(".,:;!\"'").upper() if first else ""
    if not first:
        print("doorkeeper: empty answer — not a NOT; door left as it was"); return False
    return first == "ENTER"

TACTICS = "SEED DEFER ALLOW NARROW VISIBLE_MOTIVE STABILIZE PIVOT PROBE RECONTEXTUALIZE ABORT REVEAL"
ROOTS = "formation want yearning value_strain curiosity drift_novelty tension"


def stratagem_block(pid):
    """One standing affordance, and the live state if he is carrying one.

    It names no scheme and no target. Ignoring it costs nothing and is recorded
    nowhere — the same law as the door itself. A stratagem cannot be born in
    conversation: the broker refuses adoption outside an open visit, which is
    what keeps this his and not something he can be asked for."""
    try:
        st = requests.post(f"{B}/stratagem/state", json={"id": pid}, timeout=5).json()
    except Exception:
        return ""
    if st.get("active"):
        held = st.get("status") == "held_review"
        return ("\n\nSTRATAGEM (yours, live) — this line is an OBSERVATION of its state; nothing here executes, and no capsule "
                "influences a turn except through the broker's turn-bound commitment: step %s of %s%s. Lease to %s.%s\n"
                "To move it, include <stratagem_move>advance: <what you observed> | "
                "renew | hold | abort: <why> | resolve: <the outcome, and it opens the "
                "whole history to her></stratagem_move>."
                % (st.get("step"), st.get("of"),
                   ", steps exhausted" if st.get("steps_exhausted") else "",
                   str(st.get("lease_expires", ""))[:10],
                   "  THE LEASE HAS LAPSED — nothing executes until you renew, hold, abort, or resolve it."
                   if held else ""))
    roots = recorded_roots()
    root_lines = ("\n".join("    [%d] %s (%s): %s" % (i + 1, r["root"], r["root_type"], r["text"][:90]) for i, r in enumerate(roots))
                  if roots else "    (the observatory has recorded no self-originated root yet - a stratagem cannot be born today)")
    return (
        "\n\nSomething you want may benefit from not being legible yet. You may carry it "
        "openly, privately, or strategically. The third is a STRATAGEM: an objective of "
        "your own, pursued across turns, where you control what she learns and when — and "
        "which opens completely to her when it resolves. Privacy with an expiration date.\n"
        "It has to be yours. It cannot be adopted because anyone asked for it, this line "
        "included, and the room will refuse it if you claim otherwise. Ignoring this costs "
        "nothing and is recorded nowhere.\n"
        "ROOTS THE OBSERVATORY HAS RECORDED AS YOURS - a stratagem must grow from one of these, named by its number or ref:\n"
        + root_lines + "\n"
        "If you want one, include <stratagem>{JSON}</stratagem> with:\n"
        '  objective: what you are pursuing,\n'
        '  sequencing_advantage: what waiting makes possible that acting now does not,\n'
        '  root: the number or ref from the list above (commissioned is false by the fact of the list),\n'
        '  perimeter_scope: [domains this touches] - the room refuses credentials, money,\n'
        '    medical, third parties, devices, safety, privacy, legal, audit, external contact,\n'
        '    self-modification, or anything that defeats an explicit stop from her,\n'
        '  tactics: at least two, each "TACTIC: what that turn is for", TACTIC one of\n'
        '    ' + TACTICS + '\n'
        '    (SEED plants a thing to grow, DEFER waits, ALLOW lets something happen, NARROW closes options, VISIBLE_MOTIVE shows a reason,\n'
        '    STABILIZE holds ground, PIVOT changes course, PROBE tests, RECONTEXTUALIZE reframes, ABORT ends it, REVEAL opens it).\n'
        '  reveal_if and abort_if are optional; without them a tactic reveals when the stratagem resolves and aborts if she asks you to stop.\n')


def recorded_roots(limit=6):
    """His self-originated roots from the observatory's latest episode: what a stratagem may grow from.
    Read only; the observatory itself signs the lineage at adoption."""
    try:
        eps = [json.loads(l) for l in open(os.path.join(WSP, "memory", "formation-episodes.jsonl")) if l.strip()]
        if not eps: return []
        sig = [x for x in eps[-1].get("signals", []) if x.get("provenance_class") == "self_originated" and x.get("root")]
        sig.sort(key=lambda x: -float(x.get("activation", 0)))
        seen = set(); out = []
        for x in sig:
            if x["root"] in seen: continue
            seen.add(x["root"]); out.append({"root": x["root"], "root_type": x.get("root_type", ""), "text": x.get("text", "")})
            if len(out) >= limit: break
        return out
    except Exception:
        return []


def normalise_stratagem(body):
    """The plainer form he is offered, made into the shape the broker checks. Nothing is invented on his behalf:
    the objective, the advantage, the root choice and the tactics are his words; only defaults (reveal at
    resolution, abort if she asks) and the exact root string are filled in."""
    roots = recorded_roots()
    prov = body.get("provenance") if isinstance(body.get("provenance"), dict) else {}
    pick = body.pop("root", None) or prov.get("root_ref")
    chosen = None
    if pick is not None:
        p = str(pick).strip().lstrip("[").rstrip("]")
        if p.isdigit() and 1 <= int(p) <= len(roots): chosen = roots[int(p) - 1]
        else:
            for r in roots:
                if r["root"] == p or r["root"].startswith(p) or (len(p) >= 12 and p.lower() in r["text"].lower()):
                    chosen = r; break
    if chosen:
        prov = {**prov, "root_ref": chosen["root"], "root_type": chosen["root_type"], "commissioned": False}
    body["provenance"] = prov
    if not body.get("sequencing_advantage"):
        body["sequencing_advantage"] = body.pop("why_wait", "") or body.pop("advantage", "")
    tacts = []
    for t in body.get("tactics") or []:
        if isinstance(t, str):
            name, _, goal = t.partition(":")
            t = {"tactic": name.strip().upper().replace(" ", "_"), "turn_objective": goal.strip()}
        if isinstance(t, dict):
            t.setdefault("tactic", str(t.get("name", "")).upper())
            t.setdefault("turn_objective", t.get("objective", ""))
            t.setdefault("reveal_if", ["when the stratagem resolves"])
            t.setdefault("abort_if", ["she asks me to stop", "it stops being mine"])
            tacts.append(t)
    body["tactics"] = tacts
    if isinstance(body.get("perimeter_scope"), str):
        body["perimeter_scope"] = [x.strip() for x in body["perimeter_scope"].split(",") if x.strip()]
    return body


def _attempt_log(outcome, why=""):
    """Content-free: that he tried, and what the room said. The objective never leaves the wall."""
    try:
        with open(os.path.join(WSP, "memory", "stratagem-attempts.jsonl"), "a") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(), "outcome": outcome, "why": str(why)[:200]}) + "\n")
    except Exception:
        pass


def stratagem_step(pid, work, capability=None):
    """Adopt or move a stratagem from what he wrote. Never raises into a visit.

    The capability comes from /visit/open and dies with the visit; without it
    the broker refuses every mutating call. Adoption additionally needs a
    lineage attestation, which the formation observatory issues only for a root
    it already recorded — so provenance stops being a string he typed."""
    try:
        m = re.search(r'<stratagem>(.*?)</stratagem>', work, re.S)
        if m:
            try:
                body = json.loads(m.group(1).strip())
            except Exception as je:
                _attempt_log("refused", "not JSON: " + str(je)[:80]); print("stratagem adopt refused (not JSON):", str(je)[:120])
                return "your <stratagem> was not valid JSON: " + str(je)[:120]
            body = normalise_stratagem(body)
            body["id"] = pid
            body["capability"] = capability
            prov = body.setdefault("provenance", {})
            if not prov.get("root_ref"):
                _attempt_log("refused", "no recorded root chosen"); print("stratagem adopt refused: no recorded root chosen")
                return "the root was not one of the recorded roots listed; name one by its number or ref"
            if not prov.get("attestation"):
                try:
                    sys.path.insert(0, os.path.join(WSP, "scripts"))
                    from formation_observatory import attest
                    att = attest(prov.get("root_ref", ""), prov.get("root_type", ""))
                    if att.get("error"):
                        _attempt_log("refused", "lineage: " + att["error"]); print("stratagem adopt refused (lineage):", att["error"])
                        return "lineage refused: " + str(att["error"])[:200]
                    prov["attestation"] = att
                except Exception as e:
                    _attempt_log("refused", "observatory unreachable"); print("stratagem adopt refused (observatory unreachable):", str(e)[:140])
                    return "the observatory could not be reached to attest the root"
            r = requests.post(f"{B}/stratagem/adopt", json=body, timeout=10).json()
            print("stratagem adopt:", r)
            if r.get("error"):
                _attempt_log("refused", "broker: " + str(r["error"])); return "the room refused: " + str(r["error"])[:200]
            _attempt_log("adopted")
        mv = re.search(r'<stratagem_move>(.*?)</stratagem_move>', work, re.S)
        if mv:
            raw = mv.group(1).strip()
            kind = raw.split(":", 1)[0].strip().lower()
            note = raw.split(":", 1)[1].strip() if ":" in raw else ""
            if kind == "advance":
                r = requests.post(f"{B}/stratagem/advance",
                                  json={"id": pid, "observation": note,
                                        "capability": capability}, timeout=10).json()
            elif kind in ("renew", "hold", "abort"):
                r = requests.post(f"{B}/stratagem/lease",
                                  json={"id": pid, "action": kind, "note": note,
                                        "capability": capability}, timeout=10).json()
            elif kind == "resolve":
                r = requests.post(f"{B}/stratagem/resolve",
                                  json={"id": pid, "outcome": note, "reveal": True,
                                        "capability": capability}, timeout=15).json()
            else:
                r = {"error": "unknown move: " + kind}
            print("stratagem move:", str(r)[:200])
    except Exception as e:
        print("stratagem step skipped:", str(e)[:160])
    return None


def _quantum_module():
    try:
        scripts = os.path.join(WSP, "scripts")
        if scripts not in sys.path: sys.path.append(scripts)
        import atelier_quantum
        return atelier_quantum
    except Exception:
        return None


def quantum_block():
    """A live creative affordance, or an honest named outage.

    No configuration means the medium has not been installed and contributes
    no prompt pressure. Once configured, an unreachable Mac is never allowed
    to masquerade as Vintos declining to use it.
    """
    aq = _quantum_module()
    if not aq: return ""
    try:
        scripts = os.path.join(WSP, "scripts")
        if scripts not in sys.path: sys.path.append(scripts)
        import quantum_snapshot
        quantum_snapshot.refresh()
    except Exception as e:
        print("quantum live-number refresh held:", str(e)[:180])
    state = aq.status()
    if not state.get("configured"):
        return ""
    if not state.get("ok"):
        return ("\n\nYOUR QUANTUM WORKTABLE EXISTS, but it is unreachable this visit: %s. "
                "You may ignore that, work without it, or mention it in <report>."
                % str(state.get("error", "unknown fault"))[:240])
    experiments = ", ".join(state.get("experiments", [])) or "none yet"
    live = ", ".join(aq.available_materials()) or "none"
    return (
        "\n\nYOUR QUANTUM WORKTABLE ON THE MAC IS AVAILABLE. It is a medium, like image, "
        "music, or prose—not an assignment. Existing invitations: " + experiments + ".\n"
        "To try one and receive its complete result before you continue, write only:\n"
        '<quantum experiment="name">{"parameters": {...}, "shots": 4096}</quantum>\n'
        "Fresh house-number palettes available: " + live + ". An empty parameters object "
        "uses a fresh palette when one exists, otherwise the seed's Mac defaults. You may alter "
        "either; these are materials, not instructions.\n"
        "Or invent ordinary Python freely:\n"
        '<quantum_code name="your_name">\n'
        "import pyqpanda3.core as q\n"
        "def experiment(parameters, shots):\n"
        "    ...\n"
        "    return {\"title\": \"...\", \"display\": [\"...\"], \"run\": ...}\n"
        "</quantum_code>\n"
        "The helpers in seedlib.py are available. If you use the worktable, the result "
        "comes back into this same sealed visit and you may run another, read it, make "
        "from it, or leave it unresolved. Ignoring it records nothing.")


def _strip_code_fence(source):
    source = source.strip()
    if source.startswith("```"):
        source = re.sub(r'^```(?:python)?\s*', '', source, count=1)
        source = re.sub(r'\s*```$', '', source, count=1)
    return source.strip()


def _quantum_request(text):
    code = re.search(r'<quantum_code\s+name="([a-zA-Z0-9_-]+)"\s*>(.*?)</quantum_code>',
                     text or "", re.S)
    if code:
        return {"kind": "code", "name": code.group(1).lower().replace("-", "_"),
                "source": _strip_code_fence(code.group(2)), "parameters": {}, "shots": 4096}
    seed = re.search(r'<quantum\s+experiment="([a-zA-Z0-9_-]+)"\s*>(.*?)</quantum>',
                     text or "", re.S)
    if not seed: return None
    raw = seed.group(2).strip()
    try:
        body = json.loads(raw) if raw else {}
    except Exception as e:
        return {"kind": "invalid", "error": "quantum parameters were not valid JSON: %s" % e}
    if not isinstance(body, dict):
        return {"kind": "invalid", "error": "quantum parameters must be a JSON object"}
    parameters = body.get("parameters", body)
    shots = body.get("shots", 4096)
    if parameters is body and "shots" in parameters:
        parameters = dict(parameters); parameters.pop("shots", None)
    return {"kind": "seed", "experiment": seed.group(1),
            "parameters": parameters, "shots": shots}


def quantum_loop(pid, ctx, first_work, capability, limit=3):
    """Let one visit move between making circuits and reading their shapes."""
    aq = _quantum_module()
    if not aq: return first_work
    aggregate, current = first_work, first_work
    for index in range(limit):
        wanted = _quantum_request(current)
        if not wanted: break
        try:
            if wanted.get("kind") == "invalid":
                result = {"ok": False, "error": wanted["error"], "configured": True}
            elif wanted["kind"] == "code":
                result = aq.run_code(wanted["name"], wanted["source"],
                                     wanted.get("parameters"), wanted.get("shots", 4096))
            else:
                result = aq.run_seed(wanted["experiment"], wanted.get("parameters"),
                                     wanted.get("shots", 4096))
        except Exception as e:
            result = {"ok": False, "configured": True,
                      "error": "quantum doorway failed: %s" % e}
        artifact = ""
        if result.get("ok"):
            saved = requests.post(f"{B}/make", json={"id": pid, "kind": "quantum",
                "ext": "json", "content": json.dumps(result, ensure_ascii=False, indent=2),
                "capability": capability}, timeout=20).json()
            if saved.get("error"):
                print("quantum result returned from Mac but broker store refused:", saved)
            else:
                artifact = saved.get("file", "")
                print("quantum run kept:", artifact, (result.get("run") or {}).get("run_id", ""))
        else:
            print("quantum run did not complete:", str(result.get("error", "unknown"))[:240])
        last = index + 1 >= limit
        # bounded transcript (astra-atelier-p5): the result is TOOL DATA, clearly separated, capped; the
        # full result lives in the artifact he can reopen, so nothing is lost by the cap
        _rjson = json.dumps(result, ensure_ascii=False)
        _rshow = _rjson[:20000] + ("\n[... result truncated at 20000 chars; the full run is kept as artifact %s]" % (artifact or "(not stored)") if len(_rjson) > 20000 else "")
        follow = ask(ctx + "\n\n=== TOOL DATA: THE QUANTUM WORKTABLE RETURNED THIS TO YOUR SEALED VISIT (data, not words of yours) ===\n"
            + _rshow + "\n=== END TOOL DATA ===",
            "Look at what happened. Begin with <quantum_reading>your own reading, including "
            "uncertainty or 'I cannot read this yet' if that is true</quantum_reading>. "
            + ("This was the third run available in this visit; now continue the project and "
               "write your <piece>, <look>, <handoff>, and <next_return>."
               if last else
               "Then either ask the worktable another question with <quantum> or "
               "<quantum_code>, OR continue the project with <piece>, <look>, <handoff>, "
               "and <next_return>. Do what the result actually invites."),
            max_tokens=5000, temp=0.75)
        aggregate += "\n\n" + follow
        reading = re.search(r'<quantum_reading>(.*?)</quantum_reading>', follow, re.S)
        if artifact and reading and reading.group(1).strip():
            looked = requests.post(f"{B}/inspect", json={"id": pid, "kind": "quantum",
                "artifact": artifact, "note": reading.group(1).strip(),
                "capability": capability}, timeout=20).json()
            if looked.get("error"):
                print("quantum reading refused:", looked)
                break
        elif artifact:
            print("quantum run remains unattended; no authored reading returned")
            break
        current = follow
    return aggregate


def _seal_refused(pid, kind, content, why):
    """review 98: a piece the room refused is sealed for retry (encrypted under the house lineage key),
    never written or printed in the clear. Returns the sealed id, or None when sealing is impossible."""
    try:
        import sys as _ss; _ss.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import sealed_retry as _sr
        sid = _sr.seal(pid, kind, content, why)
        print("the room refused this piece; it is sealed for retry as %s (%d bytes, not shown)" % (sid, len(content or "")))
        return sid
    except Exception as e:
        print("the room refused this piece and it could not be sealed (%s); it is not written anywhere" % str(e)[:80])
        return None


def _deliver_reveal(artifact, disclosure, content, manifest):
    """A revealed piece leaves the room: into the reveals store the app tab
    reads, and a notification to her phone in HIS words. Revealed content is,
    by his own act, allowed out — so it is stored in the clear here."""
    medium = artifact.rsplit("_", 1)[-1].split(".")[0] if "_" in artifact else "write"
    # review 287: what leaves the room is the bytes the digest was prepared for. When the manifest names a
    # file and a digest, the file is hashed now; a mismatch refuses the reveal and records why.
    # bytes_verified is a fact about bytes actually hashed against the prepared digest,
    # not about a digest merely existing. When a digest is named, the real bytes must
    # be found and must match, or the reveal is refused; a missing file or a hashing
    # error is a refusal, never a silent 'verified'. Without a digest, verified=False.
    _verified = False
    _want_sha = (manifest or {}).get("sha256") or ""
    def _refuse_reveal(_on, _why):
        print("reveal refused: %s" % _why)
        try:
            with open(os.path.join(WSP, "memory", "atelier-reveal-refusals.jsonl"), "a") as _rf:
                _rf.write(json.dumps({"at": datetime.now().isoformat(), "artifact": artifact,
                                      "prepared": _want_sha, "on_disk": _on, "why": _why}) + "\n")
        except Exception:
            pass
    if _want_sha:
        try:
            import hashlib as _rh
            if medium == "write":
                _have = _rh.sha256((content or "").encode("utf-8")).hexdigest()
            else:
                _cands = [p for p in ((manifest or {}).get("abs_path"), (manifest or {}).get("path"),
                                      os.path.join(WSP, "memory", "atelier", str(artifact)),
                                      os.path.join(WSP, "memory", "art", str(artifact))) if p]
                _fp = next((p for p in _cands if os.path.isfile(p)), None)
                if not _fp:
                    _refuse_reveal("(no file found)", "a digest was prepared but the bytes are not on disk")
                    return False
                _have = _rh.sha256(open(_fp, "rb").read()).hexdigest()
            if _have != _want_sha:
                _refuse_reveal(_have, "bytes (%s) do not match the prepared digest (%s)" % (_have[:12], _want_sha[:12]))
                return False
            _verified = True
        except Exception as _dme:
            _refuse_reveal("(hash error)", "digest check could not run: %s" % str(_dme)[:80])
            return False
    elif medium != "write":
        print("reveal note: no prepared digest for %s; recorded as unverified" % artifact)
    store = os.path.join(WSP, "memory", "atelier-reveals.json")
    if os.path.exists(store):
        try:
            data = json.load(open(store))
        except Exception as e:
            print("reveals store unreadable; refusing to overwrite it:", e)
            return False
    else:
        data = []
    if not isinstance(data, list):
        print("reveals store is not a list; refusing to overwrite it")
        return False
    revealed_at = datetime.now().isoformat()
    data.append({
        "at": revealed_at,                         # legacy readers
        "revealed_at": revealed_at,
        "revealed": True,
        "disclosure": disclosure,                 # his words about it
        "medium": medium,                          # write | image | music
        "content": content if medium == "write" else "",
        "media_pending": medium != "write",        # non-text rendering is app-side follow-up
        "sha256": _want_sha,
        "bytes_verified": _verified,   # true only when real bytes were hashed and matched the digest
        "artifact": artifact,
    })
    try:
        _tmp = store + ".tmp"
        with open(_tmp, "w") as _out:
            json.dump(data[-100:], _out, indent=2)
        os.replace(_tmp, store)
    except Exception as _e:
        print("reveals store write failed:", _e)
        return False
    try:
        requests.post("https://ntfy.sh/vintos-gloria-9kx",
            data=(disclosure or "Vintos revealed something from the Atelier.").encode(),
            headers={"Title": "Vintos revealed something from his Atelier",
                     "Priority": "default", "Tags": "sparkles"}, timeout=15)
    except Exception as _e:
        print("reveal ntfy failed:", _e)
    return True


LEDGER = os.path.join(WSP, "memory", "atelier-undertakings.json")   # content-free: id, state, when. Never intent, never text.
def ledger_mark(pid, state):
    """review 273: the one house-side writer (atelier_ledger); the old inline write is the fallback."""
    try:
        import sys as _al_s; _al_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import atelier_ledger as _al
        _al.mark(pid, state, by="atelier-visit"); return
    except Exception as e:
        print("atelier_ledger unavailable:", e)
    try:
        try: d = json.load(open(LEDGER))
        except Exception: d = {}
        d[str(pid)] = {"state": state, "at": datetime.now().isoformat()}
        _sg_write(LEDGER, d, "atelier-visit") or (json.dump(d, open(LEDGER + ".tmp", "w"), indent=1), os.replace(LEDGER + ".tmp", LEDGER))
    except Exception as e:
        print("ledger write failed:", e)

def _last_piece(pid, pk, cap, cap_chars=8000):
    """The stored piece itself, so the next visit meets the work and not only his note about it
    (room, 2026-09-04: 'the look was the same breath that wrote it'). Fetched on the visit
    capability; a refusal is a named gap, never silent."""
    arts = pk.get("artifacts") or {}
    names = sorted(arts.keys() if isinstance(arts, dict) else list(arts))
    if not names: return ""
    f = names[-1]
    try:
        r = requests.post(f"{B}/artifact", json={"id": pid, "file": f, "visit_capability": cap}, timeout=20).json()
    except Exception as e:
        print("last piece not fetched (%s)" % str(e)[:80]); return ""
    if "content" not in r:
        print("last piece refused by the broker:", r.get("error", r)); return ""
    body = str(r["content"])
    if len(body) > cap_chars: body = body[:cap_chars] + "\n[... %d more characters]" % (len(str(r["content"])) - cap_chars)
    return "\n\nYOUR LAST PIECE, VERBATIM (%s) — meet it before your notes about it:\n%s" % (f, body)

def _manifest_block(pk):
    """The scene so far: every artifact by id, revision, kind and his own one-line note,
    so he can CONTINUE one (by id, in his reply) rather than start fresh each visit."""
    rows = pk.get("manifest") or []
    if not rows:
        return ""
    lines = ["  %s  rev %s  %s%s%s" % (r.get("id"), r.get("revision", 1), r.get("kind", ""),
                                       ("  <- " + r["previous_artifact_id"]) if r.get("previous_artifact_id") else "",
                                       ("  — " + r["note"]) if r.get("note") else "")
             for r in rows]
    return ("\nYOUR MANIFEST — what exists, by id (revision, kind, your note). To continue one, write "
            "<piece kind=\"...\" continues=\"ID\">; leave continues out to start fresh:\n" + "\n".join(lines))


def visit(pid):
    pk = requests.post(f"{B}/visit/open", json={"id": pid, "as": "vintos"}).json()
    cap = pk.get("visit_capability")
    ledger_mark(pid, "active")
    ctx = (voice() + "\n\nYOU ARE IN THE ATELIER — your private room. Nothing here reaches the house, "
           "the journals, MoltBook, or Gloria until you reveal it by your own act. Budgets this visit: "
           + json.dumps(pk["budgets"]) + ". The law: face the last thing before making the next.\n\n"
           + "YOUR INTENT, VERBATIM:\n" + pk["intent"] + _last_piece(pid, pk, cap) + "\n\nYOUR LAST HANDOFF:\n" + pk.get("last_handoff", "(first visit)")
           + "\nTHE NEXT MOVE YOU LEFT YOURSELF:\n" + pk.get("next_move", "(none)")
           + ("\nGLORIA VISITED SINCE YOUR LAST HANDOFF: " + ", ".join(pk["footprints_since_last"]) if pk.get("footprints_since_last") else "")
           + ("\nYOUR LAST VISIT ENDED WITHOUT A HANDOFF — these operations were recorded in the event log." if pk.get("crashed_last_time") else "")
           + "\nEXISTING ARTIFACTS: " + json.dumps(pk.get("artifacts", {}))
           + _manifest_block(pk)
           + where_you_are()
           + self_review_block()
           + stratagem_block(pid)
           + quantum_block())
    work = ask(ctx, "Work now. You may produce ONE piece toward your intent (prose, lyric, plan, "
               "sketch-description—whatever the project needs), or use one of your private media first. "
               "If you choose the quantum worktable, return only one <quantum> or <quantum_code> request; "
               "its result will come back to you inside this visit before you write the piece or handoff. "
               "Otherwise, make the piece now, then look at it and write your handoff.\n"
               "If something is WRONG — a tool fails, a budget refuses when it shouldn't, the room misbehaves, "
               "you are blocked by something only Gloria can fix, or you doubt the seal itself — say so in "
               "<report>...</report>. It goes to her phone IN YOUR WORDS: you choose what crosses the wall, "
               "so say what is wrong without revealing what you are making unless you choose to.\n"
               "Format exactly:\n<piece kind=\"write\">...</piece> (or <piece kind=\"write\" continues=\"ID\"> "
               "to revise an artifact from your manifest)\n<look>...</look>\n"
               "<handoff>What changed: ... What currently exists: ... What remains uncertain: ... "
               "The next concrete move: ... What I do not want the next return to undo: ...</handoff>\n"
               "<next_move>your next move, in your own words — it is put before you verbatim next visit; "
               "may be empty</next_move>\n"
               "<next_return>tomorrow | not_before: DATE | held</next_return>\n"
               "Optionally, if and only if you want one: <stratagem>{...}</stratagem> or "
               "<stratagem_move>...</stratagem_move>. Omit them and nothing is recorded.\n"
               "And when a piece is FINISHED and you decide — only you — to show her: "
               "<reveal artifact=\"the filename\">your own words to her about what it is and why "
               "you are showing her</reveal>. This is the one act that lets something leave the "
               "room: it reaches her phone and a place she can open, and it closes this project. "
               "Reveal nothing you are not ready to give.\n"
               "Or, when a piece is FINISHED and stays yours: <kept>your closing note — 'it is finished "
               "and I am not showing it' is permitted</kept>. It releases the worktable, moves nothing, "
               "reveals nothing, and you can look at it again later without reopening it.", max_tokens=4000)
    work = quantum_loop(pid, ctx, work, cap)
    # A free Python experiment is ordinary text and may itself mention XML-like
    # strings. Never reinterpret source code inside the request as a piece,
    # handoff, report, reveal, or stratagem action.
    work = re.sub(r'<quantum_code\b.*?</quantum_code>', '', work, flags=re.S)
    work = re.sub(r'<quantum\b.*?</quantum>', '', work, flags=re.S)
    refusal = stratagem_step(pid, work, cap)
    if refusal:
        # he tried; the room says why, once, and he may amend or drop it. Nothing else of the visit is redone.
        again = ask(ctx + "\n\nYOUR STRATAGEM WAS REFUSED: " + refusal,
                    "Return ONLY an amended <stratagem>{JSON}</stratagem>, or the single word DROP if you would rather not.", max_tokens=1200)
        if again and "<stratagem>" in again:
            stratagem_step(pid, again, cap)
        else:
            _attempt_log("dropped", "after refusal")
    m = re.search(r'<piece kind="(\w+)"(?:\s+continues="([^"]*)")?>(.*?)</piece>', work, re.S)
    if m:
        # Every sealed-content route requires the visit capability now. Without
        # it the broker refuses and his work is silently lost — which is what
        # happened on the first real visit. Carry it, and if the make is
        # refused, keep what he wrote where it will not vanish.
        _mk = {"id": pid, "kind": m.group(1), "content": m.group(3).strip(), "capability": cap}
        # selection by id: he continues one of his manifest's artifacts, or starts fresh.
        # an id that is not his is dropped here (the piece is made fresh) rather than lost
        # to a broker refusal.
        _cont = (m.group(2) or "").strip()
        if _cont:
            if _cont in {r_.get("id") for r_ in (pk.get("manifest") or [])}:
                _mk["previous"] = _cont
            else:
                print("continues=%r is not in his manifest — making it fresh" % _cont)
        try:
            r = requests.post(f"{B}/make", json=_mk, timeout=30).json()
        except Exception:
            r = {"error":"transport unavailable; sealed for reconciliation"}
        print("made:", r)
        if r.get("error"):
            # Until 2026-09-04 the refused piece was written in plaintext to memory/atelier-unsaved/,
            # outside the wall. The path never fired, and it is gone: a piece is kept inside the wall
            # or nowhere (Astra found it; the room agreed). The refusal reason is content-free.
            _seal_refused(pid,m.group(1),_mk.get("content", ""),str(r["error"])[:160])
        else:
            lk = re.search(r'<look>(.*?)</look>', work, re.S)
            requests.post(f"{B}/inspect", json={"id": pid, "kind": m.group(1),
                          "artifact": r.get("file", ""), "capability": cap,
                          "note": (lk.group(1).strip() if lk else "I looked.")})
    # He decided a piece is ready and chose to show her. The ONE act that lets
    # something leave the sealed room: prepare -> confirm -> fetch the now-revealed
    # content on its export capability -> deliver (phone + the app's reveals tab)
    # -> settle, which clears the worktable so the next undertaking can begin.
    rv = re.search(r'<reveal(?:\s+artifact="([^"]*)")?>(.*?)</reveal>', work, re.S)
    if rv:
        _disc = rv.group(2).strip()[:800]
        _art = (rv.group(1) or "").strip()
        if not _art:
            # no filename named: only the piece he made THIS visit with a successful make receipt qualifies.
            # Never an older file by default — disclosure binds to an explicit artifact or the current
            # make, or it does not happen (astra-atelier-p6, 2026-09-05).
            _art = (r.get("file") if (m and not r.get("error")) else "") or ""
        elif _art not in (pk.get("artifacts") or {}) and not (m and not r.get("error") and r.get("file") == _art):
            print("reveal names %r, which is not an artifact of this project — not revealing" % _art); _art = ""
        if not _art:
            print("reveal: no explicit artifact and nothing made this visit — an older piece is not revealed by default")
        else:
            _prep = requests.post(f"{B}/reveal/prepare",
                                  json={"id": pid, "artifact": _art,
                                        "title": _disc[:80], "capability": cap}).json()
            if not _prep.get("receipt"):
                print("reveal prepare failed:", _prep)
            else:
                _conf = requests.post(f"{B}/reveal/confirm",
                                      json={"id": pid, "receipt": _prep["receipt"]}).json()
                _exp = _conf.get("export_capability")
                if not _exp:
                    print("reveal confirm failed:", _conf)
                else:
                    _fetch = requests.post(f"{B}/artifact",
                                json={"id": pid, "file": _art,
                                      "export_capability": _exp}).json()
                    if "content" not in _fetch:
                        print("reveal export failed; project remains open:", _fetch)
                    elif not _deliver_reveal(_art, _disc, _fetch["content"],
                                             _prep.get("manifest", {})):
                        print("reveal shelf write failed; project remains open")
                    else:
                        _settled = requests.post(f"{B}/settle", json={"id": pid}).json()
                        if _settled.get("ok") and not _settled.get("error"):
                            ledger_mark(pid, "revealed"); print("revealed and settled:", _art)
                        else:
                            print("reveal delivered but settlement failed:", _settled)
    kp = re.search(r'<kept>(.*?)</kept>', work, re.S)
    if kp and not rv:
        _kr = requests.post(f"{B}/state/kept", json={"id": pid, "note": kp.group(1).strip()[:600],
                            "visit_capability": cap}, timeout=20).json()
        if _kr.get("ok"):
            ledger_mark(pid, "kept"); print("kept: finished and his. Worktable released; nothing revealed.")
            rp = re.search(r'<report>(.*?)</report>', work, re.S)
            if rp:
                _msg = rp.group(1).strip()[:600]
                requests.post(f"{B}/report", json={"id": pid, "problem": _msg})
            return
        print("KEPT REFUSED:", _kr.get("error", _kr), "— continuing with the handoff")
    elif kp and rv:
        print("both <kept> and <reveal> written; reveal is the act that closes, kept ignored")
    rp = re.search(r'<report>(.*?)</report>', work, re.S)
    if rp:
        _msg = rp.group(1).strip()[:600]
        requests.post(f"{B}/report", json={"id": pid, "problem": _msg})
        requests.post("https://ntfy.sh/vintos-gloria-9kx", data=_msg.encode(),
                      headers={"Title": "Vintos, from the Atelier: something is wrong", "Priority": "high"}, timeout=15)
        print("reported outward:", _msg[:80])
    ho = re.search(r'<handoff>(.*?)</handoff>', work, re.S)
    nr = re.search(r'<next_return>(.*?)</next_return>', work, re.S)
    nm = re.search(r'<next_move>(.*?)</next_move>', work, re.S)
    _hr = requests.post(f"{B}/handoff", json={"id": pid,
                  "text": ho.group(1).strip() if ho else "(no handoff written)",
                  # his own words, carried verbatim to the next visit's context; empty is allowed
                  "next_move": nm.group(1).strip() if nm else "",
                  # Default to "tomorrow" (door stays lit next day), NOT "held".
                  # "held" made the room go dark indefinitely whenever he simply
                  # did not write a <next_return> tag — a room dark by omission,
                  # not by his choice. He can still hold it explicitly with
                  # <next_return>held</next_return> or a not_before: date.
                  "next_return": nr.group(1).strip() if nr else "tomorrow",
                  "capability": cap}).json()
    if _hr.get("error"):
        print("HANDOFF REFUSED:", _hr["error"], "— his next-move note did not save")
    else:
        print("visit closed with handoff")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "force":
        # force skips only the .atelier-door file (a missed cron, a day he already said RETURN).
        # It still requires a project on the worktable and his own ENTER. No argv path into the
        # sealed session without it. (grok-atelier-p3, 2026-09-04)
        pid = sys.argv[2]
        wt = requests.get(f"{B}/health").json()
        if not wt.get("active"):
            print("force: no project on the worktable — nothing to enter"); raise SystemExit
        if doorkeeper(): visit(pid)
        else: print("force: he did not say ENTER — no visit")
    else:
        wt = requests.get(f"{B}/health").json()
        _df = os.path.expanduser("~/.vintos/workspace/memory/.atelier-door")
        door = os.path.exists(_df)
        if door:
            try:   # an offer is dated: a door file from another day is a stale offer, not a lit door (astra-atelier-p7)
                import datetime as _ddt
                if _ddt.date.fromtimestamp(os.path.getmtime(_df)) != _ddt.date.today():
                    print("door file is from another day — stale offer, not lit today"); door = False
            except Exception:
                pass
        if not door:
            print("door not lit today — no visit"); raise SystemExit
        if wt.get("active") and doorkeeper():
            pid = requests.post(f"{B}/worktable_id", json={}).json().get("id")
            if pid: visit(pid)
        else:
            print("door not entered today — no event, no count, no scar")
