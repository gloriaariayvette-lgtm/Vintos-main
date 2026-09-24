#!/usr/bin/env python3
"""Scratch-only IMG/VR acquisition and query contracts. No live network or host stores."""
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SCRATCH = tempfile.TemporaryDirectory(prefix='imgvr-test-')
os.environ['HOME'] = SCRATCH.name
os.environ['VINTOS_IMGVR_ROOT'] = str(Path(SCRATCH.name)/'imgvr')
sys.path.insert(0, str(REPO/'scripts'))
import imgvr_store as store
import lab_sources
import lab_genome_mining


class Reply(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self,*args): return False


class Tests(unittest.TestCase):
    def setUp(self):
        self.network=patch('urllib.request.urlopen',side_effect=AssertionError('live network forbidden'))
        self.network.start(); self.addCleanup(self.network.stop)
        self.assertTrue(str(store.ROOT).startswith(SCRATCH.name))
        self.assertTrue(str(store.TOKEN_FILE).startswith(SCRATCH.name))

    def manifest_payload(self):
        files=[]
        for index,name in enumerate(sorted(store.EXPECTED)):
            files.append({'_id':format(index+1,'024x'),'file_id':index+1,'file_name':name,
                          'file_size':index+10,'md5sum':format(index+1,'032x'),
                          'file_status':'RESTORED','metadata':{'portal':{'display_location':[store.RELEASE]}}})
        return {'organisms':[{'id':store.DATASET,'files':files}]}

    def test_manifest_is_exact_and_restore_payload_is_bounded(self):
        opener=lambda request,timeout=0:Reply(json.dumps(self.manifest_payload()).encode())
        manifest=store.provider_manifest(opener=opener)
        self.assertEqual({x['file_name'] for x in manifest['files']},store.EXPECTED)
        payload=store._restore_payload(manifest)
        self.assertEqual(set(payload['ids']),{store.DATASET})
        self.assertEqual(len(payload['ids'][store.DATASET]['file_ids']),5)
        changed=self.manifest_payload(); changed['organisms'][0]['files'].pop()
        bad=lambda request,timeout=0:Reply(json.dumps(changed).encode())
        with self.assertRaisesRegex(RuntimeError,'file set changed'):store.provider_manifest(opener=bad)

    def fixture_index(self):
        store.ROOT.mkdir(parents=True,exist_ok=True)
        headers=['UVIG','Taxon_oid','Scaffold_oid',"Coordinates ('whole' if the UViG is the entire contig)",
                 'Ecosystem classification','vOTU','Length','Topology','geNomad score','Confidence',
                 'Estimated completeness','Estimated contamination','MIUViG quality',
                 'Gene content (total genes;cds;tRNA;geNomad marker)','Taxonomic classification',
                 'Taxonomic classification method','Host taxonomy prediction','Host prediction method','Sequence origin (doi)']
        values=['IMGVR_UViG_1_000001','1','2','whole','Environmental;Aquatic;Marine;Oceanic',
                'vOTU_1','240','Linear','0.9','High-confidence','100','0','High-quality','3;3;0;1',
                'r__Duplodnaviria','geNomad','d__Bacteria;p__Proteobacteria','CRISPR spacer match','fixture doi']
        metadata=store.ROOT/'metadata.tsv'; metadata.write_text('\t'.join(headers)+'\n'+'\t'.join(values)+'\n')
        sequence=('ACGTTGCACTGA'+'GATTACA'*30)[:240]
        fasta=store.ROOT/'fixture.fna'; fasta.write_text('>IMGVR_UViG_1_000001|1|2|whole\n'+sequence+'\n')
        connection=sqlite3.connect(store.DB)
        store._build_metadata(connection,metadata); store._build_fasta_index(connection,fasta); connection.commit(); connection.close()
        return fasta,sequence

    def test_local_metadata_and_exact_sequence_are_bounded(self):
        fasta,sequence=self.fixture_index()
        found=store.query({'operation':'metadata','term':'marine Proteobacteria','limit':4},db=store.DB,nucleotide=fasta)
        self.assertEqual(found['records'][0]['uvig'],'IMGVR_UViG_1_000001')
        exact=store.query({'operation':'uvig','uvig':'IMGVR_UViG_1_000001','start':2,'end':21},db=store.DB,nucleotide=fasta)
        self.assertEqual(exact['records'][0]['sequence'],sequence[1:21])
        for bad in ({'operation':'metadata','term':'x'},
                    {'operation':'uvig','uvig':'../secret'},
                    {'operation':'uvig','uvig':'IMGVR_UViG_1_000001','start':0,'end':20}):
            with self.assertRaises(ValueError):store.query(bad,db=store.DB,nucleotide=fasta)

    def test_similarity_runs_only_pinned_local_command_and_wraps_receipt(self):
        fasta,_=self.fixture_index(); mmseqs=store.ROOT/'mmseqs'; mmseqs.write_text('fixture'); mmseqs.chmod(0o700)
        mmdb=store.ROOT/'protein-db'; Path(str(mmdb)+'.dbtype').write_text('fixture')
        (mmdb.parent/'index-ready.json').write_text('{}')
        calls=[]
        def runner(command,**kwargs):
            calls.append(command); Path(command[4]).write_text('IMGVR_UViG_1_000001|1|protein1\t55.5\t42\t1e-20\t88.2\t60\t65\n')
        spec={'source':'imgvr','operation':'protein_similarity','sequence':'ACDEFGHIKLMNPQRSTVWY'*2,'limit':1}
        local=lambda request:store.query(request,db=store.DB,nucleotide=fasta,mmseqs=mmseqs,mmseqs_db=mmdb,runner=runner)
        result=lab_sources.Sources(imgvr=local).query(spec)
        self.assertEqual(result['records'][0]['uvig'],'IMGVR_UViG_1_000001')
        self.assertIn('not_novelty',result['metadata']['interpretation'])
        self.assertEqual(calls[0][0],str(mmseqs)); self.assertEqual(calls[0][1],'easy-search')
        self.assertNotIn(str(Path.home()/'.vintos/workspace'),str(store.ROOT))

    def test_token_permissions_fail_closed(self):
        store.TOKEN_FILE.parent.mkdir(parents=True,exist_ok=True); store.TOKEN_FILE.write_text('x'*40+'\n')
        store.TOKEN_FILE.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError,'0600'):store._token()
        store.TOKEN_FILE.chmod(0o600); self.assertEqual(store._token(),'x'*40)

    def test_public_download_is_pinned_resumable_and_locally_receipted(self):
        calls=[]
        def runner(command,**kwargs):
            calls.append(command)
            target=Path(command[command.index('--output')+1])
            url=command[-1]
            row=next(x for x in store.public_manifest()['files'] if x['url']==url)
            target.write_bytes(b'x'*row['file_size'])
        tiny=tuple((local,remote,index+3) for index,(local,remote,_) in enumerate(store.PUBLIC_FILES))
        with patch.object(store,'PUBLIC_FILES',tiny), patch.object(store,'MIN_FREE_BYTES',1):
            result=store.download_public(runner=runner)
        manifest=json.loads(store.MANIFEST.read_text())
        self.assertEqual(result['source'],'doe_nersc_public_unrestricted_only_snapshot_2024-01-13')
        self.assertEqual(len(manifest['files']),3)
        self.assertTrue(all(len(x['sha256'])==64 for x in manifest['files']))
        self.assertTrue(all('--continue-at' in x for x in calls))
        self.assertNotIn('Authorization',json.dumps(calls))

    def test_planner_sees_imgvr_only_after_the_index_is_ready(self):
        with patch.object(store,'status',return_value={'ready':False}):
            self.assertNotIn('operation:protein_similarity',lab_genome_mining.campaign_instructions())
        with patch.object(store,'status',return_value={'ready':True}):
            menu=lab_genome_mining.campaign_instructions()
        self.assertIn('operation:protein_similarity',menu)
        self.assertIn('do not establish novelty or function',menu)


if __name__=='__main__':unittest.main()
