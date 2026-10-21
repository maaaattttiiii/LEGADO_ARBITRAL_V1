from sqlalchemy.orm import Session

from app.models.torneo import CategoriaTorneo, Torneo
from app.services import validaciones


class TorneoInvalido(ValueError):
    """Los datos del torneo no son válidos."""


def _nombre(valor: object | None) -> str:
    nombre = validaciones.texto(valor)
    if not nombre:
        raise TorneoInvalido("El nombre del torneo es obligatorio.")
    return nombre


def _categoria(session: Session, valor: object | None) -> CategoriaTorneo:
    texto = validaciones.texto(valor)
    if not texto:
        raise TorneoInvalido("Elegí la categoría del torneo.")
    try:
        categoria_id = int(texto)
    except (TypeError, ValueError) as exc:
        raise TorneoInvalido(f"Categoría inválida: '{valor}'.") from exc
    categoria = session.get(CategoriaTorneo, categoria_id)
    if categoria is None:
        raise TorneoInvalido(f"No existe la categoría {categoria_id}.")
    return categoria


def _fechas(
    inicio: object | None, fin: object | None
) -> tuple[object, object]:
    desde = validaciones.fecha(inicio, campo="La fecha de inicio", error=TorneoInvalido)
    hasta = validaciones.fecha(fin, campo="La fecha de fin", error=TorneoInvalido)
    if desde and hasta and hasta < desde:
        raise TorneoInvalido(
            "La fecha de fin no puede ser anterior a la de inicio."
        )
    return desde, hasta


def crear_torneo(
    session: Session,
    *,
    nombre: object,
    categoria_torneo_id: object,
    temporada: object | None = None,
    fecha_inicio: object | None = None,
    fecha_fin: object | None = None,
    activo: bool | str = True,
) -> Torneo:
    """Da de alta un torneo. No hace ``commit`` (regla 13)."""
    categoria = _categoria(session, categoria_torneo_id)
    desde, hasta = _fechas(fecha_inicio, fecha_fin)
    torneo = Torneo(
        nombre=_nombre(nombre),
        categoria_torneo_id=categoria.id,
        temporada=validaciones.texto(temporada) or None,
        fecha_inicio=desde,
        fecha_fin=hasta,
        activo=validaciones.booleano(activo),
    )
    session.add(torneo)
    session.flush()
    return torneo


def actualizar_torneo(
    session: Session,
    torneo: Torneo,
    *,
    nombre: object,
    categoria_torneo_id: object,
    temporada: object | None = None,
    fecha_inicio: object | None = None,
    fecha_fin: object | None = None,
) -> Torneo:
    """Actualiza un torneo. No hace ``commit`` (regla 13)."""
    categoria = _categoria(session, categoria_torneo_id)
    desde, hasta = _fechas(fecha_inicio, fecha_fin)
    torneo.nombre = _nombre(nombre)
    torneo.categoria_torneo_id = categoria.id
    torneo.temporada = validaciones.texto(temporada) or None
    torneo.fecha_inicio = desde
    torneo.fecha_fin = hasta
    session.flush()
    return torneo


def cambiar_estado(
    session: Session, torneo: Torneo, *, activo: bool | str
) -> Torneo:
    torneo.activo = validaciones.booleano(activo)
    session.flush()
    return torneo
