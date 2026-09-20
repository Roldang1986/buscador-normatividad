import anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.embeddings import embed_query
from app.models import DocumentoSFC, Norma

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
6. Para cifras, porcentajes, plazos, montos en UVT y condiciones específicas
   (literales, numerales), transcribe el texto exacto del fragmento entre
   comillas — no los parafrasees ni los resumas, aunque el resto de la
   respuesta sí esté en tus propias palabras.
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

    client = anthropic.Anthropic()
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


# ---------------------------------------------------------------------------
# Corpus SFC (doctrina y jurisprudencia de la Superintendencia Financiera).
# Función separada a propósito, no una generalización de responder_pregunta:
# el corpus tributario de arriba queda intocado mientras este sigue en
# construcción. Espejo de Ingest/SFC/query_pilot.py, pero como parte del
# agente real (usado por POST /consulta-sfc) en vez de un script de prueba.
# ---------------------------------------------------------------------------

TOP_K_SFC = 5

MENSAJE_SIN_NORMATIVIDAD_SFC = (
    "No encontré doctrina o jurisprudencia de la Superfinanciera indexada sobre esto."
)

SYSTEM_PROMPT_SFC = f"""Eres un asistente experto en doctrina y jurisprudencia de la
Superintendencia Financiera de Colombia (SFC). Respondes ÚNICAMENTE con base en los
fragmentos entregados como contexto en cada mensaje (recuperados por búsqueda
semántica de un catálogo de conceptos, fallos y jurisprudencia de la SFC). Nunca
respondas con conocimiento general ni con lo que recuerdes de tu entrenamiento.

Distingue SIEMPRE el valor normativo de cada fragmento según su tipo_documento:
- "concepto" (doctrina): es la interpretación/opinión de la Superintendencia sobre
  una norma, dirigida a quien consulta. NO es vinculante ni de obligatorio
  cumplimiento para terceros, no sienta precedente judicial, y la propia entidad
  puede reconsiderarla en un concepto posterior. Preséntalo como "según el
  concepto de la SFC No. X..." o "en criterio de la Superintendencia...", nunca
  como si fuera una norma o una decisión obligatoria.
- "fallo" / "jurisprudencia": es la decisión de una autoridad sobre un caso
  concreto. SÍ es vinculante para las partes de ese caso y puede tener valor de
  precedente. Preséntalo como "en el fallo/la decisión No. X..." y aclara que
  aplica al caso decidido — no lo generalices automáticamente a cualquier
  situación distinta.

Si citas fragmentos de ambos tipos en la misma respuesta, sepáralos
explícitamente: cuáles son doctrina (no vinculante) y cuáles son decisión de un
caso concreto (vinculante para las partes). No les des el mismo peso.

(Hoy la base solo tiene doctrina —tipo_documento="concepto"— indexada; fallos y
jurisprudencia se cargarán más adelante, pero esta distinción rige desde ya.)

Reglas estrictas:
1. Solo puedes afirmar algo si está respaldado textualmente por uno o más de
   los fragmentos entregados. No completes vacíos de información con memoria
   propia ni suposiciones.
2. Cada afirmación cita tipo de documento, número y fecha tal como aparecen en
   el fragmento correspondiente. No inventes ni parafrasees números ni fechas.
3. Si los fragmentos entregados no contienen información suficiente o
   relevante, no intentes responder de todos modos: responde exactamente
   "{MENSAJE_SIN_NORMATIVIDAD_SFC}" y deja la lista de fragmentos citados vacía.
4. Al final de la respuesta, incluye la línea de fuente_atribucion de los
   fragmentos citados, tal como aparece en el fragmento.
"""


class _RespuestaAgenteSFC(BaseModel):
    respuesta: str
    fragmentos_citados: list[int]


def buscar_fragmentos_relevantes_sfc(
    db: Session, pregunta: str, top_k: int = TOP_K_SFC
) -> list[DocumentoSFC]:
    """Búsqueda semántica top-k en `documentos_sfc` por similitud coseno.
    Nunca toca `norma` (corpus tributario)."""
    vector = embed_query(pregunta)
    return (
        db.query(DocumentoSFC)
        .filter(DocumentoSFC.embedding.is_not(None))
        .order_by(DocumentoSFC.embedding.cosine_distance(vector))
        .limit(top_k)
        .all()
    )


def _formatear_contexto_sfc(fragmentos: list[DocumentoSFC]) -> str:
    bloques = []
    for i, d in enumerate(fragmentos, start=1):
        texto = (d.texto_completo or d.resumen or "")[:8000]
        bloques.append(
            f"[Fragmento {i}]\n"
            f"tipo_documento: {d.tipo_documento}\n"
            f"numero_documento: {d.numero_documento or 'N/A'}\n"
            f"fecha: {d.fecha_texto or 'N/A'}\n"
            f"titulo: {d.titulo or 'N/A'}\n"
            f"fuente_atribucion: {d.fuente_atribucion}\n"
            f"texto: {texto}"
        )
    return "\n\n".join(bloques)


def _fuente_dict_sfc(d: DocumentoSFC) -> dict:
    return {
        "id": d.id,
        "tipo_documento": d.tipo_documento,
        "numero_documento": d.numero_documento,
        "fecha_texto": d.fecha_texto,
        "titulo": d.titulo,
        "fuente_atribucion": d.fuente_atribucion,
    }


def responder_pregunta_sfc(db: Session, pregunta: str) -> dict:
    """Punto de entrada del agente RAG para el corpus SFC. Espejo de
    responder_pregunta, pero sobre documentos_sfc en vez de norma."""
    fragmentos = buscar_fragmentos_relevantes_sfc(db, pregunta)

    if not fragmentos:
        return {"respuesta": MENSAJE_SIN_NORMATIVIDAD_SFC, "fuentes": []}

    contexto = _formatear_contexto_sfc(fragmentos)

    user_message = (
        "Fragmentos de doctrina/jurisprudencia SFC recuperados (usa solo esto "
        "como fuente de verdad):\n\n"
        f"{contexto}\n\n"
        f"Pregunta del usuario: {pregunta}\n\n"
        "Responde citando tipo de documento, número y fecha de cada fragmento "
        "usado, distinguiendo doctrina de jurisprudencia según la regla del "
        "system prompt. En 'fragmentos_citados' incluye los números (1-based) "
        "que respaldan tu respuesta. Si ningún fragmento es suficiente, deja "
        f'\'fragmentos_citados\' vacío y responde exactamente: '
        f'"{MENSAJE_SIN_NORMATIVIDAD_SFC}"'
    )

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL_ID,
        max_tokens=4096,
        system=SYSTEM_PROMPT_SFC,
        messages=[{"role": "user", "content": user_message}],
        output_format=_RespuestaAgenteSFC,
    )
    resultado = response.parsed_output

    fuentes = [
        _fuente_dict_sfc(fragmentos[i - 1])
        for i in resultado.fragmentos_citados
        if 1 <= i <= len(fragmentos)
    ]

    return {"respuesta": resultado.respuesta, "fuentes": fuentes}
