#!/usr/bin/env python3
"""One unownable stored row must not stop every pass (12 October: from 04:44 CDT the Lab re-raised "question hold
lacks a named retrieval route" out of _question_holds — which the orient phase and two tick paths all call — and
wrote 4.5 MB of identical faults without planning anything; the service read as waiting_for_compute while Gemma and
the shim were both answering).

A stored entry whose owner cannot be computed is quarantined rather than released or raised on: it keeps holding
its own question under the question-only key, and it no longer stops the Lab from doing anything else. A notebook
row with no nameable route is passed over, and every legitimate hold is still kept. Scratch workspace; the model and every source are stubs; sockets and processes are refused."""
from pathlib import Path
import json, os, socket, subprocess, sys, tempfile, unittest
scratch = tempfile.TemporaryDirectory(prefix='lab-hold-store-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name + '/workspace', VINTOS_SECRETS=scratch.name + '/secrets')
NET = []
def forbidden(*a, **k):
    NET.append(a); raise AssertionError('External operation forbidden')
socket.socket.connect = forbidden; socket.create_connection = forbidden; subprocess.Popen = forbidden
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import chemistry_lab as C
C._ask = forbidden; C.urllib.request.urlopen = forbidden

HELD = {'question': 'Does human Pendrin bind chloride at its STAS interface?', 'refused': 'repeat: spent subject',
        'evidence_status': 'insufficient', 'planning_evidence': 'abc123',
        'source_query': {'source': 'pdb', 'entry_id': '1ABC'}}
UNNAMED = dict(HELD, question='What are the PDB identifiers for human GSDMD?', source_query={'entry_id': '9ZZZ'})
UNIPROT_ONLY = {k: v for k, v in HELD.items() if k != 'source_query'}
UNIPROT_ONLY.update(question='What is the topology of human SLC26A11?',
                    uniprot_query='gene:SLC26A11 AND organism_id:9606')
NOTHING_NAMED = {k: v for k, v in HELD.items() if k != 'source_query'}
NOTHING_NAMED['question'] = 'What can be said about anion transport in general?'

class HoldStoreRecovery(unittest.TestCase):
    def setUp(self):
        os.makedirs(C.ROOT, exist_ok=True)
        self.path = Path(C.ROOT, 'question-holds.json')
        self.path.unlink(missing_ok=True)
        Path(str(self.path) + '.unreadable').unlink(missing_ok=True)
        open(C.NOTEBOOK, 'w').close(); open(C.FAULTS, 'w').close()

    def notebook(self, *inquiries):
        with open(C.NOTEBOOK, 'w') as stream:
            for inquiry in inquiries:
                stream.write(json.dumps({'kind': 'inquiry_refused', 'inquiry': inquiry}) + '\n')

    def test_the_store_is_scratch_and_nothing_reaches_the_world(self):
        self.assertTrue(C.ROOT.startswith(scratch.name), C.ROOT)
        self.assertIs(C._ask, forbidden); self.assertIs(socket.socket.connect, forbidden); self.assertEqual(NET, [])

    def test_an_unnamed_route_in_the_notebook_does_not_stop_the_pass(self):
        self.notebook(UNNAMED, HELD)
        kept = C._question_holds()
        self.assertEqual([h['question'] for h in kept], [HELD['question']])

    def test_an_unnamed_route_in_the_saved_file_is_quarantined_under_its_question(self):
        # Kept, not released: it still holds its own question. It simply cannot stop anything else any more.
        json.dump({C._hold_owner(HELD): HELD, 'v1-key': UNNAMED}, open(self.path, 'w'))
        kept = C._question_holds()
        self.assertEqual(sorted(h['question'] for h in kept),
                         sorted([HELD['question'], UNNAMED['question']]))
        question_key = ' '.join(UNNAMED['question'].casefold().split())
        self.assertEqual(sorted(json.load(open(self.path))), sorted([C._hold_owner(HELD), question_key]))
        self.assertEqual([row['stage'] for row in C._tail_jsonl(C.FAULTS)], ['question_holds_quarantined'])
        C._question_holds()      # rewritten under the question key, so the fault does not repeat every tick
        self.assertEqual([row['stage'] for row in C._tail_jsonl(C.FAULTS)], ['question_holds_quarantined'])

    def test_an_unreadable_file_is_kept_aside_and_the_pass_continues(self):
        self.path.write_text('{not json')
        self.notebook(HELD)
        self.assertEqual([h['question'] for h in C._question_holds()], [HELD['question']])
        self.assertTrue(Path(str(self.path) + '.unreadable').exists())
        self.assertIn('question_holds_unreadable', [row['stage'] for row in C._tail_jsonl(C.FAULTS)])

    def test_a_named_route_still_holds_and_is_still_owned_by_its_retrieval(self):
        self.notebook(HELD)
        self.assertEqual([h['question'] for h in C._question_holds()], [HELD['question']])
        other = dict(HELD, source_query={'source': 'interpro', 'accession': 'O43511'})
        self.assertNotEqual(C._hold_owner(other), C._hold_owner(HELD))   # a different route is its own slot

    def test_a_uniprot_only_hold_is_kept_as_before(self):
        self.notebook(UNIPROT_ONLY, HELD)
        self.assertEqual(sorted(h['question'] for h in C._question_holds()),
                         sorted([UNIPROT_ONLY['question'], HELD['question']]))

    def test_a_row_naming_no_retrieval_at_all_is_passed_over(self):
        # It has no lookup to be matched against, so it was never a hold; before this it raised instead.
        self.assertIsNone(C._hold_owner(NOTHING_NAMED, strict=False))
        self.notebook(NOTHING_NAMED, HELD)
        self.assertEqual([h['question'] for h in C._question_holds()], [HELD['question']])

    def test_strict_is_still_strict_for_callers_that_want_it(self):
        with self.assertRaises(ValueError):
            C._hold_owner(UNNAMED)
        self.assertIsNone(C._hold_owner(UNNAMED, strict=False))

    def test_many_unownable_rows_still_leave_the_holds_that_are_real(self):
        rows = [dict(UNNAMED, question='bad %d' % n) for n in range(5)] + [HELD]
        self.notebook(*rows)
        self.assertEqual([h['question'] for h in C._question_holds()], [HELD['question']])

if __name__ == '__main__':
    unittest.main()
