"""The Lab's bond-length search for its molecule experiment (14 November 2026).

Before this, every molecule step on record (15 of them, 28 October - 12 November) sent the menu's example grid
0.6/0.735/0.9/1.2 A (or a wider textbook grid), and re-sent it unchanged. That grid was written around the textbook
minima of H2 and HeH+, so the Lab found a molecule's bond-length minimum only where the textbook had put a point: on a
simulated benchmark of 50 held-out cases, 44% right overall and 30% on unfamiliar molecules (offline experiment of 14
November).

A planner now writes "bond_lengths": "search" and this module chooses the lengths, from what this investigation has
already measured on that molecule:
  1. bracket: nine lengths spread evenly in log r over 0.45-2.2 A, centred on no molecule's textbook answer;
  2. refine: up to nine lengths across where the minimum can still be (the 1st-99th percentile of the belief about
     it, never narrower than 0.04 A), with more shots once it is narrow;
  3. stop: when the belief is 95% sure the minimum lies within +-0.02 A of its answer, the search says so and sends
     nothing more; when its budget (20 cost units, or the investigation's steps) runs out first, it says "not sure",
     with its best answer and how sure it is.

The belief is a Gaussian process over the energy curve E(log r) (prior amplitude and length scale fitted on simulated
two-electron curves), read as in the experiment, whose stated confidence matched how often it was right (ECE 0.02):
  exact mode (exact=true, the bench's default): the exact_energy column, noise-free;
  measured mode (exact=false): the VQE value, with the simulated bench's bias and spread per (vqe_shots, restarts)
    and bond length. Past about 1.6 A the bench's search often stalls near Hartree-Fock (spread 15-30 mHa there
    against 1-5 mHa near the minimum): those readings carry their larger spread, a reading at or above Hartree-Fock
    from 1.2 A out is treated as a stalled search, readings are Student-t (one stalled reading cannot drag the curve),
    a shared per-molecule offset is modelled, and a refinement reaching past 1.55 A asks for 2 restarts.

Deterministic for the same readings (fixed sampling seed), so the planner-trial's check and the step itself fill the
same request. Pure computation on stored receipts: nothing here calls the Mac or any service.
"""
from __future__ import annotations

import json
import math

import numpy as np

LO, HI, STEP = 0.40, 2.50, 0.01
GRID = np.round(np.arange(LO, HI + 1e-9, STEP), 2)
NG = len(GRID)
MAX_BONDS = 9                     # lab_experiments: the bench keeps the first 9 bond lengths
BRACKET = (0.45, 0.55, 0.67, 0.81, 0.99, 1.21, 1.47, 1.8, 2.2)   # 0.45 * (2.2/0.45)**(i/8), rounded
BUDGET = 20.0                     # cost units: one step = 1, plus restarts * vqe_shots / 16384 per bond (measured)
SURE = 0.95
TOL_BOND = 0.02                   # A
TOL_ENERGY = 0.0016               # Ha (chemical accuracy)
NOISY_FROM = 1.55                 # A: a refinement reaching past this asks for 2 restarts in measured mode
LOCAL = 0.05                      # A: "sure" needs readings this close to the answer on both sides
UNSUPPORTED = 0.9                 # the confidence stated until they are there
WINDOW = 0.12                     # a refinement spans at least +-12% of the answer's bond length
FLOOR_RATIO = 1.35               # energy spread within this of the shared offset: more readings will not help
STALL_FROM = 1.2                 # A: a measured reading at or above Hartree-Fock from here out is a stalled search
STALL_SD = 0.1                    # Ha: the spread given such a reading
STALL_MARGIN = 0.003              # Ha: within this of Hartree-Fock (or above it) is a stall; a converged search sits
                                  # 20 mHa or more below it from 1.2 A out
EXACT_SD = 2e-6                   # Ha: the bench prints six decimals
SHOTS = (2048, 4096, 8192, 16384)
RESTARTS = (1, 2, 4)
SEARCH_WORDS = ('search',)
# LiH: the bench stops a run after 180 s and LiH took about 11 s a length at layers 2 (12 November), so its requests
# keep at most 5 lengths
MOLECULE_BONDS = {'LIH': 5}

# Gaussian-process prior over E(log r) (marginal likelihood on simulated two-electron curves) and the per-molecule
# offset shared by all of one molecule's measured readings, per restarts.
AMP, LENGTH, MEAN_VAR = 0.6927, 0.6342, 4.0
TAU = {1: 0.0010, 2: 0.0014, 4: 0.0018}

# The simulated bench's measured-mode reading minus the exact energy, in mHa: (bias, spread) at these bond lengths,
# per (vqe_shots, restarts). Interpolated in bond length; past 2.5 A the last value holds.
CAL_BONDS = (0.5, 0.7, 0.9, 1.2, 1.6, 2.0, 2.5)
CAL = {
    (2048, 1): ((-5.79, -6.35, -4.21, -3.06, -0.31, 3.17, 7.29), (4.81, 4.07, 4.82, 6.68, 9.72, 17.55, 26.63)),
    (2048, 2): ((-7.99, -8.05, -8.71, -7.94, -5.22, 0.08, 4.33), (3.93, 4.05, 4.63, 4.27, 6.39, 16.63, 23.17)),
    (2048, 4): ((-10.1, -10.16, -10.51, -10.08, -7.21, -3.24, 0.1), (3.27, 3.54, 3.65, 4.36, 5.88, 11.09, 21.73)),
    (4096, 1): ((-3.45, -3.11, -2.84, -2.95, -0.42, 5.89, 10.81), (3.74, 4.24, 4.73, 5.68, 8.06, 20.29, 29.91)),
    (4096, 2): ((-4.76, -5.34, -5.75, -5.35, -3.81, 0.44, 4.66), (2.78, 2.62, 3.23, 2.75, 4.47, 13.3, 21.34)),
    (4096, 4): ((-6.55, -6.73, -6.64, -7.16, -4.27, -2.72, 1.99), (3.03, 2.6, 2.5, 3.28, 6.09, 9.28, 19.0)),
    (8192, 1): ((-1.44, -1.61, -1.48, -1.06, 1.88, 5.72, 8.75), (3.17, 3.08, 3.26, 4.55, 10.29, 20.24, 26.45)),
    (8192, 2): ((-2.67, -3.68, -3.02, -3.62, -1.83, 0.64, 6.18), (2.51, 2.4, 2.42, 2.6, 2.99, 11.44, 24.01)),
    (8192, 4): ((-4.13, -4.44, -4.63, -5.05, -3.4, -0.51, 0.98), (1.73, 1.76, 1.81, 2.01, 3.88, 9.69, 14.85)),
    (16384, 1): ((-0.17, -0.67, -0.77, -0.7, 1.25, 5.47, 8.31), (3.09, 2.22, 2.37, 2.75, 7.34, 18.11, 25.27)),
    (16384, 2): ((-1.92, -2.31, -2.29, -2.38, -1.47, -0.51, 6.23), (1.72, 1.74, 1.63, 1.73, 1.95, 4.21, 22.88)),
    (16384, 4): ((-2.85, -2.92, -3.04, -3.32, -2.58, -0.76, 0.9), (1.45, 1.38, 1.29, 1.58, 1.5, 8.46, 14.25)),
}


# ----------------------------------------------------------------------------------------------- requests and costs
def _truthy(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        word = value.strip().lower()
        if word in ('false', '0', 'no', 'off'):
            return False
        if word in ('true', '1', 'yes', 'on'):
            return True
        return default
    return bool(value)


def setting(shots, restarts):
    """The calibrated (vqe_shots, restarts) nearest a request's: shots at least the bench's 2048, nearest in log;
    restarts the largest calibrated value not above the request's."""
    try:
        s = float(shots)
    except (TypeError, ValueError):
        s = 4096.0
    s = min(SHOTS, key=lambda c: abs(math.log(c) - math.log(max(2048.0, s))))
    try:
        k = int(restarts)
    except (TypeError, ValueError):
        k = 4
    k = max([c for c in RESTARTS if c <= max(1, k)])
    return s, k


def cost(n_bonds, exact, shots=4096, restarts=4):
    """One Lab step plus, in measured mode, restarts * vqe_shots / 16384 per bond; in exact mode a quarter per bond at
    the bench's default 4 restarts (its run time is the optimizer's, not shots)."""
    if exact:
        return 1.0 + n_bonds * max(1, int(restarts or 4)) / 16.0
    s, k = setting(shots, restarts)
    return 1.0 + n_bonds * k * s / 16384.0


def asks_search(request):
    """True for a molecule request whose bond_lengths is the word "search"."""
    if not isinstance(request, dict) or str(request.get('experiment') or '').strip().lower() != 'molecule':
        return False
    params = request.get('parameters')
    value = params.get('bond_lengths') if isinstance(params, dict) else None
    return isinstance(value, str) and value.strip().lower() in SEARCH_WORDS


def _key(params):
    """Which molecule a request measures: its name (H2 when unnamed, the bench's default) and active space."""
    params = params if isinstance(params, dict) else {}
    name = str(params.get('molecule') or 'H2').strip().replace(' ', '').upper()
    space = params.get('active_space')
    return name, json.dumps(space, sort_keys=True) if space is not None else ''


# ---------------------------------------------------------------------------------------------------------- readings
class Reading:
    """One bond length's reading: the value used, whether it is exact, and its (vqe_shots, restarts)."""
    __slots__ = ('bond', 'value', 'exact', 'shots', 'restarts', 'hf')

    def __init__(self, bond, value, exact, shots=4096, restarts=4, hf=None):
        self.bond, self.value, self.exact = float(bond), float(value), bool(exact)
        self.shots, self.restarts = setting(shots, restarts)
        self.hf = None if hf is None else float(hf)

    def __repr__(self):
        return 'Reading(%.3f, %.6f, %s)' % (self.bond, self.value, 'exact' if self.exact else 'measured')


def _number(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _points(payload):
    """The per-bond rows of a molecule result: the grade's points when graded, else the first list of rows naming a
    bond_length anywhere in it."""
    if not isinstance(payload, dict):
        return []
    grade = payload.get('grade')
    if isinstance(grade, dict) and isinstance(grade.get('points'), list) and grade['points']:
        return [p for p in grade['points'] if isinstance(p, dict)]
    stack = [payload]
    while stack:
        value = stack.pop(0)
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value) \
                and any('bond_length' in v for v in value):
            return value
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return []


def readings_from(payload, params, top_shots=None):
    """Readings from one stored molecule result. An exact_energy, when the bench printed one, is the exact curve and is
    used as such; otherwise, in measured mode, the VQE value."""
    params = params if isinstance(params, dict) else {}
    exact_mode = _truthy(params.get('exact'), True)
    shots = params.get('vqe_shots') or top_shots or 4096
    restarts = params.get('restarts') or 4
    out = []
    for row in _points(payload):
        bond = _number(row.get('bond_length'))
        if bond is None or not (LO - 1e-9 <= bond <= HI + 1e-9):
            continue
        # the grade's names, else the bench's own (exact, vqe, hartree_fock: its raw rows, 28 October)
        exact, vqe, hf = (_number(row.get('exact_energy', row.get('exact'))),
                          _number(row.get('vqe_energy', row.get('vqe'))),
                          _number(row.get('hartree_fock_energy', row.get('hartree_fock'))))
        if exact is not None:
            out.append(Reading(bond, exact, True, shots, restarts, hf))
        elif vqe is not None and not exact_mode:
            out.append(Reading(bond, vqe, False, shots, restarts, hf))
    return out


def _request(step):
    request = step.get('executed_request') or step.get('request') or {}
    return request if isinstance(request, dict) else {}


def molecule_steps(steps, key=None):
    """This investigation's molecule steps (for one molecule when key is given), in order."""
    out = []
    for step in steps or []:
        if not isinstance(step, dict) or step.get('route') != 'experiment':
            continue
        request = _request(step)
        if str(request.get('experiment') or '').strip().lower() != 'molecule':
            continue
        if key is None or _key(request.get('parameters')) == key:
            out.append(step)
    return out


def _load(step, steps):
    import lab_investigations
    return lab_investigations.resolve({'step': step['id'], 'path': []}, steps)


def history(steps, key, load=None):
    """(readings, cost spent) for one molecule in this investigation. A step handed an earlier step's output (a
    repeat, or the same receipt) adds no readings: the same reading counted twice would look like two."""
    load = load or _load
    readings, spent, seen = [], 0.0, set()
    for step in molecule_steps(steps, key):
        request = _request(step)
        params = request.get('parameters') if isinstance(request.get('parameters'), dict) else {}
        bonds = params.get('bond_lengths')
        n = len(bonds) if isinstance(bonds, list) else 1
        if step.get('state') in ('completed', 'failed', 'outcome_unknown') and not step.get('reused_from'):
            spent += cost(min(n, MAX_BONDS), _truthy(params.get('exact'), True),
                          params.get('vqe_shots') or request.get('shots') or 4096, params.get('restarts') or 4)
        # a step handed an earlier output (reused_from) carries that output's readings: the same output twice is
        # caught by its hash below, and one handed another investigation's run is this one's only reading of it
        # (review: the deterministic bracket is reused across investigations, and skipping it stuck the search)
        if step.get('state') != 'completed' or step.get('same_receipt_as'):
            continue
        sha = step.get('output_sha256')
        if sha and sha in seen:
            continue
        seen.add(sha)
        try:
            payload = load(step, steps)
        except Exception:
            continue
        readings += readings_from(payload, params, request.get('shots'))
    return readings, spent


# ------------------------------------------------------------------------------------------------------------ belief
def _bias_sd(bond, shots, restarts):
    bias, sd = CAL[(shots, restarts)]
    return (float(np.interp(bond, CAL_BONDS, bias)) / 1000.0, float(np.interp(bond, CAL_BONDS, sd)) / 1000.0)


def _prior():
    x = np.log(GRID)
    K = np.zeros((NG + 1, NG + 1))
    K[:NG, :NG] = MEAN_VAR + AMP ** 2 * np.exp(-0.5 * (x[:, None] - x[None, :]) ** 2 / LENGTH ** 2)
    K[NG, NG] = 1.0
    return K


_K = None


def _chol(M):
    jitter = 0.0
    for _ in range(6):
        try:
            return np.linalg.cholesky(M + jitter * np.eye(len(M)))
        except np.linalg.LinAlgError:
            jitter = max(jitter * 10.0, 1e-12)
    raise np.linalg.LinAlgError('belief could not be formed')


def posterior(readings):
    """Mean and covariance of [E on GRID, shared offset u] given the readings: reading = E(r) + bias + tau*u + noise,
    with Student-t (nu = 3) readings by reweighting."""
    global _K
    if _K is None:
        _K = _prior()
    K = _K
    if not readings:
        return np.zeros(NG + 1), K.copy()
    idx, tau, y, v = [], [], [], []
    for r in readings:
        # between grid points by linear interpolation, not snapped: an exact reading at 0.735 snapped to 0.73 beside
        # one at 0.74 forced a wild curve (review, 14 November)
        idx.append((min(max(r.bond, LO), HI) - LO) / STEP)
        if r.exact:
            tau.append(0.0); y.append(r.value); v.append(EXACT_SD ** 2)
            continue
        bias, sd = _bias_sd(r.bond, r.shots, r.restarts)
        if r.hf is not None and r.bond >= STALL_FROM and r.value >= r.hf - STALL_MARGIN:
            # a search that never left Hartree-Fock only says the curve is below Hartree-Fock there: next to nothing
            # about its shape (test: three such readings past 1.4 A put the minimum 0.1 A short)
            sd = max(sd, STALL_SD)
        tau.append(TAU[r.restarts]); y.append(r.value - bias); v.append(sd ** 2)
    n = len(idx)
    H = np.zeros((n, NG + 1))
    pos = np.array(idx)
    left = np.minimum(np.floor(pos + 1e-9).astype(int), NG - 2)
    w = np.clip(pos - left, 0.0, 1.0)
    H[np.arange(n), left] = 1.0 - w
    H[np.arange(n), left + 1] += w
    H[:, NG] = tau
    KH = K @ H.T
    y, v = np.array(y), np.array(v)
    mu0 = np.zeros(NG + 1)
    mu0[:NG] = float(np.median(y))
    veff = v.copy()
    robust = not all(r.exact for r in readings)
    for _ in range(6 if robust else 0):
        L = _chol(H @ KH + np.diag(veff))
        A = np.linalg.solve(L, KH.T)
        mu = mu0 + A.T @ np.linalg.solve(L, y - H @ mu0)
        z2 = (y - H @ mu) ** 2 / v
        veff = v * (3.0 + z2) / 4.0
    L = _chol(H @ KH + np.diag(veff))
    A = np.linalg.solve(L, KH.T)
    mu = mu0 + A.T @ np.linalg.solve(L, y - H @ mu0)
    return mu, K - A.T @ A


def samples(readings, M=1024, seed=0):
    mu, cov = posterior(readings)
    w, V = np.linalg.eigh((cov + cov.T) / 2.0)
    w = np.clip(w, 0.0, None)
    Z = np.random.default_rng(seed).standard_normal((M, NG + 1))
    return (mu + (Z * np.sqrt(w)) @ V.T)[:, :NG]


def _single_well(F):
    """Per sampled curve, True when it has exactly one local minimum on the grid (an end counts when the curve rises
    away from it)."""
    rising = np.diff(F, axis=1) > 0
    inner = (~rising[:, :-1] & rising[:, 1:]).sum(axis=1)
    return (inner + rising[:, 0] + ~rising[:, -1]) == 1


def _answer(t, tol, digits):
    """The value with the most belief within the tolerance, and that share (the stated confidence)."""
    cands = np.unique(np.round(t, digits))
    if len(cands) > 400:
        cands = np.quantile(t, np.linspace(0, 1, 401))
    mass = np.array([np.mean(np.abs(t - c) <= tol + 1e-12) for c in cands])
    i = int(np.argmax(mass))
    return float(cands[i]), float(mass[i])


def estimate(readings, M=1024):
    """What the readings say about the minimum: its bond length and energy, each with the share of belief within its
    tolerance (+-0.02 A, +-1.6 mHa), and where the minimum can still be (1st-99th percentile)."""
    if not readings:
        return {'readings': 0, 'bond_length': None, 'bond_confidence': 0.0, 'energy': None, 'energy_confidence': 0.0,
                'energy_at_floor': False, 'interval': [LO, HI], 'at_edge': False}
    F = samples(readings, M)
    # A diatomic's ground-state curve has one well. Curves the belief allows with a second dip are set aside: noisy
    # stretched-bond readings (15-30 mHa) otherwise leave room for a "minimum" at 2.5 A beside a clear well near 1 A,
    # and the search spent its budget there (dev round 2: wide107, wide115, wide118).
    one = _single_well(F)
    if one.sum() >= M // 8:
        F = F[one]
    where = GRID[np.argmin(F, axis=1)]
    depth = F.min(axis=1)
    bond, bconf = _answer(where, TOL_BOND, 2)
    energy, econf = _answer(depth, TOL_ENERGY, 4)
    lo, hi = np.quantile(where, [0.01, 0.99])
    edge = float(np.mean((where <= LO + 1e-9) | (where >= HI - 1e-9)))
    # Between readings the curve is the prior's guess, and a smooth prior can be sure of a minimum no reading is near
    # (dev, exact mode: 100% sure after the bracket alone, 0.02 A off). Until readings within LOCAL of the answer
    # stand on both sides of it, the stated confidence stays below SURE.
    near = [r.bond for r in readings if abs(r.bond - bond) <= LOCAL + 1e-9]
    if not (any(b <= bond + 1e-9 for b in near) and any(b >= bond - 1e-9 for b in near) and len(set(near)) >= 2):
        bconf = min(bconf, UNSUPPORTED)
        econf = min(econf, UNSUPPORTED)
    # The energy cannot be pinned below the offset every measured reading of one molecule shares (about 1-2 mHa):
    # once its spread is near that floor, more readings of this kind will not make it surer.
    taus = [TAU[r.restarts] for r in readings if not r.exact]
    floor = bool(taus) and float(np.std(depth)) <= FLOOR_RATIO * min(taus)
    return {'readings': len(readings), 'bond_length': round(bond, 2), 'bond_confidence': round(bconf, 3),
            'energy': round(energy, 6), 'energy_confidence': round(econf, 3), 'energy_at_floor': floor,
            'interval': [round(float(lo), 2), round(float(hi), 2)], 'at_edge': edge > 0.05}


# ----------------------------------------------------------------------------------------------------------- planner
def _spread(lo, hi, n):
    bonds = sorted({round(float(b), 2) for b in np.linspace(lo, hi, n)})
    return [b for b in bonds if LO - 1e-9 <= b <= HI + 1e-9]


def propose(readings, exact, spent=0.0, steps_left=None, shots=None, restarts=None, budget=BUDGET,
            max_bonds=MAX_BONDS):
    """The next request's {bond_lengths, vqe_shots, restarts} (the last two None in exact mode, or when the planner set
    them), or None with why: 'sure' when the belief is 95% sure of the minimum's bond length, 'budget' when no request
    is left to make. Returns (plan or None, verdict, estimate)."""
    est = estimate(readings)
    left = budget - spent
    if (readings and est['bond_confidence'] >= SURE and not est['at_edge']
            and (est['energy_confidence'] >= SURE or est['energy_at_floor'])):
        return None, 'sure', est
    if (steps_left is not None and steps_left <= 0) or left < 1.0 + 1e-9:
        return None, 'budget', est
    fixed = shots is not None or restarts is not None
    if not readings:
        bonds = _thin(list(BRACKET), max_bonds)
        options = [(4096, 1), (2048, 1)]
    else:
        # where the minimum can still be, and never narrower than WINDOW of its bond length on each side: near the
        # minimum the curve is flat (about 0.1 mHa over 0.02 A), so its place shows in the rise on either side, not in
        # readings packed beside it (dev round 2: eight lengths inside 0.07 A, 16384 shots, 100% sure and 0.02 A off)
        lo, hi = est['interval']
        centre = est['bond_length']
        lo, hi = min(lo - 0.01, centre * (1 - WINDOW)), max(hi + 0.01, centre * (1 + WINDOW))
        lo, hi = max(LO, lo), min(HI, hi)
        bonds = _spread(lo, hi, max_bonds)
        k = 2 if hi > NOISY_FROM else 1
        # a wide window is still being narrowed: fewer shots there keep the budget for where it ends up
        width = hi - lo
        first = 4096 if width > 0.5 else 8192 if width > 0.25 else 16384
        options = [(s, k) for s in (16384, 8192, 4096, 2048) if s <= first] + [(2048, 1)]
    if exact:
        bonds = next((_thin(bonds, n) for n in range(len(bonds), 0, -1) if cost(n, True) <= left + 1e-9), [])
        if not bonds:
            return None, 'budget', est
        return {'bond_lengths': bonds, 'vqe_shots': None, 'restarts': None}, 'searching', est
    if fixed:
        options = [setting(shots or 4096, restarts or 4)]
    for s, k in options:
        trial = next((_thin(bonds, n) for n in range(len(bonds), 0, -1) if cost(n, False, s, k) <= left + 1e-9), [])
        if trial and (len(trial) >= min(3, len(bonds)) or (s, k) == options[-1]):
            return ({'bond_lengths': trial, 'vqe_shots': None if fixed else s, 'restarts': None if fixed else k},
                    'searching', est)
    return None, 'budget', est


def _thin(bonds, n=None):
    """n of the bond lengths (one fewer by default), keeping both ends and an even spread."""
    n = len(bonds) - 1 if n is None else n
    if n >= len(bonds):
        return list(bonds)
    if n <= 0:
        return []
    if n == 1:
        return [bonds[len(bonds) // 2]]
    picks = sorted({int(round(i)) for i in np.linspace(0, len(bonds) - 1, n)})
    return [bonds[i] for i in picks]


# ------------------------------------------------------------------------------------------------- the Lab's use of it
def _words(name, est, verdict, spent, budget=BUDGET):
    if not est.get('readings'):
        return 'no reading of %s yet' % name
    said = ('minimum at %.2f A (%d%% sure within +-0.02 A); energy there %.4f Ha (%d%% sure within +-1.6 mHa)'
            % (est['bond_length'], round(100 * est['bond_confidence']), est['energy'],
               round(100 * est['energy_confidence'])))
    if verdict == 'sure':
        return 'sure: ' + said
    if est.get('at_edge'):
        return 'not sure: the minimum may lie outside %.2f-%.2f A; best so far %s' % (LO, HI, said)
    bond_sure = est['bond_confidence'] >= SURE
    if verdict == 'budget':
        return '%s (search budget spent, %.1f of %.0f units): %s%s' % (
            'bond length sure, energy not sure' if bond_sure else 'not sure', spent, budget,
            '' if bond_sure else 'best so far ', said)
    if bond_sure:
        return 'bond length sure; the energy there is still being narrowed: ' + said
    return 'not sure yet: ' + said


def fill(route, request, steps, steps_left=None, load=None):
    """(request, why, view) for a proposed operation. A molecule request whose bond_lengths is "search" comes back
    with the search's next bond lengths (and, in measured mode, vqe_shots and restarts unless the planner set them);
    why is '' then. When the search is already sure, or its budget is spent, nothing is to be sent: why says so with
    the answer. Any other request comes back unchanged with why ''."""
    if route != 'experiment' or not asks_search(request):
        return request, '', None
    params = dict(request.get('parameters') or {})
    key = _key(params)
    exact = _truthy(params.get('exact'), True)
    readings, spent = history(steps, key, load)
    plan, verdict, est = propose(readings, exact, spent, steps_left, params.get('vqe_shots'), params.get('restarts'),
                                 max_bonds=MOLECULE_BONDS.get(key[0], MAX_BONDS))
    name = key[0] if not key[1] else '%s (active space %s)' % key
    view = {'molecule': key[0], 'mode': 'exact' if exact else 'measured', 'verdict': verdict,
            'said': _words(name, est, verdict, spent), **{k: est.get(k) for k in (
                'bond_length', 'bond_confidence', 'energy', 'energy_confidence', 'interval', 'readings')}}
    if plan is None:
        if verdict == 'sure':
            why = ('the bond-length search for %s is already sure, so nothing more is measured: %s. Finish, or take a '
                   'step with another tool' % (name, view['said']))
        else:
            why = ('the bond-length search for %s has no budget left, so nothing more is measured: %s. Finish and '
                   'report what it is not sure of as not sure' % (name, view['said']))
        return request, why, view
    params['bond_lengths'] = plan['bond_lengths']
    if not exact:
        if plan['vqe_shots'] is not None:
            params['vqe_shots'] = plan['vqe_shots']
        if plan['restarts'] is not None:
            params['restarts'] = plan['restarts']
    out = dict(request, parameters=params)
    if not exact and plan['vqe_shots'] is not None:
        out['shots'] = plan['vqe_shots']
    view['sent'] = {k: v for k, v in plan.items() if v is not None}
    return out, '', view


def at_door(parameters):
    """The Mac door's last word on a molecule request: "search" with no investigation behind it (the daily session)
    is the search's first request, the bracket. Anything else is returned unchanged."""
    if not asks_search({'experiment': 'molecule', 'parameters': parameters}):
        return parameters
    out = dict(parameters, bond_lengths=_thin(list(BRACKET), MOLECULE_BONDS.get(_key(parameters)[0], MAX_BONDS)))
    if not _truthy(out.get('exact'), True):
        out.setdefault('vqe_shots', 4096)
        out.setdefault('restarts', 1)
    return out


def planner_view(steps, load=None):
    """What the search knows, per molecule this investigation measured, for the planner's task; [] with none."""
    keys = []
    for step in molecule_steps(steps):
        key = _key(_request(step).get('parameters'))
        if key not in keys:
            keys.append(key)
    out = []
    for key in keys[:3]:
        try:
            readings, spent = history(steps, key, load)
            exacts = [_truthy((_request(s).get('parameters') or {}).get('exact'), True)
                      for s in molecule_steps(steps, key)]
            exact = exacts[-1] if exacts else True
            plan, verdict, est = propose(readings, exact, spent, max_bonds=MOLECULE_BONDS.get(key[0], MAX_BONDS))
        except Exception:
            continue
        name = key[0] if not key[1] else '%s (active space %s)' % key
        row = {'molecule': key[0], 'readings': est.get('readings', 0), 'spent': round(spent, 1), 'budget': BUDGET,
               'said': _words(name, est, verdict, spent)}
        row['next'] = ('finish: the search is done' if plan is None else
                       'bond_lengths "search" measures where the minimum can still be: %s' % plan['bond_lengths'])
        out.append(row)
    return out
