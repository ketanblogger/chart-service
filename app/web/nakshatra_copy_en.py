"""What each nakshatra means, in English. One short, specific paragraph per nakshatra.

WRITTEN ONCE, REVIEWED, AND NEVER REGENERATED. There is no AI on this path and no daily cost: a
nakshatra's meaning has not changed in two thousand years and does not need refreshing overnight.

The tone rule is the same as everywhere else on this site: say what the tradition holds, say it
specifically enough to be useful, and do not turn a birth star into a character verdict. Nobody chose
their nakshatra and nobody should be told theirs makes them untrustworthy.
"""

MEANINGS = {
    "Ashwini": "The first nakshatra, and the one that moves fastest. Its deity is the twin horsemen "
               "physicians of the gods, and its symbol a horse's head: speed, initiative, and the "
               "instinct to begin. Ashwini people are often the ones who start things - quick to act, "
               "quick to heal, and sometimes quick to move on before the thing is finished. Ruled by "
               "Ketu, so it carries a streak of the unworldly under all that motion.",
    "Bharani": "Ruled by Venus and presided over by Yama, the god who receives the dead - which sounds "
               "severe and is not. Bharani is the nakshatra of bearing: carrying something through, "
               "whether a pregnancy, a responsibility or a hard truth. Its people tend to have "
               "unusual endurance and a directness that can read as blunt.",
    "Krittika": "Agni's nakshatra, ruled by the Sun, with a blade for a symbol. Krittika cuts - it "
               "separates what is true from what is not, and it burns off what is not needed. The "
               "classical association is with sharpness in both senses: capable, critical, and better "
               "at honesty than at tact.",
    "Rohini": "The Moon's own favourite, ruled by the Moon and presided over by Brahma the creator. "
              "Rohini is growth and fertility - the nakshatra of things that flourish. Its people are "
              "often magnetic, good with beauty and material things, and prone to attachment, which is "
              "the gift and the difficulty together.",
    "Mrigashira": "A deer's head, ruled by Mars, with Soma for its deity. This is the searching "
                  "nakshatra: curious, restless, always slightly in pursuit of something just out of "
                  "sight. Good at research and at finding things; less good at being satisfied.",
    "Ardra": "Rudra's nakshatra, ruled by Rahu, with a teardrop for its symbol. Ardra is the storm "
             "that clears the air. It is associated with upheaval, and with the clarity that follows - "
             "its people often have a sharp mind that works best after something has been broken open.",
    "Punarvasu": "'Good again' - the nakshatra of return and renewal, ruled by Jupiter with Aditi, "
                 "mother of the gods, as its deity. Punarvasu is resilience: the capacity to begin "
                 "again after loss without bitterness. Generous, philosophical, and happiest when it "
                 "has somewhere to come home to.",
    "Pushya": "Classically the most auspicious of all twenty-seven. Ruled by Saturn, with Brihaspati "
              "the guru of the gods as deity, and a cow's udder for a symbol: nourishment. Pushya "
              "people tend to be caretakers - steady, dutiful, protective, and sometimes reluctant to "
              "be looked after in return.",
    "Ashlesha": "The coiled serpent, ruled by Mercury with the Nagas as deities. Ashlesha is "
                "penetrating: it sees what people are not saying. That makes for excellent insight and "
                "a tendency to hold things close. A gandmool nakshatra, which tradition marks with a "
                "shanti ritual - a junction, not a flaw.",
    "Magha": "The throne, ruled by Ketu, with the Pitris - the ancestors - as its deities. Magha is "
             "about lineage and inherited position: what you were given before you did anything. Its "
             "people often carry a natural dignity and a strong sense of obligation to where they came "
             "from. Also gandmool.",
    "Purva Phalguni": "Venus-ruled, with Bhaga the god of delight and good fortune. The symbol is the "
                      "front of a bed, and the meaning is rest, pleasure, creativity and romance. "
                      "Warm, sociable people who are better at enjoying life than most, and who "
                      "sometimes need a reason to get up.",
    "Uttara Phalguni": "The back of the bed, ruled by the Sun with Aryaman, god of contracts and "
                       "patronage. Where its first half is pleasure, this half is partnership and "
                       "obligation kept. Reliable, generous, good at the long agreement rather than "
                       "the quick one.",
    "Hasta": "An open hand, ruled by the Moon with Savitr the solar deity of skill. Hasta is "
             "craftsmanship - the nakshatra of people who are good with their hands and with detail. "
             "Dexterous, clever, occasionally too fond of their own cleverness.",
    "Chitra": "The bright jewel, ruled by Mars with Tvashtar the celestial architect. Chitra makes "
              "things beautiful and makes them well. Its people have a strong eye for form, often work "
              "in design or building, and care more than they admit about how things look.",
    "Swati": "A young shoot moving in the wind, ruled by Rahu with Vayu for its deity. Swati is "
             "independence: flexible, self-directed, hard to pin down. Associated with trade and "
             "diplomacy, and with a dislike of being owned by anything.",
    "Vishakha": "An archway, ruled by Jupiter with Indra and Agni together. Vishakha is ambition with "
                "a target - the nakshatra of determined, goal-fixed people who will wait a long time "
                "for the thing they want. The difficulty is knowing when the goal has stopped being "
                "worth it.",
    "Anuradha": "The lotus, ruled by Saturn with Mitra, god of friendship. Anuradha is devotion and "
                "the ability to work with other people - the one nakshatra most associated with "
                "friendship that lasts. Its people often succeed away from where they were born.",
    "Jyeshtha": "'The eldest', an earring for a symbol, ruled by Mercury with Indra, king of the gods. "
                "Jyeshtha carries seniority and the weight that comes with it: protective, capable, "
                "proud, and often carrying more than it says. A gandmool nakshatra.",
    "Mula": "The root, ruled by Ketu with Nirriti, goddess of dissolution. Mula digs to the bottom of "
            "things - it is the nakshatra of researchers, investigators and anyone who cannot leave a "
            "question half-answered. Gandmool, and the one most often used to frighten parents, which "
            "it does not deserve: a root is where a thing is held, not where it is cursed.",
    "Purvashadha": "'The early victory', ruled by Venus with Apas, the waters. A fan for a symbol: "
                   "something that spreads. Purvashadha is persuasive and hard to discourage - its "
                   "people have conviction and tend to carry others along with it.",
    "Uttarashadha": "'The later victory', ruled by the Sun with the Vishwadevas. An elephant's tusk: "
                    "the win that lasts because it was earned slowly. Associated with integrity and "
                    "with leadership that people actually follow.",
    "Shravana": "An ear, ruled by the Moon with Vishnu. Shravana is listening - the nakshatra of "
                "learning by hearing, of teachers, counsellors and anyone whose work is to understand "
                "what is being said. Its people are often the ones others tell things to.",
    "Dhanishta": "A drum, ruled by Mars with the eight Vasus. Dhanishta is rhythm, wealth and "
                 "performance. Its people tend to be prosperous, musical or athletic, and comfortable "
                 "in front of others - with a streak of impatience underneath.",
    "Shatabhisha": "'A hundred healers', an empty circle, ruled by Rahu with Varuna. Shatabhisha is "
                   "the nakshatra of healing and of secrets - solitary, scientific, drawn to what is "
                   "hidden. Often associated with medicine, and with people who prefer to work alone.",
    "Purva Bhadrapada": "Ruled by Jupiter with Aja Ekapada, the one-footed goat. Intense, idealistic "
                        "and unworldly in a way that can be austere. This is the nakshatra of people "
                        "who hold a principle further than is comfortable.",
    "Uttara Bhadrapada": "Ruled by Saturn with Ahir Budhnya, the serpent of the deep. The calmer half: "
                         "deep, patient, compassionate, and unusually steady in a crisis. Classically "
                         "one of the most benign nakshatras to be born in.",
    "Revati": "The last nakshatra - a fish, ruled by Mercury with Pushan, the guardian of travellers "
              "and of herds. Revati is the one that sees everything safely across. Gentle, imaginative "
              "people, often good with animals and children. Gandmool, because it sits at the join "
              "where the cycle ends and begins again.",
}
