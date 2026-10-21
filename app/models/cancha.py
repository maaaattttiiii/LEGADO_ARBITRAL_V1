from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.partido import Partido


class Cancha(TimestampMixin, Base):
    __tablename__ = "cancha"
    __table_args__ = (
        CheckConstraint("litros_viatico >= 0", name="litros_viatico_no_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    direccion: Mapped[str | None] = mapped_column(String(200))
    localidad: Mapped[str | None] = mapped_column(String(120))
    litros_viatico: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    activo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    partidos: Mapped[list["Partido"]] = relationship(back_populates="cancha")
