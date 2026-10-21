from datetime import date, datetime, timezone
from decimal import Decimal

from app.models import (
    Arbitro,
    Cancha,
    CategoriaArbitro,
    CategoriaTorneo,
    ConceptoMovimiento,
    Designacion,
    EstadoDesignacion,
    EstadoPartido,
    MovimientoCuentaCorriente,
    Partido,
    RolDesignacion,
    TipoMovimiento,
    Torneo,
)
from app.services.exportacion import liquidacion_csv, liquidacion_mensual

FECHA_PARTIDO = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def _escenario(db_session):
    categoria = CategoriaTorneo(nombre="Primera")
    db_session.add(categoria)
    db_session.flush()
    torneo = Torneo(nombre="Apertura 2026", categoria_torneo_id=categoria.id)
    cancha = Cancha(nombre="Malvinas Argentinas")
    db_session.add_all([torneo, cancha])
    db_session.flush()

    partido = Partido(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=FECHA_PARTIDO,
        equipo_local="Estudiantes",
        equipo_visitante="Gimnasia",
        estado=EstadoPartido.JUGADO,
    )
    db_session.add(partido)
    db_session.flush()
    return partido


def _arbitro(db_session, apellido, legajo, dni):
    arbitro = Arbitro(
        legajo=legajo,
        nombre="Nombre",
        apellido=apellido,
        dni=dni,
        categoria=CategoriaArbitro.CAT_A,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _designacion(db_session, partido, arbitro, rol=RolDesignacion.PRINCIPAL):
    designacion = Designacion(
        partido_id=partido.id,
        arbitro_id=arbitro.id,
        rol=rol,
        estado=EstadoDesignacion.CUMPLIDA,
        fecha_designacion=datetime(2026, 3, 1, tzinfo=timezone.utc),
        honorario=Decimal("1000.00"),
    )
    db_session.add(designacion)
    db_session.flush()
    return designacion


def _movimiento(
    db_session,
    designacion,
    concepto,
    tipo,
    monto,
    periodo="2026-03",
    descripcion=None,
):
    movimiento = MovimientoCuentaCorriente(
        arbitro_id=designacion.arbitro_id,
        designacion_id=designacion.id,
        fecha=date(2026, 3, 15),
        tipo=tipo,
        concepto=concepto,
        monto=monto,
        periodo=periodo,
        descripcion=descripcion,
    )
    db_session.add(movimiento)
    db_session.flush()
    return movimiento


def _liquidacion_completa(db_session):
    partido = _escenario(db_session)
    gomez = _arbitro(db_session, "Gómez", "L-1", "30111222")
    alvarez = _arbitro(db_session, "Álvarez", "L-2", "30222333")

    principal = _designacion(db_session, partido, gomez)
    _movimiento(
        db_session, principal, ConceptoMovimiento.HONORARIO, TipoMovimiento.CREDITO,
        Decimal("1000.00"),
    )
    _movimiento(
        db_session, principal, ConceptoMovimiento.RETENCION, TipoMovimiento.DEBITO,
        Decimal("100.00"),
    )
    _movimiento(
        db_session, principal, ConceptoMovimiento.VIATICO, TipoMovimiento.CREDITO,
        Decimal("200.00"),
    )

    asistente = _designacion(
        db_session, partido, alvarez, rol=RolDesignacion.ASISTENTE_1
    )
    _movimiento(
        db_session, asistente, ConceptoMovimiento.HONORARIO, TipoMovimiento.CREDITO,
        Decimal("900.00"),
    )
    _movimiento(
        db_session, asistente, ConceptoMovimiento.RETENCION, TipoMovimiento.DEBITO,
        Decimal("90.00"),
    )
    return principal, asistente


# --------------------------------------------------------------------------
# Armado de filas
# --------------------------------------------------------------------------


def test_liquidacion_agrupa_los_movimientos_por_designacion(db_session):
    _liquidacion_completa(db_session)

    filas = liquidacion_mensual(db_session, periodo="2026-03")

    assert len(filas) == 2
    gomez = next(f for f in filas if f.apellido == "Gómez")
    assert gomez.honorario == Decimal("1000.00")
    assert gomez.retencion == Decimal("100.00")
    assert gomez.viatico == Decimal("200.00")
    assert gomez.neto == Decimal("1100.00")
    assert gomez.partido == "Estudiantes vs Gimnasia"
    assert gomez.rol == RolDesignacion.PRINCIPAL


def test_liquidacion_ordena_por_apellido(db_session):
    _liquidacion_completa(db_session)

    filas = liquidacion_mensual(db_session, periodo="2026-03")

    assert [f.apellido for f in filas] == ["Álvarez", "Gómez"]


def test_liquidacion_ignora_otros_periodos(db_session):
    principal, _ = _liquidacion_completa(db_session)
    original = principal.partido
    abril = Partido(
        torneo_id=original.torneo_id,
        cancha_id=original.cancha_id,
        fecha_hora=datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc),
        equipo_local="Otro",
        equipo_visitante="Equipo",
        estado=EstadoPartido.JUGADO,
    )
    db_session.add(abril)
    db_session.flush()
    designacion_abril = _designacion(db_session, abril, principal.arbitro)
    _movimiento(
        db_session, designacion_abril, ConceptoMovimiento.HONORARIO,
        TipoMovimiento.CREDITO, Decimal("500.00"), periodo="2026-04",
    )

    filas = liquidacion_mensual(db_session, periodo="2026-03")

    assert len(filas) == 2
    gomez = next(f for f in filas if f.apellido == "Gómez")
    assert gomez.honorario == Decimal("1000.00")


def test_liquidacion_ignora_ajustes_manuales_y_reintegros(db_session):
    principal, _ = _liquidacion_completa(db_session)
    _movimiento(
        db_session, principal, ConceptoMovimiento.AJUSTE, TipoMovimiento.CREDITO,
        Decimal("100.00"),
    )

    filas = liquidacion_mensual(db_session, periodo="2026-03")

    gomez = next(f for f in filas if f.apellido == "Gómez")
    assert gomez.neto == Decimal("1100.00")


def test_liquidacion_sin_movimientos_devuelve_lista_vacia(db_session):
    assert liquidacion_mensual(db_session, periodo="2026-03") == []


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------


def test_csv_tiene_encabezado_y_formato_argentino(db_session):
    _liquidacion_completa(db_session)

    texto = liquidacion_csv(liquidacion_mensual(db_session, periodo="2026-03"))
    lineas = texto.strip().splitlines()

    assert lineas[0].startswith("\ufeff")
    assert "Árbitro;Legajo;Partido;Rol;Honorario" in lineas[0]
    assert "Retención (10%)" in lineas[0]
    assert "Neto a Cobrar" in lineas[0]

    gomez = next(linea for linea in lineas if "Gómez" in linea)
    campos = gomez.split(";")
    assert campos[0] == "Gómez, Nombre"
    assert campos[1] == "L-1"
    assert campos[4] == "1.000,00"
    assert campos[5] == "100,00"
    assert campos[6] == "200,00"
    assert campos[7] == "1.100,00"


def test_csv_incluye_el_total(db_session):
    _liquidacion_completa(db_session)

    lineas = liquidacion_csv(
        liquidacion_mensual(db_session, periodo="2026-03")
    ).strip().splitlines()

    total = next(linea for linea in lineas if linea.startswith("TOTAL"))
    campos = total.split(";")
    assert campos[4] == "1.900,00"
    assert campos[5] == "190,00"
    assert campos[6] == "200,00"
    assert campos[7] == "1.910,00"


def test_csv_sin_movimientos_solo_tiene_encabezado_y_total(db_session):
    lineas = liquidacion_csv([]).strip().splitlines()

    assert len(lineas) == 2
    assert lineas[1].startswith("TOTAL")


# --------------------------------------------------------------------------
# Descarga
# --------------------------------------------------------------------------


def test_descargar_csv(client, db_session):
    _liquidacion_completa(db_session)
    db_session.commit()

    respuesta = client.get("/tesoreria/exportar?periodo=2026-03&formato=csv")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert "liquidacion-2026-03.csv" in respuesta.headers["content-disposition"]
    assert "Gómez" in respuesta.text


def test_descargar_pdf(client, db_session):
    _liquidacion_completa(db_session)
    db_session.commit()

    respuesta = client.get("/tesoreria/exportar?periodo=2026-03&formato=pdf")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert "liquidacion-2026-03.pdf" in respuesta.headers["content-disposition"]
    assert respuesta.content.startswith(b"%PDF")


def test_descargar_pdf_sin_movimientos(client):
    respuesta = client.get("/tesoreria/exportar?periodo=2026-03&formato=pdf")

    assert respuesta.status_code == 200
    assert respuesta.content.startswith(b"%PDF")


def test_exportar_con_periodo_invalido_devuelve_400(client):
    respuesta = client.get("/tesoreria/exportar?periodo=2026-13&formato=csv")

    assert respuesta.status_code == 400


def test_exportar_con_formato_desconocido_devuelve_400(client):
    respuesta = client.get("/tesoreria/exportar?periodo=2026-03&formato=xls")

    assert respuesta.status_code == 400


def test_panel_ofrece_las_descargas(client, db_session):
    _liquidacion_completa(db_session)
    db_session.commit()

    respuesta = client.get("/tesoreria?periodo=2026-03")

    assert "/tesoreria/exportar" in respuesta.text
    assert "2026-03" in respuesta.text
