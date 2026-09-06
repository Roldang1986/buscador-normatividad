"""add numeral column

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Columna `numeral`, NO una FK autoreferencial — el esquema de `norma`
    # es deliberadamente plano/desnormalizado (cada fila ya repite
    # tipo_norma/fuente/estado_vigencia/nota_vigencia, sin relaciones a
    # otras filas). Para un artículo fragmentado por numeral (ver
    # app/ingest/dian_scraper.py: _fragmentar_articulo_por_numeral),
    # numero_articulo se mantiene igual en todas las filas del mismo
    # artículo (ej. "879" para las 35 filas de sus numerales/parágrafos)
    # y `numeral` distingue cuál parte es cada una (ej. "6", "27",
    # "PARÁGRAFO 2o"). NULL para artículos no fragmentados — la inmensa
    # mayoría del ET sigue con una sola fila por numero_articulo.
    op.add_column("norma", sa.Column("numeral", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("norma", "numeral")
