from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import RolUsuario
from app.models.usuario import Usuario
from app.seguridad import (
    cerrar_sesion,
    destino_seguro,
    inicio_para_rol,
    iniciar_sesion,
    requiere_usuario,
)
from app.services.usuarios import UsuarioInvalido, autenticar, cambiar_password
from app.templating import templates

router = APIRouter()


def _login(
    request: Request,
    *,
    email: str = "",
    siguiente: str = "",
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "seccion": "login",
            "email": email,
            "next": siguiente,
            "error": error,
        },
        status_code=status_code,
    )


def _cambio(
    request: Request,
    usuario: Usuario,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "cambiar_password.html",
        {
            "seccion": "cambiar-password",
            "pendiente": usuario.debe_cambiar_password,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/login", response_class=HTMLResponse)
def formulario(request: Request, siguiente: str = Query("", alias="next")):
    rol = request.session.get("rol")
    if rol:
        if request.session.get("debe_cambiar_password"):
            return RedirectResponse("/cambiar-password", status_code=303)
        try:
            return RedirectResponse(
                inicio_para_rol(RolUsuario(rol)), status_code=303
            )
        except ValueError:
            pass
    return _login(request, siguiente=siguiente)


@router.post("/login", response_class=HTMLResponse)
def ingresar(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(""),
    password: str = Form(""),
    siguiente: str = Form("", alias="next"),
):
    usuario = autenticar(db, email=email, password=password)
    if usuario is None:
        return _login(
            request,
            email=email.strip(),
            siguiente=siguiente,
            error="Email o contraseña incorrectos.",
            status_code=401,
        )

    iniciar_sesion(request, usuario)
    if usuario.debe_cambiar_password:
        return RedirectResponse("/cambiar-password", status_code=303)

    destino = destino_seguro(siguiente) or inicio_para_rol(usuario.rol)
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
    return RedirectResponse(inicio_para_rol(usuario.rol), status_code=303)


@router.post("/logout")
def salir(request: Request):
    cerrar_sesion(request)
    return RedirectResponse("/login", status_code=303)
