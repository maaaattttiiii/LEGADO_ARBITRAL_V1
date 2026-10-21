from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cancha import Cancha
from app.models.enums import EstadoPartido, ModalidadPago
from app.models.torneo import Torneo
from app.services.partidos import PartidoInvalido, crear_partido, filtrar_partidos
from app.services.cierres import PeriodoCerrado
from app.templating import templates

router = APIRouter()

ESTADO_ETIQUETAS = {
    EstadoPartido.PROGRAMADO.value: "Programado",
    EstadoPartido.DESIGNADO.value: "Designado",
    EstadoPartido.JUGADO.value: "Jugado",
    EstadoPartido.SUSPENDIDO.value: "Suspendido",
    EstadoPartido.REPROGRAMADO.value: "Reprogramado",
}

ESTADO_CLASES = {
    EstadoPartido.PROGRAMADO.value: "secondary",
    EstadoPartido.DESIGNADO.value: "primary",
    EstadoPartido.JUGADO.value: "success",
    EstadoPartido.SUSPENDIDO.value: "warning",
    EstadoPartido.REPROGRAMADO.value: "info",
}

MODALIDAD_ETIQUETAS = {
    ModalidadPago.EN_CANCHA.value: "En cancha",
    ModalidadPago.DIFERIDO.value: "Diferido",
}


def _render(
    request: Request,
    db: Session,
    *,
    partidos,
    error: str | None = None,
    form: dict[str, str] | None = None,
    filtros: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    torneos = (
        db.execute(
            select(Torneo).order_by(Torneo.nombre, Torneo.id)
        )
        .scalars()
        .all()
    )
    canchas = (
        db.execute(
            select(Cancha).order_by(Cancha.nombre, Cancha.id)
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request,
        "partidos/index.html",
        {
            "seccion": "partidos",
            "partidos": partidos,
            "torneos": torneos,
            "canchas": canchas,
            "estado_etiquetas": ESTADO_ETIQUETAS,
            "estado_clases": ESTADO_CLASES,
            "modalidad_etiquetas": MODALIDAD_ETIQUETAS,
            "modalidades": [
                (modalidad.value, MODALIDAD_ETIQUETAS[modalidad.value])
                for modalidad in ModalidadPago
            ],
            "error": error,
            "form": form or {},
            "filtros": filtros or {},
        },
        status_code=status_code,
    )


@router.get("/partidos", response_class=HTMLResponse)
def listar_partidos(
    request: Request,
    db: Session = Depends(get_db),
    torneo_id: str = Query(""),
    desde: str = Query(""),
    hasta: str = Query(""),
):
    filtros = {"torneo_id": torneo_id, "desde": desde, "hasta": hasta}
    error = None
    try:
        partidos = filtrar_partidos(
            db, torneo_id=torneo_id, desde=desde, hasta=hasta
        )
    except PartidoInvalido as exc:
        error = str(exc)
        partidos = filtrar_partidos(db)

    return _render(request, db, partidos=partidos, filtros=filtros, error=error)


@router.post("/partidos", response_class=HTMLResponse)
def alta_partido(
    request: Request,
    db: Session = Depends(get_db),
    torneo_id: str = Form(""),
    cancha_id: str = Form(""),
    fecha: str = Form(""),
    hora: str = Form(""),
    equipo_local: str = Form(""),
    equipo_visitante: str = Form(""),
    observaciones: str = Form(""),
    modalidad_pago: str = Form(""),
):
    form = {
        "torneo_id": torneo_id,
        "cancha_id": cancha_id,
        "fecha": fecha,
        "hora": hora,
        "equipo_local": equipo_local,
        "equipo_visitante": equipo_visitante,
        "observaciones": observaciones,
        "modalidad_pago": modalidad_pago,
    }
    try:
        crear_partido(
            db,
            torneo_id=torneo_id,
            cancha_id=cancha_id,
            fecha=fecha,
            hora=hora,
            equipo_local=equipo_local,
            equipo_visitante=equipo_visitante,
            observaciones=observaciones,
            modalidad_pago=modalidad_pago,
        )
        db.commit()
    except (PartidoInvalido, PeriodoCerrado) as exc:
        db.rollback()
        return _render(
            request,
            db,
            partidos=filtrar_partidos(db),
            error=str(exc),
            form=form,
            status_code=400,
        )

    return RedirectResponse("/partidos", status_code=303)
