"""Lógica compartida para capturar hacia `nota_vigencia` las notas
reales de la fuente que VIGENCIA_RE (app/ingest/dian_scraper.py) nunca
reconoce: "compilado en el"/"NO compilado en el"/"tachado NULO"/
"sustituido"/"condicionalmente exequible".

Deliberadamente en un módulo separado de dian_scraper.py: no se toca
VIGENCIA_RE ni _estado_y_nota_vigencia — este módulo solo captura texto
hacia nota_vigencia, nunca decide estado_vigencia.

Usado por scripts/proponer_captura_nota_vigencia.py (solo lectura,
preview) y scripts/aplicar_captura_nota_vigencia.py (MODO DE ESCRITURA)
— ambos deben usar EXACTAMENTE la misma clasificación, así que vive acá
una sola vez en vez de duplicarse entre los dos scripts.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import Norma

BRACKET_RE = re.compile(r"<[^<>]{1,400}>")

# Orden importa: "no_compilado" se revisa antes que "compilado" para
# que un bracket "<...NO compilado en el...>" nunca se clasifique como
# "compilado" (el negativo contiene el positivo como substring).
CATEGORIAS: list[tuple[str, re.Pattern]] = [
    ("no_compilado", re.compile(r"no\s+compilado\s+en\s+el", re.IGNORECASE)),
    ("compilado", re.compile(r"compilado\s+en\s+el", re.IGNORECASE)),
    ("tachado_nulo", re.compile(r"tachad[oa]s?\s+nulo", re.IGNORECASE)),
    ("sustituido", re.compile(r"sustituid[oa]", re.IGNORECASE)),
    ("condicionalmente_exequible", re.compile(r"condicionalmente\s+exequible", re.IGNORECASE)),
]

ETIQUETAS = {
    "no_compilado": "NO compilado en el",
    "compilado": "compilado en el",
    "tachado_nulo": "tachado NULO",
    "sustituido": "sustituido",
    "condicionalmente_exequible": "condicionalmente exequible",
}

# Filtros SQL candidatos deliberadamente simples (ILIKE, sin regex
# acotado): PostgreSQL limita las repeticiones {m,n} a RE_DUP_MAX (255
# por defecto) — ver auditar_alcance_notas_no_capturadas.py para el bug
# real que esto evita. Toda la clasificación fina ocurre en Python.
FILTROS_SQL_UNICOS = {
    "compilado en el": Norma.texto.ilike("%compilado en el%"),
    "nulo": Norma.texto.ilike("%nulo%"),
    "sustituid": Norma.texto.ilike("%sustituid%"),
    "condicionalmente": Norma.texto.ilike("%condicionalmente%"),
}

# Separador entre notas distintas dentro de nota_vigencia — legible y
# permite que el agente identifique cada nota como una unidad separada
# al citarlas (regla 5 del SYSTEM_PROMPT).
SEPARADOR = "; "


def _limpiar_nota(bracket_con_signos: str) -> str:
    nota = bracket_con_signos.strip("<> ")
    return re.sub(r"\s+", " ", nota).strip()


def notas_por_categoria(texto: str) -> dict[str, list[str]]:
    """{categoria: [notas encontradas]} — para las estadísticas de
    alcance por categoría (Parte 1 del script de propuesta)."""
    encontradas: dict[str, list[str]] = {}
    for m in BRACKET_RE.finditer(texto):
        contenido = m.group(0)
        for nombre, patron in CATEGORIAS:
            if patron.search(contenido):
                encontradas.setdefault(nombre, []).append(_limpiar_nota(contenido))
                break
    return encontradas


def notas_en_orden(texto: str) -> list[str]:
    """Todas las notas encontradas en el artículo, en el orden real en
    que aparecen en el texto (no agrupadas por categoría) — es el orden
    que se usa para construir el nota_vigencia final, porque leerlas en
    orden de aparición es más útil que agruparlas por tipo."""
    notas: list[str] = []
    for m in BRACKET_RE.finditer(texto):
        contenido = m.group(0)
        for _, patron in CATEGORIAS:
            if patron.search(contenido):
                notas.append(_limpiar_nota(contenido))
                break
    return notas


def encontrar_filas_afectadas(db: Session) -> dict[int, tuple[Norma, list[str]]]:
    """Query única de solo lectura: {id: (norma, [notas en orden])} para
    toda fila de `norma` con al menos una nota de las 5 categorías."""
    candidatas: dict[int, Norma] = {}
    for filtro in FILTROS_SQL_UNICOS.values():
        for f in db.query(Norma).filter(filtro).all():
            candidatas[f.id] = f

    afectadas: dict[int, tuple[Norma, list[str]]] = {}
    for norma in candidatas.values():
        notas = notas_en_orden(norma.texto)
        if notas:
            afectadas[norma.id] = (norma, notas)
    return afectadas


# Mismo patrón de cola que ya usa VIGENCIA_RE para asumir "modificado":
# un reemplazo total de texto termina en "...el nuevo texto es el
# siguiente:" antes del cierre del bracket. Confirmado con evidencia
# real (scripts/verificar_sustituido_y_condicionalmente.py): 437 de 468
# filas "sustituido" cumplen esto en TODAS sus notas; las 31 restantes
# tienen variantes reales y distintas (formularios/anexos/capítulos
# sustituidos sin esa cola, y al menos una — "el texto vigente HASTA
# esta fecha es el siguiente:" — con significado invertido: el cuerpo
# mostrado es el texto YA SUPERADO, no el nuevo) — se excluyen a
# propósito de la reclasificación automática.
RE_COLA_NUEVO_TEXTO = re.compile(r"nuevo texto es el siguiente:?\s*$", re.IGNORECASE)


def filas_sustituido_seguras(filas_afectadas: dict[int, tuple[Norma, list[str]]]) -> list[Norma]:
    """Filas 'sustituido' donde TODAS sus notas de esa categoría
    confirman el patrón de reemplazo total de texto — candidatas
    seguras a estado_vigencia='modificado', igual que ya se trata a las
    notas 'modificado' de VIGENCIA_RE (que también mezclan artículo
    completo/inciso/numeral bajo un solo estado)."""
    seguras = []
    for norma, notas in filas_afectadas.values():
        notas_sustituido = [n for n in notas if re.search(r"sustituid[oa]", n, re.IGNORECASE)]
        if notas_sustituido and all(RE_COLA_NUEVO_TEXTO.search(n) for n in notas_sustituido):
            seguras.append(norma)
    return seguras


def filas_condicionalmente_vigente(filas_afectadas: dict[int, tuple[Norma, list[str]]]) -> list[Norma]:
    """Filas 'condicionalmente exequible' cuyo estado_vigencia actual es
    'vigente' — únicas candidatas seguras a un estado nuevo
    ('condicionado'). Se excluyen a propósito las que ya son
    'modificado' (para no perder esa señal, más operativa, con una
    reclasificación) o 'derogado' (donde 'condicionalmente exequible'
    convive con una nota de inexequibilidad/derogación parcial real —
    ver id=5767 en la verificación: 'Literal CONDICIONALMENTE exequible.
    Aparte tachado INEXEQUIBLE' — bajarlo a 'condicionado' ocultaría que
    una parte SÍ fue anulada)."""
    return [
        norma
        for norma, notas in filas_afectadas.values()
        if norma.estado_vigencia == "vigente"
        and any(re.search(r"condicionalmente\s+exequible", n, re.IGNORECASE) for n in notas)
    ]


def calcular_nota_final(nota_actual: str | None, notas_nuevas: list[str]) -> str:
    """Combina nota_actual (puede ser None/"") con notas_nuevas, sin
    duplicar una nota que ya esté presente textualmente (idempotente
    ante una segunda corrida)."""
    partes: list[str] = [nota_actual] if nota_actual else []
    base = nota_actual or ""
    for nota in notas_nuevas:
        if nota not in base:
            partes.append(nota)
            base += SEPARADOR + nota
    return SEPARADOR.join(partes)
