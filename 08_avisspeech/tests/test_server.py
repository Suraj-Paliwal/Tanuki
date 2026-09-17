import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import wave
from unittest.mock import Mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Service, make_track, decode_wav, query_reading, EngineUnavailable


def wav_bytes(rate=44100, channels=2):
    t = np.arange(rate * 2) / rate
    x = 0.3 * np.sin(2 * np.pi * 240 * t)
    x[(t < 0.2) | ((t > 0.8) & (t < 1.15)) | (t > 1.75)] = 0
    raw = np.repeat((x * 32767).astype('<i2')[:, None], channels, axis=1).tobytes()
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(rate); w.writeframes(raw)
    return out.getvalue()


QUERY = {'kana': '愛、上', 'speedScale': 1, 'accent_phrases': [
    {'moras': [{'text': t, 'vowel': v, 'vowel_length': 0, 'consonant_length': 0}
               for t, v in [('ア', 'a'), ('イ', 'i'), ('、', 'pau'), ('ウ', 'u'), ('エ', 'e')]]}]}


class SpeechTests(unittest.TestCase):
    def test_uses_engine_moras_instead_of_top_level_kanji(self):
        self.assertEqual(query_reading(QUERY), 'あい、うえ')

    def test_stereo_resampling_and_duration(self):
        x, duration = decode_wav(wav_bytes())
        self.assertEqual(len(x), 32000)
        self.assertEqual(duration, 2)
        self.assertLessEqual(float(np.max(np.abs(x))), 0.31)

    def test_timing_zeros_are_not_used_and_silence_closes_mouth(self):
        track, kana, span, report = make_track(wav_bytes(), QUERY)
        self.assertEqual(track['duration'], 2)
        self.assertGreater(span[0], 0.1)
        self.assertLess(span[1], 1.9)
        times = np.arange(0, 2, 0.01)
        total = np.zeros(len(times))
        for keys in track['tracks'].values():
            self.assertEqual(keys[0], [0, 0])
            self.assertEqual(keys[-1], [2, 0])
            self.assertTrue(all(0 <= w <= 1 for _, w in keys))
            self.assertTrue(all(a[0] < b[0] for a, b in zip(keys, keys[1:])))
            total += np.interp(times, *np.array(keys).T)
        self.assertGreater(total.max(), 0.5)
        self.assertLessEqual(total.max(), 1.001)
        self.assertLess(total[(times > 0.9) & (times < 1.05)].max(), 0.01)

    def test_service_discovers_nonstandard_style_id_and_caches_pair(self):
        engine = Mock(base='http://127.0.0.1:10101')
        engine.voices.return_value = [{'id': '888753760', 'name': 'Test', 'style': 'Normal'}]
        engine.request.side_effect = lambda path, *a, **kw: json.loads(json.dumps(QUERY)) if path == '/audio_query' else wav_bytes()
        with tempfile.TemporaryDirectory() as folder:
            service = Service(engine, folder)
            result = service.say({'text': '愛、上', 'speed': 1.2})
            self.assertEqual(result['engine'], 'aivisspeech')
            self.assertEqual(result['voice'], '888753760')
            self.assertNotIn('exact', result['timing'])
            synthesis = [c for c in engine.request.call_args_list if c.args[0] == '/synthesis'][0]
            self.assertEqual(synthesis.kwargs['body']['speedScale'], 1.2)
            self.assertTrue(service.say({'text': '愛、上', 'speed': 1.2})['cached'])
            self.assertEqual(len(list(Path(folder).glob('*.wav'))), 1)
            self.assertEqual(len(list(Path(folder).glob('*.json'))), 1)

    def test_invalid_requests_and_engine_failure_do_not_fallback(self):
        engine = Mock()
        engine.voices.side_effect = EngineUnavailable('not running')
        with tempfile.TemporaryDirectory() as folder:
            service = Service(engine, folder)
            for payload in ({'text': ''}, {'text': 'あ' * 161}, {'text': 'あ', 'speed': float('nan')}, {'text': 'あ', 'speed': True}):
                with self.assertRaises(ValueError): service.say(payload)
            with self.assertRaises(EngineUnavailable): service.say({'text': 'こんにちは'})
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
