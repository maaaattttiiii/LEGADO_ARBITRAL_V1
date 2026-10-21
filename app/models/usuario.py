from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import RolUsuario, check_enum, columna_enum

if TYPE_CHECKING:
    from app.models.arbitro import Arbitro


class Usuario(TimestampMixin, Base):
    """Credenciales de acceso al sistema (RN-42).

    Un usuario ``TESORERO`` no está vinculado a un árbitro; un usuario
    ``ARBITRO`` sí, y esa vinculación es la que acota qué datos puede ver.
    """

    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint(
            "rol <> 'ARBITRO' OR arbitro_id IS NOT NULL",
            name="arbitro_requerido",
        ),
        check_enum("rol", RolUsuario, "rol_usuario"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(
        columna_enum(RolUsuario, "rol_usuario"), nullable=False
    )
    arbitro_id: Mapped[int | None] = mapped_column(
        ForeignKey("arbitro.id", ondelete="RESTRICT")
    )
    activo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    arbitro: Mapped["Arbitro | None"] = relationship()
