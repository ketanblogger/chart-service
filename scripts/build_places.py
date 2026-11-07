#!/usr/bin/env python3
"""Build the offline India place list from a GeoNames dump.

    python scripts/build_places.py <dir with cities1000.txt, IN.txt, admin1CodesASCII.txt>

GEONAMES IS CC BY 4.0: the attribution is required and lives in docs/CREDITS.md. Nothing here runs at
request time and the site makes no external call for a place - the whole list ships with the site,
because a birth chart must be computable on a phone with a bad connection and because sending somebody
else a reader's birth place to geocode is not a thing this site will do.

WHY THE WHOLE LIST. The hand-kept one had 137 cities in it. Bhiwandi (874,000 people) and Dewas
(290,000) were not among them, and a required field somebody cannot satisfy is the end of their visit.

WHAT IS KEPT PER PLACE: name, state, latitude, longitude, and the Hindi or Marathi name where GeoNames
has one - which is for 2,146 of 7,206 places, so the search leans on transliteration rather than on
these. Population is kept only to order the results: between two places of the same name, the larger
is the one more people mean. Timezone is NOT kept: all of India is Asia/Kolkata, and a constant does
not need 7,206 copies.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _key(name: str) -> str:
    """The same search key the site matches on, so "already present" means what the reader will see."""
    from app.engine.places import key

    return key(name)
OUT = ROOT / "app" / "engine" / "places_in.json"

#: Latitude and longitude to four decimals - about 11 metres. A birth chart moves by a few arcseconds
#: over that, which is far below anything the reading reports; more decimals would be bytes spent on
#: precision nobody can use.
PLACES = 4


def build(source: Path) -> dict:
    states = {}
    for line in (source / "admin1CodesASCII.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith("IN."):
            states[parts[0]] = parts[1]

    # The Hindi and Marathi names, by geonameid. Short, colloquial and historic forms are skipped: a
    # search is better served by the name people write than by every name a place has ever had.
    native: dict[str, str] = {}
    for line in (source / "IN.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 4 or parts[2] not in ("hi", "mr"):
            continue
        if len(parts) > 7 and parts[7] == "1":          # historic
            continue
        native.setdefault(parts[1], parts[3])

    rows = []
    for line in (source / "cities1000.txt").read_text(encoding="utf-8").splitlines():
        f = line.split("\t")
        if len(f) < 15 or f[8] != "IN":
            continue
        state = states.get(f[8] + "." + f[10], "")
        rows.append({
            # THE ASCII NAME, not the unicode one. GeoNames' `name` carries diacritics - Kolhāpur,
            # Kot Kapūra - and nobody in India writes their town that way in a form. The ascii field
            # is the ordinary English spelling, which is what a reader is looking for in the list.
            "name": f[2] or f[1],
            "state": state,
            "lat": round(float(f[4]), PLACES),
            "lon": round(float(f[5]), PLACES),
            "pop": int(f[14] or 0),
            "deva": native.get(f[0], ""),
        })

    # THE HAND-KEPT LIST IS MERGED IN, NOT REPLACED. GeoNames is missing five of its 137 entries -
    # Panaji, Vasai-Virar (1.2 million people), Miraj, Davanagere, and Chhatrapati Sambhajinagar under
    # that name - and it carries the local spellings somebody actually types, like
    # "Chhatrapati Sambhajinagar (Aurangabad)". Swapping one list for the other would have fixed
    # Bhiwandi and broken Panaji, which is not a trade worth making when both can be true.
    #
    # They go in with a nominal population so the sort puts them among the large places, which is what
    # they are: this list was written for the cities people are most often born in.
    from app.engine.cities import CITIES as CURATED

    known = {_key(row["name"]) for row in rows}
    for city in CURATED:
        bare = city["name"].split("(")[0].strip()
        if _key(city["name"]) in known or _key(bare) in known:
            continue
        rows.append({"name": city["name"], "state": city["state"], "lat": city["lat"],
                     "lon": city["lon"], "pop": 250_000, "deva": ""})
        known.add(_key(city["name"]))

    # Biggest first: the list is also the order suggestions appear in, and between two places that
    # share a name the larger is the one more people mean.
    rows.sort(key=lambda row: -row["pop"])

    # COMPACT, BECAUSE THIS GOES TO A PHONE. As one object per place with named keys it is 656 KB;
    # as arrays against a table of state names it is less than half that, and the key names were
    # three quarters of the bytes. Population is dropped entirely once the sort has used it - the
    # ORDER carries that information now, and shipping the number as well would be paying twice.
    #
    #   [name, state index, lat, lon, Devanagari name or ""]
    #
    # The trailing name is omitted where there is none, so 6,409 of the rows are four long.
    names = []
    for state in sorted({row["state"] for row in rows}):
        names.append(state)
    index = {state: position for position, state in enumerate(names)}
    packed = []
    for row in rows:
        entry = [row["name"], index[row["state"]], row["lat"], row["lon"]]
        if row["deva"]:
            entry.append(row["deva"])
        packed.append(entry)
    return {"tz": "Asia/Kolkata", "source": "GeoNames (CC BY 4.0)", "states": names, "places": packed}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    data = build(Path(sys.argv[1]))
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    deva = sum(1 for row in data["places"] if len(row) > 4)
    print(f"  {len(data['places'])} places, {deva} with a Devanagari name")
    print(f"  {OUT.relative_to(ROOT)}  {OUT.stat().st_size // 1024} KB")
