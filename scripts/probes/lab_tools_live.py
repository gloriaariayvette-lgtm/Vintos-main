#!/usr/bin/env python3
"""Read-only: why each of his Lab's tools is or is not running, from Aegis itself (22 October).

Prints, and writes nothing:
  1. the Lab config as it is on Aegis (the file, merged over the code's defaults), switch by switch
  2. every key, tool and environment the tools need: present or not, and a key file's mode; never its contents
  3. whether the Mac answers (one status call, the session's own)
  4. what each source and instrument actually did in the last 7 days: runs, failures, and the last error
  5. the daily session's outcomes over the last 14 days (held_mac_unavailable and the rest)
"""
import collections, json, os, shutil, stat, sys, time

WS = os.path.expanduser("~/.vintos/workspace")
sys.path.insert(0, os.path.join(WS, "scripts"))
LAB = os.path.join(WS, "memory", "chemistry-lab")
H = os.path.expanduser


def present(path, key=False):
    path = H(path)
    if not path or not os.path.exists(path):
        return "MISSING (%s)" % path
    if key:
        mode = stat.S_IMODE(os.stat(path).st_mode)
        return "present, mode %o%s" % (mode, "" if mode == 0o600 else "  <- the code requires 600")
    return "present"


def tail(path, nbytes=40_000_000):
    rows = []
    try:
        with open(path, errors="replace") as f:
            f.seek(max(0, os.path.getsize(path) - nbytes)); f.readline()
            for line in f:
                try: rows.append(json.loads(line))
                except ValueError: pass
    except OSError:
        pass
    return rows


def ts(row):
    at = str(row.get("at") or row.get("fetched_at") or row.get("timestamp") or "")[:19]
    try: return time.mktime(time.strptime(at, "%Y-%m-%dT%H:%M:%S"))
    except ValueError: return None


print("== 1. Lab config on Aegis (file over code defaults)")
try:
    import chemistry_lab as C
    cfg = C.config()
    raw = json.load(open(C.CONFIG)) if os.path.exists(C.CONFIG) else {}
    for k in ("enabled", "campaigns", "evo2_enabled", "atlas_evo2_enabled", "evo2_every_n_cycles", "alphagenome_key_file",
              "alphagenome_python", "allow_public_database_reads", "divergence_enabled"):
        print("  %-28s %-28r %s" % (k, cfg.get(k), "(set in config.json)" if k in raw else "(code default)"))
    for k in ("alphagenome_key_file", "alphagenome_python"):
        if cfg.get(k): print("    %s -> %s" % (k, present(cfg[k], key=k.endswith("key_file"))))
    print("  LLM model:", getattr(C, "LLM_MODEL", "?"))
except Exception as exc:
    print("  could not read the Lab config:", exc)

print("\n== 2. What the tools need")
need = {
    "Mac (chemistry session) config ~/.vintos/chemistry-mac.json": ("~/.vintos/chemistry-mac.json", False),
    "Mac plugin relay ~/.vintos/plugin-relay.json": ("~/.vintos/plugin-relay.json", True),
    "quantum lab (Atelier) ~/.vintos/quantum-lab.json": ("~/.vintos/quantum-lab.json", False),
    "NVIDIA NIM key": ("~/.config/vintos/nvidia-nim.key", True),
    "nvmolkit venv python": ("~/.vintos/tools/nvmolkit-venv/bin/python", False),
    "Pfam for HMMER": ("~/.vintos/tools/chemistry-lab/pfam/Pfam-A.hmm.h3m", False),
    "connector urls": ("~/.vintos/connector-urls.json", False),
}
for label, (path, key) in need.items():
    print("  %-62s %s" % (label, present(path, key)))
print("  %-62s %s" % ("hmmscan on PATH", shutil.which("hmmscan") or "MISSING"))
try:
    names = sorted(json.load(open(H("~/.vintos/connector-urls.json"))).keys())
    print("  connector-urls.json names:", ", ".join(names))
except Exception as exc:
    print("  connector-urls.json not read:", type(exc).__name__)
try:
    import plugin_catalog as P
    conns = P.instructions("lab")["connectors"]
    print("  Lab connectors and whether the code sees them enabled:",
          ", ".join("%s=%s" % (n, r.get("enabled", True)) for n, r in sorted(conns.items())))
except Exception as exc:
    print("  plugin catalog not read:", exc)
try:
    import claude_connector_catalog as CC
    print("  Claude-relay connectors offered to the Lab:", CC.prompt_instructions("lab")[:600].replace("\n", " "))
except Exception as exc:
    print("  Claude connector catalog not read:", exc)
try:
    import chemistry_lab as C
    st = C.tools_status()
    print("  tools_status:", json.dumps({k: (v.get("state") or v.get("available")) if isinstance(v, dict) else v
                                          for k, v in st.items()})[:1500])
except Exception as exc:
    print("  tools_status not read:", exc)

print("\n== 3. Does the Mac answer?")
try:
    import chemistry_mac as M
    s = M.status()
    print("  ok:", s.get("ok"), "| experiments:", s.get("experiments"), "| error:", str(s.get("error") or "")[:200])
except Exception as exc:
    print("  status call failed:", exc)
try:
    import plugin_gateway as G
    print("  plugin relay status:", str(getattr(G, "status", lambda: "no status function")())[:300])
except Exception as exc:
    print("  plugin relay status not read:", exc)

week = time.time() - 7 * 86400
print("\n== 4. Last 7 days, by source and instrument")
use = collections.Counter(); bad = collections.Counter(); last_err = {}
for r in tail(os.path.join(LAB, "source-receipts.jsonl")):
    t = ts(r)
    if t and t >= week:
        use[str(r.get("source"))] += 1
for r in tail(os.path.join(LAB, "faults.jsonl")):
    t = ts(r)
    if t and t >= week:
        k = str(r.get("stage") or r.get("phase") or "?")
        bad[k] += 1; last_err[k] = str(r.get("error") or r.get("message") or r.get("detail") or "")[:160]
for r in tail(os.path.join(LAB, "notebook.jsonl")):
    t = ts(r)
    if not t or t < week: continue
    for key in ("plugin_query", "instrument_query"):
        q = r.get(key) or (r.get("inquiry") or {}).get(key)
        if isinstance(q, dict) and r.get("kind") in ("inquiry", "source_read", "additional_source"):
            use["%s:%s" % (key.split("_")[0], q.get("plugin") or q.get("skill"))] += 1
    if r.get("kind") in ("source_unavailable", "plugin_unavailable", "ask_proposed"):
        k = "unavailable:%s" % (r.get("source") or r.get("plugin") or "?")
        bad[k] += 1; last_err[k] = str(r.get("why") or r.get("reason") or r.get("error") or "")[:160]
print("  used:", dict(use.most_common()))
print("  failures by stage:")
for k, n in bad.most_common(25):
    print("   %4d %-34s last: %s" % (n, k, last_err.get(k, "")))
try:
    import lab_instruments as I
    runs = json.load(open(I.LEDGER))
    print("  instrument-runs ledger:", json.dumps(runs)[:600])
except Exception as exc:
    print("  instrument-runs ledger not read:", type(exc).__name__)

print("\n== 5. The daily session, last 14 days")
fort = time.time() - 14 * 86400
sess = [r for r in tail(os.path.join(LAB, "sessions.jsonl")) if (ts(r) or 0) >= fort]
print("  outcomes:", dict(collections.Counter(r.get("state") for r in sess)))
for r in sess[-6:]:
    print("   ", str(r.get("at", ""))[:16], r.get("state"), (r.get("plan") or {}).get("experiment"), str(r.get("detail") or "")[:120])
