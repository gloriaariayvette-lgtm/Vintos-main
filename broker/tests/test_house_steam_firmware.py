"""Offline firmware packaging and signal/audio behavior; never connects to a board."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'home/esphome'


class SteamFirmware(unittest.TestCase):
    def test_required_sources_are_packaged(self):
        for name in ('shower_dac.h', 'wav_pcm.h', 'steam_signal.h',
                     'components/speaker_streaming/__init__.py'):
            self.assertTrue((ROOT / name).is_file(), name)

    def test_signal_and_audio_behaviors(self):
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'firmware behavior checks require a C++ compiler')
        with tempfile.TemporaryDirectory() as temp:
            for name in ('steam-signal', 'wav-pcm', 'resampler', 'noise-shaping'):
                with self.subTest(name=name):
                    binary = Path(temp) / name
                    subprocess.run([compiler, '-std=c++17', '-O2', '-I', str(ROOT),
                                    str(ROOT / 'tests' / (name + '-test.cpp')),
                                    '-o', str(binary)], check=True, timeout=30)
                    subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
