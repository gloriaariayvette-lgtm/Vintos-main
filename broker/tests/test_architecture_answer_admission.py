#!/usr/bin/env python3
"""Answers survive candidate rendering and are consumed only by actual admission."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
TEMP = tempfile.TemporaryDirectory(prefix='architecture-admission-')
SCRATCH = Path(TEMP.name)
os.environ['HOME'] = str(SCRATCH)
os.environ['SPARK_WORKSPACE'] = str(SCRATCH/'workspace')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
import architecture_answers as A
from context_selection import readonly
import turn_record as T

SEND = Mock(side_effect=AssertionError('external action forbidden'))


class Admission(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Path(A.STORE).is_relative_to(SCRATCH))
        self.assertTrue(Path(T.RECORD).is_relative_to(SCRATCH))
        Path(A.STORE).parent.mkdir(parents=True, exist_ok=True)
        self.entry = {'id':'A-fixture', 'question':'Which fixture owns this input?',
                      'asked_at':time.time()-86400, 'answer':'The measured fixture.', 'delivered':False}
        self.save(self.entry)
        self.net = patch.object(socket.socket, 'connect', SEND)
        self.net.start()

    def tearDown(self):
        self.net.stop()
        SEND.assert_not_called()

    def save(self, entry):
        Path(A.STORE).write_text(json.dumps([entry]))

    def read(self):
        return json.loads(Path(A.STORE).read_text())[0]

    def record(self, text, selection='selection-fixture'):
        current = {'selection_id':selection,'offers':{'architecture_answers':{'state':'offered'}}}
        with patch.dict(sys.modules, {'inner_context':types.SimpleNamespace(current_selection=lambda:current)}):
            return T.record('test', text)

    def test_answer_renders_readonly_then_is_consumed_once_when_admitted(self):
        before = Path(A.STORE).read_bytes()
        with readonly():
            text = A.block()
            self.assertEqual(A.block(), text)
        self.assertIn(self.entry['answer'], text)
        self.assertEqual(Path(A.STORE).read_bytes(), before)
        self.record(text)
        after = self.read()
        self.assertTrue(after['delivered'])
        self.assertEqual(after['admitted_turn'], 'selection-fixture')
        self.record(text)
        self.assertEqual(self.read(), after)
        with readonly():
            self.assertEqual(A.block(), '')

    def test_unadmitted_or_truncated_answer_stays_available(self):
        with readonly():
            text = A.block()
        self.record('An unrelated prompt', 'unrelated')
        self.assertFalse(self.read()['delivered'])
        self.record(text[:45], 'truncated')
        self.assertFalse(self.read()['delivered'])

    def test_standing_question_is_throttled_only_after_admission(self):
        self.entry.pop('answer')
        self.save(self.entry)
        with readonly():
            text = A.block()
        self.assertIn('YOU ASKED HER THIS', text)
        self.assertNotIn('standing_shown_at', self.read())
        self.record(text)
        self.assertGreater(self.read()['standing_shown_at'], 0)
        with readonly():
            self.assertEqual(A.block(), '')

    def test_answer_changed_since_selection_is_not_marked_delivered(self):
        with readonly():
            text = A.block()
        self.entry['answer'] = 'A new answer not present in that prompt.'
        self.save(self.entry)
        self.record(text)
        self.assertFalse(self.read()['delivered'])

    def test_shared_chat_and_avatar_context_carries_the_answer_to_admission(self):
        import inner_context as inner
        self.assertEqual(inner._MISSING.count(('architecture_answers', 'block')), 1)
        with patch.object(inner, '_MISSING', [('architecture_answers', 'block')]):
            prompt = inner.missing_inner_block()
        selection = inner.current_selection()
        self.assertEqual(selection['offers']['architecture_answers']['state'], 'offered')
        self.assertIn(self.entry['answer'], prompt)
        self.assertFalse(self.read()['delivered'])
        T.record('avatar', prompt)
        self.assertEqual(self.read()['admitted_turn'], selection['selection_id'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
