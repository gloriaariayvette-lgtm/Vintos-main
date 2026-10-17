#!/usr/bin/env python3
"""Offline verification of this fixed 9UTC evidence packet using existing Lab tools and BioPython.
No downloads, model calls, folding, or state changes. This is a reproducibility check, not a new reader.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys


def verify(packet, scripts):
    packet, scripts = Path(packet), Path(scripts)
    manifest = json.loads((packet / 'packet-sha256.json').read_text())
    for name, expected in manifest.items():
        assert Path(name).name == name
        assert hashlib.sha256((packet/name).read_bytes()).hexdigest() == expected, name
    record = json.loads((packet/'verified-record.json').read_text())
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict
    from Bio.PDB import MMCIFParser
    sys.path.insert(0, str(scripts))
    import chemistry_reference_compare as compare
    from lab_sources import Sources
    cif = gzip.decompress((packet/'9UTC.cif.gz').read_bytes())
    pdb = gzip.decompress((packet/'9UTC.pdb.gz').read_bytes())
    assert len(cif) <= 4*1024*1024 and len(pdb) <= 4*1024*1024
    d = MMCIF2Dict(io.StringIO(cif.decode('utf-8')))
    def rows(prefix):
        keys = [k for k in d if k.startswith(prefix)]
        return [dict(zip([k[len(prefix):] for k in keys], vs)) for vs in zip(*(d[k] for k in keys))]
    def intervals(values):
        out = []
        for n in sorted(set(values)):
            if out and out[-1][1]+1 == n: out[-1][1] = n
            else: out.append([n,n])
        return out
    assert d['_entry.id'] == ['9UTC']
    atoms = [a for a in rows('_atom_site.') if a['pdbx_PDB_model_num']=='1'
             and a['label_alt_id'] in ('.','A') and float(a['occupancy']) > 0
             and a['group_PDB']=='ATOM' and a['auth_asym_id']=='B']
    observed = {int(a['auth_seq_id']) for a in atoms}
    assert intervals(observed) == record['observed_native_residue_intervals'] == [[22,356],[366,556]]
    assert len(observed) == record['observed_native_residue_count'] == 526
    assert all(a['label_entity_id']=='2' and a['label_asym_id']=='B' for a in atoms)
    mapping = next(r for r in rows('_struct_ref_seq.') if r['pdbx_db_accession']=='Q7RTX0')
    assert [int(mapping[k]) for k in ('seq_align_beg','seq_align_end','db_align_beg','db_align_end')] == [29,860,21,852]
    assert all(int(a['label_seq_id'])-8==int(a['auth_seq_id']) for a in atoms)
    missing = {int(r['label_seq_id']) for r in rows('_pdbx_unobs_or_zero_occ_residues.') if r['label_asym_id']=='B'}
    modeled = {int(a['label_seq_id']) for a in atoms}
    assert missing == set(range(1,1131))-modeled
    instance = json.loads((packet/'core-polymer_entity_instance-9UTC-B.json').read_text())
    reported = [[p['beg_seq_id'],p['end_seq_id']] for f in instance['rcsb_polymer_instance_feature']
                if f['type']=='UNOBSERVED_RESIDUE_XYZ' for p in f['feature_positions']]
    assert intervals(missing) == reported == [[1,29],[365,373],[565,1130]]
    structure = MMCIFParser(QUIET=True).get_structure('9UTC',io.StringIO(cif.decode('utf-8')))
    assert intervals(r[0] for r in compare._residues(structure,'B')) == intervals(observed)
    entry = json.loads((packet/'core-entry-9UTC.json').read_text())
    def fetch(url):
        assert url=='https://data.rcsb.org/rest/v1/core/entry/9UTC'
        return entry, {}
    def coordinates(url):
        assert url=='https://files.rcsb.org/download/9UTC.pdb'
        return pdb.decode('ascii')
    result = Sources(fetch=fetch,fetch_structure=coordinates).query(json.loads((packet/'source-query.json').read_text()))
    assert next(c for c in result['records'][0]['geometry']['chains'] if c['chain']=='B')['observed_residues']==526
    assert result['response_sha256'] == json.loads((packet/'lab-structure-receipt.json').read_text())['response_sha256']
    assert hashlib.sha256(record['original_question'].encode()).hexdigest()==record['question_sha256']
    assert record['ligand_interpretation']['publication_supported_binding_subunit']=='TAS1R2 Venus flytrap domain'
    assert record['ligand_interpretation']['TAS1R3_direct_sucralose_binding_supported'] is False
    return {'verified': True, 'entry':'9UTC','chain':'B','accession':'Q7RTX0',
            'observed_native_residues':len(observed),'intervals':intervals(observed),
            'existing_readers':'lab_sources.Sources and chemistry_reference_compare._residues',
            'coordinate_and_missing_annotation_checks':'passed','network_calls':0,'models_called':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scripts',type=Path,default=Path(__file__).resolve().parents[3]/'scripts')
    args=parser.parse_args()
    print(json.dumps(verify(Path(__file__).resolve().parent,args.scripts),indent=2))
