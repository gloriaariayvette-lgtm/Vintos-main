#!/usr/bin/env python3
"""Run affected synthetic suites with coarsened artifact mtimes; no live IO."""
import io
import math
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch


class Tests(unittest.TestCase):
    def test_followthrough_and_completion_under_coarse_artifact_clock(self):
        import test_want_agent_followthrough as followthrough
        import test_want_completion_binding as completion
        original = Path.stat
        observed = []

        def coarse(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if ('want-artifacts' in path.parts and 'requests' in path.parts
                    and path.suffix == '.txt' and stat.S_ISREG(result.st_mode)):
                # Both nested suites assert their paths and senders are scratch.
                self.assertTrue(any(part.startswith(('want-agent-test-', 'want-ending-test-'))
                                    for part in path.parts))
                values = list(result)
                values[8] = min(result.st_mtime, math.floor(result.st_mtime * 100) / 100)
                observed.append(result.st_mtime - values[8])
                return os.stat_result(values)
            return result

        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(module.Tests)
                                   for module in (followthrough, completion))
        output = io.StringIO()
        with patch.object(Path, 'stat', coarse):
            result = unittest.TextTestRunner(stream=output).run(suite)
        self.assertTrue(result.wasSuccessful(), output.getvalue())
        self.assertGreater(result.testsRun, 60)
        self.assertTrue(any(lag > 0 for lag in observed))
        self.assertTrue(all(0 <= lag < .011 for lag in observed))
        print('Coarse 10 ms artifact clock: %d nested checks passed' % result.testsRun)


if __name__ == '__main__':
    unittest.main()
