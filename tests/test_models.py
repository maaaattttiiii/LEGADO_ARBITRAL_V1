from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import (
    Arbitro,
    Cancha,
    CategoriaTorneo,
    ConceptoMovimiento,
    Designacion,
    EstadoArbitro,
    EstadoDesignacion,
    EstadoPartido,
    MovimientoCuentaCorriente,
    Partido,
    RolDesignacion,
    TipoMovimiento,
    Torneo,
    calcular_saldo,
)

UTC = timezone.utc
FECHA_HORA_PARTIDO = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
FECHA_DESIGNACION = datetime(2026, 2, 20, 10, 0, tzinfo=UTC)


def _arbitro(db_session, **kwargs):
    datos = dict(legajo="L-001", nombre="Ana", apellido="Gomez", dni="30000001")
    datos.update(kwargs)
    arbitro = Arbitro(**datos)
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _cancha(db_session, **kwargs):
    datos = dict(nombre="Cancha Central")
    datos.update(kwargs)
    cancha = Cancha(**datos)
    db_session.add(cancha)
    db_session.flush()
    return cancha


def _torneo(db_session, **kwargs):
    categoria_nombre = kwargs.pop("categoria_nombre", "Primera")
    categoria = CategoriaTorneo(nombre=categoria_nombre)
    db_session.add(categoria)
    db_session.flush()
    datos = dict(nombre="Torneo Apertura 2026", categoria_torneo_id=categoria.id)
    datos.update(kwargs)
    torneo = Torneo(**datos)
    db_session.add(torneo)
    db_session.flush()
    return torneo


def _partido(db_session, torneo=None, cancha=None, **kwargs):
    torneo = torneo or _torneo(db_session)
    cancha = cancha or _cancha(db_session)
    datos = dict(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=FECHA_HORA_PARTIDO,
        equipo_local="Local FC",
        equipo_visitante="Visitante FC",
    )
    datos.update(kwargs)
    partido = Partido(**datos)
    db_session.add(partido)
    db_session.flush()
    return partido


def _designacion(db_session, partido=None, arbitro=None, rol=RolDesignacion.PRINCIPAL, **kwargs):
    partido = partido or _partido(db_session)
    arbitro = arbitro or _arbitro(db_session)
    datos = dict(
        partido_id=partido.id,
        arbitro_id=arbitro.id,
        rol=rol,
        fecha_designacion=FECHA_DESIGNACION,
    )
    datos.update(kwargs)
    designacion = Designacion(**datos)
    db_session.add(designacion)
    db_session.flush()
    return designacion


def _movimiento(db_session, arbitro, **kwargs):
    datos = dict(
        arbitro_id=arbitro.id,
        fecha=date(2026, 3, 5),
        tipo=TipoMovimiento.CREDITO,
        concepto=ConceptoMovimiento.HONORARIO,
        monto=Decimal("100.00"),
        periodo="2026-03",
    )
    datos.update(kwargs)
    movimiento = MovimientoCuentaCorriente(**datos)
    db_session.add(movimiento)
    db_session.flush()
    return movimiento


def test_arbitro_se_persiste(db_session):
    arbitro = _arbitro(
        db_session,
        legajo="L-777",
        nombre="Lucia",
        apellido="Perez",
        dni="30111222",
        fecha_nacimiento=date(1990, 5, 17),
        email="lucia@example.com",
        telefono="1144556677",
        observaciones="Sin observaciones",
    )
    db_session.commit()

    recuperado = db_session.get(Arbitro, arbitro.id)

    assert recuperado is not None
    assert recuperado.legajo == "L-777"
    assert recuperado.nombre == "Lucia"
    assert recuperado.apellido == "Perez"
    assert recuperado.dni == "30111222"
    assert recuperado.fecha_nacimiento == date(1990, 5, 17)
    assert recuperado.email == "lucia@example.com"
    assert recuperado.telefono == "1144556677"
    assert recuperado.observaciones == "Sin observaciones"
    assert recuperado.estado is EstadoArbitro.ACTIVO
    assert isinstance(recuperado.fecha_alta, date)


def test_legajo_duplicado_falla(db_session):
    db_session.add(Arbitro(legajo="L-001", nombre="Ana", apellido="Gomez", dni="30000001"))
    db_session.add(Arbitro(legajo="L-001", nombre="Beto", apellido="Diaz", dni="30000002"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_dni_duplicado_falla(db_session):
    db_session.add(Arbitro(legajo="L-001", nombre="Ana", apellido="Gomez", dni="30000001"))
    db_session.add(Arbitro(legajo="L-002", nombre="Beto", apellido="Diaz", dni="30000001"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_partido_sin_torneo_valido_falla(db_session):
    cancha = _cancha(db_session)
    db_session.add(
        Partido(
            torneo_id=9999,
            cancha_id=cancha.id,
            fecha_hora=FECHA_HORA_PARTIDO,
            equipo_local="Local FC",
            equipo_visitante="Visitante FC",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_designacion_duplicada_mismo_arbitro_y_partido_falla(db_session):
    partido = _partido(db_session)
    arbitro = _arbitro(db_session)
    _designacion(db_session, partido=partido, arbitro=arbitro, rol=RolDesignacion.PRINCIPAL)
    db_session.add(
        Designacion(
            partido_id=partido.id,
            arbitro_id=arbitro.id,
            rol=RolDesignacion.ASISTENTE_1,
            fecha_designacion=FECHA_DESIGNACION,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_rol_duplicado_en_mismo_partido_falla(db_session):
    partido = _partido(db_session)
    arbitro_1 = _arbitro(db_session, legajo="L-001", dni="30000001")
    arbitro_2 = _arbitro(db_session, legajo="L-002", dni="30000002")
    _designacion(db_session, partido=partido, arbitro=arbitro_1, rol=RolDesignacion.PRINCIPAL)
    db_session.add(
        Designacion(
            partido_id=partido.id,
            arbitro_id=arbitro_2.id,
            rol=RolDesignacion.PRINCIPAL,
            fecha_designacion=FECHA_DESIGNACION,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_designacion_rol_distinto_en_mismo_partido_ok(db_session):
    partido = _partido(db_session)
    arbitro_1 = _arbitro(db_session, legajo="L-001", dni="30000001")
    arbitro_2 = _arbitro(db_session, legajo="L-002", dni="30000002")
    _designacion(db_session, partido=partido, arbitro=arbitro_1, rol=RolDesignacion.PRINCIPAL)
    _designacion(db_session, partido=partido, arbitro=arbitro_2, rol=RolDesignacion.ASISTENTE_1)

    designaciones = (
        db_session.query(Designacion).filter(Designacion.partido_id == partido.id).all()
    )
    assert {d.rol for d in designaciones} == {
        RolDesignacion.PRINCIPAL,
        RolDesignacion.ASISTENTE_1,
    }


def test_movimiento_con_monto_cero_falla(db_session):
    arbitro = _arbitro(db_session)
    db_session.add(
        MovimientoCuentaCorriente(
            arbitro_id=arbitro.id,
            fecha=date(2026, 3, 5),
            tipo=TipoMovimiento.CREDITO,
            concepto=ConceptoMovimiento.HONORARIO,
            monto=Decimal("0.00"),
            periodo="2026-03",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_movimiento_con_monto_negativo_falla(db_session):
    arbitro = _arbitro(db_session)
    db_session.add(
        MovimientoCuentaCorriente(
            arbitro_id=arbitro.id,
            fecha=date(2026, 3, 5),
            tipo=TipoMovimiento.DEBITO,
            concepto=ConceptoMovimiento.DESCUENTO,
            monto=Decimal("-10.00"),
            periodo="2026-03",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_designacion_id_unico_impide_duplicar_honorario(db_session):
    designacion = _designacion(db_session)
    _movimiento(db_session, designacion.arbitro, designacion_id=designacion.id)
    db_session.add(
        MovimientoCuentaCorriente(
            arbitro_id=designacion.arbitro_id,
            designacion_id=designacion.id,
            fecha=date(2026, 3, 5),
            tipo=TipoMovimiento.CREDITO,
            concepto=ConceptoMovimiento.HONORARIO,
            monto=Decimal("100.00"),
            periodo="2026-03",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_saldo_sin_movimientos_es_cero(db_session):
    arbitro = _arbitro(db_session)

    saldo = calcular_saldo(db_session, arbitro.id)

    assert isinstance(saldo, Decimal)
    assert saldo == Decimal("0.00")


def test_saldo_creditos_menos_debitos(db_session):
    arbitro = _arbitro(db_session)
    _movimiento(db_session, arbitro, monto=Decimal("1000.00"), tipo=TipoMovimiento.CREDITO)
    _movimiento(
        db_session,
        arbitro,
        monto=Decimal("200.00"),
        tipo=TipoMovimiento.DEBITO,
        concepto=ConceptoMovimiento.DESCUENTO,
    )
    _movimiento(
        db_session,
        arbitro,
        monto=Decimal("50.00"),
        tipo=TipoMovimiento.CREDITO,
        concepto=ConceptoMovimiento.VIATICO,
    )

    saldo = calcular_saldo(db_session, arbitro.id)

    assert saldo == Decimal("850.00")


def test_saldo_no_deriva_por_float(db_session):
    arbitro = _arbitro(db_session)
    _movimiento(db_session, arbitro, monto=Decimal("0.10"))
    _movimiento(
        db_session,
        arbitro,
        monto=Decimal("0.20"),
        concepto=ConceptoMovimiento.VIATICO,
    )

    saldo = calcular_saldo(db_session, arbitro.id)

    assert saldo == Decimal("0.30")


def test_tipo_movimiento_invalido_rechazado(db_session):
    arbitro = _arbitro(db_session)
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO movimiento_cuenta_corriente "
                "(arbitro_id, fecha, tipo, concepto, monto, periodo) "
                "VALUES (:arbitro_id, '2026-03-05', 'PAGO', 'HONORARIO', 100.00, '2026-03')"
            ),
            {"arbitro_id": arbitro.id},
        )
    db_session.rollback()


def test_periodo_con_formato_invalido_falla(db_session):
    arbitro = _arbitro(db_session)
    db_session.add(
        MovimientoCuentaCorriente(
            arbitro_id=arbitro.id,
            fecha=date(2026, 3, 5),
            tipo=TipoMovimiento.CREDITO,
            concepto=ConceptoMovimiento.HONORARIO,
            monto=Decimal("100.00"),
            periodo="2026-1",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_no_se_puede_borrar_designacion_con_movimiento(db_session):
    designacion = _designacion(db_session)
    _movimiento(db_session, designacion.arbitro, designacion_id=designacion.id)
    db_session.commit()

    db_session.delete(designacion)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    assert db_session.get(Designacion, designacion.id) is not None
    assert db_session.query(MovimientoCuentaCorriente).count() == 1
