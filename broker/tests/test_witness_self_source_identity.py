#!/usr/bin/env python3
"""Source metadata stays with selected text through actual adapters and merger."""
import ast
import copy
import json
import os
from pathlib import Path
import re
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import witness_capture as W
import witness_self_artifacts as A
import jepa_ranking_audit as RA
from witness_receipts import digest
from test_witness_source_clocks import Tests as Clocks


class Tests(unittest.TestCase):
    def setUp(self):
        self.case=Clocks('test_explicit_offset_in_chat_and_ledger_is_retained')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.ns=self.case.ns
        tree=ast.parse((ROOT/'scripts/jepa_self_head.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='his_words')
        self.ns['_DEVICE_LINE']=re.compile(r'^(?:ridge|tenera|ferri):',re.I)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-his-words','exec'),self.ns)
        self.root=self.case.root
        self.assertNotIn('.vintos',self.root.parts)
        self.assertTrue(hasattr(self.case.sender,'assert_not_called'))
        self.assertEqual(Path(os.environ['SPARK_WORKSPACE']),self.root)

    def row(self,**kw):
        return dict(dict(timestamp=self.case.aware(self.case.base+30),gloria='synthetic prompt',
                         vintos='  synthetic reply\n\nridge: synthetic mark  ',turn_id='synthetic-high',
                         surface='synthetic-chat'),**kw)

    def ledger(self,row):return self.ns['_from_ledger']([row],'','ledger')
    def chat(self,row):
        return self.ns['_from_chat']([dict(role='user',content='synthetic prompt',ts=self.case.base+10),row],'','canonical')

    def test_unscoped_and_disabled_reads_have_no_added_metadata(self):
        original=self.ledger(self.row())
        self.assertNotIn('_witness_reply_source',original[0])
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH='',JUDGES_CAPTURE_CONFIG=''):
            with A.audit_source_scope() as root:
                self.assertIsNone(root)
                self.assertEqual(self.ledger(self.row()),original)

    def test_actual_ledger_cleanup_retains_original_and_normalized_hashes(self):
        raw=self.row()
        with A.audit_source_scope(): ex,=self.ledger(raw)
        ref=ex['_witness_reply_source']
        self.assertEqual(ex['his'],'synthetic reply')
        self.assertEqual(ref['source_reply_sha256'],digest(raw['vintos']))
        self.assertEqual(ref['normalized_reply_sha256'],digest(ex['his']))
        self.assertNotEqual(ref['source_reply_sha256'],ref['normalized_reply_sha256'])
        self.assertEqual(ref['source_row_sha256'],W._fingerprint(raw))
        self.assertEqual(ref['observed_turn_id'],'synthetic-high')
        self.assertNotIn(raw['vintos'],json.dumps(ref))

    def test_chat_reference_binds_assistant_not_preceding_user(self):
        row=dict(role='assistant',content=' synthetic reply ',ts=self.case.base+20,
                 turn_id='synthetic-assistant',surface='synthetic-avatar')
        with A.audit_source_scope(): ex,=self.chat(row)
        self.assertEqual(ex['_witness_reply_source']['source_row_sha256'],W._fingerprint(row))
        self.assertEqual(ex['_witness_reply_source']['source_field'],'content')
        self.assertEqual(ex['_witness_reply_source']['observed_surface'],'synthetic-avatar')

    def test_preferred_text_and_id_do_not_follow_earlier_duplicate_clock(self):
        high=self.row()
        low=dict(role='assistant',content='synthetic reply',ts=self.case.base+20,
                 turn_id='synthetic-low',surface='synthetic-other')
        with A.audit_source_scope():
            merged,stats=self.ns['_merge']([('ledger',self.ledger(high)),('canonical',self.chat(low))])
        ex,=merged
        self.assertEqual(stats['canonical']['duplicate'],1)
        self.assertEqual(ex['at'],low['ts'])
        self.assertEqual(ex['turn_id'],high['turn_id'])
        self.assertEqual(ex['_witness_reply_source']['source_row_sha256'],W._fingerprint(high))
        self.assertEqual(ex['_witness_reply_source']['observed_surface'],high['surface'])

    def test_missing_preferred_id_is_not_backfilled_from_duplicate(self):
        high=self.row(turn_id='')
        low=dict(role='assistant',content='synthetic reply',ts=self.case.base+20,turn_id='synthetic-low')
        with A.audit_source_scope():
            merged,_=self.ns['_merge']([('ledger',self.ledger(high)),('canonical',self.chat(low))])
        row,=A.ledger_rows(merged,retain=True)
        self.assertIsNone(row['turn_id'])
        self.assertIsNone(row['_witness_reply_source']['observed_turn_id'])

    def test_legacy_stringification_never_upgrades_non_string_original_id(self):
        with A.audit_source_scope(): ex,=self.ledger(self.row(turn_id=42))
        self.assertEqual(ex['turn_id'],'42')
        row,=A.ledger_rows([ex],retain=True)
        self.assertIsNone(row['turn_id'])
        self.assertIsNone(row['_witness_reply_source']['observed_turn_id'])

    def test_mismatched_normalized_text_or_identity_drops_observation_only(self):
        with A.audit_source_scope(): ex,=self.ledger(self.row())
        for key,value in [('his','changed text'),('turn_id','changed-id')]:
            changed=dict(ex,**{key:value})
            row,=A.ledger_rows([changed],retain=True)
            self.assertNotIn('_witness_reply_source',row)
            self.assertEqual(row['vintos'],changed['his'])

    def test_malformed_source_metadata_never_passes_through(self):
        with A.audit_source_scope(): ex,=self.ledger(self.row())
        for key,value in [('schema','wrong'),('source_reply_sha256','bad'),('source_identity','verified'),
                          ('observed_surface',True),('extra','not permitted')]:
            changed=copy.deepcopy(ex);changed['_witness_reply_source'][key]=value
            self.assertEqual(A.ledger_rows([changed],retain=True),A.ledger_rows([changed]))

    def test_actual_realized_adapter_keeps_old_values_and_scoped_source_metadata(self):
        sh=types.SimpleNamespace(exchanges=lambda:self.ledger(self.row()))
        with patch.dict(sys.modules,jepa_self_head=sh):
            with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH='',JUDGES_CAPTURE_CONFIG=''):
                off=RA.realized_ledger()
            on=RA.realized_ledger()
        self.assertEqual([{k:r[k] for k in ('timestamp','gloria','vintos')} for r in on],off)
        self.assertEqual(on[0]['turn_id'],'synthetic-high')
        self.assertIsNone(A._source_scope.get())
        # The existing ranking transform sees precisely the same streams.
        self.assertEqual(RA._turns(on),RA._turns(off))

    def test_source_failure_and_bad_sink_preserve_existing_adapter_output(self):
        with A.audit_source_scope():
            with patch.object(A,'reply_source',side_effect=ValueError('synthetic failure')):
                ex,=self.ledger(self.row())
        self.assertNotIn('_witness_reply_source',ex)
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH=str(self.root/'missing')):
            with A.audit_source_scope() as root:
                self.assertIsNone(root)
                self.assertEqual(self.ledger(self.row()),[ex])

    def test_scopes_restore_on_exception_and_nested_reads(self):
        self.assertIsNone(A._source_scope.get())
        with self.assertRaises(RuntimeError):
            with A.audit_source_scope() as root:
                with A.audit_source_scope():self.assertEqual(A._source_scope.get(),root)
                self.assertEqual(A._source_scope.get(),root)
                raise RuntimeError('synthetic source failure')
        self.assertIsNone(A._source_scope.get())

    def test_saved_audit_vector_contains_exact_selected_source_observation(self):
        with A.audit_source_scope(): exs=self.ledger(self.row())
        ledger=A.ledger_rows(exs,retain=True)
        manifest={'schema':'synthetic-checkpoint'}
        wrapped=A.audit_encoder(self.case.enc,ledger,manifest)
        wrapped.encode(['synthetic reply'])
        files=list(self.root.glob('self-audit-embedding-*.json'));self.assertEqual(len(files),1)
        self.assertEqual(files[0].stat().st_mode&0o777,0o600)
        ref=json.loads(files[0].read_text())['source_refs'][0]
        self.assertEqual(ref['observed_turn_id'],'synthetic-high')
        self.assertEqual(ref['reply_source'],exs[0]['_witness_reply_source'])
        self.assertNotIn('synthetic reply',files[0].read_text())

    def test_oversized_or_non_text_source_cannot_fabricate_observation(self):
        for row in (self.row(vintos=42),self.row(vintos='x'*65537),self.row(extra='x'*262145)):
            with A.audit_source_scope(): ex,=self.ledger(row)
            self.assertNotIn('_witness_reply_source',ex)
            self.assertTrue(ex['his'])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    sys.exit(not result.wasSuccessful())
