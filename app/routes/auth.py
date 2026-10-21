from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import RolUsuario
from app.seguridad import (
    cerrar_sesion,
    destino_seguro,
    inicio_para_rol,
    iniciar_sesion,
)
from app.services.usuarios import autenticar
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


@router.get("/login", response_class=HTMLResponse)
def formulario(request: Request, siguiente: str = Query("", alias="next")):
    rol = request.session.get("rol")
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
    destino = destino_seguro(siguiente) or inicio_para_rol(usuario.rol)
    return RedirectResponse(destino, status_code=303)


@router.post("/logout")
def salir(request: Request):
    cerrar_sesion(request)
    return RedirectResponse("/login", status_code=303)
