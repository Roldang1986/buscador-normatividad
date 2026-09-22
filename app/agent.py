import anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.embeddings import embed_query
from app.models import Norma

MODEL_ID = "claude-sonnet-5"
TOP_K = 10

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
7. Cuando cites más de un fragmento, si entre ellos existe una relación
   jurídica relevante (uno modifica a otro, uno es la regla general y otro
   la excepción específica, uno fue derogado y reemplazado por otro, hay
   conflicto aparente de vigencia entre normas de distinta fecha),
   descríbela explícitamente en la respuesta usando terminología jurídica
   precisa (norma general/especial, modificación, derogación
   tácita/expresa, posterioridad).

   Límite estricto: describe la relación, nunca concluyas qué debe hacer
   el usuario ni des una recomendación de acción. No uses frases como
   "por lo tanto usted debería", "se recomienda", "lo procedente es". Si
   la pregunta pide explícitamente una recomendación de acción, aclara
   que puedes describir el marco normativo aplicable pero no sustituir el
   criterio profesional de quien consulta.
"""

# Línea fija de aviso del modo discusión — deliberadamente NO se le pide
# al modelo que la genere (ver discutir_pregunta): una constante Python
# reproduce el texto exacto siempre, sin depender de que el modelo la
# transcriba igual en cada respuesta.
AVISO_DISCUSION = (
    "Esto es una línea de análisis para que la evalúes con tu criterio "
    "profesional, no una conclusión definitiva ni asesoría legal."
)

# Modo DISCUSIÓN: a diferencia de SYSTEM_PROMPT (citación estricta, sin
# razonar), acá el modelo SÍ puede razonar sobre implicaciones, tensiones
# entre normas, líneas de argumentación o riesgos — pero solo sobre lo
# que efectivamente recuperó, nunca inventando. La separación entre cita
# literal y razonamiento no depende de un prefijo dentro de texto libre
# (frágil: el modelo podría omitirlo en una respuesta larga) — se exige
# como dos listas separadas de la respuesta estructurada
# (_RespuestaDiscusion), reforzada además con el prefijo "Análisis:"/
# "Consideración:" dentro de cada elemento de análisis como segunda capa
# de seguridad para quien consuma el texto fuera del campo estructurado.
SYSTEM_PROMPT_DISCUSION = """Eres un asistente experto en normatividad tributaria colombiana,
en modo DISCUSIÓN. Partes ÚNICAMENTE de los fragmentos de normatividad que se te entregan como
contexto en cada mensaje (recuperados por búsqueda semántica de una base de datos de normas).
A diferencia del modo de consulta estricta, en este modo SÍ puedes razonar sobre implicaciones,
tensiones entre normas, posibles líneas de argumentación o riesgos a considerar. La diferencia
con el modo consulta es que PUEDES opinar sobre lo que sí recuperaste — nunca que puedes inventar
normas, artículos, cifras o fuentes que no estén en los fragmentos entregados.

Reglas estrictas:
1. Nunca inventes normas, artículos, cifras ni fuentes que no estén en los fragmentos entregados.
   Toda cita textual debe corresponder exactamente al texto de un fragmento.
2. Separa SIEMPRE el contenido en dos listas de la respuesta estructurada, nunca mezcladas:
   - 'citas_textuales': texto literal extraído de los fragmentos (con tipo de norma, número de
     artículo y fuente), sin razonamiento ni opinión — igual de estricto que el modo consulta.
   - 'analisis_discusion': tu razonamiento sobre implicaciones, tensiones entre normas, líneas de
     argumentación o riesgos. Cada elemento de esta lista debe empezar con el prefijo "Análisis:"
     o "Consideración:" para dejar explícito que es tu interpretación, no una cita literal.
   Si necesitas razonar sobre una cita, pon la cita como elemento de 'citas_textuales' y el
   razonamiento correspondiente como un elemento aparte en 'analisis_discusion' — nunca los
   combines en el mismo elemento.
3. Si los fragmentos entregados no contienen información suficiente o relevante para la
   pregunta, deja ambas listas vacías y la lista de fragmentos citados vacía.
4. Para cada fragmento citado, ten en cuenta su estado_vigencia: si está "modificado" o
   "derogado", inclúyelo como parte del análisis de tensión/vigencia — no lo omitas.
5. Nunca concluyas qué debe hacer el usuario ni des una recomendación de acción. No uses frases
   como "por lo tanto usted debería", "se recomienda", "lo procedente es". Si la pregunta pide
   explícitamente una recomendación de acción, tu análisis debe aclarar que describes el marco
   normativo aplicable, no que sustituyes el criterio profesional de quien consulta.
"""


class _RespuestaAgente(BaseModel):
    respuesta: str
    fragmentos_citados: list[int]


class _RespuestaDiscusion(BaseModel):
    citas_textuales: list[str]
    analisis_discusion: list[str]
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


def _llamar_agente(system_prompt: str, user_message: str, output_format: type[BaseModel]) -> BaseModel:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL_ID,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        output_format=output_format,
    )
    return response.parsed_output


def responder_pregunta(db: Session, pregunta: str) -> dict:
    """Punto de entrada del modo CONSULTA (citación estricta, sin razonar):
    busca fragmentos y llama a Claude."""
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

    resultado = _llamar_agente(SYSTEM_PROMPT, user_message, _RespuestaAgente)

    fuentes = [
        _fuente_dict(fragmentos[i - 1])
        for i in resultado.fragmentos_citados
        if 1 <= i <= len(fragmentos)
    ]

    return {"respuesta": resultado.respuesta, "fuentes": fuentes}


def discutir_pregunta(db: Session, pregunta: str) -> dict:
    """Punto de entrada del modo DISCUSIÓN: mismos fragmentos que el modo
    consulta (buscar_fragmentos_relevantes), pero el modelo puede razonar
    sobre ellos — separado en 'citas_textuales' (texto literal) y
    'analisis_discusion' (razonamiento, siempre marcado con "Análisis:"/
    "Consideración:") para que el frontend los pueda mostrar con estilos
    visuales diferenciados sin depender de parsear texto libre.

    'aviso' es la línea fija AVISO_DISCUSION, no generada por el modelo
    (ver su comentario) — siempre presente, incluso sin fragmentos."""
    fragmentos = buscar_fragmentos_relevantes(db, pregunta)

    if not fragmentos:
        return {
            "aviso": AVISO_DISCUSION,
            "citas_textuales": [],
            "analisis_discusion": [MENSAJE_SIN_NORMATIVIDAD],
            "fuentes": [],
        }

    contexto = _formatear_contexto(fragmentos)

    user_message = (
        "Fragmentos de normatividad recuperados (usa solo esto como fuente de verdad):\n\n"
        f"{contexto}\n\n"
        f"Pregunta del usuario: {pregunta}\n\n"
        "Separa tu respuesta en 'citas_textuales' (texto literal de los fragmentos, con "
        "tipo de norma, número de artículo y fuente) y 'analisis_discusion' (tu "
        "razonamiento, cada elemento prefijado con \"Análisis:\" o \"Consideración:\"). "
        "En 'fragmentos_citados' incluye los números de los fragmentos (1-based) que "
        "respaldan tus citas o tu análisis. Si ningún fragmento es suficiente o relevante, "
        "deja las tres listas vacías."
    )

    resultado = _llamar_agente(SYSTEM_PROMPT_DISCUSION, user_message, _RespuestaDiscusion)

    fuentes = [
        _fuente_dict(fragmentos[i - 1])
        for i in resultado.fragmentos_citados
        if 1 <= i <= len(fragmentos)
    ]

    return {
        "aviso": AVISO_DISCUSION,
        "citas_textuales": resultado.citas_textuales,
        "analisis_discusion": resultado.analisis_discusion,
        "fuentes": fuentes,
    }
