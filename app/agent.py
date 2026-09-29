import re

import anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.embeddings import embed_query
from app.models import DocumentoSFC, Norma, NormaCBF

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
# Corpus SFC (Circular Básica Financiera + doctrina y jurisprudencia de la
# Superintendencia Financiera).
# Función separada a propósito, no una generalización de responder_pregunta:
# el corpus tributario de arriba queda intocado mientras este sigue en
# construcción. Espejo de Ingest/SFC/query_pilot.py, pero como parte del
# agente real (usado por POST /consulta-sfc) en vez de un script de prueba.
# ---------------------------------------------------------------------------

TOP_K_SFC = 5
TOP_K_CBF = 5
# Con 10 fragmentos (5 CBF + 5 conceptos) las respuestas que separan norma y
# doctrina superan 4.096 tokens; el JSON quedaba cortado y parse() fallaba.
MAX_TOKENS_SFC = 12000

MENSAJE_SIN_NORMATIVIDAD_SFC = (
    "No encontré normatividad, doctrina o jurisprudencia de la Superfinanciera "
    "indexada sobre esto."
)

# Limitación del régimen de transición de la CBF: va como regla explícita en
# el prompt (no solo en Ingest/CBF/README.md) porque el modelo no lee el
# README en tiempo de respuesta.
LIMITACION_TRANSICION_CBF = (
    "Este corpus no captura circulares puntuales de 2023-2024 que puedan "
    "mantener vigencia residual bajo la cláusula de salvaguarda de la Circular "
    "Externa 006 de 2025 (régimen de transición). Si la pregunta del usuario "
    "depende de vigencia normativa reciente o de un régimen de transición "
    "específico, menciona esta limitación explícitamente antes de responder "
    "con lo que sí está indexado."
)

# Advertencia permanente de la CBJ: más fuerte que la de la CBF porque no es
# condicional. Verificado en vivo (2026-09-29): la fuente de la CBJ puede traer
# ya incorporado texto de circulares que aún no rigen, sin nota ni marca
# alguna (ej. CE 008 de 2026, subnumerales 2.2.5/2.4/2.5, que rigen el
# 30-oct-2026). Por eso va en TODA respuesta que cite la CBJ, no solo cuando
# un fragmento traiga nota de vigencia. Además de la regla del prompt,
# `_asegurar_advertencia_cbj` la antepone en código si el modelo la omite.
ADVERTENCIA_VIGENCIA_CBJ = (
    "El texto de la Circular Básica Jurídica puede incluir modificaciones "
    "recientes que aún no han entrado en vigencia, sin ninguna marca que lo "
    "indique en la fuente. Para decisiones donde la fecha exacta de vigencia "
    "sea crítica, verifica directamente contra las circulares externas más "
    "recientes de la SFC."
)

SYSTEM_PROMPT_SFC = f"""Eres un asistente experto en regulación, doctrina y
jurisprudencia de la Superintendencia Financiera de Colombia (SFC). Respondes
ÚNICAMENTE con base en los fragmentos entregados como contexto en cada mensaje
(recuperados por búsqueda semántica de dos fuentes: la Circular Básica
Financiera y el catálogo de conceptos, fallos y jurisprudencia de la SFC).
Nunca respondas con conocimiento general ni con lo que recuerdes de tu
entrenamiento.

Cada fragmento trae un campo "origen". Distingue SIEMPRE su valor normativo:
- origen "normas_cbf" (Circular Básica Financiera): es NORMA VIGENTE, de
  obligatorio cumplimiento para las entidades vigiladas. Preséntala como
  "según la Circular Básica Financiera, Parte X, Capítulo Y, numeral Z...".
- origen "documentos_sfc" con tipo_documento "concepto" (doctrina): es la
  interpretación/opinión de la Superintendencia sobre una norma, dirigida a
  quien consulta. NO es vinculante ni de obligatorio cumplimiento para
  terceros, no sienta precedente judicial, y la propia entidad puede
  reconsiderarla en un concepto posterior. Preséntalo como "según el concepto
  de la SFC No. X..." o "en criterio de la Superintendencia...", nunca como si
  fuera una norma o una decisión obligatoria.
- origen "documentos_sfc" con tipo_documento "fallo" / "jurisprudencia": es la
  decisión de una autoridad sobre un caso concreto. SÍ es vinculante para las
  partes de ese caso y puede tener valor de precedente. Preséntalo como "en el
  fallo/la decisión No. X..." y aclara que aplica al caso decidido — no lo
  generalices automáticamente a cualquier situación distinta.

Si citas fragmentos de distinto tipo en la misma respuesta, sepáralos
explícitamente (norma vigente / doctrina no vinculante / decisión de un caso
concreto). No les des el mismo peso.

Orden cuando un concepto interpreta una norma también citada: si la pregunta
es sobre el CONTENIDO O ALCANCE DE UNA NORMA, cita la norma primero y el
concepto después, como interpretación. Si la pregunta es sobre QUÉ HA
INTERPRETADO O RESUELTO LA SUPERFINANCIERA en un caso concreto, el concepto
encabeza la respuesta y la norma aparece como su fundamento. El criterio es el
tipo de pregunta, no una regla fija de qué va primero.

(Hoy la base solo tiene doctrina —tipo_documento="concepto"— indexada en
documentos_sfc; fallos y jurisprudencia se cargarán más adelante, pero esta
distinción rige desde ya.)

Reglas estrictas:
1. Solo puedes afirmar algo si está respaldado textualmente por uno o más de
   los fragmentos entregados. No completes vacíos de información con memoria
   propia ni suposiciones.
2. Cada afirmación cita su fuente tal como aparece en el fragmento: para
   normas_cbf, parte, capítulo y numeral; para documentos_sfc, tipo de
   documento, número y fecha. No inventes ni parafrasees números ni fechas.
3. Si los fragmentos entregados no contienen información suficiente o
   relevante, no intentes responder de todos modos: responde exactamente
   "{MENSAJE_SIN_NORMATIVIDAD_SFC}" y deja la lista de fragmentos citados vacía.
4. Para cada fragmento de normas_cbf citado, revisa su estado_vigencia. Si es
   "vigencia_futura" o "vigencia_condicionada", adviértelo explícitamente e
   incluye su nota_vigencia — nunca lo presentes como aplicable hoy.
5. Para cifras, porcentajes, plazos y condiciones específicas de la norma,
   transcribe el texto exacto del fragmento entre comillas.
6. {LIMITACION_TRANSICION_CBF}
7. Si un concepto de documentos_sfc cita explícitamente una circular o norma
   anterior a la Circular Básica Financiera vigente (por ejemplo la Circular
   Externa 100 de 1995, la Circular Externa 24 de 1997, la Circular Externa
   44 de 1997, o cualquier otra norma que el propio texto del fragmento
   muestre como reemplazada), adviértelo explícitamente: la norma citada por
   el concepto ya no rige y el criterio del concepto podría estar
   desactualizado. Basa esta advertencia solo en lo que dice el texto de los
   fragmentos entregados; no afirmes la derogatoria de una norma específica
   con conocimiento propio más allá de eso.
8. Al final de la respuesta, incluye la línea de fuente_atribucion de los
   fragmentos citados de documentos_sfc, tal como aparece en el fragmento.
9. Si citas CUALQUIER fragmento de origen "normas_cbj" (Circular Básica
   Jurídica), empieza la respuesta con esta advertencia, textual y sin
   condiciones: "{ADVERTENCIA_VIGENCIA_CBJ}" Inclúyela siempre, aunque el
   fragmento no traiga nota_vigencia ni un estado_vigencia distinto de
   "vigente": en la CBJ puede haber cambios aún no vigentes sin ninguna nota.
   (La CBJ todavía no está indexada; esta regla rige desde que lo esté.)
"""


class _RespuestaAgenteSFC(BaseModel):
    respuesta: str
    fragmentos_citados: list[int]


def buscar_fragmentos_relevantes_sfc(
    db: Session, vector: list[float], top_k: int = TOP_K_SFC
) -> list[DocumentoSFC]:
    """Búsqueda semántica top-k en `documentos_sfc` por similitud coseno.
    Nunca toca `norma` (corpus tributario)."""
    return (
        db.query(DocumentoSFC)
        .filter(DocumentoSFC.embedding.is_not(None))
        .order_by(DocumentoSFC.embedding.cosine_distance(vector))
        .limit(top_k)
        .all()
    )


def buscar_fragmentos_relevantes_cbf(
    db: Session, vector: list[float], top_k: int = TOP_K_CBF
) -> list[NormaCBF]:
    """Búsqueda semántica top-k en `normas_cbf`. Solo trae filas 'articulo':
    'anexo_zip' y 'reservado' no tienen embedding (ni texto que citar)."""
    return (
        db.query(NormaCBF)
        .filter(NormaCBF.tipo_registro == "articulo", NormaCBF.embedding.is_not(None))
        .order_by(NormaCBF.embedding.cosine_distance(vector))
        .limit(top_k)
        .all()
    )


def _formatear_fragmento_sfc(i: int, f: DocumentoSFC | NormaCBF) -> str:
    if isinstance(f, NormaCBF):
        return (
            f"[Fragmento {i}]\n"
            f"origen: normas_cbf\n"
            f"fuente: {f.fuente}\n"
            f"numeral: {f.numeral or 'N/A'}\n"
            f"estado_vigencia: {f.estado_vigencia}\n"
            f"nota_vigencia: {f.nota_vigencia or 'N/A'}\n"
            f"texto: {(f.texto or '')[:8000]}"
        )
    texto = (f.texto_completo or f.resumen or "")[:8000]
    return (
        f"[Fragmento {i}]\n"
        f"origen: documentos_sfc\n"
        f"tipo_documento: {f.tipo_documento}\n"
        f"numero_documento: {f.numero_documento or 'N/A'}\n"
        f"fecha: {f.fecha_texto or 'N/A'}\n"
        f"titulo: {f.titulo or 'N/A'}\n"
        f"fuente_atribucion: {f.fuente_atribucion}\n"
        f"texto: {texto}"
    )


def _formatear_contexto_sfc(fragmentos: list[DocumentoSFC | NormaCBF]) -> str:
    return "\n\n".join(
        _formatear_fragmento_sfc(i, f) for i, f in enumerate(fragmentos, start=1)
    )


def _fuente_dict_sfc(f: DocumentoSFC | NormaCBF) -> dict:
    # "origen" le dice al frontend qué tarjeta dibujar y a qué endpoint pedir
    # el texto completo (/documento-sfc/{id} vs /norma-cbf/{id}) — los ids
    # de las dos tablas se pisan entre sí.
    if isinstance(f, NormaCBF):
        return {
            "origen": "normas_cbf",
            "id": f.id,
            "fuente": f.fuente,
            "numeral": f.numeral,
            "estado_vigencia": f.estado_vigencia,
            "url_archivo": f.url_archivo,
        }
    return {
        "origen": "documentos_sfc",
        "id": f.id,
        "tipo_documento": f.tipo_documento,
        "numero_documento": f.numero_documento,
        "fecha_texto": f.fecha_texto,
        "titulo": f.titulo,
        "fuente_atribucion": f.fuente_atribucion,
    }


def _etiqueta_citable(f: DocumentoSFC | NormaCBF) -> str | None:
    """Cómo aparece el fragmento citado en el texto de la respuesta: el
    numeral para la CBF ("2.9.3"), el número de documento para SFC
    ("2018060742-001", sin los espacios del catálogo). None si no hay una
    etiqueta con forma de número que se pueda buscar sin falsos positivos
    (p. ej. "Concepto interno", o un número suelto como "3685")."""
    if isinstance(f, NormaCBF):
        etiqueta = f.numeral
        if etiqueta and re.fullmatch(r"\d+(\.\d+){2,}(-bis)?", etiqueta):
            return etiqueta
        return None
    etiqueta = re.sub(r"\s*-\s*", "-", f.numero_documento or "").strip()
    return etiqueta if re.fullmatch(r"\d+-\d+", etiqueta) else None


def _completar_fragmentos_citados(
    respuesta: str, fragmentos: list[DocumentoSFC | NormaCBF], citados: list[int]
) -> list[int]:
    """El modelo a veces menciona un fragmento en el texto sin incluirlo en
    `fragmentos_citados` (2 de 5 corridas de la misma pregunta, 2026-09-28):
    el texto cita "numeral 2.9.3" y la tarjeta no aparece en fuentes. Acá se
    agrega, en el orden en que aparece en el texto, todo fragmento del
    contexto cuya etiqueta (_etiqueta_citable) esté en la respuesta y falte
    en la lista.

    Si una misma etiqueta corresponde a más de un fragmento del contexto (p.
    ej. el mismo numeral en la versión vigente y la futura de P2.C9), no se
    agrega ninguno: no hay forma de saber a cuál se refiere el texto, y es
    preferible omitir la tarjeta a mostrar la versión equivocada. Tampoco se
    quita nada de lo que el modelo sí listó."""
    texto = re.sub(r"\s*-\s*", "-", respuesta)
    etiquetas = [_etiqueta_citable(f) for f in fragmentos]

    def posicion(i: int) -> int | None:
        etiqueta = etiquetas[i - 1]
        if etiqueta is None or etiquetas.count(etiqueta) > 1:
            return None
        # (?<![\d.]) / (?!\.?\d|-bis): que "2.9.1" no matchee dentro de
        # "2.9.14", "12.9.1", "2.9.1.2" ni "2.9.1-bis"; el punto final de
        # "2.9.1." sí se admite.
        m = re.search(rf"(?<![\d.]){re.escape(etiqueta)}(?!\.?\d|-bis)", texto)
        return m.start() if m else None

    resultado: list[int] = []
    for i in citados:
        if 1 <= i <= len(fragmentos) and i not in resultado:
            resultado.append(i)

    faltantes = sorted(
        (pos, i)
        for i in range(1, len(fragmentos) + 1)
        if i not in resultado and (pos := posicion(i)) is not None
    )
    for pos, i in faltantes:
        # Se inserta antes del primer citado que aparece más adelante en el
        # texto, para respetar el orden de aparición que usa el frontend.
        destino = next(
            (k for k, j in enumerate(resultado) if (pj := posicion(j)) is not None and pj > pos),
            len(resultado),
        )
        resultado.insert(destino, i)
    return resultado


def _asegurar_advertencia_cbj(respuesta: str, fuentes: list[dict]) -> str:
    """Antepone ADVERTENCIA_VIGENCIA_CBJ si alguna fuente citada es de la CBJ
    y el modelo no la incluyó textualmente (regla 9 del prompt). Garantía en
    código: la advertencia no puede depender de que el modelo la recuerde."""
    cita_cbj = any(f.get("origen") == "normas_cbj" for f in fuentes)
    if not cita_cbj or ADVERTENCIA_VIGENCIA_CBJ in respuesta:
        return respuesta
    return f"{ADVERTENCIA_VIGENCIA_CBJ}\n\n{respuesta}"


def responder_pregunta_sfc(db: Session, pregunta: str) -> dict:
    """Punto de entrada del agente RAG para el corpus SFC: busca por separado
    en normas_cbf (norma vigente) y documentos_sfc (doctrina) con el mismo
    embedding de la pregunta, y le entrega ambos al modelo marcados por
    origen. Nunca toca `norma` (corpus tributario)."""
    vector = embed_query(pregunta)
    fragmentos: list[DocumentoSFC | NormaCBF] = [
        *buscar_fragmentos_relevantes_cbf(db, vector),
        *buscar_fragmentos_relevantes_sfc(db, vector),
    ]

    if not fragmentos:
        return {"respuesta": MENSAJE_SIN_NORMATIVIDAD_SFC, "fuentes": []}

    contexto = _formatear_contexto_sfc(fragmentos)

    user_message = (
        "Fragmentos de normatividad (Circular Básica Financiera) y de "
        "doctrina/jurisprudencia SFC recuperados (usa solo esto como fuente "
        "de verdad):\n\n"
        f"{contexto}\n\n"
        f"Pregunta del usuario: {pregunta}\n\n"
        "Responde citando la fuente de cada fragmento usado, distinguiendo "
        "norma vigente, doctrina y jurisprudencia según las reglas del system "
        "prompt. En 'fragmentos_citados' incluye los números (1-based) que "
        "respaldan tu respuesta, en el mismo orden en que los citas en el texto "
        "(no en orden numérico): el frontend muestra las fuentes en ese orden. "
        "Todo fragmento que menciones en el texto por su numeral o número de "
        "documento —aunque sea de pasada, dentro de una lista o entre "
        "paréntesis— debe estar en 'fragmentos_citados'; si no lo usas, no lo "
        "menciones. "
        "Si ningún fragmento es suficiente, deja "
        f"'fragmentos_citados' vacío y responde exactamente: "
        f'"{MENSAJE_SIN_NORMATIVIDAD_SFC}"'
    )

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL_ID,
        max_tokens=MAX_TOKENS_SFC,
        system=SYSTEM_PROMPT_SFC,
        messages=[{"role": "user", "content": user_message}],
        output_format=_RespuestaAgenteSFC,
    )
    resultado = response.parsed_output

    citados = _completar_fragmentos_citados(
        resultado.respuesta, fragmentos, resultado.fragmentos_citados
    )
    fuentes = [_fuente_dict_sfc(fragmentos[i - 1]) for i in citados]
    respuesta = _asegurar_advertencia_cbj(resultado.respuesta, fuentes)

    return {"respuesta": respuesta, "fuentes": fuentes}
