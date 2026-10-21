from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import AccionAuditoria, check_enum, columna_enum

if TYPE_CHECKING:
    from app.models.usuario import Usuario


class AuditoriaPeriodo(TimestampMixin, Base):
    """Historial inmutable de cierres y reaperturas de período (RN-49).

    Se guarda una fila por acción, con el motivo de la reapertura y el usuario
    que la ejecutó. Es append-only: no se edita ni se borra.
    """

    __tablename__ = "auditoria_periodo"
    __table_args__ = (
        CheckConstraint("length(periodo) = 7", name="formato_periodo"),
        check_enum("accion", AccionAuditoria, "accion_auditoria"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)
    accion: Mapped[AccionAuditoria] = mapped_column(
        columna_enum(AccionAuditoria, "accion_auditoria"), nullable=False
    )
    motivo: Mapped[str | None] = mapped_column(String(500))
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT")
    )

    usuario: Mapped["Usuario | None"] = relationship()
