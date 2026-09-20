"""Atlas observation -> reference-checked local Evo 2 question, never sequence design."""
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlencode
from lab_sources import fetch_json


def choose_variant(result):
    if result.get('source') != 'atlas' or result.get('metadata',{}).get('assembly') != 'GRCh38':
        raise ValueError('GRCh38 Atlas receipt required')
    candidates=[]
    for scorer, matrix in result['records'].items():
        quantiles=matrix.get('quantiles')
        # Raw scales differ across scorers. Do not rank them as if comparable.
        if quantiles is None: continue
        for variant, row in zip(matrix.get('variants',[]),quantiles,strict=True):
            finite=[float(x) for x in row if x is not None and math.isfinite(float(x)) and 0 <= float(x) <= 1]
            if finite: candidates.append((max(finite),scorer,variant))
    if not candidates: raise ValueError('no calibrated quantile with an explicit source variant; choose manually')
    quantile,scorer,variant=max(candidates,key=lambda x:x[0])
    return dict(variant,selection_scorer=scorer,selection_quantile=quantile)


def prepare(result, *, fetch=fetch_json):
    v=choose_variant(result)
    chrom=v['chromosome'];position=v['position'];ref=v['reference_bases'];alt=v['alternate_bases']
    if not re.fullmatch(r'chr(?:[1-9]|1[0-9]|2[0-2]|X|Y)',chrom) or type(position) is not int or position < 1:
        raise ValueError('invalid genomic coordinate')
    if ref not in 'ACGT' or alt not in 'ACGT' or len(ref)!=1 or len(alt)!=1 or ref==alt:
        raise ValueError('single nucleotide source variant required')
    start=max(1,position-255);stop=start+511
    url='https://rest.ensembl.org/sequence/region/human/'+chrom[3:]+f':{start}..{stop}:1?'+urlencode(
        {'coord_system_version':'GRCh38','content-type':'application/json'})
    raw,_=fetch(url)
    # Returned coordinate identity must bind the requested assembly and strand.
    identity=str(raw.get('id',''))
    expected=f'chromosome:GRCh38:{chrom[3:]}:{start}:{stop}:1'
    if identity != expected: raise ValueError('reference provider returned a different assembly, interval or strand')
    sequence=str(raw.get('seq','')).upper();offset=position-start
    if len(sequence)!=512 or not re.fullmatch('[ACGTN]+',sequence) or sequence[offset]!=ref:
        raise ValueError('reference allele/window mismatch')
    payload={'source_key':'atlas_grch38','source':'Ensembl GRCh38 reference + AlphaGenome Atlas',
             'accession':identity,'taxon_id':9606,'organism':'Homo sapiens public reference',
             'start':start,'stop':stop,'source_header':'>'+identity,'sequence':sequence,
             'sequence_sha256':hashlib.sha256(sequence.encode()).hexdigest(),
             'fetched_at':datetime.now(timezone.utc).isoformat(),'atlas_receipt_id':result['receipt_id'],
             'atlas_variant':v,'variant_offset':offset,
             'truth_status':'reference_checked_public_variant_question_not_clinical_inference'}
    validate_payload(payload)
    return payload


def validate_payload(p):
    sequence=p.get('sequence','');v=p.get('atlas_variant') or {};offset=p.get('variant_offset')
    if p.get('source_key')!='atlas_grch38' or p.get('taxon_id')!=9606:
        raise ValueError('Atlas reference source required')
    if len(sequence)!=512 or not re.fullmatch('[ACGTN]+',sequence) or hashlib.sha256(sequence.encode()).hexdigest()!=p.get('sequence_sha256'):
        raise ValueError('bounded reference sequence digest required')
    if type(offset) is not int or not 0<=offset<len(sequence) or sequence[offset]!=v.get('reference_bases'):
        raise ValueError('source allele mismatch')
    if v.get('alternate_bases') not in ('A','C','G','T') or v['alternate_bases']==v['reference_bases']:
        raise ValueError('single observed alternate required')
    if not re.fullmatch('[a-f0-9]{64}',str(p.get('atlas_receipt_id',''))):raise ValueError('source receipt missing')
    if v.get('position') != p.get('start',-1)+offset: raise ValueError('coordinate conversion mismatch')
    return sequence


def analyze(result):
    import chemistry_lab as lab
    if not lab.config().get('atlas_evo2_enabled'): raise RuntimeError('Atlas-directed Evo 2 not enabled')
    import chemistry_evo2
    payload=prepare(result)
    return chemistry_evo2.analyze(source_payload=payload)
