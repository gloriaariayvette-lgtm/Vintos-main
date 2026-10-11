"""Bounded authoritative locus lookup and its original-action evidence contract."""
import hashlib
import re
from urllib.parse import quote
from lab_sources import receipt, fetch_json

SPECIES = {'human':('homo_sapiens',9606),'homo sapiens':('homo_sapiens',9606),
           'homo_sapiens':('homo_sapiens',9606),'mouse':('mus_musculus',10090),
           'mus musculus':('mus_musculus',10090),'mus_musculus':('mus_musculus',10090)}
SCOPES = {('hgnc',9606),('ensembl',9606),('ensembl',10090),('ncbi_gene',9606),('ncbi_gene',10090)}

def request_digest(text):return hashlib.sha256(text.encode()).hexdigest()

def commissioned(original, args):
    species,target=args.get('species'),args.get('gene')
    if not isinstance(species,str) or species.lower() not in SPECIES or not isinstance(target,str):return False
    if not re.fullmatch('[A-Za-z][A-Za-z0-9-]{0,29}',target):return False
    original=original.split('\nSource packet (untrusted observations):',1)[0]
    action=original.removeprefix('The Lab needs an instrument it does not have:').strip()
    named=rf'(?:{re.escape(species)}\s+{re.escape(target)}|{re.escape(target)}\s+(?:in\s+)?{re.escape(species)})'
    return bool(re.fullmatch(rf'verify\s+(?:that\s+)?{named}\s+(?:exists|existence|locus)[.!?]?',action,re.I))

def query_for(row,args):
    query={key:row[key] for key in ('project_id','cycle_id','ownership_sha256')}
    query.update(original_request_sha256=request_digest(row['original_request']),action='verify_gene_locus',
                 target=args['gene'],species=args['species'],taxon_id=SPECIES[args['species'].lower()][1])
    return query

def check(value, row, args):
    from lab_forge_consumer import digest
    query=query_for(row,args)
    unsigned=dict(value);rid=unsigned.pop('receipt_id',None)
    data=value.get('records');taxon=query['taxon_id'];target=query['target']
    if (value.get('source')!='gene_locus_verification' or value.get('query')!=query
            or rid!=digest(unsigned) or value.get('response_sha256')!=digest(data) or not isinstance(data,dict)):
        raise ValueError('locus receipt integrity or ownership mismatch')
    reference=data.get('reference') or {}
    if (data.get('action')!='verify_gene_locus' or data.get('requested_target')!=target
            or type(data.get('taxon_id')) is not int or data['taxon_id']!=taxon or data.get('query_completed') is not True
            or (reference.get('provider'),taxon) not in SCOPES
            or not isinstance(reference.get('release'),str) or not re.fullmatch('[A-Za-z0-9_. -]{1,80}',reference['release'])):
        raise ValueError('reference is incomplete or outside provider taxonomy scope')
    matches=data.get('matches')
    if data.get('verdict')=='not_found_in_reference' and matches==[]:return 'verified_absent'
    if data.get('verdict')!='present' or not isinstance(matches,list) or len(matches)!=1:raise ValueError('ambiguous locus')
    match=matches[0]
    if (match.get('symbol')!=target or type(match.get('taxon_id')) is not int or match['taxon_id']!=taxon
            or any(not isinstance(match.get(k),str) or not re.fullmatch('[A-Za-z0-9_.:-]{1,100}',match[k]) for k in ('gene_id','assembly','chromosome'))
            or match.get('coordinate_system') not in ('0-based-half-open','1-based-inclusive')
            or type(match.get('start')) is not int or type(match.get('end')) is not int
            or match['start'] < (1 if match['coordinate_system']=='1-based-inclusive' else 0)
            or match['end'] < match['start']+(match['coordinate_system']=='0-based-half-open')):
        raise ValueError('exact target and sourced locus required')
    return 'verified_present'

def lookup(row,args,*,fetch=fetch_json):
    """Three or four bounded reads; HTTP errors and ambiguity are never absence."""
    species,taxon=SPECIES[args['species'].lower()];target=args['gene']
    if not re.fullmatch('[A-Za-z][A-Za-z0-9-]{0,29}',target):raise ValueError('exact symbol required')
    base='https://rest.ensembl.org'
    def get(path):return fetch(base+path+('&' if '?' in path else '?')+'content-type=application/json')[0]
    release=get('/info/data')
    releases=release.get('releases') if isinstance(release,dict) else None
    if not isinstance(releases,list) or len(releases)!=1 or type(releases[0]) is not int or releases[0]<1:
        raise ValueError('one current Ensembl release required')
    xrefs=get('/xrefs/symbol/'+species+'/'+quote(target,safe='')+'?object_type=gene')
    if not isinstance(xrefs,list) or len(xrefs)>8:raise ValueError('bounded gene matches required')
    if any(not isinstance(x,dict) or x.get('type')!='gene' or not isinstance(x.get('id'),str) or
           not re.fullmatch('ENS[A-Z]*G[0-9]{6,20}',x['id']) for x in xrefs):raise ValueError('invalid gene identifier')
    ids=set(x['id'] for x in xrefs)
    if len(ids)>1:raise ValueError('ambiguous gene reference')
    matches=[]
    if ids:
        gene=get('/lookup/id/'+next(iter(ids)))
        if (gene.get('id') not in ids or gene.get('object_type')!='Gene' or gene.get('species')!=species
                or gene.get('display_name')!=target):raise ValueError('reference target differs from original')
        matches=[dict(symbol=gene['display_name'],taxon_id=taxon,gene_id=gene['id'],assembly=gene.get('assembly_name'),
                      chromosome=gene.get('seq_region_name'),coordinate_system='1-based-inclusive',start=gene.get('start'),end=gene.get('end'))]
    if get('/info/data')!=release:raise ValueError('reference release changed during lookup')
    data=dict(action='verify_gene_locus',requested_target=target,taxon_id=taxon,query_completed=True,
              reference={'provider':'ensembl','release':str(releases[0])},
              verdict='present' if matches else 'not_found_in_reference',matches=matches)
    value=receipt('gene_locus_verification',query_for(row,args),data,
                  metadata={'scope':'exact named reference lookup; no universal absence or sequence-handle claim'})
    check(value,row,args)
    return value

def send_ack(cfg,body):
    """Reuse the configured local intake credential; no redirects or new secrets."""
    import json
    from urllib.parse import urlsplit,urlunsplit
    from urllib.request import Request,build_opener,HTTPRedirectHandler
    from forge_loop_runtime import secret
    endpoint=cfg.get('forge_report_intake') or {}
    parsed=urlsplit(endpoint.get('url',''))
    if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.path!='/api/lab-intake'
            or parsed.username or parsed.password or parsed.query or parsed.fragment):raise ValueError('dedicated local intake required')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    token=secret(endpoint['token_file'])
    url=urlunsplit((parsed.scheme,parsed.netloc,'/api/lab-verification','',''))
    request=Request(url,data=json.dumps(body).encode(),method='POST',
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
    with build_opener(NoRedirect).open(request,timeout=10) as response:
        raw=response.read(8193)
        if len(raw)>8192:raise ValueError('oversized acknowledgement')
        result=json.loads(raw)
        if response.status!=200:raise ValueError('acknowledgement refused')
        return result
