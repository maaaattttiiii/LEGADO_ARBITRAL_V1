from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.routes import (
    arbitros,
    auth,
    canchas,
    designaciones,
    partidos,
    portal,
    tarifas,
    tesoreria,
    torneos,
)
from app.seguridad import (
    HTTPS_ONLY,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    SESSION_SECRET,
    AccesoDenegado,
    NoAutenticado,
)
from app.templating import templates

app = FastAPI(title="CABM - Colegio de Árbitros", version="0.1.0")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie=SESSION_COOKIE,
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=HTTPS_ONLY,
)

app.include_router(auth.router)
app.include_router(portal.router)
app.include_router(arbitros.router)
app.include_router(partidos.router)
app.include_router(designaciones.router)
app.include_router(tesoreria.router)
app.include_router(canchas.router)
app.include_router(torneos.router)
app.include_router(tarifas.router)


@app.exception_handler(NoAutenticado)
async def _login_requerido(
    request: Request, exc: NoAutenticado
) -> RedirectResponse:
    destino = request.url.path
    if request.url.query:
        destino = f"{destino}?{request.url.query}"
    return RedirectResponse(
        "/login?" + urlencode({"next": destino}), status_code=303
    )


@app.exception_handler(AccesoDenegado)
async def _prohibido(request: Request, exc: AccesoDenegado) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "403.html",
        {"seccion": None, "error": str(exc)},
        status_code=403,
    )
