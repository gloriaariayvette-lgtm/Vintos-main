#!/usr/bin/env python3
"""The continuous energy model: soft truth values in [0, 1], a differentiable inconsistency energy, gradient descent.

Variant "free" (Chat's proposal as written): every node - source, inference step and belief - gets its own soft
truth value x in [0, 1]. The energy is

    anchors        sum_a w_a * (1 - x_a)                      giving up a source costs what its evidence is worth
    implication    lam * sum_j relu(AND_j - x_v)              a justification that holds forces its belief
    support        lam * sum_v relu(x_v - OR_v)               a belief holds only as far as some justification does
    contradiction  sum_c W_c * prod_{n in c} x_n              all members of a contradiction holding costs W_c
    checks         sum_k U_k * (1 - x_k)                      a passed check whose belief fails costs U_k

with AND_j the product of a justification's members and OR_v = 1 - prod_j (1 - AND_j). Minimized by Adam on the
logits, then discretized: a source or step is retracted when its value ends under 0.5.

Variant "propagated" (iteration 2): only sources and steps get free values; every belief's value is COMPUTED from
them by the same soft AND / OR, iterated from zero (the least fixpoint, so a loop cannot hold itself up). At 0/1
values this energy equals the exact repair energy, so the landscape has no logical slack to hide in.
"""
import math, random, time
import torch

torch.set_num_threads(4)


class Tensors:
    def __init__(self, P):
        self.P = P
        self.nodes = P.assumptions + P.derived
        self.id = {n: i for i, n in enumerate(self.nodes)}
        self.nA = len(P.assumptions)
        jv, ja, jidx = [], [], []        # justification -> its belief; (member, justification) pairs
        k = 0
        for v in P.derived:
            for j in P.just[v]:
                jv.append(self.id[v])
                for a in j:
                    ja.append(self.id[a]); jidx.append(k)
                k += 1
        self.nJ = k
        self.jv = torch.tensor(jv, dtype=torch.long)
        self.ja = torch.tensor(ja, dtype=torch.long)
        self.jidx = torch.tensor(jidx, dtype=torch.long)
        cm, ci = [], []
        for i, (_, ns, _) in enumerate(P.conflicts):
            for n in ns:
                cm.append(self.id[n]); ci.append(i)
        self.cm = torch.tensor(cm, dtype=torch.long)
        self.ci = torch.tensor(ci, dtype=torch.long)
        self.W = torch.tensor([W for _, _, W in P.conflicts], dtype=torch.float32)
        self.kn = torch.tensor([self.id[n] for n, _ in P.confirms], dtype=torch.long)
        self.U = torch.tensor([U for _, U in P.confirms], dtype=torch.float32)
        self.w = torch.tensor([P.w[a] for a in P.assumptions], dtype=torch.float32)
        self.depth = torch.tensor([P.depth.get(a, 0) for a in P.assumptions], dtype=torch.float32)
        self.nV = len(P.derived)
        self.rounds = len(P.derived) + 1

    def and_j(self, x):
        logx = torch.log(x.clamp_min(1e-6))
        s = torch.zeros(self.nJ).index_add(0, self.jidx, logx[self.ja])
        return torch.exp(s)

    def or_v(self, andj):
        log1m = torch.log((1 - andj).clamp_min(1e-6))
        s = torch.zeros(len(self.nodes)).index_add(0, self.jv, log1m)
        return 1 - torch.exp(s)

    def propagate(self, xa):
        """Belief values from source/step values: soft AND / OR iterated from zero (least fixpoint)."""
        x = torch.cat([xa, torch.zeros(self.nV)])
        for _ in range(self.rounds):
            orv = self.or_v(self.and_j(x))
            x_new = torch.cat([xa, orv[self.nA:]])
            if torch.allclose(x_new, x, atol=1e-5):
                x = x_new
                break
            x = x_new
        return x

    def terms(self, x):
        e = torch.zeros(())
        if len(self.W):
            logx = torch.log(x.clamp_min(1e-6))
            pc = torch.exp(torch.zeros(len(self.W)).index_add(0, self.ci, logx[self.cm]))
            e = e + (self.W * pc).sum()
        if len(self.U):
            e = e + (self.U * (1 - x[self.kn])).sum()
        return e


def minimize(P, variant="propagated", steps=300, lr=0.1, lam=10.0, init=3.0, noise=0.0, seed=0, earliness=0.0,
             T=None, anneal=0.0):
    """Gradient descent on the energy. Returns (repair, soft values of the sources/steps, seconds).
    earliness: a small extra cost per depth step on retracting, so equal suspects resolve toward the earlier one.
    anneal: the weight, ramped up from zero over the run, of a term x(1-x) that pushes every free value to 0 or 1."""
    t0 = time.perf_counter()
    T = T or Tensors(P)
    g = torch.Generator().manual_seed(seed)
    n = T.nA if variant == "propagated" else len(T.nodes)
    theta = torch.full((n,), float(init)) + noise * torch.randn(n, generator=g)
    theta.requires_grad_(True)
    opt = torch.optim.Adam([theta], lr=lr)
    w = T.w + earliness * T.depth
    for step in range(steps):
        opt.zero_grad()
        if variant == "propagated":
            xa = torch.sigmoid(theta)
            x = T.propagate(xa)
        else:
            x = torch.sigmoid(theta)
            xa = x[:T.nA]
            andj = T.and_j(x)
            orv = T.or_v(andj)
        e = (w * (1 - xa)).sum() + T.terms(x)
        if variant != "propagated":
            imp = torch.relu(andj - x[T.jv]).sum()
            sup = torch.relu(x[T.nA:] - orv[T.nA:]).sum()
            e = e + lam * (imp + sup)
        if anneal:
            xf = torch.sigmoid(theta)
            e = e + anneal * (step / steps) * (xf * (1 - xf)).sum()
        e.backward()
        opt.step()
    xa = torch.sigmoid(theta.detach())[:T.nA]
    R = {a for a, v in zip(P.assumptions, xa.tolist()) if v < 0.5}
    return R, dict(zip(P.assumptions, xa.tolist())), time.perf_counter() - t0
