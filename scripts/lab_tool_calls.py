"""Normalize a Lab request by its actual operation, without changing its inputs."""
from __future__ import annotations
import re


def normalize_plugin(request, purpose=''):
    """Return (public source, connector request); unknown operations stay explicit."""
    if not isinstance(request, dict): return None, request
    out = dict(request)
    plugin = str(out.get('plugin') or '').lower()
    tool = str(out.get('tool') or '')
    args = out.get('arguments') or {}
    if not isinstance(args, dict): return None, out
    # A connector operation identifies its owner even if the planner put a
    # database name in the plugin field. Paid operations still reach its policy.
    bare = tool.split('.')[-1]
    if bare.startswith('boltz_'):
        return None, dict(out, plugin='boltz', tool=bare)
    if bare in ('predict_immunogenicity',):
        return None, dict(out, plugin='eden', tool=bare)
    if plugin in ('atlas', 'alphagenome'):
        gene = args.get('gene') or args.get('gene_symbol')
        if not gene:
            from lab_sources import human_question_symbols
            symbols = human_question_symbols(purpose)
            if len(symbols) == 1: gene = symbols[0]
        if gene:
            return dict(args, source='atlas', gene=gene), None
        if args.get('chromosome') and args.get('start') is not None and args.get('end') is not None:
            return dict(args, source='atlas'), None
    if plugin in ('pdb', 'rcsb'):
        entry = next((args.get(k) for k in ('entry_id', 'pdb_id', 'pdb_code', 'id') if args.get(k)), None)
        if entry:
            return {'source': 'pdb', 'entry_id': entry, 'operation': 'structure_evidence'}, None
        if args.get('accession'):
            return dict(args, source='pdb', operation='search_accession'), None
    if plugin in ('ncbi', 'entrez'):
        op = args.get('operation') or args.get('database') or args.get('db') or bare
        return dict(args, source='ncbi', operation=op), None
    return None, out


def normalize_inquiry(value):
    out = dict(value)
    sq = out.get('source_query')
    if isinstance(sq, dict):
        tool = str(sq.get('tool') or sq.get('operation') or '')
        import plugin_catalog
        import claude_connector_catalog
        plugins = getattr(plugin_catalog, 'PLUGINS', {})
        account_plugins = getattr(claude_connector_catalog, 'PLUGINS', {})
        source = str(sq.get('source') or '')
        # pubmed and chembl are public Lab sources and account connectors both: a source request is the connector's
        # call only when it names one of the connector's own tools. {"source":"pubmed","operation":"literature"}
        # went to the connector as "pubmed.literature" and was refused by its policy, 25 times by 25 October.
        account = account_plugins.get(source)
        if source in ('pubmed', 'chembl') and isinstance(account, dict) and tool.split('.')[-1] not in (
                set(account.get('read') or ()) | set(account.get('action') or ())):
            tool = ''
        if tool and (source in plugins or source in account_plugins or tool.split('.')[-1].startswith('boltz_')):
            arguments = sq.get('arguments')
            if arguments is None:
                arguments = {k:v for k,v in sq.items() if k not in ('source','tool','operation')}
            public, connector = normalize_plugin({'plugin':source,'tool':tool,'arguments':arguments},
                                                  str(out.get('question') or ''))
            if connector:
                out.update(source_query=None, plugin_query=connector)
            elif public:
                out.update(source_query=public, plugin_query=None)
    public, connector = normalize_plugin(out.get('plugin_query'), str(out.get('question') or ''))
    if public and not out.get('source_query'):
        out.update(source_query=public, plugin_query=None)
    elif connector:
        out['plugin_query'] = connector
    return out


NCBI_OPERATIONS = {
    'search_taxonomy': 'taxonomy', 'taxon': 'taxonomy', 'taxonomies': 'taxonomy',
    'search_assemblies': 'assembly', 'assemblies': 'assembly', 'genome': 'assembly',
    'search_genes': 'gene', 'genes': 'gene',
    'search_proteins': 'protein', 'proteins': 'protein',
    'pubmed': 'literature', 'search_pubmed': 'literature', 'search_articles': 'literature',
    'search_literature': 'literature', 'nucleotide': 'sequence', 'nuccore': 'sequence',
}
UNIPROT_ACCESSION = r'(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})'


def normalize_source(spec):
    out = dict(spec)
    source = str(out.get('source') or '').lower()
    out['source'] = {'rcsb': 'pdb', 'alphagenome': 'atlas', 'entrez': 'ncbi',
                     'ncbi_rt_locus_screen': 'rt_locus_screen'}.get(source, source)
    if out['source'] == 'pubmed':
        citation = out.get('query') or out.get('term')
        if isinstance(citation, str) and re.fullmatch(r'[1-9][0-9]{0,19}', citation.strip()) and not out.get('pmids'):
            out = {k: v for k, v in out.items() if k not in ('query', 'term')}
            out.update(source='pubmed_abstracts', pmids=[citation.strip()])
    if out['source'] == 'uniprot':
        query=out.get('query') or out.get('accession')
        if isinstance(query,str) and re.fullmatch(UNIPROT_ACCESSION,query.upper()):
            out['query']='accession:'+query.upper()
        # An NCBI protein accession.version (DBB25069.1, NP_000483.3) is no UniProt accession: UniProt answered
        # HTTP 400 every time it was asked for one (DBB25069.1, from an NCBI protein search, 24-25 October). Its
        # record is NCBI's, and that is the one read.
        bare=re.sub(r'^\s*accession\s*:\s*','',query.strip()) if isinstance(query,str) else ''
        if re.fullmatch(r'(?:[A-Z]{3}[0-9]{5}(?:[0-9]{2})?|(?:NP|XP|YP|WP|AP)_[0-9]{6,9})\.[1-9][0-9]*',bare):
            out={'source':'ncbi_protein_context','accession':bare}
    if out['source'] == 'interpro' and not out.get('accession'):
        value=out.get('uniprot_accession') or out.get('protein_accession') or out.get('query') or out.get('id')
        if value is not None:out['accession']=value
    if out['source'] == 'pdb' and not out.get('entry_id'):
        # 22 October: {"source": "pdb", "query": "entry_id:6V7X"} failed "PDB entry ID required" again and again
        for key in ('pdb_id', 'pdb_code', 'id', 'query'):
            value = re.sub(r'^\s*(?:entry_id|pdb_id|pdb|entry)\s*[:=]\s*', '', str(out.get(key) or ''), flags=re.I).strip()
            if re.fullmatch(r'[0-9][A-Za-z0-9]{3}', value):
                out.pop(key); out['entry_id'] = value.upper()
                break
    if out['source'] == 'pdb' and not out.get('entry_id') and not out.get('operation') and isinstance(out.get('query'), str):
        # 26 October: a pdb query holding a UniProt accession, or one entry id inside words, still failed "PDB entry ID
        # required". An accession is the archive's accession search; one id among words is that entry. Anything else
        # (free text, two ids) is left for the source to refuse.
        q = out['query'].strip()
        if re.fullmatch(r'[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2}', q):
            out.pop('query'); out.update(operation='search_accession', accession=q)
        else:
            ids = set(m.upper() for m in re.findall(r'\b([1-9](?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{3})\b', q))
            if len(ids) == 1:
                out.pop('query'); out['entry_id'] = ids.pop()
    if out['source'] == 'ncbi':
        op = str(out.get('operation') or out.get('database') or out.get('db') or '').lower()
        # Remove a transport prefix, not any scientific qualifier.
        op = re.sub(r'^(?:ncbi[._]|entrez[._])', '', op)
        out['operation'] = NCBI_OPERATIONS.get(op, op)
        if not out.get('term'):
            out['term'] = out.get('query') or out.get('search_term')
        if out['operation'] == 'sequence' and out.get('accession'):
            out['source'] = 'ncbi_sequence'
            out['database'] = 'nuccore' if op in ('nuccore', 'nucleotide') else out.get('database', 'protein')
    return out


def is_measurement(inquiry):
    if inquiry.get('instrument_query'): return True
    pq = inquiry.get('plugin_query') or {}
    plugin, tool = pq.get('plugin'), pq.get('tool')
    return (plugin == 'nvidia_nim' and tool in ('nvidia_nim.boltz2', 'nvidia_nim.diffdock',
            'nvidia_nim.proteinmpnn', 'nvidia_nim.rfdiffusion') or
            plugin == 'nvmolkit' and tool in ('nvmolkit.fingerprints', 'nvmolkit.similarity',
            'nvmolkit.cluster', 'nvmolkit.conformers') or
            plugin == 'inductive' and tool == 'inductive.predict_properties' or
            plugin == 'genomic_intelligence' and str(tool).startswith('genomic_intelligence.predict_') or
            plugin == 'eden' and tool == 'predict_immunogenicity')


def normalize_request(route, request):
    """Accept explicit source/door shorthands while keeping the authored request in the step."""
    wrappers={'source':'source_query','plugin':'plugin_query','instrument':'instrument_query'}
    wrapper=wrappers.get(route)
    if wrapper and set(request)=={wrapper} and isinstance(request[wrapper],dict):request=dict(request[wrapper])
    if route=='source' and isinstance(request.get('source'),str) and set(request)=={'source',request['source']}:
        # {"source":"pubmed","pubmed":"<search>"}: the query under the source's own name is the shorthand below
        # with the source said twice; it was refused as having no search terms (25 October)
        request={request['source']:request[request['source']]}
    allowed={'uniprot','ncbi','pdb','atlas','interpro','pubchem','pubmed','chembl','ncbi_sequence',
             'ncbi_protein_context','ncbi_neighborhood','rt_locus_screen','mgnify','reactome','rhea','quickgo','imgvr','bvbrc'}
    if route=='source' and not request.get('source'):
        request={k:v for k,v in request.items() if k!='source'}
        # A source named where its operation goes ({"operation":"rt_locus_screen","accession":...}), or a UniProt
        # accession query with no source ({"query":"accession:O43511"}): each names one source, and each was
        # refused as an empty source ("unsupported Lab source", 25 October)
        if request.get('operation') in allowed:
            request=dict({k:v for k,v in request.items() if k!='operation'},source=request['operation'])
        elif set(request)=={'query'} and re.fullmatch(r'accession:'+UNIPROT_ACCESSION,str(request['query']).strip()):
            request={'source':'uniprot','query':request['query'].strip()}
    if route=='source' and not request.get('source') and len(request)==1:
        source,value=next(iter(request.items()))
        if source in allowed:
            if isinstance(value,dict):request=dict(value,source=source)
            elif isinstance(value,str) and source=='uniprot':request={'source':'uniprot','query':value}
            elif isinstance(value,str) and source=='pdb':request={'source':'pdb','entry_id':value}
            elif isinstance(value,str) and source in ('interpro','ncbi_sequence','ncbi_protein_context','rt_locus_screen'):
                request={'source':source,'accession':value}
            elif isinstance(value,str) and source=='pubchem':request={'source':source,'name':value}
            elif isinstance(value,str) and source=='pubmed':request={'source':source,'query':value}
    if route=='source':return normalize_source(request)
    if route=='instrument':return normalize_instrument(request)
    return request


def _flat(word):
    return re.sub(r'[^a-z0-9]', '', str(word or '').lower())


def canonical(word, names):
    """The one name in names that word spells, ignoring case, spaces, hyphens, dots and underscores; None when it
    spells none or more than one."""
    if not isinstance(word, str) or not word.strip():
        return None
    if word in names:
        return word
    hits = [n for n in names if _flat(n) == _flat(word)]
    return hits[0] if len(hits) == 1 else None


# keys the planner has put an instrument's name under instead of "skill" (26 October: "instrument" 31 times)
_SKILL_KEYS = ('instrument', 'instrument_name', 'skill_name', 'name', 'tool')
# keys she has put one Lab artifact under instead of "files"
_FILE_KEYS = ('artifact', 'structure_id', 'structure', 'model', 'file', 'structure_file', 'model_file', 'path')


def _artifact(value):
    """The one Lab artifact a value names: its listed path, its file name, or (for an accession) the protein's only
    ESMFold model; None when it names none or several."""
    if not isinstance(value, str) or not value.strip():
        return None
    import lab_instruments
    listed = lab_instruments.artifacts('structure', 50) + lab_instruments.artifacts('sequence', 50)
    v = value.strip()
    if '/memory/chemistry-lab/' in v:
        v = v.split('/memory/chemistry-lab/', 1)[1]
    if v in listed:
        return v
    named = [f for f in listed if f.rsplit('/', 1)[-1] == v.rsplit('/', 1)[-1]]
    if len(named) == 1:
        return named[0]
    if re.fullmatch(r'[A-Za-z0-9]{4,12}', v):
        models = [f for f in listed if f.startswith('artifacts/esmfold/%s-' % v.upper()) and f.endswith('.pdb')]
        if len(models) == 1:
            return models[0]
    return None


def normalize_instrument(request):
    """Name the instrument when the planner named only its operation, or put the instrument's name where the
    operation goes ({"operation":"fold_read"}): each operation belongs to one instrument, so nothing is guessed. 125
    investigation steps in two days were refused as "not offered" for this alone (23 October).

    Also read, when exactly one thing is meant: the instrument's name under another key ({"instrument":
    "fold_read"}) or as a key of its own ({"fold_read": {...}}), its name or operation in another spelling
    ("Fold-Read", "analyze" for structure.analyze), the one operation of a one-operation instrument left out, and one
    Lab artifact under another key ({"artifact": <a listed model>}). On 26 October 42 steps were refused as "not
    offered" for these shapes, every one with "instrument:None" as its tool."""
    from lab_instruments import OFFERED
    from lab_native_instruments import OPERATIONS
    request=dict(request)
    wrapped=request.get('protein_design_mcp')
    if isinstance(wrapped,dict) and wrapped.get('tool') in _mcp_tools() and set(request)<={'protein_design_mcp','question'}:
        # {"protein_design_mcp": {"tool": "predict_structure_boltz", ...}}: the menu's own heading around the call
        request=dict(wrapped,**({'question':request['question']} if request.get('question') else {}))
    if request.get('tool') in _mcp_tools():
        return request
    names=list(OFFERED)+list(OPERATIONS)
    ops_of=lambda s: list(OFFERED.get(s) or ())+([OPERATIONS[s]] if s in OPERATIONS else [])
    if isinstance(request.get('skill'),str) and request['skill'] not in names:
        named=canonical(request['skill'],names)
        if named:request['skill']=named
    if not request.get('skill'):
        for key in _SKILL_KEYS:
            named=canonical(request.get(key),names)
            if named and not (key=='tool' and request.get(key) in _mcp_tools()):
                request['skill']=named
                if key!='tool':request.pop(key)
                break
    if not request.get('skill') and not request.get('operation'):
        for key in _SKILL_KEYS[:-1]:     # an operation under the instrument's key: {"instrument": "structure.analyze"}
            named=canonical(request.get(key),[o for s in names for o in ops_of(s)])
            if named:
                request.pop(key);request['operation']=named
                break
    if not request.get('skill'):
        own=[k for k in request if canonical(k,names)]
        if len(own)==1:
            key=own[0];inner=request.pop(key);request['skill']=canonical(key,names)
            if isinstance(inner,dict) and set(inner)!={'step','path'}:
                request={**inner,**request}
            elif isinstance(inner,str) and _artifact(inner) and not request.get('files'):
                request['files']=[_artifact(inner)]
            elif inner not in (None,'',{},[]):
                request[key]=inner      # kept as given; the instrument's own checks say what is missing
    if isinstance(request.get('operation'),str) and request.get('operation') not in [o for s in names for o in ops_of(s)] \
            and request['operation'] not in names:
        pool=ops_of(request['skill']) if request.get('skill') in names else [o for s in names for o in ops_of(s)]
        named=canonical(request['operation'],pool)
        if not named:   # "analyze" for structure.analyze: the part after the dot, if only one operation has it
            tail=[o for o in pool if _flat(o.rsplit('.',1)[-1])==_flat(request['operation'])]
            named=tail[0] if len(tail)==1 else None
        if not named:
            named=canonical(request['operation'],names)   # an instrument's name where the operation goes
        if named:request['operation']=named
    if not request.get('skill') and request.get('operation') in names and len(ops_of(request['operation']))>1:
        # {"operation": "structure_viewer"}: the instrument is named, its operation is not; that is asked for, not guessed
        request['skill']=request.pop('operation')
    if request.get('skill') in names and not request.get('operation') and len(ops_of(request['skill']))==1:
        request['operation']=ops_of(request['skill'])[0]
    if not request.get('files'):
        for key in _FILE_KEYS:
            found=_artifact(request.get(key))
            if found:
                request['files']=[found];request.pop(key)
                break
    skill,op=request.get('skill'),request.get('operation')
    # An explicit single-operation instrument name identifies its reader even
    # when the request also carries the generic viewer skill.
    if op in OFFERED and len(OFFERED[op]) == 1:
        request.update(skill=op, operation=OFFERED[op][0])
        return request
    # An operation only one instrument has names it under another instrument's name too:
    # {"skill":"structure_viewer","operation":"structure.read"} is fold_read's read (25 October).
    owners=[k for k,v in OFFERED.items() if op in v]
    if skill in OFFERED and op not in OFFERED[skill] and len(owners)==1:
        request.update(skill=owners[0])
        return request
    if skill in OFFERED or skill in OPERATIONS:return request
    if op in OFFERED and len(OFFERED[op])==1:skill,op=op,OFFERED[op][0]
    elif op in OPERATIONS:skill,op=op,OPERATIONS[op]
    else:
        owners=[k for k,v in OFFERED.items() if op in v]+[k for k,v in OPERATIONS.items() if v==op]
        if len(owners)!=1:return request
        skill=owners[0]
    request.update(skill=skill,operation=op)
    return request


def _mcp_tools():
    try:
        from chemistry_mcp import TOOLS
        return TOOLS
    except Exception:
        return frozenset(("score_stability", "suggest_hotspots", "predict_structure_boltz", "predict_complex"))


def execution_request(route, request):
    """Normalize structural cardinality after exact references have been resolved."""
    out=dict(request)
    if route=='source':
        out=normalize_source(out)
        if out.get('source')=='interpro' and out.get('accession'):
            out={k:v for k,v in out.items() if k not in ('query','id','uniprot_accession','protein_accession')}
    if route=='representation' and isinstance(out.get('records'),dict):
        record=out['records']
        if isinstance(record.get('sequence'),str) and record.get('accession'):out['records']=[record]
    if route in ('instrument','native') and isinstance(out.get('files'),str):out['files']=[out['files']]
    return out
