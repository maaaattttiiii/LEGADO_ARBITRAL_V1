from enum import Enum

import sqlalchemy as sa


class RolUsuario(str, Enum):
    """Rol de acceso al sistema.

    ``TESORERO`` administra todo el circuito (padrón, partidos, designaciones y
    tesorería). ``ARBITRO`` solo accede a su portal (``/mis-partidos`` y
    ``/mi-cuenta``) y debe estar vinculado a un ``Arbitro``.
    """

    TESORERO = "TESORERO"
    ARBITRO = "ARBITRO"


class EstadoArbitro(str, Enum):
    ACTIVO = "ACTIVO"
    SUSPENDIDO = "SUSPENDIDO"
    INACTIVO = "INACTIVO"


class EstadoPartido(str, Enum):
    PROGRAMADO = "PROGRAMADO"
    DESIGNADO = "DESIGNADO"
    JUGADO = "JUGADO"
    SUSPENDIDO = "SUSPENDIDO"
    REPROGRAMADO = "REPROGRAMADO"


class RolDesignacion(str, Enum):
    PRINCIPAL = "PRINCIPAL"
    ASISTENTE_1 = "ASISTENTE_1"
    ASISTENTE_2 = "ASISTENTE_2"
    CUARTO = "CUARTO"


class CategoriaArbitro(str, Enum):
    """Escalafón del árbitro. Determina el arancel junto con el torneo."""

    CAT_A = "CAT_A"
    CAT_A1 = "CAT_A1"
    CAT_B = "CAT_B"
    PROMOCIONAL = "PROMOCIONAL"
    UNICA = "UNICA"


class EstadoDesignacion(str, Enum):
    PROPUESTA = "PROPUESTA"
    CONFIRMADA = "CONFIRMADA"
    RECHAZADA = "RECHAZADA"
    CUMPLIDA = "CUMPLIDA"
    AUSENTE = "AUSENTE"


class TipoMovimiento(str, Enum):
    CREDITO = "CREDITO"
    DEBITO = "DEBITO"


class ConceptoMovimiento(str, Enum):
    HONORARIO = "HONORARIO"
    VIATICO = "VIATICO"
    DESCUENTO = "DESCUENTO"
    ADELANTO = "ADELANTO"
    PAGO = "PAGO"
    MULTA = "MULTA"
    AJUSTE = "AJUSTE"
    RETENCION = "RETENCION"


class ModalidadPago(str, Enum):
    """Cómo se cobra el partido.

    - ``EN_CANCHA``: el club paga el 100% al árbitro; la asociación le debita
      el 10% de retención.
    - ``DIFERIDO``: cobra la asociación (municipio, 45-90 días) y le acredita
      al árbitro el 90% de su honorario.
    """

    EN_CANCHA = "EN_CANCHA"
    DIFERIDO = "DIFERIDO"


def columna_enum(py_enum: type[Enum], nombre: str) -> sa.Enum:
    return sa.Enum(
        py_enum,
        name=nombre,
        native_enum=False,
        create_constraint=False,
        length=20,
        values_callable=lambda enum: [miembro.value for miembro in enum],
    )


def check_enum(
    columna: str, py_enum: type[Enum], nombre: str
) -> sa.CheckConstraint:
    """CHECK explícito con los valores válidos del enum.

    Se declara a nivel de tabla (y no vía `create_constraint=True`) porque
    Alembic, al copiar la tabla para un `CreateTableOp`, vuelve a adjuntar el
    tipo `Enum` y duplica la constraint en la migración.
    """
    valores = ", ".join(f"'{miembro.value}'" for miembro in py_enum)
    return sa.CheckConstraint(f"{columna} IN ({valores})", name=nombre)
