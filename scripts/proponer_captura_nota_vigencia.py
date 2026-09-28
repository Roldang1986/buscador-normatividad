"""Propuesta de captura de nota_vigencia, de solo lectura (dry-run: NO
escribe nada en la BD).

Contexto: la auditoría de alcance (scripts/auditar_alcance_notas_no_capturadas.py)
encontró que miles de filas tienen en su `texto` una nota real de la
fuente ("compilado en el", "NO compilado en el", "tachado NULO",
"sustituido", "condicionalmente exequible") que VIGENCIA_RE nunca
captura hacia nota_vigencia. Antes de decidir el mapeo de
estado_vigencia (que requiere criterio jurídico, no solo técnico), la
prioridad es que ese texto real quede en nota_vigencia para que la
regla 5 del SYSTEM_PROMPT pueda advertir al usuario con la cita
textual — eso no depende de acertar la categorización.

Este script:
1. Para cada una de las 5 categorías, busca en TODA la tabla `norma`
   (no solo 1.4/1.5) y calcula, sin escribir nada:
   - cuántas filas tienen la nota en el texto
   - cuántas de esas YA tienen nota_vigencia poblada (necesitarían
     combinarse, no sobrescribirse) vs cuántas la tienen vacía
     (asignación directa)
2. Imprime 5-10 ejemplos reales POR CATEGORÍA con el artículo COMPLETO
   (no solo los primeros 250 caracteres) para revisión manual antes de
   decidir el mapeo a estado_vigencia.

No modifica la BD. No toca VIGENCIA_RE. Es el mismo patrón de solo
lectura que el resto de scripts de diagnóstico de esta sesión.

Uso:
    python scripts/proponer_captura_nota_vigencia.py
"""

import re

from app.database import SessionLocal
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
# por defecto) — ver el bug real que esto evita en
# auditar_alcance_notas_no_capturadas.py. Toda la clasificación fina
# ocurre en Python. Claves por SUBSTRING literal único (no por
# categoría): "compilado en el" cubre tanto "compilado" como
# "no_compilado" en una sola query — usar la representación str() del
# filtro como clave de caché sería incorrecto, porque dos .ilike()
# distintos compilan al mismo SQL parametrizado ("texto ILIKE :param")
# y colisionarían aunque el valor real del parámetro sea distinto.
FILTROS_SQL_UNICOS = {
    "compilado en el": Norma.texto.ilike("%compilado en el%"),
    "nulo": Norma.texto.ilike("%nulo%"),
    "sustituid": Norma.texto.ilike("%sustituid%"),
    "condicionalmente": Norma.texto.ilike("%condicionalmente%"),
}

N_EJEMPLOS = 8
LIMITE_CHARS_EJEMPLO = 6000  # cap de seguridad para artículos diluidos, no el caso normal


def _limpiar_nota(bracket_con_signos: str) -> str:
    nota = bracket_con_signos.strip("<> ")
    return re.sub(r"\s+", " ", nota).strip()


def _notas_por_categoria(texto: str) -> dict[str, list[str]]:
    """Para un texto de artículo, devuelve {categoria: [notas encontradas]},
    una sola categoría por bracket (la primera que matchea, en el orden
    de CATEGORIAS)."""
    encontradas: dict[str, list[str]] = {}
    for m in BRACKET_RE.finditer(texto):
        contenido = m.group(0)
        for nombre, patron in CATEGORIAS:
            if patron.search(contenido):
                encontradas.setdefault(nombre, []).append(_limpiar_nota(contenido))
                break
    return encontradas


def main() -> None:
    db = SessionLocal()

    print("=== Propuesta de captura de nota_vigencia (DRY RUN, no escribe nada) ===\n")

    todas_las_candidatas: dict[int, Norma] = {}
    for filtro in FILTROS_SQL_UNICOS.values():
        for f in db.query(Norma).filter(filtro).all():
            todas_las_candidatas[f.id] = f

    print(f"Filas candidatas (unión de todos los filtros SQL): {len(todas_las_candidatas)}\n")

    filas_por_categoria: dict[str, list[tuple[Norma, list[str]]]] = {c: [] for c, _ in CATEGORIAS}
    filas_afectadas: dict[int, dict[str, list[str]]] = {}

    for norma in todas_las_candidatas.values():
        notas = _notas_por_categoria(norma.texto)
        if not notas:
            continue
        filas_afectadas[norma.id] = notas
        for categoria, lista_notas in notas.items():
            filas_por_categoria[categoria].append((norma, lista_notas))

    print("=== Parte 1: alcance por categoría ===\n")
    for categoria, _ in CATEGORIAS:
        filas = filas_por_categoria[categoria]
        print(f"--- {ETIQUETAS[categoria]} ---")
        print(f"  filas con esta nota: {len(filas)}")
        print()

    print("=== Parte 2: ¿la propuesta sería asignación directa o combinación? ===\n")
    total_afectadas = len(filas_afectadas)
    con_nota_previa = sum(1 for nid in filas_afectadas if todas_las_candidatas[nid].nota_vigencia)
    sin_nota_previa = total_afectadas - con_nota_previa
    print(f"Total de filas afectadas (unión de las 5 categorías): {total_afectadas}")
    print(f"  ya tienen nota_vigencia poblada (habría que combinar, no sobrescribir): {con_nota_previa}")
    print(f"  tienen nota_vigencia vacía (asignación directa del texto capturado): {sin_nota_previa}")

    print("\n=== Parte 3: ejemplos reales por categoría (artículo COMPLETO) ===")
    for categoria, _ in CATEGORIAS:
        ejemplos = filas_por_categoria[categoria][:N_EJEMPLOS]
        print(f"\n{'=' * 70}\n{ETIQUETAS[categoria].upper()} — {len(ejemplos)} de {len(filas_por_categoria[categoria])} ejemplo(s)\n{'=' * 70}")
        for norma, notas in ejemplos:
            print(f"\n  id={norma.id}")
            print(f"  fuente: {norma.fuente}")
            print(f"  url_fuente: {norma.url_fuente}")
            print(f"  estado_vigencia actual: {norma.estado_vigencia!r}")
            print(f"  nota_vigencia actual: {norma.nota_vigencia!r}")
            print(f"  nota(s) que se propone capturar: {notas}")
            texto_completo = norma.texto
            if len(texto_completo) > LIMITE_CHARS_EJEMPLO:
                print(
                    f"  texto completo ({len(texto_completo)} chars, "
                    f"truncado a {LIMITE_CHARS_EJEMPLO} — artículo probablemente diluido):"
                )
                print(f"    {texto_completo[:LIMITE_CHARS_EJEMPLO]!r}")
            else:
                print(f"  texto completo ({len(texto_completo)} chars):")
                print(f"    {texto_completo!r}")

    db.close()


if __name__ == "__main__":
    main()
