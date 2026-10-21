"""reapertura de periodos y auditoria

Revision ID: d3e4f5a6b7c8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-21

"""

import sqlalchemy as sa
from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cierre_periodo") as batch:
        batch.add_column(
            sa.Column("reabierto_en", sa.DateTime(timezone=True), nullable=True)
        )
    op.create_table(
        "auditoria_periodo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo", sa.String(length=7), nullable=False),
        sa.Column("accion", sa.String(length=20), nullable=False),
        sa.Column("motivo", sa.String(length=500), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(periodo) = 7",
            name="ck_auditoria_periodo_formato_periodo",
        ),
        sa.CheckConstraint(
            "accion IN ('CIERRE', 'REAPERTURA')",
            name="ck_auditoria_periodo_accion_auditoria",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name="fk_auditoria_periodo_usuario_id_usuario",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auditoria_periodo"),
    )


def downgrade() -> None:
    op.drop_table("auditoria_periodo")
    with op.batch_alter_table("cierre_periodo") as batch:
        batch.drop_column("reabierto_en")
