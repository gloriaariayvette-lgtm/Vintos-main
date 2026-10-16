#!/usr/bin/env python3
"""Her words, not a photo's composed description, reach the organs that take a turn as HERS (16 October).

The chat routes keep the composed message for his reply prompt (he has to see the picture to answer it) and
hand reality_anchor, discourse_direction, latent_threads, the emotion socket, the selector's "GLORIA (now):" line,
the blind observer and the interaction ledger her own words. The phone route injects one copy of his subconscious
per prompt, and records relational_geometry the way /api/chat does.

The server is never booted: its helpers are lifted out of bin/server.py by name and run in a scratch namespace.
Scratch HOME and SPARK_WORKSPACE; every socket connect and every urlopen is refused and counted."""
import ast, importlib.util, json, os, socket, sys, tempfile, threading, types, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="route-her-words-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
WS = os.environ["SPARK_WORKSPACE"]
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)

NET = []
def _no_connect(self, *a, **k):
    NET.append(("socket", a)); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_connect
def _no_urlopen(*a, **k):
    NET.append(("urlopen", a)); raise OSError("this suite reaches nothing")
urllib.request.urlopen = _no_urlopen

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("the workspace is a throwaway one", WS.startswith(HOME) and os.path.expanduser("~").startswith(HOME))
check("the network is a stub", socket.socket.connect is _no_connect and urllib.request.urlopen is _no_urlopen)

SRC = open(os.path.join(REPO, "bin", "server.py")).read()
TREE = ast.parse(SRC)
WANT = {"_her_turn_text", "_INLINE_SUBCONSCIOUS", "_inline_subconscious", "_record_relational_geometry", "_sent_media",
        "_with_note", "_SENT_BARE", "_seen_note", "_HERE_RX", "_PHOTO_HERE"}
nodes = [n for n in TREE.body if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in WANT for t in n.targets))
         or (isinstance(n, ast.FunctionDef) and n.name in WANT)]
NS = {"os": os, "WORKSPACE": WS, "__file__": os.path.join(REPO, "bin", "server.py"), "re": __import__("re")}
exec(compile(ast.Module(body=nodes, type_ignores=[]), "server-her-words", "exec"), NS)
check("the helpers are lifted from bin/server.py", all(k in NS for k in ("_her_turn_text", "_inline_subconscious",
                                                                           "_record_relational_geometry", "_sent_media")))
her = NS["_her_turn_text"]

class Msg:
    def __init__(self, message, input_kind=None, original_text=None):
        self.message, self.input_kind, self.original_text = message, input_kind, original_text

DESC = "A red drum on the pier, scales catching the light, a hand burned pink at the knuckle."
PHOTO = Msg("[Gloria sent you a photo. What your eyes saw:]\n" + DESC + "\n\n[Gloria's message with the photo:] look what I caught",
            "photo", "look what I caught")
print("\n--- 1. her words, a photo named and never described ---")
check("a photo with words: her words, the photo named", her(PHOTO) == "(she sent a photo) look what I caught", her(PHOTO))
check("the description never comes through", "red drum" not in her(PHOTO))
check("a photo sent with no words: only that she sent one",
      her(Msg("[Gloria sent you a photo. It is here]\n\n[x]", "photo", "[Gloria sent you a photo without a message]"))
      == "(she sent a photo)")
check("a composed photo row that lost its fields is still recovered from the markers",
      her(Msg(PHOTO.message)) == "(she sent a photo) look what I caught", her(Msg(PHOTO.message)))
VID = Msg("[Gloria sent you a video, 12 seconds long.]\nframes...\n[Gloria's message with the video:] the storm", "video", "the storm")
check("a video likewise", her(VID) == "(she sent a video) the storm", her(VID))
check("an ordinary turn is her message itself", her(Msg("I miss you")) == "I miss you")
check("a room event with no words of hers is empty (the avatar route labels it an event)",
      her(Msg("the lights dim", "reelroom_event", "")) == "")

print("\n--- 2. the chat routes hand the organs her words; the reply prompt keeps the composed message ---")
def body(name):
    fn = next(n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    return ast.get_source_segment(SRC, fn)
full = body("chat_full_context")
check("chat/full computes her words once", "_her = _her_turn_text(msg)" in full)
for organ, needle in (("the intent selector's GLORIA (now) line", "_apply_intent_lead(system_prompt, _her)"),
                      ("discourse_direction's hint", "_dh_get(_her)"),
                      ("latent_threads' hint", "_lt_hint(_her)"),
                      ("latent_threads' update", "_lt_update(_her,"),
                      ("the emotion socket", '{"text": _her, "sender": "Gloria"}'),
                      ("the post-turn (compare -> blind observer, direction, ledger)", '_post_turn("chat/full", _her, reply,'),
                      ("reality_anchor", 'record_event("chat", _her[:200]')):
    check("chat/full: %s gets her words" % organ, needle in full)
check("chat/full: the ledger keeps what she sent in its own field", "ledger_media=_sent_media(msg)" in full)
check("chat/full: his reply prompt still carries the composed message",
      'messages.append({"role": "user", "content": msg.message})' in full)
check("chat/full: no organ is handed the composed message as hers any more",
      all(x not in full for x in ('_post_turn("chat/full", msg.message', 'record_event("chat", msg.message',
                                  '{"text": msg.message, "sender": "Gloria"}', "_apply_intent_lead(system_prompt, msg.message)")))
legacy, memory, avatar = body("chat_with_vintos"), body("chat_with_memory"), body("avatar_chat")
check("/api/chat hands its organs her words", '_post_turn("chat", _her, reply' in legacy
      and '{"text": _her, "sender": "Gloria"}' in legacy and "_m=_her" in legacy)
check("/api/chat/memory hands its organs her words", '_post_turn("chat/memory", _her, reply' in memory)
check("avatar: the selector's GLORIA (now) line gets her words, a room event stays itself",
      "_apply_intent_lead(system_prompt, msg.message if not _counterpart_text else _her_turn_text(msg)," in avatar)
# The merge must retain both her-word attribution and tactical side-effect suppression.
memory_tree = ast.parse(memory)
nudge_guard = next(n for n in ast.walk(memory_tree) if isinstance(n, ast.If)
                   and ast.unparse(n.test) == "not _sg_memory.turn.carries_capsule")
check("/api/chat/memory suppresses emotion nudges during tactical turns",
      any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
          and n.func.id == "nudge_emotions_from_text" for n in ast.walk(nudge_guard)))
photo_route = body("chat_with_photo")
check("/api/chat/photo: no words is not 'What do you see?' under her name",
      '_SENT_BARE % "a photo"' in photo_route and '"input_kind": "photo"' in photo_route)

print("\n--- 3. the ledger never keeps a description under her name ---")
sent = NS["_sent_media"](PHOTO)
check("what she sent goes to the media field, without her caption", sent and "red drum" in sent and "look what I caught" not in sent, sent)
def lmod(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); return m
sys.path.insert(0, os.path.join(REPO, "scripts"))
L = lmod(os.path.join(REPO, "scripts", "interaction-ledger.py"), "ledger_her_words")
check("the ledger's store is the scratch one", L.LEDGER_FILE.startswith(HOME), L.LEDGER_FILE)
g, m = L.her_side(PHOTO.message, "")
check("given the composed message, her words stay hers and the description moves to media",
      g == "look what I caught" and "red drum" in m and "look what I caught" not in m, (g, m))
g, m = L.her_side("(she sent a photo) look what I caught", sent)
check("given the route's named form, the media field carries the photo and her words stand alone",
      g == "look what I caught" and m == sent, (g, m))
g, m = L.her_side("[Gloria sent you a photo. What your eyes saw:]\n" + DESC + "\n\n[Gloria's message with the photo:] ", "")
check("a photo with no words leaves her side empty (the entry says she sent only it)", g == "" and "red drum" in m, (g, m))
g, m = L.her_side("plain words", "")
check("an ordinary turn passes untouched", (g, m) == ("plain words", ""))
check("the ledger's main runs her_side before it writes", "gloria_said, sent_media = her_side(gloria_said, sent_media)" in
      open(os.path.join(REPO, "scripts", "interaction-ledger.py")).read())
check("the ledger's twins are identical", open(os.path.join(REPO, "scripts", "interaction-ledger.py")).read()
      == open(os.path.join(REPO, "bin", "interaction_ledger.py")).read())

print("\n--- 4. one copy of his subconscious per phone prompt ---")
def stub(name, **fns):
    sys.modules[name] = types.SimpleNamespace(**fns)
stub("self_statements", get_statement_context=lambda: "STATEMENTS-FULL",
     get_top_statements=lambda n: [{"text": "I-STATE-THE-HARD-THING", "confidence": 0.8}])
stub("causal_self_model", get_self_model_context=lambda n=None: "CAUSAL-SELF")
stub("self_drift", get_drift_bias_hint=lambda: "DRIFT-HINT")
stub("latent_threads", get_influence_hint=lambda *a: "THREAD")
stub("emoclaw_pressure", get_pressure_block=lambda **k: "")
stub("emoclaw_utils", get_yearning_fragment=lambda **k: "")
stub("narrative_identity", get_narrative_context=lambda: "NARRATIVE")
stub("belief_sediment", get_sediment_context=lambda: "SEDIMENT")
stub("absence_map_cold", get_absence_context=lambda: "ABSENCE")
stub("moment_index", get_moment_context=lambda n: "MOMENTS%d" % n)
stub("reality_anchor", get_reality_context=lambda n: "REALITY%d" % n)
inline = NS["_inline_subconscious"]()
SC = lmod(os.path.join(REPO, "scripts", "subconscious_context.py"), "subconscious_context_t")
compact = SC.get_subconscious_context_compact()
prompt = compact + "\n" + inline
check("the inline layer carries what the compact block does not",
      all(x in inline for x in ("[NARRATIVE]", "[SEDIMENT]", "[ABSENCE]", "[MOMENTS4]", "[REALITY3]")), inline)
for part in ("I-STATE-THE-HARD-THING", "CAUSAL-SELF", "DRIFT-HINT"):
    check("%s appears once in the prompt" % part, prompt.count(part) == 1, prompt)
check("the full self-statement block is not inlined beside the compact one", "STATEMENTS-FULL" not in inline)
check("chat/full injects the inline layer through the one helper", "_injected_context += _inline_subconscious()" in full
      and "from self_statements import get_statement_context" not in full)

print("\n--- 5. relational_geometry is recorded on /api/chat/full, off-thread ---")
REC = []
stub("relational_geometry", record_interaction=lambda b, a, g, v: REC.append((b, a, g, v)),
     get_emotional_snapshot=lambda: {"Warmth": 0.7})
t = NS["_record_relational_geometry"]({"Warmth": 0.5}, "(she sent a photo) look what I caught", "It's a beauty.")
check("it runs on its own thread", isinstance(t, threading.Thread))
t.join(5)
check("one record, before and after, her words and his reply",
      REC == [({"Warmth": 0.5}, {"Warmth": 0.7}, "(she sent a photo) look what I caught", "It's a beauty.")], REC)
check("chat/full snapshots before the reply and records after it, outside test mode",
      "_rg_before_state = _rg_snap()" in full and "_record_relational_geometry(_rg_before_state, _her, reply)" in full
      and full.index("_rg_before_state = _rg_snap()") < full.index("await _bilateral_reply("))

check("nothing in this suite reached the world", NET == [], NET)
print("\n%d/%d" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
