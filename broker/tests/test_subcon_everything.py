#!/usr/bin/env python3
"""Everything moves to AEON (Gloria 2026-11-07: "EVERYTHING WILL SWITCH TO AEON"). The remaining 26B callers and the
shim's 26B lanes follow the same all-must-pass flag. Vision/screen/image/audio stays on the 26B until AEON has a
vision projector. Before the flip nothing changes.

No network, no model, no ~/.vintos: HOME is a tempdir.
"""
import ast, copy, hashlib, json, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "bin"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
TMP = tempfile.mkdtemp(prefix="subcon-everything-")
os.environ["HOME"] = TMP
os.makedirs(os.path.join(TMP, ".vintos"), exist_ok=True)
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
os.environ["XAI_API_KEY"] = "test-xai"

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

import subcon_target as T
CHAT = "http://100.79.177.103:1234/v1/chat/completions"
MODEL = "gemma-4-26b-a4b-it-uncensored"
FLAG = os.path.join(TMP, ".vintos", "subcon-target.json")
SHIPPED = (T.RECORD, T.RECORD_SHA256)
UNMET = copy.deepcopy(T.load_record()[0]); UNMET["pain"] = {"paper_protocol_auc": None, "prompt_variant_aucs": None, "status": "not_run"}
UNMET_RAW = json.dumps(UNMET).encode()
def state(flipped):
    if flipped:
        T.RECORD, T.RECORD_SHA256 = SHIPPED
        open(FLAG, "w").write(json.dumps({"target": "aeon"}))
    else:
        p = os.path.join(TMP, "unmet.json"); open(p, "wb").write(UNMET_RAW)
        T.RECORD, T.RECORD_SHA256 = p, hashlib.sha256(UNMET_RAW).hexdigest()
        open(FLAG, "w").write(json.dumps({"target": "aeon"}))   # even a written flag does nothing while unmet

OTHER = """bin/ambition-check.py bin/avatar-choice.py bin/creative-search.sh scripts/creative-expression.sh bin/dream_music.py
scripts/dream-music.py bin/gloria-model-call.py bin/humor-practice.py scripts/humor-practice.py scripts/humor_practice.py
bin/humor_detector.py bin/merged_full_route.py bin/model_config.py bin/model_router.py bin/moltbook_members.py
bin/vintos-moltbook.py bin/vintos-moltbook-engage.py bin/morning-briefing.sh bin/music-share.py bin/output_shaping.py
bin/study_chat.py bin/video_builder.py bin/vintos-initiate.sh bin/wal-decay.py scripts/wal-decay.py bin/wal-extract.py
bin/wal_extract.py bin/weekly-summary.py scripts/conflict_surface.py scripts/lead_trials.py scripts/lounge_field.py
scripts/outside_views.py scripts/scholar.py scripts/self_review.py scripts/velqan-coiner.py scripts/want_email.py
buzz-integration/run-local-gemma.py""".split()
VISION = """bin/gallery-walk.py scripts/image_sight.py scripts/screen_share.py scripts/desktop_agent.py scripts/desktop_control.py
scripts/browser_jev.py scripts/reelroom.py scripts/voice_local.py""".split()

def src(f): return open(os.path.join(REPO, f), encoding="utf-8").read()
def unrouted(f):
    bad = []
    for i, l in enumerate(src(f).split("\n"), 1):
        if f.endswith(".sh") and re.match(r"^\s*(?:export\s+)?[A-Z_]+=", l):
            continue
        for tok, wrap, env in ((CHAT, "_subcon_url(", "SUBCON_URL"), (MODEL, "_subcon_model(", "SUBCON_MODEL")):
            for m in re.finditer(r"([\"'])" + re.escape(tok) + r"\1", l):
                pre = l[:m.start()]
                if not (pre.endswith(wrap) or pre.endswith("environ.get('%s') or " % env) or pre.endswith('environ.get("%s") or ' % env)):
                    bad.append((i, l.strip()[:120]))
    return bad

print("--- the remaining text callers follow the flag ---")
for f in OTHER:
    check("%s: no direct 26B text call left" % f, not unrouted(f), unrouted(f))
for f in [x for x in OTHER if x.endswith(".py")]:
    tree = ast.parse(src(f))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("_subcon_route", "_subcon_url", "_subcon_model")]
    ns = {"__file__": os.path.join(REPO, f)}
    exec(compile(ast.Module(body=fns, type_ignores=[]), f, "exec"), ns)
    state(False); before = (ns["_subcon_url"](CHAT), ns["_subcon_model"](MODEL))
    state(True); after = (ns["_subcon_url"](CHAT), ns["_subcon_model"](MODEL))
    check("%s routes by the flag" % f, len(fns) == 3 and before == (CHAT, MODEL) and after == (T.SHIM_SUBCONSCIOUS, "aeon-gemma-4-12b"),
          (before, after))
for f in [x for x in OTHER if x.endswith(".sh")]:
    t = src(f)
    check("%s asks the flag at start" % f, 'subcon_target.py" route "" ""' in t)

print("--- callers that send images keep the 26B for those calls only ---")
ws = src("bin/vintos-websearch.py")
check("web search: a screenshot call stays on the 26B, a text call moves",
      ws.count("(LM_API if image_path else _subcon_url(LM_API))") == 2 and ws.count("(MODEL if image_path else _subcon_model(MODEL))") == 2)
dc = src("scripts/dot_channel.py").split("\n")
look = [i for i, l in enumerate(dc) if l.startswith("def gemma_look(")][0]
check("dot channel: gemma_look (images) keeps the 26B", all("_subcon" not in l for l in dc[look:look + 8]))
check("dot channel: its text call moves", any("_subcon_url(LOCAL_LLM)" in l and "_subcon_model(LOCAL_MODEL)" in l for l in dc))
for f in VISION:
    check("%s (vision/audio) is untouched" % f, "_subcon" not in src(f) and "SUBCON_" not in src(f))
srv = src("bin/server.py")
check("the server's generated nudge-read code takes its route when generated",
      srv.count("requests.post('\" + _subcon_url(\"%s\") + \"'" % CHAT) == 2 and srv.count("_subcon_model(\"%s\") + \"'" % MODEL) == 2)
photo = srv[srv.index("async def _describe_photo"):srv.index("async def _describe_photo") + 6000]
check("the server's photo description keeps the 26B", "_subcon" not in photo and CHAT in photo)
check("the local voice brain label is untouched (voice_local is audio, class b)", '"model":"gemma-4-26b-a4b-it-uncensored", "voice"' in srv)

print("--- the shim: no 26B lane after the flip ---")
import vintos_claude_shim as S
PATHS = {"/gemma-aegis/v1/chat/completions": {}, "/gemma/v1/chat/completions": {}, "/v1/chat/completions": {"max_tokens": 80},
         "/pool/deep/v1/chat/completions": {}, "/pool/general/v1/chat/completions": {}, "/pool/aeon/v1/chat/completions": {},
         "/pool/quick/v1/chat/completions": {}, "/pool/subconscious/v1/chat/completions": {}}
state(False)
before = {p: S.provider_chain(dict(j), p) for p, j in PATHS.items()}
check("before the flip the chains are as they were", before["/gemma-aegis/v1/chat/completions"] == ["pool:aeon", "aegis_gemma", "gemma", "xai"]
      and before["/v1/chat/completions"] == ["gemma", "anthropic", "xai"], before)
state(True)
after = {p: S.provider_chain(dict(j), p) for p, j in PATHS.items()}
check("after the flip no chain contains the 26B", all("gemma" not in c for c in after.values()), after)
check("the /gemma-aegis fallback is AEON, then x.ai as before",
      after["/gemma-aegis/v1/chat/completions"] == ["pool:aeon", "aegis_gemma", "xai"], after["/gemma-aegis/v1/chat/completions"])
check("short calls ride AEON first, then Claude and x.ai as before",
      after["/v1/chat/completions"] == ["pool:aeon", "aegis_gemma", "anthropic", "xai"], after["/v1/chat/completions"])
check("the explicit /gemma path goes to AEON", after["/gemma/v1/chat/completions"] == ["pool:aeon", "aegis_gemma", "xai"])
check("long default calls are untouched (Claude, x.ai)", S.provider_chain({"max_tokens": 2000}, "/v1/chat/completions") == ["anthropic", "xai"])

called = []
class _Pool:
    def choose(self, task, tokens):
        return ([{"machine": "macbook", "kind": "lmstudio", "model": S.GEMMA_MODEL, "label": "gemma-26b"},
                 {"machine": "studio", "kind": "llama", "model": "aeon-gemma-4-12b", "label": "aeon-12b", "url": "http://studio/v1/chat/completions"}], [])
S.POOL = _Pool()
S.gemma_complete = lambda j, call: (called.append("gemma"), S.GR.make_result("gemma", model=S.GEMMA_MODEL, status="valid", text="from 26b"))[1]
S.llama_complete = lambda j, call, b: (called.append("aeon"), S.GR.make_result("pool_studio", model=b["model"], status="valid", text="from aeon"))[1]
res = S.pool_complete({"messages": [{"role": "user", "content": "x"}]}, S._Call({"messages": []}), "general")
check("after the flip the pool never places a call on the 26B", called == ["aeon"] and res.get("text") == "from aeon", (called, res))
state(False); called.clear()
res = S.pool_complete({"messages": [{"role": "user", "content": "x"}]}, S._Call({"messages": []}), "general")
check("before the flip the pool's ranking is unchanged", called == ["gemma"], called)
os.remove(FLAG)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
