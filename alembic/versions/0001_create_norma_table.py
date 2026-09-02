"""create norma table

Revision ID: 0001
Revises:
Create Date: 2026-09-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "norma",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tipo_norma", sa.String(length=100), nullable=False),
        sa.Column("numero_articulo", sa.String(length=50), nullable=True),
        sa.Column("fuente", sa.Text(), nullable=False),
        sa.Column("url_fuente", sa.Text(), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("estado_vigencia", sa.String(length=50), nullable=False),
        sa.Column("nota_vigencia", sa.Text(), nullable=True),
        sa.Column(
            "fecha_ingesta",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("norma")
    op.execute("DROP EXTENSION IF EXISTS vector")
