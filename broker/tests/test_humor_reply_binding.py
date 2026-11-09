#!/usr/bin/env python3
"""Exact prospective draft bindings; synthetic stores and forbidden senders."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import joke_fermentation as J
import build_merged_chat as M

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='humor-binding-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'humor-drafts.json'
        self.text='The synthetic moon filed a noise complaint.'
        self.rows=[dict(joke_id='fixture-joke',joke=self.text)]
        self.sender=Mock(side_effect=AssertionError('external send forbidden'))
        p=patch.object(socket.socket,'connect',self.sender);p.start();self.addCleanup(p.stop)
        self.addCleanup(self.sender.assert_not_called)
        self.assertIs(socket.socket.connect,self.sender);self.assertNotIn('.vintos',self.root.parts)

    def binding(self,text=None):
        self.path.write_text(json.dumps(dict(drafts=self.rows)))
        return J.reply_binding(self.text if text is None else text,'fixture-turn',str(self.root))

    def test_exact_content_only_no_copied_text_or_store_change(self):
        b=self.binding();before=self.path.read_bytes()
        self.assertEqual(b['joke_id'],'fixture-joke');self.assertEqual(b['joke_text_sha256'],J.hashlib.sha256(self.text.encode()).hexdigest())
        self.assertNotIn(self.text,json.dumps(b));self.assertEqual(b,J.reply_binding(self.text,'fixture-turn',str(self.root)))
        self.assertEqual(before,self.path.read_bytes())

    def test_prefix_rewrite_wrapper_and_offer_are_not_draft_identity(self):
        for text in (self.text[:20],self.text+'!',self.text.lower(),'I liked this: '+self.text,'[FERMENTED CALLBACK '+self.text+']'):
            self.assertEqual(self.binding(text),{})

    def test_ambiguous_text_or_reused_id_refuses(self):
        for extra in (dict(joke_id='other',joke=self.text),dict(joke_id='fixture-joke',joke='Other synthetic text')):
            self.rows.append(extra);self.assertEqual(self.binding(),{});self.rows.pop()

    def test_unknown_identity_and_oversize_input_refuse(self):
        for key in (None,'',[],7):
            self.rows[0]['joke_id']=key;self.assertEqual(self.binding(),{})
        self.path.write_bytes(b' '*1048577);self.assertEqual(J.reply_binding(self.text,'turn',str(self.root)),{})

    def test_canonical_overlap_retains_only_exact_same_turn_and_surface_binding(self):
        binding=self.binding();row=dict(vintos=self.text,turn_id='fixture-turn',surface='chat',
            timestamp='2020-01-01T00:00:00Z',**binding)
        canonical=dict(role='assistant',content=self.text,turn_id='fixture-turn',surface='chat',ts=1577836800)
        with patch.object(M,'load_json',return_value=[row]),patch.object(M,'load_jsonl',return_value=[canonical]):
            merged=M.build();self.assertEqual(len(merged),1);self.assertEqual(merged[0]['joke_binding'],binding['joke_binding'])
        for change in ({'vintos':self.text+'suffix'},{'surface':'other'},{'joke_text_sha256':'a'*64}):
            bad=dict(row,**change)
            with patch.object(M,'load_json',return_value=[bad]),patch.object(M,'load_jsonl',return_value=[canonical]):
                self.assertNotIn('joke_id',M.build()[0])
        with patch.object(M,'load_json',return_value=[row,dict(row,joke_id='conflict')]),patch.object(M,'load_jsonl',return_value=[canonical]):
            self.assertNotIn('joke_id',M.build()[0])

    def test_new_ledger_entry_hook_and_merge_retention(self):
        self.binding();entry=dict(vintos=self.text,turn_id='fixture-turn',other_field='retained')
        source=(ROOT/'scripts/interaction-ledger.py').read_text();tree=ast.parse(source)
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        hook=next(n for n in main.body if isinstance(n,ast.Try) and 'from joke_fermentation import reply_binding' in ast.get_source_segment(source,n))
        namespace=dict(entry=entry,MEMORY=str(self.root))
        exec(compile(ast.Module(body=[hook],type_ignores=[]),'ledger-hook','exec'),namespace)
        self.assertEqual(entry['joke_id'],'fixture-joke');self.assertEqual(entry['other_field'],'retained')
        merged=M.entry(entry,'assistant',entry['vintos'],'2020-01-01T00:00:00Z','ledger')
        for field in ('joke_id','joke_text_sha256','joke_binding'):self.assertEqual(merged[field],entry[field])
        self.assertEqual((ROOT/'bin/interaction_ledger.py').read_text(),source)
        old=dict(vintos=self.text);self.assertNotIn('joke_id',old)

if __name__=='__main__':unittest.main()
