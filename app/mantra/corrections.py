"""The reviewer's corrections, as data applied to the extracted text.

WHY NOT JUST EDIT THE JSON. The texts in app/mantra/texts/ are produced by extraction, and any
re-extraction - a better filter, a re-fetched source - would silently throw hand edits away. Keeping
the corrections here means the pipeline is `source -> extract -> correct -> text`, every step
repeatable, and the reasoning for each change is next to the change.

HOW A PADA IS ADDRESSED, because the two kinds of review sheet number differently and getting this
wrong would corrupt a text rather than fail loudly:

  * a SINGLE-SOURCE sheet lists the whole text, so `pada N` is the Nth pada;
  * a COMPARISON sheet has a differences table numbered separately from the full listing, and the
    reviewer's numbers follow that table - so `pada N` is the Nth DIFFERING pada, which the builder
    resolves back to its position in source A.

Both were checked against the reviewer's own quotations before a single correction was applied:
Hanuman Chalisa "pada 15" is शंकर स्वयं/सुवन केसरी नंदन in the differences table and
कंचन बरन बिराज सुबेसा in the full text, so only one reading of the numbering can be right.
"""
from __future__ import annotations

import re
import unicodedata

# ---- the rules that apply to every text ---------------------------------------------------------
ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿⁠"), None)


def apply_global(text: str) -> str:
    """Rules 1-4 of the review notes, applied to every pada of every text.

    These are orthographic, not editorial: an ASCII colon standing in for a visarga, ॠ where the
    word is ऋ, the South-Indian ॆ and ॊ vowel signs, and invisible characters a source left behind.
    None of them changes a word; each of them changes how it is read or searched for.
    """
    text = text.translate(ZERO_WIDTH)
    # Rule 1: the Devanagari visarga, never an ASCII colon. Only where it follows Devanagari, so a
    # colon doing a colon's job elsewhere is left alone.
    text = re.sub(r"(?<=[ऀ-ॿ]):", "ः", text)
    # Rule 2: ऋ, never ॠ. The long vocalic R is a different letter and none of these words has it.
    text = text.replace("ॠ", "ऋ")
    # Rule 3: no ॆ or ॊ - those are South-Indian short vowels and the words here take े and ो.
    text = text.replace("ॆ", "े").replace("ॊ", "ो")
    # Rule 6 (orthographic half): the candrabindu forms ेँ and ीँ are written ें and ीं here.
    text = text.replace("ेँ", "ें").replace("ीँ", "ीं")
    return unicodedata.normalize("NFC", " ".join(text.split()))


# ---- the operations a correction can be ---------------------------------------------------------
def setp(n: int, text: str) -> tuple:
    """Replace pada n."""
    return ("set", n, text)


def drop(*numbers: int) -> tuple:
    """Remove these padas - headings, site furniture, text the source added."""
    return ("drop", numbers, None)


def after(n: int, *lines: str) -> tuple:
    """Insert lines after pada n - a line the source omitted."""
    return ("after", n, lines)


def keep_first(n: int) -> tuple:
    """Keep the first n padas and drop everything after them.

    SAYS THE INTENT INSTEAD OF GUESSING A RANGE. This was written as `drop(*range(5, 200))` - drop
    everything from pada 5 to some number comfortably past the end - which worked only because
    dropping an index that does not exist was a silent no-op. The accounting in apply() needs the
    number of padas actually removed to mean something, and "the mantra is the first four lines" is
    both the real intent and impossible to get wrong by one.
    """
    return ("keep", n, None)


def fixp(n: int, old: str, new: str) -> tuple:
    """Like fix(), but `n` is an ABSOLUTE PADA NUMBER even on a two-source text.

    THE TWO KINDS OF NUMBER ARE EASY TO CONFUSE, SO THEY ARE DIFFERENT WORDS. On a text with two
    sources every other op here is numbered by its row in the differences table, because that is
    what the first review sheet showed. The final sheets print the whole corrected text, so a
    correction read off one of those is numbered by pada instead. Passing a pada number to fix() on
    such a text either raises - row 88 of a twenty-row table does not exist - or, on a smaller
    number, silently edits whichever pada happens to sit at that row. The first case is how this
    was noticed; the second is why the distinction is in the name.
    """
    return ("fixp", n, (old, new))


def fix(n: int, old: str, new: str) -> tuple:
    """Replace a SUBSTRING inside pada n.

    MOST OF THE REVIEWER'S CORRECTIONS ARE WORDS, NOT LINES, and treating them as lines would
    truncate the verse. "pada 8: को नहिं जानत" against a pada reading "को नहीं जानत है जग में कपि,"
    is a correction to one word; written as a replacement it would delete two thirds of the line and
    look, in the output, exactly like a shorter pada. Every correction in this file was classified
    against the actual pada before it was written.
    """
    return ("fix", n, (old, new))


def take_b(*numbers: int) -> tuple:
    """Use source B's reading for these difference rows."""
    return ("take_b", numbers, None)


def apply(padas: list[str], ops: list, *, b_readings: dict | None = None,
          diff_index: list | None = None) -> list[str]:
    """Run the operations against the extracted padas and return the corrected text.

    `diff_index` maps a difference-row number to its position in `padas`; it is required for the
    comparison-sheet texts and absent for the rest. Operations are resolved against the ORIGINAL
    numbering and applied together at the end, so an insertion never shifts a later correction's
    target - which is the way this goes wrong if each edit is applied as it is read.
    """
    def resolve(n: int) -> int:
        if diff_index is not None:
            return diff_index[n - 1]
        return n - 1

    replace: dict[int, str] = {}
    remove: set[int] = set()
    inserts: dict[int, tuple] = {}
    for kind, target, payload in ops:
        if kind == "set":
            replace[resolve(target)] = payload
        elif kind in ("fix", "fixp"):
            # `fixp` is numbered by PADA even on a two-source text, where `fix` is numbered by its
            # row in the differences table. See fixp() for why they are different words.
            index = target - 1 if kind == "fixp" else resolve(target)
            base = replace.get(index, padas[index] if index < len(padas) else "")
            was, now = payload
            if was not in base:
                raise ValueError(f"pada {target}: {was!r} is not in {base!r}")
            replace[index] = base.replace(was, now)
        elif kind == "drop":
            indices = {resolve(n) for n in target}
            # A DROP THAT NAMES A PADA THE TEXT DOES NOT HAVE is a numbering mistake, not a no-op:
            # if 37 is out of range then some other number in the same list is probably wrong too.
            beyond = sorted(n + 1 for n in indices if n >= len(padas))
            if beyond:
                raise ValueError(f"drop() names pada(s) {beyond} but the text has {len(padas)}")
            remove |= indices
        elif kind == "keep":
            remove |= set(range(target, len(padas)))
        elif kind == "after":
            inserts.setdefault(resolve(target), ()) 
            inserts[resolve(target)] = inserts[resolve(target)] + payload
        elif kind == "take_b":
            for n in target:
                index = resolve(n)
                if b_readings and n in b_readings and b_readings[n]:
                    replace[index] = b_readings[n]

    out: list[str] = []
    for index, pada in enumerate(padas):
        if index not in remove:
            out.append(replace.get(index, pada))
        for extra in inserts.get(index, ()):
            out.append(extra)
    final = [apply_global(pada) for pada in out]

    # A CORRECTION NEVER DROPS A PADA UNLESS IT SAYS SO. This accounting exists because the Hanuman
    # Ashtak lost a line of scripture to a correction meant only to remove a typo: the source
    # printed "मोह भयो यह संकट भारो I" with a stray Latin I standing in for the danda, and dropping
    # the pada to be rid of the I deleted the verse with it. The output was one line shorter and
    # looked, from every angle except a reader who knew the stanza, like a correctly corrected text.
    #
    # The old last line ended `for p in out if p.strip()`, which was the second silent path: a `fix`
    # or `set` that emptied a pada made it vanish with no drop recorded. An empty pada is an error
    # now, not a deletion.
    blank = [n for n, pada in enumerate(final, 1) if not pada.strip()]
    if blank:
        raise ValueError(f"correction emptied pada(s) {blank} without dropping them; "
                         f"use drop() if that is what was meant")
    inserted = sum(len(extra) for extra in inserts.values())
    expected = len(padas) - len(remove) + inserted
    if len(final) != expected:
        raise ValueError(f"pada accounting: {len(padas)} in, {len(remove)} dropped, "
                         f"{inserted} inserted, so {expected} expected - got {len(final)}")
    return final


# ---- per text, exactly as the review notes give them ---------------------------------------------
#
# TWO-SOURCE TEXTS: numbers are rows of the differences table. The base is source A throughout
# unless a `take_b` says otherwise, which is what the notes instruct for each of these.

HANUMAN_CHALISA = [
    # PADA-NUMBERED, from the final sheet: the candrabindu on महँ, which the source omitted.
    # Everything else in this list is numbered by its row in the differences table.
    fixp(88, "हृदय मह डेरा", "हृदय महँ डेरा"),
    setp(15, "शंकर सुवन केसरीनंदन"),          # A merged two variants with a slash
    setp(33, "तुम उपकार सुग्रीवहिं कीन्हा"),   # A: कीह्ना, a wrong conjunct
    setp(34, "राम मिलाय राज पद दीन्हा"),       # A: दीह्ना
    setp(37, "जुग सहस्र जोजन पर भानू"),        # it rhymes with जानू
    setp(41, "तीनों लोक हाँक तें काँपै"),
    setp(44, "संकट तें हनुमान छुड़ावै"),
    setp(55, "और देवता चित्त न धरई"),          # A: ना
    # padas 3 and 61 have no reading in B; the note says keep A, which is the default.
    #
    # THE OPTIONAL GITA PRESS READINGS ARE TAKEN. The note calls pada 13 and 14 optional and says
    # either is fine; rule 6 of the same notes asks for the Gita Press convention on Awadhi texts,
    # so taking them is the reading that agrees with the rest of the file rather than a preference.
    setp(13, "हाथ बज्र औ ध्वजा बिराजै"),
    setp(14, "काँधे मूँज जनेऊ साजै"),
]

DURGA_CHALISA = [
    take_b(1),                                  # A's कहु is a typo for करहु
    setp(2, "मातु लीजिये अंक"),                 # closing doha, only in A
    take_b(6),                                  # drop A's "इति … संपूर्ण", use B's line
    drop(7, 8),                                 # site text about performing the aarti
]

RUDRASHTAKAM = [
    setp(1, "नमामीशमीशान निर्वाणरूपं"),         # long ई
    fix(2, "गंभीरं", "गभीरं"),                 # a word inside the pada, not the pada
    setp(10, "चिदानंदसंदोह मोहापहारी"),
    setp(15, "प्रभो पाहि आपन्नमामीश शंभो"),     # A: आपन्नमाशीश
    # padas 9 and 11 keep their long-ई endings पुरारी / मन्मथारी, as in the Ramcharitmanas -
    # which is the default, so there is nothing to do.
]

SHIV_TANDAV = [
    take_b(6, 7, 8, 11, 17),
    # padas 3 and 5 take A, which is the default: लम्बितां and धगज्ज्वलल्ललाट.
    # A's two extra verses (12-15) are kept; most printed editions carry them.
    drop(1, 2),                                 # A's "अथ सुसंशुद्धं…" heading
    setp(18, "इति श्रीरावणकृतं शिवताण्डवस्तोत्रं सम्पूर्णम्"),
]

RAM_RAKSHA = [
    take_b(4, 6, 7, 8, 9, 10, 11, 12, 14, 16, 38, 42, 43, 44, 49, 51, 53, 56, 67, 68, 69),
    # Both sources are wrong here; the reviewer supplies the reading.
    setp(18, "करौ सीतापतिः पातु हृदयं जामदग्न्यजित्"),
    setp(63, "जितेन्द्रियं बुद्धिमतां वरिष्ठम्"),
    setp(30, "जगज्जैत्रैकमन्त्रेण रामनाम्नाभिरक्षितम्"),
    # pada 55 needs nothing: the note names रामचन्द्रः as correct and B as the one that has
    # रामचंन्द्र, and A - the base - already reads it correctly.
    setp(57, "सर्वस्वं मे रामचन्द्रो दयालुर्नान्यं जाने नैव जाने न जाने"),
    drop(58),                                   # 57 and 58 become one line
]


# SINGLE-SOURCE TEXTS: numbers are padas of the full text as the sheet listed it.

SHIV_CHALISA = [
    # Rule 2 does the work here - ॠ becomes ऋ - and apply_global applies it everywhere, so padas
    # 73 and 91 need no individual operation. The reviewer's note is satisfied by the rule.
]

OM_JAI_JAGDISH_HARE = [
    setp(15, "शरण गहूं मैं किसकी"),
    setp(51, "स्वामी पाप हरो देवा"),            # source: स्वमी, and a "(कष्ट)" gloss
]

GANESH_AARTI = [
    drop(1),                                     # source intro line
]

JAI_AMBE_GAURI = [
    drop(1),                                     # "भक्ति भारत आप तक लिरिक्स पहुँचा रहा है"
    fix(37, "रूद्राणी", "रुद्राणी"),
    fix(45, "अरू", "अरु"),
    drop(54),                                    # the bracketed variant; वर मुद्रा धारी stays
    setp(63, "श्री अंबेजी की आरती, जो कोई नर गावे"),
    drop(64),
]

AARTI_KUNJ_BIHARI = [
    # The whole line was restored after pada 21, which left the source's two half-lines standing
    # behind it as padas 22 and 23 - sheet rows 23 and 24, the duplicates the reviewer struck out.
    after(21, "बजे मुरचंग, मधुर मिरदंग, ग्वालिन संग"),
    drop(22, 23),
    fix(20, "तरसैं", "तरसै"),                 # no anusvara, as the printed book has it
    setp(29, "कलिमल हारिणि श्रीगंगा"),
    after(30, "बसी शिव सीस, जटा के बीच, हरै अघ कीच"),
    after(38, "चांदनी चंद, कटत भव फंद"),
]

HANUMAN_AARTI = [
    drop(1, 2, 3, 4, 5, 39),                     # the मनोजवं shloka and "इति संपूर्णंम्"
    fix(8, "गिरवर", "गिरिवर"),
    fix(20, "मुर्छित", "मूर्छित"),
    setp(21, "लाये संजीवन प्राण उबारे"),
    fix(23, "पैठि पताल", "पैठि पाताल"),
    setp(28, "सुर नर मुनि जन आरती उतारें"),
]

SHANI_CHALISA = [
    after(2, "जय जय श्री शनिदेव प्रभु, सुनहु विनय महाराज"),
    setp(73, "स्वर्ण सर्व सुख मंगल भारी"),       # "सर्व" was duplicated
]

GANESH_CHALISA = [
    fix(6, "शुभः काजू", "शुभ काजू"),
    fix(8, "विश्व विनायका", "विश्व विनायक"),
    setp(9, "वक्र तुण्ड शुचि शुण्ड सुहावन"),
    fix(18, "गौरी लालन", "गौरी ललन"),
    fix(20, "मुषक", "मूषक"),
    fix(22, "अति शुची", "अति शुचि"),
    fix(26, "धरी द्विज रूपा", "धरि द्विज रूपा"),
    fix(27, "अतिथि जानी के", "अतिथि जानि कै"),
    # The note lists 29, 35, 36 and 55 for ह्वै; 35 and 36 also have their own word corrections,
    # and both have to be applied to the same pada rather than one replacing the other.
    fix(29, "हवै", "ह्वै"), fix(55, "हवै", "ह्वै"),
    fix(35, "अस कही", "अस कहि"), fix(35, "हवै", "ह्वै"),
    fix(36, "पालना पर", "पलना पर"), fix(36, "हवै", "ह्वै"),
    fix(40, "नाभ ते सुरन", "नभ ते सुरन"),
    fix(49, "कहत लगे शनि", "कहन लगे शनि"),
    fix(53, "पदतहिं शनि", "पड़तहिं शनि"),
    setp(79, "अब प्रभु दया दीन पर कीजै"),
    setp(80, "अपनी भक्ति शक्ति कछु दीजै"),
    setp(85, "सम्वत अपन सहस्र दश"),
    setp(88, "मंगल मूर्ति गणेश"),
]

BAJRANG_BAAN = [
    # The note quotes the opening doha from its second half to its fourth: the correction is करैं,
    # and बिनय for विनय, in padas 2 and 4.
    setp(2, "बिनय करैं सनमान"), setp(4, "सिद्ध करैं हनुमान"),
    setp(12, "मारेहु लात गई सुरलोका"),
    setp(19, "लाह समान लंक जरि गई"), setp(20, "जय जय धुनि सुरपुर नभ भई"),
    setp(24, "आतुर ह्वै दुख करहु निपाता"),
    setp(29, "ॐ ह्रीं ह्रीं ह्रीं हनुमंत कपीसा"),
    setp(39, "सत्य होहु हरि सपथ पाइ कै"), setp(40, "राम दूत धरु मारु धाइ कै"),
    setp(52, "यहि औसर अब केहि गोहरावौं"),
    setp(53, "उठु उठु चलु तोहि राम दुहाई"), setp(54, "पायँ परौं कर जोरि मनाई"),
    setp(56, "ॐ हनु हनु हनु हनु हनुमंता"),
    # The closing doha is four half-lines, not three: 71 and 72 stay separate.
    setp(69, "उर प्रतीति दृढ़, सरन ह्वै"),
    setp(71, "बाधा सब हर, करैं"),
    # ॐ for "ओं" wherever it appears - padas 27, 30, 55, 57, 58 as well as the two set above.
    fix(27, "ओं", "ॐ"), fix(30, "ओं", "ॐ"),
    fix(55, "ओं", "ॐ"), fix(57, "ओं", "ॐ"), fix(58, "ओं", "ॐ"),
]

HANUMAN_ASHTAK = [
    drop(1),                                     # a heading
    # PADA 37 WAS NOT A STRAY CHARACTER, IT WAS A LINE OF SCRIPTURE WITH ONE. The source printed
    # "मोह भयो यह संकट भारो I" - a Latin I where the danda belongs - and this list used to drop the
    # whole pada, which deleted the verse along with the typo. The reviewer caught the missing line
    # against a printed book. The accounting in apply() now refuses any correction that loses a
    # pada without saying so.
    fix(37, " I", ""),
    fix(34, "रावन युद्ध", "रावन जुध"),
    fix(3, "अंधियारों", "अँधियारो"),
    fix(7, "छाड़ी दियो", "छाँड़ि दियो"),
    fix(8, "को नहीं जानत", "को नहिं जानत"),
    setp(25, "जाय महा रजनीचर मारो"),
    # THE REFRAIN CLOSES EVERY STANZA. The source prints it once, after stanza 1 (padas 8-9);
    # stanzas 2 to 8 end at padas 15, 21, 27, 33, 39, 45 and 51, and each needs it back.
    *[after(n, "को नहिं जानत है जग में कपि", "संकटमोचन नाम तिहारो")
      for n in (15, 21, 27, 33, 39, 45, 51)],
]

MAHAMRITYUNJAYA = [
    # The source page printed its own explanation after the mantra; only the first four padas are
    # the mantra itself. Everything else goes, and our explainer is written rather than borrowed.
    keep_first(4),
]

KANAKADHARA = [
    drop(1),                                     # title
]

LINGASHTAKAM = [
    setp(1, "ब्रह्ममुरारिसुरार्चितलिङ्गं"),
    setp(5, "देवमुनिप्रवरार्चितलिङ्गं"),
    setp(10, "बुद्धिविवर्धनकारणलिङ्गं"),
    setp(17, "कुङ्कुमचन्दनलेपितलिङ्गं"),
    setp(21, "देवगणार्चितसेवितलिङ्गं"),
    setp(23, "दिनकरकोटिप्रभाकरलिङ्गं"),
    setp(25, "अष्टदलोपरिवेष्टितलिङ्गं"),
    setp(31, "परात्परं परमात्मकलिङ्गं"),
    setp(33, "लिङ्गाष्टकमिदं पुण्यं यः पठेच्छिवसन्निधौ"),
    setp(34, "शिवलोकमवाप्नोति शिवेन सह मोदते"),
]

GANESH_ATHARVASHIRSHA = [
    drop(1, 19, 51, 67, 77, 112),                # the source's own headings
    after(50, "त्वं ब्रह्मा त्वं विष्णुस्त्वं रुद्रस्त्वमिन्द्रस्त्वमग्निस्त्वं "
              "वायुस्त्वं सूर्यस्त्वं चन्द्रमास्त्वं ब्रह्म भूर्भुवः स्वरोम्"),
    fix(20, " (वदिष्यामि)", ""), fix(21, " (वदिष्यामि)", ""),
    fix(48, "स्थिथोऽसि", "स्थितोऽसि"),
    setp(69, "तन्नो दन्ती प्रचोदयात्"),
    setp(84, "स सर्वविघ्नैर्न बाध्यते"),
    after(112, "ॐ सह नाववतु", "सह नौ भुनक्तु"),
]

GAYATRI = []          # approved as it stands

#: Every text with corrections, and the sheet kind its numbers come from.
#: THE TWO SAHASRANAMAMS, after the reviewer rejected the first attempt. Source notes out, and ॐ
#: for the source's ओं. EVERY NOTE IS NAMED BY ITS PADA rather than matched by a pattern, because
#: "लिखित्वा पुस्तके यस्तु नामसाहस्रमुत्तमम्" is a line of the phalashruti that happens to contain
#: the word पुस्तक - a pattern for "पुस्तक" would have deleted scripture to remove a note about a
#: book. The padas were read one at a time and classified.
VISHNU_SAHASRANAMAM = [
    drop(2, 68, 75, 181, 379, 387, 388),
    fix(298, "[** ", ""),                        # a note marker on a line that is real verse
    # NUMBERED AGAINST THE DE-DUPLICATED TEXT. The first version of this list named padas 438 to
    # 458, which existed only because the uttarapeetika's 47 repeated lines were still in the text;
    # removing the duplication moved everything after it, and the build raised on pada 438 rather
    # than editing whatever had taken its place.
    *[fix(n, "ओं", "ॐ") for n in (16, 295, 298, 345, 352, 355, 361, 367, 417)],
]

LALITA_SAHASRANAMAM = [
    # pada 600 stays: it is phalashruti, not a note about a book.
    drop(107, 355, 500, 501),
]

BY_SLUG = {
    "vishnu-sahasranamam": (VISHNU_SAHASRANAMAM, "single"),
    "lalita-sahasranamam": (LALITA_SAHASRANAMAM, "single"),
    "hanuman-chalisa": (HANUMAN_CHALISA, "comparison"),
    "durga-chalisa": (DURGA_CHALISA, "comparison"),
    "rudrashtakam": (RUDRASHTAKAM, "comparison"),
    "shiv-tandav-stotram": (SHIV_TANDAV, "comparison"),
    "ram-raksha-stotra": (RAM_RAKSHA, "comparison"),
    "shiv-chalisa": (SHIV_CHALISA, "single"),
    "om-jai-jagdish-hare": (OM_JAI_JAGDISH_HARE, "single"),
    "ganesh-aarti-jai-ganesh-deva": (GANESH_AARTI, "single"),
    "jai-ambe-gauri": (JAI_AMBE_GAURI, "single"),
    "aarti-kunj-bihari-ki": (AARTI_KUNJ_BIHARI, "single"),
    "hanuman-aarti": (HANUMAN_AARTI, "single"),
    "shani-chalisa": (SHANI_CHALISA, "single"),
    "ganesh-chalisa": (GANESH_CHALISA, "single"),
    "bajrang-baan": (BAJRANG_BAAN, "single"),
    "hanuman-ashtak": (HANUMAN_ASHTAK, "single"),
    "mahamrityunjaya-mantra": (MAHAMRITYUNJAYA, "single"),
    "kanakadhara-stotram": (KANAKADHARA, "single"),
    "lingashtakam": (LINGASHTAKAM, "single"),
    "ganesh-atharvashirsha": (GANESH_ATHARVASHIRSHA, "single"),
    "gayatri-mantra": (GAYATRI, "single"),
}
