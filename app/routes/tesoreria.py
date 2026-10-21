from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib.parse import urlencode

from datetime import datetime, timezone

from app.database import get_db
from app.models.arbitro import Arbitro
from app.models.enums import (
    ConceptoMovimiento,
    EstadoPartido,
    ModalidadPago,
    TipoMovimiento,
)
from app.models.partido import Partido
from app.services.cierres import (
    CierreInvalido,
    PeriodoCerrado,
    PeriodoYaCerrado,
    cerrar_periodo,
    periodos_cerrados,
)
from app.services.exportacion import (
    liquidacion_csv,
    liquidacion_mensual,
    liquidacion_pdf,
)
from app.services.liquidacion import (
    CobroInvalido,
    ErrorLiquidacion,
    liquidar_partido,
    registrar_cobro,
)
from app.services.tarifas import TarifaNoEncontrada
from app.services.tesoreria import (
    CONCEPTOS_MANUALES,
    AjusteInvalido,
    crear_ajuste,
    movimientos_de_arbitro,
    normalizar_periodo,
    saldo_de,
    saldos,
)
from app.services.viaticos import ErrorViatico
from app.seguridad import requiere_tesorero
from app.templating import templates
from app.tiempo import a_local

router = APIRouter(dependencies=[Depends(requiere_tesorero)])

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

ESTADO_CLASES = {
    EstadoPartido.DESIGNADO.value: "primary",
    EstadoPartido.JUGADO.value: "success",
}

TIPO_ETIQUETAS = {
    TipoMovimiento.CREDITO.value: "Crédito",
    TipoMovimiento.DEBITO.value: "Débito",
}


def _periodo_actual() -> str:
    """Período en curso en hora de Argentina (AAAA-MM)."""
    return a_local(datetime.now(timezone.utc)).strftime("%Y-%m")


def _render(
    request: Request,
    db: Session,
    *,
    periodo: str = "",
    error: str | None = None,
    mensaje: str | None = None,
    aviso: str | None = None,
    form: dict[str, str] | None = None,
    status_code: int = 200,
    abrir_ajuste: bool = False,
) -> HTMLResponse:
    periodo_normalizado = ""
    try:
        periodo_normalizado = normalizar_periodo(periodo) or ""
    except AjusteInvalido as exc:
        error = error or str(exc)

    partidos = (
        db.execute(
            select(Partido)
            .where(Partido.estado == EstadoPartido.DESIGNADO)
            .order_by(Partido.fecha_hora, Partido.id)
        )
        .scalars()
        .all()
    )

    arbitros = (
        db.execute(
            select(Arbitro)
            .order_by(Arbitro.apellido, Arbitro.nombre, Arbitro.id)
        )
        .scalars()
        .all()
    )

    cobros = (
        db.execute(
            select(Partido)
            .where(
                Partido.modalidad_pago == ModalidadPago.DIFERIDO,
                Partido.fecha_cobro.is_(None),
            )
            .order_by(Partido.fecha_hora, Partido.id)
        )
        .scalars()
        .all()
    )

    cerrados = periodos_cerrados(db)

    return templates.TemplateResponse(
        request,
        "tesoreria/index.html",
        {
            "seccion": "tesoreria",
            "cuentas": saldos(db, periodo=periodo_normalizado),
            "partidos": partidos,
            "cobros": cobros,
            "arbitros": arbitros,
            "periodo": periodo_normalizado,
            "periodo_exportacion": periodo_normalizado or _periodo_actual(),
            "periodos_cerrados": cerrados,
            "periodo_cerrado": bool(
                periodo_normalizado and periodo_normalizado in cerrados
            ),
            "periodo_actual": _periodo_actual(),
            "concepto_etiquetas": CONCEPTO_ETIQUETAS,
            "conceptos_ajuste": [
                (concepto.value, CONCEPTO_ETIQUETAS[concepto.value])
                for concepto in sorted(
                    CONCEPTOS_MANUALES,
                    key=lambda item: CONCEPTO_ETIQUETAS[item.value],
                )
            ],
            "estado_clases": ESTADO_CLASES,
            "error": error,
            "mensaje": mensaje,
            "aviso": aviso,
            "form": form or {},
            "abrir_ajuste": abrir_ajuste,
        },
        status_code=status_code,
    )


@router.get("/tesoreria", response_class=HTMLResponse)
def panel(
    request: Request,
    db: Session = Depends(get_db),
    periodo: str = Query(""),
    ok: str = Query(""),
    error: str = Query(""),
):
    return _render(
        request,
        db,
        periodo=periodo,
        mensaje=ok or None,
        error=error or None,
    )


@router.get("/tesoreria/arbitros/{arbitro_id}", response_class=HTMLResponse)
def detalle_cuenta(
    arbitro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    periodo: str = Query(""),
):
    arbitro = db.get(Arbitro, arbitro_id)
    if arbitro is None:
        raise HTTPException(status_code=404, detail="No existe el árbitro.")

    error = None
    periodo_normalizado = ""
    try:
        periodo_normalizado = normalizar_periodo(periodo) or ""
    except AjusteInvalido as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "tesoreria/arbitro.html",
        {
            "seccion": "tesoreria",
            "arbitro": arbitro,
            "movimientos": movimientos_de_arbitro(
                db, arbitro_id=arbitro.id, periodo=periodo_normalizado
            ),
            "saldo": saldo_de(
                db, arbitro_id=arbitro.id, periodo=periodo_normalizado
            ),
            "periodo": periodo_normalizado,
            "concepto_etiquetas": CONCEPTO_ETIQUETAS,
            "tipo_etiquetas": TIPO_ETIQUETAS,
            "error": error,
        },
        status_code=400 if error else 200,
    )


@router.post("/tesoreria/liquidar-partido/{partido_id}")
def liquidar(partido_id: int, db: Session = Depends(get_db)):
    partido = db.get(Partido, partido_id)
    if partido is None:
        raise HTTPException(status_code=404, detail="No existe el partido.")

    try:
        resultado = liquidar_partido(db, partido=partido)
        db.commit()
    except (ErrorLiquidacion, TarifaNoEncontrada, ErrorViatico, PeriodoCerrado) as exc:
        db.rollback()
        return RedirectResponse(
            "/tesoreria?" + urlencode({"error": str(exc)}), status_code=303
        )

    mensaje = (
        f"Partido liquidado: {resultado.movimientos_creados} honorario(s), "
        f"{resultado.retenciones_creadas} retención(es)"
        f" y {resultado.viaticos_creados} viático(s)"
        f" · período {resultado.periodo}."
    )
    return RedirectResponse(
        "/tesoreria?" + urlencode({"ok": mensaje}), status_code=303
    )


@router.post("/tesoreria/cobro/{partido_id}")
def cobrar(
    partido_id: int,
    db: Session = Depends(get_db),
    fecha_cobro: str = Form(""),
):
    try:
        resultado = registrar_cobro(
            db, partido_id=partido_id, fecha_cobro=fecha_cobro
        )
        db.commit()
    except (CobroInvalido, PeriodoCerrado) as exc:
        db.rollback()
        return RedirectResponse(
            "/tesoreria?" + urlencode({"error": str(exc)}), status_code=303
        )

    mensaje = f"Cobro registrado a los {resultado.dias} días del partido."
    if resultado.en_mora:
        mensaje += (
            f" Mora: se reintegró la retención de "
            f"{resultado.reintegros_creados} designación(es)."
        )
    return RedirectResponse(
        "/tesoreria?" + urlencode({"ok": mensaje}), status_code=303
    )


@router.get("/tesoreria/exportar")
def exportar(
    db: Session = Depends(get_db),
    periodo: str = Query(""),
    formato: str = Query("csv"),
):
    try:
        periodo_normalizado = normalizar_periodo(periodo)
    except AjusteInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not periodo_normalizado:
        raise HTTPException(
            status_code=400,
            detail="Indicá el período a exportar (formato AAAA-MM).",
        )

    filas = liquidacion_mensual(db, periodo=periodo_normalizado)
    formato = formato.strip().lower()
    if formato == "csv":
        contenido = liquidacion_csv(filas).encode("utf-8")
        media_type = "text/csv; charset=utf-8"
    elif formato == "pdf":
        contenido = liquidacion_pdf(filas, periodo=periodo_normalizado)
        media_type = "application/pdf"
    else:
        raise HTTPException(
            status_code=400, detail="Formato inválido: usá 'csv' o 'pdf'."
        )

    return Response(
        content=contenido,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="liquidacion-{periodo_normalizado}.{formato}"'
            )
        },
    )


@router.post("/tesoreria/cierre-periodo")
def cerrar(
    request: Request,
    db: Session = Depends(get_db),
    periodo: str = Form(""),
):
    try:
        cierre = cerrar_periodo(db, periodo=periodo)
        db.commit()
    except PeriodoYaCerrado as exc:
        db.rollback()
        return _render(
            request, db, aviso=str(exc), periodo=periodo
        )
    except CierreInvalido as exc:
        db.rollback()
        return _render(
            request, db, error=str(exc), periodo=periodo, status_code=400
        )

    mensaje = (
        f"Período {cierre.periodo} cerrado: ya no admite altas, designaciones, "
        "liquidaciones, cobros ni ajustes."
    )
    return RedirectResponse(
        "/tesoreria?" + urlencode({"ok": mensaje}), status_code=303
    )


@router.post("/tesoreria/ajuste", response_class=HTMLResponse)
def registrar_ajuste(
    request: Request,
    db: Session = Depends(get_db),
    arbitro_id: str = Form(""),
    tipo: str = Form(""),
    concepto: str = Form(""),
    monto: str = Form(""),
    periodo: str = Form(""),
    descripcion: str = Form(""),
):
    form = {
        "arbitro_id": arbitro_id,
        "tipo": tipo,
        "concepto": concepto,
        "monto": monto,
        "periodo": periodo,
        "descripcion": descripcion,
    }
    try:
        crear_ajuste(
            db,
            arbitro_id=arbitro_id,
            tipo=tipo,
            concepto=concepto,
            monto=monto,
            periodo=periodo,
            descripcion=descripcion,
        )
        db.commit()
    except (AjusteInvalido, PeriodoCerrado) as exc:
        db.rollback()
        return _render(
            request,
            db,
            error=str(exc),
            form=form,
            status_code=400,
            abrir_ajuste=True,
        )

    mensaje = "Ajuste registrado en la cuenta corriente."
    return RedirectResponse(
        "/tesoreria?" + urlencode({"ok": mensaje}), status_code=303
    )
