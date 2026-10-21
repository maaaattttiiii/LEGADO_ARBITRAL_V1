from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cancha import Cancha
from app.models.enums import EstadoPartido, ModalidadPago
from app.models.partido import Partido
from app.models.torneo import Torneo
from app.periodos import periodo_de
from app.services.cierres import validar_abierto
from app.tiempo import combinar, inicio_del_dia


class PartidoInvalido(ValueError):
    """Los datos del partido no son válidos."""


class TorneoInexistente(PartidoInvalido):
    """El torneo indicado no existe."""


class CanchaInexistente(PartidoInvalido):
    """La cancha indicada no existe."""


def _entero(valor: int | str | None, etiqueta: str) -> int:
    try:
        numero = int(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise PartidoInvalido(f"{etiqueta} inválido.") from exc
    if numero <= 0:
        raise PartidoInvalido(f"{etiqueta} inválido.")
    return numero


def _fecha(valor: date | str | None, etiqueta: str = "Fecha") -> date:
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    try:
        return date.fromisoformat((valor or "").strip())
    except (AttributeError, ValueError) as exc:
        raise PartidoInvalido(
            f"{etiqueta} inválida. Formato esperado: AAAA-MM-DD."
        ) from exc


def _hora(valor: time | str | None) -> time:
    if isinstance(valor, time):
        return valor
    try:
        return time.fromisoformat((valor or "").strip())
    except (AttributeError, ValueError) as exc:
        raise PartidoInvalido(
            "Hora inválida. Formato esperado: HH:MM."
        ) from exc


def _estado(valor: str | EstadoPartido | None) -> EstadoPartido:
    if valor in (None, ""):
        return EstadoPartido.PROGRAMADO
    if isinstance(valor, EstadoPartido):
        return valor
    try:
        return EstadoPartido(valor.strip().upper())
    except ValueError as exc:
        validos = ", ".join(e.value for e in EstadoPartido)
        raise PartidoInvalido(
            f"Estado inválido: '{valor}'. Valores admitidos: {validos}."
        ) from exc


def _modalidad(
    valor: str | ModalidadPago | None,
) -> ModalidadPago:
    if valor in (None, ""):
        return ModalidadPago.EN_CANCHA
    if isinstance(valor, ModalidadPago):
        return valor
    try:
        return ModalidadPago(valor.strip().upper())
    except ValueError as exc:
        validos = ", ".join(e.value for e in ModalidadPago)
        raise PartidoInvalido(
            f"Modalidad de pago inválida: '{valor}'. "
            f"Valores admitidos: {validos}."
        ) from exc


def crear_partido(
    session: Session,
    *,
    torneo_id: int | str,
    cancha_id: int | str,
    fecha: date | str,
    hora: time | str,
    equipo_local: str,
    equipo_visitante: str,
    observaciones: str | None = None,
    estado: str | EstadoPartido | None = None,
    modalidad_pago: str | ModalidadPago | None = None,
) -> Partido:
    """Da de alta un partido en estado `PROGRAMADO`.

    No hace ``commit``: la transacción pertenece al llamador (regla 13).
    """
    id_torneo = _entero(torneo_id, "Torneo")
    id_cancha = _entero(cancha_id, "Cancha")

    if session.get(Torneo, id_torneo) is None:
        raise TorneoInexistente(f"No existe el torneo {id_torneo}.")
    if session.get(Cancha, id_cancha) is None:
        raise CanchaInexistente(f"No existe la cancha {id_cancha}.")

    local = (equipo_local or "").strip()
    visitante = (equipo_visitante or "").strip()
    faltantes = [
        etiqueta
        for valor, etiqueta in (
            (local, "equipo local"),
            (visitante, "equipo visitante"),
        )
        if not valor
    ]
    if faltantes:
        raise PartidoInvalido(
            "Campos obligatorios incompletos: " + ", ".join(faltantes) + "."
        )
    if local.casefold() == visitante.casefold():
        raise PartidoInvalido(
            "El equipo local y el visitante no pueden ser el mismo."
        )

    fecha_hora = combinar(_fecha(fecha), _hora(hora))
    validar_abierto(session, periodo_de(fecha_hora))

    partido = Partido(
        torneo_id=id_torneo,
        cancha_id=id_cancha,
        fecha_hora=fecha_hora,
        equipo_local=local,
        equipo_visitante=visitante,
        estado=_estado(estado),
        modalidad_pago=_modalidad(modalidad_pago),
        observaciones=(observaciones or "").strip() or None,
    )
    session.add(partido)
    session.flush()
    return partido


def filtrar_partidos(
    session: Session,
    *,
    torneo_id: int | str | None = None,
    desde: date | str | None = None,
    hasta: date | str | None = None,
) -> list[Partido]:
    """Lista partidos ordenados por fecha, con filtros opcionales.

    `desde` y `hasta` son días locales e inclusivos.
    """
    condiciones = []

    if torneo_id not in (None, ""):
        id_torneo = _entero(torneo_id, "Torneo")
        if session.get(Torneo, id_torneo) is None:
            raise TorneoInexistente(f"No existe el torneo {id_torneo}.")
        condiciones.append(Partido.torneo_id == id_torneo)

    if desde not in (None, ""):
        condiciones.append(Partido.fecha_hora >= inicio_del_dia(_fecha(desde, "Fecha desde")))

    if hasta not in (None, ""):
        limite = inicio_del_dia(_fecha(hasta, "Fecha hasta") + timedelta(days=1))
        condiciones.append(Partido.fecha_hora < limite)

    return list(
        session.execute(
            select(Partido)
            .where(*condiciones)
            .order_by(Partido.fecha_hora, Partido.id)
        )
        .scalars()
        .all()
    )
