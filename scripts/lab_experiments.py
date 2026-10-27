"""The Lab's named experiments as a planner must write them: the exact request, the bench's own limits, what each
returns, and what it runs on. One definition, read by the investigation menu (lab_investigations._menu), the daily
session's prompt (chemistry_session._plan), request normalization (lab_tool_calls.normalize_request) and the run
attestation (chemistry_probe). It imports nothing, so a test that stands a stub in for the Mac door still reads it.

Until 27 October the investigation menu gave flat shapes ({molecule:H2,bond_lengths:[...]}) while its door read
request.parameters, so a molecule step would have run the bench's default H2 whatever was asked; molecule was never
chosen in any investigation or session. The parameter names below are the ones the Mac's bench/experiments/*.py
read (p.get(...)), checked against the Mac on 27 October. The quantum experiments run on pyqpanda3's CPUQVM, a local
simulator on Gloria's Mac: no hosted quantum service, no cost.
"""
from __future__ import annotations

SHOTS = (256, 16384)
BENCH_SECONDS = 180          # bench_execution.perform's default: the bench stops a run after this
MAX_HP_LATTICE_RESIDUES = 9  # chemistry_mac.MAX_HP_LATTICE_RESIDUES; benchlib.parse_sequence keeps 9 beads
ESMFOLD_MAX = 911            # chemistry_mac.ESMFOLD_MAX
QPANDA_EXPERIMENTS = ("fold", "titrate", "molecule")      # each drives pyqpanda3 circuits on the Mac's CPUQVM
EXPERIMENT_PARAMETERS = {
    # chemistry_mac.ESMFOLD_PARAMETERS
    "protein": ("accession", "fragment", "gene", "protein_backend", "protein_name", "region", "region_label",
                "requested_accession", "requested_protein", "sequence", "sequence_source", "target_accession",
                "target_gene"),
    "fold": ("sequence", "charges", "chain_stiffness", "hydrophobic_pull", "charge_pull", "overlap_penalty", "layers",
             "search_steps", "tail", "seed"),
    "titrate": ("sequence", "charges", "dial", "from", "to", "points", "search_steps", "chain_stiffness",
                "hydrophobic_pull", "charge_pull", "overlap_penalty"),
    "molecule": ("molecule", "bond_length", "bond_lengths", "layers", "search_steps", "restarts", "exact", "seed",
                 "vqe_shots", "active_space"),
}
_QPANDA = "pyqpanda3 CPUQVM on Gloria's Mac (local simulator, free; nothing hosted)"
EXPERIMENTS = {
    "protein": {"runs_on": "ESMFold on Aegis (not quantum)",
                "request": {"experiment": "protein", "parameters": {
                    "target_accession": "<exact sourced UniProt accession>",
                    "protein_name": "<the gene symbol or protein name asked about>", "region": "<first-last, optional>"}},
                "limits": "refused before it folds if UniProt's record for the accession is not that protein; a chain "
                          "over %d residues must name a region" % ESMFOLD_MAX,
                "returns": "mean and per-residue pLDDT, helix and strand ranges; no energies or ensembles"},
    "fold": {"runs_on": _QPANDA,
             "request": {"experiment": "fold", "parameters": {"sequence": "HPHPPHHP", "chain_stiffness": 0.15,
                         "hydrophobic_pull": 1, "charge_pull": 0.5, "search_steps": 40}, "shots": 4096},
             "limits": "an H/P lattice chain of at most %d beads (letters H and P only; optional charges '+-0' per "
                       "bead): a toy chain, never a protein" % MAX_HP_LATTICE_RESIDUES,
             "returns": "the quantum search's lowest-energy fold and its energy against the exact lowest energy"},
    "titrate": {"runs_on": _QPANDA,
                "request": {"experiment": "titrate", "parameters": {"sequence": "HPHPPHHP", "dial": "chain_stiffness",
                            "from": 0, "to": 0.8, "points": 5}, "shots": 4096},
                "limits": "dial one of chain_stiffness | hydrophobic_pull | charge_pull; the fold's %d-bead limit; "
                          "every point is one fold" % MAX_HP_LATTICE_RESIDUES,
                "returns": "per point, measured versus exact energy, and where the chain changes shape"},
    "molecule": {"runs_on": _QPANDA + ", VQE on PySCF/OpenFermion STO-3G integrals",
                 "request": {"experiment": "molecule", "parameters": {"molecule": "H2",
                             "bond_lengths": [0.6, 0.735, 0.9, 1.2], "layers": 2, "search_steps": 200}, "shots": 4096},
                 "limits": "molecule one of H2 | HeH+ | LiH; at most 9 bond lengths in angstrom (the bench keeps the "
                           "first 9); LiH freezes the lithium core; the bench stops a run after %d s, so LiH takes "
                           "few lengths" % BENCH_SECONDS,
                 "returns": "per bond length, the VQE energy against Hartree-Fock and the exact (FCI) ground energy, "
                            "in Hartree: a bond's dissociation curve, and how far the quantum search is from exact"},
}


def experiment_request(request):
    """An experiment request in the shape the door reads, {experiment, parameters, shots}: the experiment's own
    parameters written beside "experiment" are moved under "parameters" (what is under it already wins), and
    {"titrate": {...}} names its experiment by its key (25 October: two titrate steps written that way were refused
    as experiment None). Anything that is not one of the experiment's parameters is left where it was written."""
    if not isinstance(request, dict):
        return request
    request = dict(request)
    named = [k for k in request if k in EXPERIMENTS]
    if not request.get("experiment") and len(named) == 1 and isinstance(request[named[0]], dict):
        inner = dict(request.pop(named[0]))
        request["experiment"] = named[0]
        if not isinstance(inner.get("parameters"), dict):
            inner = {"parameters": {k: inner.pop(k) for k in list(inner) if k != "shots"}, **inner}
        for key, value in inner.items():
            request.setdefault(key, value)
    names = EXPERIMENT_PARAMETERS.get(str(request.get("experiment") or ""))
    if names:
        flat = {k: request.pop(k) for k in list(request) if k in names}
        if flat:
            held = request.get("parameters") if isinstance(request.get("parameters"), dict) else {}
            request["parameters"] = dict(flat, **held)
    return request


def bounded_shots(shots):
    try:
        value = int(shots)
    except (TypeError, ValueError):
        value = 4096
    return max(SHOTS[0], min(SHOTS[1], value))


def menu(states=None):
    """The experiments as the planner is shown them, each with its exact request, limits and what it returns; a
    quantum one also carries QPanda's commissioning receipt state from chemistry_lab.tools_status(). It is shown,
    not filtered: an expired receipt is renewed by the next completed fold, titrate or molecule run
    (chemistry_probe.record_run_attestation), or by bin/chemistry_mac_probe.py on the Mac ingested with
    chemistry_probe.py --record-run."""
    q = states.get("qpanda") if isinstance(states, dict) else None
    out = {}
    for name, spec in EXPERIMENTS.items():
        row = dict(spec)
        if name in QPANDA_EXPERIMENTS:
            row["shots"] = "%d..%d" % SHOTS
            if isinstance(q, dict):
                row["qpanda_receipt"] = q.get("state") or ("measured" if q.get("available") else "not_measured")
        out[name] = row
    return out
