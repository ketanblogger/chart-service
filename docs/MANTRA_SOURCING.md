# Mantra texts: where each one came from, and what is still missing

**Status: reviewed and corrected. 20 of 24 verified, 2 re-sourced and awaiting a read, 2 unsourced.** This file is the
record behind that, and it is updated as sources are found.

This file is the record behind that sentence. It is written for the decision it needs, not as an
apology: the texts ARE the product on these pages, and shipping one that is subtly wrong is worse
than shipping nothing, because people recite them.

## What was tried

`hi.wikisource.org`, `sa.wikisource.org`, `en.wikisource.org` and `sanskritdocuments.org`, searched
by exact title in Devanagari and by ITRANS filename, plus Hindi and English Wikipedia as a second
source. Everything cached under `var/mantra-sources/`.

A first sweep reported "0 of 24 found", which was wrong: Wikimedia refuses a request with no
User-Agent and the error was being swallowed into an empty list. The numbers below are from the
corrected run.

## The result

| | count | |
|---|---|---|
| Verified - two sources, or one source plus the reviewer's read | **20** | everything except the four below |
| Re-sourced after rejection, awaiting a read | **2** | Vishnu Sahasranamam, Lalita Sahasranamam |
| No usable source | **2** | Sundarkand, Om Namah Shivaya |

## The review round

The reviewer read all 22 sheets and returned about 150 corrections, then read five final
sheets against a printed book and returned the last of them, which are held as data in
`app/mantra/corrections.py` and applied by `scripts/build_mantra_texts.py`. The pipeline is
`source -> extract -> correct -> text`: nothing is hand-edited into the text files, so a better
extractor or a re-fetched source can be run again without losing a correction.

Both sahasranamams were **rejected**: the page carrying each name held only the पूर्वपीठिका, the
preface, and not the thousand names. They are published in three parts and are now assembled from
all three. Vishnu is 416 padas and Lalita 674, against 45 and 105 on the rejected
pages - and 470/678 on the first assembly, before 47 padas the uttarapeetika reprints
from the main page were found to be in the text twice.

### The three that are left, and why each is hard

Every one is a case of the right title sitting on the wrong text:

* **Sundarkand** - `sa.wikisource`'s सुन्दरकाण्ड is VALMIKI'S Sanskrit, a 68-sarga index. The
  368,000-a-month search is for TULSIDAS'S Awadhi text from the Ramcharitmanas.
* **Hanuman Ashtak** - now sourced. stotranidhi's "Hanuman Ashtakam attributed to Tulsidas" is
  SANSKRIT (हनूमन्नञ्जनासूनो वायुपुत्र महाबल) and was the wrong text; the Awadhi one that the
  201,000-a-month search wants is on bhaktibharat, found by web search rather than by probing URLs.
* **Om Namah Shivaya** - the mantra is five syllables, so what a page needs beside it is the Shiva
  Panchakshara Stotram; the fetch of that returned nothing usable.

Devotional sites (bhaktibharat.com, stotranidhi.com) carry the Hindi chalisas and aartis that
Wikisource does not, which is what moved Hanuman Chalisa and Durga Chalisa into the verified column.

The pattern is consistent: Wikisource carries **Sanskrit stotras** and barely carries the
**Awadhi and Hindi devotional literature** - the chalisas, the aartis, Bajrang Baan - which is where
most of the search volume is.

Two specific traps worth recording:

* `sa.wikisource` has a page titled सुन्दरकाण्ड, but it is **Valmiki's Sanskrit Sundarakanda**, a
  68-sarga index. What a Hindi reader means by "sundarkand path" is **Tulsidas's Awadhi Sundarkand**
  from the Ramcharitmanas. Taking the first for the second would have shipped the wrong work under
  the right title.
* The second-source check is not a formality. On Rudrashtakam the two sources disagree on the very
  first word - नमामिशमीशान against नमामीशमीशान, a short i against a long ii in a word people say
  aloud every day.

## The comparison, as run

Compared at the **pada** (what the danda separates), not the line: the two sources break verses
differently, so a line-by-line diff said every line differed. Orthography is folded first - final
anusvara against final म्, compounding, spacing - because रूपं and रूपम् are the same word typeset
two ways. Real variants survive the folding, which is the point.

The first run of this comparison is in git history and its numbers are not current: it ran
before whole-page extraction was replaced by container extraction and before the danda rule was
fixed, so it was comparing padas that included sidebars and was missing others entirely.

**Every text as built, 2026-10-31** - `srcs` is how
many sources the text was taken from or checked against, `read` whether the reviewer read it
against a printed book. `tests/test_mantra_texts.py` asserts these pada counts against the built
files, so a change to a text that is not reflected here fails a test.

```
  text                           padas  srcs  read     release
  aarti-kunj-bihari-ki              47     1   yes  2026-11-17
  bajrang-baan                      72     1   yes  2026-11-16
  durga-chalisa                     87     2   yes  2026-11-11
  ganesh-aarti-jai-ganesh-deva      44     1   yes  2026-11-15
  ganesh-atharvashirsha            122     1   yes  2026-11-18
  ganesh-chalisa                    88     1   yes  2026-11-14
  gayatri-mantra                     4     1   yes  2026-11-13
  hanuman-aarti                     33     1   yes  2026-11-14
  hanuman-ashtak                    68     1   yes  2026-11-16
  hanuman-chalisa                   92     2   yes  2026-11-12
  jai-ambe-gauri                    66     1   yes  2026-11-12
  kanakadhara-stotram               89     1   yes  2026-11-18
  lalita-sahasranamam              674     1    no           -
  lingashtakam                      34     1   yes  2026-11-10
  mahamrityunjaya-mantra             4     1   yes  2026-11-11
  om-jai-jagdish-hare               59     1   yes  2026-11-13
  ram-raksha-stotra                101     2   yes  2026-11-17
  rudrashtakam                      34     2   yes  2026-11-09
  shani-chalisa                     86     1   yes  2026-11-15
  shiv-chalisa                      94     1   yes  2026-11-09
  shiv-tandav-stotram               35     2   yes  2026-11-10
  vishnu-sahasranamam              416     1    no           -
                                  2349 padas in all
```

"no second source" means the second source describes the text without printing it, so there was
nothing to compare - not that the two agreed.

## Review list

Every pada in source A with no match in source B, for the three texts where a comparison was
possible. A reader of Devanagari has to decide each one; most of the Ram Raksha entries are likely
a longer recension rather than a disagreement.

```

```

The full list, including the texts where no comparison was possible, is regenerated by the script
kept with the cached sources.

## Copyright, per text

Nothing in the batch has a plausible author still in copyright. The oldest are Vedic; the newest is
the Durga Chalisa, a 19th-century devotional composition of unrecorded authorship. Where the author
is genuinely unrecorded the registry says "Traditional, author unknown", which is a statement about
the record rather than a claim that nobody wrote it.

## What would unblock the rest

A source for the 16, which realistically means scans the proprietor trusts and a transcription pass
that is read by somebody who knows the texts. OCR alone is not usable here and was not used.

## A note on reading an index rather than guessing a URL

Three aartis were "missing" only because the slugs I guessed were wrong - `aarti/jai-ambe-gauri`
answers 302 to a 404 page while `aarti/jai-ambe-gauri-maiya-jai-shyama-gauri` is the text. Reading
the site's own index found all three in one request. The same mistake cost a pass on
sanskritdocuments and on stotranidhi before it; guessing a URL shape is not searching.

And a 200 is not a source: bhaktibharat answers 200 for Ganesh Chalisa and Shani Chalisa and serves
no Devanagari on either.

## The danda rule, and why it is gone

For most of this work a line had to contain a danda to count as verse. It was the only thing
separating text from navigation when whole pages were being read, and it cost three texts before it
was dropped:

* the **Gayatri Mantra** came out halved - its first two padas carry no danda;
* **Sankat Mochan Hanuman Ashtak** punctuates with commas, so 28 of its 55 padas vanished,
  including the opening बाल समय रवि भक्षी लियो तब;
* the **Hanuman Chalisa**'s opening dohas end in commas too, so श्रीगुरु चरन सरोज रज - the most
  recited line in the batch - was being dropped. That is how a count of 86 looked "exactly right"
  for a text whose real structure is 92: two opening dohas at four padas, forty chaupais at two,
  and a closing doha.

Reading from the container and skipping anchor text does the separating now, and does it without
throwing verse away.

## The keyword rule, as it now stands

A **ceiling of 2%** on the density of the text's own name in OUR written part - the explainer, not
the verses, which are the bulk of the page and are not ours to pad or trim. There is no floor.

The 1% floor was dropped on 2026-10-30, and it is worth recording why rather than just removing it.
Natural writing lands at 0.1% to 0.8%, so the floor forced a rewrite of all forty pages; the
rewrites then overshot to 3.6% about as often as they landed, and the batch ran roughly 23% over its
AI budget converging. And a one-word Hindi name at 1% of 1,500 words means saying it 15 to 30 times
- which is the repetition rate search engines now read as a signal against a page. The floor was
pushing the prose in the direction the ceiling exists to prevent.

The placement rules are unchanged and are what actually carries the keyword: the title, the H1, the
URL slug, the first hundred words, at least one H2, the meta description, and the alt text of any
content image. These pages carry no content image - the only `<img>` is the site's brand emblem,
whose alt is deliberately empty because it is decorative - so that last rule is asserted
conditionally and will fail the day a content image arrives without it.
