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
from app.models.usuario import Usuario
from app.presentacion import es_htmx, respuesta_o_fragmento, toast
from app.services.cierres import (
    CierreInvalido,
    PeriodoCerrado,
    PeriodoNoCerrado,
    PeriodoYaCerrado,
    ReaperturaInvalida,
    auditoria_periodos,
    cerrar_periodo,
    cerrar_periodos,
    periodos_cerrados,
    reabrir_periodo,
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


_PAGINA = "tesoreria/index.html"
_PARCIAL_ACTUALIZACION = "partials/tesoreria/actualizacion.html"
_PARCIAL_AJUSTE = "partials/tesoreria/modal_ajuste.html"


def _contexto(
    db: Session,
    *,
    periodo: str = "",
    error: str | None = None,
    mensaje: str | None = None,
    aviso: str | None = None,
    form: dict[str, str] | None = None,
    abrir_ajuste: bool = False,
) -> dict:
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

    return {
        "seccion": "tesoreria",
        "cuentas": saldos(db, periodo=periodo_normalizado),
        "partidos": partidos,
        "cobros": cobros,
        "arbitros": arbitros,
        "periodo": periodo_normalizado,
        "periodo_exportacion": periodo_normalizado or _periodo_actual(),
        "periodos_cerrados": cerrados,
        "reaperturas": auditoria_periodos(db),
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
    }


def _render(
    request: Request,
    db: Session,
    *,
    status_code: int = 200,
    **kwargs,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        _PAGINA,
        _contexto(db, **kwargs),
        status_code=status_code,
    )


def _fragmento(
    request: Request,
    db: Session,
    *,
    principal: str,
    regiones: tuple[str, ...],
    status_code: int = 200,
    trigger: str | None = None,
    headers: dict[str, str] | None = None,
    **kwargs,
) -> HTMLResponse:
    """Renderiza las regiones afectadas por una acción de tesorería.

    Sólo se invoca desde la rama ``HX-Request``; el parcial principal ocupa el
    swap normal y el resto se marca ``hx-swap-oob`` para refrescar la página.
    """
    contexto = _contexto(db, **kwargs)
    contexto["principal"] = principal
    contexto["regiones"] = list(regiones)
    return respuesta_o_fragmento(
        request,
        completa=_PAGINA,
        parcial=_PARCIAL_ACTUALIZACION,
        contexto=contexto,
        status_code=status_code,
        headers=headers,
        trigger=trigger,
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
def liquidar(
    partido_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_tesorero),
):
    partido = db.get(Partido, partido_id)
    if partido is None:
        raise HTTPException(status_code=404, detail="No existe el partido.")

    try:
        resultado = liquidar_partido(
            db, partido=partido, usuario_id=usuario.id
        )
        db.commit()
    except (ErrorLiquidacion, TarifaNoEncontrada, ErrorViatico, PeriodoCerrado) as exc:
        db.rollback()
        if es_htmx(request):
            return _fragmento(
                request,
                db,
                principal="partidos",
                regiones=("partidos", "cuentas"),
                status_code=400,
                headers={
                    "HX-Retarget": "#partidos-a-liquidar",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return RedirectResponse(
            "/tesoreria?" + urlencode({"error": str(exc)}), status_code=303
        )

    mensaje = (
        f"Partido liquidado: {resultado.movimientos_creados} honorario(s), "
        f"{resultado.retenciones_creadas} retención(es)"
        f" y {resultado.viaticos_creados} viático(s)"
        f" · período {resultado.periodo}."
    )
    if es_htmx(request):
        return _fragmento(
            request,
            db,
            principal="partidos",
            regiones=("partidos", "cuentas"),
            trigger=toast("success", mensaje),
        )
    return RedirectResponse(
        "/tesoreria?" + urlencode({"ok": mensaje}), status_code=303
    )


@router.post("/tesoreria/cobro/{partido_id}")
def cobrar(
    partido_id: int,
    request: Request,
    db: Session = Depends(get_db),
    fecha_cobro: str = Form(""),
    usuario: Usuario = Depends(requiere_tesorero),
):
    try:
        resultado = registrar_cobro(
            db,
            partido_id=partido_id,
            fecha_cobro=fecha_cobro,
            usuario_id=usuario.id,
        )
        db.commit()
    except (CobroInvalido, PeriodoCerrado) as exc:
        db.rollback()
        if es_htmx(request):
            return _fragmento(
                request,
                db,
                principal="cobros",
                regiones=("cobros", "cuentas"),
                status_code=400,
                headers={
                    "HX-Retarget": "#cobros-diferidos",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return RedirectResponse(
            "/tesoreria?" + urlencode({"error": str(exc)}), status_code=303
        )

    mensaje = f"Cobro registrado a los {resultado.dias} días del partido."
    if resultado.en_mora:
        mensaje += (
            f" Mora: se reintegró la retención de "
            f"{resultado.reintegros_creados} designación(es)."
        )
    if es_htmx(request):
        return _fragmento(
            request,
            db,
            principal="cobros",
            regiones=("cobros", "cuentas"),
            trigger=toast("success", mensaje),
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
    usuario: Usuario = Depends(requiere_tesorero),
):
    try:
        cierre = cerrar_periodo(
            db, periodo=periodo, usuario_id=usuario.id
        )
        db.commit()
    except PeriodoYaCerrado as exc:
        db.rollback()
        if es_htmx(request):
            return _fragmento(
                request,
                db,
                principal="cierres",
                regiones=("cierres",),
                trigger=toast("info", str(exc)),
            )
        return _render(
            request, db, aviso=str(exc), periodo=periodo
        )
    except CierreInvalido as exc:
        db.rollback()
        if es_htmx(request):
            return _fragmento(
                request,
                db,
                principal="cierres",
                regiones=("cierres",),
                status_code=400,
                headers={
                    "HX-Retarget": "#cierres-periodo",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
                periodo=periodo,
            )
        return _render(
            request, db, error=str(exc), periodo=periodo, status_code=400
        )

    mensaje = (
        f"Período {cierre.periodo} cerrado: ya no admite altas, designaciones, "
        "liquidaciones, cobros ni ajustes."
    )
    if es_htmx(request):
        return _fragmento(
            request,
            db,
            principal="cierres",
            regiones=("cierres", "cuentas", "partidos", "cobros"),
            trigger=toast("success", mensaje),
        )
    return RedirectResponse(
        "/tesoreria?" + urlencode({"ok": mensaje}), status_code=303
    )


@router.post("/tesoreria/cierres-lote")
def cerrar_lote(
    request: Request,
    db: Session = Depends(get_db),
    periodos: str = Form(""),
    usuario: Usuario = Depends(requiere_tesorero),
):
    try:
        cierres = cerrar_periodos(
            db, periodos=periodos, usuario_id=usuario.id
        )
        db.commit()
    except PeriodoYaCerrado as exc:
        db.rollback()
        if es_htmx(request):
            return _fragmento(
                request,
                db,
                principal="cierres",
                regiones=("cierres",),
                trigger=toast("info", str(exc)),
            )
        return _render(request, db, aviso=str(exc))
    except CierreInvalido as exc:
        db.rollback()
        if es_htmx(request):
            return _fragmento(
                request,
                db,
                principal="cierres",
                regiones=("cierres",),
                status_code=400,
                headers={
                    "HX-Retarget": "#cierres-periodo",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return _render(request, db, error=str(exc), status_code=400)

    detalle = ", ".join(cierre.periodo for cierre in cierres)
    mensaje = (
        f"{len(cierres)} período(s) cerrado(s): {detalle}. "
        "Ya no admiten altas, liquidaciones, cobros ni ajustes."
    )
    if es_htmx(request):
        return _fragmento(
            request,
            db,
            principal="cierres",
            regiones=("cierres", "cuentas", "partidos", "cobros"),
            trigger=toast("success", mensaje),
        )
    return RedirectResponse(
        "/tesoreria?" + urlencode({"ok": mensaje}), status_code=303
    )


@router.post("/tesoreria/reapertura")
def reabrir(
    request: Request,
    db: Session = Depends(get_db),
    periodo: str = Form(""),
    motivo: str = Form(""),
    usuario: Usuario = Depends(requiere_tesorero),
):
    try:
        cierre = reabrir_periodo(
            db, periodo=periodo, motivo=motivo, usuario_id=usuario.id
        )
        db.commit()
    except (ReaperturaInvalida, PeriodoNoCerrado) as exc:
        db.rollback()
        if es_htmx(request):
            return _fragmento(
                request,
                db,
                principal="cierres",
                regiones=("cierres",),
                status_code=400,
                headers={
                    "HX-Retarget": "#cierres-periodo",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return _render(request, db, error=str(exc), status_code=400)

    mensaje = (
        f"Período {cierre.periodo} reabierto: vuelve a admitir altas, "
        "liquidaciones, cobros y ajustes. La reapertura quedó auditada."
    )
    if es_htmx(request):
        return _fragmento(
            request,
            db,
            principal="cierres",
            regiones=("cierres", "cuentas", "partidos", "cobros"),
            trigger=toast("success", mensaje),
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
    usuario: Usuario = Depends(requiere_tesorero),
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
            usuario_id=usuario.id,
        )
        db.commit()
    except (AjusteInvalido, PeriodoCerrado) as exc:
        db.rollback()
        if es_htmx(request):
            return respuesta_o_fragmento(
                request,
                completa=_PAGINA,
                parcial=_PARCIAL_AJUSTE,
                contexto=_contexto(
                    db, error=str(exc), form=form, abrir_ajuste=True
                ),
                status_code=400,
                headers={
                    "HX-Retarget": "#modalAjuste",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return _render(
            request,
            db,
            error=str(exc),
            form=form,
            status_code=400,
            abrir_ajuste=True,
        )

    mensaje = "Ajuste registrado en la cuenta corriente."
    if es_htmx(request):
        return _fragmento(
            request,
            db,
            principal="cuentas",
            regiones=("cuentas",),
            trigger=toast("success", mensaje, cerrar_modal="modalAjuste"),
        )
    return RedirectResponse(
        "/tesoreria?" + urlencode({"ok": mensaje}), status_code=303
    )
