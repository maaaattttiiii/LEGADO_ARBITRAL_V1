from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.arbitro import Arbitro
from app.models.designacion import Designacion
from app.models.enums import (
    EstadoDesignacion,
    EstadoPartido,
    RolDesignacion,
)
from app.models.movimiento import MovimientoCuentaCorriente
from app.models.partido import Partido
from app.services.cierres import validar_abierto
from app.services.tarifas import TarifaNoEncontrada, resolver_tarifa

ESTADOS_EDITABLES = frozenset(
    {
        EstadoPartido.PROGRAMADO,
        EstadoPartido.DESIGNADO,
        EstadoPartido.REPROGRAMADO,
    }
)

ROLES_TERNA = (
    RolDesignacion.PRINCIPAL,
    RolDesignacion.ASISTENTE_1,
    RolDesignacion.ASISTENTE_2,
    RolDesignacion.CUARTO,
)

# Un partido de básquetbol dura ~1h30 (calentamiento, entretiempo y cierre de
# planilla): dos partidos exigen al menos 2 horas de diferencia, en la misma
# cancha o en otra. En la misma sede no hay traslado, pero el árbitro tampoco
# puede solapar la atención de dos partidos consecutivos.
MARGEN_CONFLICTO = timedelta(hours=2)

# U11 se juega con un árbitro (tarifa U11) o con dos (U11_DOBLE repartida).
CATEGORIA_U11 = "U11"
MAX_ARBITROS_U11 = 2


class DesignacionInvalida(ValueError):
    """La terna no se puede asignar."""


class ConflictoHorario(DesignacionInvalida):
    """El árbitro no puede llegar: poco margen entre partidos o solapamiento."""


class DesignacionLiquidada(DesignacionInvalida):
    """La designación ya generó movimientos y no se puede modificar."""


class CuartoNoAplica(DesignacionInvalida):
    """La categoría del torneo no admite cuarto árbitro."""


def _opcional_id(valor: int | str | None) -> int | None:
    if valor in (None, ""):
        return None
    try:
        numero = int(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise DesignacionInvalida(f"Identificador inválido: '{valor}'.") from exc
    if numero <= 0:
        raise DesignacionInvalida(f"Identificador inválido: '{valor}'.")
    return numero


def _rol_auto(valor: str | RolDesignacion | None) -> RolDesignacion | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, RolDesignacion):
        return valor
    try:
        return RolDesignacion(valor.strip().upper())
    except ValueError as exc:
        raise DesignacionInvalida(f"Rol de auto inválido: '{valor}'.") from exc


def _tiene_movimientos(session: Session, designacion_id: int) -> bool:
    return (
        session.execute(
            select(MovimientoCuentaCorriente.id)
            .where(MovimientoCuentaCorriente.designacion_id == designacion_id)
            .limit(1)
        ).first()
        is not None
    )


def admite_cuarto(session: Session, partido: Partido) -> bool:
    """¿La categoría del partido tiene arancel de cuarto árbitro vigente?"""
    try:
        resolver_tarifa(
            session,
            categoria_torneo_id=partido.torneo.categoria_torneo_id,
            rol=RolDesignacion.CUARTO,
            fecha=partido.fecha_hora.date(),
        )
    except TarifaNoEncontrada:
        return False
    return True


def _nombre(arbitro: Arbitro) -> str:
    return f"{arbitro.apellido}, {arbitro.nombre}"


def asignar_terna(
    session: Session,
    *,
    partido_id: int | str,
    principal_id: int | str | None = None,
    asistente_1_id: int | str | None = None,
    asistente_2_id: int | str | None = None,
    cuarto_id: int | str | None = None,
    auto_rol: str | RolDesignacion | None = None,
) -> list[Designacion]:
    """Asigna o reemplaza la terna de un partido.

    - Roles con árbitro: se crean o actualizan.
    - Roles que quedan vacíos: se eliminan (salvo que ya estén liquidados).
    - ``auto_rol`` indica qué rol de la terna usa el vehículo (``usa_auto``).

    No hace ``commit``: la transacción pertenece al llamador (regla 13).
    """
    id_partido = _opcional_id(partido_id)
    if id_partido is None:
        raise DesignacionInvalida("Falta el partido.")

    partido = session.get(Partido, id_partido)
    if partido is None:
        raise DesignacionInvalida(f"No existe el partido {id_partido}.")
    if partido.estado not in ESTADOS_EDITABLES:
        raise DesignacionInvalida(
            f"El partido está en estado {partido.estado.value} y no admite "
            "cambios en la terna."
        )
    validar_abierto(session, partido.periodo)

    asignaciones: dict[RolDesignacion, int] = {}
    for rol, valor in (
        (RolDesignacion.PRINCIPAL, principal_id),
        (RolDesignacion.ASISTENTE_1, asistente_1_id),
        (RolDesignacion.ASISTENTE_2, asistente_2_id),
        (RolDesignacion.CUARTO, cuarto_id),
    ):
        arbitro_id = _opcional_id(valor)
        if arbitro_id is not None:
            asignaciones[rol] = arbitro_id

    if not asignaciones:
        raise DesignacionInvalida("Asigná al menos un árbitro a la terna.")

    arbitros = {
        arbitro.id: arbitro
        for arbitro in session.execute(
            select(Arbitro).where(Arbitro.id.in_(set(asignaciones.values())))
        )
        .scalars()
        .all()
    }
    for arbitro_id in asignaciones.values():
        if arbitro_id not in arbitros:
            raise DesignacionInvalida(f"No existe el árbitro {arbitro_id}.")

    if len(set(asignaciones.values())) != len(asignaciones):
        duplicados = {
            _nombre(arbitros[a_id])
            for a_id in asignaciones.values()
            if list(asignaciones.values()).count(a_id) > 1
        }
        raise DesignacionInvalida(
            "Un árbitro no puede ocupar dos roles en la misma terna: "
            + ", ".join(sorted(duplicados))
            + "."
        )

    if len(asignaciones) > MAX_ARBITROS_U11 and (
        partido.torneo.categoria.nombre == CATEGORIA_U11
    ):
        raise DesignacionInvalida(
            f"Un partido U11 admite como máximo {MAX_ARBITROS_U11} árbitros "
            f"(la terna tiene {len(asignaciones)})."
        )

    if RolDesignacion.CUARTO in asignaciones and not admite_cuarto(session, partido):
        raise CuartoNoAplica(
            "La categoría del torneo no admite cuarto árbitro "
            "(no hay arancel CUARTO vigente para la fecha del partido)."
        )

    rol_auto = _rol_auto(auto_rol)
    if rol_auto is not None and rol_auto not in asignaciones:
        raise DesignacionInvalida(
            "El rol elegido para el auto no tiene árbitro designado en esta terna."
        )

    conflictos = session.execute(
        select(Designacion, Partido)
        .join(Partido, Designacion.partido_id == Partido.id)
        .where(
            Designacion.arbitro_id.in_(set(asignaciones.values())),
            Designacion.partido_id != partido.id,
            Designacion.estado != EstadoDesignacion.RECHAZADA,
            # El margen de 2 h se aplica siempre, sin importar la cancha.
            Partido.fecha_hora > partido.fecha_hora - MARGEN_CONFLICTO,
            Partido.fecha_hora < partido.fecha_hora + MARGEN_CONFLICTO,
        )
    ).all()
    if conflictos:
        designacion, otro_partido = conflictos[0]
        raise ConflictoHorario(
            f"{_nombre(arbitros[designacion.arbitro_id])} ya está designado en "
            f"{otro_partido.equipo_local} vs {otro_partido.equipo_visitante}, "
            f"a menos de 2 horas."
        )

    existentes = {
        designacion.rol: designacion
        for designacion in session.execute(
            select(Designacion).where(Designacion.partido_id == partido.id)
        )
        .scalars()
        .all()
    }

    terna: list[Designacion] = []
    for rol, arbitro_id in asignaciones.items():
        designacion = existentes.get(rol)
        usa_auto = rol == rol_auto

        if designacion is None:
            designacion = Designacion(
                partido_id=partido.id,
                arbitro_id=arbitro_id,
                rol=rol,
                estado=EstadoDesignacion.CONFIRMADA,
                fecha_designacion=datetime.now(timezone.utc),
                usa_auto=usa_auto,
            )
            session.add(designacion)
            terna.append(designacion)
            continue

        if designacion.arbitro_id != arbitro_id:
            if _tiene_movimientos(session, designacion.id):
                raise DesignacionLiquidada(
                    f"La designación de {_nombre(arbitros[designacion.arbitro_id])} "
                    "ya está liquidada y no se puede reemplazar."
                )
            designacion.arbitro_id = arbitro_id

        if designacion.usa_auto != usa_auto and _tiene_movimientos(
            session, designacion.id
        ):
            raise DesignacionLiquidada(
                "No se puede cambiar el uso del auto de una designación liquidada."
            )

        if designacion.estado is EstadoDesignacion.RECHAZADA:
            designacion.estado = EstadoDesignacion.CONFIRMADA
        designacion.usa_auto = usa_auto
        terna.append(designacion)

    for rol, designacion in existentes.items():
        if rol in asignaciones:
            continue
        if designacion.estado is EstadoDesignacion.RECHAZADA:
            continue
        if _tiene_movimientos(session, designacion.id):
            raise DesignacionLiquidada(
                f"La designación de {designacion.arbitro.apellido} ya está "
                "liquidada y no se puede quitar de la terna."
            )
        session.delete(designacion)

    if partido.estado in (EstadoPartido.PROGRAMADO, EstadoPartido.REPROGRAMADO):
        partido.estado = EstadoPartido.DESIGNADO

    session.flush()
    return terna
