from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.usuario import Usuario


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
    # Auditoría (RN-49): quién ejecutó el cierre.
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT")
    )

    usuario: Mapped["Usuario | None"] = relationship()
