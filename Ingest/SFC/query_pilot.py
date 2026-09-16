"""Consulta RAG de prueba, acotada EXCLUSIVAMENTE a documentos_sfc — nunca
toca `norma` (corpus tributario). Solo para validar el piloto antes de
integrar un endpoint real; no es el pipeline de producción."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

import anthropic
from pydantic import BaseModel
from sqlalchemy import text

from app.database import engine
from app.embeddings import embed_query

MODEL_ID = "claude-sonnet-5"
TOP_K = 5

MENSAJE_SIN_INFO = "No encontré doctrina/jurisprudencia de la Superfinanciera indexada sobre esto."

SYSTEM_PROMPT = f"""Eres un asistente experto en doctrina y jurisprudencia de la
Superintendencia Financiera de Colombia (SFC). Respondes ÚNICAMENTE con base en
los fragmentos entregados como contexto (recuperados por búsqueda semántica de
un catálogo de conceptos, fallos y jurisprudencia de la SFC). Nunca respondas
con conocimiento general ni con lo que recuerdes de tu entrenamiento.

Reglas estrictas:
1. Solo puedes afirmar algo si está respaldado textualmente por uno o más
   fragmentos entregados.
2. Cada afirmación debe citar el fragmento: tipo de documento, número y fecha
   tal como aparecen en el fragmento.
3. Si los fragmentos no contienen información suficiente, responde
   exactamente "{MENSAJE_SIN_INFO}" y deja la lista de fragmentos citados vacía.
4. Al final de la respuesta, incluye la línea de atribución de fuente tal
   como aparece en fuente_atribucion de los fragmentos citados.
"""


class _Respuesta(BaseModel):
    respuesta: str
    fragmentos_citados: list[int]


SQL_BUSQUEDA = text(
    """
    SELECT id, tipo_documento, numero_documento, fecha_texto, titulo, resumen,
           texto_completo, materias, fuente_atribucion
    FROM documentos_sfc
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> :query_vector
    LIMIT :top_k
    """
)


def buscar_fragmentos(pregunta: str, top_k: int = TOP_K) -> list[dict]:
    vector = embed_query(pregunta)
    vector_literal = "[" + ",".join(repr(x) for x in vector) + "]"
    with engine.connect() as conn:
        rows = conn.execute(SQL_BUSQUEDA, {"query_vector": vector_literal, "top_k": top_k}).mappings().all()
    return [dict(r) for r in rows]


def _formatear_contexto(fragmentos: list[dict]) -> str:
    bloques = []
    for i, f in enumerate(fragmentos, start=1):
        texto = (f["texto_completo"] or f["resumen"] or "")[:6000]
        bloques.append(
            f"[Fragmento {i}]\n"
            f"tipo_documento: {f['tipo_documento']}\n"
            f"numero_documento: {f['numero_documento']}\n"
            f"fecha: {f['fecha_texto']}\n"
            f"titulo: {f['titulo']}\n"
            f"materias: {', '.join(f['materias'] or [])}\n"
            f"fuente_atribucion: {f['fuente_atribucion']}\n"
            f"texto: {texto}"
        )
    return "\n\n".join(bloques)


def responder(pregunta: str) -> dict:
    fragmentos = buscar_fragmentos(pregunta)
    if not fragmentos:
        return {"respuesta": MENSAJE_SIN_INFO, "fuentes": []}

    contexto = _formatear_contexto(fragmentos)
    user_message = (
        "Fragmentos recuperados (usa solo esto como fuente de verdad):\n\n"
        f"{contexto}\n\n"
        f"Pregunta del usuario: {pregunta}\n\n"
        "Responde citando tipo de documento, número y fecha de cada fragmento "
        "usado. En 'fragmentos_citados' incluye los números (1-based) que "
        "respaldan tu respuesta."
    )

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL_ID,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        output_format=_Respuesta,
    )
    resultado = response.parsed_output

    fuentes = [
        {
            "id": fragmentos[i - 1]["id"],
            "numero_documento": fragmentos[i - 1]["numero_documento"],
            "titulo": fragmentos[i - 1]["titulo"],
        }
        for i in resultado.fragmentos_citados
        if 1 <= i <= len(fragmentos)
    ]
    return {"respuesta": resultado.respuesta, "fuentes": fuentes}


if __name__ == "__main__":
    preguntas = [
        "¿Puede el oficial de cumplimiento renunciar a su cargo, y qué pasa con la vacancia mientras se nombra un reemplazo?",
        "¿Qué ha dicho la Superfinanciera sobre el retiro parcial de cesantías durante la emergencia sanitaria por COVID-19?",
    ]
    for p in preguntas:
        print("=" * 70)
        print("PREGUNTA:", p)
        r = responder(p)
        print("\nRESPUESTA:\n", r["respuesta"])
        print("\nFUENTES:", r["fuentes"])
        print()
