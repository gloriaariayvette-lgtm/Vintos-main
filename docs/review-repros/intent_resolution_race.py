"""Synthetic reproduction: a slow HELD result must not erase a settled verdict."""
import copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"broker/tests"))
import threading
import unittest
from unittest.mock import patch
import test_intent_fields_fix as fixtures

class ResolutionRace(unittest.TestCase):
    def test_slow_held_result_does_not_erase_an_already_settled_row(self):
        case=fixtures.IntentFieldsFix(methodName='runTest')
        case.setUp(); self.addCleanup(case.doCleanups)
        case.delivered(gloria=copy.deepcopy(fixtures.GLORIA))
        started=threading.Event(); release=threading.Event(); errors=[]
        def judge(*args,**kwargs):
            if threading.current_thread().name=='slow-judge':
                started.set()
                if not release.wait(5): raise AssertionError('fixture release timed out')
                fixtures.E._held_why.set('judge_unavailable')
                return 'HELD'
            return 'YES'
        def resolve():
            try: fixtures.E.resolve_previous(fixtures.HER)
            except BaseException as exc: errors.append(exc)
        with patch.object(fixtures.E,'_judge_realized',side_effect=judge):
            worker=threading.Thread(target=resolve,name='slow-judge')
            worker.start()
            try:
                self.assertTrue(started.wait(5))
                fixtures.E.resolve_previous(fixtures.HER)
                settled=copy.deepcopy(case.rows()[-1]['realized'])
                self.assertEqual(settled,dict.fromkeys(('field','gloria','self'),'YES'))
            finally:
                release.set(); worker.join(5)
        self.assertFalse(worker.is_alive()); self.assertEqual(errors,[])
        self.assertEqual(case.rows()[-1]['realized'],settled)

    def test_conflicting_late_verdict_does_not_repeat_pressure_feedback(self):
        case=fixtures.IntentFieldsFix(methodName='runTest')
        case.setUp(); self.addCleanup(case.doCleanups)
        case.press(**{fixtures.A:case.prow(fixtures.TEXT_A,2.0)})
        case.delivered(gloria=copy.deepcopy(fixtures.GLORIA),addresses=fixtures.A)
        started=threading.Event(); release=threading.Event(); errors=[]
        def judge(*args,**kwargs):
            if threading.current_thread().name=='slow-judge':
                started.set()
                if not release.wait(5): raise AssertionError('fixture release timed out')
                return 'NO'
            return 'YES'
        def resolve():
            try: fixtures.E.resolve_previous(fixtures.HER)
            except BaseException as exc: errors.append(exc)
        with patch.object(fixtures.E,'_judge_realized',side_effect=judge):
            worker=threading.Thread(target=resolve,name='slow-judge')
            worker.start()
            try:
                self.assertTrue(started.wait(5))
                fixtures.E.resolve_previous(fixtures.HER)
                settled_pressure=copy.deepcopy(case.pressure(fixtures.A))
            finally:
                release.set(); worker.join(5)
        self.assertFalse(worker.is_alive()); self.assertEqual(errors,[])
        self.assertEqual(case.pressure(fixtures.A),settled_pressure)
        self.assertFalse((case.mem/'.intent-required-consideration.json').exists())

if __name__=='__main__': unittest.main()
