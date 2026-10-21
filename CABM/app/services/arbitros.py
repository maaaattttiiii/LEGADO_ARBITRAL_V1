from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.arbitro import Arbitro
from app.models.enums import CategoriaArbitro, EstadoArbitro


class ArbitroInvalido(ValueError):
    """Los datos del padrón no son válidos."""


class LegajoDuplicado(ArbitroInvalido):
    """Ya existe un árbitro con ese legajo."""


class DniDuplicado(ArbitroInvalido):
    """Ya existe un árbitro con ese DNI."""


def _texto(valor: str | None) -> str:
    return (valor or "").strip()


def _categoria(valor: str | CategoriaArbitro | None) -> CategoriaArbitro | None:
    if valor in (None, "") or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, CategoriaArbitro):
        return valor
    try:
        return CategoriaArbitro(valor.strip().upper())
    except ValueError as exc:
        validos = ", ".join(c.value for c in CategoriaArbitro)
        raise ArbitroInvalido(
            f"Escalafón inválido: '{valor}'. Valores admitidos: {validos}."
        ) from exc


def _estado(valor: str | EstadoArbitro | None) -> EstadoArbitro:
    if valor in (None, "") or (isinstance(valor, str) and not valor.strip()):
        return EstadoArbitro.ACTIVO
    if isinstance(valor, EstadoArbitro):
        return valor
    try:
        return EstadoArbitro(valor.strip().upper())
    except ValueError as exc:
        validos = ", ".join(e.value for e in EstadoArbitro)
        raise ArbitroInvalido(
            f"Estado inválido: '{valor}'. Valores admitidos: {validos}."
        ) from exc


def _fecha(valor: date | str | None) -> date | None:
    if valor in (None, "") or isinstance(valor, date):
        return valor or None
    try:
        return date.fromisoformat(valor.strip())
    except ValueError as exc:
        raise ArbitroInvalido(
            f"Fecha inválida: '{valor}'. Formato esperado: AAAA-MM-DD."
        ) from exc


def _booleano(valor: bool | str | None) -> bool:
    if isinstance(valor, bool):
        return valor
    return (valor or "").strip().lower() in {"on", "1", "true", "si", "sí"}


def crear_arbitro(
    session: Session,
    *,
    legajo: str,
    nombre: str,
    apellido: str,
    dni: str,
    categoria: str | CategoriaArbitro | None = None,
    estado: str | EstadoArbitro | None = None,
    tiene_auto: bool | str = False,
    email: str | None = None,
    telefono: str | None = None,
    localidad: str | None = None,
    domicilio: str | None = None,
    fecha_nacimiento: date | str | None = None,
    observaciones: str | None = None,
) -> Arbitro:
    """Da de alta un árbitro en el padrón.

    No hace ``commit``: la transacción pertenece al llamador (regla 13).
    """
    legajo = _texto(legajo)
    nombre = _texto(nombre)
    apellido = _texto(apellido)
    dni = _texto(dni)

    faltantes = [
        etiqueta
        for valor, etiqueta in (
            (legajo, "legajo"),
            (nombre, "nombre"),
            (apellido, "apellido"),
            (dni, "DNI"),
        )
        if not valor
    ]
    if faltantes:
        raise ArbitroInvalido(
            "Campos obligatorios incompletos: " + ", ".join(faltantes) + "."
        )

    if session.execute(select(Arbitro.id).where(Arbitro.legajo == legajo)).first():
        raise LegajoDuplicado(f"Ya existe un árbitro con el legajo {legajo}.")

    if session.execute(select(Arbitro.id).where(Arbitro.dni == dni)).first():
        raise DniDuplicado(f"Ya existe un árbitro con el DNI {dni}.")

    arbitro = Arbitro(
        legajo=legajo,
        nombre=nombre,
        apellido=apellido,
        dni=dni,
        categoria=_categoria(categoria),
        estado=_estado(estado),
        tiene_auto=_booleano(tiene_auto),
        email=_texto(email) or None,
        telefono=_texto(telefono) or None,
        localidad=_texto(localidad) or None,
        domicilio=_texto(domicilio) or None,
        fecha_nacimiento=_fecha(fecha_nacimiento),
        observaciones=_texto(observaciones) or None,
    )
    session.add(arbitro)
    session.flush()
    return arbitro
