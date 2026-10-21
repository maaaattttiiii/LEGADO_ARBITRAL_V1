from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.partido import Partido
    from app.models.tarifa import Tarifa


class CategoriaTorneo(TimestampMixin, Base):
    __tablename__ = "categoria_torneo"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    torneos: Mapped[list["Torneo"]] = relationship(back_populates="categoria")
    tarifas: Mapped[list["Tarifa"]] = relationship(back_populates="categoria")


class Torneo(TimestampMixin, Base):
    __tablename__ = "torneo"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria_torneo_id: Mapped[int] = mapped_column(
        ForeignKey("categoria_torneo.id", ondelete="RESTRICT"), nullable=False
    )
    temporada: Mapped[str | None] = mapped_column(String(20))
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    categoria: Mapped["CategoriaTorneo"] = relationship(back_populates="torneos")
    partidos: Mapped[list["Partido"]] = relationship(back_populates="torneo")
