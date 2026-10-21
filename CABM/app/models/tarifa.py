from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    CategoriaArbitro,
    RolDesignacion,
    check_enum,
    columna_enum,
)

if TYPE_CHECKING:
    from app.models.torneo import CategoriaTorneo


class Tarifa(TimestampMixin, Base):
    """Arancel de honorario.

    La clave de resolución es ``(categoría de torneo, rol, categoría de árbitro)``:

    - ``rol=None`` → aplica a cualquier rol de campo (principal o asistentes).
    - ``categoria_arbitro=None`` → aplica a cualquier escalafón (ej.: 3° juez).
    - ``categoria_arbitro=UNICA`` → torneos con arancel único (Inferiores, Master).
    """

    __tablename__ = "tarifa"
    __table_args__ = (
        UniqueConstraint(
            "categoria_torneo_id",
            "rol",
            "categoria_arbitro",
            "vigencia_desde",
            name="uq_tarifa_categoria_rol_cat_desde",
        ),
        CheckConstraint("monto_base > 0", name="monto_base_positivo"),
        CheckConstraint(
            "vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde",
            name="vigencia_valida",
        ),
        check_enum("rol", RolDesignacion, "rol_tarifa"),
        check_enum("categoria_arbitro", CategoriaArbitro, "categoria_arbitro_tarifa"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_torneo_id: Mapped[int] = mapped_column(
        ForeignKey("categoria_torneo.id", ondelete="RESTRICT"), nullable=False
    )
    rol: Mapped[RolDesignacion | None] = mapped_column(
        columna_enum(RolDesignacion, "rol_tarifa"), nullable=True
    )
    categoria_arbitro: Mapped[CategoriaArbitro | None] = mapped_column(
        columna_enum(CategoriaArbitro, "categoria_arbitro_tarifa"), nullable=True
    )
    monto_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vigencia_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date)
    descripcion: Mapped[str | None] = mapped_column(String(255))

    categoria: Mapped["CategoriaTorneo"] = relationship(back_populates="tarifas")
