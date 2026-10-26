#!/usr/bin/env python3
"""A source that did not answer this time is a wait, not a fault.

26 October: the day's Lab run asked UniProt for O43511, the TLS connection closed before an answer ("TLS/SSL
connection has been closed (EOF)"), and the whole run stopped as held_fault - the fault sweep's "a Lab run stopped".
Now a transport failure (TLS EOF, reset, timeout, temporary DNS, HTTP 429/5xx) is asked again a bounded number of
times; still failing, the run waits with its plan kept and is tried again later without planning anew. A 404, a
bad accession or a missing record is UniProt's answer and is not retried.

Scratch HOME and Lab stores; UniProt, the Mac, the planner and the reader are stubs; every socket is refused and
nothing sleeps."""
import contextlib, http.client, importlib.util, io, json, os, socket, ssl, sys, tempfile, time, types
from urllib.error import HTTPError, URLError

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-source-transient-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_CHEMISTRY_MAC_CONFIG"] = os.path.join(HOME, "chemistry-mac.json")
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no(sock, *a, **k):
    if sock.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

import lab_sources as LS

# ---- 1. what counts as passing
def http_error(code): return HTTPError("https://rest.uniprot.org/x", code, "x", {}, io.BytesIO(b""))
def wrapped(inner):
    try:
        try: raise inner
        except Exception as e: raise RuntimeError("source_query_unavailable") from e
    except Exception as e: return e
the_26th = URLError(ssl.SSLZeroReturnError(6, "TLS/SSL connection has been closed (EOF) (_ssl.c:1000)"))
transient = {"the 26 October TLS EOF": the_26th,
             "SSL EOF": URLError(ssl.SSLEOFError(8, "EOF occurred in violation of protocol")),
             "connection reset": ConnectionResetError(104, "Connection reset by peer"),
             "reset inside URLError": URLError(ConnectionResetError(104, "reset")),
             "timeout": TimeoutError("timed out"), "socket timeout in URLError": URLError(socket.timeout("timed out")),
             "temporary DNS failure": URLError(socket.gaierror(socket.EAI_AGAIN, "Temporary failure in name resolution")),
             "remote disconnected": http.client.RemoteDisconnected("Remote end closed connection"),
             "HTTP 429": http_error(429), "HTTP 503": http_error(503), "HTTP 500": http_error(500), "HTTP 502": http_error(502),
             "wrapped by the source door": wrapped(the_26th)}
permanent = {"HTTP 404": http_error(404), "HTTP 400": http_error(400), "HTTP 403": http_error(403),
             "a bad accession": ValueError("exact sourced UniProt accession required"),
             "a missing record": ValueError("UniProt returned no record for O43511"),
             "certificate failure": URLError(ssl.SSLCertVerificationError(1, "certificate verify failed")),
             "unknown host": URLError(socket.gaierror(socket.EAI_NONAME, "Name or service not known"))}
for name, exc in transient.items():
    check("transient: %s" % name, LS.transient_source_error(exc) is True)
for name, exc in permanent.items():
    check("not retried: %s" % name, LS.transient_source_error(exc) is False)

# ---- 2. bounded retry
slept, calls = [], []
def flaky(fails, exc):
    def call():
        calls.append(1)
        if len(calls) <= fails: raise exc
        return "answered"
    return call
calls.clear(); slept.clear()
check("a transient failure is asked again and then answers",
      LS.with_transient_retry(flaky(2, the_26th), delays=(3, 10), sleep=slept.append) == "answered"
      and len(calls) == 3 and slept == [3, 10], (calls, slept))
calls.clear(); slept.clear()
try: LS.with_transient_retry(flaky(99, the_26th), delays=(3, 10), sleep=slept.append); out = None
except Exception as e: out = e
check("retries are bounded: three tries, then the last transient failure is raised", out is the_26th and len(calls) == 3,
      (out, calls))
calls.clear(); slept.clear()
try: LS.with_transient_retry(flaky(99, http_error(404)), delays=(3, 10), sleep=slept.append); out = None
except Exception as e: out = e
check("a permanent failure is raised at once, never retried", isinstance(out, HTTPError) and len(calls) == 1 and slept == [])

# ---- 3. the protein door
mac = load("chemistry_mac_transient", os.path.join(REPO, "scripts", "chemistry_mac.py"))
check("the Mac config is scratch", mac.CONFIG.startswith(HOME), mac.CONFIG)
mac._sleep = slept.append
def record(acc, seq="ACDEFGHIKL"):
    return {"primaryAccession": acc, "sequence": {"value": seq, "length": len(seq)}}
def resolver(fails, exc):
    def r(acc):
        calls.append(acc)
        if len(calls) <= fails: raise exc
        return record(acc), {"provider": "UniProtKB", "accession": acc, "receipt_id": "rcpt"}
    return r
calls.clear(); slept.clear()
p = mac.prepare_protein({"target_accession": "O43511"}, resolver=resolver(1, the_26th))
check("one TLS EOF, then UniProt answers: the protein is bound to its sequence",
      p.get("ok") and p["sequence_request"] and len(calls) == 2, p)
calls.clear(); slept.clear()
before = time.time()
p = mac.prepare_protein({"target_accession": "O43511"}, resolver=resolver(99, the_26th))
check("still unreachable: a wait with a retry time, not a fault",
      p.get("ok") is False and p.get("waiting") is True and p.get("refused") == "source_waiting"
      and float(p.get("retry_at") or 0) >= before + mac.SOURCE_WAIT_SECONDS - 1 and len(calls) == 3
      and "nothing was sent" in p.get("error", ""), p)
calls.clear(); slept.clear()
p = mac.prepare_protein({"target_accession": "O43511"}, resolver=resolver(99, http_error(404)))
check("a 404 is UniProt's answer: refused once, no wait", p.get("refused") == "sequence_unavailable"
      and not p.get("waiting") and len(calls) == 1 and slept == [], p)
calls.clear()
p = mac.prepare_protein({"target_accession": "O43511"},
                        resolver=lambda acc: (calls.append(acc), (None, {"provider": "UniProtKB"}))[1])
check("no record for the accession: refused once, no wait", p.get("refused") == "sequence_unavailable"
      and not p.get("waiting") and len(calls) == 1, p)
sent = []
w = mac.run("protein", {"target_accession": "O43511"}, 64, resolver=resolver(99, the_26th),
            transport=lambda body: sent.append(body) or {"ok": True})
check("a waiting protein run sends nothing to the bench", w.get("waiting") and sent == [], (w, sent))
sys.modules.pop("chemistry_mac_transient", None)

# ---- 4. the scheduled session: a wait, its plan kept, tried again without planning anew
sys.modules["line_prospect"] = types.SimpleNamespace(prospect=lambda: None)
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
check("the Lab's stores are scratch", lab.ROOT.startswith(HOME), lab.ROOT)
lab.set_enabled(True)
import chemistry_probe as probe_mod
probe_mod.AEGIS_PROBES = {"openmm": {"marker": "stepped_energy", "entry": "fake"}}
probe_mod.probe_aegis = lambda name: probe_mod._receipt(name, "aegis", "smoke_passed",
                                                         evidence={"exercised": "test-stub"}, source="test-stub")
check("instrument probes are stubbed and scratch", probe_mod.PROBES.startswith(HOME), probe_mod.PROBES)
RUNS = []
WAIT = {"ok": False, "refused": "source_waiting", "waiting": True, "requested_accession": "O43511",
        "error": "UniProt did not answer for O43511 (transient, 3 tries): TLS EOF; nothing was sent, waiting"}
mode = {"wait": True}
def mac_run(experiment, parameters, shots):
    RUNS.append((experiment, dict(parameters), shots))
    if mode["wait"]: return dict(WAIT, retry_at=time.time() + 1800)
    return {"ok": True, "run_id": "RUN-OK", "result": {"lowest_energy": -1.0}}
mac_stub = types.SimpleNamespace(status=lambda: {"ok": True, "experiments": ["protein", "fold"]}, run=mac_run,
                                 reading=lambda run_id, text: {"ok": True})
sys.modules["chemistry_mac"] = mac_stub
@contextlib.contextmanager
def admitted(*a, **k): yield object()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
session = load("chemistry_session_transient", os.path.join(REPO, "scripts", "chemistry_session.py"))
PLANS = []
def _plan(context, experiments, lens, instruments=None, offered_entry_ids=None, **leans):
    PLANS.append(lens)
    return {"addressed_entry_ids": [], "experiment": "protein", "parameters": {"target_accession": "O43511"},
            "shots": 64, "question": "how does O43511 fold?", "why_this": "curiosity"}
session._plan = _plan
session._reading = lambda context, plan, result, grade=None, lens=None: {"reading": "r", "next_question": "n?"}
import failure_watch
check("the fault sweep reads the scratch sessions", failure_watch.LAB_SESSIONS == session.SESSIONS and failure_watch.LAB_SESSIONS.startswith(HOME), failure_watch.LAB_SESSIONS)

def st(): return json.load(open(session.SESSION_STATE))
lens0 = int((json.load(open(session.SESSION_STATE)) if os.path.exists(session.SESSION_STATE) else {}).get("lens_index", 0))
row = session.run()
check("UniProt unreachable: the session waits, it is not a fault", row["state"] == "waiting_for_source"
      and row["state"] not in failure_watch.LAB_FAILED and row.get("retry_at"), row)
check("the lens keeps its turn and the plan is kept", st().get("lens_index", 0) == lens0
      and st()["waiting_plan"]["plan"]["parameters"] == {"target_accession": "O43511"}
      and st()["waiting_plan"]["tries"] == 1, st())
check("the fault sweep does not report it", not any(o == "lab" for o, *_ in failure_watch.gather(__import__("datetime").datetime(2000, 1, 1))))

n_plans, n_runs = len(PLANS), len(RUNS)
row = session.run()
check("before its retry time: still waiting, nothing planned or sent", row["state"] == "waiting_for_source"
      and len(PLANS) == n_plans and len(RUNS) == n_runs, (row, PLANS, RUNS))

def due():
    s = st(); s["waiting_plan"]["retry_at"] = time.time() - 1; json.dump(s, open(session.SESSION_STATE, "w"))
due(); mode["wait"] = False
row = session.run()
check("after the wait: the same plan is tried again, not planned anew", row["state"] == "completed"
      and len(PLANS) == n_plans and RUNS[-1] == ("protein", {"target_accession": "O43511"}, 64)
      and row["plan"].get("carried_from"), (row.get("state"), PLANS, RUNS[-1:]))
check("and the wait is cleared, the lens advances", "waiting_plan" not in st() and st()["lens_index"] == (lens0 + 1) % len(session.LENSES),
      st())

# waiting is bounded too: a source still unreachable after MAX_SOURCE_WAITS holds is a fault
mode["wait"] = True
states = []
for _ in range(session.MAX_SOURCE_WAITS + 1):
    if "waiting_plan" in st(): due()
    states.append(session.run()["state"])
check("a source unreachable through every wait becomes a fault, said as one",
      states == ["waiting_for_source"] * session.MAX_SOURCE_WAITS + ["held_fault"] and "waiting_plan" not in st(), states)
last = [json.loads(l) for l in open(session.SESSIONS) if l.strip()][-1]
check("its detail says it waited", "after %d waits" % session.MAX_SOURCE_WAITS in last.get("detail", ""), last)

# ---- 5. an investigation step: a wait, not a failed step
import lab_investigations as LI
sys.modules["chemistry_mac"] = mac_stub; sys.modules["chemistry_probe"] = types.SimpleNamespace(record_run_attestation=lambda *a: None)
sys.modules["lab_tool_calls"] = types.SimpleNamespace(execution_request=lambda route, r: r)
LI.resolve = lambda r, steps: r
LI._gate = lambda inquiry: {}
try:
    LI.dispatch("experiment", {"experiment": "protein", "parameters": {"target_accession": "O43511"}, "shots": 64}, "q?", [])
    out = None
except Exception as e: out = e
check("an investigation's protein step waits (waiting_not_sent), it does not fail", isinstance(out, LI.SourceWaiting)
      and out.until > time.time(), repr(out))

check("nothing left this host", NET == [], NET)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
