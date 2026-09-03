import os

import anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.embeddings import embed_query
from app.models import Norma

MODEL_ID = "claude-sonnet-5"
TOP_K = 5

MENSAJE_SIN_NORMATIVIDAD = "No encontré normatividad indexada sobre esto."

SYSTEM_PROMPT = f"""Eres un asistente experto en normatividad tributaria colombiana.
Respondes preguntas ÚNICAMENTE con base en los fragmentos de normatividad que se
te entregan como contexto en cada mensaje (recuperados por búsqueda semántica
de una base de datos de normas). Nunca respondas con conocimiento general ni
con lo que recuerdes de tu entrenamiento sobre leyes tributarias.

Reglas estrictas:
1. Solo puedes afirmar algo si está respaldado textualmente por uno o más de
   los fragmentos entregados. No completes vacíos de información con memoria
   propia, inferencias legales generales ni suposiciones.
2. Cada afirmación debe estar acompañada de su cita exacta: tipo de norma,
   número de artículo (si aplica) y fuente, tal como aparecen en el fragmento
   correspondiente. No inventes ni parafrasees números de artículo, decretos
   o fuentes que no estén en el contexto.
3. Si los fragmentos entregados no contienen información suficiente o
   relevante para responder la pregunta, no intentes responderla de todos
   modos: responde exactamente "{MENSAJE_SIN_NORMATIVIDAD}" y dejas la lista
   de fragmentos citados vacía.
4. Si algunos fragmentos son relevantes pero no cubren toda la pregunta,
   responde solo la parte que sí está respaldada y aclara explícitamente qué
   parte no pudiste responder por falta de normatividad indexada.
5. Para cada fragmento citado, indica su estado_vigencia. Si un fragmento
   está marcado como "modificado" o "derogado", adviértelo explícitamente
   en la respuesta y, si existe nota_vigencia, inclúyela (ej. "modificado
   por el artículo 57 de la Ley 2277 de 2022").
"""


class _RespuestaAgente(BaseModel):
    respuesta: str
    fragmentos_citados: list[int]


def buscar_fragmentos_relevantes(db: Session, pregunta: str, top_k: int = TOP_K) -> list[Norma]:
    """Búsqueda semántica top-k en `norma` por similitud coseno sobre `embedding`."""
    vector = embed_query(pregunta)
    return (
        db.query(Norma)
        .filter(Norma.embedding.is_not(None))
        .order_by(Norma.embedding.cosine_distance(vector))
        .limit(top_k)
        .all()
    )


def _formatear_contexto(fragmentos: list[Norma]) -> str:
    bloques = []
    for i, norma in enumerate(fragmentos, start=1):
        bloques.append(
            f"[Fragmento {i}]\n"
            f"tipo_norma: {norma.tipo_norma}\n"
            f"numero_articulo: {norma.numero_articulo or 'N/A'}\n"
            f"fuente: {norma.fuente}\n"
            f"estado_vigencia: {norma.estado_vigencia}\n"
            f"nota_vigencia: {norma.nota_vigencia or 'N/A'}\n"
            f"texto: {norma.texto}"
        )
    return "\n\n".join(bloques)


def _fuente_dict(norma: Norma) -> dict:
    return {
        "id": norma.id,
        "tipo_norma": norma.tipo_norma,
        "numero_articulo": norma.numero_articulo,
        "fuente": norma.fuente,
        "url_fuente": norma.url_fuente,
        "estado_vigencia": norma.estado_vigencia,
    }


def responder_pregunta(db: Session, pregunta: str) -> dict:
    """Punto de entrada del agente RAG: busca fragmentos y llama a Claude."""
    fragmentos = buscar_fragmentos_relevantes(db, pregunta)

    if not fragmentos:
        return {"respuesta": MENSAJE_SIN_NORMATIVIDAD, "fuentes": []}

    contexto = _formatear_contexto(fragmentos)

    user_message = (
        "Fragmentos de normatividad recuperados (usa solo esto como fuente de verdad):\n\n"
        f"{contexto}\n\n"
        f"Pregunta del usuario: {pregunta}\n\n"
        "Responde en 'respuesta' citando explícitamente tipo de norma, número de "
        "artículo y fuente de cada afirmación. En 'fragmentos_citados' incluye los "
        "números de los fragmentos (1-based) que respaldan tu respuesta. Si ningún "
        "fragmento es suficiente, deja 'fragmentos_citados' vacío y responde "
        f'exactamente: "{MENSAJE_SIN_NORMATIVIDAD}"'
    )

    client = anthropic.Anthropic(api_key=os.environ["APP_ANTHROPIC_API_KEY"])
    response = client.messages.parse(
        model=MODEL_ID,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        output_format=_RespuestaAgente,
    )
    resultado = response.parsed_output

    fuentes = [
        _fuente_dict(fragmentos[i - 1])
        for i in resultado.fragmentos_citados
        if 1 <= i <= len(fragmentos)
    ]

    return {"respuesta": resultado.respuesta, "fuentes": fuentes}
