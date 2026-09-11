"""Regression checks for Japanese mouth poses at known speech positions."""
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB / "lib"))
sys.path.insert(0, str(WEB))

from jp_kana import moras, to_hiragana
from jp_lipsync import build, sample
from vv_timing import track_from_query


def query(moras, pre=0.1, post=0.2, speed=1.0):
    return {"accent_phrases": [{"moras": moras}],
            "prePhonemeLength": pre, "postPhonemeLength": post,
            "speedScale": speed}


def mora(vowel, duration=0.2, consonant=None, consonant_length=0.0):
    return {"vowel": vowel, "vowel_length": duration,
            "consonant": consonant, "consonant_length": consonant_length}


class JapanesePronunciationTests(unittest.TestCase):
    def test_small_vowels_form_one_mora(self):
        parsed = moras("ファティシェチェフォウィ")
        self.assertEqual([m.kana for m in parsed], ["ふぁ", "てぃ", "しぇ", "ちぇ", "ふぉ", "うぃ"])
        self.assertEqual([m.vowel for m in parsed], list("aieeoi"))

    def test_existing_japanese_survives_romaji_run(self):
        self.assertEqual(to_hiragana("こんにちは tanuki です"), "こんにちは たぬき です")
        self.assertEqual(to_hiragana("タンポポ"), "たんぽぽ")

    def test_small_y_and_long_vowel_still_work(self):
        parsed = moras("きょう、コーヒー")
        self.assertEqual([m.kana for m in parsed], ["きょ", "う", "、", "こ", "ー", "ひ", "ー"])
        self.assertEqual(parsed[4].vowel, "o")


class PoseAssertions:
    def assert_pose(self, track, time, vowel=None, weight=1.0):
        got = sample(track["tracks"], time)
        for name in ("A", "I", "U", "E", "O"):
            self.assertAlmostEqual(got[name], weight if name == vowel else 0.0, places=3)


class EstimatedPoseTests(PoseAssertions, unittest.TestCase):
    def test_vowels_hold_identifiable_shapes(self):
        track = build("あいうえお", mora_dur=0.2)
        for index, name in enumerate("AIUEO"):
            for fraction in (0.25, 0.5, 0.75):
                self.assert_pose(track, index * 0.2 + fraction * 0.2, name)

    def test_bilabial_closure_and_vowel_release(self):
        for text in ("あま", "あば", "あぱ"):
            track = build(text, mora_dur=0.2)
            self.assert_pose(track, 0.21)
            self.assert_pose(track, 0.24)
            self.assert_pose(track, 0.32, "A")

    def test_pause_and_end_are_closed(self):
        track = build("あ、う", mora_dur=0.2)
        for time in (0.201, 0.25, 0.319, 0.52, 0.7):
            self.assert_pose(track, time)
        self.assert_pose(track, 0.42, "U")

    def test_supplied_duration_includes_final_closure(self):
        track = build("あいう", total=0.9)
        self.assertAlmostEqual(track["duration"], 0.9)
        self.assert_pose(track, 0.9)
        self.assertTrue(all(key[0] <= 0.9 for keys in track["tracks"].values() for key in keys))

    def test_text_does_not_weaken_vowel_shape_from_previous_kana(self):
        for text in ("はぐ", "しう", "です"):
            self.assert_pose(build(text, mora_dur=0.2), 0.3, "U")


class EnginePoseTests(PoseAssertions, unittest.TestCase):
    def test_engine_holds_bilabial_consonant_until_vowel(self):
        for cons in ("m", "b", "p"):
            track, total = track_from_query(query([mora("a"), mora("u", consonant=cons, consonant_length=0.1)]))
            self.assertAlmostEqual(total, 0.8)
            for time in (0.31, 0.35, 0.395):
                self.assert_pose(track, time)
            self.assert_pose(track, 0.50, "U")

    def test_engine_vowel_plateaus_and_silent_padding(self):
        track, _ = track_from_query(query([mora("a"), mora("i")]))
        for time in (0.0, 0.05, 0.09, 0.50, 0.60, 0.70):
            self.assert_pose(track, time)
        for time in (0.15, 0.20, 0.25):
            self.assert_pose(track, time, "A")
        for time in (0.35, 0.40, 0.45):
            self.assert_pose(track, time, "I")

    def test_engine_devoiced_u_retains_rounded_shape(self):
        track, _ = track_from_query(query([mora("U")]))
        self.assert_pose(track, 0.2, "U", 0.9)

    def test_zero_dummy_or_nonfinite_durations_are_not_exact(self):
        for duration in (0.0, -0.1, math.nan, math.inf):
            track, _ = track_from_query(query([mora("a", duration=duration)]))
            self.assertIsNone(track)

    def test_mixed_zero_dummy_durations_are_not_exact(self):
        track, _ = track_from_query(query([mora("a"), mora("u", duration=0.0)]))
        self.assertIsNone(track)

    def test_track_weights_remain_valid_during_transitions(self):
        track, total = track_from_query(query([mora(v) for v in "aiueo"]))
        for index in range(math.ceil(total * 100)):
            values = sample(track["tracks"], index / 100.0)
            self.assertTrue(all(0 <= value <= 1 for value in values.values()))
            self.assertLessEqual(sum(values.values()), 1.00001)


class CacheTests(unittest.TestCase):
    def test_track_revision_changes_persisted_response_key(self):
        import tanuki_tts_server as server
        args = ("あいう", "offline", None, "+0%", True, 1.0, True, True)
        current = server._resp_key(*args)
        with patch.object(server, "TRACK_CACHE_VERSION", "old-poses"):
            self.assertNotEqual(current, server._resp_key(*args))


if __name__ == "__main__":
    unittest.main()
