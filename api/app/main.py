import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from .api import router
from .seed import seed

# index.html fica na raiz do repositório (ou em /app/static dentro do container)
ROOT = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parents[2]))

SECURITY_HEADERS = {
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=31536000",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed()
    yield


app = FastAPI(title="VitaSchedule API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)


@app.middleware("http")
async def guard(request: Request, call_next):
    # Defesa extra contra CSRF (além do cookie SameSite=Strict): mutações exigem este cabeçalho,
    # que um formulário HTML de outro site não consegue enviar.
    if request.url.path.startswith("/api") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("x-requested-with") != "vitaschedule":
            return JSONResponse({"detail": "Requisição inválida."}, status_code=403)
    response = await call_next(request)
    for k, val in SECURITY_HEADERS.items():
        response.headers.setdefault(k, val)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "index.html", media_type="text/html")
