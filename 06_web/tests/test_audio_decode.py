import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import audio_lipsync as audio


class DecoderTests(unittest.TestCase):
    def test_explicit_decoder_path_is_respected(self):
        with patch.dict(os.environ, {'FFMPEG_BINARY': 'C:/my tools/ffmpeg.exe'}):
            self.assertEqual(audio.ffmpeg_executable(), 'C:/my tools/ffmpeg.exe')

    def test_decoder_on_path_is_preferred(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(audio.shutil, 'which', return_value='system-ffmpeg'):
            self.assertEqual(audio.ffmpeg_executable(), 'system-ffmpeg')

    def test_imageio_decoder_works_without_path_entry(self):
        try:
            import imageio_ffmpeg
        except ImportError:
            self.skipTest('optional imageio-ffmpeg package is not installed')
        with patch.dict(os.environ, {}, clear=True), patch.object(audio.shutil, 'which', return_value=None):
            self.assertTrue(Path(audio.ffmpeg_executable()).is_file())

    def test_saved_japanese_mp3_really_decodes(self):
        clips = list((Path(__file__).resolve().parents[1] / '.media').glob('*.mp3'))
        if not clips:
            self.skipTest('no saved audio in this copy')
        samples = audio.decode(str(clips[0]))
        self.assertGreater(len(samples), 1600)
        self.assertGreater(float(abs(samples).max()), 0.01)
        self.assertLessEqual(float(abs(samples).max()), 1)


if __name__ == '__main__':
    unittest.main()
