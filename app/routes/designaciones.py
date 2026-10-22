from collections import defaultdict

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.arbitro import Arbitro
from app.models.designacion import Designacion
from app.models.enums import EstadoArbitro, EstadoDesignacion, EstadoPartido, RolDesignacion
from app.models.partido import Partido
from app.services.cierres import PeriodoCerrado
from app.services.designaciones import (
    CATEGORIA_U11,
    MAX_ARBITROS_U11,
    DesignacionInvalida,
    admite_cuarto,
    asignar_terna,
)
from app.presentacion import es_htmx, respuesta_o_fragmento, toast
from app.seguridad import requiere_tesorero
from app.templating import templates

router = APIRouter(dependencies=[Depends(requiere_tesorero)])

PAGINA = "designaciones/index.html"
PARCIAL_LISTADO = "partials/designaciones/listado.html"
PARCIAL_MODAL = "partials/designaciones/modal_terna.html"

ESTADOS_PENDIENTES = (
    EstadoPartido.PROGRAMADO,
    EstadoPartido.DESIGNADO,
    EstadoPartido.REPROGRAMADO,
)

ROL_ETIQUETAS = {
    RolDesignacion.PRINCIPAL.value: "Juez Principal",
    RolDesignacion.ASISTENTE_1.value: "Juez 2",
    RolDesignacion.ASISTENTE_2.value: "Juez 3",
    RolDesignacion.CUARTO.value: "Cuarto árbitro",
}

ESTADO_PARTIDO_CLASES = {
    EstadoPartido.PROGRAMADO.value: "secondary",
    EstadoPartido.DESIGNADO.value: "primary",
    EstadoPartido.REPROGRAMADO.value: "info",
}


def _filas(db: Session) -> list[dict]:
    partidos = (
        db.execute(
            select(Partido)
            .where(Partido.estado.in_(ESTADOS_PENDIENTES))
            .order_by(Partido.fecha_hora, Partido.id)
        )
        .scalars()
        .all()
    )
    if not partidos:
        return []

    designaciones = (
        db.execute(
            select(Designacion).where(
                Designacion.partido_id.in_([p.id for p in partidos]),
                Designacion.estado != EstadoDesignacion.RECHAZADA,
            )
        )
        .scalars()
        .all()
    )
    ternas: dict[int, dict] = defaultdict(dict)
    for designacion in designaciones:
        ternas[designacion.partido_id][designacion.rol] = designacion

    cache_cuarto: dict[tuple[int, object], bool] = {}
    filas = []
    for partido in partidos:
        clave = (partido.torneo.categoria_torneo_id, partido.fecha_hora.date())
        if clave not in cache_cuarto:
            cache_cuarto[clave] = admite_cuarto(db, partido)
        tiene_cuarto = cache_cuarto[clave]

        roles = [
            (RolDesignacion.PRINCIPAL, ROL_ETIQUETAS[RolDesignacion.PRINCIPAL.value]),
            (
                RolDesignacion.ASISTENTE_1,
                ROL_ETIQUETAS[RolDesignacion.ASISTENTE_1.value],
            ),
            (
                RolDesignacion.ASISTENTE_2,
                ROL_ETIQUETAS[RolDesignacion.ASISTENTE_2.value],
            ),
        ]
        if tiene_cuarto:
            roles.append(
                (RolDesignacion.CUARTO, ROL_ETIQUETAS[RolDesignacion.CUARTO.value])
            )

        es_u11 = partido.torneo.categoria.nombre == CATEGORIA_U11
        if es_u11:
            roles = roles[:MAX_ARBITROS_U11]

        terna = ternas.get(partido.id, {})
        filas.append(
            {
                "partido": partido,
                "terna": terna,
                "roles": roles,
                "tiene_cuarto": tiene_cuarto,
                "es_u11": es_u11,
                "roles_extra": len(terna) > len(roles),
                "auto": next((d for d in terna.values() if d.usa_auto), None),
            }
        )
    return filas


def _contexto(
    db: Session,
    *,
    error: str | None = None,
    form: dict[str, str] | None = None,
) -> dict:
    arbitros = (
        db.execute(
            select(Arbitro)
            .where(Arbitro.estado == EstadoArbitro.ACTIVO)
            .order_by(Arbitro.apellido, Arbitro.nombre, Arbitro.id)
        )
        .scalars()
        .all()
    )
    return {
        "seccion": "designaciones",
        "filas": _filas(db),
        "arbitros": arbitros,
        "rol_etiquetas": ROL_ETIQUETAS,
        "estado_partido_clases": ESTADO_PARTIDO_CLASES,
        "roles_auto": [
            (RolDesignacion.PRINCIPAL, ROL_ETIQUETAS[RolDesignacion.PRINCIPAL.value]),
            (
                RolDesignacion.ASISTENTE_1,
                ROL_ETIQUETAS[RolDesignacion.ASISTENTE_1.value],
            ),
            (
                RolDesignacion.ASISTENTE_2,
                ROL_ETIQUETAS[RolDesignacion.ASISTENTE_2.value],
            ),
            (RolDesignacion.CUARTO, ROL_ETIQUETAS[RolDesignacion.CUARTO.value]),
        ],
        "error": error,
        "form": form or {},
    }


def _fila(db: Session, partido_id: str) -> dict | None:
    return next(
        (fila for fila in _filas(db) if str(fila["partido"].id) == partido_id),
        None,
    )


def _render(
    request: Request,
    db: Session,
    *,
    error: str | None = None,
    form: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        PAGINA,
        _contexto(db, error=error, form=form),
        status_code=status_code,
    )


@router.get("/designaciones", response_class=HTMLResponse)
def listar_designaciones(request: Request, db: Session = Depends(get_db)):
    return _render(request, db)


@router.post("/designaciones", response_class=HTMLResponse)
def alta_designacion(
    request: Request,
    db: Session = Depends(get_db),
    partido_id: str = Form(""),
    principal_id: str = Form(""),
    asistente_1_id: str = Form(""),
    asistente_2_id: str = Form(""),
    cuarto_id: str = Form(""),
    auto_rol: str = Form(""),
):
    form = {
        "partido_id": partido_id,
        "principal_id": principal_id,
        "asistente_1_id": asistente_1_id,
        "asistente_2_id": asistente_2_id,
        "cuarto_id": cuarto_id,
        "auto_rol": auto_rol,
    }
    try:
        asignar_terna(
            db,
            partido_id=partido_id,
            principal_id=principal_id,
            asistente_1_id=asistente_1_id,
            asistente_2_id=asistente_2_id,
            cuarto_id=cuarto_id,
            auto_rol=auto_rol,
        )
        db.commit()
    except (DesignacionInvalida, PeriodoCerrado) as exc:
        db.rollback()
        if es_htmx(request):
            fila = _fila(db, partido_id)
            if fila is not None:
                contexto = _contexto(db, error=str(exc), form=form)
                contexto["fila"] = fila
                return respuesta_o_fragmento(
                    request,
                    completa=PAGINA,
                    parcial=PARCIAL_MODAL,
                    contexto=contexto,
                    status_code=400,
                    headers={
                        "HX-Retarget": f"#modalTerna{fila['partido'].id}",
                        "HX-Reswap": "outerHTML",
                    },
                    trigger=toast("error", str(exc)),
                )
            return respuesta_o_fragmento(
                request,
                completa=PAGINA,
                parcial=PARCIAL_LISTADO,
                contexto=_contexto(db, error=str(exc), form=form),
                status_code=400,
                trigger=toast("error", str(exc)),
            )
        return _render(request, db, error=str(exc), form=form, status_code=400)

    if es_htmx(request):
        return respuesta_o_fragmento(
            request,
            completa=PAGINA,
            parcial=PARCIAL_LISTADO,
            contexto=_contexto(db),
            trigger=toast("success", "Terna guardada."),
        )

    return RedirectResponse("/designaciones", status_code=303)
