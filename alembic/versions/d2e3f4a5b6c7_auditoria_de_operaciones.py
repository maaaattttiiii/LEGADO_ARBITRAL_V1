"""auditoria de operaciones sensibles

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-21

"""

import sqlalchemy as sa
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("movimiento_cuenta_corriente") as batch:
        batch.add_column(sa.Column("usuario_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_movimiento_cuenta_corriente_usuario_id_usuario",
            "usuario",
            ["usuario_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    with op.batch_alter_table("cierre_periodo") as batch:
        batch.add_column(sa.Column("usuario_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_cierre_periodo_usuario_id_usuario",
            "usuario",
            ["usuario_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("cierre_periodo") as batch:
        batch.drop_constraint(
            "fk_cierre_periodo_usuario_id_usuario", type_="foreignkey"
        )
        batch.drop_column("usuario_id")
    with op.batch_alter_table("movimiento_cuenta_corriente") as batch:
        batch.drop_constraint(
            "fk_movimiento_cuenta_corriente_usuario_id_usuario", type_="foreignkey"
        )
        batch.drop_column("usuario_id")
