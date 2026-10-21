#!/usr/bin/env python3
"""Read-only: where human SLC26A4 residues 606-641 (Huber et al. 2026, ZBTB16 truncations S606/S642) fall on the pig
pendrin of PDB 8SGW, and which of them 8SGW leaves unresolved. Prints; writes nothing.

1. 8SGW's mmCIF: the entity's source organism, its UniProt reference and the reference-to-author numbering
   (_struct_ref_seq), and every residue the model leaves unobserved (_pdbx_poly_seq_scheme with no pdb_mon_id).
2. Human O43511 and the pig reference sequence from UniProt, aligned globally (Needleman-Wunsch, BLOSUM62 when
   Biopython is installed, identity scoring otherwise; the scoring used is printed).
3. Human 606-641 mapped residue by residue to pig UniProt numbering, to 8SGW author numbering, and marked
   observed / unresolved. Nothing is predicted; a residue with no pig counterpart is said to have none.

Lab evidence on pendrin already in his notebook is listed at the end, unchanged."""
import json, os, re, sys, urllib.request

HUMAN = "O43511"
HUMAN_RANGE = (606, 641)
PDB = "8SGW"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vintos-lab-probe"})
    return urllib.request.urlopen(req, timeout=60).read().decode()


def fasta(acc):
    return "".join(get("https://rest.uniprot.org/uniprotkb/%s.fasta" % acc).splitlines()[1:])


def cif_loops(text):
    """{category: [row dicts]} for the few loops this needs, parsed without a library."""
    out, lines, i = {}, text.splitlines(), 0
    while i < len(lines):
        if lines[i].strip() == "loop_":
            keys, i = [], i + 1
            while i < len(lines) and lines[i].startswith("_"):
                keys.append(lines[i].split()[0]); i += 1
            cat = keys[0].split(".")[0] if keys else ""
            rows, buf = [], []
            while i < len(lines) and not lines[i].startswith(("_", "loop_", "#")):
                buf.extend(re.findall(r"'[^']*'|\"[^\"]*\"|\S+", lines[i])); i += 1
                while len(buf) >= len(keys):
                    rows.append({k.split(".")[1]: v.strip("'\"") for k, v in zip(keys, buf[:len(keys)])})
                    buf = buf[len(keys):]
            out[cat] = rows
        else:
            m = re.match(r"(_[\w]+)\.(\w+)\s+(.+)", lines[i])
            if m:
                out.setdefault(m[1] + ".single", [{}])[0][m[2]] = m[3].strip().strip("'\"")
            i += 1
    return out


def align(a, b):
    """Global alignment; returns (scoring, [(i or None, j or None)]) with 1-based positions."""
    try:
        from Bio import Align
        from Bio.Align import substitution_matrices
        al = Align.PairwiseAligner(mode="global", open_gap_score=-10, extend_gap_score=-0.5,
                                   substitution_matrix=substitution_matrices.load("BLOSUM62"))
        best = al.align(a, b)[0]
        pairs, (ia, ib) = [], (0, 0)
        for (s1, e1), (s2, e2) in zip(*best.aligned):
            while ia < s1: pairs.append((ia + 1, None)); ia += 1
            while ib < s2: pairs.append((None, ib + 1)); ib += 1
            for k in range(e1 - s1): pairs.append((s1 + k + 1, s2 + k + 1))
            ia, ib = e1, e2
        pairs += [(x + 1, None) for x in range(ia, len(a))] + [(None, y + 1) for y in range(ib, len(b))]
        return "Biopython global, BLOSUM62, gap open -10 / extend -0.5", pairs
    except ImportError:
        pass
    n, m, G = len(a), len(b), -3
    S = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1): S[i][0] = i * G
    for j in range(1, m + 1): S[0][j] = j * G
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            S[i][j] = max(S[i-1][j-1] + (2 if a[i-1] == b[j-1] else -1), S[i-1][j] + G, S[i][j-1] + G)
    pairs, i, j = [], n, m
    while i or j:
        if i and j and S[i][j] == S[i-1][j-1] + (2 if a[i-1] == b[j-1] else -1): pairs.append((i, j)); i, j = i - 1, j - 1
        elif i and S[i][j] == S[i-1][j] + G: pairs.append((i, None)); i -= 1
        else: pairs.append((None, j)); j -= 1
    return "Needleman-Wunsch, identity +2 / mismatch -1 / gap -3 (Biopython not installed)", pairs[::-1]


def main():
    cif = cif_loops(get("https://files.rcsb.org/download/%s.cif" % PDB))
    src = (cif.get("_entity_src_gen") or cif.get("_entity_src_gen.single") or [{}])
    organisms = sorted({r.get("pdbx_gene_src_scientific_name", "?") for r in src})
    refs = [r for r in (cif.get("_struct_ref") or cif.get("_struct_ref.single") or []) if r.get("db_name") == "UNP"]
    ref_seq = cif.get("_struct_ref_seq") or cif.get("_struct_ref_seq.single") or []
    print("8SGW source organism:", ", ".join(organisms))
    print("8SGW UniProt reference:", ", ".join("%s (%s)" % (r.get("pdbx_db_accession"), r.get("db_code")) for r in refs))
    if not refs:
        print("No UniProt reference in the entry: stopping rather than guessing the pig sequence."); return
    pig = refs[0]["pdbx_db_accession"]
    seg = ref_seq[0] if ref_seq else {}
    db_beg, auth_beg = int(seg.get("db_align_beg", 1)), int(seg.get("pdbx_auth_seq_align_beg", seg.get("db_align_beg", 1)))
    offset = auth_beg - db_beg
    print("author numbering = %s UniProt numbering %+d (from _struct_ref_seq %s..%s)"
          % (pig, offset, seg.get("db_align_beg"), seg.get("db_align_end")))
    # The structure's own residues, not a database sequence: what was in the sample, in its own numbering.
    scheme = cif.get("_pdbx_poly_seq_scheme", [])
    chains = sorted({r.get("pdb_strand_id") for r in scheme if r.get("entity_id") == "1"})
    print("scheme rows: %d; entity 1 chains: %s" % (len(scheme), ",".join(chains) or "none"))
    if not chains:
        print("No polymer scheme for entity 1: stopping rather than guessing."); return
    chain = chains[0]
    rows_c = sorted((r for r in scheme if r.get("pdb_strand_id") == chain), key=lambda r: int(r["seq_id"]))
    three = {"ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E","GLY":"G","HIS":"H","ILE":"I",
             "LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P","SER":"S","THR":"T","TRP":"W","TYR":"Y","VAL":"V"}
    pigseq = "".join(three.get(r.get("mon_id"), "X") for r in rows_c)
    auth_of = {k + 1: r.get("pdb_seq_num") for k, r in enumerate(rows_c)}
    unobserved = {k + 1 for k, r in enumerate(rows_c) if r.get("pdb_mon_id") in ("?", ".")}
    for c in chains:
        rc = sorted((r for r in scheme if r.get("pdb_strand_id") == c), key=lambda r: int(r["seq_id"]))
        un = [r.get("pdb_seq_num") for r in rc if r.get("pdb_mon_id") in ("?", ".")]
        runs, start = [], None
        for x in [int(v) for v in un if str(v).lstrip("-").isdigit()]:
            if start is None: start = prev = x
            elif x == prev + 1: prev = x
            else: runs.append((start, prev)); start = prev = x
        if start is not None: runs.append((start, prev))
        print("chain %s: %d residues in the sample, %d unresolved; runs (author numbering): %s"
              % (c, len(rc), len(un), ", ".join("%d-%d" % r for r in runs) or "none"))

    human = fasta(HUMAN)
    try: print("pig UniProt %s: %d aa (for reference; the alignment uses the structure's own sequence)" % (pig, len(fasta(pig))))
    except Exception as e: print("pig UniProt %s not fetched (%s); the alignment uses the structure's own sequence" % (pig, e))
    scoring, pairs = align(human, pigseq)
    ident = sum(1 for i, j in pairs if i and j and human[i-1] == pigseq[j-1])
    aligned = sum(1 for i, j in pairs if i and j)
    print("\nhuman %s (%d aa) vs 8SGW chain %s sample sequence (%d aa): %s" % (HUMAN, len(human), chain, len(pigseq), scoring))
    print("identity over aligned positions: %d/%d (%.1f%%)" % (ident, aligned, 100.0 * ident / max(1, aligned)))
    h2p = {i: j for i, j in pairs if i}
    print("\nhuman  aa  -> 8SGW author  aa  in 8SGW")
    rows, mapped = [], []
    for h in range(HUMAN_RANGE[0], HUMAN_RANGE[1] + 1):
        p = h2p.get(h)
        auth = auth_of.get(p) if p else None
        state = "no pig counterpart" if not p else ("UNRESOLVED" if p in unobserved else "observed")
        rows.append(state)
        if auth and str(auth).lstrip("-").isdigit(): mapped.append(int(auth))
        print("%5d  %s  -> %5s  %s  %s" % (h, human[h-1], auth or "-", pigseq[p-1] if p else "-", state))
    print("\nsummary: human %d-%d -> 8SGW author %s-%s; %d unresolved, %d observed, %d without a pig counterpart"
          % (HUMAN_RANGE[0], HUMAN_RANGE[1], min(mapped) if mapped else "-", max(mapped) if mapped else "-",
             rows.count("UNRESOLVED"), rows.count("observed"), rows.count("no pig counterpart")))

    nb = os.path.expanduser("~/.vintos/workspace/memory/chemistry-lab/notebook.jsonl")
    print("\nhis Lab notebook rows on pendrin / STAS / 8SGW (newest 12, unchanged):")
    hits = []
    if os.path.exists(nb):
        with open(nb, errors="replace") as f:
            for n, line in enumerate(f, 1):
                if re.search(r"SLC26A4|pendrin|8SGW|ZBTB16", line, re.I):
                    try: r = json.loads(line)
                    except Exception: continue
                    hits.append((n, r.get("at", "")[:16], r.get("kind"), str((r.get("inquiry") or {}).get("question") or r.get("note") or "")[:110]))
    for h in hits[-12:]: print("  line %d  %s  %s  %s" % h)
    print("  (%d rows in all)" % len(hits))


if __name__ == "__main__":
    main()
