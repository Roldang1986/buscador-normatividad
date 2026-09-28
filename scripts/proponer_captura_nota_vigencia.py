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
3. Muestra una muestra de N filas con el nota_vigencia ANTES/DESPUÉS
   que resultaría de aplicar la captura (misma lógica exacta que
   scripts/aplicar_captura_nota_vigencia.py, vía
   app/ingest/notas_vigencia_adicionales.py) — para aprobar el formato
   antes de escribir nada.

No modifica la BD. No toca VIGENCIA_RE. Es el mismo patrón de solo
lectura que el resto de scripts de diagnóstico de esta sesión.

Uso:
    python scripts/proponer_captura_nota_vigencia.py [--muestra N]
"""

import argparse
from collections import Counter

from app.database import SessionLocal
from app.ingest.notas_vigencia_adicionales import (
    CATEGORIAS,
    ETIQUETAS,
    calcular_nota_final,
    encontrar_filas_afectadas,
    notas_por_categoria,
)

N_EJEMPLOS = 8
N_MUESTRA_ANTES_DESPUES = 15
LIMITE_CHARS_EJEMPLO = 6000  # cap de seguridad para artículos diluidos, no el caso normal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--muestra", type=int, default=N_MUESTRA_ANTES_DESPUES)
    args = parser.parse_args()

    db = SessionLocal()

    print("=== Propuesta de captura de nota_vigencia (DRY RUN, no escribe nada) ===\n")

    filas_afectadas = encontrar_filas_afectadas(db)
    print(f"Filas afectadas (unión de las 5 categorías): {len(filas_afectadas)}\n")

    print("=== Parte 1: alcance por categoría ===\n")
    conteo_por_categoria: Counter[str] = Counter()
    filas_por_categoria: dict[str, list[tuple]] = {c: [] for c, _ in CATEGORIAS}
    for norma_id, (norma, _notas) in filas_afectadas.items():
        clasificadas = notas_por_categoria(norma.texto)
        for categoria, lista_notas in clasificadas.items():
            conteo_por_categoria[categoria] += 1
            filas_por_categoria[categoria].append((norma, lista_notas))

    for categoria, _ in CATEGORIAS:
        print(f"--- {ETIQUETAS[categoria]} ---")
        print(f"  filas con esta nota: {conteo_por_categoria[categoria]}")
        print()

    print("=== Parte 2: ¿la propuesta sería asignación directa o combinación? ===\n")
    con_nota_previa = sum(1 for norma, _ in filas_afectadas.values() if norma.nota_vigencia)
    sin_nota_previa = len(filas_afectadas) - con_nota_previa
    print(f"Total de filas afectadas (unión de las 5 categorías): {len(filas_afectadas)}")
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

    print(f"\n=== Parte 4: muestra antes/después ({args.muestra} filas, SIN escribir) ===\n")
    for norma, notas_nuevas in list(filas_afectadas.values())[: args.muestra]:
        nota_final = calcular_nota_final(norma.nota_vigencia, notas_nuevas)
        print(f"  id={norma.id} — {norma.fuente}")
        print(f"    estado_vigencia (sin cambios): {norma.estado_vigencia!r}")
        print(f"    nota_vigencia ANTES:    {norma.nota_vigencia!r}")
        print(f"    nota_vigencia DESPUÉS:  {nota_final!r}")
        print()

    db.close()


if __name__ == "__main__":
    main()
