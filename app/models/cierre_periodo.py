from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class CierrePeriodo(TimestampMixin, Base):
    """Cierre contable de un período ``AAAA-MM``.

    Mientras existe el registro, el período no admite altas de partidos,
    designaciones, liquidaciones, cobros ni ajustes: las correcciones se
    registran como ajuste en un período abierto (RN-38).
    """

    __tablename__ = "cierre_periodo"
    __table_args__ = (
        CheckConstraint(
            "length(periodo) = 7", name="formato_periodo"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo: Mapped[str] = mapped_column(
        String(7), unique=True, nullable=False
    )
    cerrado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
