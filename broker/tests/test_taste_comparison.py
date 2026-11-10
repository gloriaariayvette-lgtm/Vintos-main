"""Synthetic-only offline comparison; no live inputs, providers or encoders."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'experiments/nonllm-judges/taste_comparison.py'
spec = importlib.util.spec_from_file_location('taste_comparison_test', SCRIPT)
T = importlib.util.module_from_spec(spec); spec.loader.exec_module(T)


def row(n, text='quiet contrast', rating='landed', **extra):
    return dict(id='synthetic-rating-'+str(n), ref='synthetic-item-'+str(n), surface='message',
        at='2026-01-02T00:00:00Z', rating=rating, why='synthetic private explanation',
        piece={'type':'message','text':text}, made={'message':text}, **extra)


class Tests(unittest.TestCase):
    def setUp(self):
        self.profile={'likes':['quiet contrast'],'dislikes':['empty ornament'],'principles':['clear form']}
        self.cutoff='2026-01-10T00:00:00Z'

    def compare(self, rows):
        with patch('builtins.open',side_effect=AssertionError('I/O forbidden')), \
             patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
            return T.compare(self.profile,rows,self.cutoff)

    def test_fixed_aggregate_crosstab_and_explicit_proxy_denominator(self):
        result=self.compare([row(1),row(2,'empty ornament','missed'),row(3,'quiet contrast','missed'),
                             row(4,'quiet contrast','partly'),row(5,'quiet contrast empty ornament'),row(6,'other')])
        self.assertEqual(result['counts']['compared_items'],6)
        self.assertEqual(result['counts']['decisive_proxy_items'],3)
        self.assertEqual(result['counts']['literal_proxy_agreements'],2)
        self.assertAlmostEqual(result['agreement_rates']['literal_polarity_proxy'],2/3)
        self.assertEqual(result['literal_overlap_by_rating']['both']['landed'],1)
        self.assertFalse(result['semantic_agreement_measured'])
        for key in ('anchors_emitted','labels_emitted','training_signals_emitted','policy_inputs_emitted'):
            self.assertEqual(result[key],0)

    def test_empty_and_unmatched_are_not_disagreement(self):
        for rows in ([],[row(1,'other')],[row(1,rating='partly')]):
            self.assertIsNone(self.compare(rows)['agreement_rates']['literal_polarity_proxy'])

    def test_whole_phrase_boundaries_case_punctuation_unicode_and_duplicates(self):
        self.profile['likes']=['QUIET contrast','quiet contrast','café light']
        result=self.compare([row(1,'Quiet, contrast!'),row(2,'unquiet contrast'),row(3,'cafe\u0301 light')])
        self.assertEqual(result['counts']['like_only'],2)
        self.assertEqual(result['profile_counts']['likes_duplicates'],1)

    def test_no_keywords_negation_inference_or_paraphrase_inference(self):
        result=self.compare([row(1,'quiet'),row(2,'subtle opposition'),row(3,'not quiet contrast')])
        self.assertEqual(result['counts']['like_only'],1)  # Literal presence, including negated mentions.
        self.assertFalse(result['semantic_agreement_measured'])

    def test_principles_and_both_polarities_do_not_become_labels(self):
        self.profile['dislikes'].append('quiet contrast')
        result=self.compare([row(1,'quiet contrast clear form')])
        self.assertEqual(result['counts']['both'],1)
        self.assertEqual(result['counts']['principle_match'],1)
        self.assertEqual(result['counts']['decisive_proxy_items'],0)

    def test_latest_rating_replaces_prior_and_duplicates_do_not_weight(self):
        one=row(1); later=copy.deepcopy(one);later.update(id='later',at='2026-01-03T00:00:00Z',rating='missed')
        result=self.compare([one,one,later])
        self.assertEqual(result['counts']['compared_items'],1)
        self.assertEqual(result['counts']['duplicate_records'],1)
        self.assertEqual(result['agreement_rates']['literal_polarity_proxy'],0.)

    def test_future_rating_does_not_replace_prior(self):
        one=row(1); later=dict(one,id='future',at=self.cutoff,rating='missed')
        self.assertEqual(self.compare([one,later])['agreement_rates']['literal_polarity_proxy'],1.)

    def test_unknown_backward_and_tied_clocks_poison_item(self):
        for at in ('unknown','2026-01-01T00:00:00Z','2026-01-02T00:00:00Z'):
            one=row(1); later=dict(one,id='later',at=at)
            self.assertEqual(self.compare([one,later])['counts']['compared_items'],0)
        naive=row(1); naive['at']='2026-01-02T00:00:00'
        self.assertEqual(self.compare([naive])['counts']['unknown_time'],1)
        self.assertEqual(T.compare(self.profile,[naive],self.cutoff,'America/Chicago')['counts']['compared_items'],1)

    def test_conflicting_ids_and_bad_profile_refuse(self):
        one=row(1)
        with self.assertRaises(ValueError): self.compare([one,dict(one,rating='missed')])
        for profile in ({'vector':[]},{'likes':'bad'},{'likes':['!!!']},{'likes':[True]},{'likes':['x']*501}):
            with self.assertRaises(ValueError): T.compare(profile,[],self.cutoff)

    def test_explanations_context_titles_and_unknown_keys_cannot_match(self):
        one=row(1,'other');one.update(why='quiet contrast',before='quiet contrast',lead_up=['quiet contrast'])
        one['made']['unknown']='quiet contrast'
        song=row(2);song.update(surface='song',piece={'type':'song','title':'quiet contrast'},made={'title':'quiet contrast','style':'other'})
        self.assertEqual(self.compare([one,song])['counts']['like_only'],0)

    def test_media_descriptions_supported_without_claiming_media_contents(self):
        records=[]
        for n,(surface,key) in enumerate((('image','seen'),('video','prompt'),('song','style'))):
            one=row(n);one.update(surface=surface,piece={'type':surface},made={key:'quiet contrast'})
            records.append(one)
        result=self.compare(records)
        self.assertEqual(result['counts']['media_description_items'],3)
        self.assertEqual(result['counts']['like_only'],3)
        records[0]['made']={'prompt':'quiet','seen':'contrast'}
        self.assertEqual(self.compare(records)['counts']['like_only'],2)

    def test_invalid_frozen_text_and_unsupported_surfaces_are_not_evidence(self):
        a=row(1);a['made']['message']='different'
        b=row(2);b['surface']='unknown'
        c=row(3);c['why']=''
        result=self.compare([a,b,c])
        self.assertEqual(result['counts']['unsupported_piece'],2)
        self.assertEqual(result['counts']['invalid_rating'],1)

    def test_output_no_private_strings_ids_hashes_or_dynamic_keys_and_no_mutation(self):
        self.profile['SYNTHETIC_SECRET_KEY']={'private':'SYNTHETIC_SECRET'}
        rows=[row('SYNTHETIC_ID')];before=copy.deepcopy((self.profile,rows))
        result=self.compare(rows);encoded=json.dumps(result)
        for value in ('quiet contrast','empty ornament','synthetic-item','SYNTHETIC','explanation'):
            self.assertNotIn(value,encoded)
        self.assertEqual(before,(self.profile,rows))
        self.assertEqual(result['profile_counts']['unsupported_profile_fields'],1)

    def cli(self, root):
        return subprocess.run([sys.executable,str(SCRIPT),'--scratch',str(root),'--profile',str(root/'profile.json'),
            '--landings',str(root/'ratings.jsonl'),'--cutoff',self.cutoff],capture_output=True,text=True,timeout=15)

    def files(self, root):
        root.chmod(0o700)
        (root/'profile.json').write_text(json.dumps(self.profile))
        (root/'ratings.jsonl').write_text(json.dumps(row(1))+'\n')
        for p in root.iterdir(): p.chmod(0o600)

    def test_cli_only_reads_explicit_private_snapshots(self):
        with tempfile.TemporaryDirectory(prefix='taste-comparison-') as d:
            root=Path(d);self.files(root)
            before={p.name:p.read_bytes() for p in root.iterdir()}
            result=self.cli(root)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['counts']['compared_items'],1)
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})
            self.assertNotIn(str(root),result.stdout+result.stderr)

    def test_cli_refuses_unsafe_files_and_sanitizes_errors(self):
        with tempfile.TemporaryDirectory(prefix='taste-comparison-') as d:
            root=Path(d);self.files(root)
            for raw in ('{"likes":[],"likes":[]}', '{"likes":[NaN]}', '{private', ' '*(4*1024*1024+1)):
                (root/'profile.json').write_text(raw)
                result=self.cli(root)
                self.assertEqual((result.returncode,result.stdout,result.stderr),(1,'','taste_comparison_refused\n'))
            self.files(root);(root/'profile.json').chmod(0o644)
            self.assertEqual(self.cli(root).returncode,1)
            (root/'profile.json').unlink();(root/'profile.json').symlink_to(root/'ratings.jsonl')
            self.assertEqual(self.cli(root).returncode,1)


if __name__=='__main__': unittest.main()
