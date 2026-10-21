from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.torneo import CategoriaTorneo, Torneo
from app.services.torneos import TorneoInvalido, actualizar_torneo, cambiar_estado, crear_torneo
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
    torneos = (
        db.execute(select(Torneo).order_by(Torneo.nombre, Torneo.id))
        .scalars()
        .all()
    )
    categorias = (
        db.execute(
            select(CategoriaTorneo).order_by(
                CategoriaTorneo.orden, CategoriaTorneo.nombre
            )
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        request,
        "torneos/index.html",
        {
            "seccion": "torneos",
            "torneos": torneos,
            "categorias": categorias,
            "error": error,
            "form": form or {},
            "abrir_alta": abrir_alta,
        },
        status_code=status_code,
    )


def _obtener(db: Session, torneo_id: int) -> Torneo:
    torneo = db.get(Torneo, torneo_id)
    if torneo is None:
        raise HTTPException(status_code=404, detail="No existe el torneo.")
    return torneo


@router.get("/torneos", response_class=HTMLResponse)
def listar_torneos(request: Request, db: Session = Depends(get_db)):
    return _render(request, db)


@router.post("/torneos", response_class=HTMLResponse)
def alta_torneo(
    request: Request,
    db: Session = Depends(get_db),
    nombre: str = Form(""),
    categoria_torneo_id: str = Form(""),
    temporada: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_fin: str = Form(""),
):
    form = {
        "nombre": nombre,
        "categoria_torneo_id": categoria_torneo_id,
        "temporada": temporada,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }
    try:
        crear_torneo(
            db,
            nombre=nombre,
            categoria_torneo_id=categoria_torneo_id,
            temporada=temporada,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
        db.commit()
    except TorneoInvalido as exc:
        db.rollback()
        return _render(
            request, db, error=str(exc), form=form, status_code=400, abrir_alta=True
        )

    return RedirectResponse("/torneos", status_code=303)


@router.post("/torneos/{torneo_id}", response_class=HTMLResponse)
def editar_torneo(
    torneo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    nombre: str = Form(""),
    categoria_torneo_id: str = Form(""),
    temporada: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_fin: str = Form(""),
):
    torneo = _obtener(db, torneo_id)
    try:
        actualizar_torneo(
            db,
            torneo,
            nombre=nombre,
            categoria_torneo_id=categoria_torneo_id,
            temporada=temporada,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
        db.commit()
    except TorneoInvalido as exc:
        db.rollback()
        return _render(request, db, error=str(exc), status_code=400)

    return RedirectResponse("/torneos", status_code=303)


@router.post("/torneos/{torneo_id}/estado")
def estado_torneo(
    torneo_id: int,
    db: Session = Depends(get_db),
    activo: str = Form(""),
):
    torneo = _obtener(db, torneo_id)
    cambiar_estado(db, torneo, activo=activo)
    db.commit()
    return RedirectResponse("/torneos", status_code=303)
