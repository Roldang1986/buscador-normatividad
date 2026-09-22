"""Auditoría de alcance, de solo lectura: ¿cuántas filas de TODA la BD
(no solo la sección 1.4/1.5) tienen en su `texto` ya almacenado una nota
tipo "<Artículo compilado en...>", "<...NO compilado en...>" o
"<Aparte tachado NULO>" que _estado_y_nota_vigencia() nunca reconoce
(VIGENCIA_RE solo busca Modificado/Derogado/Adicionado/Subrogado/
INEXEQUIBLE/inconstitucional)?

No hace falta red: estas notas ya viven tal cual en `texto` (el scraper
guarda el texto plano completo del artículo, brackets incluidos; el
heurístico de vigencia simplemente nunca los interpreta). Todo lo que
sigue es SQL + regex sobre lo ya ingerido.

Tres partes:
  1. Conteo exhaustivo (toda la tabla `norma`) de filas con cada frase
     conocida: "compilado en el" (afirmativo), "no compilado en el"
     (explícitamente negativo), y "tachado" + "nulo" cerca.
  2. De esas filas, cuántas tienen estado_vigencia="vigente" ahora mismo
     (mal etiquetadas si asumimos que estas notas SÍ deberían afectar el
     estado).
  3. Descubrimiento de variantes no anticipadas: sobre un conjunto más
     amplio de filas con brackets `<...>` que no matchean ni VIGENCIA_RE
     ni las frases conocidas, agrupa por palabra clave inicial y muestra
     frecuencias — para no asumir que ya conocemos todo el vocabulario
     real del sitio.

No modifica la BD. No toca VIGENCIA_RE. Solo reporta.

Uso:
    python scripts/auditar_alcance_notas_no_capturadas.py
"""

import re
from collections import Counter, defaultdict

from app.database import SessionLocal
from app.ingest.dian_scraper import VIGENCIA_RE
from app.models import Norma

BRACKET_RE = re.compile(r"<[^<>]{1,400}>")

RE_COMPILADO_AFIRMATIVO = re.compile(
    r"(?<!no\s)(?<!NO\s)compilado\s+en\s+el", re.IGNORECASE
)
RE_NO_COMPILADO = re.compile(r"no\s+compilado\s+en\s+el", re.IGNORECASE)
RE_TACHADO_NULO = re.compile(r"tachad[oa]s?\s+nulo", re.IGNORECASE)

# Palabras clave candidatas para clasificar brackets NO capturados por
# VIGENCIA_RE ni por las tres frases conocidas de arriba — descubiertas
# a mano en la investigación anterior o candidatas razonables dado el
# vocabulario ya visto en el sitio (compilado/tachado/nulo + variantes
# cercanas de "reubicación"/"anotación" normativa). El orden importa:
# "no_compilado" se revisa antes que "compilado" para no clasificar mal.
KEYWORDS_ORDENADAS = [
    ("no_compilado", RE_NO_COMPILADO),
    ("compilado", RE_COMPILADO_AFIRMATIVO),
    ("tachado_nulo", RE_TACHADO_NULO),
    ("suspendido", re.compile(r"suspendid[oa]", re.IGNORECASE)),
    ("reglamentado", re.compile(r"reglamentad[oa]", re.IGNORECASE)),
    ("aclarado", re.compile(r"aclarad[oa]", re.IGNORECASE)),
    ("corregido", re.compile(r"corregid[oa]", re.IGNORECASE)),
    ("sustituido", re.compile(r"sustituid[oa]", re.IGNORECASE)),
    ("consultar", re.compile(r"consultar", re.IGNORECASE)),
    ("ver_decreto", re.compile(r"^ver\b", re.IGNORECASE)),
]

N_EJEMPLOS = 8


def clasificar_bracket(texto_bracket: str) -> str:
    if VIGENCIA_RE.search(f"<{texto_bracket}>"):
        return "ya_capturado_por_vigencia_re"
    for nombre, patron in KEYWORDS_ORDENADAS:
        if patron.search(texto_bracket):
            return nombre
    return "otro_no_clasificado"


def main() -> None:
    db = SessionLocal()

    print("=== Parte 1 y 2: conteo exhaustivo (TODA la tabla norma) ===\n")

    total_filas = db.query(Norma).count()
    print(f"Total de filas en `norma`: {total_filas}\n")

    # PostgreSQL (motor POSIX ARE) no soporta lookbehind, así que la
    # distinción "compilado en el" vs "NO compilado en el" se resuelve
    # en Python (re sí soporta lookbehind de ancho fijo) sobre un único
    # fetch por substring — evita depender de sintaxis no soportada por
    # la BD y clasifica cada fila por lo que realmente contiene, no por
    # una condición SQL aproximada.
    filas_compilado_cualquiera = (
        db.query(Norma).filter(Norma.texto.op("~*")(r"compilado en el")).all()
    )
    filas_tachado_nulo = (
        db.query(Norma).filter(Norma.texto.op("~*")(r"tachad[oa]s? nulo")).all()
    )

    filas_no_compilado = [f for f in filas_compilado_cualquiera if RE_NO_COMPILADO.search(f.texto)]
    filas_compilado_afirmativo = [
        f for f in filas_compilado_cualquiera if RE_COMPILADO_AFIRMATIVO.search(f.texto)
    ]

    consultas_resueltas = {
        "compilado en el (afirmativo, sin 'no' antes)": filas_compilado_afirmativo,
        "NO compilado en el (negativo explícito)": filas_no_compilado,
        "tachado NULO (o variantes de género/plural)": filas_tachado_nulo,
    }

    ejemplos_por_categoria: dict[str, list[Norma]] = {}

    for etiqueta, filas in consultas_resueltas.items():
        vigentes = [f for f in filas if f.estado_vigencia == "vigente"]
        print(f"--- {etiqueta} ---")
        print(f"  filas totales:                 {len(filas)}")
        print(f"  de esas, estado_vigencia=vigente: {len(vigentes)}")
        otros_estados = Counter(f.estado_vigencia for f in filas)
        print(f"  distribución de estado_vigencia: {dict(otros_estados)}")
        ejemplos_por_categoria[etiqueta] = filas[:N_EJEMPLOS]
        print()

    print("\n=== Parte 3: descubrimiento de variantes no anticipadas ===\n")

    # Candidatas amplias: cualquier fila con AL MENOS un bracket <...>,
    # para no limitarnos a las palabras clave que ya se nos ocurrieron.
    candidatas = (
        db.query(Norma)
        .filter(Norma.texto.op("~")(r"<[^<>]{1,400}>"))
        .all()
    )
    print(f"Filas con al menos un bracket <...> en `texto`: {len(candidatas)}\n")

    conteo_categorias: Counter[str] = Counter()
    filas_por_categoria: dict[str, list[tuple[Norma, str]]] = defaultdict(list)

    for norma in candidatas:
        for m in BRACKET_RE.finditer(norma.texto):
            contenido = m.group(0)[1:-1]
            categoria = clasificar_bracket(contenido)
            conteo_categorias[categoria] += 1
            if len(filas_por_categoria[categoria]) < N_EJEMPLOS:
                filas_por_categoria[categoria].append((norma, contenido))

    print("Frecuencia de brackets por categoría (conteo de BRACKETS, no de filas):")
    for categoria, n in conteo_categorias.most_common():
        print(f"  {categoria}: {n}")

    print("\n--- Ejemplos de brackets 'otro_no_clasificado' (para revisión manual) ---")
    for norma, contenido in filas_por_categoria.get("otro_no_clasificado", [])[:N_EJEMPLOS]:
        print(f"  id={norma.id} fuente={norma.fuente!r}")
        print(f"    <{contenido[:200]}>")

    print("\n=== Ejemplos reales por categoría conocida (para decidir el mapeo) ===")
    for etiqueta, filas in ejemplos_por_categoria.items():
        print(f"\n--- {etiqueta} ---")
        for f in filas:
            print(f"  id={f.id} estado_vigencia={f.estado_vigencia!r} fuente={f.fuente!r}")
            print(f"    url_fuente: {f.url_fuente}")
            print(f"    texto[:250]: {f.texto[:250]!r}")

    db.close()


if __name__ == "__main__":
    main()
