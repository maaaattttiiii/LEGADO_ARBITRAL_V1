from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.limiter import LimitadorLogin
from app.presentacion import (
    es_htmx,
    redireccion_htmx,
    respuesta_o_fragmento,
    toast,
)
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
    CambioPasswordRequerido,
    NoAutenticado,
)


app = FastAPI(title="CABM - Colegio de Árbitros", version="0.1.0")
app.state.limiter = LimitadorLogin()

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
) -> Response:
    destino = request.url.path
    if request.url.query:
        destino = f"{destino}?{request.url.query}"
    login = "/login?" + urlencode({"next": destino})
    if es_htmx(request):
        return redireccion_htmx(login)
    return RedirectResponse(login, status_code=303)


@app.exception_handler(AccesoDenegado)
async def _prohibido(request: Request, exc: AccesoDenegado) -> HTMLResponse:
    mensaje = str(exc)
    return respuesta_o_fragmento(
        request,
        completa="403.html",
        parcial="partials/errors/403_panel.html",
        contexto={"seccion": None, "error": mensaje},
        status_code=403,
        trigger=toast("error", mensaje),
    )


@app.exception_handler(CambioPasswordRequerido)
async def _cambio_pendiente(
    request: Request, exc: CambioPasswordRequerido
) -> Response:
    if es_htmx(request):
        return redireccion_htmx("/cambiar-password")
    return RedirectResponse("/cambiar-password", status_code=303)
