# Credits

## Artwork

**All of it is ours.** `app/static/img/glyphs.svg` - the nine grahas, the twelve rashis, Om, the lotus and
the seated figure - was drawn for this repository from primitives: circles, arcs, crosses and arrows, on one
24x24 grid with one stroke width. Nothing is traced, nothing is imported, and no stock art is used anywhere
on the site. The repository is AGPL and public, so that had to be true rather than probably true.

The constellation tile in `app/static/css/site.css` and the drifting graha marks are the same: drawn inline
as SVG, in the stylesheet, by us.

If anything external is ever added - a font, an icon, a photograph - it goes here with its source, its
licence and the date it was added, before it is used.

## Software and data

| What | Source | Licence |
|---|---|---|
| Swiss Ephemeris (via pyswisseph) | Astrodienst AG | AGPL-3.0 (a commercial licence is the alternative; see the launch notes) |
| City coordinates and place names | GeoNames `cities1000` and `alternateNames` | CC BY 4.0 |
| Noto Sans / Noto Sans Devanagari | Google Fonts | SIL Open Font License 1.1 |

The fonts are bundled in `app/pdf/fonts/` so a PDF renders the same on any machine, and are not loaded from
any third party at page time.

**GeoNames, in detail, because CC BY 4.0 asks for attribution and because the file is large enough that
somebody will wonder where it came from.** `app/engine/places_in.json` holds 7,206 Indian places with a
population of a thousand or more - name, state, latitude, longitude, and the Hindi or Marathi name where
GeoNames records one. It is built by `scripts/build_places.py` from the `cities1000` and per-country
`alternateNames` dumps at <https://download.geonames.org/export/dump/>, which are published by GeoNames
under the Creative Commons Attribution 4.0 licence: <https://creativecommons.org/licenses/by/4.0/>.

The file ships with the site and **no request is ever made to GeoNames, or to any other geocoder, at page
time**. A birth chart has to be computable on a phone with a bad connection, and a reader's birth place is
not something to hand to somebody else's service.
