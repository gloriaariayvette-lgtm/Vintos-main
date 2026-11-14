#!/usr/bin/env python3
"""belief_revision_answer.py - who answers a check question: his own records first, then a LOCAL checker model.

Gloria, 14 November 2026, option (b): when the back-propagation (belief_revision.localize) needs to know whether one
of his beliefs on a contradiction's line really holds, the question is answered by his own records and, when they do
not settle it, by a checker model that runs on Aegis. Anything that touches HER words is never asked: line_of() never
offers her words as a question, and belief_revision_live sends what stands against her words to her instead.

  1. Records. A record that states the belief's standing outright settles it (records.settle): for a tension, the
     ledger saying it was REVOKED or CONTRADICTED (fails) or CONFIRMED by her explicit answer (holds). Settled once:
     the same record read again is not a second witness, so a second opinion on that belief goes to the checker
     (with the record in front of it).
  2. Checker. The belief, how he came to it (the causality chain: the beliefs and steps it was derived from) and the
     records that bear on it (the tension's evidence, the hypothesis's nightly marks, his memories that share its
     words) go to AEON on the house shim's Aegis-only lane (/gemma-aegis-local: provider aegis_gemma, no hosted
     fallback). A reply that did not come from AEON is discarded. Nothing is sent anywhere else: check_url refuses
     every other host and path before any call. No paid model is called.
  3. Unknown. The checker says holds / fails / unsure with a confidence. "unsure", a confidence under CONFIDENT_AT,
     an unreadable reply, a wrong model, a timeout - every one of them is "unknown" (None), which adds no evidence.

Each answer carries its provenance: who answered (records / checker / none), which record or which model and lane,
the opinion number, the checker's confidence. Provenance holds ids, kinds and numbers, never the text.

The accuracy each answer is weighed with is measured, not assumed: CHECKER_ACCURACY is the checker's measured share
of right definite answers on the development seeds of experiments/contradiction-backprop/bench_answerer.py.
"""
import json, os, random, re, time, urllib.error, urllib.parse, urllib.request

CHECKER_URL = "http://127.0.0.1:8599/gemma-aegis-local/v1/chat/completions"
CHECKER_MODEL = "aeon/gemma-4-12b"
ALLOWED_HOSTS = ("127.0.0.1", "localhost", "::1")
SHIM_PORT = 8599
ALLOWED_PATH = "/gemma-aegis-local/v1/chat/completions"   # the shim's AEON-on-Aegis lane, exactly: no pool spill,
                                                          # no hosted fallback (bin/vintos_claude_shim.py provider_chain)
AEON_PROVIDERS = ("aegis_gemma",)
RECORD_ACCURACY = 0.95       # a record that states the standing outright: right unless the record itself is wrong
CHECKER_ACCURACY = 0.97      # measured on the development seeds (bench_answerer.py: 849 of 868 definite answers
                             # right, 0.978, rounded down); frozen before the held-out run
CONFIDENT_AT = 70            # a checker verdict below this confidence is "unknown"
TEMPERATURE = 0.6            # separate opinions are separate draws, with the records in a different order
MAX_TOKENS = 60
TIMEOUT_S = 90
MAX_RECORDS = 12
MAX_CHARS = 360              # one record line, clipped
REVISION_LOG = "belief-revisions.jsonl"      # belief_revision_live.LOG_NAME: what this module itself changed
PRIORITY_FILE = "/tmp/velaris-chat-priority"   # her live chat has the GPU: no check is asked while it is fresh

SYSTEM = (
    "You check whether one belief holds, using only the records you are given. "
    "A record of what was observed outweighs anyone's earlier belief, hope or inference, including the belief's own "
    "derivation. A later observation outweighs an earlier one. A stated rule plus an observation can settle it. "
    "If the records do not show whether the belief holds, the verdict is unsure - do not guess from how plausible "
    "it sounds or from how it was derived. "
    'Reply with JSON only: {"verdict": "holds" | "fails" | "unsure", "confidence": <0-100>}')


def check_url(url):
    """The checker may only reach the house shim's AEON-only lane on this machine. Anything else is refused."""
    u = urllib.parse.urlparse(url or "")
    try:
        port = u.port
    except ValueError:
        port = None
    if u.scheme != "http" or u.hostname not in ALLOWED_HOSTS or u.username or u.password or u.query \
            or u.params or u.fragment or port != SHIM_PORT:
        raise ValueError("belief revision checker: only the local house shim is allowed, not %r" % (u.hostname or url))
    # the shim routes AEON-only on this exact path; any other /gemma-aegis* path may fall back to a hosted model
    if u.path != ALLOWED_PATH:
        raise ValueError("belief revision checker: path %s can reach another provider; only %s" % (u.path, ALLOWED_PATH))
    return url


def is_aeon(provider, model):
    return str(provider) in AEON_PROVIDERS and "aeon" in str(model).lower()


def _urllib_transport(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read()


def _clip(s, n=MAX_CHARS):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 3] + "..."


def messages(ctx, opinion=1):
    """The checker's prompt. Opinion k sees the same records in its own seeded order."""
    recs = [_clip(r) for r in (ctx.get("records") or []) if str(r or "").strip()][:MAX_RECORDS]
    random.Random("opinion:%d:%s" % (opinion, ctx.get("statement", ""))).shuffle(recs)
    user = "BELIEF: %s\n\nHOW HE CAME TO IT: %s\n\nRECORDS:\n%s\n\nDoes the belief hold?" % (
        _clip(ctx.get("statement"), 500), _clip(ctx.get("derivation") or "not recorded", 700),
        "\n".join("- " + r for r in recs) if recs else "(none)")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


VERDICT = re.compile(r'"?verdict"?\s*[:=]\s*"?(holds|fails|unsure)', re.I)
CONF = re.compile(r'"?confidence"?\s*[:=]\s*"?(\d{1,3})', re.I)


def parse(text):
    """(verdict, confidence) from the checker's reply; (None, 0) when it cannot be read."""
    t = str(text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").split("\n", 1)[-1]
    v, c = None, 0
    try:
        d = json.loads(t[t.index("{"):t.rindex("}") + 1])
        v, c = str(d.get("verdict", "")).lower(), int(float(d.get("confidence", 0)))
    except (ValueError, TypeError, AttributeError):
        m, n = VERDICT.search(t), CONF.search(t)
        v, c = (m.group(1).lower() if m else None), (int(n.group(1)) if n else 0)
    if v not in ("holds", "fails", "unsure"):
        return None, 0
    return v, max(0, min(100, c))


def _priority_fresh(path=None):
    path = path or PRIORITY_FILE
    try:
        return time.time() - os.path.getmtime(path) < 600
    except OSError:
        return False


def ask_checker(ctx, opinion=1, transport=None, url=None, model=None, timeout=TIMEOUT_S):
    """One checker call. {"verdict", "confidence", "status", "provider", "model", "latency_s"}; never raises."""
    out = {"verdict": None, "confidence": 0, "status": "error", "provider": "", "model": "", "latency_s": None}
    try:
        url = check_url(url or os.environ.get("BELIEF_REVISION_CHECKER_URL") or CHECKER_URL)
    except ValueError as e:
        out["status"] = "refused: %s" % str(e)[:120]
        return out
    if transport is None and _priority_fresh():
        out["status"] = "deferred: her chat has priority"
        return out
    body = {"model": model or CHECKER_MODEL, "messages": messages(ctx, opinion), "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS, "seed": int(opinion)}
    t0 = time.monotonic()
    try:
        status, headers, raw = (transport or _urllib_transport)(url, body, timeout)
        d = json.loads(raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw)
    except Exception as e:
        out.update(status="transport: %s" % type(e).__name__, latency_s=round(time.monotonic() - t0, 2))
        return out
    out["latency_s"] = round(time.monotonic() - t0, 2)
    headers = headers or {}
    out["provider"] = str(headers.get("x-vintos-provider") or d.get("provider") or "")
    out["model"] = str(headers.get("x-vintos-model") or d.get("model") or "")
    if status != 200:
        out["status"] = "http %s" % status
        return out
    if not is_aeon(out["provider"], out["model"]):
        out["status"] = "wrong_model"                       # answered by something that is not AEON: discarded
        return out
    try:
        text = d["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        text = ""
    v, c = parse(text)
    out.update(status="ok" if v else "unreadable", verdict=v, confidence=c)
    return out


class Answerer:
    """ask(node) for belief_revision.localize: {"answer": True | False | None, "accuracy", "provenance"}.

    records: an object with settle(node) -> None | (bool, source label) and context(node) -> None | {"statement",
    "derivation", "records": [lines]}. StoreRecords reads his stores; the benchmark has a synthetic one."""

    def __init__(self, records, transport=None, url=None, model=None, checker_accuracy=None, max_calls=None):
        self.records, self.transport, self.url, self.model = records, transport, url, model
        self.checker_accuracy = float(checker_accuracy or CHECKER_ACCURACY)
        self.max_calls = max_calls
        self.calls = 0
        self.opinions = {}
        self.log = []

    def __call__(self, node):
        k = self.opinions[node] = self.opinions.get(node, 0) + 1
        prov = {"node": node, "opinion": k}
        settled = None
        if k == 1:
            try:
                settled = self.records.settle(node)
            except Exception:
                settled = None
        if settled is not None:
            ans, src = settled
            prov.update(by="records", source=str(src)[:80])
            return self._done({"answer": bool(ans), "accuracy": RECORD_ACCURACY, "provenance": prov})
        try:
            ctx = self.records.context(node)
        except Exception:
            ctx = None
        if not ctx or not str(ctx.get("statement") or "").strip():
            prov.update(by="none", status="no record text for this belief")
            return self._done({"answer": None, "accuracy": 0.5, "provenance": prov})
        if self.max_calls is not None and self.calls >= self.max_calls:
            prov.update(by="none", status="checker budget spent")
            return self._done({"answer": None, "accuracy": 0.5, "provenance": prov})
        self.calls += 1
        r = ask_checker(ctx, k, self.transport, self.url, self.model)
        prov.update(by="checker", model=r["model"][:60], provider=r["provider"][:40], status=r["status"][:80],
                    verdict=r["verdict"], confidence=r["confidence"])
        ans = None
        if r["status"] == "ok" and r["verdict"] in ("holds", "fails") and r["confidence"] >= CONFIDENT_AT:
            ans = r["verdict"] == "holds"
        return self._done({"answer": ans, "accuracy": self.checker_accuracy, "provenance": prov})

    def _done(self, a):
        self.log.append(a)
        return a


# -- his records -----------------------------------------------------------------------------------------------
WORD = re.compile(r"[a-z][a-z']{3,}")
STOP = set("that this with from have were what when they them their there about would could should been into "
           "your yours mine just than then also over more some only very much like does said says will".split())


def _words(s):
    return {w for w in WORD.findall(str(s or "").lower()) if w not in STOP}


class StoreRecords:
    """His records, read once from the memory directory, as the answerer needs them. Read-only."""

    def __init__(self, mem, graph=None):
        import belief_revision_sources as S
        self.g = graph
        load = lambda n, d: S._load(mem, n, d)
        self.own = {str(r.get("node")) for r in load(REVISION_LOG, []) if isinstance(r, dict) and r.get("node")}
        rows = S._rows
        self.tensions = {str(t.get("tension_id")): t for t in rows(load("tension-ledger.json", {}), "tensions")}
        self.t_ev = {}
        for t in self.tensions.values():
            for e in t.get("evidence") or []:
                if isinstance(e, dict) and e.get("evidence_id"):
                    self.t_ev[str(e["evidence_id"])] = (t, e)
        self.hyps = {str(h.get("hypothesis_id")): h for h in rows(load("causality-hypotheses.json", {}), "hypotheses")
                     if h.get("hypothesis_id")}
        self.marks_by_ev = {}
        for h in self.hyps.values():
            for m in h.get("marks") or []:
                if isinstance(m, dict):
                    for e in m.get("evidence_ids") or []:
                        self.marks_by_ev.setdefault(str(e), []).append((h, m))
        self.sediment = rows(load("belief-sediment.json", {}), "beliefs")
        self.csm = rows(load("causal-self-model.json", {}), "entries")
        self.claims = {str(t.get("id")): t for t in rows(load("claim-hold-trials.json", {}), "trials") if t.get("id")}
        self.smc = [r for r in load("self-model-corrections.jsonl", []) if isinstance(r, dict)]
        self.flags = {str(f.get("id")): f for f in (load("hallucination-flags.json", []) or [])
                      if isinstance(f, dict) and f.get("id")}
        self.ra = {str(e.get("id")): e for e in rows(load("reality-anchor.json", {}), "events") if e.get("id")}
        dm = load("durable-memory.json", [])
        self.memories = [m for m in (dm if isinstance(dm, list) else []) if isinstance(m, dict)
                         and m.get("standing") != "invalidated"]

    # -- a record that states the standing outright
    def settle(self, node):
        if node.startswith("t:tension:"):
            t = self.tensions.get(node[10:])
            # a status this module's own live revision set is not a witness: it would confirm itself. Known by the
            # revision log, not only the record's mark, which another organ's rewrite can drop (review 4)
            if t and not t.get("belief_revision") and node not in self.own:
                st = str(t.get("status") or "")
                if st in ("REVOKED", "CONTRADICTED") or t.get("lifecycle") == "CONTRADICTED":
                    return False, "tension-ledger status %s" % (st or t.get("lifecycle"))
                if st == "CONFIRMED":
                    return True, "tension-ledger status CONFIRMED"
        return None

    # -- what the checker reads
    def _memories(self, text, n=3):
        want = _words(text)
        if len(want) < 2:
            return []
        scored = []
        for m in self.memories:
            body = " ".join(str(m.get(k) or "") for k in ("event", "exact_words", "what_changed"))
            s = len(want & _words(body))
            if s >= 3:
                scored.append((s, str(m.get("occurred_at") or ""), body))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return ["memory (%s): %s" % (when[:10] or "undated", body) for _, when, body in scored[:n]]

    def _derivation(self, node):
        """The causality chain: what this belief was derived from, as statements where the record has them."""
        g = self.g
        if g is None or node not in g.nodes or g.nodes[node]["assumption"]:
            return "one of his recorded sources" if node in getattr(g, "nodes", {}) else ""
        parts = []
        for j in g.nodes[node]["justifications"]:
            names = [a for a in j if not a.startswith("rule:")]
            said = [self.statement(a) or "(a source not captured)" for a in names]
            parts.append(" and ".join(_clip(s, 160) for s in said) or "(no recorded sources)")
        return "he inferred it from: " + " | or from: ".join(parts[:4]) if parts else ""

    def statement(self, node):
        c = self._raw(node)
        return c[0] if c else ""

    def _raw(self, node):
        """(statement, [record lines]) for a node, from the stores; None when there is no text for it."""
        p, _, key = node.partition(":")
        kind, _, rest = key.partition(":")
        if node.startswith("t:tension:"):
            t = self.tensions.get(node[10:])
            if not t:
                return None
            recs = []
            for e in t.get("evidence") or []:
                if not isinstance(e, dict) or e.get("invalid") or e.get("under_influence"):
                    continue
                who = {"E1": "Gloria said", "E2": "he said", "E3": "his private note", "E4": "Gloria answered"}.get(
                    e.get("channel"), "record")
                recs.append("%s (%s, %s): %s" % (who, str(e.get("at") or "")[:10], e.get("polarity") or "?",
                                                 e.get("quote") or ""))
            return "%s %s" % (t.get("canonical") or "", ("(%s)" % t["direction"]) if t.get("direction") else ""), recs
        if node.startswith("t:ev:"):
            hit = self.t_ev.get(node[5:])
            if not hit:
                return None
            t, e = hit
            return (str(e.get("quote") or ""),
                    ["it was recorded as %s the tension: %s" % (e.get("polarity") or "bearing on", t.get("canonical") or "")])
        if node.startswith("c:hyp:"):
            h = self.hyps.get(node[6:])
            if not h:
                return None
            recs = ["test: %s" % (h.get("test") or "")]
            for m in (h.get("marks") or [])[-8:]:
                if isinstance(m, dict) and not m.get("voided"):
                    recs.append("night %s: %s - %s" % (str(m.get("date") or "")[:10], m.get("verdict") or "?",
                                                      m.get("reason") or m.get("outcome") or ""))
            return str(h.get("hypothesis") or ""), recs
        if node.startswith("c:ev:"):
            rows = self.marks_by_ev.get(node[5:]) or []
            if not rows:
                return None
            h, m = rows[-1]
            return (str(m.get("evidence") or m.get("outcome") or ""),
                    ["night %s, for the hypothesis '%s': %s" % (str(m.get("date") or "")[:10], h.get("hypothesis") or "",
                                                                m.get("reason") or "") for h, m in rows[-4:]])
        if node.startswith("c:belief:"):
            try:
                b = self.sediment[int(node[9:])]
            except (ValueError, IndexError):
                return None
            hs = [self.hyps.get(str(h)) for h in b.get("hypothesis_ids") or []]
            return str(b.get("pattern") or ""), ["from the hypothesis: %s" % h.get("hypothesis") for h in hs if h]
        if node.startswith("c:csm:"):
            try:
                e = self.csm[int(node[6:])]
            except (ValueError, IndexError):
                return None
            return "when %s, he tends to %s" % (e.get("trigger") or "?", e.get("tendency") or "?"), []
        if node.startswith("h:claim:"):
            t = self.claims.get(node[8:])
            if not t:
                return None
            return str(t.get("claim") or ""), ["his reason then: %s" % (t.get("his_reason") or "")]
        if node.startswith("m:sentence:"):
            try:
                r = self.smc[int(node[11:])]
            except (ValueError, IndexError):
                return None
            return str(r.get("supersedes") or ""), []
        if node.startswith("f:journal:"):
            f = self.flags.get(node[10:])
            if not f:
                return None
            return str(f.get("excerpt") or ""), ["journal entry: %s" % (f.get("entry_header") or "")]
        if node.startswith("r:"):
            e = self.ra.get(node[2:])
            if not e:
                return None
            return str(e.get("statement") or ""), ["context: %s" % (e.get("context") or "")]
        return None

    def context(self, node):
        raw = self._raw(node)
        if not raw or not str(raw[0]).strip():
            return None
        statement, recs = raw
        return {"statement": statement, "derivation": self._derivation(node),
                "records": [r for r in recs if r] + self._memories(statement)}
