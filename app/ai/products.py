"""The four paid report products: which sections each has and what the writer is asked to cover.

Slugs match app/web/pages.py. `kind` is the request shape: "single" = one person's birth details,
"pair" = boy + girl (same bodies as POST /api/chart and POST /api/matching).
"""

from dataclasses import dataclass

LANGUAGES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}


@dataclass(frozen=True)
class Product:
    slug: str
    kind: str  # "single" | "pair" | "numerology"
    name: str
    sections: tuple[tuple[str, str], ...]  # (section id, brief for the writer); empty when `book`
    min_remedies: int = 4
    book: bool = False  # True = written part by part (app/ai/book.py), not as a flat section list
    tier: str = "detailed"  # book products only: "detailed" (Parts A-H) or "simple" (a subset)


KUNDALI = Product(
    slug="kundali-report",
    kind="single",
    name="Detailed Janam Kundali Report",
    # The flagship Detailed book. Its structure is Parts A-H in app/ai/book.py, built per chart from
    # the engine's facts and written one part at a time (app/ai/book_report.py), so there is no fixed
    # section list here.
    sections=(),
    min_remedies=5,
    book=True,
    tier="detailed",
)

KUNDALI_SIMPLE = Product(
    slug="kundali-report-simple",
    kind="single",
    name="Janam Kundali Report",
    # The cheaper tier. NOT a truncated book - its own product, and deliberately a different promise:
    # who you are, where you stand now, and what the near term asks for. What it does not have is the
    # twenty-year dated timeline, the six life-area deep dives and the year table, which is what the
    # Detailed tier sells and the honest reason to upgrade.
    #
    # Every correctness guarantee is shared, not relaxed: the same engine facts, the same validator
    # with window and near-horizon scoping, the same safety screens, the same "the model never writes
    # a date" rule, and the same historical-defects regression. A wrong cheap report is worse than
    # no cheap report.
    #
    # COSTING: standalone. It reads a byte-identical cached prefix to the Detailed book, but the cache
    # has a 5-minute TTL and almost nobody buys both tiers for one chart inside it - so this tier pays
    # its own cache write plus its three calls, every time. Never quote it as a marginal add-on.
    sections=(),
    min_remedies=3,
    book=True,
    tier="simple",
)

MATCHING = Product(
    slug="matching-report",
    kind="pair",
    name="Kundali Matching Report",
    sections=(
        ("overview", "The ashtakoota result: matching.total out of matching.max_total and what that score band "
                     "means. State clearly that guna milan is one traditional input, not a verdict on the couple."),
        ("koota_analysis", "One subsection per koota, in the order given in matching.kootas, with the koota "
                           "name as heading. State the score out of the maximum exactly as given and explain "
                           "what it says about this couple in daily life."),
        ("strengths", "Where this couple fits naturally, from the high-scoring kootas and from both Moon signs "
                      "and nakshatras."),
        ("growth_areas", "The low-scoring kootas and matching.doshas (nadi, bhakoot), including whether a "
                         "cancellation applies. Frame each as something to understand and work on together, "
                         "with one practical suggestion each."),
        ("mangal_dosha", "Mangal dosha for both charts from matching.mangal_dosha: who has it, the mitigating "
                         "factors, and whether it is mutually balanced (compatible)."),
        ("guidance", "Practical guidance for the couple and their families: communication, shared decisions, "
                     "and what to talk through before marriage. Never tell them to marry or not to marry."),
    ),
)

MANGAL = Product(
    slug="mangal-dosha-remedy",
    kind="single",
    name="Mangal Dosha Remedy Guide",
    sections=(
        ("status", "Mangal dosha status from chart.mangal_dosha: present or not, intensity, and Mars's house "
                   "counted from lagna, Moon and Venus exactly as given."),
        ("meaning", "What Mars in that position means for this person: energy, drive, temper, directness. "
                    "Include the constructive side of a strong Mars."),
        ("mitigating_factors", "The classical mitigating factors in chart.mangal_dosha.mitigating_factors: which "
                               "apply to this chart and which do not, in plain language. They soften a dosha "
                               "that is present; they do not remove it."),
        ("marriage", "What it means for marriage and partnership, including the traditional view on matching "
                     "with a partner who also has the dosha. Reassuring and practical."),
        ("myths_and_facts", "Common fears about Mangal dosha versus what the tradition actually says. "
                            "Dispel the frightening folklore."),
        ("daily_practice", "A simple weekly routine for channelling Mars energy well: exercise, discipline, "
                           "patience in arguments."),
    ),
)

SADE_SATI = Product(
    slug="sade-sati-guide",
    kind="single",
    name="Sade Sati Guide",
    sections=(
        ("status", "Sade-sati status from chart.sade_sati: active or not, current phase, Saturn's sign and its "
                   "house from the Moon, and whether the cycle given is the current or the next one."),
        ("timeline", "The cycle timeline. One subsection per entry of chart.sade_sati.cycle.periods, in order, "
                     "headed by the phase name and its exact dates, with what that stretch asks of the person."),
        ("work_and_money", "What Saturn's passage means for work, responsibility and finances for this Moon "
                           "sign, and how to plan for it sensibly."),
        ("mind_and_relationships", "Its effect on mood, patience and family ties, and how to stay steady."),
        ("myths_and_facts", "Common fears about sade-sati versus the traditional view of Saturn as a teacher "
                            "who rewards effort. Mention that many people do their most solid work in it."),
        ("daily_practice", "A simple routine for the period: discipline, service, rest, saving."),
    ),
)

NUMEROLOGY = Product(
    slug="numerology-report",
    # ITS OWN KIND, because it needs its own request shape. Every other single-person product is a
    # chart and needs a birth time and a place to cast one. Numerology needs a name and a date, and
    # asking somebody for the hour of their birth to add up digits is asking for something we will
    # not use - which costs the order and tells the reader we do not know what we are doing.
    kind="numerology",
    name="Numerology Report",
    # SIX SECTIONS, like the other written guides beside it. Not a book: a numerology reading has a
    # fixed shape and does not need eight parts built per person.
    #
    # THE SPELLING SECTION IS THE ONE PEOPLE PAY FOR, and it is also the one that could most easily
    # become "change your name or else". The brief says what it may and may not be: alternatives
    # OFFERED with their numbers shown, and a plain statement that the name somebody has is not a
    # problem to be fixed. The writer prompt and app/blog/safety.py both refuse the other version.
    sections=(
        ("your_numbers",
         "The reader's mulank, bhagyank and name number, what each one IS, and how they were worked "
         "out. Show the arithmetic. Chaldean only."),
        ("what_they_say",
         "What the tradition associates with these numbers together - tendencies and ways of "
         "working, never predictions and never what will happen to them."),
        ("lo_shu",
         "Their Lo Shu grid: which numbers repeat, which are absent, which planes are complete. A "
         "missing number is an area somebody works at, never a fault and never something to fix."),
        ("name_spelling",
         "Alternative spellings of the reader's own name, each with the number it makes and why "
         "somebody might prefer it. OFFERED, never prescribed: say plainly that the name they have "
         "is not a problem, that nobody has to change anything, and that a spelling change is a "
         "personal choice and not a remedy. Never say a name is unlucky or must be corrected."),
        ("numbers_around_you",
         "How their mulank and bhagyank sit with the numbers they deal with daily - a phone, a house, "
         "a vehicle. Strong, good or neutral, and nothing worse. Never tell them to change one."),
        ("working_with_it",
         "Practical, free things somebody can do with what the numbers suggest: how to plan a week, "
         "which kind of work suits the way they already are. Nothing to buy."),
    ),
    min_remedies=0,     # numerology has no remedies to prescribe, and inventing some would be selling
)


PRODUCTS: dict[str, Product] = {p.slug: p for p in (KUNDALI, KUNDALI_SIMPLE, MATCHING, NUMEROLOGY,
                                                   MANGAL, SADE_SATI)}
BOOK_TIERS = {p.slug: p.tier for p in PRODUCTS.values() if p.book}
