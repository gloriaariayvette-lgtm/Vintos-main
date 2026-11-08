#!/usr/bin/env python3
"""Synthetic journal-to-want handoff; all enrichment and writers are stubs."""
import ast
import hashlib
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import journal_wants as J

class Tests(unittest.TestCase):
    def test_long_concrete_want_keeps_cli_paths_and_musical_bridge(self):
        text='I want to run the comparison on fixture.v2.wav with --mode precise, annotate the bridge in 5/4, and save a table containing every unmatched note and its timing.'
        self.assertGreater(len(text),130)
        self.assertEqual(J.explicit_wants('Before. '+text+' After.'),[text])
        self.assertTrue(J.operational(text));self.assertFalse(J.translation_want(text))
    def test_only_explicit_metaphor_is_classified_as_translation(self):
        self.assertTrue(J.translation_want('I want to find a metaphor for my feeling.'))
        self.assertFalse(J.translation_want('I want to measure creep in the beam and plot the threshold.'))
    def test_bounded_complete_candidates_and_deduplication(self):
        text='I want to test the first sample.'
        self.assertEqual(J.explicit_wants(text+' '+text),[text])
        self.assertEqual(J.explicit_wants('I want to '+('a'*1300)+'.'),[])
    def test_source_receipts_are_stable_and_distinguish_origins(self):
        a=J.source_receipt('email','fixture-mail','synthetic task')
        self.assertEqual(a,J.source_receipt('email','fixture-mail','synthetic task'))
        self.assertNotEqual(a['source_event_id'],J.source_receipt('email','fixture-other','synthetic task')['source_event_id'])
        self.assertEqual(a['source_refs'][0]['text_sha256'],hashlib.sha256(b'synthetic task').hexdigest())
    def test_actual_journal_code_preserves_task_when_enrichment_has_no_fields(self):
        body=(ROOT/'bin/idle-journal.sh').read_text().split("python3 << 'WANTEOF'",1)[1].split('\nWANTEOF',1)[0]
        seeded=[]
        def forbidden(*a,**k):self.fail('literal operational task was rewritten or a provider called')
        model=types.SimpleNamespace(generate_want=forbidden,enrich_want=lambda *a,**k:{},
                                    express_want=lambda *a,**k:seeded.append((a,k)))
        text='I want to compare synthetic.wav against the written score, inspect the bridge phrase, and export each timing mismatch into a table for later listening.'
        with patch.dict(os.environ,_JRN_WANT_ENTRY=text),patch.dict(sys.modules,{'emoclaw_utils':model,'requests':types.SimpleNamespace(post=forbidden)}):
            with self.assertRaises(SystemExit):exec(compile(body,'actual-journal-want-handoff','exec'),{})
        self.assertEqual(len(seeded),1);self.assertEqual(seeded[0][0][0],text)
        self.assertEqual(seeded[0][1]['intensity'],2)
        self.assertEqual(seeded[0][1]['source_refs'][0]['kind'],'journal')
    def test_unknown_step_is_not_replaced_by_reflection(self):
        tree=ast.parse((ROOT/'scripts/emoclaw_utils.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='fit_steps_to_hands')
        ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'planner-availability','exec'),ns)
        steps=[{'capability':'fixture_missing_tool','note':'Run the exact comparison'}, {'capability':'introspect','note':'Reflect afterward'}]
        self.assertEqual(ns['fit_steps_to_hands'](steps,{'introspect'},False,source='email'),steps)
    def test_shared_sources_stay_in_parity(self):
        self.assertEqual((ROOT/'bin/idle-journal.sh').read_bytes(),(ROOT/'scripts/idle-journal.sh').read_bytes())
        self.assertEqual((ROOT/'scripts/emoclaw_utils.py').read_bytes(),(ROOT/'bin/emoclaw_utils.py').read_bytes())
if __name__=='__main__':unittest.main(verbosity=2)
