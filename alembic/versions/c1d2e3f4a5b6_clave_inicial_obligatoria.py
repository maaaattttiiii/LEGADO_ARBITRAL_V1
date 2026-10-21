"""clave inicial obligatoria

Revision ID: c1d2e3f4a5b6
Revises: aab622ffc2bc
Create Date: 2026-10-21

"""

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "aab622ffc2bc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usuario") as batch:
        batch.add_column(
            sa.Column(
                "debe_cambiar_password",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("usuario") as batch:
        batch.drop_column("debe_cambiar_password")
