from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cancha import Cancha
from app.services.canchas import CanchaInvalida, actualizar_cancha, cambiar_estado, crear_cancha
from app.templating import templates

router = APIRouter()


def _render(
    request: Request,
    db: Session,
    *,
    error: str | None = None,
    form: dict[str, str] | None = None,
    status_code: int = 200,
    abrir_alta: bool = False,
) -> HTMLResponse:
    canchas = (
        db.execute(select(Cancha).order_by(Cancha.nombre, Cancha.id))
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        request,
        "canchas/index.html",
        {
            "seccion": "canchas",
            "canchas": canchas,
            "error": error,
            "form": form or {},
            "abrir_alta": abrir_alta,
        },
        status_code=status_code,
    )


def _obtener(db: Session, cancha_id: int) -> Cancha:
    cancha = db.get(Cancha, cancha_id)
    if cancha is None:
        raise HTTPException(status_code=404, detail="No existe la cancha.")
    return cancha


@router.get("/canchas", response_class=HTMLResponse)
def listar_canchas(request: Request, db: Session = Depends(get_db)):
    return _render(request, db)


@router.post("/canchas", response_class=HTMLResponse)
def alta_cancha(
    request: Request,
    db: Session = Depends(get_db),
    nombre: str = Form(""),
    localidad: str = Form(""),
    direccion: str = Form(""),
    litros_viatico: str = Form(""),
):
    form = {
        "nombre": nombre,
        "localidad": localidad,
        "direccion": direccion,
        "litros_viatico": litros_viatico,
    }
    try:
        crear_cancha(
            db,
            nombre=nombre,
            localidad=localidad,
            direccion=direccion,
            litros_viatico=litros_viatico,
        )
        db.commit()
    except CanchaInvalida as exc:
        db.rollback()
        return _render(
            request, db, error=str(exc), form=form, status_code=400, abrir_alta=True
        )

    return RedirectResponse("/canchas", status_code=303)


@router.post("/canchas/{cancha_id}", response_class=HTMLResponse)
def editar_cancha(
    cancha_id: int,
    request: Request,
    db: Session = Depends(get_db),
    nombre: str = Form(""),
    localidad: str = Form(""),
    direccion: str = Form(""),
    litros_viatico: str = Form(""),
):
    cancha = _obtener(db, cancha_id)
    try:
        actualizar_cancha(
            db,
            cancha,
            nombre=nombre,
            localidad=localidad,
            direccion=direccion,
            litros_viatico=litros_viatico,
        )
        db.commit()
    except CanchaInvalida as exc:
        db.rollback()
        return _render(request, db, error=str(exc), status_code=400)

    return RedirectResponse("/canchas", status_code=303)


@router.post("/canchas/{cancha_id}/estado")
def estado_cancha(
    cancha_id: int,
    db: Session = Depends(get_db),
    activo: str = Form(""),
):
    cancha = _obtener(db, cancha_id)
    cambiar_estado(db, cancha, activo=activo)
    db.commit()
    return RedirectResponse("/canchas", status_code=303)
