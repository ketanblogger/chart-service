"""Freeze what pyswisseph answers TODAY, so our own binding can be proved identical to it.

    PYTHONPATH=. uv run python scripts/build_swe_golden.py     # -> tests/fixtures/swe_golden.json

This is generated BEFORE the binding is swapped in, and never regenerated afterwards without saying so:
the whole value of the file is that it was written by the library we are replacing. A fixture rebuilt with
the new binding would agree with it by construction and prove nothing.

It pins the SIX PRIMITIVES `app/engine/swe.py` has to reproduce - longitude, speed, the returned flags,
ayanamsa, ascendant and sunrise - across the reference charts plus 200 generated ones spread over
1900-2100 and every latitude band we ship cities in. Everything else the engine computes (nakshatra, pada,
house, D9, dasha dates, the transit table) is pure Python arithmetic on top of these numbers, and is
already pinned by the 1655-test suite; if the primitives match, the derived values cannot differ.

The generated charts use INVENTED coordinates and times only. There is no name, no place and no real
person anywhere in this file or its output - `tests/` is published, and a fixture is as public as a comment.
"""

import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine import core  # noqa: E402

OUT = ROOT / "tests/fixtures/swe_golden.json"
GRAHAS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu")
# A fixed seed, so the same 200 charts come back on every machine and the fixture is reviewable as a diff.
SEED = 20260928
COUNT = 200


def cases() -> list[dict]:
    """200 invented (jd, lat, lon) triples, spread on purpose rather than at random.

    Latitude is swept across the whole range, not sampled uniformly: the ascendant and the sunrise are
    where a wrapper's flags go wrong, and they go wrong at the extremes - above the Arctic circle the Sun
    may not rise at all, and `swe_rise_trans` reports that by its return value rather than by raising.
    """
    rng = random.Random(SEED)
    out = []
    for n in range(COUNT):
        # 1900-2100, uniformly over the Julian range rather than over calendar years
        jd = rng.uniform(2415020.5, 2488070.5)   # ~1900-01-01 to ~2100-01-01
        if n < 20:                                # the hard latitudes first, deliberately
            lat = rng.choice([-89.0, -78.5, -66.6, -45.0, 66.6, 71.0, 78.5, 89.0])
        else:
            lat = rng.uniform(-60.0, 60.0)
        lon = rng.uniform(-180.0, 180.0)
        out.append({"jd": round(jd, 6), "lat": round(lat, 4), "lon": round(lon, 4)})
    return out


def measure(case: dict) -> dict:
    jd, lat, lon = case["jd"], case["lat"], case["lon"]
    row = {**case, "grahas": {}}
    for graha in GRAHAS:
        longitude, speed = core.longitude_and_speed(jd, graha)
        row["grahas"][graha] = [longitude, speed]
    row["ayanamsa"] = core.ayanamsa(jd)
    row["ascendant"] = core.ascendant(jd, lat, lon)
    try:
        row["sunrise"] = core.sunrise(jd, lat, lon)
    except Exception as exc:                       # noqa: BLE001 - a polar night is a legitimate answer
        row["sunrise"] = None
        row["sunrise_error"] = type(exc).__name__
    row["ephemeris"] = core.ephemeris_in_use(jd)
    return row


def main() -> int:
    import swisseph

    rows = [measure(case) for case in cases()]
    payload = {
        "generated_by": "pyswisseph",
        "pyswisseph_libswe_version": swisseph.version,
        "seed": SEED,
        "grahas": list(GRAHAS),
        "note": "Invented coordinates only. Regenerating this with the new binding would prove nothing.",
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    polar = sum(1 for row in rows if row["sunrise"] is None)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} charts, libswe {swisseph.version}, "
          f"{polar} with no sunrise (polar day/night)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
