from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import func, select

from app.models import (
    Arbitro,
    Cancha,
    CategoriaArbitro,
    CategoriaTorneo,
    ConceptoMovimiento,
    Designacion,
    EstadoDesignacion,
    EstadoPartido,
    ModalidadPago,
    MovimientoCuentaCorriente,
    Partido,
    RolDesignacion,
    TipoMovimiento,
    Torneo,
)
from app.services.tarifas import TarifaNoEncontrada, crear_tarifa
from app.services.liquidacion import (
    CantidadDesignacionesInvalida,
    PartidoNoLiquidable,
    ResultadoLiquidacion,
    TarifaFaltante,
    liquidar_partido,
)
from app.services.viaticos import (
    PrecioCombustibleNoEncontrado,
    ViaticoInvalido,
    crear_precio_combustible,
)

UTC = timezone.utc
FECHA_PARTIDO = datetime(2026, 3, 15, 15, 0, tzinfo=UTC)
FECHA_DESIGNACION = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)

_secuencia = count(1)


def _categoria(db_session, nombre=None):
    nombre = nombre or f"Categoria {next(_secuencia)}"
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.flush()
    return categoria


def _torneo(db_session, categoria=None, **kwargs):
    categoria = categoria or _categoria(db_session)
    datos = dict(
        nombre=f"Torneo {next(_secuencia)}",
        categoria_torneo_id=categoria.id,
    )
    datos.update(kwargs)
    torneo = Torneo(**datos)
    db_session.add(torneo)
    db_session.flush()
    return torneo


def _cancha(db_session, **kwargs):
    datos = dict(nombre=f"Cancha {next(_secuencia)}")
    datos.update(kwargs)
    cancha = Cancha(**datos)
    db_session.add(cancha)
    db_session.flush()
    return cancha


def _partido(db_session, torneo=None, cancha=None, **kwargs):
    torneo = torneo or _torneo(db_session)
    cancha = cancha or _cancha(db_session)
    datos = dict(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=FECHA_PARTIDO,
        equipo_local="Local FC",
        equipo_visitante="Visitante FC",
        estado=EstadoPartido.DESIGNADO,
    )
    datos.update(kwargs)
    partido = Partido(**datos)
    db_session.add(partido)
    db_session.flush()
    return partido


def _arbitro(db_session, *, categoria=None):
    n = next(_secuencia)
    arbitro = Arbitro(
        legajo=f"L-{n:04d}",
        nombre="Ana",
        apellido="Gomez",
        dni=f"30{n:07d}",
        categoria=categoria,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _designacion(
    db_session,
    partido,
    *,
    rol=RolDesignacion.PRINCIPAL,
    arbitro=None,
    estado=EstadoDesignacion.CONFIRMADA,
    honorario=None,
    usa_auto=False,
):
    arbitro = arbitro or _arbitro(db_session)
    designacion = Designacion(
        partido_id=partido.id,
        arbitro_id=arbitro.id,
        rol=rol,
        estado=estado,
        fecha_designacion=FECHA_DESIGNACION,
        honorario=honorario,
        usa_auto=usa_auto,
    )
    db_session.add(designacion)
    db_session.flush()
    return designacion


def _tarifa(
    db_session,
    categoria,
    *,
    rol=RolDesignacion.PRINCIPAL,
    monto=Decimal("1000.00"),
    desde=date(2026, 1, 1),
    hasta=None,
    categoria_arbitro=None,
):
    return crear_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=rol,
        categoria_arbitro=categoria_arbitro,
        monto_base=monto,
        vigencia_desde=desde,
        vigencia_hasta=hasta,
    )


def _movimientos(db_session):
    return (
        db_session.execute(
            select(MovimientoCuentaCorriente).order_by(MovimientoCuentaCorriente.id)
        )
        .scalars()
        .all()
    )


def _precio(db_session, *, valor=Decimal("1000.000"), desde=date(2026, 1, 1), hasta=None):
    return crear_precio_combustible(
        db_session,
        precio_litro=valor,
        vigencia_desde=desde,
        vigencia_hasta=hasta,
    )


def _de_designacion(db_session, designacion_id):
    return (
        db_session.execute(
            select(MovimientoCuentaCorriente)
            .where(MovimientoCuentaCorriente.designacion_id == designacion_id)
            .order_by(MovimientoCuentaCorriente.concepto)
        )
        .scalars()
        .all()
    )


def _por_designacion(db_session):
    """Honorario por designación (el concepto que fija el monto del partido)."""
    return {
        m.designacion_id: m
        for m in db_session.execute(
            select(MovimientoCuentaCorriente).where(
                MovimientoCuentaCorriente.concepto == ConceptoMovimiento.HONORARIO
            )
        ).scalars()
    }


def test_liquida_partido_designado_y_crea_movimientos(db_session):
    partido = _partido(db_session)
    categoria = partido.torneo.categoria
    _tarifa(db_session, categoria, rol=RolDesignacion.PRINCIPAL, monto=Decimal("1000.00"))
    _tarifa(
        db_session, categoria, rol=RolDesignacion.ASISTENTE_1, monto=Decimal("700.00")
    )
    principal = _designacion(db_session, partido, rol=RolDesignacion.PRINCIPAL)
    asistente = _designacion(db_session, partido, rol=RolDesignacion.ASISTENTE_1)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado == ResultadoLiquidacion(
        movimientos_creados=2,
        designaciones_omitidas=0,
        periodo="2026-03",
        retenciones_creadas=2,
    )
    movimientos = _movimientos(db_session)
    assert len(movimientos) == 4
    por_id = _por_designacion(db_session)

    mov_principal = por_id[principal.id]
    assert mov_principal.arbitro_id == principal.arbitro_id
    assert mov_principal.monto == Decimal("1000.00")
    assert mov_principal.tipo is TipoMovimiento.CREDITO
    assert mov_principal.concepto is ConceptoMovimiento.HONORARIO
    assert mov_principal.fecha == FECHA_PARTIDO.date()
    assert mov_principal.periodo == "2026-03"
    assert mov_principal.descripcion == f"Honorario partido {partido.id} - PRINCIPAL"

    mov_asistente = por_id[asistente.id]
    assert mov_asistente.monto == Decimal("700.00")
    assert mov_asistente.periodo == "2026-03"


def test_cambia_estado_del_partido_a_jugado(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido.torneo.categoria)
    _designacion(db_session, partido)

    liquidar_partido(db_session, partido=partido)

    assert partido.estado is EstadoPartido.JUGADO


def test_congela_honorario_en_la_designacion(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    designacion = _designacion(db_session, partido)
    assert designacion.honorario is None

    liquidar_partido(db_session, partido=partido)

    assert designacion.honorario == Decimal("1000.00")


def test_usa_la_tarifa_vigente_a_la_fecha_del_partido(db_session):
    partido = _partido(db_session)
    categoria = partido.torneo.categoria
    _tarifa(
        db_session,
        categoria,
        monto=Decimal("1000.00"),
        desde=date(2026, 3, 1),
        hasta=date(2026, 3, 31),
    )
    _tarifa(
        db_session,
        categoria,
        monto=Decimal("1500.00"),
        desde=date(2026, 4, 1),
        hasta=None,
    )
    designacion = _designacion(db_session, partido)

    liquidar_partido(db_session, partido=partido)

    assert _por_designacion(db_session)[designacion.id].monto == Decimal("1000.00")


def test_es_idempotente(db_session):
    partido = _partido(db_session)
    categoria = partido.torneo.categoria
    _tarifa(db_session, categoria, rol=RolDesignacion.PRINCIPAL, monto=Decimal("1000.00"))
    _tarifa(
        db_session, categoria, rol=RolDesignacion.ASISTENTE_1, monto=Decimal("700.00")
    )
    _designacion(db_session, partido)
    _designacion(db_session, partido, rol=RolDesignacion.ASISTENTE_1)

    liquidar_partido(db_session, partido=partido)
    total_antes = len(_movimientos(db_session))

    segundo = liquidar_partido(db_session, partido=partido)

    assert segundo == ResultadoLiquidacion(
        movimientos_creados=0, designaciones_omitidas=2, periodo="2026-03"
    )
    assert len(_movimientos(db_session)) == total_antes == 4


def test_omite_designacion_que_ya_tiene_movimiento(db_session):
    partido = _partido(db_session)
    categoria = partido.torneo.categoria
    _tarifa(db_session, categoria, rol=RolDesignacion.PRINCIPAL, monto=Decimal("1000.00"))
    _tarifa(
        db_session, categoria, rol=RolDesignacion.ASISTENTE_1, monto=Decimal("700.00")
    )
    principal = _designacion(db_session, partido, rol=RolDesignacion.PRINCIPAL)
    asistente = _designacion(db_session, partido, rol=RolDesignacion.ASISTENTE_1)
    db_session.add(
        MovimientoCuentaCorriente(
            arbitro_id=principal.arbitro_id,
            designacion_id=principal.id,
            fecha=FECHA_PARTIDO.date(),
            tipo=TipoMovimiento.CREDITO,
            concepto=ConceptoMovimiento.HONORARIO,
            monto=Decimal("1000.00"),
            periodo="2026-03",
        )
    )
    db_session.flush()

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.movimientos_creados == 1
    assert resultado.designaciones_omitidas == 1
    assert set(_por_designacion(db_session)) == {principal.id, asistente.id}
    assert len(_movimientos(db_session)) == 3


@pytest.mark.parametrize(
    "estado",
    [
        EstadoDesignacion.AUSENTE,
        EstadoDesignacion.RECHAZADA,
        EstadoDesignacion.PROPUESTA,
    ],
)
def test_designaciones_no_liquidables_no_cobran(db_session, estado):
    partido = _partido(db_session)
    _designacion(db_session, partido, estado=estado)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.movimientos_creados == 0
    assert resultado.designaciones_omitidas == 0
    assert _movimientos(db_session) == []
    assert partido.estado is EstadoPartido.JUGADO


def test_cumplida_y_confirmada_si_cobran(db_session):
    partido = _partido(db_session)
    categoria = partido.torneo.categoria
    _tarifa(db_session, categoria, rol=RolDesignacion.PRINCIPAL, monto=Decimal("1000.00"))
    _tarifa(
        db_session, categoria, rol=RolDesignacion.ASISTENTE_1, monto=Decimal("700.00")
    )
    _designacion(
        db_session,
        partido,
        rol=RolDesignacion.PRINCIPAL,
        estado=EstadoDesignacion.CUMPLIDA,
    )
    _designacion(
        db_session,
        partido,
        rol=RolDesignacion.ASISTENTE_1,
        estado=EstadoDesignacion.CONFIRMADA,
    )

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.movimientos_creados == 2
    assert resultado.designaciones_omitidas == 0


def test_falta_tarifa_aborta_sin_escribir_nada(db_session):
    partido = _partido(db_session)
    categoria = partido.torneo.categoria
    _tarifa(db_session, categoria, rol=RolDesignacion.PRINCIPAL, monto=Decimal("1000.00"))
    _designacion(db_session, partido, rol=RolDesignacion.PRINCIPAL)
    _designacion(db_session, partido, rol=RolDesignacion.ASISTENTE_1)

    with pytest.raises(TarifaNoEncontrada):
        liquidar_partido(db_session, partido=partido)

    total = db_session.execute(
        select(func.count()).select_from(MovimientoCuentaCorriente)
    ).scalar_one()
    assert total == 0
    assert partido.estado is EstadoPartido.DESIGNADO


def test_error_de_tarifa_incluye_la_designacion(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido.torneo.categoria, rol=RolDesignacion.PRINCIPAL)
    principal = _designacion(
        db_session, partido, rol=RolDesignacion.PRINCIPAL
    )
    designacion_sin_tarifa = _designacion(
        db_session, partido, rol=RolDesignacion.ASISTENTE_1
    )

    with pytest.raises(TarifaFaltante) as excinfo:
        liquidar_partido(db_session, partido=partido)

    error = excinfo.value
    assert error.designacion_id == designacion_sin_tarifa.id
    assert error.partido_id == partido.id
    assert error.rol is RolDesignacion.ASISTENTE_1
    assert error.fecha == FECHA_PARTIDO.date()
    assert error.designacion_id != principal.id


@pytest.mark.parametrize(
    "estado", [EstadoPartido.SUSPENDIDO, EstadoPartido.REPROGRAMADO]
)
def test_partido_no_liquidable(db_session, estado):
    partido = _partido(db_session, estado=estado)

    with pytest.raises(PartidoNoLiquidable):
        liquidar_partido(db_session, partido=partido)


def test_partido_programado_no_es_liquidable(db_session):
    partido = _partido(db_session, estado=EstadoPartido.PROGRAMADO)

    with pytest.raises(PartidoNoLiquidable):
        liquidar_partido(db_session, partido=partido)


def test_partido_ya_jugado_se_puede_reliquidar_sin_duplicar(db_session):
    partido = _partido(db_session, estado=EstadoPartido.JUGADO)
    _tarifa(db_session, partido.torneo.categoria)
    _designacion(db_session, partido)

    primero = liquidar_partido(db_session, partido=partido)
    segundo = liquidar_partido(db_session, partido=partido)

    assert primero.movimientos_creados == 1
    assert segundo.movimientos_creados == 0
    assert segundo.designaciones_omitidas == 1
    assert len(_movimientos(db_session)) == 2


def test_roles_distintos_usan_su_propia_tarifa(db_session):
    partido = _partido(db_session)
    categoria = partido.torneo.categoria
    _tarifa(db_session, categoria, rol=RolDesignacion.PRINCIPAL, monto=Decimal("1000.00"))
    _tarifa(
        db_session, categoria, rol=RolDesignacion.ASISTENTE_1, monto=Decimal("700.00")
    )
    principal = _designacion(db_session, partido, rol=RolDesignacion.PRINCIPAL)
    asistente = _designacion(db_session, partido, rol=RolDesignacion.ASISTENTE_1)

    liquidar_partido(db_session, partido=partido)

    por_id = _por_designacion(db_session)
    assert por_id[principal.id].monto == Decimal("1000.00")
    assert por_id[asistente.id].monto == Decimal("700.00")


def test_respeta_honorario_ya_congelado(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    designacion = _designacion(db_session, partido, honorario=Decimal("500.00"))

    liquidar_partido(db_session, partido=partido)

    assert _por_designacion(db_session)[designacion.id].monto == Decimal("500.00")
    assert designacion.honorario == Decimal("500.00")


def test_partido_sin_designaciones_elegibles_no_crea_nada(db_session):
    partido = _partido(db_session)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado == ResultadoLiquidacion(
        movimientos_creados=0, designaciones_omitidas=0, periodo="2026-03"
    )
    assert _movimientos(db_session) == []
    assert partido.estado is EstadoPartido.JUGADO


def test_periodo_se_deriva_de_la_fecha_del_partido(db_session):
    partido = _partido(
        db_session,
        fecha_hora=datetime(2026, 12, 31, 21, 30, tzinfo=UTC),
    )
    _tarifa(db_session, partido.torneo.categoria)
    designacion = _designacion(db_session, partido)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.periodo == "2026-12"
    assert _por_designacion(db_session)[designacion.id].periodo == "2026-12"
    assert _por_designacion(db_session)[designacion.id].fecha == date(2026, 12, 31)


def test_partido_sin_auto_no_genera_viatico(db_session):
    cancha = _cancha(db_session, litros_viatico=Decimal("10.00"))
    partido = _partido(db_session, cancha=cancha)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    _precio(db_session)
    _designacion(db_session, partido)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.movimientos_creados == 1
    assert resultado.viaticos_creados == 0
    assert len(_movimientos(db_session)) == 2
    assert {m.concepto for m in _movimientos(db_session)} == {
        ConceptoMovimiento.HONORARIO,
        ConceptoMovimiento.RETENCION,
    }


def test_partido_con_auto_genera_viatico(db_session):
    cancha = _cancha(db_session, litros_viatico=Decimal("12.00"))
    partido = _partido(db_session, cancha=cancha)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    _precio(db_session, valor=Decimal("1000.000"))
    designacion = _designacion(db_session, partido, usa_auto=True)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.movimientos_creados == 1
    assert resultado.viaticos_creados == 1
    movimientos = _de_designacion(db_session, designacion.id)
    assert len(movimientos) == 3
    viatico = next(
        m for m in movimientos if m.concepto is ConceptoMovimiento.VIATICO
    )
    assert viatico.tipo is TipoMovimiento.CREDITO
    assert viatico.designacion_id == designacion.id
    assert viatico.arbitro_id == designacion.arbitro_id
    assert viatico.monto == Decimal("12000.00")
    assert viatico.periodo == "2026-03"
    assert viatico.fecha == FECHA_PARTIDO.date()
    assert viatico.descripcion == f"Viático partido {partido.id} - 12.00 L"


def test_cancha_con_cero_km_no_genera_viatico(db_session):
    cancha = _cancha(db_session, litros_viatico=Decimal("0.00"))
    partido = _partido(db_session, cancha=cancha)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    _designacion(db_session, partido, usa_auto=True)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.viaticos_creados == 0
    assert len(_movimientos(db_session)) == 2


def test_viatico_usa_precio_de_la_fecha_del_partido(db_session):
    cancha = _cancha(db_session, litros_viatico=Decimal("10.00"))
    partido = _partido(db_session, cancha=cancha)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    _precio(
        db_session,
        valor=Decimal("1000.000"),
        desde=date(2026, 3, 1),
        hasta=date(2026, 3, 31),
    )
    _precio(
        db_session,
        valor=Decimal("1200.000"),
        desde=date(2026, 4, 1),
        hasta=None,
    )
    designacion = _designacion(db_session, partido, usa_auto=True)

    liquidar_partido(db_session, partido=partido)

    viatico = next(
        m
        for m in _de_designacion(db_session, designacion.id)
        if m.concepto is ConceptoMovimiento.VIATICO
    )
    assert viatico.monto == Decimal("10000.00")


def test_falta_precio_combustible_aborta_todo(db_session):
    cancha = _cancha(db_session, litros_viatico=Decimal("10.00"))
    partido = _partido(db_session, cancha=cancha)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    _designacion(db_session, partido, usa_auto=True)

    with pytest.raises(PrecioCombustibleNoEncontrado):
        liquidar_partido(db_session, partido=partido)

    assert _movimientos(db_session) == []
    assert partido.estado is EstadoPartido.DESIGNADO


def test_dos_designaciones_con_auto_es_invalido(db_session):
    cancha = _cancha(db_session, litros_viatico=Decimal("10.00"))
    partido = _partido(db_session, cancha=cancha)
    _tarifa(db_session, partido.torneo.categoria, rol=RolDesignacion.PRINCIPAL)
    _precio(db_session)
    _designacion(db_session, partido, rol=RolDesignacion.PRINCIPAL, usa_auto=True)
    _designacion(db_session, partido, rol=RolDesignacion.ASISTENTE_1, usa_auto=True)

    with pytest.raises(ViaticoInvalido):
        liquidar_partido(db_session, partido=partido)

    assert _movimientos(db_session) == []
    assert partido.estado is EstadoPartido.DESIGNADO


def test_viatico_es_idempotente(db_session):
    cancha = _cancha(db_session, litros_viatico=Decimal("10.00"))
    partido = _partido(db_session, cancha=cancha)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    _precio(db_session)
    _designacion(db_session, partido, usa_auto=True)

    primero = liquidar_partido(db_session, partido=partido)
    total_antes = len(_movimientos(db_session))

    segundo = liquidar_partido(db_session, partido=partido)

    assert primero.viaticos_creados == 1
    assert primero.movimientos_creados == 1
    assert segundo.viaticos_creados == 0
    assert segundo.movimientos_creados == 0
    assert len(_movimientos(db_session)) == total_antes == 3


def test_honorario_y_viatico_coexisten_para_la_misma_designacion(db_session):
    cancha = _cancha(db_session, litros_viatico=Decimal("15.00"))
    partido = _partido(db_session, cancha=cancha)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    _precio(db_session, valor=Decimal("800.000"))
    designacion = _designacion(db_session, partido, usa_auto=True)

    liquidar_partido(db_session, partido=partido)

    movimientos = _de_designacion(db_session, designacion.id)
    assert len(movimientos) == 3
    assert {m.concepto for m in movimientos} == {
        ConceptoMovimiento.HONORARIO,
        ConceptoMovimiento.RETENCION,
        ConceptoMovimiento.VIATICO,
    }
    montos = {m.concepto: m.monto for m in movimientos}
    assert montos[ConceptoMovimiento.HONORARIO] == Decimal("1000.00")
    assert montos[ConceptoMovimiento.VIATICO] == Decimal("12000.00")


def test_ausente_con_auto_no_genera_viatico(db_session):
    cancha = _cancha(db_session, litros_viatico=Decimal("10.00"))
    partido = _partido(db_session, cancha=cancha)
    _tarifa(db_session, partido.torneo.categoria, rol=RolDesignacion.PRINCIPAL)
    _designacion(db_session, partido, rol=RolDesignacion.PRINCIPAL)
    _designacion(
        db_session,
        partido,
        rol=RolDesignacion.ASISTENTE_1,
        estado=EstadoDesignacion.AUSENTE,
        usa_auto=True,
    )

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.movimientos_creados == 1
    assert resultado.viaticos_creados == 0
    assert len(_movimientos(db_session)) == 2

def _escenario_u11(db_session, cantidad, categoria_arbitro=None):
    categoria_u11 = _categoria(db_session, nombre="U11")
    categoria_doble = _categoria(db_session, nombre="U11_DOBLE")
    _tarifa(
        db_session,
        categoria_u11,
        rol=None,
        categoria_arbitro=CategoriaArbitro.UNICA,
        monto=Decimal("19600.00"),
    )
    _tarifa(
        db_session,
        categoria_doble,
        rol=None,
        categoria_arbitro=CategoriaArbitro.UNICA,
        monto=Decimal("31900.00"),
    )
    torneo = _torneo(db_session, categoria=categoria_u11)
    partido = _partido(db_session, torneo=torneo)
    roles = (
        RolDesignacion.PRINCIPAL,
        RolDesignacion.ASISTENTE_1,
        RolDesignacion.ASISTENTE_2,
    )
    return partido, [
        _designacion(
            db_session,
            partido,
            rol=roles[i],
            arbitro=_arbitro(db_session, categoria=categoria_arbitro),
        )
        for i in range(cantidad)
    ]


def _honorarios(db_session, designaciones):
    ids = [d.id for d in designaciones]
    return [
        m.monto
        for m in db_session.execute(
            select(MovimientoCuentaCorriente)
            .where(
                MovimientoCuentaCorriente.designacion_id.in_(ids),
                MovimientoCuentaCorriente.concepto == ConceptoMovimiento.HONORARIO,
            )
            .order_by(MovimientoCuentaCorriente.id)
        ).scalars()
    ]


def test_u11_con_un_arbitro_cobra_la_tarifa_individual(db_session):
    partido, designaciones = _escenario_u11(db_session, cantidad=1)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.movimientos_creados == 1
    assert _honorarios(db_session, designaciones) == [Decimal("19600.00")]


def test_u11_con_dos_arbitros_reparte_la_tarifa_doble(db_session):
    partido, designaciones = _escenario_u11(db_session, cantidad=2)

    resultado = liquidar_partido(db_session, partido=partido)

    montos = _honorarios(db_session, designaciones)
    assert resultado.movimientos_creados == 2
    assert montos == [Decimal("15950.00"), Decimal("15950.00")]
    assert sum(montos) == Decimal("31900.00")


def test_u11_con_tres_arbitros_es_invalido(db_session):
    partido, _ = _escenario_u11(db_session, cantidad=3)

    with pytest.raises(CantidadDesignacionesInvalida):
        liquidar_partido(db_session, partido=partido)

    assert _movimientos(db_session) == []
    assert partido.estado is EstadoPartido.DESIGNADO


def test_u11_doble_es_idempotente(db_session):
    partido, designaciones = _escenario_u11(db_session, cantidad=2)

    primero = liquidar_partido(db_session, partido=partido)
    segundo = liquidar_partido(db_session, partido=partido)

    assert primero.movimientos_creados == 2
    assert segundo.movimientos_creados == 0
    assert len(_honorarios(db_session, designaciones)) == 2


def test_u11_individual_usa_la_tarifa_unica_sin_importar_el_escalafon(db_session):
    partido, designaciones = _escenario_u11(
        db_session, cantidad=1, categoria_arbitro=CategoriaArbitro.CAT_A
    )

    liquidar_partido(db_session, partido=partido)

    assert _honorarios(db_session, designaciones) == [Decimal("19600.00")]


def test_otra_categoria_con_dos_arbitros_no_reparte_tarifa(db_session):
    categoria = _categoria(db_session, nombre="U19")
    _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.UNICA,
        monto=Decimal("31600.00"),
    )
    torneo = _torneo(db_session, categoria=categoria)
    partido = _partido(db_session, torneo=torneo)
    designaciones = [
        _designacion(db_session, partido, rol=RolDesignacion.PRINCIPAL),
        _designacion(db_session, partido, rol=RolDesignacion.ASISTENTE_1),
    ]

    liquidar_partido(db_session, partido=partido)

    assert _honorarios(db_session, designaciones) == [
        Decimal("31600.00"),
        Decimal("31600.00"),
    ]


# --------------------------------------------------------------------------
# Retención del 10% (RN-30)
# --------------------------------------------------------------------------


def test_en_cancha_acredita_el_honorario_y_debita_la_retencion(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    designacion = _designacion(db_session, partido)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.retenciones_creadas == 1
    movimientos = _de_designacion(db_session, designacion.id)
    honorario = next(
        m for m in movimientos if m.concepto is ConceptoMovimiento.HONORARIO
    )
    retencion = next(
        m for m in movimientos if m.concepto is ConceptoMovimiento.RETENCION
    )
    assert honorario.tipo is TipoMovimiento.CREDITO
    assert honorario.monto == Decimal("1000.00")
    assert retencion.tipo is TipoMovimiento.DEBITO
    assert retencion.monto == Decimal("100.00")
    assert designacion.honorario == Decimal("1000.00")


def test_diferido_tambien_acredita_el_100_y_debita_retencion(db_session):
    partido = _partido(db_session, modalidad_pago=ModalidadPago.DIFERIDO)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    designacion = _designacion(db_session, partido)

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.retenciones_creadas == 1
    movimientos = _de_designacion(db_session, designacion.id)
    assert len(movimientos) == 2
    honorario = next(
        m for m in movimientos if m.concepto is ConceptoMovimiento.HONORARIO
    )
    retencion = next(
        m for m in movimientos if m.concepto is ConceptoMovimiento.RETENCION
    )
    assert honorario.tipo is TipoMovimiento.CREDITO
    assert honorario.monto == Decimal("1000.00")
    assert retencion.tipo is TipoMovimiento.DEBITO
    assert retencion.monto == Decimal("100.00")
    assert designacion.honorario == Decimal("1000.00")


def test_ambas_modalidades_dejan_el_mismo_neto(db_session):
    en_cancha = _partido(db_session, equipo_local="Uno")
    diferido = _partido(
        db_session, equipo_local="Dos", modalidad_pago=ModalidadPago.DIFERIDO
    )
    for partido in (en_cancha, diferido):
        _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    designacion_local = _designacion(db_session, en_cancha)
    designacion_diferida = _designacion(db_session, diferido)

    liquidar_partido(db_session, partido=en_cancha)
    liquidar_partido(db_session, partido=diferido)

    def neto(designacion):
        total = Decimal("0.00")
        for movimiento in _de_designacion(db_session, designacion.id):
            if movimiento.concepto is ConceptoMovimiento.RETENCION:
                total -= movimiento.monto
            else:
                total += movimiento.monto
        return total

    assert neto(designacion_local) == neto(designacion_diferida) == Decimal("900.00")


def test_la_retencion_no_toca_el_viatico(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    _precio(db_session, valor=Decimal("1000.000"))
    partido.cancha.litros_viatico = Decimal("10")
    designacion = _designacion(db_session, partido, usa_auto=True)

    liquidar_partido(db_session, partido=partido)

    viatico = next(
        m
        for m in _de_designacion(db_session, designacion.id)
        if m.concepto is ConceptoMovimiento.VIATICO
    )
    assert viatico.monto == Decimal("10000.00")


def test_la_retencion_es_idempotente(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1000.00"))
    _designacion(db_session, partido)

    liquidar_partido(db_session, partido=partido)
    partido.estado = EstadoPartido.DESIGNADO
    segundo = liquidar_partido(db_session, partido=partido)

    assert segundo.movimientos_creados == 0
    assert segundo.retenciones_creadas == 0
    assert len(_movimientos(db_session)) == 2


def test_la_retencion_redondea_half_up(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("1234.56"))
    designacion = _designacion(db_session, partido)

    liquidar_partido(db_session, partido=partido)

    retencion = next(
        m
        for m in _de_designacion(db_session, designacion.id)
        if m.concepto is ConceptoMovimiento.RETENCION
    )
    assert retencion.monto == Decimal("123.46")


def test_la_retencion_usa_el_honorario_congelado(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido.torneo.categoria, monto=Decimal("9999.00"))
    designacion = _designacion(db_session, partido, honorario=Decimal("1000.00"))

    liquidar_partido(db_session, partido=partido)

    movimientos = {m.concepto: m for m in _de_designacion(db_session, designacion.id)}
    assert movimientos[ConceptoMovimiento.HONORARIO].monto == Decimal("1000.00")
    assert movimientos[ConceptoMovimiento.RETENCION].monto == Decimal("100.00")


def test_u11_doble_retencion_sobre_la_parte_de_cada_arbitro(db_session):
    categoria_u11 = _categoria(db_session, nombre="U11")
    _tarifa(db_session, categoria_u11, monto=Decimal("19600.00"))
    categoria_doble = _categoria(db_session, nombre="U11_DOBLE")
    _tarifa(db_session, categoria_doble, monto=Decimal("31900.00"))
    partido = _partido(db_session, torneo=_torneo(db_session, categoria=categoria_u11))
    primera = _designacion(db_session, partido)
    segunda = _designacion(db_session, partido, rol=RolDesignacion.ASISTENTE_1)

    liquidar_partido(db_session, partido=partido)

    for designacion in (primera, segunda):
        movimientos = {
            m.concepto: m for m in _de_designacion(db_session, designacion.id)
        }
        assert movimientos[ConceptoMovimiento.HONORARIO].monto == Decimal("15950.00")
        assert movimientos[ConceptoMovimiento.RETENCION].monto == Decimal("1595.00")
