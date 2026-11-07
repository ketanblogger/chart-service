"""The twenty-seven nakshatras: the facts that are the same in every language.

Names, ruling grahas and indices come from the engine. What is here is the part the engine has no reason
to carry - deity, symbol, gana, and whether the nakshatra is gandmool - because it is tradition rather
than astronomy, and it belongs with the pages that print it rather than with the ephemeris.

GANDMOOL is marked rather than hidden. Six nakshatras sit at the junctions between the elements -
Revati/Ashwini, Ashlesha/Magha and Jyeshtha/Mula - and a birth in them is traditionally held to need a
shanti ritual. It is also one of the most reliable ways to frighten a new parent, so the pages say what
the tradition holds, say that it is a junction rather than a flaw, and sell nothing against it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Nakshatra:
    index: int           # 1-27
    key: str
    deity: str
    symbol: str
    gana: str            # deva | manushya | rakshasa
    gandmool: bool = False


#: In order. The ruling graha is NOT repeated here - it comes from the engine, so the two cannot drift.
NAKSHATRAS = (
    Nakshatra(1, "Ashwini", "Ashwini Kumaras", "a horse's head", "deva", gandmool=True),
    Nakshatra(2, "Bharani", "Yama", "a yoni", "manushya"),
    Nakshatra(3, "Krittika", "Agni", "a blade", "rakshasa"),
    Nakshatra(4, "Rohini", "Brahma", "a cart", "manushya"),
    Nakshatra(5, "Mrigashira", "Soma", "a deer's head", "deva"),
    Nakshatra(6, "Ardra", "Rudra", "a teardrop", "manushya"),
    Nakshatra(7, "Punarvasu", "Aditi", "a quiver of arrows", "deva"),
    Nakshatra(8, "Pushya", "Brihaspati", "a cow's udder", "deva"),
    Nakshatra(9, "Ashlesha", "the Nagas", "a coiled serpent", "rakshasa", gandmool=True),
    Nakshatra(10, "Magha", "the Pitris", "a throne", "rakshasa", gandmool=True),
    Nakshatra(11, "Purva Phalguni", "Bhaga", "the front legs of a bed", "manushya"),
    Nakshatra(12, "Uttara Phalguni", "Aryaman", "the back legs of a bed", "manushya"),
    Nakshatra(13, "Hasta", "Savitr", "an open hand", "deva"),
    Nakshatra(14, "Chitra", "Tvashtar", "a bright jewel", "rakshasa"),
    Nakshatra(15, "Swati", "Vayu", "a young shoot in the wind", "deva"),
    Nakshatra(16, "Vishakha", "Indra and Agni", "an archway", "rakshasa"),
    Nakshatra(17, "Anuradha", "Mitra", "a lotus", "deva"),
    Nakshatra(18, "Jyeshtha", "Indra", "an earring", "rakshasa", gandmool=True),
    Nakshatra(19, "Mula", "Nirriti", "a bunch of tied roots", "rakshasa", gandmool=True),
    Nakshatra(20, "Purvashadha", "Apas", "a fan", "manushya"),
    Nakshatra(21, "Uttarashadha", "the Vishwadevas", "an elephant's tusk", "manushya"),
    Nakshatra(22, "Shravana", "Vishnu", "an ear", "deva"),
    Nakshatra(23, "Dhanishta", "the Vasus", "a drum", "rakshasa"),
    Nakshatra(24, "Shatabhisha", "Varuna", "an empty circle", "rakshasa"),
    Nakshatra(25, "Purva Bhadrapada", "Aja Ekapada", "the front of a funeral cot", "manushya"),
    Nakshatra(26, "Uttara Bhadrapada", "Ahir Budhnya", "the back of a funeral cot", "manushya"),
    Nakshatra(27, "Revati", "Pushan", "a fish", "deva", gandmool=True),
)

BY_KEY = {n.key: n for n in NAKSHATRAS}
GANDMOOL = tuple(n.key for n in NAKSHATRAS if n.gandmool)
