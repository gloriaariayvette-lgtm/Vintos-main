#!/usr/bin/env python3
"""The learned energy model: a small graph network that proposes repairs. Trained ONLY on small networks (the seven
small scenarios, training seeds 100000+), labelled by the exact solver's minimum-energy repair - no human labels and
no planted truth. Tested on larger, differently built networks it has never seen.

The network reads the repair problem as a factor graph: sources/steps, beliefs, justifications, contradictions and
checks are nodes; edges join each justification to its members and its belief, each contradiction and check to its
nodes. Messages pass for a number of rounds that grows with the network's depth (the same weights every round, so a
deeper network just gets more rounds). It outputs, per source or step, the chance it belongs in the minimal repair.

    python3 gnn.py train --out gnn.pt [--per 400] [--epochs 30]
"""
import argparse, math, os, random, sys, time
import torch
import torch.nn as nn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen, core

torch.set_num_threads(int(os.environ.get("GNN_THREADS", "2")))
TYPES = ("assumption", "belief", "justification", "contradiction", "check")
EDGE_TYPES = ("member>just", "just>member", "just>belief", "belief>just", "node>contra", "contra>node",
              "node>check", "check>node")
F = len(TYPES) + 7
H = 64
TRAIN_SEED0 = 100000


def featurize(P):
    """Factor-graph tensors for one repair problem."""
    names = list(P.assumptions) + list(P.derived)
    idx = {n: i for i, n in enumerate(names)}
    maxd = max([P.depth.get(n, 0) for n in names] + [1])
    feats = []
    # structural hints (iteration 2): how many contradictions an assumption is a suspect in, and whether it is the
    # cheapest (and the earliest of the cheapest) suspect of one of them
    sus_n, cheapest, earliest = {}, set(), set()
    for cid, _, _ in P.conflicts:
        sus = P.suspects(cid)
        for a in sus:
            sus_n[a] = sus_n.get(a, 0) + 1
        if sus:
            lo = min(P.w[a] for a in sus)
            low = [a for a in sus if P.w[a] <= lo + 1e-6]
            cheapest.update(low)
            earliest.add(min(low, key=lambda a: (P.depth.get(a, 0), a)))
    nc = max(1, len(P.conflicts))
    for n in P.assumptions:
        feats.append([1, 0, 0, 0, 0, P.w[n] / 5.0, float(n.startswith("rule:")), P.depth.get(n, 0) / maxd, 0.0,
                      sus_n.get(n, 0) / nc, float(n in cheapest), float(n in earliest)])
    for n in P.derived:
        feats.append([0, 1, 0, 0, 0, 0.0, 0.0, P.depth.get(n, 0) / maxd, 0.0, 0.0, 0.0, 0.0])
    edges = {t: ([], []) for t in EDGE_TYPES}

    def e(t, s, d):
        edges[t][0].append(s); edges[t][1].append(d)
    for v in P.derived:
        for j in P.just[v]:
            k = len(feats)
            feats.append([0, 0, 1, 0, 0, 0.0, 0.0, P.depth.get(v, 0) / maxd, len(j) / 4.0, 0.0, 0.0, 0.0])
            for a in j:
                e("member>just", idx[a], k); e("just>member", k, idx[a])
            e("just>belief", k, idx[v]); e("belief>just", idx[v], k)
    for _, ns, W in P.conflicts:
        k = len(feats)
        feats.append([0, 0, 0, 1, 0, W / 5.0, 0.0, 0.0, len(ns) / 4.0, 0.0, 0.0, 0.0])
        for n in ns:
            e("node>contra", idx[n], k); e("contra>node", k, idx[n])
    for n, U in P.confirms:
        k = len(feats)
        feats.append([0, 0, 0, 0, 1, U / 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        e("node>check", idx[n], k); e("check>node", k, idx[n])
    return {"x": torch.tensor(feats, dtype=torch.float32), "nA": len(P.assumptions),
            "edges": {t: (torch.tensor(s, dtype=torch.long), torch.tensor(d, dtype=torch.long)) for t, (s, d) in edges.items()},
            "rounds": rounds_for(P)}


def rounds_for(P):
    return 2 * max([P.depth.get(n, 0) for n in P.derived] + [1]) + 6


def batch(items):
    """Concatenate several graphs into one."""
    xs, edges, amask, off = [], {t: ([], []) for t in EDGE_TYPES}, [], 0
    for it in items:
        n = it["x"].shape[0]
        xs.append(it["x"])
        m = torch.zeros(n, dtype=torch.bool); m[:it["nA"]] = True
        amask.append(m)
        for t, (s, d) in it["edges"].items():
            edges[t][0].append(s + off); edges[t][1].append(d + off)
        off += n
    return {"x": torch.cat(xs), "amask": torch.cat(amask),
            "edges": {t: (torch.cat(s), torch.cat(d)) for t, (s, d) in edges.items()},
            "rounds": max(it["rounds"] for it in items)}


class RepairGNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(F, H), nn.ReLU(), nn.Linear(H, H))
        self.msg = nn.ModuleDict({t.replace(">", "_"): nn.Sequential(nn.Linear(H, H), nn.ReLU()) for t in EDGE_TYPES})
        self.mix = nn.Linear(2 * H * len(EDGE_TYPES) + F, H)
        self.gru = nn.GRUCell(H, H)
        self.norm = nn.LayerNorm(H)
        self.out = nn.Sequential(nn.Linear(H + F, H), nn.ReLU(), nn.Linear(H, 1))

    def forward(self, b, rounds=None):
        x = b["x"]
        h = self.enc(x)
        N = x.shape[0]
        for _ in range(rounds or b["rounds"]):
            parts = []
            for t in EDGE_TYPES:
                s, d = b["edges"][t]
                m = self.msg[t.replace(">", "_")](h[s]) if len(s) else torch.zeros(0, H, device=x.device)
                summ = torch.zeros(N, H, device=x.device).index_add(0, d, m)
                cnt = torch.zeros(N, device=x.device).index_add(0, d, torch.ones(len(d), device=x.device)).clamp_min(1).unsqueeze(1)
                mx = summ / 4.0                                   # a scaled sum: counts matter for AND/OR
                parts += [summ / cnt, mx]
            h = self.norm(self.gru(torch.relu(self.mix(torch.cat(parts + [x], 1))), h))
        return self.out(torch.cat([h, x], 1)).squeeze(1)


def label(P):
    R, E, _ = core.solve_exact(P)
    return torch.tensor([1.0 if a in R else 0.0 for a in P.assumptions])


def dataset(per, seed0=TRAIN_SEED0, checked=True):
    """Small networks only. Iteration 3: each training network appears twice - as recorded, and after
    belief_revision's own checks (the evaluation's main track has check answers as sources; gnn-v2 never saw one in
    training and flagged them as faults)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("energy_bench", os.path.join(HERE, "bench.py"))
    bench = importlib.util.module_from_spec(spec)          # not contradiction-backprop/bench.py, also on the path
    sys.modules["energy_bench"] = bench
    spec.loader.exec_module(bench)
    if checked:
        bench.warm([(sc, s) for sc in gen.SMALL for s in range(seed0, seed0 + per)], workers=14)
    data = []
    for sc in gen.SMALL:
        for s in range(seed0, seed0 + per):
            nets = [gen.network(sc, s)[0]] + ([bench.checked(sc, s)[0]] if checked else [])
            for g in nets:
                P = core.Problem(g)
                data.append((featurize(P), label(P)))
    return data


def to(b, dev):
    return {"x": b["x"].to(dev), "amask": b["amask"].to(dev), "rounds": b["rounds"],
            "edges": {t: (s.to(dev), d.to(dev)) for t, (s, d) in b["edges"].items()}}


def train(out, per=400, epochs=30, bs=32, lr=2e-3, log=print, device=None):
    """CPU by default: the torch build on Aegis has no kernels for its GPU."""
    dev = torch.device(device or os.environ.get("GNN_DEVICE", "cpu"))
    t0 = time.time()
    data = dataset(per)
    log("built %d training networks in %.0fs" % (len(data), time.time() - t0))
    model = RepairGNN().to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    pos = sum(float(y.sum()) for _, y in data)
    tot = sum(len(y) for _, y in data)
    pw = torch.tensor(math.sqrt((tot - pos) / max(pos, 1.0)), device=dev)   # v1's full ratio taught "retract all"
    rng = random.Random(0)
    for ep in range(epochs):
        rng.shuffle(data)
        tl = 0.0
        for i in range(0, len(data), bs):
            chunk = data[i:i + bs]
            b = to(batch([c[0] for c in chunk]), dev)
            y = torch.cat([c[1] for c in chunk]).to(dev)
            logit = model(b)[b["amask"]]
            loss = nn.functional.binary_cross_entropy_with_logits(logit, y, pos_weight=pw)
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tl += float(loss) * len(chunk)
        log("epoch %d loss %.4f (%.0fs)" % (ep, tl / len(data), time.time() - t0))
        sys.stdout.flush()
    torch.save({k: v.cpu() for k, v in model.state_dict().items()}, out)
    return model


_MODEL = {}


def load(path):
    if path not in _MODEL:
        m = RepairGNN()
        m.load_state_dict(torch.load(path, map_location="cpu"))
        m.eval()
        _MODEL[path] = m
    return _MODEL[path]


def probs(model, P):
    with torch.no_grad():
        f = featurize(P)
        b = batch([f])
        return dict(zip(P.assumptions, torch.sigmoid(model(b)[b["amask"]]).tolist()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["train"])
    ap.add_argument("--out", default=os.path.join(HERE, "gnn.pt"))
    ap.add_argument("--per", type=int, default=400)
    ap.add_argument("--epochs", type=int, default=30)
    a = ap.parse_args()
    train(a.out, a.per, a.epochs)
