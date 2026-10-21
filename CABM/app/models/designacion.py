from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    EstadoDesignacion,
    RolDesignacion,
    check_enum,
    columna_enum,
)

if TYPE_CHECKING:
    from app.models.arbitro import Arbitro
    from app.models.partido import Partido


class Designacion(TimestampMixin, Base):
    __tablename__ = "designacion"
    __table_args__ = (
        UniqueConstraint(
            "partido_id", "arbitro_id", name="uq_designacion_partido_arbitro"
        ),
        UniqueConstraint("partido_id", "rol", name="uq_designacion_partido_rol"),
        check_enum("rol", RolDesignacion, "rol_designacion"),
        check_enum("estado", EstadoDesignacion, "estado_designacion"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    partido_id: Mapped[int] = mapped_column(
        ForeignKey("partido.id", ondelete="CASCADE"), nullable=False
    )
    arbitro_id: Mapped[int] = mapped_column(
        ForeignKey("arbitro.id", ondelete="RESTRICT"), nullable=False
    )
    rol: Mapped[RolDesignacion] = mapped_column(
        columna_enum(RolDesignacion, "rol_designacion"), nullable=False
    )
    estado: Mapped[EstadoDesignacion] = mapped_column(
        columna_enum(EstadoDesignacion, "estado_designacion"),
        default=EstadoDesignacion.PROPUESTA,
        server_default=EstadoDesignacion.PROPUESTA.value,
        nullable=False,
    )
    fecha_designacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    honorario: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    usa_auto: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    observaciones: Mapped[str | None] = mapped_column(Text)

    partido: Mapped["Partido"] = relationship(back_populates="designaciones")
    arbitro: Mapped["Arbitro"] = relationship(back_populates="designaciones")
