"""Pure source selection: no stores, senders, or models are invoked."""
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone
from copy import deepcopy
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from forge_want_context import select

class ContextTests(unittest.TestCase):
    def test_offer_is_not_adoption_and_repeats_are_excluded(self):
        rows = [{'key':'lab:a','source':'lab','text':'Recorded observation','state':'standing'}]
        before = deepcopy(rows)
        now = datetime(2026,9,20,tzinfo=timezone.utc)
        self.assertEqual(select(rows, [], now)['source_event_id'], 'spark:lab:a')
        self.assertEqual(rows, before)
        self.assertIsNone(select(rows, [{'source_event_id':'spark:lab:a'}], now))
    def test_daily_bound_and_empty_pool(self):
        now = datetime(2026,9,20,tzinfo=timezone.utc)
        wants = [{'source_event_id':'spark:'+str(i),'timestamp':now.isoformat()} for i in range(2)]
        self.assertIsNone(select([{'key':'x','source':'lab','text':'x','state':'standing'}], wants, now))
        self.assertIsNone(select([], [], now))
    def test_rotation_is_across_sources_before_rows(self):
        rows = [
            {'key':'lab:new','source':'lab','text':'new lab row','state':'standing','seen':'2026-09-20'},
            {'key':'lab:old','source':'lab','text':'old lab row','state':'standing','seen':'2026-09-10'},
            {'key':'gap:old','source':'absence_map','text':'missing body channel','state':'standing','seen':'2026-09-01'},
        ]
        hour0=datetime(1970,1,1,tzinfo=timezone.utc)
        hour1=datetime(1970,1,1,1,tzinfo=timezone.utc)
        self.assertEqual(select(rows,[],hour0)['source'],'absence_map')
        selected=select(rows,[],hour1)
        self.assertEqual((selected['source'],selected['source_event_id']),('lab','spark:lab:old'))

if __name__ == '__main__': unittest.main()
