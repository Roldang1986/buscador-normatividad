from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Dimensión del embedding: Anthropic no expone un endpoint de embeddings propio,
# así que se usa Voyage AI (partner recomendado por Anthropic). El modelo por
# defecto (ver app/embeddings.py, VOYAGE_EMBEDDING_MODEL) genera vectores de
# 1024 dimensiones. Si se cambia de modelo/dimensión hay que actualizar esta
# constante y la migración correspondiente.
EMBEDDING_DIM = 1024


class Norma(Base):
    __tablename__ = "norma"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ej. "articulo_et", "decreto", "concepto_dian"
    tipo_norma: Mapped[str] = mapped_column(String(100), nullable=False)

    numero_articulo: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Ej. "Estatuto Tributario art. 420"
    fuente: Mapped[str] = mapped_column(Text, nullable=False)

    url_fuente: Mapped[str | None] = mapped_column(Text, nullable=True)

    texto: Mapped[str] = mapped_column(Text, nullable=False)

    # Ej. "vigente", "modificado", "derogado"
    estado_vigencia: Mapped[str] = mapped_column(String(50), nullable=False)

    nota_vigencia: Mapped[str | None] = mapped_column(Text, nullable=True)

    fecha_ingesta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
