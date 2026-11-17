"""Synthetic cursor regression; never resolves files outside its temporary room."""
import importlib.util
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'scripts/file_reach.py'
if not SOURCE.exists():
    SOURCE = Path(__file__).with_name('file_reach_candidate.py')

class LongLinePaging(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='file-reach-cursor-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location('file_reach_cursor_fixture', SOURCE)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.fixture = self.root / 'fixture.txt'
        self.m._ROOM = SimpleNamespace(
            resolve=lambda label: str(self.fixture) if label == 'shared/fixture.txt' else None,
            _label_path=lambda path: 'shared/fixture.txt' if Path(path) == self.fixture else None)

    def pages(self, text):
        self.fixture.write_text(text, encoding='utf-8')
        arg = 'shared/fixture.txt'
        rows = []
        for _ in range(10):
            row = self.m._do('READ', arg, 'her', 'synthetic', 1, str(self.root / 'memory'))
            rows.append(row)
            self.m._load = lambda mem=None, row=row: [row]
            arg = self.m.read_on_arg(str(self.root / 'memory'))
            if arg is None:
                return rows
        self.fail('cursor did not reach end')

    def content(self, rows):
        return [match.group(1) for row in rows for match in re.finditer(r'^\s*\d+  (.*)$', row['text'], re.M)]

    def test_single_long_line_keeps_every_character(self):
        text = 'A' * 70000 + 'END_SENTINEL'
        rows = self.pages(text)
        self.assertEqual(len(rows), 3)
        self.assertEqual(''.join(self.content(rows)), text)
        self.assertEqual(rows[0]['next'], 1)
        self.assertEqual(rows[0]['next_char'], self.m.OPEN_CHARS)
        self.assertIsNone(rows[-1]['next'])

    def test_long_line_between_short_lines_preserves_line_cursor(self):
        rows = self.pages('first\n' + 'B' * 30000 + '\nlast')
        parts = self.content(rows)
        self.assertEqual(parts[0], 'first')
        self.assertEqual(parts[-1], 'last')
        self.assertEqual(''.join(parts[1:-1]), 'B' * 30000)
        self.assertIn('[READ: shared/fixture.txt:2]', rows[0]['text'])

    def test_unicode_continuation_uses_character_offsets(self):
        text = '\u03bb' * 30000 + 'END'
        self.assertEqual(''.join(self.content(self.pages(text))), text)

    def test_existing_line_only_position_is_unchanged(self):
        self.fixture.write_text('one\ntwo\nthree')
        _, body, _, n = self.m.read('shared/fixture.txt:2')
        self.assertEqual(n, 3)
        self.assertIn('    2  two', body)
        self.assertNotIn('one', body)
        self.assertNotIn('continues', body)

if __name__ == '__main__':
    unittest.main()
