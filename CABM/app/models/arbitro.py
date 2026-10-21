from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    CategoriaArbitro,
    EstadoArbitro,
    check_enum,
    columna_enum,
)

if TYPE_CHECKING:
    from app.models.designacion import Designacion
    from app.models.movimiento import MovimientoCuentaCorriente


def _hoy_utc() -> date:
    return datetime.now(timezone.utc).date()


class Arbitro(TimestampMixin, Base):
    __tablename__ = "arbitro"
    __table_args__ = (
        check_enum("estado", EstadoArbitro, "estado_arbitro"),
        check_enum("categoria", CategoriaArbitro, "categoria_arbitro"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    legajo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellido: Mapped[str] = mapped_column(String(100), nullable=False)
    dni: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(150))
    telefono: Mapped[str | None] = mapped_column(String(40))
    categoria: Mapped[CategoriaArbitro | None] = mapped_column(
        columna_enum(CategoriaArbitro, "categoria_arbitro"), nullable=True
    )
    estado: Mapped[EstadoArbitro] = mapped_column(
        columna_enum(EstadoArbitro, "estado_arbitro"),
        default=EstadoArbitro.ACTIVO,
        server_default=EstadoArbitro.ACTIVO.value,
        nullable=False,
    )
    tiene_auto: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    fecha_alta: Mapped[date] = mapped_column(
        Date, default=_hoy_utc, server_default=text("CURRENT_DATE"), nullable=False
    )
    fecha_baja: Mapped[date | None] = mapped_column(Date)
    domicilio: Mapped[str | None] = mapped_column(String(200))
    localidad: Mapped[str | None] = mapped_column(String(120))
    observaciones: Mapped[str | None] = mapped_column(Text)

    designaciones: Mapped[list["Designacion"]] = relationship(back_populates="arbitro")
    movimientos: Mapped[list["MovimientoCuentaCorriente"]] = relationship(
        back_populates="arbitro"
    )
