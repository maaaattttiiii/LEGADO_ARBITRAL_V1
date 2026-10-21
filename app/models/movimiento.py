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
    case,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    ConceptoMovimiento,
    TipoMovimiento,
    check_enum,
    columna_enum,
)

if TYPE_CHECKING:
    from app.models.arbitro import Arbitro
    from app.models.usuario import Usuario


class MovimientoCuentaCorriente(TimestampMixin, Base):
    __tablename__ = "movimiento_cuenta_corriente"
    __table_args__ = (
        CheckConstraint("monto > 0", name="monto_positivo"),
        CheckConstraint("length(periodo) = 7", name="periodo_longitud"),
        UniqueConstraint(
            "designacion_id", "concepto", name="uq_movimiento_designacion_concepto"
        ),
        check_enum("tipo", TipoMovimiento, "tipo_movimiento"),
        check_enum("concepto", ConceptoMovimiento, "concepto_movimiento"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    arbitro_id: Mapped[int] = mapped_column(
        ForeignKey("arbitro.id", ondelete="RESTRICT"), nullable=False
    )
    designacion_id: Mapped[int | None] = mapped_column(
        ForeignKey("designacion.id", ondelete="RESTRICT")
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[TipoMovimiento] = mapped_column(
        columna_enum(TipoMovimiento, "tipo_movimiento"), nullable=False
    )
    concepto: Mapped[ConceptoMovimiento] = mapped_column(
        columna_enum(ConceptoMovimiento, "concepto_movimiento"), nullable=False
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(255))
    # Auditoría (RN-49): quién liquidó o cargó el movimiento.
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT")
    )

    arbitro: Mapped["Arbitro"] = relationship(back_populates="movimientos")
    usuario: Mapped["Usuario | None"] = relationship()


def calcular_saldo(session: Session, arbitro_id: int) -> Decimal:
    monto_firmado = case(
        (
            MovimientoCuentaCorriente.tipo == TipoMovimiento.CREDITO,
            MovimientoCuentaCorriente.monto,
        ),
        else_=-MovimientoCuentaCorriente.monto,
    )
    total = select(
        func.cast(func.coalesce(func.sum(monto_firmado), 0), Numeric(12, 2))
    ).where(MovimientoCuentaCorriente.arbitro_id == arbitro_id)

    valor = session.execute(total).scalar_one()
    return Decimal(valor).quantize(Decimal("0.01"))
