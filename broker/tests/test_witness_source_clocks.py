#!/usr/bin/env python3
"""Explicit source clocks through actual adapters, merger and forecast job; scratch only."""
import ast
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('source_clock_fixture',ROOT/'broker/tests/test_witness_self_forecast_inputs.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)


class Tests(unittest.TestCase):
    packets=F.Tests.packets
    base=1700000000.
    def setUp(self):
        F.Tests.setUp(self)
        self.raw=self.base+20
        self.source='chat'
        self.mutation=None
        tree=ast.parse((ROOT/'scripts/jepa_self_head.py').read_text())
        names={'_epoch','_iso','_from_chat','_from_ledger','_merge','_attach_forecast_clock','_not_us'}
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
        self.ns.update(_her=lambda x:x.get('content','') if isinstance(x,dict) else x,
                       his_words=lambda x:x or '', _norm=lambda x:x.strip().lower(),
                       SCRUBBED_SOURCES=('video-outreach',),_DESKTOP='synthetic desktop marker',DUP_WINDOW=900)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-source-adapters','exec'),self.ns)

    def chat(self,raw):
        return self.ns['_from_chat']([
            dict(role='user',content='synthetic previous prompt',timestamp=self.base+10),
            dict(role='assistant',content='synthetic source reply',timestamp=raw,turn_id='source-fixture')], '', 'canonical')

    def ledger(self,raw):
        return self.ns['_from_ledger']([dict(timestamp=raw,gloria='synthetic previous prompt',
                         vintos='synthetic source reply',turn_id='source-fixture')], '', 'ledger')

    def forecast(self,enc,**kw):
        if self.source=='chat': self.exs=self.chat(self.raw)
        elif self.source=='ledger': self.exs=self.ledger(self.raw)
        else:
            self.exs,self.stats=self.ns['_merge']([('ledger',self.ledger(self.ledger_raw)),
                                                  ('canonical',self.chat(self.raw))])
        if self.mutation: self.mutation(self.exs)
        return F.Tests.forecast(self,enc,**kw)

    def job(self):
        self.pending.write_text(json.dumps(dict(her='synthetic arrival',arrived_at=self.base+200,
                                               surface='fixture-chat',turn_id='fixture-target')))
        return self.ns['on_message_job'](str(self.pending),enc=self.enc,now=self.base+210)

    def clocks(self):
        paths=list(self.root.glob('self-forecast-clock-*.json'))
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in paths))
        return [json.loads(p.read_text()) for p in paths]

    def aware(self,at): return datetime.fromtimestamp(at,timezone.utc).isoformat()

    def test_numeric_chat_clock_survives_legacy_naive_format_without_changing_row(self):
        row=self.job(); clock,=self.clocks()
        self.assertIsNone(datetime.fromisoformat(row['self']['context_last_ts']).tzinfo)
        self.assertEqual(clock['context_clock']['epoch'],self.raw)
        self.assertEqual(clock['context_clock']['raw_kind'],'numeric_epoch')
        self.assertEqual(clock['forecast_row_sha256'],F.W._fingerprint(row))
        self.assertEqual(clock['context_clock']['rendered_clock_sha256'],F.digest(row['self']['context_last_ts']))
        self.assertEqual(clock['source_identity'],'unverified')
        self.assertEqual(clock['boundary'],'forecast_log_close')
        self.assertEqual(clock['context_clock']['meaning'],'source_exchange_time_not_reply_finalization')
        self.assertEqual(row,json.loads(self.output.read_text()))
        self.assertNotIn('synthetic source reply',json.dumps(clock))
        self.assertNotIn('source-fixture',json.dumps(clock))
        self.assertEqual(self.packets()[0]['schema'],'self-forecast-inputs-v1')

    def test_explicit_offset_in_chat_and_ledger_is_retained(self):
        self.raw=self.aware(self.raw)
        for source in ('chat','ledger'):
            self.source=source
            self.assertIsNotNone(self.job())
        self.assertEqual(len(self.clocks()),2)
        self.assertTrue(all(c['context_clock']['raw_kind']=='offset_iso' for c in self.clocks()))

    def test_naive_source_never_inherits_host_timezone(self):
        self.raw=self.ns['_iso'](self.raw)
        self.assertIsNotNone(self.job())
        self.assertEqual(self.clocks(),[])
        self.assertEqual(self.packets()[0]['state'],'observed')

    def test_off_on_and_unscoped_source_reads_preserve_legacy_values(self):
        self.assertNotIn('_witness_clock',self.chat(self.raw)[0])
        with patch.dict(os.environ,JUDGES_CAPTURE_SCRATCH=''):
            off=self.job(); off_exs=copy.deepcopy(self.exs)
        on=self.job(); on_exs=copy.deepcopy(self.exs)
        on_exs[0].pop('_witness_clock')
        self.assertEqual(off_exs,on_exs)
        self.assertEqual(off,on)
        self.assertEqual(self.enc.encode.call_count,2)
        self.assertEqual(len(self.clocks()),1)

    def test_merge_clock_follows_earlier_source_while_text_priority_stays(self):
        self.source='merge';self.ledger_raw=self.aware(self.base+30)
        self.job(); clock,=self.clocks()
        self.assertEqual(self.exs[0]['origin'],'ledger')
        self.assertEqual(self.exs[0]['at'],self.base+20)
        self.assertEqual(clock['context_clock']['raw_kind'],'numeric_epoch')
        self.assertEqual(self.stats['canonical']['duplicate'],1)

    def test_earlier_unknown_clock_clears_later_known_clock(self):
        self.source='merge';self.ledger_raw=self.aware(self.base+30)
        self.raw=self.ns['_iso'](self.base+20)
        self.assertIsNotNone(self.job())
        self.assertNotIn('_witness_clock',self.exs[0])
        self.assertEqual(self.clocks(),[])

    def test_later_known_clock_never_backfills_earlier_unknown_clock(self):
        self.source='merge';self.ledger_raw=self.ns['_iso'](self.base+15)
        self.assertIsNotNone(self.job())
        self.assertEqual(self.exs[0]['at'],self.base+15)
        self.assertEqual(self.clocks(),[])

    def test_equal_time_preserves_original_selected_source_clock(self):
        self.source='merge';self.ledger_raw=self.aware(self.base+20)
        self.raw=self.ns['_iso'](self.base+20)
        self.job(); clock,=self.clocks()
        self.assertEqual(clock['context_clock']['raw_kind'],'offset_iso')

    def test_bad_clock_metadata_cannot_destroy_the_existing_input_receipt(self):
        for field,value in [('epoch',self.base+21),('rendered_clock_sha256','0'*64),('raw_clock_sha256','bad'),
                            ('meaning','finalization'),('epoch',True)]:
            self.mutation=lambda exs,k=field,v=value:exs[0]['_witness_clock'].__setitem__(k,v)
            self.assertIsNotNone(self.job())
        self.assertEqual(self.clocks(),[])
        self.assertTrue(all(p['state']=='observed' for p in self.packets()))

    def test_clock_observer_failure_preserves_forecast_and_original_receipt(self):
        with patch.object(F.W,'self_exchange_clock',side_effect=ValueError('private clock failure')):
            self.assertIsNotNone(self.job())
        self.assertEqual(self.clocks(),[])
        self.assertEqual(self.packets()[0]['state'],'observed')

    def test_clock_sink_failure_preserves_log_and_already_published_inputs(self):
        original=F.W._publish_private
        def publish(root,packet,prefix):
            if prefix=='self-forecast-clock-': raise OSError('private sink failure')
            return original(root,packet,prefix)
        with patch.object(F.W,'_publish_private',side_effect=publish):
            row=self.job()
        self.assertEqual(row,json.loads(self.output.read_text()))
        self.assertEqual(self.clocks(),[])
        self.assertEqual(self.packets()[0]['state'],'observed')

    def test_unscoped_and_mismatched_raw_clock_produce_no_evidence(self):
        self.assertIsNone(F.W.self_exchange_clock(self.raw,self.raw,self.aware(self.raw)))
        token=F.W.begin_self_forecast()
        try:
            for raw,parsed in ((self.raw,self.raw+1),(True,1),('1700000020',self.raw),(float('inf'),float('inf'))):
                self.assertIsNone(F.W.self_exchange_clock(raw,parsed,'synthetic clock'))
        finally:F.W.end_self_forecast(token)


if __name__=='__main__': unittest.main()
