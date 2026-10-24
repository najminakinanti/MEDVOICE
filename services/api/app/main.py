from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .config import get_settings, require_secrets
from .deps import known_origins
from .live_ws import router as live_router
from .routes import router
from .ui_api import router as ui_router

app = FastAPI(title="MedVoice Engine", version="0.1.0", docs_url="/v1/docs", openapi_url="/v1/openapi.json")


@app.on_event("startup")
def _check_config() -> None:
    require_secrets(get_settings())


@app.middleware("http")
async def cors(request: Request, call_next):
    """CORS: header hanya untuk origin yang terdaftar di salah satu client (union, cache 60 dtk).
    Penegakan per client dilakukan di deps.get_principal."""
    origin = request.headers.get("origin")
    allowed = False
    if origin:
        try:
            allowed = origin in known_origins()
        except Exception:
            allowed = False
    if request.method == "OPTIONS" and origin:
        r = Response(status_code=204 if allowed else 403)
    else:
        r = await call_next(request)
    if allowed:
        r.headers["Access-Control-Allow-Origin"] = origin
        r.headers["Vary"] = "Origin"
        r.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-API-Key"
        r.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
    r.headers["Cache-Control"] = "no-store"
    r.headers["X-Content-Type-Options"] = "nosniff"
    if request.url.path.startswith("/ui"):
        host = request.headers.get("host", "")
        try:                                  # widget: hanya origin client terdaftar yang boleh menyematkan UI
            ancestors = " ".join(sorted(known_origins()))
        except Exception:
            ancestors = ""
        r.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            f"connect-src 'self' ws://{host} wss://{host}; frame-ancestors 'self' " + ancestors)
    return r


app.include_router(router)
app.include_router(ui_router)
app.include_router(live_router)

_ui = Path(__file__).parent / "static"
if _ui.exists():
    app.mount("/ui", StaticFiles(directory=_ui, html=True), name="ui")
