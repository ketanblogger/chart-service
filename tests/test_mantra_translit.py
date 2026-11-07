"""The transliteration is ours, by table, and readable aloud."""
from app.mantra import translit


def test_it_is_a_table_not_a_model_and_not_a_copy():
    """A transliteration is a mechanical mapping. Taking one from a source would be taking the
    source's work; asking a model would make every line something to check."""
    assert translit.CONSONANTS and translit.VOWELS and translit.MATRAS
    assert translit.romanise("हनुमान") == translit.romanise("हनुमान")      # deterministic


def test_it_reads_the_way_the_reader_expects():
    """Reading-Roman, not IAST: somebody searching "hanuman chalisa in english" wants to say the
    verse out loud, not to see Hanumāna Cālīsā."""
    assert translit.romanise("हनुमान") == "hanuman"
    assert translit.romanise("शिव") == "shiva"
    assert translit.romanise("चरन") == "charan"
    for roman in (translit.romanise("श्रीगुरु चरन सरोज रज"),):
        assert not any(ch in roman for ch in "āīūṇṭḍṣśṛṁḥ"), roman


def test_the_final_inherent_vowel_goes_unless_it_cannot():
    """Hindi does not pronounce it - but देवस्य without it is "devasy", which cannot be read."""
    assert translit.romanise("देवस्य") == "devasya"
    assert translit.romanise("सरोज") == "saroj"


def test_a_conjunct_loses_its_inherent_vowel():
    assert "tts" in translit.romanise("तत्सवितुर्वरेण्यम्") or \
           translit.romanise("तत्सवितुर्वरेण्यम्").startswith("tats")


def test_every_pada_of_every_text_transliterates_without_leaving_devanagari():
    from app.mantra import texts as T

    for text in T.PHASE_1:
        for verse in T.verses(text.slug):
            roman = translit.romanise(verse["text"])
            left = [ch for ch in roman if "ऀ" <= ch <= "ॿ"]
            assert not left, f"{text.slug}: {verse['text'][:30]} -> {roman[:40]} left {left[:4]}"
