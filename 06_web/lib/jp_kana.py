# -*- coding: utf-8 -*-
"""Japanese text -> mora sequence.

Accepts hiragana, katakana or romaji. Kanji is not handled: give it kana.
"""
import re, unicodedata

KATA_TO_HIRA = {chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)}

SMALL_Y = set("ゃゅょ")
SMALL_V = set("ぁぃぅぇぉ")
SOKUON  = "っ"
HATSUON = "ん"
CHOON   = "ー"

# every base kana -> the vowel it ends on
VOWEL = {}
for row, v in [("あかさたなはまやらわがざだばぱ", "a"),
               ("いきしちにひみりぎじぢびぴ",     "i"),
               ("うくすつぬふむゆるぐずづぶぷ",   "u"),
               ("えけせてねへめれげぜでべぺ",     "e"),
               ("おこそとのほもよろをごぞどぼぽ", "o")]:
    for ch in row:
        VOWEL[ch] = v
VOWEL["ゔ"] = "u"
for ch, v in zip("ぁぃぅぇぉ", "aiueo"):
    VOWEL[ch] = v
# small ya/yu/yo carry the vowel of the whole youon mora: きょ ends on "o"
for ch, v in zip("ゃゅょ", "auo"):
    VOWEL[ch] = v

# consonant class, used for lip closure and timing
BILABIAL  = set("まみむめもばびぶべぼぱぴぷぺぽ")     # lips must meet first
FRICATIVE = set("さしすせそざじずぜぞはひふへほ")
PLOSIVE   = set("かきくけこがぎぐげごたちつてとだぢづでど")

ROMAJI = [
    ("kya","きゃ"),("kyu","きゅ"),("kyo","きょ"),("sha","しゃ"),("shu","しゅ"),("sho","しょ"),
    ("cha","ちゃ"),("chu","ちゅ"),("cho","ちょ"),("nya","にゃ"),("nyu","にゅ"),("nyo","にょ"),
    ("hya","ひゃ"),("hyu","ひゅ"),("hyo","ひょ"),("mya","みゃ"),("myu","みゅ"),("myo","みょ"),
    ("rya","りゃ"),("ryu","りゅ"),("ryo","りょ"),("gya","ぎゃ"),("gyu","ぎゅ"),("gyo","ぎょ"),
    ("ja","じゃ"),("ju","じゅ"),("jo","じょ"),("bya","びゃ"),("byu","びゅ"),("byo","びょ"),
    ("pya","ぴゃ"),("pyu","ぴゅ"),("pyo","ぴょ"),
    ("shi","し"),("chi","ち"),("tsu","つ"),("fu","ふ"),("ji","じ"),
    ("ka","か"),("ki","き"),("ku","く"),("ke","け"),("ko","こ"),
    ("sa","さ"),("su","す"),("se","せ"),("so","そ"),
    ("ta","た"),("te","て"),("to","と"),
    ("na","な"),("ni","に"),("nu","ぬ"),("ne","ね"),("no","の"),
    ("ha","は"),("hi","ひ"),("he","へ"),("ho","ほ"),
    ("ma","ま"),("mi","み"),("mu","む"),("me","め"),("mo","も"),
    ("ya","や"),("yu","ゆ"),("yo","よ"),
    ("ra","ら"),("ri","り"),("ru","る"),("re","れ"),("ro","ろ"),
    ("wa","わ"),("wo","を"),
    ("ga","が"),("gi","ぎ"),("gu","ぐ"),("ge","げ"),("go","ご"),
    ("za","ざ"),("zu","ず"),("ze","ぜ"),("zo","ぞ"),
    ("da","だ"),("de","で"),("do","ど"),
    ("ba","ば"),("bi","び"),("bu","ぶ"),("be","べ"),("bo","ぼ"),
    ("pa","ぱ"),("pi","ぴ"),("pu","ぷ"),("pe","ぺ"),("po","ぽ"),
    ("n","ん"),
    ("a","あ"),("i","い"),("u","う"),("e","え"),("o","お"),
]

def romaji_to_kana(s):
    s = s.lower()
    out, i = [], 0
    while i < len(s):
        if s[i] in " \t,.!?-":
            out.append(" " if s[i] in " \t" else "。"); i += 1; continue
        # geminate: double consonant -> sokuon
        if i + 1 < len(s) and s[i] == s[i+1] and s[i] not in "aeioun":
            out.append(SOKUON); i += 1; continue
        for r, k in ROMAJI:
            if s.startswith(r, i):
                out.append(k); i += len(r); break
        else:
            i += 1
    return "".join(out)

def to_hiragana(text):
    text = unicodedata.normalize("NFKC", text)
    if re.search(r"[a-zA-Z]", text):
        text = romaji_to_kana(text)
    return "".join(KATA_TO_HIRA.get(c, c) for c in text)

class Mora:
    __slots__ = ("kana", "vowel", "kind", "bilabial")
    def __init__(self, kana, vowel, kind, bilabial=False):
        self.kana, self.vowel, self.kind, self.bilabial = kana, vowel, kind, bilabial
    def __repr__(self):
        return f"<{self.kana} {self.vowel or '-'} {self.kind}>"

def moras(text):
    """Split kana into moras, the unit Japanese timing actually runs on.

    A youon pair (きゃ) is ONE mora, not two - treating it as two makes the
    mouth flap on a sound that is a single beat. Sokuon and hatsuon are moras
    that carry a beat but no vowel, so they get their own kinds.
    """
    h = to_hiragana(text)
    out, i = [], 0
    while i < len(h):
        c = h[i]
        if c in " 　":
            out.append(Mora(c, None, "pause")); i += 1; continue
        if c in "。、!?！？.,":
            out.append(Mora(c, None, "pause")); i += 1; continue
        if c == SOKUON:
            out.append(Mora(c, None, "stop")); i += 1; continue
        if c == HATSUON:
            out.append(Mora(c, None, "nasal")); i += 1; continue
        if c == CHOON:
            if out and out[-1].vowel:
                out.append(Mora(c, out[-1].vowel, "long"))
            i += 1; continue
        if i + 1 < len(h) and h[i+1] in SMALL_Y:
            out.append(Mora(c + h[i+1], VOWEL.get(h[i+1], "a"), "mora", c in BILABIAL))
            i += 2; continue
        if c in VOWEL:
            out.append(Mora(c, VOWEL[c], "mora", c in BILABIAL))
            i += 1; continue
        i += 1
    return out
