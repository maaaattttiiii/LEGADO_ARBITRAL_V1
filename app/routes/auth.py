import math

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import LimitadorLogin
from app.models.enums import RolUsuario
from app.models.usuario import Usuario
from app.presentacion import (
    es_htmx,
    redireccion_htmx,
    respuesta_o_fragmento,
    toast,
)
from app.seguridad import (
    cerrar_sesion,
    destino_seguro,
    inicio_para_rol,
    iniciar_sesion,
    requiere_usuario,
)
from app.services.usuarios import UsuarioInvalido, autenticar, cambiar_password

router = APIRouter()


def _limitador(request: Request) -> LimitadorLogin:
    limitador = getattr(request.app.state, "limiter", None)
    if limitador is None:
        limitador = request.app.state.limiter = LimitadorLogin()
    return limitador


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def _espera(segundos: int) -> str:
    minutos = max(1, math.ceil(segundos / 60))
    return f"{minutos} minuto{'s' if minutos != 1 else ''}"


def _login(
    request: Request,
    *,
    email: str = "",
    siguiente: str = "",
    error: str | None = None,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    return respuesta_o_fragmento(
        request,
        completa="login.html",
        parcial="partials/auth/login_panel.html",
        contexto={
            "seccion": "login",
            "email": email,
            "next": siguiente,
            "error": error,
        },
        status_code=status_code,
        headers=headers,
        trigger=toast("error", error) if error else None,
    )


def _cambio(
    request: Request,
    usuario: Usuario,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return respuesta_o_fragmento(
        request,
        completa="cambiar_password.html",
        parcial="partials/auth/cambiar_password_panel.html",
        contexto={
            "seccion": "cambiar-password",
            "pendiente": usuario.debe_cambiar_password,
            "error": error,
        },
        status_code=status_code,
        trigger=toast("error", error) if error else None,
    )


@router.get("/login", response_class=HTMLResponse)
def formulario(request: Request, siguiente: str = Query("", alias="next")):
    rol = request.session.get("rol")
    if rol:
        destino = None
        if request.session.get("debe_cambiar_password"):
            destino = "/cambiar-password"
        else:
            try:
                destino = inicio_para_rol(RolUsuario(rol))
            except ValueError:
                pass
        if destino:
            if es_htmx(request):
                return redireccion_htmx(destino)
            return RedirectResponse(destino, status_code=303)
    return _login(request, siguiente=siguiente)


@router.post("/login", response_class=HTMLResponse)
def ingresar(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(""),
    password: str = Form(""),
    siguiente: str = Form("", alias="next"),
):
    limitador = _limitador(request)
    ip = _ip(request)
    restante = limitador.segundos_bloqueado(ip, email)
    if restante:
        return _login(
            request,
            email=email.strip(),
            siguiente=siguiente,
            error=(
                "Demasiados intentos fallidos. "
                f"Probá de nuevo en {_espera(restante)}."
            ),
            status_code=429,
            headers={"Retry-After": str(restante)},
        )

    usuario = autenticar(db, email=email, password=password)
    if usuario is None:
        restante = limitador.registrar_fallo(ip, email)
        mensaje = "Email o contraseña incorrectos."
        headers = None
        if restante:
            mensaje = (
                "Demasiados intentos fallidos. "
                f"Probá de nuevo en {_espera(restante)}."
            )
            headers = {"Retry-After": str(restante)}
        return _login(
            request,
            email=email.strip(),
            siguiente=siguiente,
            error=mensaje,
            status_code=429 if restante else 401,
            headers=headers,
        )

    limitador.registrar_exito(ip, email)

    iniciar_sesion(request, usuario)
    if usuario.debe_cambiar_password:
        destino = "/cambiar-password"
    else:
        destino = destino_seguro(siguiente) or inicio_para_rol(usuario.rol)

    if es_htmx(request):
        return redireccion_htmx(destino)
    return RedirectResponse(destino, status_code=303)


@router.get("/cambiar-password", response_class=HTMLResponse)
def formulario_cambio(
    request: Request,
    usuario: Usuario = Depends(requiere_usuario),
):
    return _cambio(request, usuario)


@router.post("/cambiar-password", response_class=HTMLResponse)
def cambiar(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_usuario),
    actual: str = Form(""),
    nueva: str = Form(""),
    repetir: str = Form(""),
):
    try:
        cambiar_password(
            db,
            usuario,
            actual=actual,
            nueva=nueva,
            repetir=repetir,
        )
        db.commit()
    except UsuarioInvalido as exc:
        # El servicio valida antes de escribir: no hace falta rollback y así
        # no se invalidan objetos de la sesión.
        return _cambio(request, usuario, error=str(exc), status_code=400)

    request.session["debe_cambiar_password"] = False
    destino = inicio_para_rol(usuario.rol)
    if es_htmx(request):
        return redireccion_htmx(destino)
    return RedirectResponse(destino, status_code=303)


@router.post("/logout")
def salir(request: Request):
    cerrar_sesion(request)
    return RedirectResponse("/login", status_code=303)
