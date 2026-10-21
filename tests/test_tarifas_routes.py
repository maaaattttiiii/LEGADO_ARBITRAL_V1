from datetime import date
from decimal import Decimal

from app.models import CategoriaTorneo, Tarifa


def _categoria(db_session, nombre="Primera"):
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.commit()
    return categoria


def test_listado_sin_tarifas_muestra_estado_vacio(client):
    respuesta = client.get("/tarifas")

    assert respuesta.status_code == 200
    assert "No hay" in respuesta.text


def test_alta_de_tarifa_redirige_y_persiste(client, db_session):
    categoria = _categoria(db_session)

    respuesta = client.post(
        "/tarifas",
        data={
            "categoria_torneo_id": str(categoria.id),
            "rol": "PRINCIPAL",
            "categoria_arbitro": "CAT_A",
            "monto_base": "73100",
            "vigencia_desde": "2026-03-01",
            "descripcion": "Aumento marzo",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    tarifa = db_session.query(Tarifa).one()
    assert tarifa.monto_base == Decimal("73100.00")
    assert tarifa.vigencia_desde == date(2026, 3, 1)
    assert tarifa.descripcion == "Aumento marzo"


def test_alta_sin_rol_crea_tarifa_de_cualquier_rol(client, db_session):
    categoria = _categoria(db_session)

    respuesta = client.post(
        "/tarifas",
        data={
            "categoria_torneo_id": str(categoria.id),
            "rol": "",
            "categoria_arbitro": "",
            "monto_base": "25900",
            "vigencia_desde": "2026-01-01",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    tarifa = db_session.query(Tarifa).one()
    assert tarifa.rol is None
    assert tarifa.categoria_arbitro is None


def test_alta_solapada_muestra_error(client, db_session):
    categoria = _categoria(db_session)
    datos = {
        "categoria_torneo_id": str(categoria.id),
        "rol": "PRINCIPAL",
        "categoria_arbitro": "CAT_A",
        "monto_base": "73100",
        "vigencia_desde": "2026-03-01",
    }
    client.post("/tarifas", data=datos, follow_redirects=False)

    respuesta = client.post(
        "/tarifas", data={**datos, "monto_base": "80000", "vigencia_desde": "2026-05-01"}
    )

    assert respuesta.status_code == 400
    assert db_session.query(Tarifa).count() == 1


def test_alta_con_monto_invalido_muestra_error(client, db_session):
    categoria = _categoria(db_session)

    respuesta = client.post(
        "/tarifas",
        data={
            "categoria_torneo_id": str(categoria.id),
            "monto_base": "gratis",
            "vigencia_desde": "2026-03-01",
        },
    )

    assert respuesta.status_code == 400
    assert db_session.query(Tarifa).count() == 0


def test_listado_muestra_el_historial_de_vigencias(client, db_session):
    categoria = _categoria(db_session)
    db_session.add_all(
        [
            Tarifa(
                categoria_torneo_id=categoria.id,
                monto_base=Decimal("60000.00"),
                vigencia_desde=date(2026, 1, 1),
                vigencia_hasta=date(2026, 2, 28),
            ),
            Tarifa(
                categoria_torneo_id=categoria.id,
                monto_base=Decimal("73100.00"),
                vigencia_desde=date(2026, 3, 1),
            ),
        ]
    )
    db_session.commit()

    respuesta = client.get("/tarifas")

    assert "60.000,00" in respuesta.text
    assert "73.100,00" in respuesta.text
    assert "Primera" in respuesta.text
