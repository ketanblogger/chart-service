"""Our own binding to the Swiss Ephemeris C library. Replaces `pyswisseph`.

WHY THIS EXISTS. Astrodienst dual-licenses libswe: AGPL, or a paid Professional Licence. `pyswisseph` -
the Python wrapper, a separate project - is AGPL-3.0 ONLY. While it is in the stack, buying the
Professional Licence frees nothing, because the AGPL obligation arrives through the wrapper. So the
wrapper has to be ours. Nothing about the ephemeris maths changes; this file is a calling convention.

SCOPE IS DELIBERATELY SIX FUNCTIONS. That is everything `app/engine/core.py` has ever called, and core.py
is the only module in the codebase that touches the ephemeris at all. A binding that exposed the rest of
libswe would be more code to be wrong in, with nothing asking for it.

THE LOCK IS NOT OPTIONAL, AND IT IS THE REASON THIS FILE IS RISKIER THAN IT LOOKS.
libswe keeps the ephemeris path, the sidereal mode and its open-file cache in GLOBAL state, and its
documentation does not promise thread safety. ctypes RELEASES THE GIL around every foreign call, so a
ctypes binding lets two requests be inside libswe at the same time - which a C extension holding the GIL
would have prevented by accident. We serve concurrent requests, so this would not be theoretical: it would
be a rare wrong chart that never reproduces. Every call below therefore runs under one module-level lock,
and the global state is set once, under that same lock. A chart costs about ten milliseconds of ephemeris
work, so serialising it is affordable, and correctness is not the thing to trade away for it.

THE CONSTANTS ARE LITERALS, PINNED BY A TEST. They are copied from swephexp.h via the library they replace,
and `tests/test_swe_binding.py` asserts every one of them against pyswisseph while pyswisseph is still
installed. A wrong constant here does not raise - `FLG_SIDEREAL` off by a bit returns TROPICAL longitudes,
which are plausible numbers and wrong by about 24 degrees.
"""

import ctypes
import os
import threading
from ctypes.util import find_library
from pathlib import Path

# ---- constants (swephexp.h) ---------------------------------------------------------------------------
FLG_SWIEPH = 2
FLG_SPEED = 256
FLG_SIDEREAL = 65536
SIDM_LAHIRI = 1
CALC_RISE = 1
BIT_HINDU_RISING = 896      # disc centre | no refraction | geocentric, the panchang convention
SUN, MOON, MERCURY, VENUS, MARS, JUPITER, SATURN = 0, 1, 2, 3, 4, 5, 6
MEAN_NODE = 10

_ERR_LEN = 256              # AS_MAXCH in swephexp.h
RISE_NOT_FOUND = -2         # swe_rise_trans: the Sun does not rise here today. An answer, not a fault.
_lock = threading.Lock()
_lib = None


class SweError(RuntimeError):
    """libswe reported an error and filled `serr`. Raised rather than returned, because the alternative is
    handing back zeros - and 0.0 degrees is a perfectly plausible longitude."""


def _candidates() -> list[str]:
    """Where libswe might be. `SWE_LIB` wins, then the deploy location, then the system loader."""
    found = []
    if os.getenv("SWE_LIB"):
        found.append(os.environ["SWE_LIB"])
    found.append("/srv/astrology/lib/libswe.so")
    found.append(str(Path(__file__).resolve().parents[2] / "lib/libswe.so"))
    system = find_library("swe")
    if system:
        found.append(system)
    return found


def _load():
    """Bind the six symbols once. Raises if libswe is absent, naming where it was looked for - a silent
    fallback to a different ephemeris is the one failure that would not show up in any output."""
    for path in _candidates():
        if not path:
            continue
        try:
            lib = ctypes.CDLL(path)
        except OSError:
            continue
        lib.swe_set_ephe_path.argtypes = [ctypes.c_char_p]
        lib.swe_set_ephe_path.restype = None
        lib.swe_set_sid_mode.argtypes = [ctypes.c_int32, ctypes.c_double, ctypes.c_double]
        lib.swe_set_sid_mode.restype = None
        lib.swe_calc_ut.argtypes = [ctypes.c_double, ctypes.c_int32, ctypes.c_int32,
                                    ctypes.POINTER(ctypes.c_double), ctypes.c_char_p]
        lib.swe_calc_ut.restype = ctypes.c_int32
        lib.swe_get_ayanamsa_ut.argtypes = [ctypes.c_double]
        lib.swe_get_ayanamsa_ut.restype = ctypes.c_double
        lib.swe_houses_ex.argtypes = [ctypes.c_double, ctypes.c_int32, ctypes.c_double, ctypes.c_double,
                                      ctypes.c_int, ctypes.POINTER(ctypes.c_double),
                                      ctypes.POINTER(ctypes.c_double)]
        lib.swe_houses_ex.restype = ctypes.c_int
        lib.swe_rise_trans.argtypes = [ctypes.c_double, ctypes.c_int32, ctypes.c_char_p, ctypes.c_int32,
                                       ctypes.c_int32, ctypes.POINTER(ctypes.c_double), ctypes.c_double,
                                       ctypes.c_double, ctypes.POINTER(ctypes.c_double), ctypes.c_char_p]
        lib.swe_rise_trans.restype = ctypes.c_int32
        return lib
    raise SweError("libswe not found. Looked in: " + ", ".join(p for p in _candidates() if p)
                   + ". Build it from github.com/aloistr/swisseph at tag v2.10.03 "
                     "(commit 175e1fcb3108bcd5c0d146c803f51dcf23508012) and set SWE_LIB, "
                     "or see deploy/build-libswe.sh.")


def available() -> bool:
    """True when libswe can be loaded. Lets tests skip with a reason instead of erroring."""
    try:
        _libswe()
        return True
    except SweError:
        return False


def _libswe():
    global _lib
    with _lock:
        if _lib is None:
            _lib = _load()
        return _lib


# ---- the six calls, each under the lock ---------------------------------------------------------------

def set_ephe_path(path: str) -> None:
    lib = _libswe()
    with _lock:
        lib.swe_set_ephe_path(str(path).encode())


def set_sid_mode(mode: int, t0: float = 0.0, ayan_t0: float = 0.0) -> None:
    """pyswisseph's one-argument form hides `t0` and `ayan_t0`; both must be 0.0 for Lahiri as we use it,
    and passing anything else silently shifts the ayanamsa."""
    lib = _libswe()
    with _lock:
        lib.swe_set_sid_mode(int(mode), float(t0), float(ayan_t0))


def calc_ut(jd: float, body: int, flags: int) -> tuple[tuple[float, ...], int]:
    """(six values, returned flags) - the same shape pyswisseph gives. values[0] is longitude, values[3]
    its daily speed. The RETURNED flags matter: `core.ephemeris_in_use` reads them to tell whether the
    .se1 files answered or Moshier did, so they must be surfaced rather than discarded."""
    lib = _libswe()
    values = (ctypes.c_double * 6)()
    err = ctypes.create_string_buffer(_ERR_LEN)
    with _lock:
        returned = lib.swe_calc_ut(float(jd), int(body), int(flags), values, err)
    if returned < 0:
        raise SweError(err.value.decode(errors="replace") or f"swe_calc_ut failed for body {body}")
    return tuple(values), int(returned)


def get_ayanamsa_ut(jd: float) -> float:
    lib = _libswe()
    with _lock:
        return float(lib.swe_get_ayanamsa_ut(float(jd)))


def houses_ex(jd: float, lat: float, lon: float, hsys: bytes, flags: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """(cusps, ascmc); ascmc[0] is the ascendant.

    Two argument-order traps, both silent. pyswisseph takes (jd, lat, lon, hsys, flags); the C function
    takes (jd, iflag, geolat, geolon, hsys, ...) - flags SECOND and latitude before longitude. And `hsys`
    is a C int, not a string: b"W" (whole sign) has to be passed as 87. A wrong code does not error, it
    returns a DIFFERENT house system.
    """
    lib = _libswe()
    cusps = (ctypes.c_double * 13)()
    ascmc = (ctypes.c_double * 10)()
    code = hsys if isinstance(hsys, int) else ord(hsys.decode() if isinstance(hsys, bytes) else hsys)
    with _lock:
        returned = lib.swe_houses_ex(float(jd), int(flags), float(lat), float(lon), int(code), cusps, ascmc)
    if returned < 0:
        raise SweError(f"swe_houses_ex failed at lat={lat}, lon={lon}")
    return tuple(cusps), tuple(ascmc)


def rise_trans(jd: float, body: int, rsmi: int, geopos: tuple, atpress: float, attemp: float,
               flags: int) -> tuple[int, tuple[float, ...]]:
    """(return value, times). A NON-ZERO return is not always an error.

    -2 is "the event does not occur" - a polar day or night - and it is a LEGITIMATE ANSWER, which
    `core.sunrise` turns into a ValueError itself. libswe fills `serr` for it all the same ("rise or set
    not found for planet 0"), so the first version of this function raised on it and 7 of the 200 golden
    charts failed. Measured against pyswisseph on those same charts: it returns -2 and raises nothing. So
    the test caught a real behaviour difference, which is exactly the return-convention risk the sizing
    named, and the rule is: -2 is returned, every other negative with a message is an error.
    """
    lib = _libswe()
    position = (ctypes.c_double * 3)(*[float(v) for v in geopos])
    times = (ctypes.c_double * 10)()
    err = ctypes.create_string_buffer(_ERR_LEN)
    with _lock:
        returned = lib.swe_rise_trans(float(jd), int(body), None, int(flags), int(rsmi), position,
                                      float(atpress), float(attemp), times, err)
    if returned < 0 and returned != RISE_NOT_FOUND and err.value:
        raise SweError(err.value.decode(errors="replace"))
    return int(returned), tuple(times)
