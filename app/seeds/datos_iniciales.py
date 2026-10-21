"""Datos iniciales oficiales del CABM — planilla Octubre 2026.

Uso::

    & C:\\Python314\\python.exe -m app.seeds.datos_iniciales

El seed es **idempotente**: se puede correr varias veces sin duplicar filas ni
sobrescribir datos cargados a mano. Si un valor oficial difiere del existente,
no lo pisa: lo reporta como advertencia para revisión humana.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Cancha,
    CategoriaArbitro,
    CategoriaTorneo,
    PrecioCombustible,
    RolDesignacion,
    Tarifa,
)
from app.services.tarifas import crear_tarifa
from app.services.viaticos import crear_precio_combustible

# --- Combustible -----------------------------------------------------------
PRECIO_INFINIA = Decimal("2361.00")
PRECIO_INFINIA_DESDE = date(2026, 10, 13)

# --- Viáticos: litros fijos por localidad (planilla oficial) ---------------
CANCHAS_OFICIALES: dict[str, Decimal] = {
    "La Paz": Decimal("39.00"),
    "San Carlos": Decimal("27.00"),
    "Tunuyán": Decimal("24.00"),
    "Tupungato": Decimal("24.00"),
    "Rivadavia": Decimal("18.00"),
    "Junín": Decimal("16.00"),
    "Barriales": Decimal("16.00"),
    "San Martín": Decimal("14.00"),
    "Lavalle": Decimal("8.00"),
    "Luján": Decimal("5.00"),
    "Maipú": Decimal("5.00"),
}

# --- Categorías de torneo --------------------------------------------------
# Inferiores se divide por división. U11_DOBLE no se designa: es la categoría
# técnica que sostiene el arancel global de U11 cuando el partido tiene 2 árbitros.
CATEGORIAS_OFICIALES: tuple[str, ...] = (
    "Super Liga",
    "Ascenso",
    "Promoción",
    "Super Liga Femenina",
    "U23",
    "U19",
    "JUVENILES",
    "CADETES",
    "INFANTILES",
    "U11_DOBLE",
    "U11",
    "U9",
    "Master",
)


# --- Aranceles -------------------------------------------------------------
ARANCELES_DESDE = date(2026, 10, 1)


@dataclass(frozen=True)
class ArancelOficial:
    """Un monto de la planilla.

    ``rol=None`` → aplica a cualquier rol de campo (principal y asistentes).
    ``categoria_arbitro=None`` → aplica a cualquier escalafón (3° juez).
    """

    categoria_torneo: str
    monto: Decimal
    categoria_arbitro: CategoriaArbitro | None
    rol: RolDesignacion | None = None


TARIFAS_OFICIALES: tuple[ArancelOficial, ...] = (
    # Super Liga
    ArancelOficial("Super Liga", Decimal("73100.00"), CategoriaArbitro.CAT_A),
    ArancelOficial("Super Liga", Decimal("61200.00"), CategoriaArbitro.CAT_A1),
    ArancelOficial("Super Liga", Decimal("53100.00"), CategoriaArbitro.CAT_B),
    ArancelOficial("Super Liga", Decimal("53100.00"), CategoriaArbitro.PROMOCIONAL),
    ArancelOficial(
        "Super Liga",
        Decimal("30700.00"),
        None,
        rol=RolDesignacion.CUARTO,
    ),
    # Ascenso
    ArancelOficial("Ascenso", Decimal("52500.00"), CategoriaArbitro.CAT_A),
    ArancelOficial("Ascenso", Decimal("44500.00"), CategoriaArbitro.CAT_A1),
    ArancelOficial("Ascenso", Decimal("40300.00"), CategoriaArbitro.CAT_B),
    ArancelOficial("Ascenso", Decimal("40300.00"), CategoriaArbitro.PROMOCIONAL),
    # Promoción
    ArancelOficial("Promoción", Decimal("42300.00"), CategoriaArbitro.CAT_A),
    ArancelOficial("Promoción", Decimal("41400.00"), CategoriaArbitro.CAT_A1),
    ArancelOficial("Promoción", Decimal("38500.00"), CategoriaArbitro.CAT_B),
    ArancelOficial("Promoción", Decimal("38500.00"), CategoriaArbitro.PROMOCIONAL),
    # Super Liga Femenina
    ArancelOficial("Super Liga Femenina", Decimal("45400.00"), CategoriaArbitro.CAT_A),
    ArancelOficial("Super Liga Femenina", Decimal("44500.00"), CategoriaArbitro.CAT_A1),
    ArancelOficial("Super Liga Femenina", Decimal("40300.00"), CategoriaArbitro.CAT_B),
    ArancelOficial(
        "Super Liga Femenina", Decimal("40300.00"), CategoriaArbitro.PROMOCIONAL
    ),
    # Inferiores (arancel único por división)
    ArancelOficial("U23", Decimal("38700.00"), CategoriaArbitro.UNICA),
    ArancelOficial("U19", Decimal("31600.00"), CategoriaArbitro.UNICA),
    ArancelOficial("JUVENILES", Decimal("28200.00"), CategoriaArbitro.UNICA),
    ArancelOficial("CADETES", Decimal("25900.00"), CategoriaArbitro.UNICA),
    ArancelOficial("INFANTILES", Decimal("24600.00"), CategoriaArbitro.UNICA),
    ArancelOficial("U11_DOBLE", Decimal("31900.00"), CategoriaArbitro.UNICA),
    ArancelOficial("U11", Decimal("19600.00"), CategoriaArbitro.UNICA),
    ArancelOficial("U9", Decimal("19600.00"), CategoriaArbitro.UNICA),
    # Master
    ArancelOficial("Master", Decimal("52500.00"), CategoriaArbitro.UNICA),
)


@dataclass(frozen=True)
class ReporteSeed:
    precios_creados: int = 0
    canchas_creadas: int = 0
    categorias_creadas: int = 0
    tarifas_creadas: int = 0
    omitidos: int = 0
    advertencias: tuple[str, ...] = ()


def _igual(columna, valor):
    return columna.is_(None) if valor is None else columna == valor


def _categoria_por_nombre(session: Session, nombre: str) -> CategoriaTorneo:
    return session.execute(
        select(CategoriaTorneo).where(CategoriaTorneo.nombre == nombre)
    ).scalar_one()


def sembrar_datos_iniciales(session: Session) -> ReporteSeed:
    """Carga los datos oficiales. Solo hace ``flush``; el commit es del llamador."""
    precios = canchas = categorias = tarifas = omitidos = 0
    advertencias: list[str] = []

    # 1. Precio del combustible
    existente = session.execute(
        select(PrecioCombustible).where(
            PrecioCombustible.vigencia_desde == PRECIO_INFINIA_DESDE
        )
    ).scalar_one_or_none()
    if existente is None:
        crear_precio_combustible(
            session,
            precio_litro=PRECIO_INFINIA,
            vigencia_desde=PRECIO_INFINIA_DESDE,
            descripcion="Nafta Infinia - planilla oficial",
        )
        precios += 1
    else:
        omitidos += 1
        if Decimal(existente.precio_litro) != PRECIO_INFINIA:
            advertencias.append(
                "Precio de combustible del "
                f"{PRECIO_INFINIA_DESDE} ya existe con "
                f"{existente.precio_litro} (planilla {PRECIO_INFINIA}); "
                "no se modificó."
            )

    # 2. Canchas / localidades con litros de viático
    for nombre, litros in CANCHAS_OFICIALES.items():
        cancha = session.execute(
            select(Cancha).where(Cancha.nombre == nombre)
        ).scalar_one_or_none()
        if cancha is None:
            session.add(
                Cancha(
                    nombre=nombre,
                    localidad=nombre,
                    litros_viatico=litros,
                )
            )
            canchas += 1
            continue

        omitidos += 1
        if Decimal(cancha.litros_viatico) != litros:
            advertencias.append(
                f"La cancha '{nombre}' ya existe con "
                f"{cancha.litros_viatico} L (planilla {litros} L); "
                "no se modificó."
            )

    # 3. Categorías de torneo
    for orden, nombre in enumerate(CATEGORIAS_OFICIALES, start=1):
        categoria = session.execute(
            select(CategoriaTorneo).where(CategoriaTorneo.nombre == nombre)
        ).scalar_one_or_none()
        if categoria is None:
            session.add(CategoriaTorneo(nombre=nombre, orden=orden))
            categorias += 1
        else:
            omitidos += 1

    session.flush()

    # 4. Aranceles oficiales
    for arancel in TARIFAS_OFICIALES:
        categoria = _categoria_por_nombre(session, arancel.categoria_torneo)
        ya_existe = session.execute(
            select(Tarifa.id)
            .where(
                Tarifa.categoria_torneo_id == categoria.id,
                _igual(Tarifa.rol, arancel.rol),
                _igual(Tarifa.categoria_arbitro, arancel.categoria_arbitro),
                Tarifa.vigencia_desde == ARANCELES_DESDE,
            )
            .limit(1)
        ).scalar_one_or_none()
        if ya_existe is not None:
            omitidos += 1
            continue

        crear_tarifa(
            session,
            categoria_torneo_id=categoria.id,
            rol=arancel.rol,
            categoria_arbitro=arancel.categoria_arbitro,
            monto_base=arancel.monto,
            vigencia_desde=ARANCELES_DESDE,
            descripcion="Arancel oficial",
        )
        tarifas += 1

    session.flush()

    return ReporteSeed(
        precios_creados=precios,
        canchas_creadas=canchas,
        categorias_creadas=categorias,
        tarifas_creadas=tarifas,
        omitidos=omitidos,
        advertencias=tuple(advertencias),
    )


def main() -> None:
    from app.database import SessionLocal

    with SessionLocal() as session:
        reporte = sembrar_datos_iniciales(session)
        session.commit()

    print(
        "Seed completado: "
        f"{reporte.precios_creados} precios, "
        f"{reporte.canchas_creadas} canchas, "
        f"{reporte.categorias_creadas} categorías, "
        f"{reporte.tarifas_creadas} tarifas "
        f"({reporte.omitidos} existentes omitidos)."
    )
    for aviso in reporte.advertencias:
        print(f"  ADVERTENCIA: {aviso}")


if __name__ == "__main__":
    main()
