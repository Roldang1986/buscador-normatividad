from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, DateTime, Integer, String, Text
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

    # Distingue el numeral/parágrafo dentro de un artículo fragmentado
    # (ver app/ingest/dian_scraper.py: _fragmentar_articulo_por_numeral) —
    # numero_articulo se mantiene igual entre todas las filas del mismo
    # artículo fragmentado (ej. "879"), numeral las diferencia (ej. "6",
    # "PARÁGRAFO 2o"). NULL para artículos no fragmentados (la mayoría).
    numeral: Mapped[str | None] = mapped_column(String(20), nullable=True)

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


class DocumentoSFC(Base):
    """Segundo corpus (doctrina y jurisprudencia de la Superintendencia
    Financiera de Colombia), tabla independiente de `norma` — ver
    Ingest/SFC/schema.sql. Modelo de solo lectura para el agente RAG del
    endpoint /consulta-sfc: la ingesta real (Ingest/SFC/ingest_pilot.py)
    sigue insertando con SQL crudo, no vía este modelo."""

    __tablename__ = "documentos_sfc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # "concepto" (doctrina, no vinculante) | "fallo" | "jurisprudencia"
    # (decisión de un caso concreto, vinculante para las partes) — ver
    # SYSTEM_PROMPT_SFC en app/agent.py. Hoy solo hay "concepto" cargado.
    tipo_documento: Mapped[str] = mapped_column(Text, nullable=False)

    numero_documento: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    titulo: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumen: Mapped[str | None] = mapped_column(Text, nullable=True)
    texto_completo: Mapped[str | None] = mapped_column(Text, nullable=True)
    materias: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    url_archivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    tiene_texto_completo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fuente_atribucion: Mapped[str] = mapped_column(Text, nullable=False)

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
