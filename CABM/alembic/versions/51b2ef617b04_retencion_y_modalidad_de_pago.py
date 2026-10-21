"""retencion y modalidad de pago

Revision ID: 51b2ef617b04
Revises: 03974f692eb8
Create Date: 2026-10-20 16:22:26.534652

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '51b2ef617b04'
down_revision: Union[str, Sequence[str], None] = '03974f692eb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONCEPTO_ANTERIOR = (
    "concepto IN ('HONORARIO', 'VIATICO', 'DESCUENTO', "
    "'ADELANTO', 'PAGO', 'MULTA', 'AJUSTE')"
)
CONCEPTO_NUEVO = (
    "concepto IN ('HONORARIO', 'VIATICO', 'DESCUENTO', "
    "'ADELANTO', 'PAGO', 'MULTA', 'AJUSTE', 'RETENCION')"
)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('partido', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'modalidad_pago',
                sa.String(length=20),
                server_default='EN_CANCHA',
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            batch_op.f('ck_partido_modalidad_pago'),
            "modalidad_pago IN ('EN_CANCHA', 'DIFERIDO')",
        )

    with op.batch_alter_table(
        'movimiento_cuenta_corriente', schema=None
    ) as batch_op:
        batch_op.drop_constraint(
            batch_op.f('ck_movimiento_cuenta_corriente_concepto_movimiento'),
            type_='check',
        )
        batch_op.create_check_constraint(
            batch_op.f('ck_movimiento_cuenta_corriente_concepto_movimiento'),
            CONCEPTO_NUEVO,
        )


def downgrade() -> None:
    """Downgrade schema.

    Revierte el CHECK de `concepto` a los valores previos: si ya existen
    movimientos con concepto RETENCION el downgrade falla a propósito (evita
    dejar filas que violan la constraint).
    """
    with op.batch_alter_table(
        'movimiento_cuenta_corriente', schema=None
    ) as batch_op:
        batch_op.drop_constraint(
            batch_op.f('ck_movimiento_cuenta_corriente_concepto_movimiento'),
            type_='check',
        )
        batch_op.create_check_constraint(
            batch_op.f('ck_movimiento_cuenta_corriente_concepto_movimiento'),
            CONCEPTO_ANTERIOR,
        )

    with op.batch_alter_table('partido', schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f('ck_partido_modalidad_pago'), type_='check'
        )
        batch_op.drop_column('modalidad_pago')
