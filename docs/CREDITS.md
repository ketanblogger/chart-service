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
| City coordinates | GeoNames | CC BY 4.0 |
| Noto Sans / Noto Sans Devanagari | Google Fonts | SIL Open Font License 1.1 |

The fonts are bundled in `app/pdf/fonts/` so a PDF renders the same on any machine, and are not loaded from
any third party at page time.
