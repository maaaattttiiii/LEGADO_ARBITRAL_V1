"""Portal del árbitro: solo sus propios partidos y su cuenta corriente."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.designacion import Designacion
from app.models.enums import (
    ConceptoMovimiento,
    EstadoDesignacion,
    RolDesignacion,
    TipoMovimiento,
)
from app.models.partido import Partido
from app.models.usuario import Usuario
from app.seguridad import requiere_arbitro
from app.services.tesoreria import movimientos_de_arbitro, saldo_de
from app.templating import templates

router = APIRouter()

ROL_ETIQUETAS = {
    RolDesignacion.PRINCIPAL.value: "Juez Principal",
    RolDesignacion.ASISTENTE_1.value: "Juez 2",
    RolDesignacion.ASISTENTE_2.value: "Juez 3",
    RolDesignacion.CUARTO.value: "Cuarto árbitro",
}

ESTADO_ETIQUETAS = {
    EstadoDesignacion.PROPUESTA.value: "Propuesta",
    EstadoDesignacion.CONFIRMADA.value: "Confirmada",
    EstadoDesignacion.CUMPLIDA.value: "Cumplida",
    EstadoDesignacion.AUSENTE.value: "Ausente",
    EstadoDesignacion.RECHAZADA.value: "Rechazada",
}

ESTADO_CLASES = {
    EstadoDesignacion.PROPUESTA.value: "warning",
    EstadoDesignacion.CONFIRMADA.value: "primary",
    EstadoDesignacion.CUMPLIDA.value: "success",
    EstadoDesignacion.AUSENTE.value: "danger",
    EstadoDesignacion.RECHAZADA.value: "secondary",
}

CONCEPTO_ETIQUETAS = {
    ConceptoMovimiento.HONORARIO.value: "Honorario",
    ConceptoMovimiento.VIATICO.value: "Viático",
    ConceptoMovimiento.DESCUENTO.value: "Descuento",
    ConceptoMovimiento.ADELANTO.value: "Adelanto",
    ConceptoMovimiento.PAGO.value: "Pago",
    ConceptoMovimiento.MULTA.value: "Multa",
    ConceptoMovimiento.AJUSTE.value: "Ajuste",
    ConceptoMovimiento.RETENCION.value: "Retención",
}

TIPO_ETIQUETAS = {
    TipoMovimiento.CREDITO.value: "Crédito",
    TipoMovimiento.DEBITO.value: "Débito",
}


@router.get("/mis-partidos", response_class=HTMLResponse)
def mis_partidos(
    request: Request,
    usuario: Usuario = Depends(requiere_arbitro),
    db: Session = Depends(get_db),
):
    designaciones = (
        db.execute(
            select(Designacion)
            .join(Partido, Designacion.partido_id == Partido.id)
            .where(Designacion.arbitro_id == usuario.arbitro_id)
            .order_by(Partido.fecha_hora.desc(), Designacion.id.desc())
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request,
        "portal/mis_partidos.html",
        {
            "seccion": "mis-partidos",
            "usuario": usuario,
            "designaciones": designaciones,
            "rol_etiquetas": ROL_ETIQUETAS,
            "estado_etiquetas": ESTADO_ETIQUETAS,
            "estado_clases": ESTADO_CLASES,
        },
    )


@router.get("/mi-cuenta", response_class=HTMLResponse)
def mi_cuenta(
    request: Request,
    usuario: Usuario = Depends(requiere_arbitro),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "portal/mi_cuenta.html",
        {
            "seccion": "mi-cuenta",
            "usuario": usuario,
            "movimientos": movimientos_de_arbitro(
                db, arbitro_id=usuario.arbitro_id
            ),
            "saldo": saldo_de(db, arbitro_id=usuario.arbitro_id),
            "concepto_etiquetas": CONCEPTO_ETIQUETAS,
            "tipo_etiquetas": TIPO_ETIQUETAS,
        },
    )
