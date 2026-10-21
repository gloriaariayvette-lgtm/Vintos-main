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


def normalize_source(spec):
    out = dict(spec)
    source = str(out.get('source') or '').lower()
    out['source'] = {'rcsb': 'pdb', 'alphagenome': 'atlas', 'entrez': 'ncbi',
                     'ncbi_rt_locus_screen': 'rt_locus_screen'}.get(source, source)
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
