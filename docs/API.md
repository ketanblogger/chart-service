# Calculation API

All routes are pure Swiss Ephemeris math (sidereal, Lahiri ayanamsa, whole-sign houses, mean
Rahu/Ketu). No AI is called - except the paid report routes at the end of this file
([Paid AI reports](#paid-ai-reports)). Interactive schema: `/docs` on the running server.

| Route | Purpose |
|---|---|
| `POST /api/chart` | Full birth chart: lagna, grahas, houses, dasha, mangal dosha, sade-sati |
| `POST /api/chart?detail=full` | The same, plus `report`: navamsa, dignity, aspects, yogas, highlights, gemstone, dhaiya and the dated timeline |
| `POST /api/mangal-dosha` | Mangal dosha only |
| `POST /api/sade-sati` | Sade-sati only |
| `POST /api/matching` | Ashtakoota guna milan (36 points) + mangal dosha comparison |
| `GET /api/transits` | Current graha positions; optional houses from a rashi and events in a period |
| `GET /api/cities` | City list for the place dropdown |

Errors: invalid input returns **422** with FastAPI's usual `{"detail": ...}` body (unknown
city, missing place, bad date/time/timezone, unknown rashi, `end` before `at`).

## `accuracy` - how far to trust a chart

Every chart, including the free pages, carries an `accuracy` block. It is **data, never prose**: the
web and report layers write the wording in three languages. Both caveats exist only to be *true* -
a warning on a chart where nothing could have gone wrong is noise that trains people to skip the one
that matters, so each stays silent unless it applies. The place caveat fires on about 6% of charts,
the clock caveat on pre-1906 and 1942-45 births.

```json
"accuracy": {
  "lagna_boundary": {
    "degrees_into_sign": 28.288172,
    "arcminutes_to_boundary": 102.71,
    "nearer_boundary": "next",
    "adjacent_sign": {"index": 5, "key": "Leo", "name": "Simha", "…": "…"},
    "km_to_change_sign": 188.8,
    "threshold_km": 100.0,
    "sensitive": false,
    "basis": "Distance in the most sensitive direction, …"
  },
  "clock": {
    "timezone": "Asia/Kolkata", "timezone_kind": "zone",
    "offset": "+05:21:10", "offset_seconds": 19270,
    "zone_offset_today": "+05:30:00", "differs_from_zone_today": true,
    "non_standard": true,
    "era": "madras_time",
    "era_label": "Madras time - the railway standard, fixed by Goldingham in 1802",
    "basis": "The offset the birth time was actually converted on. …"
  }
}
```

### `lagna_boundary` - would a different birthplace have changed the rising sign?

The form only offers cities from a list, so a visitor born somewhere not on it picks the nearest one
that is. **The engine cannot detect that** - whatever city arrives looks like a deliberate choice.
What it can answer is whether it would have mattered, which is the useful half.

`km_to_change_sign` is how far the birthplace would have to be, **in the most sensitive direction**,
for the rising sign to change. It is measured per chart, not derived from a rule of thumb: the
ascendant is recomputed a quarter-degree east and a quarter-degree north and the local gradient is
read off. Longitude dominates (0.87-1.00 degrees of ascendant per degree of longitude across the
reference charts) and latitude contributes about a third as much, but the mix depends on the latitude
and on which sign is rising. A test walks the computed distance and checks the sign actually changes.

`sensitive` is the flag to render on. **`threshold_km` is 100**, grounded in the city list itself:
the 124 cities have a median nearest-neighbour distance of 81 km and a 90th percentile of 138 km, so
a visitor whose own town is missing is typically within ~40 km of a listed one and, in the sparser
parts of the country, within ~70 km. 100 km covers that with margin while staying well inside
implausible. Which coordinates were used is already in `input.lat` / `input.lon` / `input.city`.

### `clock` - which civil clock was the birth time recorded on?

India's civil time has moved four times and `zoneinfo` carries all four, so these charts are computed
correctly - but the recorded clock was not today's, and a reader comparing against another site
deserves to know which system applied. See the era table under **Historical Indian time** above.

`non_standard` is the flag. For a named zone it means the birth's offset differs from the one that
zone uses today; for an explicitly-passed fixed offset - which carries no history of its own - it
falls back to "is this India's current offset?", which is what makes a pre-1870 Porbandar birth at
+04:38 report as non-standard. `era` names the system when the offset is one of the four recognised
Indian ones and is **`null` rather than a guess** otherwise.

**The trigger is the offset, not the year.** A year-based test would catch 1906 and miss 1942-45 -
the wartime window, which is the one with living customers.

## Accuracy, and how it is proved

Every position comes from the Swiss Ephemeris with the Lahiri ayanamsa. The claim that those
positions are *right* is checked against charts anyone can look up, not against numbers this
codebase produced - a suite that pinned its own output would keep passing while the engine drifted.

The test suite is anchored on three public, published births, defined once in
`tests/reference_charts.py` with the source and the date it was fetched:

| | born | lagna | rashi | what it proves |
|---|---|---|---|---|
| Jawaharlal Nehru | 14 Nov 1889, 23:30, Allahabad | Karka | Karka | AstroSage prints sign and degree for all seven classical grahas (rated "Accurate (A)"); every one agrees to under 1.2 arc-minutes, and the ascendant to 7.6 |
| A. P. J. Abdul Kalam | 15 Oct 1931, 01:15, Rameswaram | Karka | Vrishchika | a published analysis states six things about this chart - ascendant, nakshatra, a debilitated Chandra in the 5th, an exalted Guru in the 1st ruling 6 and 9, an exalted Budha in the 3rd with Surya, Shani in the 6th ruling 7 and 8 - and all six hold |
| Swami Vivekananda | 12 Jan 1863, 06:33:33 LMT, Calcutta | Dhanu | Kanya | VedAstro's lagna, Moon sign, nakshatra and pada all agree exactly |
| Indira Gandhi | 19 Nov 1917, 23:11, Allahabad | Karka | Makara | the fullest table of the set - sign, degree, nakshatra and pada for all nine grahas, which are combust, which retrograde, **and the ascendant**: theirs Karka 27°29'48", ours Karka 27°30'04" |
| Mahatma Gandhi | 2 Oct 1869, 07:11:53 LMT, Porbandar | | | a source that publishes a whole **navamsa** - rare - and we reproduce all nine D9 positions |

**The ascendant is verified on two charts, and one of them taught us something.** Indira Gandhi's
agrees to sixteen arc-seconds, about one second of clock time. Nehru's agrees to 7.6 arc-minutes -
but only once both sides use the same clock, and getting that wrong is how this suite came to carry
a documented "disputed ascendant" that did not exist. See **Pre-IST births** below.

**Matching is anchored on a pair, not on two individuals.** Guna milan is a function of two charts,
so `tests/reference_charts.py` also defines `MATCH_PAIR` and `MATCH_PAIR_LOW`. No published
per-koota breakdown for a famous couple could be found, so the external half is each chart's own
published Moon nakshatra *and pada* - which is precisely what the 36 points are computed from - and
the score is a deterministic consequence of two independently verified inputs. The tests say which
half is external and which is derived. Neither pairing is a couple and none is implied; they are
chosen for what they exercise (a mid-range total with a zero-scoring koota and a bhakoot dosha; a
low total with a nadi dosha; mangal dosha on both sides of both).

### Historical Indian time, and a lesson about tolerances

**India's clock has moved four times, and `Asia/Kolkata` knows all four.** Pass the zone name and
the engine gets them for free; hardcode `+05:30` and it is wrong for three of the five eras:

| Birth falls in | `Asia/Kolkata` resolves to | what it was |
|---|---|---|
| before 1870 | **+05:53:20** | Calcutta local mean time |
| 1870 – 1905 | **+05:21:10** | Madras time, the railway standard, fixed by Goldingham in 1802 |
| 1906 – Aug 1942 | +05:30 | IST, adopted 1 January 1906 |
| **Sep 1942 – Oct 1945** | **+06:30** | wartime: India ran an hour ahead |
| 1946 onwards | +05:30 | IST |

**The wartime row is the one with living customers.** Someone born in 1944 is in their eighties, and
their chart gets computed the moment a customer orders one for a parent. An hour is fifteen degrees
of ascendant - half a sign to a sign and a half. The pre-1906 rows touch only ancestors' charts.

**A limit of the zone name, before 1870.** `Asia/Kolkata` in that era is *Calcutta's* local mean
time, not a national standard - so it is right for Bengal and wrong further west, by 75 minutes for
Porbandar in Gujarat, which moves Gandhi's ascendant a full sign (Tula to Kanya). This is a property
of the named zone, not of our fixtures: for any pre-1870 birth outside Bengal the birthplace's own
longitude-derived offset is the correct input and the zone name is not sufficient. The two pre-1870
reference charts store explicit offsets for that reason. The same caveat is on `parse_tz` in
`app/engine/core.py`, where a caller would actually meet it.

### An open product decision: pre-1906 births (NOT yet decided)

**What this engine does today.** A user entering a pre-1906 Indian birth through the site picks a
city, the city carries `Asia/Kolkata`, and the chart is cast on the era's real offset - Madras time
for an 1889 birth. Nothing here needs changing for that to happen; it is what naming a zone gets you.

**What that means against other sites,** checked 2026-09-22 rather than assumed:

| source | stated convention for a pre-1906 birth | Nehru's ascendant |
|---|---|---|
| **this engine** | the era's offset, via `zoneinfo` (+05:21:10 for 1889) | **Simha 0°13'41"** |
| Lagna360 | Madras time, stated explicitly: *"11:30 PM Madras time (-5h 21m from Greenwich) is equal to 11:36 PM LMT"* | **Leo - agrees with us** |
| VedAstro | local mean time (publishes an 1863 chart at `+05:53`) | same principle |
| [freeastroapi guide](https://www.freeastroapi.com/guide/timezones-and-lmt) | *"Calculating a chart for 1890 using modern 'Asia/Kolkata' (+05:30) time would be incorrect. You must use LMT."* | same principle |
| AstroSage | modern IST applied retroactively ("Time Zone: 5.5" on an 1889 chart) | Karka 28°24'55" |

Lagna360's arithmetic checks out against ours to the minute: Allahabad's own longitude gives
+05:27:23, which is 6.2 minutes after Madras time - exactly the "11:30 → 11:36" they print - and the
instant, and therefore the ascendant, is the same one we compute.

**So the premise that we would stand alone is wrong.** Three of the four sources checked - including
the only one that shows its working, and the only one offering explicit guidance - do what we do.
AstroSage is the outlier. But it is a *popular* outlier, and that is the whole of the problem.

**What a customer would actually see.** For a pre-1906 birth near a sign cusp, our lagna and
AstroSage's differ by a sign, and every house statement in the report moves with it. A customer who
checks our report against the most popular free site in the market sees a different ascendant and has
no way to tell which is right. Note the blast radius is wider than the lagna: on Nehru's chart the
same nine minutes changed the mangal dosha verdict from "medium, on two counts" to "low, on one" - a
timezone convention propagating into what reads as our opinion about someone's marriage.

**The two options, neither implemented:**
1. **Stay historically correct** and say so in the report's limitations: that births before 1906 are
   cast on the time actually in use, that some sites apply modern IST retroactively, and that this is
   why the charts differ. Costs an explanation; keeps the accuracy claim literally true.
2. **Follow the popular convention** for pre-1906 births and note that we do. Costs the accuracy
   claim for those charts; removes the support burden.

Practical stakes: the 1906 cutoff means no living customer's own chart is affected - it is ancestors'
charts and our own fixtures. The 1942-1945 wartime row above is the one that reaches living people,
and it is not in dispute.

### A note on tolerances, kept because it cost us

When a test documents a disagreement with an external source, check we computed it the same way they
did before reaching for a domain explanation - a convention mismatch is likelier, and it is the
explanation that does not flatter us.

This suite carried a documented "disputed ascendant" for Nehru for some time. There was no dispute:
our fixture named `Asia/Kolkata` while its own comment claimed the `+05:30` the source had used, and
the 8m50s between the two moved the ascendant across a sign boundary. A paragraph was written
explaining the disagreement, and a second authority was cited in support of it - which is what a
careful person does, and is exactly why it survived three reviews. What let it live was the
tolerance: the graha comparison allowed 4.2 arc-minutes and the Moon's error from the clock shift
was 4.0, just inside. **A tolerance wide enough to absorb a whole timezone convention has stopped
testing the ephemeris.** It is 1.2 arc-minutes now.

And its companion, which cost a separate afternoon:

**A claim that confirms the lesson you just learned gets less scrutiny, not more.**

Chasing the above, someone reasoned that a city entry would silently substitute IST for a
local-mean-time birth and shift a chart by 23 minutes. It was specific, alarming, and wrong - the
timezone database handles historical India correctly and `ZoneInfo("Asia/Kolkata")` resolves an 1863
birth to +05:53:20. Three people passed the claim along, with emphasis added, without once calling
`utcoffset()`. Nobody was being lazy. The claim *matched a pattern everyone had just been burned by*,
and pattern-matching felt like diligence. That is more dangerous than an ordinary unchecked
assumption, because it arrives wearing the costume of the thing you just got right - and it is most
likely to land on the day you feel sharpest. The ten-second check is cheapest exactly when the
conclusion already looks obvious.

(The instinct was not worthless: the same mechanism turned out to be real on a *different* chart,
where a named zone and a stored offset genuinely differ by 8m50s and change the ascendant's sign.
The error was generalising from one chart to a class, which is the failure mode underneath both of
these notes.)

One limitation worth stating: `tzdata` models the legal zone, and Calcutta and Bombay in fact kept
their own local time well past 1906 (Calcutta until 1948, Bombay until 1955). For a 1906-1948
Calcutta birth there is therefore real uncertainty about which clock the recorded time was on, and
no software can resolve it from the birth details alone.

That property is also how a phantom disagreement got into this suite. The Nehru reference named
`Asia/Kolkata` - correctly resolving to Madras time - while its own comment claimed it used the
+05:30 the source had applied. The 8m50s between the two conventions moved the ascendant from Karka
28°17' to Simha 0°13', across a sign boundary, and a long note was written explaining the
"dispute" between us and the source. There was none: on the source's own clock the ascendant agrees
to 7.6 arc-minutes.

**What let it survive was the tolerance.** The graha comparison allowed 4.2 arc-minutes, and the
Moon's error from an 8m50s clock shift is 4.0 - just inside. A tolerance wide enough to absorb a
whole timezone convention had stopped testing the ephemeris. It is now 1.2 arc-minutes, which the
correct chart passes with room and the wrong one cannot.

**Disagreements are recorded, not hidden.** Where a source genuinely differs, the test says so and
names their value rather than widening a bound until it fits. Gandhi's D9 ascendant differs from
ours (his minute of birth really is disputed, and the ascendant is the only quantity sensitive to
it); all nine of his grahas agree.
VedAstro also puts Vivekananda's Surya in Makara against our Dhanu 29°25': that page states it uses
the **Raman** ayanamsa, which is about 1.1° smaller than Lahiri, and Surya falls inside the 1.1° gap
between the two. One chart, two ayanamsas. That case is kept deliberately - it is the clearest
demonstration in the suite that the Lahiri choice is a real one. On Indira Gandhi's chart, Guru and
Shani - the slow outer grahas, where ephemerides differ most - are 2.1' and 6.2' from the published
degrees while the other seven agree to under an arc-minute; Shani moves about 2' a day, so 6' cannot
be a birth-time difference. The tests assert those two separately rather than widening one tolerance
until everything fits.

### Measure a filter's rejects, not its output

The same lesson in a different costume, and the more expensive half is that the *measurement* was
wrong rather than the code.

Before the `dignity` rule was made blocking, we set out to price its false positives honestly: run it
over every report a human had already read and accepted, and count the findings. It returned one
finding across 1,366 text slots, and that one was a genuine error. Nearly a perfect record - except
the number was meaningless. **A false positive is exactly what fails a draft and forces the
regeneration that replaces it**, so it can never appear in accepted output. Zero was the only answer
that measurement could have produced, whatever the true rate was. It is the reject rate of a filter,
measured by examining what came through it.

The findings live in the **rejected drafts**, which is why `meta.checks.rejected_drafts` is kept. Over
34 of them the rule had 7 findings: 4 true and 3 false. All three false ones were the same sentence
shape - "Guru returns to **your own sign**", a claim about the reader's lagna being read as a claim
about the graha - and fixing that one subject-identification bug took the false count to zero and let
the rule be promoted. Measured the first way, we would have promoted a rule with a known 43%
false-positive rate on its own findings and called it evidence-led.

So: when a check's cost is being judged, look at what it *rejected*. Its output has been filtered by
the very behaviour under examination.

Engine-generated values appear in the suite too, but only as **regression pins** for feature coverage
(that a yoga list keeps its shape, that a timeline stays contiguous, that a ranking keeps choosing the
same three factors). Those say so where they are asserted, because a pin proves nothing about accuracy.

The running service checks itself the same way: `/health/ready` calls `engine.self_check()`, which
recomputes Nehru's chart and verifies the Sun's sign, the Moon's sign, the janma nakshatra and that
the `.se1` data files answered. It deliberately does **not** assert the lagna - see
`app/engine/reference.py`.

`app/engine/cities.py` lists ~124 Indian cities for the place dropdown. That is public geography and
has nothing to do with the charts above.

## Shared objects

Every sign, nakshatra and graha is returned as an object, so pages can render any language:

```json
{"index": 4, "key": "Cancer", "name": "Karka", "devanagari": "कर्क", "slug": "karka", "lord": "Moon"}
{"index": 17, "key": "Anuradha", "name": "Anuradha", "devanagari": "अनुराधा", "lord": "Saturn"}
{"key": "Moon", "name": "Chandra", "devanagari": "चंद्र"}
```

- sign `index` 1–12 (1 = Aries/Mesha); `key` English, `name` Sanskrit, `slug` = rashifal URL part.
- nakshatra `index` 1–27 (1 = Ashwini); `lord` = Vimshottari lord.
- graha keys, always in this order: `Sun Moon Mars Mercury Jupiter Venus Saturn Rahu Ketu`.

A **position** (used for the lagna, every graha, and transits):

```json
{
  "graha": {"key": "Moon", "name": "Chandra", "devanagari": "चंद्र"},
  "longitude": 262.589547,
  "sign": {"index": 9, "key": "Sagittarius", "name": "Dhanu", "devanagari": "धनु", "slug": "dhanu", "lord": "Jupiter"},
  "degree": 22.589547,
  "degree_dms": "22°35'22\"",
  "nakshatra": {"index": 20, "key": "Purvashadha", "name": "Purvashadha", "devanagari": "पूर्वाषाढा", "lord": "Venus"},
  "pada": 3,
  "house": 5,
  "retrograde": false,
  "speed": 14.107419
}
```

`longitude` is sidereal 0–360, `degree` is within the sign, `speed` is degrees/day. The lagna
has no `graha`, `house`, `retrograde` or `speed`. In transits `house` appears only when a
`rashi` is given.

## Birth details (request body of all POST routes)

```json
{"date": "1889-11-14", "time": "23:30", "city": "Allahabad"}
{"date": "1931-10-15", "time": "01:15:00", "lat": 9.2881, "lon": 79.3129, "timezone": "+05:30"}
```

| Field | Notes |
|---|---|
| `date` | `YYYY-MM-DD`, required |
| `time` | `HH:MM` or `HH:MM:SS`, local clock time at the birth place, required |
| `city` | A name from `GET /api/cities`. Case-insensitive; old names work too (`Belgaum`, `Aurangabad`, `Mysore`) |
| `lat`, `lon` | Decimal degrees, north/east positive. Give both. If present they win over `city` |
| `timezone` | IANA name (`Asia/Kolkata`) or UTC offset (`+05:30`). Default: the city's timezone, else `Asia/Kolkata` |

Either `city` or `lat` + `lon` is required.

## POST /api/chart

Request: birth details. Response — the worked example throughout this document is **A. P. J. Abdul
Kalam, 15 Oct 1931, 01:15, Rameswaram**, a public birth whose published analysis this engine
reproduces on every point it states (see `tests/reference_charts.py`). Abridged where marked `…`:

```json
{
  "input": {"date": "1931-10-15", "time": "01:15:00", "lat": 9.2881, "lon": 79.3129,
            "timezone": "Asia/Kolkata", "datetime_utc": "1931-10-14T19:45:00+00:00", "city": null},
  "meta": {"zodiac": "sidereal", "ayanamsa": {"name": "Lahiri", "degrees": 22.904342},
           "house_system": "whole_sign", "lunar_node": "mean", "ephemeris": "swiss_ephemeris"},
  "lagna": {"longitude": 105.68778, "sign": {"index": 4, "key": "Cancer", "name": "Karka", "…": "…"},
            "degree": 15.68778, "degree_dms": "15°41'16\"",
            "nakshatra": {"index": 8, "key": "Pushya", "…": "…"}, "pada": 4},
  "grahas": {
    "Sun": {"graha": {"key": "Sun", "name": "Surya", "devanagari": "सूर्य"}, "longitude": 177.594091,
            "sign": {"index": 6, "key": "Virgo", "name": "Kanya", "…": "…"},
            "degree": 27.594091, "degree_dms": "27°35'38\"",
            "nakshatra": {"index": 14, "key": "Chitra", "…": "…"}, "pada": 2, "house": 3,
            "retrograde": false, "speed": 0.991295, "combust": null, "dignity": "neutral_sign"},
    "…": "… 9 keys in fixed order, Sun to Ketu"},
  "moon_rashi": {"index": 8, "key": "Scorpio", "name": "Vrishchika", "devanagari": "वृश्चिक", "slug": "vrishchika", "lord": "Mars"},
  "janma_nakshatra": {"index": 17, "key": "Anuradha", "name": "Anuradha",
                      "devanagari": "अनुराधा", "lord": "Saturn", "pada": 3},
  "houses": [
    {"house": 1, "sign": {"index": 4, "key": "Cancer", "…": "…"}, "grahas": ["Jupiter"]},
    {"house": 3, "sign": {"index": 6, "key": "Virgo", "…": "…"}, "grahas": ["Sun", "Mercury", "Ketu"]}
  ],
  "dasha": {"…": "see below"},
  "mangal_dosha": {"…": "see POST /api/mangal-dosha"},
  "sade_sati": {"…": "see POST /api/sade-sati"}
}
```

`houses` always has 12 entries (house 1 = lagna sign) — enough to draw a North or South
Indian chart. `meta.ephemeris` is `"moshier"` only for dates outside 1800–2399 CE.

Each graha row carries, besides its position: `house` (from the lagna), `retrograde`, `speed`, and

| Field | Values |
|---|---|
| `combust` | `true` / `false`, and **`null` for Surya, Rahu and Ketu**, where the rule does not apply |
| `dignity` | `exalted` \| `moolatrikona` \| `own_sign` \| `friendly_sign` \| `neutral_sign` \| `enemy_sign` \| `debilitated`, and **`null` for Rahu and Ketu**, whose exaltation is disputed between authorities, so the engine asserts none |

Both are plain lookups once the Sun's longitude is known, both are printed in the report's planet
table (the book's chart-basics part), and both also appear on `GET /api/transits` rows. The full working - which orb,
which arc, which precedence - is in `report.dignity` when the chart is computed with `detail=full`,
and the reasoning is in `app/engine/dignity.py`.

### `dasha` (Vimshottari)

```json
{
  "system": "Vimshottari",
  "year_length_days": 365.25,
  "balance_at_birth": {"lord": {"key": "Saturn", "name": "Shani", "devanagari": "शनि"},
                       "years": 5, "months": 2, "days": 5, "decimal_years": 5.1811},
  "as_of": "2026-09-22",
  "cycles_to_reach_as_of": 1,
  "current": {
    "mahadasha": {"level": "mahadasha", "lord": {"key": "Jupiter", "…": "…"}, "start": "2021-12-19", "end": "2037-12-19"},
    "antardasha": {"lord": {"key": "Mercury", "…": "…"}, "start": "2026-08-20", "end": "2028-11-25"}
  },
  "mahadashas": [
    {"lord": {"key": "Saturn", "…": "…"}, "years": 19, "start": "1917-12-19", "end": "1936-12-19",
     "antardashas": [{"lord": {"key": "Rahu", "…": "…"}, "start": "1931-08-02", "end": "1934-06-08"}, "…"]},
    "… 9 mahadashas, 120 years, contiguous"
  ]
}
```

The first mahadasha's `start` is its theoretical start (before birth); antardashas that ended
before birth are omitted. Dates are in the birth timezone. `current` is evaluated at request time.

**Past 120 years.** The nine mahadashas total 120 years, which the texts take as a full lifespan, but
the sequence is periodic and simply begins again - which is what practitioners do for the rare chart
that outlives one round. `mahadashas` therefore always has exactly nine entries (that list *is* the
classical table), while `current` is answered from the extended sequence and carries
`"cycle": 2` plus a note saying the sequence has begun again. `cycles_to_reach_as_of` is 1 for any
ordinary chart. Before this, a chart older than 120 years produced no current dasha at all and the
timeline builder raised `TypeError` on it.

## POST /api/chart?detail=full - report facts

`detail=full` adds **exactly one key**, `report`, to the chart above; nothing else changes, so the
free pages can keep calling the default. It is every fact the flagship Kundali report needs
(the two-layer rule: the engine computes all facts, the AI only interprets). No AI, no
network, ~0.6 s and ~390 KB of JSON for the reference chart, and **deterministic** - the same chart
and the same `as_of` always produce the same bytes.

| Query | Notes |
|---|---|
| `detail` | `basic` (default) or `full` |
| `as_of` | ISO datetime; the moment the current dasha, sade-sati, dhaiya and the timeline are evaluated for. Default now; without an offset it is read as IST |

```
POST /api/chart?detail=full&as_of=2026-09-21T00:00:00%2B05:30
```

From Python: `compute_chart(..., detail="full")`, or `report_facts(chart, as_of=None,
timeline_knobs=None)` on a chart you already have.

```json
{"…the basic chart…": "",
 "report": {"as_of": "2026-09-21T00:00:00+00:00",
            "navamsa": {}, "dignity": {}, "aspects": {}, "yogas": [],
            "highlights": {}, "gemstone": {}, "dhaiya": {}, "timeline": {}}}
```

### The two conventions that hold everywhere in `report`
**One canonical date range, pre-formatted in all three languages.** Every dated thing in
`report.timeline` and every dated factor in `report.highlights` uses this exact object and no other:

```json
{"start": "2026-10-03", "end": "2026-10-27",
 "label": "3 – 26 Oct 2026",
 "labels": {"en": "3 – 26 Oct 2026", "hi": "3 – 26 अक्टूबर 2026", "mr": "3 – 26 ऑक्टोबर 2026"},
 "precision": "day", "start_ym": "2026-10", "end_ym": "2026-10", "days": 24}
```

**Interval convention, stated once and true everywhere in the engine: the range is HALF-OPEN.**
`start` is included, `end` is **exclusive** and is the same day the next window begins, so
`windows[i].end == windows[i+1].start` exactly. The labels and `end_ym` name the last day/month
actually *covered* (`end` minus one day), so a window ending 1 Oct reads `"... Sep 2026"`, never
`"... Oct 2026"`. The same sentence is in `report.timeline.interval` at runtime.

**The engine owns date formatting for the whole platform.** The AI never writes a date - it names a
window `id` and the renderer prints `labels[language]`, so the same range is byte-identical in the
book, the tables and the debug markdown. Rules:

- `label` is the English string (unchanged since the first contract); `labels` carries `en`/`hi`/`mr`.
- English uses short month names; Hindi and Marathi use that language's own full month names
  (Marathi is Marathi, not Hindi: `सप्टेंबर` vs `सितंबर`). Years and days are **Latin digits** in all three.
- The separator is an en dash with spaces - the one canonical separator every printed range uses.
- `precision` is `"month"` when the range is 45 days or longer, or when it covers whole calendar
  months exactly (starts on a 1st and ends on a 1st); `"day"` otherwise. A three-week
  pratyantardasha window printed as `"Oct 2026"` would be both wrong and, next to its neighbour,
  ambiguous.
- Label forms, shortest unambiguous one wins: `"Jan 2026"`, `"Jan 2026 – Mar 2026"`, `"3 Oct 2026"`,
  `"3 – 26 Oct 2026"`, `"3 Oct – 14 Nov 2026"`, `"20 Dec 2026 – 9 Jan 2027"`.
- **No two windows of one timeline ever share a label**, in any language. That falls out of the
  precision rule and is asserted in the tests, so a heading can never be printed twice.

Never an age band, never a decade: the timeline is dated. `engine.date_range(d1, d2)` builds one if you need
another, and `engine.format_range(start, last_day, language, precision)` formats one by hand. The
canonical month table is `app.engine.constants.MONTHS` - `app/pdf/labels.py`, `app/rashifal/i18n.py`
and `app/ai/engine_facts.py` each still carry a copy and should read this one instead.

**House counts are always named.** There is no bare `house` key anywhere in `report.timeline` or
`report.highlights`. Every graha mentioned carries `house_from_lagna` **and** `house_from_moon`, and
navamsa placements carry `house_from_navamsa_lagna`. (`report.navamsa.grahas[*].house` is counted
from the navamsa lagna and is repeated as `house_from_navamsa_lagna` for exactly that reason.) A
house counted from the Moon can therefore never be written up as "your Nth house".

### `report.navamsa` - D9 (chart basics)

```json
{"division": "D9 (Navamsa), Parashari: 3°20' parts, movable from the sign, fixed from the 9th, dual from the 5th",
 "lagna": {"sign": {"index": 8, "key": "Scorpio", "name": "Vrishchika", "…": "…"}, "navamsa": 8,
           "d1_sign_nature": "fixed", "vargottama": false, "house": 1, "house_from_navamsa_lagna": 1},
 "grahas": {"Sun": {"sign": {"index": 6, "name": "Kanya", "…": "…"}, "navamsa": 9,
                    "d1_sign_nature": "dual", "vargottama": true, "house": 11,
                    "house_from_navamsa_lagna": 11, "graha": {"key": "Sun", "…": "…"},
                    "d1_sign": {"index": 6, "name": "Kanya", "…": "…"}, "retrograde": false},
            "…": "… 9 keys"},
 "houses": [{"house": 1, "sign": {"…": "…"}, "grahas": []}, "… 12 entries, for the D9 renderer"],
 "vargottama": ["Sun"], "lagna_vargottama": false}
```

`navamsa` is 1–9, which of the sign's nine 3°20' parts the graha falls in. `vargottama` = same sign
in D1 and D9. Verified against two published charts - see the module docstring in
`app/engine/varga.py` and `tests/test_varga.py`.

**The shape is deliberately the D1 chart's shape** - `lagna`, `grahas` keyed by graha with
`sign` / `house` / `retrograde`, and `houses` as a 12-entry list of `{house, sign, grahas}` - so the
renderer that draws the rashi chart draws this one unchanged. `retrograde` is copied from D1
(retrogression is a fact about the graha, not about the division). There is deliberately **no
`degree`**: a "degree within the navamsa sign" is not a quantity the classical texts use, and
inventing one would only invite it onto the page. `house` is counted from the **navamsa** lagna and
is repeated as `house_from_navamsa_lagna`. `engine.navamsa(chart)` is an alias for
`engine.navamsa_chart(chart)`.

### `report.dignity` - combustion and dignity (the chart-basics planet table)

Keyed by graha. This **extends** the `lordships` block `app/ai/compact.py` builds; `rules_houses`,
`in_own_sign` and `sign_lord` mean exactly what they did there.

```json
{"Saturn": {
   "graha": {"key": "Saturn", "name": "Shani", "devanagari": "शनि"},
   "sign": {"index": 11, "name": "Kumbha", "…": "…"}, "degree": 20.178531,
   "house_from_lagna": 7, "retrograde": false,
   "rules_houses": [6, 7], "in_own_sign": true, "sign_lord": "Saturn",
   "dignity": {"label": "own_sign", "score": 3, "reason": "in its own sign Kumbha",
               "dispositor": "Saturn", "exact_exaltation_degrees_away": null},
   "combustion": {"applicable": true, "combust": true, "deeply_combust": false,
                  "separation_degrees": 7.4742, "orb_degrees": 15.0,
                  "retrograde_orb_used": false, "rule": "Longitude difference from the Sun below …"},
   "natural_class": {"class": "malefic", "reason": "natural malefic"}}}
```

- `dignity.label`: `exalted` | `moolatrikona` | `own_sign` | `friendly_sign` | `neutral_sign` |
  `enemy_sign` | `debilitated`, **or `null` for Rahu and Ketu** - their exaltation is disputed
  between authorities, so the engine asserts none and `reason` says why. The AI must not claim one.
- `combustion.combust` is **`null` for Sun, Rahu and Ketu** (`applicable: false`).
- Orbs: Moon 12°, Mars 17°, Mercury 14° (12° retrograde), Jupiter 11°, Venus 10° (8° retrograde),
  Saturn 15°. `deeply_combust` = within 1°.
- `natural_class.class` is `"variable"` for Mercury, and for the Moon depends on how bright it is
  (36°–216° of elongation from the Sun = the bright fortnight = benefic).

### `report.aspects` - graha drishti

Keyed by graha, plus a `rule` string. Whole-sign: everything aspects the 7th; Mars also the 4th and
8th, Jupiter the 5th and 9th, Saturn the 3rd and 10th.

```json
{"Jupiter": {"graha": {"…": "…"}, "aspects_from_own_sign": [5, 7, 9],
             "aspected_signs": [{"…sign…": ""}], "aspected_houses_from_lagna": [4, 8, 12],
             "aspects_grahas": ["Mars"], "disputed": false},
 "Rahu": {"…": "…", "disputed": true, "note": "The nodes' drishti is disputed: …"},
 "rule": "Whole-sign drishti: every graha aspects the 7th sign from itself; …"}
```

Rahu and Ketu get the 5/7/9 set but are flagged `disputed`; **no yoga in this engine is ever
triggered by a nodal aspect**.

### `report.yogas` - list, empty when none apply (highlight card 7, and the remedies part)

```json
[{"key": "mahapurusha_sasa", "name": "Sasa Yoga", "devanagari": "शश योग",
  "category": "mahapurusha", "nature": "benefic", "strength": "moderate",
  "rule": "One of the Pancha Mahapurusha yogas: the graha is in its own sign (or moolatrikona) or exaltation sign AND in a kendra (1/4/7/10) from the lagna",
  "combination": "Shani is own sign in Kumbha, in house 7 from the lagna",
  "grahas": [{"key": "Saturn", "name": "Shani", "devanagari": "शनि", "sign": {"…": "…"},
              "house_from_lagna": 7, "house_from_moon": 3, "rules_houses": [6, 7],
              "dignity": "own_sign", "combust": true}],
  "houses": [7], "dignity": "own_sign", "also_kendra_from_moon": false}]
```

- `rule` is the definition **this engine uses** - print it or paraphrase it, never substitute another.
- `combination` is the placement in THIS chart that satisfied it. `strength` is `strong` |
  `moderate` | `mild`; any participating graha that is debilitated or combust drops it one step.
- Sorted strongest-and-most-auspicious first.
- Extra keys per yoga: `association` (Raj/Dhana), `conditions_met` + `cancellation_conditions`
  (Neecha Bhanga, Pitra dosha), `cancellations` + `cancellations_met` (Kemadruma),
  `in_own_dusthana` + `also_rules` + `caution` (Vipreeta), `kind`/`arc`/`type`/`grahas_on_axis`
  (Kaal Sarp), `kind` (Parivartana), `framing` on the challenging ones.
- **`framing` must reach the prompt.** It is the safety wording for that yoga (e.g. Kaal Sarp:
  "never as a curse, never as danger"; Pitra dosha: "no blame, no fear, never a claim about any
  living relative").
- Detected: Raj, Yogakaraka, Dhana, Gajakesari, Budhaditya, Chandra-Mangal, the five Pancha
  Mahapurusha (Ruchaka/Bhadra/Hamsa/Malavya/Sasa), Neecha Bhanga, the three Vipreeta
  (Harsha/Sarala/Vimala), Kemadruma, Shakata, Kaal Sarp (with its 12 traditional type names),
  Pitra dosha, and the three Parivartana (Maha/Khala/Dainya). Reference chart: Neecha Bhanga Raja
  Yoga, Sasa Yoga, Raj Yoga, Yogakaraka, Dhana Yoga, Pitra Dosha.
- Where authorities disagree, the chosen definition is named in `rule` and argued in the docstring
  of `app/engine/yogas.py`. Pitra dosha in particular uses **one** of several published definitions
  and says so in `definition_note`.

### `report.highlights` - the top three of each (highlight cards 5 and 6: strengths and cautions)

```json
{"method": "Deterministic scoring over computed facts only; …", "weights": {"…": "…"},
 "safety": "Constructive framing only. Never death, never serious illness, …",
 "health_framing": "Health-related: write it strictly as TIMING AND LIFESTYLE …",
 "top_strengths": [{"…factor…": ""}], "top_cautions": [{"…factor…": ""}],
 "all_strengths": [], "all_cautions": []}
```

A factor:

```json
{"key": "dhaiya:fourth", "kind": "caution", "score": 5,
 "title": "Shani dhaiya is running (fourth from the Moon sign)",
 "reason": "Shani is in Meena, house 4 from the Moon sign, from 2025-03-29 to 2027-06-03",
 "houses": [4], "life_areas": ["home", "mother", "property", "vehicle", "peace of mind"],
 "pillars": ["education", "family_property"],
 "grahas": [{"key": "Saturn", "…": "…", "house_from_lagna": 7, "house_from_moon": 3, "…": "…"}],
 "frame": "timing",
 "evidence": {"modifiers": ["dhaiya fourth"], "period": {"…date range…": ""}},
 "safety": "Constructive framing only. …", "health_related": true,
 "framing": "Health-related: write it strictly as TIMING AND LIFESTYLE …"}
```

- Sorted `(-score, key)`; keys are unique, so the order is total and the same chart always yields
  the same three. `top_*` is the first ≤3 of `all_*` and may be shorter on a plain chart.
- `frame`: `timing` | `lifestyle` | `effort` | `opportunity`.
- **Cautions only:** `safety` (always) and `health_related`. `framing` is present **if and only if**
  `health_related` is true, and it is the instruction to write the point as timing and lifestyle -
  never a condition, never a severity, never anything medical.
- A debilitation that a Neecha Bhanga cancels appears under strengths as the yoga, and is *not*
  repeated as a caution.
- Scoring inputs: benefic/challenging yogas, graha dignity, vargottama, the lagna lord's placement,
  benefics in kendra/trikona, Mangal dosha, sade-sati and dhaiya, lords of the 1st/2nd/7th/11th in
  dusthanas, combustion, and whether the mahadasha/antardasha running NOW is well placed or damaged
  (the "dasha relevance" term). The full weight table is in `weights` and in
  `app/engine/highlights.py`.

### `report.gemstone` (the remedies part)

```json
{"rule_set": "Lagna-lord ratna rule: life stone from the lagna lord, fortune stone from the 9th lord, …",
 "presentation": "Traditional faith-based practice. Present as what tradition suggests, always optional, … never as a purchase instruction …",
 "wearing_note": "Tradition has a stone set in the named metal and first worn on the named weekday, …",
 "lagna": {"index": 4, "name": "Karka", "…": "…"},
 "primary": {"role": "life_stone", "role_description": "Life stone (jeevan ratna) - the lagna lord's gemstone",
             "graha": {"key": "Moon", "name": "Chandra", "devanagari": "चंद्र"},
             "stone": "Pearl", "sanskrit": "Mukta / Moti", "devanagari": "मोती",
             "metal": "silver", "finger": "little finger", "day": "Monday",
             "weight": {"ratti": [4, 6], "carats": [3.64, 5.46], "guidance": "4-6 ratti (3.64-5.46 carats), the classical range; a practitioner fixes the exact weight"},
             "mantra": "ॐ श्रां श्रीं श्रौं सः चन्द्राय नमः", "substitute": null,
             "because": "Chandra rules house 1 (Karka) in this chart"},
 "recommended": ["… primary, then the 9th lord's, then the 5th lord's …"],
 "avoid": [{"graha": {"key": "Saturn", "…": "…"}, "stone": "Blue Sapphire", "sanskrit": "Neelam",
            "devanagari": "नीलम", "because": "Shani rules house 8 (Kumbha), one of the difficult houses, and rules none of the 1st, 5th or 9th"}],
 "precedence_applied": [{"graha": {"key": "Jupiter", "…": "…"}, "dusthana": 6, "also_rules": [9], "note": "…"}],
 "not_selected_by_this_rule": {"grahas": ["Rahu", "Ketu"], "reason": "Rahu and Ketu own no sign, …"}}
```

Reference chart (Karka lagna): recommend Pearl, Yellow Sapphire, Red Coral; avoid Blue Sapphire and
Emerald. Guru rules both the 9th and the 6th, so the favourable lordship wins and Pukhraj is
recommended rather than avoided - that is what `precedence_applied` records.
`substitute` is non-null only for Diamond. **`presentation` must reach the prompt**: this is data
about traditional practice, not an instruction to buy anything.

### `report.dhaiya`

The companion to `chart["sade_sati"]`: Shani transiting the 4th or 8th from the Moon sign.

```json
{"active": true, "kind": "fourth", "saturn_sign": {"index": 12, "name": "Meena", "…": "…"},
 "saturn_house_from_moon": 4, "period": {"start": "2025-03-29", "end": "2027-06-03"}}
```

`kind` is `"fourth"` | `"eighth"` | `null`; `period` is `null` when inactive.

### `report.timeline` - the dated window list (the life timeline, and the year table)

```json
{"as_of": "2026-09-21", "today_boundary": "2026-09-01",
 "date_range_format": "…", "house_convention": "…",
 "knobs": {"current_year_max_windows": 24, "…": "…"},
 "coverage": {"past": {"…range…": ""}, "current_year": {"…range…": ""},
              "near_years": {"…range…": ""}, "far_years": {"…range…": ""},
              "dasha_cycle_ends": "2101-04-09"},
 "past": {"…D1…": ""},
 "current_year": {"…D2 section…": ""},
 "near_years": ["…4 D3 sections…"],
 "far_blocks": ["…D4 sections…"],
 "windows": ["…the flat list…"], "window_count": 45,
 "year_table": ["…one row per calendar year of D2+D3…"]}
```

**`windows` is THE list the report is written against.** Flat, sorted, and **contiguous**:
`windows[i].range.end == windows[i+1].range.start`, from `coverage.current_year.start` through the
end of the last far block. The sections do **not** repeat the objects - each carries
`window_indexes: [int]` **and** `window_ids: [str]` into `windows`, and each window carries its
`section` label back.

**Every window has a stable, self-checking `id`**: `"w-" + range.start`, e.g. `"w-2026-10-03"`
(past entries are `"p-" + range.start`). This is the only handle the AI ever gets on time - it names
an id, never a date, and the renderer fills in `labels[language]` afterwards. Because the id *is*
the window's start date, `id == "w-" + range["start"]` always holds, so a made-up id is almost never
a real one and a mismatched one is caught by checking it against the window it was attached to. That
is what a bare index cannot do: an off-by-one there silently attaches text to the wrong period,
which in a paid report means a wrong prediction against a wrong date. Ids are unique within a
report and stable for a given chart and `as_of`.

Section layout, exactly contiguous from birth:

| Section | Covers | Split by |
|---|---|---|
| `past` (D1) | birth → `today_boundary` (the 1st of the `as_of` month) | mahadasha changes only, no transits |
| `current_year` (D2) | `today_boundary` → a 1 January | antardasha **and** pratyantardasha boundaries, merged with month-level transits |
| `near_years` (D3) | 4 whole calendar years | antardasha shifts; 2–4 windows per year, none over 200 days |
| `far_blocks` (D4) | 5-year blocks | mahadasha/antardasha changes; still dated sub-ranges, none over 730 days |

D2 runs to the next 1 January unless less than `current_year_min_months` (6) remains, in which case
it runs to the one after - so a report bought on 20 December never gets an 11-day "current year".
Everything after D2 is whole calendar years, which is what makes the Part G table line up. The strip
is clamped to `coverage.dasha_cycle_ends`, so an older chart simply gets fewer far blocks and
`coverage.far_years` is `null`.

A window:

```json
{"id": "w-2026-10-03", "section": "current_year",
 "range": {"start": "2026-10-03", "end": "2026-10-27", "label": "3 – 26 Oct 2026", "…": "…"},
 "why_it_starts_here": ["pratyantardasha of Mars begins", "Shukra turns retrograde in Tula"],
 "dasha": {
   "mahadasha": {"level": "mahadasha", "lord": {"key": "Rahu", "…": "…"}, "start": "2024-04-08", "end": "2042-04-08"},
   "antardasha": {"level": "antardasha", "lord": {"key": "Rahu", "…": "…"}, "start": "2024-04-08", "end": "2026-12-20"},
   "pratyantardasha": {"level": "pratyantardasha", "lord": {"key": "Moon", "…": "…"}, "start": "2026-08-02", "end": "2026-10-23"},
   "antardashas_in_window": [{"mahadasha_lord": {"…": "…"}, "antardasha_lord": {"…": "…"},
                              "range": {"…clipped to the window…": ""}}]},
 "active_lords": [
   {"key": "Rahu", "name": "Rahu", "devanagari": "राहु",
    "natal_sign": {"index": 7, "name": "Tula", "…": "…"},
    "house_from_lagna": 3, "house_from_moon": 11, "rules_houses_from_lagna": [],
    "dignity": null, "combust": null, "retrograde": true, "nakshatra": "Swati",
    "navamsa_sign": {"index": 11, "name": "Kumbha", "…": "…"}, "house_from_navamsa_lagna": 4}],
 "transits": [
   {"date": "2026-10-03", "graha": {"key": "Venus", "name": "Shukra", "…": "…"},
    "event": "turns retrograde in", "retrograde_entry": null,
    "sign": {"index": 7, "name": "Tula", "…": "…"},
    "house_from_lagna": 3, "house_from_moon": 11,
    "natal_house_from_lagna": 5, "natal_house_from_moon": 1, "rules_houses_from_lagna": [3, 10]}],
 "saturn_phases": [{"sign": {"…": "…"}, "house_from_moon": 4, "phase": "dhaiya_fourth",
                    "phase_label": "Shani dhaiya / kantaka shani (Shani in the 4th from the Moon sign)",
                    "start": "2025-03-29", "end": "2027-06-03", "range": {"…": "…"}}],
 "houses_lit": [3, 5, 12],
 "life_areas": ["courage", "siblings", "communication", "short travel", "…"],
 "areas": [{"area": "travel", "houses": [3, 12], "weight": 2},
           {"area": "education", "houses": [5], "weight": 1}, "…"]}
```

- `dasha.pratyantardasha` is **the only optional field here**: it is `null` outside the
  `current_year` section. The running dasha is resolved on the window's **printed start date**, so
  a window that begins on the day an antardasha changes carries the new lord.
- `active_lords` = the 2–3 dasha lords of that window, deduplicated, each with the full natal
  fact block.
- `transits`: `event` is `"enters"`, `"turns retrograde in"` or `"turns direct in"`.
  `retrograde_entry` is `null` for stations. May be `[]`.
- `saturn_phases`: the sade-sati / dhaiya stays overlapping the window. `phase` is `null` for a
  Shani stay that is neither, and `phase` values are `sade_sati_rising` | `sade_sati_peak` |
  `sade_sati_setting` | `dhaiya_fourth` | `dhaiya_eighth`. May be `[]`.
- `areas` is the **life-area vocabulary for the whole book** and the feed for the six life-area deep
  dives: which of
  `career` `money` `marriage` `family` `health` `education` `property` `travel` `study` `spiritual`
  this window belongs in, with the houses behind the claim. An area with nothing behind it is
  **omitted, never emitted empty**; the list is sorted by how many of its houses are lit, then by
  name. The house map is `app.engine.timeline.AREAS`, written out house by house in that module.
  `life_areas` is the plain-English significations of `houses_lit`, for colour, not a key set.
  *Deprecated:* a `pillars` key with the same content under the old inner key `pillar` is still
  emitted for `app/ai/compact.py`, and will be removed once ai-layer reads `areas`.
- `why_it_starts_here` is `["section start"]` for the first window of a section.

`past` entries are deliberately thin (spec D1 - "past important nahi, sirf reference"):

```json
{"section": "past", "detail": "mahadasha changes only - context and credibility, not a reading",
 "range": {"…birth → today…": ""},
 "entries": [{"id": "p-1931-10-15",
              "range": {"start": "1931-10-15", "end": "1936-12-19", "label": "Oct 1931 – Dec 1936", "…": "…"},
              "mahadasha_lord": {"key": "Saturn", "…": "…"}, "dasha_cycle": 1,
              "full_mahadasha": {"…the untruncated period…": ""}, "partial": true,
              "age_years": [0, 5], "lord_facts": {"…as active_lords…": ""}, "houses_lit": [7, 8]}]}
```

`year_table` is the Part G feed - one row per calendar year of D2 + D3:

```json
[{"year": 2027, "range": {"start": "2027-01-01", "end": "2028-01-01", "label": "Jan 2027 – Dec 2027", "…": "…"},
  "age_at_year_start": 31,
  "dashas": [{"range": {"…clipped to the year…": ""}, "mahadasha": {"…lord facts…": ""}, "antardasha": {"…lord facts…": ""}}],
  "transits": ["…as in a window…"], "saturn_phases": [], "houses_lit": [], "life_areas": [], "pillars": []}]
```

#### `engine.timeline_windows(chart, as_of)` - the lean, grouped view

`report.timeline` carries everything a checker could want and is ~350 KB. The writer does not need
most of it, so the engine also offers the same facts grouped into the chapters of the life timeline, with
each window flattened - about a fifth of the size (106 KB for the reference chart):

```python
from app.engine import timeline_windows
view = timeline_windows(chart, as_of=None, knobs=None)       # or timeline=<an already-built one>
```

```json
{"as_of": "2026-09-21", "interval": "Half-open: …", "languages": ["en", "hi", "mr"],
 "past": [{"id": "p-1931-10-15", "…": "…"}],
 "current_year": [{"id": "w-2026-10-03", "section": "current_year",
                   "start": "2026-10-03", "end": "2026-10-27",
                   "label": "3 – 26 Oct 2026", "labels": {"en": "…", "hi": "…", "mr": "…"},
                   "mahadasha": {"lord": "Rahu", "key": "Rahu", "devanagari": "राहु",
                                 "start": "2024-04-08", "end": "2042-04-08"},
                   "antardasha": {"…": "…"}, "pratyantardasha": {"…": "…"} ,
                   "lords": [{"key": "Rahu", "name": "Rahu", "devanagari": "राहु",
                              "house_from_lagna": 3, "house_from_moon": 11,
                              "rules_houses_from_lagna": [], "dignity": null,
                              "combust": null, "retrograde": true}],
                   "transits": [{"date": "2026-10-03", "graha": "Shukra",
                                 "event": "turns retrograde in", "to_sign": "Tula",
                                 "house_from_lagna": 3, "house_from_moon": 11,
                                 "note": "natally in house 5 from the lagna, 1 from the Moon"}],
                   "saturn_phase": "dhaiya_fourth",
                   "areas": ["travel", "education", "spiritual", "study"],
                   "houses_lit": [3, 5, 12]}],
 "years": [{"year": 2028, "label": "…", "labels": {"…": "…"}, "start": "…", "end": "…", "windows": ["…"]}],
 "blocks": [{"label": "Jan 2032 – Dec 2036", "labels": {"…": "…"}, "start": "…", "end": "…", "windows": ["…"]}],
 "window_ids": ["…"], "past_ids": ["…"]}
```

What is dropped per window: everything already known chart-wide (a lord's natal sign, nakshatra and
navamsa placement) and everything only a checker needs (`why_it_starts_here`,
`antardashas_in_window`, the per-transit natal house numbers, folded into one `note` string). What is
never dropped: `house_from_lagna` and `house_from_moon` on every graha, the ISO `start`/`end`, the
`id`, and the pre-formatted `labels`. `pratyantardasha` is `null` outside the current year, and past
entries have `antardasha`/`pratyantardasha` `null` and an extra `age_years`.

#### Window count and the cost lever

The number of windows is **chart-driven** (*"jitni chart demand kare"* - as long as the chart demands
and no longer) - a chart in a Rahu
mahadasha with many short pratyantardashas and several ingresses produces more than a quiet one. The
reference chart gives 45. Nothing is capped artificially; `knobs` bounds the work and is echoed in
the output:

| Knob | Default | Effect |
|---|---|---|
| `current_year_min_months` | 6 | how short D2 may get before it extends into the next year |
| `current_year_max_windows` | 24 | the D2 window cap (~monthly) |
| `current_year_min_window_days` | 20 | D2 windows shorter than this are merged away |
| `near_years` | 4 | how many D3 years |
| `near_min_ranges_per_year` / `near_max_ranges_per_year` | 2 / 4 | the required "2–4 date-ranges within that year" |
| `near_max_window_days` | 200 | a D3 year with no antardasha shift is still split |
| `far_blocks` / `far_block_years` | 4 / 5 | how far D4 reaches |
| `far_max_ranges_per_block` / `far_min_window_days` / `far_max_window_days` | 6 / 150 / 730 | D4 granularity |
| `current_year_ingress_grahas` / `current_year_station_grahas` / `far_grahas` | see `KNOBS` | which transits are attached at which depth |

Pass them as `compute_chart(..., detail="full")` → `report_facts(chart, timeline_knobs={...})`, or
`build_timeline(..., knobs={...})`. A mahadasha boundary is **never** dropped, so a window can
exceed a cap only when a real mahadasha change forces it. If AI cost ever needs trimming these are
the levers - not the depth the customer paid for.

### What the engine deliberately does NOT compute

This list is settled, and it is here so a later session does not "helpfully" add a disputed rule to a
product that has to defend its answers to a paying customer. Each omission is argued in the docstring
of the module it would have belonged to.

| Not computed | Why |
|---|---|
| Any varga but D9 | Nothing in the report asks for one. D10, D7, D2 etc. are absent, not pending |
| Shadbala, Ashtakavarga, Bhava Bala | Not needed by any section, and a numeric "strength" invites the AI to editorialise about a number it cannot explain |
| Graded / partial drishti (1/4, 1/2, 3/4) | Same reason; `report.aspects` is whole-sign and binary. The highlights ranking is explicit about its own weights instead |
| Tatkalika and panchadha friendship | They would change a dignity label with no way for the report to explain the change, and no rule here depends on them. `report.dignity` uses naisargika (natural) friendship only |
| Rahu/Ketu exaltation | Genuinely disputed between authorities. `dignity.label` is `null` for the nodes and says why, rather than picking a side |
| Nodal aspects as a yoga trigger | The nodes' drishti is disputed, so `report.aspects` reports the 5/7/9 set flagged `disputed` and **no yoga is ever triggered by one** |
| Mars' 8° retrograde combustion orb | One documented variant among several; keeping the 17° orb is the wider one, so combustion is flagged more readily, never less |
| Cazimi | A Western notion with no classical Parashari equivalent. `deeply_combust` (within 1°) is reported as a plain qualifier that claims nothing |
| Yogini, Ashtottari, Chara dasha | Vimshottari only, to three levels |
| Bhava-madhya (cusp) houses | Whole-sign houses throughout, as fixed for the whole platform |
| "Kaal Amrit" as its own yoga | Reported as Kaal Sarp with `arc: "ketu_to_rahu"` and the dispute stated on the yoga |
| Avoiding the 3rd/11th lords' gemstones | Some schools do; `report.gemstone` follows the lagna-lord rule set only, and names it |
| Ashtakavarga gating of transits | Timeline windows are dasha-driven with transits attached |

## POST /api/mangal-dosha

Request: birth details. Response:

```json
{
  "input": {"…": "as in /api/chart"},
  "lagna": {"…position…": ""},
  "moon_rashi": {"…sign…": ""},
  "mars": {"…position of Mars…": ""},
  "mangal_dosha": {
    "rule": "Mars in house 1, 2, 4, 7, 8 or 12 (whole-sign) counted from Lagna, Moon and Venus",
    "from_lagna": {"mars_house": 12, "dosha": true},
    "from_moon": {"mars_house": 8, "dosha": true},
    "from_venus": {"mars_house": 8, "dosha": true},
    "present": true,
    "intensity": "high",
    "cancellations": [
      {"key": "mars_in_own_or_exaltation_sign", "description": "Mars in its own sign …", "applies": false},
      {"key": "jupiter_conjunct_or_aspecting_mars", "description": "…", "applies": true},
      {"key": "house_sign_exception", "description": "…", "applies": false},
      {"key": "cancer_or_leo_lagna", "description": "…", "applies": true}
    ],
    "cancellation_applies": true,
    "notes": ["When both partners have Mangal dosha …", "…"]
  }
}
```

- `present`: the raw rule — true if Mars triggers from any of the three references.
- `intensity`: `none` / `low` / `medium` / `high` = dosha from 0 / 1 / 2 / 3 references.
- `cancellation_applies`: `present` and at least one classical cancellation condition holds.
  Cancellations never flip `present`; show them as "dosha present, with mitigating factors".

## POST /api/sade-sati

Request: birth details. Response:

```json
{
  "input": {"…": "as in /api/chart"},
  "moon_rashi": {"…sign…": ""},
  "janma_nakshatra": {"…nakshatra + pada…": ""},
  "sade_sati": {
    "moon_sign": {"index": 8, "key": "Scorpio", "name": "Vrishchika", "…": "…"},
    "saturn_sign": {"index": 12, "key": "Pisces", "name": "Meena", "…": "…"},
    "saturn_house_from_moon": 4,
    "as_of": "2026-09-21",
    "active": false,
    "phase": null,
    "cycle": {
      "which": "next",
      "start": "2043-12-11",
      "end": "2052-02-25",
      "periods": [
        {"phase": "rising", "start": "2043-12-11", "end": "2044-06-23"},
        {"phase": "rising", "start": "2044-08-30", "end": "2046-12-08"},
        {"phase": "peak", "start": "2046-12-08", "end": "2049-03-06"},
        "…"
      ]
    }
  }
}
```

- `phase`: `rising` (Saturn in 12th from Moon), `peak` (over the Moon sign), `setting` (2nd), or `null`.
- `cycle.which`: `current` if a sade-sati is running, else `next`. Dates come from Saturn's real
  sign ingresses; retrograde re-entries produce several `periods` (and sometimes a gap of a few
  months inside a `current` cycle, during which `active` is false).

## POST /api/matching

Request:

```json
{
  "boy": {"date": "1889-11-14", "time": "23:30", "city": "Allahabad"},
  "girl": {"date": "1997-08-14", "time": "06:15", "city": "Pune"}
}
```

Response:

```json
{
  "boy": {"moon_sign": {"…sign…": ""}, "moon_nakshatra": {"…nakshatra…": ""}, "varna": "Brahmin",
          "vashya": "Jalachara", "yoni": "Cat", "sign_lord": "Moon", "gana": "Rakshasa",
          "nadi": "Antya", "input": {"…": "as in /api/chart"}},
  "girl": {"…": "same shape"},
  "kootas": [
    {"koota": "varna", "boy": "Brahmin", "girl": "Brahmin", "score": 1, "max": 1},
    {"koota": "vashya", "boy": "Jalachara", "girl": "Keeta", "score": 1, "max": 2},
    {"koota": "tara", "boy": "Ashlesha", "girl": "Jyeshtha", "score": 3.0, "max": 3},
    {"koota": "yoni", "boy": "Cat", "girl": "Deer", "score": 3, "max": 4},
    {"koota": "graha_maitri", "boy": "Moon", "girl": "Mars", "score": 4, "max": 5},
    {"koota": "gana", "boy": "Rakshasa", "girl": "Rakshasa", "score": 6, "max": 6},
    {"koota": "bhakoot", "boy": "Karka", "girl": "Vrishchika", "score": 0, "max": 7},
    {"koota": "nadi", "boy": "Antya", "girl": "Aadi", "score": 8, "max": 8}
  ],
  "total": 26.0,
  "max_total": 36,
  "percentage": 72.2,
  "verdict": "good",
  "doshas": {
    "nadi_dosha": {"present": false, "cancellation_applies": false},
    "bhakoot_dosha": {"present": true, "sign_distance": [5, 9], "cancellation_applies": false}
  },
  "mangal_dosha": {"boy": {"…": "as in /api/mangal-dosha"}, "girl": {"…": "…"}, "compatible": true}
}
```

- `kootas` is always these 8, in this order. Scores can be halves (0.5, 1.5).
- `verdict`: `below_average` (<18), `average` (18–24.5), `good` (25–32.5), `excellent` (33+).
- `mangal_dosha.compatible`: both have the dosha (mutual cancellation) or neither does.
- `basis`: `"birth"` for this mode (added with the by-name mode; everything else is unchanged).

### By-name mode ("kundli milan by name") - free, no birth details, no AI

```json
{"mode": "name", "boy": {"name": "Keshav"}, "girl": {"name": "Tina"}}
{"mode": "name", "boy": {"name": "केशव"}, "girl": {"name": "Tina", "syllable": "टी"}}
```

`name`: 1-80 characters, Latin transliteration **or** Devanagari (Hindi / Marathi spelling); titles (Shri, Dr., कु. ...)
and surnames are ignored - only the first sound of the first name matters. `syllable` (optional): the user's explicit
choice of that sound, a Devanagari syllable of the chakra - normally one of `name_match.candidates[].syllable` from
the previous response. `mode` defaults to `"birth"`, so existing callers are unaffected.

The first sound selects one of the 108 nakshatra padas (Avakahada chakra, `app/engine/namakshar.py`, sources cited
there), and the usual Ashtakoota runs on the midpoints of the two padas. Response = the birth-mode shape, with:

```json
{
  "basis": "name",
  "note": "Derived from the first sound of each name (Avakahada chakra), not from a birth chart. If the date, time and place of birth are known, matching from birth details is more accurate.",
  "boy": {"moon_sign": {"…": ""}, "moon_nakshatra": {"…": ""}, "varna": "Shudra", "vashya": "Manava", "yoni": "Cat",
          "sign_lord": "Mercury", "gana": "Deva", "nadi": "Aadi",
          "pada": 1,
          "input": {"name": "Keshav"},
          "name_match": {"read_as": "Keshav", "script": "latin", "syllable": "के", "latin": "ke",
                         "confidence": "exact", "rules": [], "candidates": [], "vashya_options": ["Manava"]}},
  "girl": {"…": "same", "pada": 1, "input": {"name": "Tina"},
           "name_match": {"read_as": "Tina", "script": "latin", "syllable": "ती", "latin": "ti",
                          "confidence": "ambiguous",
                          "rules": ["Latin 't' can be त or ट; त (dental) is assumed"],
                          "candidates": [
                            {"syllable": "ती", "latin": "ti", "nakshatra": {"…": "Vishakha"}, "pada": 1, "moon_sign": {"…": "Tula"}},
                            {"syllable": "टी", "latin": "ṭi", "nakshatra": {"…": "Purva Phalguni"}, "pada": 3, "moon_sign": {"…": "Simha"}}],
                          "vashya_options": ["Manava"]}},
  "kootas": ["… the same 8 …"], "total": 20.0, "max_total": 36, "percentage": 55.6, "verdict": "average",
  "total_range": [20.0, 20.0],
  "doshas": {"…": "as in birth mode"},
  "mangal_dosha": null
}
```

- `name_match.confidence`:
  - `exact` - the sound is in the chakra;
  - `convention` - a standard substitution was applied, listed in `rules` (श→स, ब→व, a conjunct takes its first
    consonant: क्ष→क, त्र→त, श्र→स, प्र→प; ऐ→ए, औ→ओ; the Abhijit syllables जू जे जो खा);
  - `ambiguous` - several readings: `candidates` lists them, **the first one was used**. Show a picker
    ("Is it ती as in तीर्थ or टी as in टीना?") and re-post with `syllable`. Causes: Latin `t` = त/ट, `th` = थ/ठ,
    `d` = द/ड; ज्ञ (Dnyanesh / Gyan) = ज/ग; Devanagari ऋ / ृ = "ri"/"ru". Latin is otherwise read literally
    (Rutuja → रू, Rishi → री); IAST letters (ṭ ḍ ṣ ṛ ā ī ū) are exact;
  - `chosen` - `syllable` was supplied.
- `candidates` is `[]` unless ambiguous. Each candidate carries its nakshatra, pada and moon sign for the picker.
- `total_range` = `[min, max]` of `total`. It differs from `total` only when a name lands on one of the two padas
  that straddle the 15° Vashya boundary of Dhanu / Makara (भू = Purvashadha 1, खू = Shravana 2; then
  `vashya_options` has two classes, the first is scored, and the range is at most 2 points wide).
- `mangal_dosha` is `null` (it needs a birth chart) - hide that block and show `note` prominently instead.
- Errors: unreadable name (digits, punctuation, another script, only spaces) or a bad `syllable` →
  `422 {"detail": {"error": "name_unreadable", "who": "boy" | "girl", "message": "…"}}`; empty / over-long `name`,
  missing person, unknown `mode` → the standard FastAPI 422 list.
- Python: `from app.engine import match_names; match_names("Keshav", "Tina", girl_syllable="टी")`.

## GET /api/transits

| Query | Notes |
|---|---|
| `at` | ISO datetime, default now. Without an offset it is read as IST |
| `rashi` | Moon sign — `1`–`12`, `Leo`, `Simha` or `simha`. Adds `house` (whole-sign, from that rashi) everywhere |
| `end` | ISO datetime. Adds `events`: sign ingresses and retrograde/direct stations between `at` and `end` |

`GET /api/transits?at=2026-09-21T00:00:00Z&rashi=dhanu&end=2026-10-21T00:00:00Z`

```json
{
  "datetime_utc": "2026-09-21T00:00:00+00:00",
  "ayanamsa": {"name": "Lahiri", "degrees": 24.230364},
  "rashi": {"index": 9, "key": "Sagittarius", "name": "Dhanu", "…": "…"},
  "grahas": {"Sun": {"…position with house…": ""}, "…": "… 9 keys"},
  "events": [
    {"type": "ingress", "graha": {"key": "Moon", "…": "…"},
     "datetime": "2026-09-21T11:15+05:30", "datetime_utc": "2026-09-21T05:45+00:00",
     "from_sign": {"…sign…": ""}, "to_sign": {"index": 10, "key": "Capricorn", "name": "Makara", "…": "…"},
     "retrograde": false, "house": 2},
    {"type": "station", "graha": {"key": "Venus", "…": "…"},
     "datetime": "2026-10-03T12:43+05:30", "datetime_utc": "2026-10-03T07:13+00:00",
     "direction": "retrograde", "sign": {"index": 7, "key": "Libra", "name": "Tula", "…": "…"},
     "degree": 14.257952, "nakshatra": {"…nakshatra…": ""}, "house": 11}
  ]
}
```

- Events are in time order. `datetime` is IST.
- ingress `retrograde: true` = the graha moved backwards into `to_sign`. Rahu/Ketu always do.
- station `direction` = the motion that begins at that moment.
- Moon ingresses are listed only when the period is 31 days or shorter.
- `house` on an event = house of `to_sign` / `sign` from the given rashi.

## GET /api/cities

```json
{"cities": [{"name": "Mumbai", "state": "Maharashtra", "lat": 19.0728, "lon": 72.8826, "tz": "Asia/Kolkata"}, "…"]}
```

124 cities, Maharashtra and neighbours first. Send `name` back as `city`.

## Using the engine from Python (ai-layer, platform, rashifal)

```python
from app.engine import compute_chart, match_charts, current_transits, transit_events, find_city

chart = compute_chart(date(1931, 10, 15), time(1, 15), 9.2881, 79.3129)  # same dict as POST /api/chart
transits = current_transits(rashi="dhanu")                              # same dict as GET /api/transits
events = transit_events(start, end, rashi="dhanu")
```

`compute_chart(..., as_of=datetime)` pins the moment used for the current dasha and sade-sati.

For the paid report, `detail="full"` (or `report_facts` on a chart you already have) adds the whole
fact set - see [POST /api/chart?detail=full](#post-apichartdetailfull---report-facts):

```python
from app.engine import compute_chart, report_facts, build_timeline, date_range

chart = compute_chart(date(1931, 10, 15), time(1, 15), 9.2881, 79.3129, detail="full")
facts = chart["report"]                        # or report_facts(chart, as_of=..., timeline_knobs=...)
for window in facts["timeline"]["windows"]:    # flat, sorted, contiguous, every one dated
    ...
```

Also exported: `timeline_windows` (the lean grouped view), `navamsa` / `navamsa_chart`,
`graha_dignities`, `graha_aspects`, `yogas`, `highlights`, `gemstones`, `build_timeline`,
`date_range`, `format_range`, `AREAS`, `areas_for`, `saturn_stays`, `running_dasha`,
`antardashas_between`, `pratyantardashas_between`. `transit_events(..., grahas=[...])` restricts the
scan to named grahas, which is most of the cost on a multi-decade span.

---

# Public pages (web layer) - three language trees

English at `/`, Hindi under `/hi/`, Marathi under `/mr/`, each tree on its own search vocabulary:
246 URLs = (home + 4 tools +
consultation + daily hub + weekly hub + 12 rashi hubs + 60 readings) x 3 languages + 6 English-only policy pages.

| Piece | Where | Notes |
|---|---|---|
| URL registry | `app/web/i18n.py` | The ONLY place a path is spelled. `url_for(page_key, lang, **params)`, `alternates(page_key, **params)` (absolute en / hi / mr / x-default), `all_pages()` (sitemap), `resolve(path)`, `legacy_redirect(path, query)`, `switcher(...)`, `rashis_by_demand(lang)`, `rashi_names(rashi, lang)`. Params are internal keys: `rashi` = engine sign slug (`mesha` ... `meena`), `period` = `today weekly monthly 6-months yearly` |
| Page config | `app/web/pages.py` + `app/web/content/{en,hi,mr}.py` | One `PageCopy` per (page key, language), each written to its own keyword. `pages.get(key, lang)` fills `{price}`, `{pack_messages}`, `{url_kundali}` ... placeholders: prices come from `app.payments.catalogue`, links from the registry. `pages.TOOLS` = language-independent wiring (form, endpoint, renderer, product). `pages.PURCHASE_OPTIONS` = the pages that sell two tiers (kundali: concise report + book; consultation: basic + premium); `purchase_offers(key, copy)` gives the template one `{product, price_inr, key, label, blurb}` per tier, cheapest first, skipping anything `catalogue.sellable()` refuses. A tier's words are `copy.extra["buy_<key>"]` / `["gets_<key>"]`; a page that sells one thing keeps `Product.button` |
| Routes | `app/web/routes.py` (home, tools, consultation, policies, order, legacy 301s), `app/web/rashifal.py` | `page_context()` supplies `<html lang>`, og:locale, Content-Language, self canonical, reciprocal hreflang, nav, footer and the language switcher. Templates link with `href("page-key")` |
| Page paths | | `/birth-chart` `/hi/kundli` `/mr/kundali` · `/horoscope-matching` `/hi/kundali-matching` `/mr/patrika-matching` · `/mangal-dosha` `/sade-sati` (+ `/hi/`, `/mr/`) · `/ai-astrologer` `/hi/ai-jyotish` `/mr/ai-jyotish` · `/horoscope[/weekly]` `/hi/rashifal[/saptahik]` `/mr/rashi-bhavishya[/saptahik]` and `/{sign or rashi}[/{period}]` below them |
| Legacy 301s (one hop) | `i18n.legacy_redirect` | `/janam-kundali`, `/kundali-matching`, `/consultation`, `/marathi-kundali`, `/rashifal[/{old rashi}[/{period}]]` incl. `?lang=hi|mr` and `3-months` -> `monthly` |
| Result rendering | `static/js/render.js`, `chat.js`, `app.js` | Pure renderers in en / hi / mr chosen by the form's `data-lang` (HI मंगल / शनि / तुला, MR मंगळ / शनी / तूळ). Matching by name: `[data-mode]` toggle, deep link `?mode=name` or `#by-name`, `AstroRender.validateNames` / `buildNamePayload(values, choices)`, syllable picker `[data-name-candidate]` |
| Payment hooks | templates | `[data-product]` + `data-price-inr` (**one button per tier**, each in its own `.cta__option` so pay.js can put its panel beside the button that was pressed), `#chat-buy` (the entry tier), `#chat-paywall`, `#cta-notice`, `#chat-form`, `#chat-quota`, `#result`, `#submit-btn`, `#self-*`, `<script data-pay data-enabled>`, the `product:purchase` event. chat.js puts `data-session-id` on every paywall button |

Checks: `tests/test_i18n_registry.py`, `test_pages_i18n.py` (all 246 URLs: language signals, site-wide unique title /
description / H1, hreflang reciprocity, switcher, prices = catalogue), `test_no_hardcoded_paths.py`,
`test_render_i18n.py`, `test_matching_by_name_web.py`, `test_web.py`, `test_consultation_web.py`,
`test_rashifal_web.py`; real browser: `scripts/browser_check_i18n.py`.

---

# Paid AI reports

`app/ai/` - the only code that calls Claude. The engine computes, Claude interprets, code checks.

| Route | Purpose |
|---|---|
| `POST /api/report` | Generate (or fetch from cache) a paid report. **402 unless entitled.** |
| `GET /api/report/{id}` | Re-download a generated report from disk. Never calls the AI. 402 unless entitled, 404 if unknown. |
| `GET /api/report/{id}/pdf` | The same report as a styled PDF download ([Report PDFs](#report-pdfs)). Same gate. |

## Payment gate

All three routes call `require_entitlement(request, product, report_id)` in `app/ai/entitlement.py` before
any engine or AI work. It passes only if:

1. env `REPORTS_UNLOCKED=1` - dev/test only, never in production (the app logs a CRITICAL warning when it is set
   while `BASE_URL` is not localhost); or
2. `is_entitled(...)`: a **paid** order ([Payments](#payments)) exists for exactly this `report_id` and product, and
   the caller is its buyer - proven by the signed `uid` cookie, or by the order's access token sent as `?token=...`
   or header `X-Order-Token` (this is how a purchase survives cleared cookies or another device).

Otherwise: `402 {"detail": {"error": "payment_required", "product": "...", "message": "..."}}`.
The `report_id` for a request is known before paying: `app.ai.report.report_id(product, language, births, as_of)`.

## POST /api/report

```json
{"product": "kundali-report", "language": "mr", "birth": {"date": "1889-11-14", "time": "23:30", "city": "Allahabad"}}
{"product": "matching-report", "language": "hi", "boy": {"...birth details...": ""}, "girl": {"...": ""}}
```

| Field | Notes |
|---|---|
| `product` | `kundali-report`, `matching-report`, `mangal-dosha-remedy`, `sade-sati-guide` (slugs from app/web/pages.py) |
| `language` | `en` (default), `hi`, `mr` |
| `birth` | Birth details (same object as `POST /api/chart`). Required for the three single-person products |
| `boy`, `girl` | Birth details. Required for `matching-report` |
| `as_of` | `YYYY-MM-DD`, default today (IST). Pins "current" dasha / sade-sati, and is part of the report id |

`kundali-report` is the **flagship book** and has its own shape and its own generation path - see
[The flagship Kundali book](#the-flagship-kundali-book) below. The other three products keep the flat
`sections` shape documented here.

Takes **1-3 minutes** on a cache miss for the three flat products (one long streamed Claude call,
sometimes two) and a **measured ~8.8 minutes** for the detailed book (twelve part calls, three at a
time - four waves). The simple tier is **three calls, one wave: a measured 240s (4.0 minutes)**, and that
run took five attempts for three calls, so it already includes a retry and is a typical figure rather than
a best case. The customer-facing wait is quoted per tier from `order_page.WAIT_RANGE` - "5-10" for the book,
"3-5" for the simple report - and travels to the browser as `report_wait` on the order view. Call it from a background job or with a long client timeout; the handler is sync so it runs in
FastAPI's threadpool.

Errors: 422 bad input · 402 not paid · 503 `ai_not_configured` (no/invalid API key) or `ai_unavailable`
(rate limit, outage, timeout) · 502 `ai_unavailable` (model refused or output unusable after retries).
Bodies are `{"detail": {"error", "message"}}` with a customer-safe message; details go to the log.
Nothing is cached on error, so retrying is safe.

### Response - the three flat products

```json
{
  "id": "5b0c…32 hex chars",
  "product": "sade-sati-guide", "product_name": "Sade Sati Guide", "language": "mr",
  "title": "…", "summary": "…",
  "sections": [
    {"id": "status", "heading": "…", "paragraphs": ["…"], "subsections": [],
     "bullets": ["…"], "table": null},
    {"id": "timeline", "heading": "…", "paragraphs": ["…"],
     "subsections": [{"heading": "…", "paragraphs": ["…"]}], "bullets": [],
     "table": {"columns": ["…"], "rows": [["…", "…"]]}}
  ],
  "remedies": [{"title": "…", "type": "mantra", "description": "…", "how_to": "…", "frequency": "…"}],
  "disclaimer": "fixed text per language, written by us, not by the AI",
  "data": {"chart": {"…": "exactly POST /api/chart, with as_of pinned"}, "lordships": {"…": ""}},
  "meta": {"model": "claude-sonnet-5", "requested_model": "claude-sonnet-5", "effort": "medium",
           "as_of": "2026-09-21", "generated_at": "…Z", "attempts": 1,
           "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
           "cost_estimate_usd": 0.0, "cost_estimate_inr": 0.0, "request_ids": ["req_…"],
           "checks": {"clean": true, "redactions": [], "warnings": [], "rejected_drafts": []},
           "cache_version": 5, "cache_hit": false},
  "pdf_url": "/api/report/5b0c…/pdf"
}
```

`pdf_url` (relative; prefix `BASE_URL` for e-mails) is added to the response by the route and is not stored in the cache.

Rendering contract (Phase 4):

- All strings are **plain text** in the report language - no markdown, no HTML. Escape and style them.
- Every section always has all six keys. `subsections`/`bullets` may be `[]`, `table` may be `null`,
  `heading` may be `""` after a redaction (fall back to your own label for that `id`).
- Section ids, in order, per product:
  - `matching-report`: `overview, koota_analysis, strengths, growth_areas, mangal_dosha, guidance`
  - `mangal-dosha-remedy`: `status, meaning, mitigating_factors, marriage, myths_and_facts, daily_practice`
  - `sade-sati-guide`: `status, timeline, work_and_money, mind_and_relationships, myths_and_facts, daily_practice`
  - `kundali-report` has no section list - it is the book (below).
- remedy `type`: `mantra | charity | service | habit | worship | meditation`.
- **Draw the chart, planet table, dasha table, koota table from `data`, never from AI text.**
  `data` is `{chart, lordships}` for mangal-dosha-remedy and sade-sati-guide, and
  `{boy_chart, girl_chart, matching}` for matching-report. `lordships` = per graha
  `{rules_houses, in_own_sign, sign_lord}`, a lookup over the engine's sign-lord fields, given to the
  model so it never works lordship out from memory.
- Always print `disclaimer`.

## The flagship Kundali book

`kundali-report` is the ₹249 product people buy and screenshot. It is not a
longer flat report: it is a **book of Parts A-H**, generated one part at a time, whose length is decided
by the chart. `app/ai/book.py` holds the structure, `app/ai/book_report.py` the generator.

### Response - the book

Same envelope as above (`id`, `product`, `language`, `title`, `summary`, `remedies`, `disclaimer`,
`data`, `meta`, `pdf_url`), plus `parts`, `highlights` and `gemstone`, and with `sections` kept as a
deprecated flat view. `highlights` (the six highlight cards, items 2-7) and `gemstone` are both optional
and both `{}` when the chart or the run did not produce them - render the engine facts and skip the
AI line.

```json
{
  "parts": [
    {"id": "timeline", "label": "D", "heading": "…", "intro": "",
     "chapters": [
       {"id": "current_year", "heading": "…",
        "paragraphs": [], "bullets": [], "subsections": [],
        "windows": [
          {"window_id": "w-2026-11-16",
           "start": "2026-11-16", "end": "2026-12-20", "label": "16 Nov – 19 Dec 2026",
           "dasha": {"mahadasha": {"key": "Rahu", "…": "…"}, "antardasha": {"…": "…"},
                     "pratyantardasha": {"…": "…"}},
           "transits": ["…as in the engine's window…"],
           "saturn_phases": ["…"], "houses_lit": [1, 3, 4],
           "headline": "…", "paragraphs": ["…"],
           "areas": [{"area": "career", "text": "…"}, {"area": "money", "text": "…"}]}
        ],
        "table": null}
     ]}
  ],

  "highlights": {"mangal": {"verdict": "…", "remedy": "…"},
                 "sade_sati": {"verdict": "…", "guidance": "…"},
                 "dasha": {"mood": "…"},
                 "strengths": ["…", "…", "…"], "cautions": ["…", "…", "…"],
                 "yogas": [{"name": "…", "text": "…"}]},
  "gemstone": {"stone": "…", "finger": "…", "day": "…", "metal": "…", "avoid": "…", "note": "…"},

  "sections": ["…one deprecated flat entry per chapter…"]
}
```

| Part | `id` | `label` | What it is |
|---|---|---|---|
| A | `highlights` | A | the 60-second hook. One chapter, `highlights[]` = spec items 1-7 in order: `basics`, `mangal_dosha`, `sade_sati`, `dasha`, `strengths`, `cautions`, `yogas` |
| B | `chart_basics` | B | `what_your_chart_looks_like`, `navamsa` |
| C | `personality` | C | `nature_and_mind`, `drive_and_relating`, `work_money_health` |
| D | `timeline` | D | `past`, `current_year`, one `year_YYYY` per near year, one `block_YYYY` per far block |
| E | `life_areas` | E | `career`, `money`, `marriage`, `health`, `education`, `family_property` |
| F | `doshas_remedies` | F | `mangal_dosha`, `sade_sati`, `other_doshas`, `gemstone` |
| G | `year_table` | G | `year_by_year` - a `table` and nothing else |
| H | `closing` | H | `closing` |

**Nothing is fixed but the order.** A chapter whose engine facts are absent is not written (no yogas →
no yoga highlight and no `other_doshas`; no engine gemstone → no `gemstone` chapter), and Part D's
chapter count comes from the engine's timeline. **Do not assume a chapter exists; iterate what is there.**

Rendering contract for the book:

- Each **part starts on a new page**. `label` is there for convenience; the PDF prints its own "PART D".
  `intro` is at most two sentences and may be `""`.
- Every chapter always has all seven keys. `paragraphs`, `bullets`, `subsections`, `windows` may be
  `[]` and `table` may be `null`; at least one is always filled. `subsections` is always `[]` today -
  it is in the contract but not in the model's schema, for the grammar-size reason below.
- **Every date in `windows` is an engine value, not AI text.** The model returns only `window_id`,
  `headline`, `paragraphs` and `areas`; `start`, `end`, `label`, `dasha`, `transits`, `saturn_phases`
  and `houses_lit` are looked up from `data["timeline"]`. A `window_id` the engine never issued fails
  that part and is regenerated, so `label` can be printed verbatim and trusted.
- `label` is already in the report's language ("Nov 2026 – Dec 2026" / "नोव्हेंबर 2026 – डिसेंबर 2026").
- `areas` is `[{area, text}]` on seven keys: `career money marriage health education family property`.
  The engine's own vocabulary is finer (it also tags `travel`, `study`, `spiritual`) and stays in
  `data`; the writer uses these seven, and `study` is folded into `education`. Part E's six chapter
  ids are the book's groupings and coarser again - do not equate the three.
- `data` = `{chart, as_of, navamsa, dignity, aspects, yogas, highlights, gemstone, dhaiya, timeline}` -
  exactly `chart["report"]` from [POST /api/chart?detail=full](#post-apichartdetailfull---report-facts),
  plus the chart. Draw the D1 and D9 charts, the planet table, the dasha table, the yoga list, the
  gemstone card and the year table from here.
- `sections` is a **deprecated** flat view, one entry per chapter, ids `"<part id>.<chapter id>"`, with
  each timeline window and each Part A highlight turned into a subsection. It exists so the Phase 4
  template keeps rendering; new work should read `parts`.
- `meta.calls` is per part: `{call, attempts, redactions, warnings, usage, cost_estimate_inr}`.

### How it is generated

Ten Sonnet calls per book, sharing one prompt-cache prefix of two blocks:

```
system = [ BOOK_SYSTEM_PROMPT   frozen - identical for every chart and language, so it caches
                                across customers,                          ~3.0k tokens
           this chart's facts   app/ai/compact.py `book_prefix` - identical for all ten calls
                                of this report                             ~5.2k tokens ]  <- cached
messages = [ user: which parts and chapters to write now, AND only the windows this call needs ]
output_config.format = CALL_SCHEMA   one schema for every call
```

Two measured facts decide this layout, and neither is guessable:

0. **The writer is never shown a window's ISO dates**, and that is a safety property rather than an
   optimisation: the model returns a `window_id`, `start`/`end` are filled in from the engine
   afterwards, so it *cannot* write a wrong date range because it never saw one. This is why
   `app/ai/compact.py` keeps its own projection instead of handing the writer
   `engine.timeline_windows(...)` - that view is the right lean view for any caller that needs dates,
   but it carries `start` and `end` per window and would quietly re-admit the failure this layer
   exists to prevent. (It is also ~3x larger once compacted - 97,681 chars against 33,600 for the
   same 45 windows - but the size is the lesser reason.)
1. **The timeline is not in the cached prefix.** `engine.report_facts` is ~370 KB (~100k tokens) and
   the timeline is 300 KB of it. Cached, that is a ~₹22 write before a word is written. Windows travel
   in the per-call message instead, so the call that writes 2028 is not charged for 2046. Part E gets
   only the windows where its life area is in the top three by weight, nearest eight - "mentions the
   area at all" selected 45 of 45 windows and doubled two calls for nothing.
2. **`output_config.format` is part of the prompt-cache key.** This is not documented anywhere and is
   easy to assume otherwise, since the caching docs describe the render order as tools -> system ->
   messages and never mention `output_config`. Measured against the live API (claude-sonnet-5,
   2026-09-21) with a >1024-token cached system block held byte-identical across three calls:

   | call | schema | `cache_creation_input_tokens` | `cache_read_input_tokens` |
   |---|---|---:|---:|
   | 1 | A | 3788 | 0 |
   | 2 | A | 0 | 3788 |
   | 3 | B | 3810 | 0 |

   Call 3 changed nothing but the schema and paid a full cache write. So there is exactly ONE schema
   for every call of the book, and it must not be specialised per part however tempting that is - ten
   writes of the ~8.2k-token prefix instead of one is roughly ₹18 a report, and nothing would announce
   it except the bill. (It is also why the schema sits so close to the grammar limit - see below.)

Calls: `A` · `BC` · `D-now` (past + current year) · `D-soon` · `D-later` · `D-beyond` · `E1` · `E2` ·
`F` (+ remedies) · `GH` (+ title and summary). The first runs alone to write the cache; the rest run
`REPORT_CONCURRENCY` (default 3) at a time. **A part that fails its checks is regenerated alone** - a
retry costs ₹2-3, not a whole book, which is why `BOOK_PART_ATTEMPTS` is 3 rather than 2. A part that
still cannot be produced cleanly raises rather than shipping a half-written book.

**The schema is at the API's grammar limit.** A structured-output schema is compiled into a grammar,
and too large a one is refused outright: `400 invalid_request_error "The compiled grammar is too
large"`. Because one schema serves every call, that failed the entire product, not one section. Two
shapes are therefore **flat in the schema and re-nested in code**, which costs nothing and buys the
headroom: `highlights` (`mangal_verdict`, `mangal_remedy`, … instead of nested objects -> `nest_highlights`)
and a window's areas (`areas` + `area_lines` paired by index -> `pair_areas`). `subsections` is in the
published contract but is **not offered to the model** for the same reason. `schema.schema_weight` is a
calibrated stand-in for the limit (24 compiles, 27 does not) and `GRAMMAR_BUDGET` guards it in tests -
but the limit is only really discovered by a real request, so probe one before going over.

**If that budget ever binds, the fix is not to trim fields.** One schema serving all ten calls is what
makes the failure total rather than local, and per-call schemas are ruled out by the cache-key finding
above. Split into **two cache groups** instead: the calls that need the `highlights` shape share
schema A, the rest share schema B. Two cache writes a report instead of one is about ₹1.8 - against
the ~₹18 that per-call schemas would cost - each schema then sits far below the grammar ceiling, and a
later field addition affects one group rather than the whole product. The budget test says this in its
failure message so nobody has to re-derive it under pressure.

Before a part is judged, `book_report.normalise` re-nests it: chapters are re-bucketed under the part
that was asked for, and anything with an id nobody asked for is dropped. The first live run returned
PART D's two chapters as three top-level parts - good writing, wrong nesting - and failing there would
have thrown away nine other good parts. Only moves and de-duplicates; nothing is invented.

Two checks exist only for the book (*"kuch bhi chipkana nahi"* - nothing generic, nothing to fill space):

- **`filler`** (blocking) - a paragraph of 30+ words that names no graha, sign, house, period,
  nakshatra or date would read the same in anyone's book, so it is removed. `boilerplate` ("in
  conclusion", "every person is unique") only drives one rewrite and is never cut.
- **`untranslated`** (fails the part) - a heading left in English in a Hindi or Marathi book. Latin
  *words* are the signal; Latin digits are required (years stay 2028) and a bracketed English gloss
  after Devanagari is fine. This one is neither redacted nor warned about: blanking a heading leaves
  a hole in the auto-generated contents page and shipping it puts English on page two of a paid
  Marathi book, so the part is regenerated and, if that fails, the report fails. Found live - the
  year and block chapters came back headed "Year 2028" and "Block 2032" in a Marathi run while every
  other check passed.
- **`untraceable`** (blocking) - a claim about a fact type the engine did not supply: aspects,
  exaltation / debilitation / combustion / friendship, a divisional chart other than the D9 we send,
  ashtakavarga, planetary war, or a named yoga when the data lists none. Each rule switches off as
  soon as the engine actually supplies that fact, so the book may discuss the D9, dignity, drishti and
  its own yogas freely - and nothing else.

**The engine owns date formatting, ids and the area vocabulary; this layer owns none of them.**
Every printed range is `range.labels[language]` read straight through (day precision for short
windows, month precision for long ones), every window id is the engine's (`w-2026-10-03`, which
carries its own start date, so a wrong id is self-evidently wrong), and area tags are read from
`areas` - never from the deprecated `pillars` alias, which exists only because this layer used to
read it. A test greps `app/ai/` to keep it that way. Intervals are half-open: `end` is exclusive and
equals the next window's start, and it is **never shown to a customer** - the label already names
the last day actually covered.

**Every piece of prose is checked against a horizon, never against the whole book.** The book spans
about twenty years, and over twenty years a slow graha visits every sign - so against the whole-book
fact set no transit claim can fail, including the one that actually shipped ("Guru also enters your
9th house transit-wise around 31 October 2026", where Simha is the lagna and the 9th only from the
Moon). Two scopes:

- **Timeline prose** -> that window's own transits plus the birth chart (`narrow_to_window`).
- **Everything else** - Parts A, B, C, E, F, H -> the birth chart plus the current year's transits
  (`near_horizon`), which is the same 12-month horizon the consultation chat uses, and why the chat
  layer never lost this check.

Only placements are narrowed; dates, months and years stay whole-book, because Part G's table
legitimately names every year. **Known limit:** the two are therefore checked independently, so a
date paired with an in-scope placement is not verified as a pair - "Shani enters Mesha in 2031"
passes, because Shani does enter Mesha (in 2027) and 2031 is a year in the report. Pinned with its
reasoning in `tests/test_historical_defects.py`; the containment is the prompt rule that outside the
timeline chapters a period is named by what it is, not by a date.

The own-sign rule reads in-scope transits for **slow grahas only**. Guru genuinely is in its own sign
while transiting Dhanu, so a 2031 window must accept that - but Budha, Shukra, Surya and Chandra
visit all twelve signs within a year, and admitting their transits would make "Budha is in its own
sign" unfalsifiable in any scope wider than a month.

### Gemstones - a deliberate reversal

The old safety screen blocked gemstones outright. The book's remedies part requires a gemstone, so `screen_text` now
takes `allow_gemstone`, which is true **only** for the `gemstone` chapter of the book and **only** when
`data["gemstone"]["recommended"]` is non-empty. It lifts the ban on naming a stone and nothing else:

| Still blocked, everywhere | Category |
|---|---|
| a price, a cost, rupees, a jeweller, a shop, a supplier, a website, "buy", "order", "energised", "consecrated" near a stone | `hard_sell` |
| "without this stone…", "you must wear…", "if you do not wear…" | `gem_fear` |
| yantras, paid pujas and homas, "consult a pandit / astrologer" | `hard_sell` |
| naming a stone anywhere else - other chapters, the other three products, the consultation chat | `gemstone` |

Carats and ratti are deliberately **not** blocked: the engine itself supplies the classical weight
range, and the chapter is told to quote it.

## Accuracy and safety enforcement

Everything here applies to all four products. The book adds `filler`, `untraceable` and per-window
scoping on top - see [The flagship Kundali book](#the-flagship-kundali-book).

1. Both system prompts contain, verbatim: *"Use ONLY the provided chart/transit data; do not calculate
   positions, dates or degrees yourself."* (`app/ai/prompts.py`: `SYSTEM_PROMPT` for the three flat
   products, `BOOK_SYSTEM_PROMPT` for the book.) The engine data travels with the prompt - in the user
   message for a flat report, in the second cached system block for the book.
2. `as_of` is pinned once and used for the chart, the prompt and the cache key, so text and tables agree.
3. Structured outputs (`output_config.format` JSON schema) - the response is always schema-valid JSON.
4. `app/ai/validator.py` checks every date, month-year, year, degree, graha-in-sign, graha-in-house and
   lagna statement in the AI text (en/hi/mr, Devanagari digits too) against the prompt data.
5. `app/ai/safety.py` screens for death / serious illness / accident-catastrophe predictions, for
   selling of any kind (`hard_sell`), for fear used as a sales tool (`gem_fear`), and for naming a
   gemstone outside the one place it is allowed (`gemstone`) - all in en/hi/mr.
6. Any hit -> one regeneration with the checker's feedback (`REPORT_MAX_ATTEMPTS`, default 2 calls). If
   the last attempt still has hits, the offending paragraph / bullet / row / remedy is **removed** and
   listed in `meta.checks.redactions`. Heuristic findings - bare years and "own sign" (dignity) claims - only
   go to `meta.checks.warnings`, never cut text. A report that loses a whole section fails with 502 instead
   of being sold. `meta.checks.rejected_drafts` records what each rejected attempt was rejected for: watch it
   for validator false positives (each one costs a second AI call - for the book, only of that part).
7. The validator separates birth-chart placements from transits: "Guru in Dhanu" passes only if Guru is in
   Dhanu natally, or the sentence is a transit statement (has a year / "enters" / "currently" / प्रवेश ...)
   and the data has that transit. "Own sign" claims are checked against the fixed sign-lord table.
8. Stray HTML tags / markdown marks are stripped from AI strings (plain-text contract).
9. **Houses are counted from the lagna.** "Your Nth house" always means whole-sign from the lagna (the chart the
   customer sees). Every transit the model reads carries `house_from_lagna` and `house_from_moon` under separate
   keys; a from-Moon count must be worded "Nth from your Moon sign / चंद्रापासून". The validator enforces it: a
   graha + house in a transit sentence must match the from-lagna house of a transit sign in the data (from-Moon
   only if the sentence says so), and any tight house-sign pairing ("9th house (Simha)", "सिंह राशीत, म्हणजे नवम
   भावात") must agree with the lagna. Both are blocking (`house`, `house_sign`).
10. **Mangal dosha that is present is "mitigated", never "cancelled".** The model-facing data replaces the
    engine's "ineffective" / "cancel each other" wording with "softens" / "balance each other" (`data` for the
    PDF keeps the engine text); the validator flags cancelled / nullified / प्रभावहीन / रद्द as `wording`
    (chat: one regeneration; reports: a warning only - not worth a second paid generation).
11. **What the model reads.** The three flat products: the compact encoding in `app/ai/compact.py`
    (`REPORT_COMPACT_DATA=1`, default) - the same engine facts with a one-time name glossary, about a
    third of the raw JSON; `REPORT_COMPACT_DATA=0` sends the raw engine JSON. The book: `book_data()`
    in the same module, which projects the engine's ~360 KB `report` block down to ~50 KB (each fact
    once, house meanings stated once instead of per window, no repeated lord profiles). Facts are
    always validated against the full engine data, whatever encoding the model read.

## Cache

`var/reports/<id>.json`, id = sha256(cache version, product, language, birth inputs, `as_of`)[:32]. A cache
hit never constructs the Claude client (works without an API key). Because `as_of` defaults to today,
the same POST tomorrow is a new report and a new AI call - **store `id` on the order at purchase and
serve re-downloads with `GET /api/report/{id}`.** Bump `CACHE_VERSION` in app/ai/report.py when the
prompt or shape changes.

## Measured cost (live, 2026-09-21, claude-sonnet-5, effort medium, Rs 88/USD)

| Product | Tokens in / out | Cost (1 attempt) |
|---|---|---|
| kundali-report en | ~15k / 8-11k | Rs 11-13 |
| kundali-report mr (hi similar) | ~15k / 13-14k | Rs 15 |
| matching-report hi | 11.6k / 7.7k | Rs 9.5 |
| mangal-dosha-remedy mr | 9.8k / 5.9k | Rs 7.6 |
| sade-sati-guide en | 9.8k / 3.9k | Rs 5.9 |
| consultation message | prefix ~7k cached | first Rs 2.3, then Rs 0.3-1.2 (avg ~Rs 1.0) |

A regeneration doubles a report's cost. `REPORT_EFFORT=low` halves Marathi cost but was measurably worse
(half the length, and an invented conjunction) - do not use it for Devanagari reports without re-testing.
For chat, medium and low cost the same (~Rs 1/message); medium writes cleaner Hindi/Marathi.

## Settings and cost

Env vars (defaults in `app/ai/config.py`, read from `.env`): `ANTHROPIC_API_KEY`, `REPORT_MODEL`
(`claude-sonnet-5`), `REPORT_EFFORT` (`medium`), `REPORT_MAX_TOKENS` (32000), `REPORT_MAX_ATTEMPTS` (2),
`REPORT_FALLBACKS` (`default` - server-side refusal fallback on Opus; `off` to disable),
`REPORT_TIMEOUT_SECONDS` (300), `REPORT_API_RETRIES` (3), `REPORTS_UNLOCKED` (0), `REPORTS_DIR`,
`USD_INR` (88), and two the book adds: `REPORT_CONCURRENCY` (3 - how many parts are written at once,
after the first has warmed the prompt cache) and `BOOK_PART_ATTEMPTS` (3 - attempts per part; higher
than `REPORT_MAX_ATTEMPTS` because a retry costs one part while a part that gives up costs the whole
book).

Live check (real, billed calls; writes `var/live_check/*.json|.md`, prints tokens and cost):

```
.venv/bin/python scripts/live_report_check.py                           # the book (kundali-report), en + mr
.venv/bin/python scripts/live_report_check.py --model claude-sonnet-5   # compare cost/quality
```

From Python: `from app.ai import generate_report, Birth` ->
`generate_report("kundali-report", "mr", [Birth(date, time, lat, lon, tz, city)], as_of=date)`.

---

# PDFs

`app/pdf/` builds **two** documents. They share the fonts, the stylesheet and the browser, and nothing else -
in particular they do not share a template.

| | Paid report | Free Basic Chart PDF |
|---|---|---|
| Route | `GET /api/report/{id}/pdf` | `POST /api/chart/pdf` |
| Input | a generated, paid-for report JSON | birth details, recomputed here |
| Gate | `require_entitlement` | none: it is free |
| Template | `templates/report.html` | `templates/basic.html` |
| Render | two passes (real page numbers) | one pass |
| AI | the report's prose was written by the AI, long before | **none, ever** |
| Cost | one browser render | one browser render |

The paid Kundali report is printed as a **book**: cover, front matter, contents page with real page numbers,
Parts A-H each starting on a new page, running head and page numbers. The PDF layer never calls the AI or the
engine for it: it prints what is in the cached report.

Every PDF, paid or free, carries the "How this report was made" box on its first page
(a trust requirement) and, when the engine flags them, the chart's accuracy caveats -
the same two notes, in the same words, that the chart page shows (`app/static/js/render.js`, `accuracyHtml`).

## GET /api/report/{id}/pdf

| Query | Notes |
|---|---|
| `name` | Optional customer name for the cover (single-person products). Max 60 chars, printable text only |
| `boy_name`, `girl_name` | The same for `matching-report` |

Response: `200 application/pdf`, `Content-Disposition: attachment; filename="kundali-report-1889-11-14-mr.pdf"`
(product, birth date(s), language), `Cache-Control: private, no-store`. The first download renders the PDF
(about 2-3 s for a 60-page book, which is rendered twice - see the contents page below) and stores it; later
downloads are served from disk.

Errors: 404 unknown id - 402 `payment_required` (same `require_entitlement(request, product, report_id)` as the
JSON route, checked before anything is rendered) - 422 name too long - 429 `too_many_name_variants` (more than
`PDF_MAX_VARIANTS` different names for one report) - 503 `pdf_unavailable` (Chromium missing / crashed / timed
out, or a bundled font failed to load; details in the log).

Typical flow after payment: `POST /api/report` -> show `pdf_url` as the download link (append
`?name=...` from the form) -> store `id` on the order for re-downloads.

## POST /api/chart/pdf - the free Basic Chart PDF

Body: the same birth details as `POST /api/chart` (`date`, `time`, and either `city` or `lat` + `lon`, plus an
optional `timezone`), and:

| Field | Notes |
|---|---|
| `language` | `en` \| `hi` \| `mr`. Default `en` |
| `script` | `en` \| `deva` - the chart's graha labels. Default: follows `language` |
| `name` | Optional, printed on the sheet. Max 60 chars, printable text only |
| `as_of` | Moment the current dasha and sade sati are evaluated for. Default now |
| `approximate_time` | `true` when `time` came from the form's tap-to-select presets rather than a record. Default `false` |

Response: `200 application/pdf`, `Content-Disposition: attachment; filename="basic-chart-1931-10-15-mr.pdf"`,
`Cache-Control: private, no-store`, `X-Robots-Tag: noindex`. Five or six A5 sheets, rendered in well under a
second.

Errors: 422 unknown city / bad timezone / bad language - 429 `rate_limited` - 503 `pdf_busy` - 503
`pdf_unavailable`.

**The rate limit counts RENDERS, not requests** (`BASIC_PDF_HOURLY_LIMIT`, default 30, per client IP per
hour, `Retry-After` in the headers). The check runs inside `ensure_basic_pdf`, only when a browser is
actually about to start, so a cache hit costs nothing. That matters because India's mobile carriers run
large-scale CGNAT: thousands of subscribers can share one public IPv4, and this is the top of the funnel.
Charging a whole NAT pool for re-downloads of a sheet one of them already generated would make the limit
bite on the cheapest possible request. It needs `TRUST_PROXY=1` behind nginx (verified in production), or
every visitor shares one bucket.

**The free sheet queues for a BOUNDED time, never an unbounded one** - `PDF_FREE_WAIT_SECONDS`, default
2 - and the reason for the bound is threadpool accounting rather than courtesy to paying customers. Both
PDF routes are sync, so they run in FastAPI's threadpool; a queued request holds one of those ~40 worker
threads for the whole render, and enough of them starve *every* route on the site, not just the PDF ones.
Since this is the ungated route - the one an anonymous visitor can fire at will - it must never be able
to accumulate waiters without limit. When the two seconds run out, `_slots` raises `PdfBusy` and the route
returns `503 pdf_busy` with `Retry-After: 10`; it never falls through into a render, because the bound is
the point. A paid book waits indefinitely: `render_book` has no `wait` parameter and cannot be made to
refuse. The asymmetry is deliberate.

Measured with `taskset -c 0,1`, pinning the whole process tree to two cores to model the 2-vCPU
production box: the 64-page book is **2.35-2.52 s** across both passes and the free chart sheet is
**0.71 s**. (Unpinned on 12 cores: 2.28-2.93 s and 0.62-0.65 s - so this path is **not** CPU-bound, and
six times the cores buys under 20%. Two concurrent renders on two pinned cores cost about 28% each, not
2x.) Peak memory is 620 MB and 480 MB as *summed VmRSS over the whole Chromium process tree*, which
double-counts pages shared between its processes; `deploy/README-DEPLOY.md` quotes ~400 MB for the same
render as proportional set size, and both are right.

Why two seconds is the right bound: a collision waits for the *residual* of whatever is already printing,
so it clears within the bound with probability `min(1, 2/D)` - certain against another free sheet
(D = 0.71 s), about 0.83 against a book (D = 2.4 s). **And the free sheet mostly contends with itself**:
at 1000 free downloads and 100 book sales a day that is 710 s/day of free renders against 240 s/day of
books, so ~96% of collisions clear inside the bound. The slot is busy about 1.1% of the day at those
volumes, so the refusal rate lands near 0.05%. Note what none of this licenses: the renders being short
is an argument that the *paid* path tolerates unbounded queueing, not that the ungated route may.
`PDF_MAX_CONCURRENT` (a file lock in `var/`, shared across uvicorn workers) is still what bounds
concurrent renders.

**`approximate_time` changes nothing about the calculation** - the chart is computed from the time given
either way - it adds a caveat, first in the caveats box and repeated as one line in the dasha section,
because a preset is up to three hours wide and that is not a small thing. Measured over 150 random births
compared across a three-hour bucket:

The window is **ninety minutes** - half the widest gap in the form's preset list, which is the furthest a
nearest-preset choice can put a reader from their real birth time. It is a fact about the form, not a
number chosen here: it was three hours until an `03:00` preset closed the six-hour jump from midnight, and
every figure below halved when it landed. `tests/test_pdf.py` derives the window from the template and
fails if the two stop agreeing.

| | changes across 90 minutes (n = 5000) |
|---|---|
| lagna | **75%** |
| mangal dosha verdict | 9.5% |
| nakshatra | 6.6% |
| running mahadasha **lord** | 6.6% |
| Moon sign | 2.6% |
| sade sati status | 0.4% |
| mahadasha start date, where the lord is unchanged | more than a year for **43%**, more than two **impossible** |

So the honest summary is narrower than it first looks, in both directions. **The dasha dates do not
survive** - which matters most, because the free sheet prints them as dates - and neither does the running
mahadasha lord, about one chart in eight. **And nothing here is immune, including sade sati**: it follows
the Moon sign, so the status flips for about one chart in a hundred. That last one is the *reassuring* half
of the caveat, the part a reader leans on, and two separate 150-birth samples measured it at zero and were
both wrong.

The dasha figure is quoted as a **spread rather than a typical value** on purpose: two careful sweeps
disagreed about the median while agreeing closely on the tails, so the tails are what the copy states. The
upper end is not measured at all but derived - the Moon covers at most 0.95° of a 13.33° nakshatra in
ninety minutes, and the longest mahadasha is 20 years, so no dasha boundary can move more than **1.44
years**. The observed maximum is 1.44 years, resting on the bound rather than inside it, which is why the
copy says the dates can *never* move further rather than that they rarely do.

That bound has already earned its place twice. It caught a sweep which built the later time as
`time(hour % 24)`, turning a bucket starting at 21:00 into a 21-hour comparison against 00:00 the same
morning and inflating every figure by roughly half - it had survived three random seeds. And it is what
made "more than two years" safe to delete rather than shrink when the window halved.
`tests/test_pdf.py` re-measures **every proportion the copy states** on a seeded 1200-birth sweep, plus
the bound and an internal coherence check (a mean slide over the 13.33-year average mahadasha predicts the
lord-change rate: 6.1% predicted against 6.6% measured).

The flag is deliberately **not** written into `chart["accuracy"]`. That block is the engine's verdict about
a chart; this is something only the caller knows, and dressing it as an engine finding is the blurring of
computed and claimed that the rest of the PDF layer exists to prevent.

**No AI call happens on this route.** It computes the chart with `detail="basic"`, derives the D9 with
`engine.navamsa_chart()`, renders `app/pdf/basic.py`'s document and prints it. There is no report, no
entitlement and no model client anywhere on the path, and `tests/test_pdf.py` asserts it by making every
`ClaudeClient` constructor raise for the duration of a request.

**The chart is recomputed here rather than accepted from the caller.** A client-supplied chart would be
attacker-controlled text arriving straight into a PDF with our name on it. The only strings a caller can put on
the sheet are the birth details and `name`, and `name` goes through the same `clean_name` the book's cover uses.

What is on the sheets, all of it computed and none of it interpreted: the birth details and lagna / rashi /
nakshatra; the trust box and any accuracy caveats; the D1 lagna chart and the D9 navamsa chart; the graha table
(sign, degree, nakshatra and pada, house, retrograde, combust); mangal dosha; sade sati, with the phase dates
when a cycle is running; the current mahadasha and antardasha with their dates; and a plain list of what the
free chart does **not** include. It names no price - a PDF outlives a price list, and
`app/payments/catalogue.py` is the only place an amount may come from.

**Why a separate template rather than the book with sections suppressed.** A "hide the paid parts" flag is one
careless edit away from being flipped, and that edit does not look dangerous. `templates/basic.html` can draw
seven block types - `facts`, `table`, `chart`, `banner`, `note`, `trust`, `caveats`, `excluded` - every one of
them engine data or one of our own labels. The block types that carry the writer's prose in
`templates/report.html` (`prose`, `bullets`, `subsections`, `windows`, `remedies`, `highlights`) have no macro
there at all, so handing that page AI text produces nothing rather than a leak. Two tests hold the line: one
reads the template, the other staples every AI-written field of a real generated book onto the chart dict and
asserts that none of it reaches the page.

Cache: `var/pdfs/basic/chart-<sha256 of the rendered HTML>.pdf`. Hashing the document itself is the exactly
right key - two requests share a file if and only if every printed character matches - and it costs a
millisecond and no browser. The directory is capped by `PDF_BASIC_CACHE_MAX` (default 400 files, oldest
evicted), because a free endpoint's cache needs a ceiling that does not depend on anyone behaving.

## The book

Page size: **A5 portrait by default** (`PDF_PAGE_SIZE=a5|a4`, also a `page_size=` argument, part of the PDF
cache file name). A5 is the booklet format this product is print-and-bind for - a print shop folds it 2-up
out of A4 - and it is the size that stays readable on a phone, which is how most buyers read a Rs 249 book.
A4 is one env var away.

1. **Cover** (`app/pdf/cover.py`): brand, title, the customer's name, birth details, lagna / rashi / nakshatra,
   and a twelve-petal rosette drawn as inline SVG. No raster art, no external file, nothing to load.
2. **Front matter**: the AI `summary` as an epigraph, the "How this report was made" box, and the accuracy
   caveats if the engine flagged any. It carries no heading element, so the contents page and the PDF outline
   are exactly what they were before it existed.
3. **Contents**, with true page numbers - see below.
3. **Parts A-H** for the book shape (`report["parts"]`), or one "Your reading" part per section for the three
   section products. Each part starts on a new page; each chapter is an `h2`; each dated timeline window is an
   `h3` carrying the engine's label for that window.
4. **Engine blocks, never AI text:** the lagna chart (D1) and the navamsa chart (D9) as inline SVG (same
   geometry as `render.js`; `app/pdf/chart_svg.py` is a port and a test compares the two label by label), the
   graha table (with a combust column when `data["dignity"]` supplies combustion), the current dasha, the
   mahadasha timeline, the complete Vimshottari table, the mangal-dosha and sade-sati tables, the engine's
   yoga classification and its gemstone table, and the year table when the writer did not produce one.
5. **Closing**: always the `disclaimer` (the fixed text for the language if the field is empty), the
   calculation note and the report id.

**The book never formats a date.** The engine owns date formatting for the whole platform (see "The two
conventions that hold everywhere in `report`" above), so:

- a range that carries its own label - every timeline window, every Shani phase - is printed by
  `Labels.label()` **verbatim** from `labels[language]`, at the precision the engine chose;
- a range that does not (a dasha period, a sade-sati cycle) goes through `Labels.range()`, which is a call
  into `engine.format_range` with the engine's exclusive `end` turned into the last day actually covered,
  so a period ending 1 Oct reads "... Sep 2026" and never "... Oct 2026";
- `app/pdf/labels.py` keeps **no month table of its own**: it re-exports `app.engine.constants.MONTHS`,
  so the book and the rashifal pages cannot spell a month two ways;
- the only thing the book adds is non-breaking spaces inside each end of a range ("16 Nov" never wraps)
  while leaving the dash breakable.

A model-written date never reaches the page: the model returns a `window_id`, `app/ai/book_report.py`
resolves it to the engine's window, and the renderer prints that window's label. A window whose id does not
resolve is not printed at all.

## The contents page (two-pass render)

Chromium cannot resolve page numbers in one pass, so `app/pdf/browser.py:render_book(build_html)` renders twice
in one browser:

1. **Pass 1** lays the contents out with a placeholder in a fixed-width column.
2. The page number of every heading is read from **the PDF's own outline** (Chromium builds it from `h1`-`h6`
   in document order) and zipped **by order** against `render.heading_ids()` - the id of every heading in the
   HTML, in document order. (Chromium sometimes repeats a heading's text in the outline title when a page break
   splits it, so nothing matches on titles.)
3. **Pass 2** prints the real numbers. Filling digits into a fixed-width column cannot reflow anything; the two
   passes are compared, and if the book paginates differently the numbers would be wrong, so it is redone - and
   if it still will not settle, the contents page is printed **without** numbers. Better none than wrong.

Nothing in the book may be **wider than one page's content box**: Chromium lays the whole document out in the
first page's content box and silently shrinks *everything* to fit whatever sticks out (that is 20% smaller type
across a 60-page book). The renderer therefore lays the page out in a print-media viewport of exactly that width
and logs a warning naming the offending element; `print.css` uses no `white-space: nowrap` in a cell (dates carry
non-breaking spaces instead) and lets a long word break. A `browser`-marked test asserts no such warning.

Language: `report.language` drives `<html lang>`, all template labels (`app/pdf/labels.py`, en / hi / mr -
Marathi spellings such as मंगळ, शनी, गुरू, तूळ, स्थान) and the chart script (Devanagari abbreviations for hi / mr).
The engine's own English vocabulary inside a fact block (a gemstone's metal, finger and weekday; a yoga's
strength and nature) is translated by `app/pdf/labels.py`; engine text written **for the model** (a gemstone
`presentation` note, a yoga `rule`) is never printed. A blank heading falls back to our label for that part or
chapter id. All report strings are HTML-escaped; symbols missing from the fonts (arrows, check marks ...) are
replaced.

## Colour

`templates/print.css` uses the ten `--color-*` tokens of the brand palette under the **same names
and values as `app/static/css/site.css`** - that file calls them "the contract with the PDF report", and
`tests/test_pdf.py` compares the two sheets token by token so neither can be edited alone. Three rules are
enforced rather than remembered:

- **Gold never carries light text.** White on gold is 2.19:1; Ink on gold is 7.65:1. Checked in the stylesheet
  with the same parser `tests/test_brand_css.py` uses on the web sheet, *and* on the rasterised pages of both
  finished PDFs - a light pixel with a gold surface within ~2mm in all four directions is what a white glyph on
  a gold badge looks like. That pixel check has a control case (a deliberately wrong swatch) so a green result
  means "no violation", not "the detector is broken".
- **Warning `#A13D2B` is only for a caution**: an active mangal dosha, an active sade sati, the accuracy
  caveats. Never Saffron, never a plain red. A dosha a classical exception cancels is information, not a
  caution, and stays neutral.
- **Success `#2E9E5B` and Saffron `#D2691E` are never text** - 3.22:1 and 3.43:1 on Cream. They are fills,
  rules and marks; a status is a tinted background with dark text (`--color-success-bg` + `--color-success-ink`,
  `--color-warning-bg` + `--color-warning`), never coloured words on Cream. (The guidelines' own contrast table
  measures Gold, Saffron and Warning, but not Success. Section 2's "OK for large bold text" exemption for
  Saffron does not reach any badge that exists here either: WCAG "large" is 18.66px bold, and the remedy badge
  is 7.5pt.)

Beyond those three, **every rule in the sheet that paints a surface and sets its text colour is measured** -
all ten pairs clear AA today, from 5.57:1 (`.banner--ok`) to 14.70:1 (`.caveats`). Neither status colour is
legible on an indigo ground (2.06:1 on Card), which no rule and no printed pixel does today; a status that ever
has to appear there must be carried by `--color-on-dark` plus a mark or a gold rule, not by hue. Both pixel
detectors are proved on control swatches first, so a green result means "no violation" rather than "the
detector is broken".

The kundali is the signature visual of Brand section 5: Card `#2E2660` ground, Gold frame and house lines, Gold
lagna marker, and the grahas in `--color-on-dark` at 12.7:1. It is the same SVG and the same class names the
web page uses (`app/pdf/chart_svg.py` is a line-for-line port of `chartSvg()` in `app/static/js/render.js`), so
the two stylesheets have to agree about it.

## Fonts

`app/pdf/fonts/`: Noto Sans 2.015 + Noto Sans Devanagari 2.007 (Regular, Bold; SIL OFL 1.1, `OFL.txt`), loaded
with `@font-face` under private family names, served to Chromium from memory. **System fonts are never needed**:
the render fails (503) if a bundled face does not load, a warning is logged if a finished PDF embeds any other
font, and `tests/test_pdf.py` checks both the font coverage of everything we print and the embedded font list of
a real PDF. `lang="mr"` also selects the Marathi letterforms (ल, श) in Noto Sans Devanagari.
Known limit: copy / search of Devanagari text inside the PDF is imperfect (Chromium/Skia omits Unicode mappings
for some matra and conjunct glyphs) - the printed shapes are right; this is normal for Indic PDFs.

## Chromium

One short-lived headless Chromium per PDF, at most `PDF_MAX_CONCURRENT` (default 1) at a time; the page is offline
(every request except the document and the bundled fonts is aborted). A book is rendered twice inside that one
browser. Measured on the dev box (WSL2, chromium-headless-shell, proportional set size across all Chromium
processes): a **63-page Marathi book = 2.4 s and ~400 MB peak, 1.1 MB PDF**; the 73-page English one 2.1 s;
a 19-page Marathi section report 1.3 s and ~320 MB (most of that is Chromium itself). `PDF_MAX_CONCURRENT` is enforced
**machine-wide** by a file lock (`PDF_RENDER_LOCK`, default `var/pdf-render.lock`), so several uvicorn workers
share the one limit and `--workers 2` cannot put two books in flight at once. `python -m app.hardening` warns
when this box does not have `600 MB + 450 MB x PDF_MAX_CONCURRENT` of RAM.

Env vars (defaults in `app/pdf/browser.py`, `app/pdf/render.py`, `app/pdf/service.py`): `PDF_CHROMIUM_EXECUTABLE`
(default: Playwright's chromium-headless-shell), `PDF_CHROMIUM_LD_LIBRARY_PATH` (extra lib dirs for the browser
process; if unset and `~/.local/share/astro-chromium/root/usr/lib/x86_64-linux-gnu` exists - the no-root dev box -
that is used; set it to empty to disable), `PDF_CHROMIUM_ARGS`, `PDF_TIMEOUT_SECONDS` (120), `PDF_MAX_CONCURRENT`
(1, machine-wide), `PDF_RENDER_LOCK` (`var/pdf-render.lock`), `PDF_PAGE_SIZE` (a5), `PDFS_DIR` (`var/pdfs`),
`PDF_MAX_VARIANTS` (5), `PDF_BASIC_CACHE_MAX` (400, the free chart cache), `BASIC_PDF_HOURLY_LIMIT`
(30 free chart RENDERS per client IP per hour; cache hits are not counted) and `PDF_FREE_WAIT_SECONDS`
(2, how long a free download queues for the render slot before a 503; 0 refuses instantly).

Install on a VPS (Phase 8), either:

```
.venv/bin/playwright install --with-deps chromium-headless-shell   # as root / sudo: browser + its apt libraries
# or: apt install chromium  and set  PDF_CHROMIUM_EXECUTABLE=/usr/bin/chromium
.venv/bin/python scripts/pdf_sample.py          # smoke test -> var/samples/kundali-report-mr.pdf, "fallback fonts: none"
.venv/bin/python scripts/pdf_sample.py --basic  # the free chart sheet -> var/samples/basic-chart-mr.pdf
```

The browser is downloaded to `~/.cache/ms-playwright` of the user who runs `playwright install` - run it as the
service user (or set `PLAYWRIGHT_BROWSERS_PATH` for both install and service). Playwright launches Chromium
without its sandbox (its default); acceptable here because the page is our own escaped HTML with the network
blocked.

Cache: `var/pdfs/<id>-v<TEMPLATE_VERSION>-<page size>-plain.pdf`, or `...-<hash of names>.pdf` when a name is
printed. Bump `TEMPLATE_VERSION` in `app/pdf/render.py` after changing the template; old files can be deleted at
any time.

Fixtures: `tests/fixtures/kundali_book_{en,mr}.json` are the long book fixtures - **real engine data and the real
part/chapter plan from `app/ai/book.py`, with placeholder prose** (`meta.model == "fixture"`), built by
`scripts/build_book_fixture.py`. Rebuild them whenever the book's parts or the engine facts change; a test says so
when they drift. `scripts/pdf_sample.py --pages 1,2,5-8` writes PNGs of chosen pages so the book can be looked at.

---

# AI consultation chat

Pages `/ai-astrologer`, `/hi/ai-jyotish`, `/mr/ai-jyotish` (the old `/consultation` 301s) + `app/ai/chat*.py`. Birth
details -> chart built once by the engine -> chat, started in the page's language (app.js sends `language`). 2 free AI
replies per user, then a paywall: Rs 99 for 10 questions **including the detailed Kundali PDF** (`CHAT_PACK_PRICE_INR`,
`CHAT_PACK_MESSAGES`; the page reads both, never hard-codes them). SQLite at `var/app.db` (`app/db.py`).

| Route | Purpose |
|---|---|
| `POST /api/consultation/start` | Birth details (same object as `POST /api/chart`) + optional `name`, `language` (`en`/`hi`/`mr`). Creates a session |
| `POST /api/consultation/message` | `{session_id, message}` -> reply. **402 = paywall, raised before any AI work** |
| `GET /api/consultation/session/{id}` | Restore after reload / refresh quota after payment. Never calls the AI |

Session view (returned by `start` and `session/{id}`):

```json
{"session_id": "…", "name": "Keshav", "language": "en",
 "summary": {"as_of": "2026-09-21", "input": {"…": ""}, "lagna": {"sign": {"…": ""}, "degree_dms": "26°12'39\""},
             "moon_rashi": {"…sign…": ""}, "janma_nakshatra": {"…": ""}, "dasha": {"mahadasha": {"…": ""}, "antardasha": {"…": ""}}},
 "messages": [{"role": "user", "content": "…", "kind": "ai"}, {"role": "assistant", "content": "…", "kind": "ai"}],
 "quota": {"free_left": 2, "paid_left": 0, "messages_left": 2},
 "paywall": null}
```

`POST /message` -> `{"reply": {"role": "assistant", "content": "plain text", "kind": "ai|safe|fallback"}, "language": "mr", "quota": {…}, "paywall": null | {…}}`.
`kind`: `ai` = model reply (the only kind that spends a message); `safe` = fixed reply from the input safety
screen; `fallback` = the model's reply failed the output screen twice. Replies are plain text - escape them.

Errors (`detail` is `{"code", "message", …}`): 402 `payment_required`
`{"code": "payment_required", "product": "consultation-pack", "price_inr": 99, "messages": 10, "session_id": "…"}` ·
404 `session_not_found` · 409 `busy` (previous question still being answered) · 422 `bad_message` (empty / over
1000 chars) or FastAPI validation · 429 `rate_limited` (+ `Retry-After`) · 503 `ai_not_configured` / `ai_unavailable`,
502 (model refused). Failed turns are never counted.

## Payment hook (Phase 6)

```python
from app.ai.chat_store import credit_session, credit_messages
credit_session(session_id, 10, reference=razorpay_payment_id)   # -> new paid balance
```

Call it after verifying the Razorpay signature. Idempotent per `reference` (a replayed webhook never credits
twice). The browser side: the paywall button (`#chat-buy`, `data-product="consultation-pack"`,
`data-price-inr` = the catalogue price) fires the site-wide cancelable `product:purchase` CustomEvent with
`detail = {product, priceInr, sessionId, …}` - `preventDefault()` it, take the payment for `sessionId`, credit
server-side, then `document.dispatchEvent(new CustomEvent("consultation:credited"))`; chat.js reloads the
session and re-opens the input. Free messages are spent before paid ones.

## Who is "a user" (no login in the MVP) - and the limits of that

- Signed, httpOnly cookie `uid` (HMAC with `SESSION_SECRET`; **set it in production** - dev generates
  `var/session_secret` and logs a warning). Free usage and the paid balance are stored per user id.
- The free quota is also stored per *(birth date + time + place, network)* bucket, so clearing cookies and
  re-entering the same birth details gives no new free replies; that usage is then charged to the new cookie too.
- `CHAT_FREE_PER_IP_PER_DAY` (10) caps free AI replies per network (IPv4 /24, IPv6 /48, stored only as an HMAC)
  per day, which bounds what varying the birth details can get. Rate limits: `CHAT_RATE_PER_MINUTE` (6) messages
  per user, 3x per network, 12 session starts per network per hour. One in-flight question per user.
- The session id is an unguessable bearer token: with cookies blocked the chat still works, and the cookie is
  re-issued for the session's owner.
- Accepted limits: new cookie + new birth details + new network = a new free trial; people behind one NAT share
  the daily free cap; a paid balance lives with the cookie / live session, so a customer who wipes their browser
  needs support (Phase 6 can re-credit by `reference`). Behind a reverse proxy set `TRUST_PROXY=1`.

## What the model sees, and prompt caching

Every request = `system[0]` frozen prompt (contains the verbatim interpret-only sentence and the §4 agent
rules) + `system[1]` `<chart_data>` compact engine JSON (chart, dasha dates, mangal dosha, sade-sati, **current
transits and the next 12 months of transit events**, `as_of` pinned; rebuilt only when the IST date changes) +
the full conversation (last 40 messages, dropped in blocks of 20). Cache breakpoints sit on both system blocks
and on the newest user turn, and history is re-rendered byte-identically, so each turn re-reads everything
before it from cache. The user's name is never sent to the model. `[Checker note` / `[Detected language`
typed by a user are defused.

## Safety, in code

- **Input screen** (`app/ai/chat_safety.py`, en/hi/mr + romanised): death / lifespan, illness diagnosis or
  outcome, accidents-jail-bankruptcy, self-harm, gemstone shopping -> fixed compassionate reply in the user's
  language, **no AI call, not counted, works even at the paywall**. Self-harm replies include Tele-MANAS 14416
  (Govt. of India, 24x7, verified at telemanas.mohfw.gov.in) and 112.
- **Output screen**: `app/ai/safety.py` + the Phase 3 fact validator (dates, degrees, sign/house/lagna
  placements vs the engine data; dates the user typed are allowed back). A hit -> one regeneration with a
  checker note -> else a fixed fallback reply (not counted).
- Language is detected per message (`detect_language`) and passed as a hint; the model replies in the same
  language and script.

## Checks

```
.venv/bin/python scripts/live_chat_check.py [--model claude-sonnet-5]   # real API: 6 scripted turns, tokens, cache hits, Rs/message
LD_LIBRARY_PATH=~/.local/share/astro-chromium/root/usr/lib/x86_64-linux-gnu \
  .venv/bin/python scripts/browser_check_consultation.py [OUT_DIR]      # real browser, fake AI: 3rd message -> paywall
```

The fake AI used by the browser check exists only inside that script (it monkeypatches
`app.ai.chat.get_chat_client` in its own process); the app has no switch that disables the real AI.

---

# Payments

`app/payments/` - Razorpay Orders API over httpx (no SDK). Operator's guide, test cards and the go-live list:
`docs/PAYMENTS.md`. Prices come only from `app/payments/catalogue.py`; no request has an amount field.

| Route | Purpose |
|---|---|
| `GET /api/payments/config` | `{enabled, key_id, test_mode, currency, prices_inr}` - nothing secret |
| `POST /api/payments/order` | Create an order for a product. Rate-limited (10/h per user, 30/h per network) |
| `POST /api/payments/verify` | Checkout's success handler posts Razorpay's triple; signature checked, then unlocked |
| `POST /api/payments/webhook` | Razorpay -> server (`payment.captured`, `order.paid`, `payment.failed`); raw-body signature |
| `GET /api/payments/order/{razorpay_order_id}` | Status for the page to poll; buyer's cookie or `?token=` required (else 404) |
| `GET /order/{token}` | HTML: the permanent "your purchase" page (noindex, no-store, no-referrer) |

All `/api/payments/*` POSTs answer `503 {"detail": {"error": "payments_not_configured"}}` without Razorpay keys.

## POST /api/payments/order

```json
{"product": "kundali-report", "language": "mr", "birth": {"date": "1889-11-14", "time": "23:30", "city": "Allahabad"},
 "name": "Keshav", "email": "optional", "phone": "optional"}
{"product": "matching-report", "language": "hi", "boy": {"...": ""}, "girl": {"...": ""}, "boy_name": "", "girl_name": ""}
{"product": "consultation-pack", "session_id": "..."}
```

Birth objects are exactly those of `POST /api/report`. For a report the server pins `as_of` to today (IST), computes
the `report_id` and stores both on the order, so the purchased report is that exact one forever. Response:

```json
{"already_paid": false, "order_id": "order_...", "amount": 9900, "currency": "INR", "key_id": "rzp_test_...",
 "product": "kundali-report", "description": "Detailed Janam Kundali Report", "prefill": {"name": "", "email": "", "contact": ""}}
```

`already_paid: true` (same buyer, same report, already bought) returns the status object below instead - do not open
Checkout. Errors: 422 bad input - 404 `session_not_found` - 429 `rate_limited` - 503 `payment_service_unavailable`
(Razorpay unreachable: nothing stored, nothing charged).

## POST /api/payments/verify

`{"razorpay_order_id", "razorpay_payment_id", "razorpay_signature"}` exactly as Checkout hands them over. The order is
looked up in our database and `HMAC_SHA256(stored_order_id + "|" + payment_id, KEY_SECRET)` is compared in constant
time. 400 `bad_signature` / 404 `order_not_found` unlock nothing. On success the order is marked paid (idempotent:
any number of verifies plus webhooks = one credit / one report job) and the status object is returned:

```json
{"order_id": "order_...", "status": "paid", "product": "kundali-report", "product_name": "...", "kind": "report",
 "amount_inr": 99.0, "fulfilment": "generating", "retrying": false, "messages": 0,
 "order_url": "/order/<token>", "report_url": null, "pdf_url": null}
```

`status`: `created | paid | failed` (failed = an attempt failed; a later success still makes it paid).
`fulfilment`: `none` (unpaid) `| pending | generating | ready | failed`. `failed` + `retrying: true` means the next
poll after the back-off restarts generation; `retrying: false` means automatic attempts are used up
(`scripts/fulfil_order.py`). `report_url` / `pdf_url` appear when `ready` and carry `?token=` (plus the cover name).
For `kind: "pack"` fulfilment is immediate and `messages` is the number credited; the page then dispatches
`consultation:credited`.

## Webhook

Header `X-Razorpay-Signature` = hex `HMAC_SHA256(raw body, RAZORPAY_WEBHOOK_SECRET)`; the body is verified before it
is parsed. `payment.captured` / `order.paid` -> same fulfilment path as verify, after checking that amount and
currency equal the order's. `payment.failed` -> noted (never downgrades a paid order). Unknown orders and other
events -> `200 {"status": "ignored"}`. `x-razorpay-event-id` is de-duplicated. Always answers within milliseconds.

## Frontend

`static/js/pay.js` (on the tool pages and the consultation page of all three language trees, and `/order/{token}`), enabled by
`<script data-pay data-enabled="1">` when keys are configured; otherwise the `product:purchase` event is left alone
and app.js shows the "launching soon" note. It cancels `product:purchase`, shows the report-language selector
(English / हिंदी / मराठी) and optional e-mail / phone, creates the order, lazy-loads
`https://checkout.razorpay.com/v1/checkout.js` (the only external URL any script loads; the other third party is
Google Analytics, a tag in base.html) on the Pay click, verifies, then polls
the status every 4 s and shows the PDF button and the order-page link. A purchase interrupted by a closed tab is picked
up on the next visit from `localStorage` (`pending-order`) and points to the order page.

---

# Rashifal (Phase 7)

`app/rashifal/` - 12 rashis x 5 periods x 3 languages = **180 permanent URLs** whose
content is rewritten on a schedule by a batch job. The engine computes a transit brief, Claude interprets it, code
checks it, the store keeps it, and the web layer renders pages from the store. **A page view never calls the AI.**

Internal keys: rashis `mesha vrishabha mithuna karka simha kanya tula vrishchika dhanu makara kumbha meena`; periods
`today weekly monthly 6-months yearly` (`monthly` replaced the MVP's `3-months`; old rows are dropped from the store
automatically); languages `en hi mr`. The **URL vocabulary per language tree** lives in `app/rashifal/periods.py` so the
routes, sitemap and tests share one source:

```python
from app.rashifal.periods import url_path, URL_PREFIX, URL_RASHI_SLUGS, URL_PERIOD_SLUGS
url_path("en", "tula", "today")     # /horoscope/libra/today
url_path("hi", "tula", "today")     # /hi/rashifal/tula/aaj           (mesh vrishabh mithun kark singh kanya tula vrishchik dhanu makar kumbh meen)
url_path("mr", "simha", "monthly")  # /mr/rashi-bhavishya/singh/masik (aaj saptahik masik 6-mahine varshik)
url_path("hi")                      # /hi/rashifal            daily hub      url_path("mr", period="weekly")  # /mr/rashi-bhavishya/saptahik
```

## Period windows (IST, half-open)

| Period | Window | Regenerated |
|---|---|---|
| `today` | the IST calendar day | daily, 00:05 IST |
| `weekly` | Monday 00:00 to the next Monday 00:00 (shown as Mon-Sun) | Mondays |
| `monthly` | the IST calendar month | the 1st of each month |
| `6-months` / `yearly` | from 00:00 on the 1st of the current month, +6 / +12 calendar months | the 1st of each month |

6-months / yearly roll forward monthly so the page always looks ahead and the permanent URL gets fresh content each
month; anchoring to the 1st makes the window identical for every run in the month (idempotent refresh).

## Engine additions (no AI; usable by any phase)

```python
from app.engine import panchang, dhaiya, sade_sati, match_names
panchang(date(2026, 9, 21))                  # vara, sunrise, tithi + nakshatra at sunrise with `ends_at`; place = Mumbai
dhaiya(moon_sign=5, as_of_utc=now)           # Saturn in the 4th / 8th from the Moon sign: active, kind, period
```

## The transit brief - `app.rashifal.brief.build_brief(rashi, period, moment=None)`

Everything a reading may state, from the engine only: `period` dates, `positions_at_start` (sign, nakshatra,
retrograde, **house from the rashi**; no degrees), `events` (dated ingresses and stations inside the window, each with
an `id` and the house), `saturn` (sade-sati phase + dates, dhaiya), and
- `today`: `panchang`, `moon_at_sunrise` with `chandra_bala` (Moon's house from the rashi in 1, 3, 6, 7, 10, 11 =
  favourable) and `lucky` (colour + number computed by code: chandra bala favourable -> the weekday lord's pair,
  otherwise the rashi lord's; the rule is printed on the page);
- `today` / `weekly`: `moon_at_start`, Moon ingresses in `events` (each with `chandra_bala`);
- `monthly` / `6-months` / `yearly`: no Moon; `slow_graha_stays` (Jupiter, Saturn, Rahu, Ketu: sign, house, from / to);
  Mercury and Venus ingresses only in `monthly` (their stations always).

## Generation - `app.rashifal.generate.refresh(periods, rashis, force=False, ...)`

**One AI call per (rashi, period, language)** by default (`RASHIFAL_SPLIT_LANGUAGES=1`): each language is written from
the brief in that language - not translated from another version (SEO map §2; with Haiku, translating its own English
gave clearly worse Hindi / Marathi). All calls of a round travel in one Message Batches API batch per model.
A reading = `headline`, `summary` (1-2 self-contained sentences for the hub pages - no extra AI call), `overview`,
`sections.{career_money, love_family, health_wellbeing}`, `key_dates` (`event_id` + note; date and event text are
printed from the brief, so no AI-written date exists), `tip`. The frozen system prompt contains the required sentence
verbatim and tells each language its readers' word: English "horoscope" with Aries...Pisces sign names (Sanskrit in
brackets), Hindi "राशिफल", Marathi "राशिभविष्य". **Titles and H1s are never AI text** - see i18n below.

Checks per language: structure (nothing empty, minimum length, summary <= 70 words, known event ids, at least one
house named), script (no Latin words in hi / mr, Marathi free of Hindi function words and vice versa),
`app.ai.safety.screen_text`, `app.ai.validator.check_text` against the brief. A rejected draft is regenerated **once**
with the feedback; if it still fails, that language is not published. A page is **complete** only with all configured
languages; clean languages are published at once, and later runs request **only the missing languages** and merge them
into the stored page (same window + same brief hash). If nothing is clean the stored content stays untouched.

Batching: `RASHIFAL_BATCH=1` (default) batches rounds of 4+ jobs - 50% of the token price, asynchronous; smaller
rounds (one page, the retry of a few rejected drafts) and `--sync` call the API directly. The Batches API rejects the
server-side refusal `fallbacks` parameter, so batch items go without it. Per-language model override:
`RASHIFAL_MODEL_MR=claude-sonnet-5` (one batch per model, run side by side).

## What the web layer gets

```python
from app.rashifal import store, i18n, config
store.get_page(rashi, period)      # {period_start, period_end, generated_at, first_published_at, languages, content{lang}, brief, meta}
store.hub_rows("today")            # {rashi: {period_start, generated_at, languages, summaries{lang}, headlines{lang}}}  ("weekly" too)
store.list_pages()                 # light listing for sitemap / index
i18n.page_title(rashi, period, lang), i18n.page_h1(...), i18n.page_meta(...)   # from the exact query patterns, e.g.
#   hi  "Tula Rashi Today – तुला राशिफल आज | Aaj Ka Tula Rashifal"      mr  "Tula Rashi Bhavishya Today – आजचे तूळ राशिभविष्य"
#   en  "Libra Horoscope Today – Tula Rashi Daily Horoscope"
i18n.hub_title(period, lang), i18n.hub_h1(...), i18n.hub_meta(...)             # period = "today" | "weekly"
i18n.rashi_names(rashi)            # {en: Libra, hi: तुला, mr: तूळ, sanskrit: Tula, latin: Tula/Kumbh/Singh, english, devanagari, index}
i18n.UI[lang], i18n.PERIOD_LABELS, i18n.describe_event(event, lang), i18n.format_date / format_range / format_timestamp,
i18n.sign_name / graha_name / nakshatra_name / tithi_name / weekday_name / place_name, i18n.KEYWORD[lang]
app.rashifal.brief.build_brief(rashi, period)   # facts for the fallback view when no reading is stored (cached, no AI)
```

A page with no stored reading (or none in that language) must still return 200 with the engine facts; a reading from
the previous window stays up, labelled with its own dates, until the refresh replaces it.
Sitemap: `from app.rashifal.sitemap import rashifal_sitemap_entries, rashifal_hub_entries` - 180 page entries + 6 hubs,
each `{loc, lastmod, changefreq, language, alternates{en, hi, mr, x-default}}`, built from `url_path`.

## Store - `app/rashifal/store.py`

Table `rashifal_pages` in `var/app.db`, primary key `(rashi, period)`; one `BEGIN IMMEDIATE` replace keeps the old
version in `previous_json` (`rollback(rashi, period)`), `merge=True` adds languages to a page written from the same
brief. Table `rashifal_lease`: the single refresh lease (TTL 30 min, renewed per page / batch poll) shared by uvicorn
workers, the CLI and timers.

## Scheduling

Single entry point: `scripts/rashifal_refresh.py` (exit 0 ok / 1 some pages failed / 2 AI not configured, nothing
generated / 3 another refresh is running). Production: `deploy/systemd/rashifal-refresh.{service,timer}` run
`--period all` at 00:05 and 05:30 IST. The job is window-based, so that one timer yields exactly the cadence above
(12 pages/day + 12/week + 36/month = 14.9 pages/day = ~45 single-language calls/day), and a failure, a rejected
language or a reboot heals at the next run. Alternative: `RASHIFAL_SCHEDULER=1` starts an in-process APScheduler with
the same two IST times; with several uvicorn workers the database lease lets only one run.

```sh
.venv/bin/python scripts/rashifal_refresh.py --period today --rashi dhanu --force --verbose   # one page, direct calls
.venv/bin/python scripts/rashifal_refresh.py --period all --force   # "run the scheduler once manually" (batched)
.venv/bin/python scripts/rashifal_check.py                          # asserts the Phase 7 "done when" for 180 readings
.venv/bin/python scripts/rashifal_check.py --snapshot var/rashifal/before.json   # ... second forced run ... --compare
.venv/bin/python scripts/rashifal_sample.py --model claude-sonnet-5 --languages mr   # judge a model's language; store untouched
.venv/bin/python scripts/rashifal_refresh.py --estimate             # pages/day and a cost table, no AI call
.venv/bin/python scripts/rashifal_refresh.py --rollback --rashi dhanu --period today
```

Every run writes `var/rashifal/runs/<run id>.json`: token usage, cost, wall-clock, every rejected check per language.

## Settings

| Env var | Default | |
|---|---|---|
| `RASHIFAL_MODEL` | `claude-haiku-4-5` | The chosen default. No adaptive thinking / effort on Haiku 4.5 (the client omits them) |
| `RASHIFAL_MODEL_EN` / `_HI` / `_MR` | - | per-language override, e.g. `RASHIFAL_MODEL_MR=claude-sonnet-5` |
| `RASHIFAL_SPLIT_LANGUAGES` | `1` | one call per language; `0` = one call returns all languages |
| `RASHIFAL_BATCH` | `1` | Message Batches API for rounds of 4+ jobs |
| `RASHIFAL_BATCH_TIMEOUT_MINUTES` | `180` | then the batch is cancelled; old content stays |
| `RASHIFAL_LANGUAGES` | `en,hi,mr` | all required for a complete page; `en` always included |
| `RASHIFAL_MAX_ATTEMPTS` | `2` | 1 generation + 1 regeneration |
| `RASHIFAL_MAX_TOKENS` | `16000` | |
| `RASHIFAL_EFFORT` | `low` | ignored by Haiku 4.5 |
| `RASHIFAL_SCHEDULER` | `0` | `1` = in-process APScheduler |

## Measured on the live API (21 Sep 2026, `var/rashifal/runs/*.json`, USD_INR = 88)

| Configuration | Full forced run (180 readings) | Projected / month | Wall-clock (batch) | Rejected drafts en / hi / mr |
|---|---|---|---|---|
| Haiku 4.5 for en + hi + mr (the default) | $2.19 = Rs 193, 266 calls | **~Rs 940** | 6.3 min + 4.2 min fill | 10 / 33 / 80 |
| Haiku 4.5 for en + hi, `RASHIFAL_MODEL_MR=claude-sonnet-5` | $2.24 = Rs 197, 199 calls | **~Rs 1,110** | 11.3 min + 1 min fill | 14 / 7 / 7 |

Per month = 12 rashis x (30.44 daily + 4.35 weekly + 1 monthly + 1 six-month + 1 yearly refreshes) = 453 pages = 1,359
readings. Input ~7.8K tokens and output ~1.9K tokens per reading on Haiku (Devanagari-heavy brief, no prompt caching:
the 1.7K-token system prompt is below Haiku's 4,096-token cache minimum). Haiku writes ~50% longer than asked; a hard
length cap is an untested ~20% saving. Quality verdict and samples: `var/rashifal/samples/` (run1 = all Haiku,
run2 = Sonnet 5 Marathi). Sonnet's Marathi costs ~Rs 250-300 / month more than Haiku's because it rarely needs a
regeneration; every rejected Haiku draft is paid for twice.
