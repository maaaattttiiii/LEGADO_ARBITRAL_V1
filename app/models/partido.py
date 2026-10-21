from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    EstadoPartido,
    ModalidadPago,
    check_enum,
    columna_enum,
)
from app.periodos import periodo_de

if TYPE_CHECKING:
    from app.models.cancha import Cancha
    from app.models.designacion import Designacion
    from app.models.torneo import Torneo


class Partido(TimestampMixin, Base):
    __tablename__ = "partido"
    __table_args__ = (
        check_enum("estado", EstadoPartido, "estado_partido"),
        check_enum("modalidad_pago", ModalidadPago, "modalidad_pago"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    torneo_id: Mapped[int] = mapped_column(
        ForeignKey("torneo.id", ondelete="RESTRICT"), nullable=False
    )
    cancha_id: Mapped[int] = mapped_column(
        ForeignKey("cancha.id", ondelete="RESTRICT"), nullable=False
    )
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equipo_local: Mapped[str] = mapped_column(String(120), nullable=False)
    equipo_visitante: Mapped[str] = mapped_column(String(120), nullable=False)
    estado: Mapped[EstadoPartido] = mapped_column(
        columna_enum(EstadoPartido, "estado_partido"),
        default=EstadoPartido.PROGRAMADO,
        server_default=EstadoPartido.PROGRAMADO.value,
        nullable=False,
    )
    observaciones: Mapped[str | None] = mapped_column(Text)
    modalidad_pago: Mapped[ModalidadPago] = mapped_column(
        columna_enum(ModalidadPago, "modalidad_pago"),
        default=ModalidadPago.EN_CANCHA,
        server_default=ModalidadPago.EN_CANCHA.value,
        nullable=False,
    )
    # Fecha real en que el municipio pagó (solo modalidad DIFERIDO). Determina
    # si hubo mora > 90 días y, por lo tanto, si corresponde retener (RN-31).
    fecha_cobro: Mapped[date | None] = mapped_column(Date)

    torneo: Mapped["Torneo"] = relationship(back_populates="partidos")
    cancha: Mapped["Cancha"] = relationship(back_populates="partidos")
    designaciones: Mapped[list["Designacion"]] = relationship(back_populates="partido")

    @property
    def periodo(self) -> str:
        """Período contable (``AAAA-MM``) del partido en hora local."""
        return periodo_de(self.fecha_hora)
