from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import hardening
from app.ai.chat_routes import router as consultation_router
from app.ai.routes import router as report_router
from app.ai.entitlement import warn_if_unlocked_in_production
from app.api import router as api_router
from app.payments import service as payments_service
from app.payments.routes import router as payments_router
from app.pdf.routes import router as pdf_router
from app.rashifal import scheduler as rashifal_scheduler
from app.web import STATIC_DIR
from app.web import router as web_router
from app.web.rashifal import router as rashifal_router
from app.web.seo import router as seo_router

_docs = not hardening.is_production()  # no Swagger UI on the public site (it also needs a CDN the CSP forbids)
app = FastAPI(title="AI Astrology Platform", docs_url="/docs" if _docs else None, redoc_url=None,
              openapi_url="/openapi.json" if _docs else None)
app.include_router(api_router)
app.include_router(report_router)
app.include_router(consultation_router)
app.include_router(pdf_router)
app.include_router(payments_router)
warn_if_unlocked_in_production()
app.router.on_startup.append(payments_service.resume_unfinished)  # paid orders interrupted by a restart
app.router.on_startup.append(rashifal_scheduler.start_if_enabled)  # no-op unless RASHIFAL_SCHEDULER=1
app.router.on_shutdown.append(rashifal_scheduler.stop)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Three files browsers and phones fetch from the ROOT whatever the <head> says, so a /static/ URL alone is
# not enough: a bare /favicon.ico request is made by every browser before it has parsed any markup, iOS asks
# for /apple-touch-icon.png when a page has no apple-touch link, and the manifest is conventionally at the
# root so its scope covers the whole site. They are the same bytes the /static/ mount serves.
_ROOT_FILES = {
    "/favicon.ico": ("icons/favicon.ico", "image/x-icon"),
    "/apple-touch-icon.png": ("icons/apple-touch-icon-180.png", "image/png"),
    "/site.webmanifest": ("site.webmanifest", "application/manifest+json"),
}


def _root_file(path: str):
    name, media = _ROOT_FILES[path]
    return FileResponse(STATIC_DIR / name, media_type=media,
                        headers={"Cache-Control": "public, max-age=86400"})


for _path in _ROOT_FILES:
    app.add_api_route(_path, (lambda p=_path: (lambda: _root_file(p)))(), include_in_schema=False)


app.include_router(seo_router)
app.include_router(web_router)
app.include_router(rashifal_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
hardening.install(app)  # config check, security headers + CSP, gzip, static caching, /health/ready, 404/500 pages
