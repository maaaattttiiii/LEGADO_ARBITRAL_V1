from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class PrecioCombustible(TimestampMixin, Base):
    __tablename__ = "precio_combustible"
    __table_args__ = (
        UniqueConstraint("vigencia_desde", name="uq_precio_combustible_vigencia_desde"),
        CheckConstraint("precio_litro > 0", name="precio_litro_positivo"),
        CheckConstraint(
            "vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde",
            name="precio_vigencia_valida",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    precio_litro: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    vigencia_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date)
    descripcion: Mapped[str | None] = mapped_column(String(255))
