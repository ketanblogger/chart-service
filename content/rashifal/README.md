# Hand-written rashifal readings

One JSON payload per `(rashi, period)`, written by hand rather than generated, and **tracked** - the
readings are the content this site is for, and they are published with the source under the AGPL
like everything else here.

They live in the repository rather than only in a database because a database is not deployable.
The 2027 yearly readings existed in one laptop's `var/app.db` for a day, and a code deploy would
have shipped every template that renders them and none of the readings themselves: the live page
would have kept serving the three-section generated text under a sixteen-section layout.

## Loading them

    uv run python scripts/rashifal_handwritten.py load content/rashifal/*.json

`load` re-runs every check before storing - structure, style, the date validator, the eclipse
accuracy checks and cross-page similarity - and refuses the file if any of them fails. It is
idempotent: loading the same payload twice stores it twice with the same content, which is a no-op
for a reader. Run it after the code is in place, because the checks import the section definitions.

## What is NOT here

The window and the brief. Both are recomputed from the ephemeris at load time, so a reading carries
its prose and its `event_id` references and nothing that could go stale.
