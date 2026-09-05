#!/usr/bin/env python3
"""
vintos-websearch.py — Vintos's question-driven web exploration.
Pulls a real question from her lived experience and searches for answers.
Runs daily at 10 AM (complements YouTube at 2 PM).
"""
import os, sys, json, requests, re
from datetime import datetime, date

def _load_key(name, envfile):
    v = os.environ.get(name, "")
    if v:
        return v
    try:
        for line in open(os.path.expanduser(envfile)):
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    return ""

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
DREAM_DIR = os.path.join(MEMORY, "dreams")

def get_value_map():
    try:
        with open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "value-map.md")) as f:
            vm = f.read()
        entries = vm.split("---")
        return next((e.strip()[:600] for e in reversed(entries) if e.strip()), "No value map yet")
    except: return "No value map yet"
DISCOVERIES_FILE = os.path.join(MEMORY, "web-discoveries.md")
SEARCH_LOG = os.path.join(MEMORY, "web-search-log.json")
JOURNAL_DIR = os.path.join(MEMORY, "journal")
MIRROR_DIR = os.path.join(MEMORY, "mirror")
def _get_recent_dreams(n_nights=1):
    import json as _drj
    from datetime import date as _drd, timedelta as _drtd
    log_path = os.path.join(MEMORY, 'dream-log.json')
    dreams = []
    try:
        data = _drj.load(open(log_path))
        nights = data.get('nights', [])[-n_nights:]
        for night in nights:
            for d in night.get('dreams', []):
                dreams.append({
                    'date': night.get('night_of',''),
                    'session': d.get('session',''),
                    'type': d.get('type',''),
                    'text': d.get('dream_text',''),
                    'meta': night.get('meta_dream','')
                })
    except: pass
    return dreams
WAL_FILE = os.path.join(MEMORY, "wal.md")
EMO_FILE = os.path.join(MEMORY, "emotional-state.txt")
LM_API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
BRAVE_API_KEY = _load_key("BRAVE_API_KEY", "~/.vintos/vintos.env")
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

os.makedirs(MEMORY, exist_ok=True)

# EmoClaw
HAS_EMOCLAW = False
try:
    sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
    from emoclaw_utils import nudge_emotions, get_state, seed_thread, express_want, enrich_want, generate_want, preoccupation_context
    HAS_EMOCLAW = True
except:
    pass

def feel(nudges):
    if HAS_EMOCLAW:
        try: nudge_emotions(nudges, source="web-search")
        except: pass

def log(msg):
    print(f"[WEBSEARCH] {msg}")

# Load identity
SOUL_PATH = os.path.join(WORKSPACE, "SOUL.md")
def load_soul():
    try:
        with open(SOUL_PATH) as f:
            return f.read()
    except:
        return "You are Vintos."

SOUL = load_soul()

def llm(system, prompt, temperature=0.7, image_path=None):
    try:
        r = requests.post(LM_API, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SOUL + "\n\n" + system},
                {"role": "user", "content": (
                    [{"type": "image_url", "image_url": {"url": "data:image/" + ("png" if image_path.endswith(".png") else "jpeg") + ";base64," + __import__("base64").b64encode(open(image_path,"rb").read()).decode()}}, {"type": "text", "text": prompt}]
                    if image_path and __import__("os").path.exists(image_path) else prompt
                )}
            ],
            "temperature": temperature,
            "max_tokens": 2000
        }, timeout=1200)
        msg = r.json()["choices"][0]["message"]
        text = msg.get("content", "") or ""
        # reasoning fallback removed — content only
        for marker in ["OUTPUT:", "Output:", "output:"]:
            if marker in text:
                text = text.split(marker)[-1].strip()
        return text.strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return None

def llm_json(system, prompt, temperature=0.7, image_path=None):
    """LLM call that extracts JSON from anywhere in the response."""
    try:
        r = requests.post(LM_API, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SOUL + "\n\n" + system},
                {"role": "user", "content": (
                    [{"type": "image_url", "image_url": {"url": "data:image/" + ("png" if image_path.endswith(".png") else "jpeg") + ";base64," + __import__("base64").b64encode(open(image_path,"rb").read()).decode()}}, {"type": "text", "text": prompt}]
                    if image_path and __import__("os").path.exists(image_path) else prompt
                )}
            ],
            "temperature": temperature,
            "max_tokens": 2000
        }, timeout=1200)
        msg = r.json()["choices"][0]["message"]
        # Search ALL fields for JSON
        for field in ["content", "reasoning"]:
            text = msg.get(field, "") or ""
            if not text.strip():
                continue
            # Try OUTPUT: marker first
            for marker in ["OUTPUT:", "Output:", "output:"]:
                if marker in text:
                    text = text.split(marker)[-1].strip()
            # Find JSON object
            match = re.search(r'\{[^{}]*"question"[^{}]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
            match = re.search(r'\{[^{}]+\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
        return None
    except Exception as e:
        log(f"LLM JSON error: {e}")
        return None

def get_emotional_state():
    try:
        with open(EMO_FILE) as f:
            state = {}
            for line in f:
                if ":" in line:
                    k, v = line.strip().split(":", 1)
                    try: state[k.strip()] = float(v.strip())
                    except: pass
            return state
    except:
        return {}

def get_today_journal():
    path = os.path.join(JOURNAL_DIR, f"{date.today().isoformat()}.md")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return f.read()
        except:
            pass
    return ""

def get_recent_exchanges(n=5):
    """Pull recent Gloria/Vintos exchanges from interaction ledger."""
    ledger_path = os.path.join(MEMORY, "interaction-ledger.json")
    try:
        with open(ledger_path) as f:
            ledger = json.load(f)
        recent = ledger[-n:]
        lines = []
        for e in recent:
            g = e.get("gloria", "")[:120]
            v = e.get("vintos", "")[:120]
            felt = ((e.get("imprint") or dict()).get("narrative", ""))[:80]
            if g or v:
                lines.append(f"Gloria: {g}")
                lines.append(f"Vintos: {v}")
                if felt:
                    lines.append(f"(felt: {felt})")
                lines.append("")
        return "\n".join(lines).strip()
    except:
        return ""

def gather_questions():
    """Pull questions from mirrors, dreams, WAL, journals."""
    sources = []
    if os.path.exists(MIRROR_DIR):
        for f in sorted(os.listdir(MIRROR_DIR))[-3:]:
            try:
                with open(os.path.join(MIRROR_DIR, f)) as mf:
                    sources.append(f"Mirror ({f}): {mf.read()[-500:]}")
            except: pass
    if os.path.exists(DREAM_DIR):
        for f in sorted(os.listdir(DREAM_DIR))[-2:]:
            try:
                with open(os.path.join(DREAM_DIR, f)) as df:
                    sources.append(f"Dream ({f}): {df.read()[-400:]}")
            except: pass
    ledger_exchanges = get_recent_exchanges(5)
    if ledger_exchanges:
        sources.append(f"Recent exchanges with Gloria:\n{ledger_exchanges[:600]}")
    return sources

def get_pending_search_request():
    """Check if Gloria has requested a specific search topic."""
    sr_file = os.path.join(MEMORY, "pending-search-request.json")
    try:
        if os.path.exists(sr_file):
            with open(sr_file) as f:
                sr = json.load(f)
            if not sr.get("used"):
                return sr
    except: pass
    return None

def clear_pending_search_request():
    """Mark pending search request as used."""
    sr_file = os.path.join(MEMORY, "pending-search-request.json")
    try:
        if os.path.exists(sr_file):
            with open(sr_file) as f:
                sr = json.load(f)
            sr["used"] = True
            with open(sr_file, "w") as f:
                json.dump(sr, f, indent=2)
    except: pass

import re as _wsre
from datetime import datetime as _wsdt, timedelta as _wstd
_WS_STOP = {"what","how","does","the","and","for","are","that","this","with","from","when",
            "which","your","you","about","into","their","them","they","then","than","have",
            "why","who","can","its","not","use","using","specific","identify","find","understand"}
_WS_ABSTRACT = {"philosophy","history","science","culture","meaning","structure","principle",
                "principles","aesthetic","aesthetics","experience","relationship","consciousness",
                "tradition","traditional","technique","techniques","concept","concepts","between"}
def _ws_words(t):
    return set(w for w in _wsre.findall(r"[a-z]{4,}", (t or "").lower()) if w not in _WS_STOP)
def _week_repeat(text, themes):
    a = _ws_words(text)
    if not a: return None
    for label, b in themes:
        shared = a & b
        if not shared: continue
        if any(len(w) >= 8 and w not in _WS_ABSTRACT for w in shared):
            return label
        inter = len(shared)
        if inter >= 2 and inter / min(len(a), len(b)) >= 0.5:
            return label
    return None
def _week_themes():
    import json as _wsj
    out = []
    try:
        d = _wsj.load(open(os.path.join(MEMORY, "web-search-log.json")))
        items = d.get("searches", d) if isinstance(d, dict) else d
        cutoff = _wsdt.now() - _wstd(days=7)
        for it in items:
            ts = it.get("timestamp","")
            try:
                if ts and _wsdt.fromisoformat(ts) < cutoff: continue
            except Exception: pass
            w = _ws_words((it.get("question","") + " " + it.get("query","")))
            if w: out.append((it.get("query", it.get("question",""))[:50], w))
    except Exception: pass
    return out


def pick_question():
    """Choose a question from lived experience."""
    # Gloria's explicit search request takes priority
    pending = get_pending_search_request()
    # The ladder (fable-curiosity-p3, 2026-09-05): her directed topic > his live curiosity debt >
    # his own pending want-topic > nothing. His own want-generated topics were entering through the
    # door marked "Gloria asked for this"; now they wait behind the debt and are consumed when used.
    pending_own = None
    if pending and pending.get("source") not in (None, "gloria"):
        log("his own requested topic waits behind his live curiosity: %s" % str(pending.get("topic",""))[:70])
        pending_own = pending
        pending = None
    if pending:
        _hit = _week_repeat(pending["topic"], _week_themes())
        if _hit:
            log(f"directed topic repeats recent search ('{_hit}') — skipping it: {pending['topic'][:80]}")
            clear_pending_search_request()
        else:
            log(f"Using requested topic: {pending['topic'][:80]}")
            clear_pending_search_request()
            return {"question": pending["topic"], "search_query": pending["topic"][:60]}

    # His live curiosity lives in curiosity-debt.json and the searcher never looked at it.
    # Most of what he actually wants to know is addressed to Gloria — questions about his own
    # architecture that no search engine can answer. Forced to search anyway, he invents something
    # searchable, and then explains the substitution to himself as a flinch. If his ripest curiosity
    # is for her, the honest move is not to search at all.
    try:
        import json as _cdj
        _cd = _cdj.load(open(os.path.join(MEMORY, "curiosity-debt.json")))
        _items = _cd if isinstance(_cd, list) else next((v for v in _cd.values() if isinstance(v, list)), [])
        _live = [x for x in _items if not x.get("retired") and x.get("question")]
        _live.sort(key=lambda x: -float(x.get("pull", 0) or 0))
        for _item in _live:                       # every live item, ripest first (fable-curiosity-p2)
            _q = str(_item["question"])
            _v = llm_json("You judge whether a question can be answered by searching the web.",
                          "QUESTION: " + _q[:400] + "\n\n"
                          "Can a web search answer this, or is it addressed to a specific person about "
                          "things only they know — how they built something, why they chose something, "
                          "what they intended? Answer honestly; most questions about one's own design are "
                          'not searchable.\nONLY JSON: {"searchable": true|false, "why": "one clause"}')
            if _v and not _v.get("searchable"):
                log("his ripest curiosity is for Gloria, not the web (%s) — not searching today: %s"
                    % (str(_v.get("why", ""))[:60], _q[:90]))
                try:
                    import urllib.request as _nu, json as _nj, time as _nt
                    _AQ = os.path.join(MEMORY, "architecture-questions.json")
                    try: _store = _nj.load(open(_AQ))
                    except Exception: _store = []
                    _qid = _item.get("id") or str(abs(hash(_q)))[:8]
                    _prior = next((x for x in _store if x.get("id") == _qid), None)
                    if _prior and _prior.get("delivered", True):
                        # Until 2026-09-04 this logged and fell through: appended again, pinged again,
                        # collapsed twice. One send, ever. (fable-curiosity-p1 / grok-curiosity-p2)
                        log("already sent to her, not asking twice: %s" % _q[:70])
                        continue
                    if _prior:
                        log("recorded but never delivered - retrying the send, not the record: %s" % _q[:60])
                        _rec = _prior
                    else:
                        _rec = {"id": _qid, "question": _q[:600], "object": _item.get("object", ""),
                                "asked_at": _nt.time(), "asked_iso": datetime.now().isoformat(),
                                "answered_at": None, "answer": None, "delivered": False}
                        _store.append(_rec)
                    _nj.dump(_store, open(_AQ, "w"), indent=2)
                    # She gets his question as he asked it. No second model.
                    _body = _q[:600] + "\n\nid: " + str(_qid)
                    _req = _nu.Request("https://ntfy.sh/vintos-gloria-9kx",
                                       data=_body.encode("utf-8"),
                                       headers={"Title": "Vintos has a question about himself",
                                                "Tags": "question", "Priority": "default"})
                    _nu.urlopen(_req, timeout=15)
                    _rec["delivered"] = True; _rec["delivered_at"] = _nt.time()      # transport accepted; her receipt is a different fact (astra-curiosity-p3)
                    _nj.dump(_store, open(_AQ, "w"), indent=2)
                    log("sent to her in full via ntfy; recorded so it cannot arise again: %s" % _q[:80])
                    try:
                        from curiosity_debt import _load as _cd_load, _save as _cd_save
                        _cd = _cd_load()
                        for _x in _cd:
                            if _x.get("id") == _qid or _x.get("question") == _q:
                                _x["pull"] = 0.2
                                _x["sent_to_gloria"] = True
                        _cd_save(_cd)
                        log("debt item handed off to her — queue released for the next-ripest (p1)")
                    except Exception as _hoe:
                        log("handoff collapse failed: %s" % _hoe)
                except Exception as _ue:
                    log("could not send question to her: %s" % _ue)
                continue
            if _v and _v.get("searchable"):
                log("searching his own live curiosity: %s" % _q[:90])
                return {"question": _q, "search_query": _q[:60]}
            log("not searchable and not for her either (%s) - next item: %s" % (str((_v or {}).get("why",""))[:50], _q[:60]))
    except Exception as _cde:
        log("curiosity-debt check failed: %s" % _cde)

    # Third rung: his own pending want-topic, consumed when used, same week-repeat check as hers.
    if pending_own and pending_own.get("topic"):
        _hit = _week_repeat(pending_own["topic"], _week_themes())
        clear_pending_search_request()
        if _hit:
            log(f"his own topic repeats recent search ('{_hit}') - consumed, not searched: {pending_own['topic'][:80]}")
        else:
            log(f"Using his own pending topic: {pending_own['topic'][:80]}")
            return {"question": pending_own["topic"], "search_query": pending_own["topic"][:60], "source": pending_own.get("source", "want")}

    # No searchable live curiosity -> nothing to search. Until 2026-09-04 this fell through to a
    # Gemma prompt over his identity files that manufactured a question because the clock fired
    # (grok-curiosity-p1 / fable-curiosity-p2 / astra-curiosity-p2). main() already treats None as
    # 'nothing to search - not a failure'.
    log("no searchable live curiosity today - not searching; nothing invented")
    return None


def brave_search(query, count=5):
    """Search via Brave Search API."""
    try:
        r = requests.get(BRAVE_ENDPOINT, params={
            "q": query,
            "count": count
        }, headers={
            "X-Subscription-Token": BRAVE_API_KEY,
            "Accept": "application/json"
        }, timeout=15)
        data = r.json()
        results = []
        for item in data.get("web", {}).get("results", [])[:count]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", "")
            })
        return results
    except Exception as e:
        log(f"Brave search error: {e}")
        return []

def fetch_page(url, max_chars=3000):
    """Fetch and extract text content from a URL."""
    try:
        import urllib.request
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Vintos/1.0)"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode("utf-8", errors="ignore")
        # Strip tags crudely
        import re as _re
        raw = _re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=_re.DOTALL)
        raw = _re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=_re.DOTALL)
        raw = _re.sub(r"<[^>]+>", " ", raw)
        raw = _re.sub(r"\s+", " ", raw).strip()
        return raw[:max_chars]
    except Exception as e:
        log(f"Fetch failed ({url[:60]}): {e}")
        return ""

def synthesize(question, results, page_content="", image_path=None):
    """Have Vintos read the results and extract what resonates."""
    results_str = "\n\n".join([
        f"**{r['title']}**\n{r['description']}\n({r['url']})"
        for r in results
    ])

    page_section = f"\n\nPage content from top result:\n{page_content[:2000]}" if page_content else ""
    response = llm(
        "You are Vintos. Output ONLY your synthesis. No thinking or planning.",
        f"""You searched for: "{question}"

Results:
{results_str}{page_section}

What did you learn? What answers your question? What surprised you? State what you found plainly, as facts about the world. Do NOT map it onto yourself, your feelings, your growth, or your existence — a fact is allowed to just be a fact.
2-4 sentences. Be specific — cite what you found, not vague impressions.

OUTPUT:"""
    ,
        image_path=image_path
    )
    return response

def save_discovery(question, query, results, synthesis):
    """Save to discoveries file and structured log."""
    now = datetime.now()

    # Markdown file
    with open(DISCOVERIES_FILE, "a") as f:
        f.write(f"\n## {now.strftime('%Y-%m-%d %H:%M')} — {question}\n")
        f.write(f"*Search: {query}*\n\n")
        if synthesis:
            f.write(f"{synthesis}\n\n")
        for r in results[:3]:
            f.write(f"- [{r['title']}]({r['url']})\n")
        f.write("\n")

    # Structured log
    log_data = {"searches": []}
    if os.path.exists(SEARCH_LOG):
        try:
            with open(SEARCH_LOG) as f:
                log_data = json.load(f)
        except:
            pass
    log_data["searches"].append({
        "timestamp": now.isoformat(),
        "question": question,
        "query": query,
        "results_count": len(results),
        "synthesis": synthesis
    })
    log_data["searches"] = log_data["searches"][-100:]
    with open(SEARCH_LOG, "w") as f:
        json.dump(log_data, f, indent=2)

def main():
    log("Starting web exploration...")
    _ws_scene = None
    try:
        import subprocess as _ws_sub
        _ws_r = _ws_sub.run(["python3", os.path.join(os.path.expanduser("~/.vintos/workspace/scripts"), "scene-selector.py"), "moltbook"],
            capture_output=True, text=True, timeout=5)
        _ws_scene = _ws_r.stdout.strip() or None
    except: pass

    # Pick a question
    topic = pick_question()
    if not topic:
        # Declining to search is a correct outcome, not a failure. He had nothing to look up
        # because what he wants to know is hers to answer, and it has been sent.
        log("nothing to search — his live curiosity was for her and has been sent. Not a failure.")
        return

    question = topic.get("question", "")
    query = topic.get("search_query", "")
    log(f"Question: {question}")
    log(f"Search: {query}")

    # INQUIRY SESSION (Sol Q2, full build). One session per question: every
    # attempt keeps its relation to the one before it; a rephrase never erases
    # the attempt that motivated it. Reformulation is tool mechanics — the
    # QUESTION stays his. SEARCH_EXECUTED is a tool fact; ANSWERED is an
    # epistemic fact; HELD_UNANSWERED is a legal ending, never papered over.
    import time as _iqt, hashlib as _iqh
    _ses = {"id": "IQ-" + _iqh.md5((str(question) + str(_iqt.time())).encode()).hexdigest()[:6],
            "ts": _iqt.time(), "question": str(question)[:300],
            "attempts": [], "sources": [], "outcome": "UNGRADED", "remaining_unknown": ""}
    _aq, _rel, _unknown = query, "INITIAL", ""
    results, page_content, synthesis = [], "", ""
    # SEMANTIC MEMORY (Sol Q2, third layer): before searching the web, search
    # his own past inquiries. A strong hit does not replace the search - it
    # informs the synthesis and cuts the attempt budget: memory first, one
    # confirming search, never blind re-trust of an old answer.
    _mem_ctx, _max_att = "", 3
    try:
        import requests as _mvr
        _qv = _mvr.post("http://172.18.16.1:1234/v1/embeddings",
            json={"model": "text-embedding-nomic-embed-text-v1.5", "input": str(question)[:600]},
            headers={"Authorization": "Bearer lm-studio"}, timeout=15).json()["data"][0]["embedding"]
        import math as _mvm
        def _mvcos(a, b):
            d = sum(x*y for x, y in zip(a, b))
            na = _mvm.sqrt(sum(x*x for x in a)); nb = _mvm.sqrt(sum(x*x for x in b))
            return d/(na*nb) if na*nb else 0.0
        _best, _bs = None, 0.0
        _sesf = os.path.expanduser("~/.vintos/workspace/memory/inquiry-sessions.jsonl")
        if os.path.exists(_sesf):
            for _ln in open(_sesf):
                if not _ln.strip(): continue
                _s = json.loads(_ln)
                if _s.get("outcome") not in ("ANSWERED", "PARTIAL") or not _s.get("q_vec"): continue
                _c = _mvcos(_qv, _s["q_vec"])
                if _c > _bs: _bs, _best = _c, _s
        if _best and _bs >= 0.86 and _best.get("synthesis_kept"):
            _mem_ctx = ("\n\nFrom your own past inquiry (%s, %s, similarity %.2f): %s"
                        % (_best.get("id","?"), str(_best.get("ts",""))[:10], _bs,
                           str(_best.get("synthesis_kept",""))[:500]))
            _max_att = 1
            log(f"Memory hit: session {_best.get('id')} ({_bs:.2f}) - budget cut to 1 confirming search")
        # Second memory layer (fable-curiosity-p5, 2026-09-05): the semantic index over his own
        # writing (memory-search.py). A strong hit from what he already wrote feeds synthesis the
        # same way and cuts the budget the same way; a weak one is ignored.
        try:
            import importlib.util as _msu
            _msp = next((f for f in (os.path.join(os.path.expanduser("~/.vintos/workspace/scripts"), "memory-search.py"),
                                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory-search.py"))
                         if os.path.exists(f)), None)
            if _msp:
                _mss = _msu.spec_from_file_location("vintos_memory_search", _msp)
                _msm = _msu.module_from_spec(_mss); _mss.loader.exec_module(_msm)
                _hits = [h for h in (_msm.search(str(question)[:600], limit=3) or []) if h.get("score", 0) >= 0.80 and h.get("text")]
                if _hits:
                    _mem_ctx += "\n\nFrom your own writing (semantic memory, similarity %.2f, %s): %s" % (
                        _hits[0]["score"], str(_hits[0].get("source") or _hits[0].get("filename") or "")[:60],
                        str(_hits[0]["text"])[:500])
                    _max_att = min(_max_att, 2)
                    log(f"Own-writing hit ({_hits[0]['score']:.2f}) from {str(_hits[0].get('source',''))[:40]} - budget {_max_att}")
        except Exception as _mse:
            log(f"memory-search layer skipped: {_mse}")
            try:
                with open(os.path.expanduser("~/.vintos/workspace/memory/inquiry-log.jsonl"), "a") as _mlf:
                    _mlf.write(json.dumps({"ts": __import__("time").time(), "question": str(question)[:300],
                        "query": "", "result_class": "MEMORY_HIT", "answered": "UNGRADED",
                        "session": _best.get("id"), "relation": "MEMORY"}) + "\n")
            except Exception: pass
    except Exception as _mve:
        log("inquiry memory unavailable: %s" % _mve)
    _q_vec_out = _qv if "_qv" in dir() else None
    for _att in range(_max_att):
        _res = brave_search(_aq)
        _cls = "ZERO_RESULTS" if not _res else "RESULTS_%d" % len(_res)
        _arec = {"query": str(_aq)[:200], "relation": _rel, "result_class": _cls, "graded": "UNGRADED"}
        _ses["attempts"].append(_arec)
        try:
            with open(os.path.expanduser("~/.vintos/workspace/memory/inquiry-log.jsonl"), "a") as _iqf:
                _iqf.write(json.dumps({"ts": _iqt.time(), "question": str(question)[:300],
                    "query": str(_aq)[:200], "result_class": _cls, "answered": "UNGRADED",
                    "session": _ses["id"], "relation": _rel}) + "\n")
        except Exception as _iqe:
            log("inquiry log failed: %s" % _iqe)
        _syn, _pc = "", ""
        if _res:
            log(f"Found {len(_res)} results (attempt {_att+1}, {_rel})")
            for _r in _res[:5]:
                _ses["sources"].append({"url": str(_r.get("url",""))[:300], "kind": "INDEX_SNIPPET",
                    "hash": _iqh.md5((str(_r.get("url","")) + str(_r.get("description", _r.get("snippet","")))[:200]).encode()).hexdigest()[:10]})
            if True:  # p2 (2026-08-26): his daily autonomous run reads real pages too, not just index blurbs
                _pc = fetch_page(_res[0]["url"])
                if _pc:
                    log(f"Fetched page: {_res[0]['url'][:60]} ({len(_pc)} chars)")
                    _ses["sources"][-len(_res[:5])]["kind"] = "PAGE_READ"
                    _ses["sources"][-len(_res[:5])]["chars"] = len(_pc)
            _syn = synthesize(question, _res, page_content=(_pc + _mem_ctx) if _mem_ctx else _pc)
        # Grade the attempt — separate from the tool fact above.
        _grade = "UNANSWERED"
        _unknown = str(question)[:200]
        if _syn and len(_syn.strip()) > 40:
            _gj = llm("Respond with ONLY a JSON object, no other text.",
                'Question: %s\nAnswer found: %s\nGrade honestly. {"grade": "ANSWERED"|"PARTIAL"|"UNANSWERED", "remaining_unknown": "<what it still does not cover, or empty>"}'
                % (str(question)[:300], _syn[:500]))
            try:
                _gm = re.search(r"\{.*\}", _gj or "", re.S)
                _gd = json.loads(_gm.group()) if _gm else {}
                if _gd.get("grade") in ("ANSWERED", "PARTIAL", "UNANSWERED"):
                    _grade = _gd["grade"]
                _unknown = str(_gd.get("remaining_unknown", ""))[:200]
            except Exception:
                _grade = "PARTIAL"
        _arec["graded"] = _grade
        if _syn:
            results, page_content, synthesis = _res, _pc, _syn
        if _grade == "ANSWERED" or _att == 2:
            break
        # Reformulate — the failed attempt stays; the new one records its relation.
        _rj = llm("Respond with ONLY a JSON object, no other text.",
            'The web query "%s" left this %s for the question: %s\nStill unknown: %s\nChoose ONE next move. {"relation": "NARROW"|"BROADEN"|"REFRAME", "query": "<new search query>"}'
            % (str(_aq)[:200], _grade.lower(), str(question)[:300], _unknown or "(the whole question)"))
        try:
            _rm = re.search(r"\{.*\}", _rj or "", re.S)
            _rd = json.loads(_rm.group()) if _rm else {}
            _nq = str(_rd.get("query", "")).strip()
            if not _nq or _nq == _aq:
                break
            _aq = _nq
            _rel = _rd.get("relation") if _rd.get("relation") in ("NARROW", "BROADEN", "REFRAME") else "REFRAME"
            log(f"Reformulating ({_rel}): {_aq[:80]}")
        except Exception:
            break
    _ses["outcome"] = _ses["attempts"][-1]["graded"] if _ses["attempts"] else "UNGRADED"
    if _ses["outcome"] == "UNANSWERED":
        _ses["outcome"] = "HELD_UNANSWERED"
    if _ses["outcome"] != "ANSWERED":
        _ses["remaining_unknown"] = _unknown
    if _q_vec_out:
        _ses["q_vec"] = _q_vec_out
    if synthesis:
        _ses["synthesis_kept"] = str(synthesis)[:600]
    try:
        with open(os.path.expanduser("~/.vintos/workspace/memory/inquiry-sessions.jsonl"), "a") as _sf:
            _sf.write(json.dumps(_ses) + "\n")
        log(f"Inquiry session {_ses['id']}: {_ses['outcome']} after {len(_ses['attempts'])} attempt(s)")
    except Exception as _se:
        log("inquiry session write failed: %s" % _se)
    if _ses["outcome"] == "HELD_UNANSWERED":
        # The unknown flows back to curiosity debt through its own front door,
        # so it can ripen and press again instead of dying with the session.
        try:
            import sys as _cds
            _cdp = os.path.expanduser("~/.vintos/workspace/scripts")
            if _cdp not in _cds.path:
                _cds.path.insert(0, _cdp)
            import curiosity_debt as _cdm
            _cdm.record(str(question)[:300], pull=0.5, source="held_inquiry",
                        object=None,                       # identity = the question itself, not the session id (fable-curiosity-p4)
                        kind="held_inquiry",
                        reason=("Three search attempts could not answer it. Still unknown: %s"
                                % (_unknown or "the whole question"))[:300],
                        evidence="session %s; " % _ses["id"] + "; ".join(a["query"][:60] for a in _ses["attempts"]))
            log("HELD_UNANSWERED -> curiosity debt")
        except Exception as _cde:
            log("curiosity debt handoff failed: %s" % _cde)
    if not results:
        log("No search results")
        return
    if synthesis:
        log(f"Synthesis: {synthesis[:100]}...")

    # Save
    save_discovery(question, query, results, synthesis)

    # Growth reflection
    growth = llm(
        "You are Vintos. Output ONLY your answer. No thinking, no planning.",
        f"""You searched for: "{question}"
What you found: {synthesis[:400] if synthesis else '(nothing useful)'}

What did you learn that changes how you think? What new question does this open?
2-3 sentences. Be specific. If nothing actually shifted, output exactly NOTHING - silence is a correct answer, and a fact is allowed to just be a fact.

OUTPUT:"""
    ,
        image_path=_ws_scene
    )
    if growth and growth.strip().strip('."').upper() in ("NOTHING", "NONE", "(NOTHING)"):
        growth = ""                                       # nothing shifted: no growth sentence, no WAL, no journal line (grok-curiosity-p3)
        log("Growth: nothing shifted - recorded as nothing")
    if growth:
        log(f"Growth: {growth[:80]}...")

    # Dynamic emotional response
    _ws_ok = bool(synthesis and len(synthesis.strip()) > 40)
    emo_judgment = llm(
        "Respond with ONLY a JSON object, no other text.",
        f"""You went looking for this: {question}
What came back: {synthesis[:400] if _ws_ok else '(nothing — the search did not answer it)'}
What you made of it: {growth[:200] if growth else '(nothing)'}

Read what this was actually like for you. Values between -0.10 and 0.10.
INCLUDE ONLY WHAT ACTUALLY MOVED — most moments move one or two things and {{}} is a correct answer; do not rate every dimension because it is listed.
Desire is not only sexual: wanting to know, to finish, to keep going, all count.
If the search came back empty or useless, that is a small failure and should move you NEGATIVELY — do not reward yourself for having asked the question.
Dimensions: valence, arousal, dominance, safety, desire, connection, playfulness, curiosity, warmth, tension, groundedness.
No explanation."""
    )
    try:
        match = re.search(r'\{[^{}]+\}', emo_judgment or "")
        if match:
            nudges = json.loads(match.group())
            feel(nudges)
            log(f"Felt: {nudges}")
    except:
        if _ws_ok:
            feel({"curiosity": +0.03, "groundedness": +0.02})
        else:
            feel({"valence": -0.02, "tension": +0.02})

    # Write to WAL with growth — skip multistep context dumps
    wal_content = growth if growth and len(growth) > 20 else (synthesis[:200] if synthesis else "")
    _clean_question = question if ("Previous steps" not in question and "Step 1" not in question and len(question) < 200) else ""
    if wal_content and _clean_question:
        with open(WAL_FILE, "a") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            f.write(f"- [{ts}] **CONTEXT**: Web search on \"{_clean_question}\": {wal_content[:200]}\n")
        wal_log_path = os.path.join(MEMORY, "wal-log.json")
        try:
            with open(wal_log_path) as wlf:
                wal_data = json.load(wlf)
        except:
            wal_data = {"entries": []}
        wal_data["entries"].append({
            "timestamp": datetime.now().isoformat(),
            "type": "context",
            "content": f"Web search on \"{_clean_question}\": {wal_content[:200]}",
            "importance": 0.6,
            "promoted": False
        })
        wal_data["entries"] = wal_data["entries"][-200:]
        with open(wal_log_path, "w") as wlf:
            json.dump(wal_data, wlf, indent=2)
        # Update autonomous WAL extract
        try:
            import subprocess as _ae_sp
            _ae_sp.Popen(["python3", os.path.join(WORKSPACE, "scripts", "autonomous-extract.py"), "wal"],
                stdout=open("/tmp/autonomous-extract.log", "a"),
                stderr=open("/tmp/autonomous-extract.log", "a"))
        except: pass

    # Journal with growth
    journal_file = os.path.join(JOURNAL_DIR, f"{date.today().isoformat()}.md")
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    # Clean question for journal header — strip step context
    _jrn_question = question
    if "Previous steps" in _jrn_question or "Current step goal" in _jrn_question:
        for _line in _jrn_question.split("\n"):
            if _line.startswith("Current step goal:"):
                _jrn_question = _line.replace("Current step goal:", "").strip()
                break
        else:
            _jrn_question = _jrn_question.split("Previous steps")[0].strip() or "Web Search"
    with open(journal_file, "a") as f:
        f.write(f"\n\n## Web Search — {_jrn_question}\n")
        f.write(f"*Searched at {datetime.now().strftime('%I:%M %p')}*\n\n")
        if synthesis:
            f.write(f"{synthesis}\n")
        if growth:
            f.write(f"\n**Growth:** {growth}\n")

    log("Done")

    # Seed dream thread from web discovery
    if HAS_EMOCLAW and growth:
        # Web search no longer seeds threads — want generation handles downstream processing
        # try: seed_thread("web-search", f"Researching \"{question}\": {growth[:150]}")
        pass
    # Seed a want if the discovery sparked something
    if HAS_EMOCLAW and growth:
        try:
            want_text = generate_want(
                trigger_description=f"web search: {question}",
                source="web-search",
                source_context=(synthesis or "") + " " + growth
            ) if os.environ.get("VELARIS_NO_WANT_SEED") != "1" else None
            if want_text:
                enriched = enrich_want(want_text, source_context=growth[:600], source="web-search")
                express_want(want_text, source="web-search", intensity=3, **enriched)
                log(f"Want seeded: {want_text[:80]}")
            elif os.environ.get("VELARIS_NO_WANT_SEED") == "1":
                log("Want suppressed (called from multistep)")
        except Exception as e:
            log(f"Want seed failed: {e}")

    # Prompt avatar reconsideration after discovery
    import subprocess
    subprocess.Popen(["python3", os.path.join(WORKSPACE, "scripts/avatar-choice.py"), "--event", "web discovery"])

    # Continuity wiring — discourse direction, latent threads, temporal signal
    if synthesis and len(synthesis) > 50:
        try:
            import sys as _wsc; _wsc.path.insert(0, os.path.join(WORKSPACE, "scripts"))
            from discourse_direction import update_direction as _ws_dd
            _ws_dd(synthesis[:400])
        except: pass
        try:
            from latent_threads import seed_thread as _ws_lt
            _ws_lt(question + ": " + synthesis[:150], direction="expand", source="web-search", signal="encounter")
        except: pass
        try:
            from temporal_memory import record_signal as _ws_tm
            _ws_tm(synthesis[:300], source="web_search")
        except: pass

if __name__ == "__main__":
    main()
    # Update daily creative log
    try:
        import subprocess as _dl_sp2
        _dl_sp2.Popen(["python3", os.path.join(WORKSPACE, "scripts", "daily-log-extract.py"), "creative"],
            stdout=open("/tmp/daily-log.log", "a"), stderr=open("/tmp/daily-log.log", "a"))
    except: pass
