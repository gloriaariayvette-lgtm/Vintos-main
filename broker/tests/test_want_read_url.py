#!/usr/bin/env python3
"""A want's step opens a link and reads its whole text (Gloria, 15 November 2026: he must be able to open links from
his wants' steps and his planner). His wants to read a paper in full could only be planned as web searches; they
found abstracts, were judged not done, reworded and dismissed. Now a read_url step goes through link_fetch (the
same safe door his letters use), keeps what it read as the step's evidence, and the completion judge is shown
READ IN FULL. Also: the provenance gaps left on 15 November - what her Watch face shows, and journal posts.

Every address, page, PDF, want and journal entry here is made up; scratch HOME; the transport and resolver are stubs;
requests and sockets are replaced, so nothing here can reach the network."""
import importlib.util, json, os, re, socket, subprocess, sys, tempfile, time, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-read-url-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.symlink(os.path.join(REPO, "scripts"), os.path.join(WS, "scripts"))      # the router imports from here
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
for k in ("VINTOS_ACTION_WANT_ID", "VINTOS_ACTION_ORGAN", "STEP_PARAMS", "STEP_WANT_ID", "STEP_ORIGINAL_WANT"):
    os.environ.pop(k, None)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
socket.getaddrinfo = no_network; socket.create_connection = no_network
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
def src(rel): return open(os.path.join(REPO, rel), encoding="utf-8").read()

import link_fetch as LF
import want_read_url as U
import action_provenance as AP
import want_contract as C
check("every store is a scratch one", U._mem().startswith(HOME) and AP._mem().startswith(HOME))

PUBLIC = lambda host: ["93.184.216.34"]
PRIVATE = lambda host: ["10.1.2.3"]
ASKED = []
def site(pages):
    def transport(url, headers, timeout, max_bytes):
        ASKED.append(url)
        if url not in pages: return 404, {}, b"", False
        status, hdrs, body = pages[url]
        body = body.encode() if isinstance(body, str) else body
        return status, hdrs, body[:max_bytes], len(body) > max_bytes
    return transport
def provenance():
    try: return [json.loads(l) for l in open(os.path.join(MEM, AP.LOG_NAME), encoding="utf-8")]
    except OSError: return []
def ledger():
    try: return [json.loads(l) for l in open(os.path.join(MEM, U.LEDGER), encoding="utf-8")]
    except OSError: return []

PAPER = "https://papers.example.org/fixture-attention-2031"
PDF = "https://papers.example.org/fixture-attention-2031.pdf"
BODY = "<html><body><h1>A made-up paper</h1><p>" + "Section one says a made-up thing. " * 200 + "</p></body></html>"

print("\n--- which link a step opens ---")
want = {"id": "w-fix01", "step_history": [
    {"step": 0, "capability": "web_search", "findings": "A synthesis.\nAddresses found: https://old.example.org/a"},
    {"step": 1, "capability": "web_search", "findings": "Another.\nAddresses found: https://new.example.org/b https://new.example.org/c"}]}
check("the step's own address first", U.pick_url({"url": PAPER}, "Current step goal: read https://x.example.org/n", "", want)[0] == PAPER)
check("then the first link in the step's goal",
      U.pick_url({}, "Previous steps...\nCurrent step goal: read https://goal.example.org/p fully", "https://w.example.org/w", want)[0]
      == "https://goal.example.org/p")
check("then the want itself", U.pick_url({}, "Current step goal: read it", "I want to read https://w.example.org/w in full", want)[0]
      == "https://w.example.org/w")
u, where = U.pick_url({}, "Current step goal: read it", "I want to read the paper", want)
check("then what its newest earlier step found", u == "https://new.example.org/b" and "step 2" in where, (u, where))
u, why = U.pick_url({}, "Current step goal: read it", "I want to read the paper", {"id": "w", "step_history": []})
check("no address anywhere: said, nothing made up", u == "" and why.startswith("no address"), why)

print("\n--- a page read in full is kept as the step's evidence, with its why ---")
ASKED.clear()
fetch = lambda url: LF.fetch(url, transport=site({PAPER: (200, {"content-type": "text/html"}, BODY)}), resolve=PUBLIC)
out = U.run({"url": PAPER}, "Current step goal: read the made-up paper in full", "w-fix01", mem=MEM, fetch=fetch)
check("findings begin READ IN FULL and name the kept file", isinstance(out, str) and out.startswith(U.FULL + ": " + PAPER)
      and "receipt: " in out, str(out)[:200])
kept = re.search(r"receipt:\s*(\S+)", out or "").group(1) if out else ""
check("the kept file is in the scratch store and holds the whole text", kept.startswith(MEM) and os.path.exists(kept)
      and open(kept).read().count("Section one says a made-up thing.") == 200, kept)
check("the findings carry the start of the text", "A made-up paper" in out)
p = provenance()[-1]
check("one provenance row: read_url, for that want, with the rule and the result",
      p["action"] == "read_url" and p["want_id"] == "w-fix01" and p["what"].startswith(U.FULL)
      and "public hosts only" in p["rule"] and "the step's own address" in p["rule"]
      and p["refs"].get("kind") == "fetched" and "read the made-up paper" in p["trigger"], p)
check("the ledger keeps the attempt", ledger()[-1]["result"] == U.FULL and ledger()[-1]["url"] == PAPER)
step = {"step": 0, "capability": "read_url", "findings": out, "receipt": {"kind": "file", "ref": kept}}
check("full_text_read counts it", U.full_text_read({"step_history": [step]}) == [{"url": PAPER, "file": kept}],
      U.full_text_read({"step_history": [step]}))
check("a kept file that is gone is not counted", U.full_text_read({"step_history": [dict(step, findings=out.replace(kept, kept + ".gone"))]}) == [])

print("\n--- a page past the cap is READ IN PART, never the full text ---")
big = lambda url: LF.fetch(url, max_bytes=500, transport=site({PAPER: (200, {"content-type": "text/html"}, BODY)}), resolve=PUBLIC)
part = U.run({"url": PAPER}, "Current step goal: read it", "w-fix02", mem=MEM, fetch=big)
check("READ IN PART, said with why", isinstance(part, str) and part.startswith(U.PART) and "only the start" in part, str(part)[:200])
check("not counted as the full text", U.full_text_read({"step_history": [{"capability": "read_url", "findings": part}]}) == [])

print("\n--- the safety rules are link_fetch's own, and an unreadable page says so ---")
for bad, resolve in (("http://127.0.0.1/admin", PUBLIC), ("https://inside.example.org/x", PRIVATE),
                     ("file:///etc/passwd", PUBLIC), ("https://user:pw@papers.example.org/x", PUBLIC),
                     ("https://papers.example.org:8443/x", PUBLIC), ("http://printer.local/", PUBLIC)):
    ASKED.clear(); n = len(provenance())
    got = U.run({"url": bad}, "Current step goal: read it", "w-fix03", mem=MEM,
                fetch=lambda url, r=resolve: LF.fetch(url, transport=site({}), resolve=r))
    check("refused without a connection: %s" % bad, got is False and ASKED == [] and ledger()[-1]["kind"] == "refused"
          and len(provenance()) == n + 1 and provenance()[-1]["what"].startswith(U.NOT), (got, ASKED, ledger()[-1]))
ASKED.clear()
redirects = {"https://a.example.org/%d" % i: (302, {"location": "https://a.example.org/%d" % (i + 1)}, "") for i in range(9)}
check("a redirect chain past the limit is refused",
      U.run({"url": "https://a.example.org/0"}, "", "w-fix03", mem=MEM,
            fetch=lambda url: LF.fetch(url, transport=site(redirects), resolve=PUBLIC)) is False
      and len(ASKED) == LF.MAX_REDIRECTS + 1, len(ASKED))
check("a redirect into a private host is refused at that hop",
      U.run({"url": PAPER}, "", "w-fix03", mem=MEM,
            fetch=lambda url: LF.fetch(url, transport=site({PAPER: (302, {"location": "http://192.168.1.9/"}, "")}),
                                       resolve=PUBLIC)) is False and ledger()[-1]["kind"] == "refused")
check("an HTTP failure is NOT READABLE with its status",
      U.run({"url": PAPER}, "", "w-fix03", mem=MEM, fetch=lambda url: LF.fetch(url, transport=site({}), resolve=PUBLIC)) is False
      and "404" in ledger()[-1]["why"])

print("\n--- a PDF is read with the reader, and is honestly not readable without one ---")
PDFBYTES = b"%PDF-1.7 made-up bytes"
pdf_site = site({PDF: (200, {"content-type": "application/pdf"}, PDFBYTES)})
got = U.run({"url": PDF}, "", "w-fix04", mem=MEM, fetch=lambda url: LF.fetch(url, transport=pdf_site, resolve=PUBLIC, pdf=None))
check("no PDF reader: NOT READABLE, and why", got is False and ledger()[-1]["result"] == U.NOT
      and "no PDF reader" in ledger()[-1]["why"], ledger()[-1])
reader = lambda body: "The made-up PDF's text, read whole." if body.startswith(b"%PDF") else ""
got = U.run({"url": PDF}, "", "w-fix04", mem=MEM, fetch=lambda url: LF.fetch(url, transport=pdf_site, resolve=PUBLIC, pdf=reader))
check("with a reader: READ IN FULL", isinstance(got, str) and got.startswith(U.FULL) and "read whole" in got, got)
check("the default reader is the Scholar's (the one his letters use)", "import scholar" in src("scripts/want_read_url.py")
      and "scholar.pdf_text" in src("scripts/want_read_url.py"))
check("no address: False, kept in the ledger, no fetch and no act recorded",
      (lambda n: U.run({}, "Current step goal: read it", "w-fix05", mem=MEM, fetch=no_network) is False
       and ledger()[-1]["kind"] == "no_address" and len(provenance()) == n)(len(provenance())))
check("a link written cut short is passed over for the whole one after it",
      U.pick_url({}, "Current step goal: read https://cut.example.org/pap\u2026 or https://whole.example.org/p", "", None)[0]
      == "https://whole.example.org/p")
struct = lambda url: {"fetched": True, "kind": "fetched", "text": "HEADER made-up", "structure": {"made": "up"}}
real_view = LF.structure_view; LF.structure_view = lambda s, *a: "HEADER made-up preview"
got = U.run({"url": PAPER}, "", "w-fix05", mem=MEM, fetch=struct); LF.structure_view = real_view
check("a structure file's preview is READ IN PART, never the full text", isinstance(got, str) and got.startswith(U.PART), got)
check("a fetch stand-in that raises is NOT READABLE, never raised to the spine",
      U.run({"url": PAPER}, "", "w-fix05", mem=MEM, fetch=lambda u: (_ for _ in ()).throw(OSError("made-up"))) is False)

print("\n--- the router: a capability, its params, its aliases, its step ---")
sys.modules["emoclaw_utils"] = types.SimpleNamespace(get_unfulfilled_wants=lambda *a, **k: [],
                                                      fulfill_want=lambda *a, **k: None,
                                                      mark_want_outreached=lambda *a, **k: None)
spec = importlib.util.spec_from_file_location("wants_router_read_url", os.path.join(REPO, "bin", "wants-router.py"))
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
check("the router's memory is the scratch one", W.MEMORY == MEM, W.MEMORY)
check("read_url is a router action, wrapped by the spine", "read_url" in W.ACTION_MAP and "_wrapped" in W.ACTION_MAP["read_url"].__name__)
check("it takes an optional url", W.validate_step_params("read_url", {"url": PAPER, "x": 1})[0] == {"url": PAPER})
check("it is in the one capability list", any(c.get("action") == "read_url" for c in W.CAPABILITIES))
W.llm_extract = lambda *a, **k: None
for w in ("I want to read the full poem I wrote last night", "I want to read the full journal entry again"):
    check("his own writing is not a link: %s" % w, W.route_want({"want": w}) != "read_url", W.route_want({"want": w}))
check("a want to read the full paper routes to it, not to email or read_memory",
      W.route_want({"want": "I want to read the full paper at %s" % PAPER}) == "read_url")
check("writing to an author is still email", W.route_want({"want": "I want to email the author about her paper"}) == "send_email")
router = src("bin/wants-router.py")
check("the planner's aliases reach it", '"read_link": "read_url"' in router and '"open_link": "read_url"' in router)
json.dump([{"id": "w-fix06", "want": "I want to read the made-up paper in full", "step_history": [
    {"step": 0, "capability": "web_search", "findings": "A synthesis.\nAddresses found: " + PAPER}]}], open(os.path.join(MEM, "current-wants.json"), "w"))
real_fetch = LF.fetch
LF.fetch = lambda url, **k: real_fetch(url, transport=site({PAPER: (200, {"content-type": "text/html"}, BODY)}), resolve=PUBLIC, **k)
os.environ.update(STEP_PARAMS="{}", STEP_WANT_ID="w-fix06", STEP_ORIGINAL_WANT="I want to read the made-up paper in full")
out = W.ACTION_MAP["read_url"]("Previous steps and what was found:\n- Step 1 (web_search): a note\n\nCurrent step goal: read it")
LF.fetch = real_fetch
check("the step opens the address its search found and reads it", isinstance(out, str) and out.startswith(U.FULL + ": " + PAPER), str(out)[:200])
check("its provenance names the want the router was running", provenance()[-1]["want_id"] == "w-fix06"
      and "step 1 (web_search)" in provenance()[-1]["rule"], provenance()[-1])
m = re.search(r"receipt:\s*(\S+)", out)
check("the router's receipt rule keeps it as a file", m and os.path.exists(m.group(1)))
import want_completion as WC
ev = WC.step_evidence({"step_history": [{"step": 1, "capability": "read_url", "findings": out,
                                         "receipt": {"kind": "file", "ref": m.group(1)}}]})
check("the completion door counts it as evidence", WC.has_evidence(ev) and ev[0]["kind"] == "file", ev)

print("\n--- the completion judge is shown READ IN FULL, not a note about it ---")
SEEN = []
class _Resp:
    def json(self): return {"choices": [{"message": {"content": '{"completed": true, "haiku": "a b c"}'}}]}
sys.modules["requests"] = types.SimpleNamespace(post=lambda url, json=None, **k: (SEEN.append(json), _Resp())[1], get=no_network)
verdict = W._want_end_verdict({"want": "I want to read the made-up paper in full", "step_history": [
    {"capability": "web_search", "note": "searched"}, {"capability": "read_url", "note": "a model's note", "findings": out}]})
prompt = SEEN[-1]["messages"][0]["content"] if SEEN else ""
check("the judge reads the step's own READ IN FULL line", ("- read_url: " + U.FULL + ": " + PAPER) in prompt
      and "a model's note" not in prompt, prompt[:600])
check("and is told what READ IN FULL means", "READ IN FULL means the whole text at that address was read" in prompt)
check("its verdict stands as it gave it", verdict[0] == "fulfilled")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)

print("\n--- a web_search step keeps what it found and where ---")
json.dump({"searches": [{"synthesis": "A made-up synthesis of the search.", "evidence": [PAPER, "ftp://no.example.org/x"]}]},
          open(os.path.join(MEM, "web-search-log.json"), "w"))
os.environ.pop("VINTOS_WEB_SEARCH_STARTED", None)
check("no search started by this step: an older row is never credited",
      W.capture_findings("web_search", "a made-up search") == "Web search completed")
os.environ["VINTOS_WEB_SEARCH_STARTED"] = "2031-01-02T10:00:00"
json.dump({"searches": [{"timestamp": "2031-01-02T09:59:00", "synthesis": "An older search.", "evidence": [PDF]}]},
          open(os.path.join(MEM, "web-search-log.json"), "w"))
check("a row from before this step's search is not this step's",
      W.capture_findings("web_search", "a made-up search") == "Web search completed")
json.dump({"searches": [{"timestamp": "2031-01-02T10:00:05", "synthesis": "A made-up synthesis of the search.",
                         "evidence": [PAPER, "ftp://no.example.org/x"]}]}, open(os.path.join(MEM, "web-search-log.json"), "w"))
found = W.capture_findings("web_search", "a made-up search")
check("the log's dict form is read: its synthesis and its addresses", "A made-up synthesis" in found
      and ("Addresses found: " + PAPER) in found and "ftp://" not in found, found)

print("\n--- a want to read the whole text needs the step that reads it ---")
for w in ("I want to read the full text of the made-up Piezo paper", "I want to read Graziano's attention schema paper",
          "I want the PDF itself, not the landing page", "I want to open the link Muse sent and read it",
          "I want to pull the full text behind the made-up eLife paper",
          "To get the actual made-up Fixture PDF as a direct file", "To feel the made-up fixture papers themselves"):
    check("full read: %s" % w, C.contract_for(w)["full_read"], C.contract_for(w))
for w in ("I want to email the author about her paper", "I want to be able to take a PDF apart: pull its text and tables",
          "I want to write a poem about paper cranes", "I want to read my journal from last week",
          "I want to hear the actual text Gloria meant, not my guess", "I want to read more and link my thoughts together",
          "I want to read through my journals and find the link between them", "I want to read the room and post an article",
          "I want to read Gloria's message and send her the link to the song", "I want to read the papers on my desk"):
    check("not a full read: %s" % w, not C.contract_for(w)["full_read"], C.contract_for(w))
steps, ch = C.normalize_steps("I want to read the full text of the made-up Piezo paper",
                              [{"capability": "introspect", "note": "what it means to me"}])
check("no address in the want: a search for it, then read_url, before working with it",
      [s["capability"] for s in steps] == ["web_search", "read_url", "introspect"]
      and "added_required_read_url" in ch and "added_search_for_the_address" in ch, (steps, ch))
steps, ch = C.normalize_steps("I want to read the full text at %s and tell Gloria what it says" % PAPER,
                              [{"capability": "gloria", "note": "tell her"}])
check("an address in the want: read_url alone, and Gloria stays last", [s["capability"] for s in steps] == ["read_url", "gloria"], steps)
steps, ch = C.normalize_steps("I want to read the full paper",
                              [{"capability": "web_search", "note": "find it"}, {"capability": "read_url", "note": "read it"}])
check("a plan that has it is left alone", [s["capability"] for s in steps] == ["web_search", "read_url"] and not ch, (steps, ch))
steps, ch = C.normalize_steps("I want to read the full paper and tell Gloria", [
    {"capability": "web_search", "note": "a"}, {"capability": "analyze_memory", "note": "b"},
    {"capability": "correlate", "note": "c"}, {"capability": "make_chart", "note": "d"}])
check("trimming to four never drops the read", "read_url" in [s["capability"] for s in steps] and len(steps) <= 4
      and steps[-1]["capability"] == "gloria", steps)
steps, ch = C.normalize_steps("I want to read the full paper on made-up grid cells and tell Gloria", [
    {"capability": "introspect", "note": "a"}, {"capability": "local_analysis", "note": "b"},
    {"capability": "read_memory", "note": "c"}, {"capability": "gloria", "note": "d"}])
caps = [s["capability"] for s in steps]
check("trimming keeps the search that finds the address with the read", len(steps) <= 4
      and caps.index("web_search") + 1 == caps.index("read_url") and caps[-1] == "gloria", caps)
check("the inserted search asks for the full text plainly", steps[caps.index("web_search")]["note"].startswith(
      "Search for the open full text of: read the full paper"), steps[caps.index("web_search")]["note"])
check("a plan without it does not satisfy the want", not C.satisfies_contract("I want to read the full paper", [{"capability": "web_search"}])
      and C.satisfies_contract("I want to read the full paper", [{"capability": "web_search"}, {"capability": "read_url"}]))
for rel in ("scripts/emoclaw_utils.py", "bin/emoclaw_utils.py"):
    s = src(rel)
    check("the planner is offered read_url (%s)" % rel, "\n- read_url: Open one link and read its WHOLE text" in s
          and "needs a read_url step" in s)
check("the planner's twins match", src("scripts/emoclaw_utils.py") == src("bin/emoclaw_utils.py"))
check("installed with the deploy", "want_read_url.py" in src("scripts/deploy-atelier.sh"))

print("\n--- her Watch face: a change keeps what it shows and why ---")
import watch_presence as WP
WP.MEMORY = MEM; WP.SONG = os.path.join(MEM, "watch-arrival-song.json")
FACE = os.path.join(MEM, "watch-face-shown.json")
items = [{"surface": "journal", "ref": "2031-01-02#10:15", "at": "2031-01-02T10:15", "piece": {"type": "journal", "text": "A made-up entry."}},
         {"surface": "image", "ref": "x.png", "at": "2031-01-01T09:00", "piece": {"type": "image", "title": "x"}}]
n = len(provenance())
r1 = WP.face_shown(items, days=7, now=time.time())
check("a new first item: one watch_face row, what the face shows and by which rule",
      r1 and r1["action"] == "watch_face" and r1["what"] == "A made-up entry." and "newest piece sent" in r1["rule"]
      and r1["refs"]["surface"] == "journal" and len(provenance()) == n + 1, r1)
check("the same first item again: nothing more", WP.face_shown(items, days=7) is None and len(provenance()) == n + 1)
check("nothing to show: the face keeps its line, nothing recorded", WP.face_shown([], days=7) is None and len(provenance()) == n + 1)
json.dump({"id": "fixturesong01", "title": "A made-up song", "ref": "A made-up song", "media_url": "https://media.example.org/s.mp3",
           "offered_ts": time.time()}, open(WP.SONG, "w"))
r2 = WP.face_shown([WP.top_song()] + items, days=7)
check("the arrival song on top: its own rule", r2 and r2["what"] == "A made-up song" and "arrival song stays first" in r2["rule"], r2)
check("the store of what was shown is in the scratch memory", json.load(open(FACE))["key"] == ["song", "A made-up song"])
check("the landings route records it", "watch_presence.face_shown(items[:5]" in src("scripts/watch_routes.py"))

print("\n--- journal posts keep why ---")
jdir = os.path.join(MEM, "journal"); os.makedirs(jdir, exist_ok=True)
jfile = os.path.join(jdir, "2031-01-02.md")
open(jfile, "w").write("# Journal — 2031-01-02\n\n## 10:15 — Idle thoughts\n\nA made-up entry.\n")
for rel in ("scripts/idle-journal.sh", "bin/idle-journal.sh"):
    sh = src(rel)
    block = sh[sh.index("\n", sh.index("<<'JRNPROVEOF'")) + 1:sh.index("\nJRNPROVEOF")]
    check("%s records right after the entry is posted" % rel,
          sh.index('Idle thoughts\\n\\n$ENTRY\\n" >> "$JOURNAL_FILE"') < sh.index("<<'JRNPROVEOF'") < sh.index("_WORKS_NEAR="))
    n = len(provenance())
    env = dict(os.environ, JRN_FILE=jfile, JRN_FORCE="0", HOME=HOME, SPARK_WORKSPACE=WS)
    run = subprocess.run([sys.executable, "-"], input=block, text=True, capture_output=True, env=env, timeout=60)
    row = provenance()[-1] if len(provenance()) == n + 1 else {}
    check("%s: a journal_post row naming the entry, its schedule and its hour rule" % rel,
          row.get("action") == "journal_post" and row.get("what") == "Idle thoughts 2031-01-02 10:15"
          and "cron" in (row.get("trigger") or "") and "one idle entry an hour" in (row.get("rule") or "")
          and row.get("refs", {}).get("entry") == "## 10:15", (run.stderr[-300:], row))
daily = src("bin/vintos-journal.sh")
check("the daily journal records after its entry is written",
      daily.index("f.write(result.strip() + chr(10))") < daily.index("action_provenance.record('journal_post', 'Daily journal '"))
check("the daily journal's record keeps to single quotes inside its shell string",
      '"' not in daily[daily.index("# the entry and why it was posted"):daily.index("# Update specificity check")])
SEEN.clear()
class _J:
    def raise_for_status(self): pass
    def json(self): return {"choices": [{"message": {"content": "A made-up want journal entry."}}]}
sys.modules["requests"] = types.SimpleNamespace(post=lambda *a, **k: _J(), get=no_network)
os.environ["STEP_WANT_ID"] = "w-fix07"
n = len(provenance())
got = W.write_journal("Current step goal: write about the made-up paper")
row = provenance()[-1] if len(provenance()) == n + 1 else {}
check("a want's journal step records its post, for that want",
      isinstance(got, str) and row.get("action") == "journal_post" and row.get("want_id") == "w-fix07"
      and row.get("organ") == "wants-router step write_journal", row)
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)

print("\n--- he can ask about each ---")
rs = provenance()
check("why the link was opened", AP.match("why did I open that paper link", rs)["action"] == "read_url")
check("why the watch face changed", AP.match("why did my watch face change", rs)["action"] == "watch_face")
check("why the journal entry was posted", AP.match("why that journal entry", rs)["action"] == "journal_post")

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
