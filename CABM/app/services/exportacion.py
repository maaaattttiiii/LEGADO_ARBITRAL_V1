"""Liquidación mensual: filas, CSV para Excel y PDF imprimible."""

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.formato import formatear_moneda
from app.models.arbitro import Arbitro
from app.models.designacion import Designacion
from app.models.enums import ConceptoMovimiento, RolDesignacion, TipoMovimiento
from app.models.movimiento import MovimientoCuentaCorriente
from app.models.partido import Partido

CERO = Decimal("0.00")
CONCEPTOS_LIQUIDACION = (
    ConceptoMovimiento.HONORARIO,
    ConceptoMovimiento.RETENCION,
    ConceptoMovimiento.VIATICO,
)

ROL_ETIQUETAS = {
    RolDesignacion.PRINCIPAL.value: "Juez Principal",
    RolDesignacion.ASISTENTE_1.value: "Juez 2",
    RolDesignacion.ASISTENTE_2.value: "Juez 3",
    RolDesignacion.CUARTO.value: "Cuarto árbitro",
}

ENCABEZADO = (
    "Árbitro",
    "Legajo",
    "Partido",
    "Rol",
    "Honorario",
    "Retención (10%)",
    "Viático",
    "Neto a Cobrar",
)


@dataclass(frozen=True)
class FilaLiquidacion:
    apellido: str
    nombre: str
    legajo: str
    partido: str
    rol: RolDesignacion
    honorario: Decimal
    retencion: Decimal
    viatico: Decimal

    @property
    def arbitro(self) -> str:
        return f"{self.apellido}, {self.nombre}"

    @property
    def rol_etiqueta(self) -> str:
        return ROL_ETIQUETAS.get(self.rol.value, self.rol.value)

    @property
    def neto(self) -> Decimal:
        return self.honorario - self.retencion + self.viatico


def liquidacion_mensual(
    session: Session, *, periodo: str
) -> list[FilaLiquidacion]:
    """Filas de la liquidación del período, una por designación."""
    filas = (
        session.execute(
            select(
                MovimientoCuentaCorriente,
                Designacion,
                Partido,
                Arbitro,
            )
            .join(
                Designacion,
                MovimientoCuentaCorriente.designacion_id == Designacion.id,
            )
            .join(Partido, Designacion.partido_id == Partido.id)
            .join(Arbitro, MovimientoCuentaCorriente.arbitro_id == Arbitro.id)
            .where(
                MovimientoCuentaCorriente.periodo == periodo,
                MovimientoCuentaCorriente.concepto.in_(CONCEPTOS_LIQUIDACION),
            )
            .order_by(
                Arbitro.apellido,
                Arbitro.nombre,
                Partido.fecha_hora,
                Designacion.rol,
            )
        )
        .all()
    )

    agrupadas: dict[int, dict] = {}
    for movimiento, designacion, partido, arbitro in filas:
        acumulado = agrupadas.setdefault(
            designacion.id,
            {
                "apellido": arbitro.apellido,
                "nombre": arbitro.nombre,
                "legajo": arbitro.legajo,
                "partido": (
                    f"{partido.equipo_local} vs {partido.equipo_visitante}"
                ),
                "rol": designacion.rol,
                "honorario": CERO,
                "retencion": CERO,
                "viatico": CERO,
            },
        )
        concepto = ConceptoMovimiento(movimiento.concepto)
        if concepto is ConceptoMovimiento.HONORARIO:
            acumulado["honorario"] += Decimal(movimiento.monto)
        elif concepto is ConceptoMovimiento.RETENCION:
            acumulado["retencion"] += Decimal(movimiento.monto)
        elif concepto is ConceptoMovimiento.VIATICO:
            acumulado["viatico"] += Decimal(movimiento.monto)

    return [
        FilaLiquidacion(**datos)
        for datos in sorted(
            agrupadas.values(),
            key=lambda fila: (
                _ordenable(fila["apellido"]),
                _ordenable(fila["nombre"]),
            ),
        )
    ]


def _ordenable(texto: str) -> str:
    """Clave de orden alfabético insensible a tildes (SQLite ordena por bytes)."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return normalizado.encode("ascii", "ignore").decode("ascii").lower()


def _totales(
    filas: list[FilaLiquidacion],
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    honorario = sum((f.honorario for f in filas), CERO)
    retencion = sum((f.retencion for f in filas), CERO)
    viatico = sum((f.viatico for f in filas), CERO)
    return honorario, retencion, viatico, honorario - retencion + viatico


def liquidacion_csv(filas: list[FilaLiquidacion]) -> str:
    """CSV para Excel (es-AR): BOM, separador ';' y decimales con coma."""
    lineas = ["\ufeff" + ";".join(ENCABEZADO)]
    for fila in filas:
        lineas.append(
            ";".join(
                [
                    fila.arbitro,
                    fila.legajo,
                    fila.partido,
                    fila.rol_etiqueta,
                    formatear_moneda(fila.honorario),
                    formatear_moneda(fila.retencion),
                    formatear_moneda(fila.viatico),
                    formatear_moneda(fila.neto),
                ]
            )
        )

    honorario, retencion, viatico, neto = _totales(filas)
    lineas.append(
        ";".join(
            [
                "TOTAL",
                "",
                "",
                "",
                formatear_moneda(honorario),
                formatear_moneda(retencion),
                formatear_moneda(viatico),
                formatear_moneda(neto),
            ]
        )
    )
    return "\n".join(lineas) + "\n"


def liquidacion_pdf(filas: list[FilaLiquidacion], *, periodo: str) -> bytes:
    """PDF imprimible con el membrete de la asociación."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Liquidación {periodo}",
        author="CABM - Colegio de Árbitros",
    )

    estilos = getSampleStyleSheet()
    titulo = Paragraph(
        "CABM · Colegio de Árbitros", estilos["Title"]
    )
    subtitulo = Paragraph(
        f"Liquidación mensual · período {periodo}", estilos["Heading2"]
    )

    datos = [
        list(ENCABEZADO),
        *[
            [
                fila.arbitro,
                fila.legajo,
                fila.partido,
                fila.rol_etiqueta,
                formatear_moneda(fila.honorario),
                formatear_moneda(fila.retencion),
                formatear_moneda(fila.viatico),
                formatear_moneda(fila.neto),
            ]
            for fila in filas
        ],
    ]
    honorario, retencion, viatico, neto = _totales(filas)
    datos.append(
        [
            "TOTAL",
            "",
            "",
            "",
            formatear_moneda(honorario),
            formatear_moneda(retencion),
            formatear_moneda(viatico),
            formatear_moneda(neto),
        ]
    )

    tabla = Table(
        datos,
        colWidths=[45 * mm, 18 * mm, 62 * mm, 28 * mm, 27 * mm, 27 * mm, 25 * mm, 30 * mm],
        repeatRows=1,
    )
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#212529")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ADB5BD")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8F9FA")]),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DEE2E6")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    pie = Paragraph(
        "La retención del 10% se aplica sobre el honorario seco; el viático es "
        "un reembolso y no se retiene. Neto = honorario - retención + viático.",
        estilos["Italic"],
    )

    documento.build(
        [titulo, subtitulo, Spacer(1, 6 * mm), tabla, Spacer(1, 4 * mm), pie]
    )
    return buffer.getvalue()
