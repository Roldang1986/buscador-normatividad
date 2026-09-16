"""Piloto de ingesta: raspa, descarga texto completo, embebe e inserta en
Neon (tabla documentos_sfc) un subconjunto de la colección `ac` (Doctrina y
conceptos). Solo para validar el flujo completo antes del scraping masivo —
no es el pipeline de producción.

Reutiliza app.embeddings.embed_document (mismo modelo/dimensión Voyage que
el corpus tributario) para que ambos corpus sean comparables si en algún
momento se necesita, aunque las búsquedas del frontend nunca los mezclan.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from sqlalchemy import text

from app.database import engine
from app.embeddings import embed_document
from scraper import raspar_coleccion

FUENTE_ATRIBUCION = "Fuente: Superintendencia Financiera de Colombia www.superfinanciera.gov.co"

# Límite de caracteres del texto completo dentro del input de embedding,
# para no acercarse al límite de tokens de voyage-3.5 en un solo request.
TRUNCADO_TEXTO_COMPLETO = 12000


def _texto_para_embedding(registro: dict) -> str:
    partes = [
        registro.get("titulo") or "",
        "Materias: " + ", ".join(registro.get("materias") or []),
        "Resumen: " + (registro.get("resumen") or ""),
    ]
    texto_completo = registro.get("texto_completo")
    if texto_completo:
        partes.append(texto_completo[:TRUNCADO_TEXTO_COMPLETO])
    return "\n\n".join(p for p in partes if p.strip())


INSERT_SQL = text(
    """
    INSERT INTO documentos_sfc (
        tipo_documento, numero_documento, fecha_texto, expediente_radicado,
        autor_corporativo, titulo, documento_fuente, resumen, notas,
        materias, otros_autores, url_archivo, tipo_archivo,
        tiene_texto_completo, texto_completo, motivo_sin_texto,
        fuente_atribucion, embedding
    ) VALUES (
        :tipo_documento, :numero_documento, :fecha_texto, :expediente_radicado,
        :autor_corporativo, :titulo, :documento_fuente, :resumen, :notas,
        :materias, :otros_autores, :url_archivo, :tipo_archivo,
        :tiene_texto_completo, :texto_completo, :motivo_sin_texto,
        :fuente_atribucion, :embedding
    )
    ON CONFLICT (tipo_documento, numero_documento) WHERE numero_documento IS NOT NULL
    DO NOTHING
    RETURNING id
    """
)


def ingestar_pilotos(coleccion: str, max_paginas: int, pausa: float = 1.0) -> dict:
    registros = raspar_coleccion(coleccion, max_paginas=max_paginas, dry_run=False, pausa=pausa)

    insertados = 0
    omitidos_sin_texto = 0
    omitidos_duplicados = 0

    with engine.begin() as conn:
        for r in registros:
            texto_embedding = _texto_para_embedding(r)
            if not texto_embedding.strip():
                omitidos_sin_texto += 1
                continue

            vector = embed_document(texto_embedding)

            resultado = conn.execute(
                INSERT_SQL,
                {
                    "tipo_documento": r["tipo_documento"],
                    "numero_documento": r["numero_documento"],
                    "fecha_texto": r["fecha_texto"],
                    "expediente_radicado": r["expediente_radicado"],
                    "autor_corporativo": r["autor_corporativo"],
                    "titulo": r["titulo"],
                    "documento_fuente": r["documento_fuente"],
                    "resumen": r["resumen"],
                    "notas": r["notas"],
                    "materias": r["materias"],
                    "otros_autores": r["otros_autores"],
                    "url_archivo": r["url_archivo"],
                    "tipo_archivo": r["tipo_archivo"],
                    "tiene_texto_completo": r["tiene_texto_completo"],
                    "texto_completo": r.get("texto_completo"),
                    "motivo_sin_texto": r.get("motivo_sin_texto"),
                    "fuente_atribucion": FUENTE_ATRIBUCION,
                    "embedding": "[" + ",".join(repr(x) for x in vector) + "]",
                },
            )
            if resultado.fetchone() is not None:
                insertados += 1
            else:
                omitidos_duplicados += 1

    return {
        "raspados": len(registros),
        "insertados": insertados,
        "omitidos_sin_texto_para_embedding": omitidos_sin_texto,
        "omitidos_duplicados": omitidos_duplicados,
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--coleccion", default="ac")
    ap.add_argument("--paginas", type=int, default=1)
    ap.add_argument("--pausa", type=float, default=1.0)
    args = ap.parse_args()

    resumen = ingestar_pilotos(args.coleccion, args.paginas, args.pausa)
    print(resumen)
