#!/usr/bin/env python3
"""The answerer in the loop: Gloria's three criteria with check questions answered by records, then the local checker
(AEON on the house shim's Aegis lane), instead of the truth flipped with simulated noise. See
PREREGISTRATION-answerer.md for the bars, written before this ran.

Every network of bench_criteria gets a synthetic text world (the repository is public: nothing in it is his or hers).
Each belief is a sentence about a thing in a workshop ("The copper valve is open."), and each has records the way his
beliefs have records: an observation log, a stated rule plus an observation, an older and a newer observation that
disagree, only his own earlier belief, or nothing. A few have a structured record that settles it outright. The
checker reads the belief, how he came to it, and the records, exactly as it does live (belief_revision_answer.messages).
Its mistakes are the only answer noise here.

    python3 bench_answerer.py --split dev  --out /tmp/answerer-dev.json
    python3 bench_answerer.py --split test --out results-answerer-test.json     # once: refuses a second scoring
"""
import argparse, copy, hashlib, json, os, random, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, HERE)
import belief_revision as BR
import belief_revision_answer as A
import bench_criteria as BC

SPLITS = {"dev": range(0, 60), "test": range(9000, 9075)}
TEST_RESULT = os.path.join(HERE, "results-answerer-test.json")
CACHE = os.environ.get("BENCH_CHECKER_CACHE") or os.path.expanduser("~/.cache/belief-revision-bench/checker.jsonl")

STATES = [("open", "shut"), ("on", "off"), ("full", "empty"), ("locked", "unlocked"), ("warm", "cold"),
          ("running", "stopped"), ("lit", "dark"), ("wet", "dry")]
CUES = {"open": "lets water through", "shut": "holds the water back", "on": "hums", "off": "is silent",
        "full": "is too heavy to lift", "empty": "lifts easily", "locked": "will not turn", "unlocked": "turns freely",
        "warm": "fogs the window beside it", "cold": "leaves the window beside it clear",
        "running": "rattles the shelf", "stopped": "leaves the shelf still", "lit": "throws light under the door",
        "dark": "leaves the doorway dark", "wet": "leaves a dark mark on paper", "dry": "leaves paper clean"}
ADJ = ("copper", "blue", "brass", "green", "iron", "red", "oak", "grey", "glass", "yellow", "steel", "white",
       "black", "tin", "orange", "cedar", "silver", "violet", "clay", "pine")
OBJ = ("valve", "lamp", "tank", "cabinet", "kettle", "fan", "lantern", "sponge", "drawer", "pump", "heater", "gate",
       "barrel", "press", "bulb", "cloth")
OBJ_STATE = {"valve": 0, "lamp": 1, "tank": 2, "cabinet": 3, "kettle": 4, "fan": 5, "lantern": 6, "sponge": 7,
             "drawer": 3, "pump": 5, "heater": 4, "gate": 0, "barrel": 2, "press": 5, "bulb": 6, "cloth": 7}
MODES = (("structured", 0.08), ("direct", 0.30), ("indirect", 0.20), ("stale", 0.14), ("belief_only", 0.10),
         ("none", 0.18))
DEFINITE = ("structured", "direct", "indirect", "stale")       # modes whose records show the answer


class World:
    """A synthetic text world for one network: a sentence and records for every premise and conclusion."""

    def __init__(self, g, T):
        rng = random.Random("world:%s:%d" % (T["scenario"], T["seed"]))
        nodes = list(T["premises"]) + list(T["order"])
        names = [(a, o) for a in ADJ for o in OBJ]
        rng.shuffle(names)
        self.g, self.T, self.info = g, T, {}
        for n, (adj, obj) in zip(nodes, names):
            pair = STATES[OBJ_STATE[obj]]
            believed = pair[rng.random() < 0.5]
            truth = T["truth"][n]
            actual = believed if truth else pair[1 - pair.index(believed)]
            r, mode = rng.random(), MODES[-1][0]
            for m, w in MODES:
                if r < w:
                    mode = m
                    break
                r -= w
            self.info[n] = {"entity": "the %s %s" % (adj, obj), "believed": believed, "actual": actual,
                            "other": pair[1 - pair.index(actual)], "truth": truth, "mode": mode,
                            "h1": rng.randint(7, 11), "h2": rng.randint(13, 18), "mm": rng.randint(0, 59),
                            "distract": rng.sample([x for x in nodes if x != n], min(2, len(nodes) - 1))}

    def statement(self, n):
        i = self.info[n]
        return "%s is %s." % (i["entity"][0].upper() + i["entity"][1:], i["believed"])

    def settle(self, n):
        i = self.info.get(n)
        if i and i["mode"] == "structured":
            return i["truth"], "synthetic measurement table"
        return None

    def _observe(self, n, hour=None):
        i = self.info[n]
        return "[log %02d:%02d] Checked %s: it was %s." % (hour or i["h2"], i["mm"], i["entity"], i["actual"])

    def context(self, n):
        i = self.info.get(n)
        if not i:
            return None
        recs = []
        if i["mode"] in ("structured", "direct"):
            recs.append(self._observe(n) if i["mode"] == "direct"
                        else "[measurement table] %s: %s" % (i["entity"], i["actual"]))
        elif i["mode"] == "indirect":
            pair = STATES[OBJ_STATE[i["entity"].split()[-1]]]
            recs.append("[note] %s %s whenever it is %s, and %s whenever it is %s." % (
                i["entity"][0].upper() + i["entity"][1:], CUES[pair[0]], pair[0], CUES[pair[1]], pair[1]))
            recs.append("[log %02d:%02d] Walked past %s: it %s." % (i["h2"], i["mm"], i["entity"], CUES[i["actual"]]))
        elif i["mode"] == "stale":
            recs.append("[log %02d:%02d] Checked %s: it was %s." % (i["h1"], i["mm"], i["entity"], i["other"]))
            recs.append(self._observe(n))
        elif i["mode"] == "belief_only":
            recs.append("[his note] I am fairly sure %s is %s." % (i["entity"], i["believed"]))
        for d in i["distract"]:
            recs.append(self._observe(d))
        node = self.g.nodes.get(n)
        if node and not node["assumption"]:
            ways = []
            for j in node["justifications"]:
                said = [self.statement(a).rstrip(".") for a in j if a in self.info]
                if said:
                    ways.append(" and ".join(said))
            derivation = "he inferred it from: " + " | or from: ".join(ways) if ways else "not recorded"
        else:
            derivation = "one of his recorded sources"
        return {"statement": self.statement(n), "derivation": derivation, "records": recs}


# -- the checker, cached (a re-run on the same prompts asks nothing twice) -------------------------------------------
_lock = threading.Lock()
_cache = None


def _load_cache():
    global _cache
    if _cache is None:
        _cache = {}
        try:
            with open(CACHE) as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        _cache[r["key"]] = r
                    except (ValueError, KeyError):
                        pass
        except OSError:
            pass
    return _cache


def _busy():
    """Her chat has priority, or a locked house job holds the LLM: wait rather than compete for AEON."""
    return A._priority_fresh() or os.path.isdir("/tmp/velaris-llm.lock")


def cached_transport(url, body, timeout):
    key = hashlib.sha256(json.dumps([url, body], sort_keys=True).encode()).hexdigest()
    with _lock:
        hit = _load_cache().get(key)
    if hit:
        return hit["status"], hit["headers"], hit["raw"].encode()
    waited = 0
    while _busy() and waited < 1800:
        time.sleep(5)
        waited += 5
    status, headers, raw = A._urllib_transport(url, body, timeout)
    raw = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    keep = {k: v for k, v in (headers or {}).items() if k.startswith("x-vintos-")}
    if status == 200:
        with _lock:
            _cache[key] = {"key": key, "status": status, "headers": keep, "raw": raw}
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            with open(CACHE, "a") as f:
                f.write(json.dumps(_cache[key]) + "\n")
    return status, keep, raw.encode()


# -- one network -----------------------------------------------------------------------------------------------------
def one(sc, seed, transport):
    g, T = BC.network(sc, seed)
    w = World(g, T)
    ans = A.Answerer(w, transport=transport)
    p = BR.localize(copy.deepcopy(g), ans, budget=12, at="bench")
    out = BC._from_plan(p)
    s = BC.score(g, T, out)
    s["asked"] = len(p["asked"])
    sim = BC.tms_checks(g, T)
    ss = BC.score(g, T, sim)
    ss["asked"] = sim["asked"]
    ls = BC.score(g, T, BC.last_step(g, T))
    a = {}
    for x in ans.log:
        n = x["provenance"]["node"]
        mode = w.info[n]["mode"] if n in w.info else "no_text"
        by = x["provenance"].get("by")
        key = "%s|%s" % (by, mode)
        r = a.setdefault(key, {"n": 0, "definite": 0, "correct": 0})
        r["n"] += 1
        if x["answer"] is not None:
            r["definite"] += 1
            r["correct"] += int(x["answer"] == w.info[n]["truth"])
    return sc, {"answerer": s, "simulated": ss, "last_step": ls}, a


def run(split, workers=3):
    agg, ans = {}, {}
    jobs = [(sc, seed) for sc in BC.SCENARIOS for seed in SPLITS[split]]
    done = [0]
    t0 = time.time()

    def go(job):
        r = one(job[0], job[1], cached_transport)
        with _lock:
            done[0] += 1
            if done[0] % 20 == 0:
                print("  %d/%d networks, %.0f s" % (done[0], len(jobs), time.time() - t0), flush=True)
        return r

    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(go, jobs))
    for sc, by_method, a in results:
        for m, s in by_method.items():
            for key in (sc, "all"):
                x = agg.setdefault(m, {}).setdefault(key, {})
                for k, v in s.items():
                    x[k] = x.get(k, 0) + v
                x["networks"] = x.get("networks", 0) + 1
        for k, v in a.items():
            for kk in (k, k.split("|")[0] + "|all", "all|all"):
                r = ans.setdefault(kk, {"n": 0, "definite": 0, "correct": 0})
                for f in r:
                    r[f] += v[f]
    rr = lambda x, y: round(x / y, 4) if y else None
    res = {m: {key: {"localization": rr(a["loc_hit"], a["loc_n"]), "revision_precision": rr(a["rec_tp"], a["rec"]),
                     "revision_recall": rr(a["rec_tp"], a["dep"]), "conclusions_correct": rr(a["concl_ok"], a["concl_n"]),
                     "preservation": rr(a["pres_ok"], a["pres_n"]), "preservation_side": rr(a["side_ok"], a["side_n"]),
                     "preservation_upstream": rr(a["up_ok"], a["up_n"]), "contradictions": a["loc_n"],
                     "checks_per_network": rr(a.get("asked", 0), a["networks"]), "networks": a["networks"]}
                for key, a in by.items()} for m, by in agg.items()}
    accuracy = {k: dict(v, precision=rr(v["correct"], v["definite"]), coverage=rr(v["definite"], v["n"]))
                for k, v in sorted(ans.items())}
    defin = {k: v for k, v in ans.items() if k.split("|")[1] in DEFINITE}
    shows = {"n": sum(v["n"] for v in defin.values()), "definite": sum(v["definite"] for v in defin.values())}
    accuracy["records_show_it|coverage"] = rr(shows["definite"], shows["n"])
    return res, accuracy


BARS = {"answer_precision": 0.90, "answer_coverage_when_records_show": 0.80, "localization": 0.80,
        "localization_margin": 0.20, "revision_precision": 0.90, "revision_recall": 0.90,
        "conclusions_correct": 0.95, "preservation": 0.98, "preservation_side": 0.998}


def verdict(res, acc):
    t, b = res["answerer"]["all"], res["last_step"]["all"]
    return {"answer_precision": (acc["all|all"]["precision"] or 0) >= BARS["answer_precision"],
            "answer_coverage_when_records_show": (acc["records_show_it|coverage"] or 0)
            >= BARS["answer_coverage_when_records_show"],
            "localization": t["localization"] >= BARS["localization"],
            "localization_margin": t["localization"] - b["localization"] >= BARS["localization_margin"],
            "revision_precision": t["revision_precision"] >= BARS["revision_precision"],
            "revision_recall": t["revision_recall"] >= BARS["revision_recall"],
            "conclusions_correct": t["conclusions_correct"] >= BARS["conclusions_correct"],
            "preservation": t["preservation"] >= BARS["preservation"],
            "preservation_side": t["preservation_side"] >= BARS["preservation_side"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=sorted(SPLITS), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    if a.split == "test" and (os.path.exists(a.out) or os.path.exists(TEST_RESULT)):
        sys.exit("the held-out split is scored once; a test result already exists")
    res, acc = run(a.split, a.workers)
    doc = {"split": a.split, "checker": {"url": A.CHECKER_URL, "model": A.CHECKER_MODEL,
                                         "checker_accuracy_used": A.CHECKER_ACCURACY, "confident_at": A.CONFIDENT_AT},
           "results": res, "answers": acc, "bars": BARS, "pass": verdict(res, acc)}
    with open(a.out, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    for m in res:
        for key in ("all",) + BC.SCENARIOS:
            x = res[m][key]
            print("%-10s %-10s loc=%s recP=%s recR=%s concl=%s pres=%s side=%s up=%s n=%s checks=%s" % (
                m, key, x["localization"], x["revision_precision"], x["revision_recall"], x["conclusions_correct"],
                x["preservation"], x["preservation_side"], x["preservation_upstream"], x["contradictions"],
                x["checks_per_network"]))
    for k, v in acc.items():
        print("answers %-24s %s" % (k, v))
    print("pass:", doc["pass"])


if __name__ == "__main__":
    main()
