"""/admin/mantra: every mantra page, its release date, and whether it is answering yet.

A READ, NOT A CONTROL PANEL. Release dates come from the registry and the gate is a pure function
of the date, so there is nothing here to press - which is the point. The page answers the question
"what goes out tomorrow, and is anything stuck?" without being able to change the answer by
accident.

It follows app/blog/admin.py: the same `require_admin` gate, the same `_page` helper so the nav and
the no-store headers are the dashboard's, and no JavaScript.
"""
from __future__ import annotations

import datetime as dt
import pathlib

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.admin.auth import require_admin
from app.mantra import texts as mantra_texts

EXPLAINERS = pathlib.Path(__file__).parent / "explainers"
LANGS = ("hi", "en")

router = APIRouter(prefix="/admin", include_in_schema=False)


def _page(*args, **kwargs):
    """Imported when called: app.admin.routes imports the web package, which imports this."""
    from app.admin.routes import _page as render  # noqa: PLC0415

    return render(*args, **kwargs)


def _status(text, today: dt.date) -> str:
    if text.slug in mantra_texts.UNSOURCED:
        return "no source"
    if not mantra_texts.is_verified(text):
        return "awaiting a read"
    if text.release is None:
        return "verified, unscheduled"
    if mantra_texts.is_live(text, today):
        return "live"
    return f"in {(text.release - today).days} days"


def rows(today: dt.date | None = None) -> list[dict]:
    """One row per text, in release order, with the unschedulable ones last."""
    today = today or mantra_texts.today()
    order = {slug: n for n, slug in enumerate(mantra_texts.RELEASE_ORDER)}
    texts = sorted(mantra_texts.PHASE_1,
                   key=lambda t: (order.get(t.slug, 999), t.slug))
    out = []
    for text in texts:
        verses = mantra_texts.verses(text.slug) if _has_text(text.slug) else ()
        out.append({
            "slug": text.slug,
            "name": text.names["hi"],
            "english": text.names["en"],
            "kind": text.kind,
            "verses": len(verses),
            "sources": len(text.sources),
            "reviewed": text.reviewed,
            "verified": mantra_texts.is_verified(text),
            "release": text.release.isoformat() if text.release else "",
            "status": _status(text, today),
            "live": mantra_texts.is_live(text, today),
            # AN EXPLAINER PER LANGUAGE OR THE PAGE IS HALF A PAGE. Shown per text so a missing
            # one is visible here rather than as a 500 on release morning.
            "explainers": [lang for lang in LANGS
                           if (EXPLAINERS / f"{text.slug}.{lang}.json").is_file()],
            "paths": [f"/{'' if lang == 'en' else lang + '/'}mantra/{text.slug}"
                      for lang in LANGS],
        })
    return out


def _has_text(slug: str) -> bool:
    return (mantra_texts.TEXTS_DIR / f"{slug}.json").is_file()


@router.get("/mantra", response_class=HTMLResponse)
def mantra_list(request: Request, actor: str = Depends(require_admin)) -> HTMLResponse:
    today = mantra_texts.today()
    table = rows(today)
    by_day: dict[str, list] = {}
    for row in table:
        if row["release"] and not row["live"]:
            by_day.setdefault(row["release"], []).append(row)
    return _page(request, actor, "mantra", "mantra_admin.html", {
        "rows": table,
        "today": today.isoformat(),
        "live_count": sum(1 for row in table if row["live"]),
        "scheduled_count": sum(1 for row in table if row["release"] and not row["live"]),
        "blocked": [row for row in table if not row["verified"]],
        "missing_explainers": [row for row in table
                               if row["verified"] and len(row["explainers"]) < len(LANGS)],
        "upcoming": sorted(by_day.items())[:6],
        "pages_per_day": mantra_texts.TEXTS_PER_DAY * len(LANGS),
    })
