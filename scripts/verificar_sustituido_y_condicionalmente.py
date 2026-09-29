"""Verificación de solo lectura, previa a decidir el mapeo de
estado_vigencia para dos de las cinco categorías descubiertas en la
auditoría de nota_vigencia:

1. "sustituido" (481 notas / 468 filas): ¿el patrón real es reemplazo
   total de texto ("...El nuevo texto es el siguiente:"), igual que
   "modificado" ya trata sus propias notas? Reporta cuántas de esas
   filas confirman el patrón en TODAS sus notas (candidatas seguras a
   "modificado") vs. cuántas tienen al menos una nota que no calza (se
   excluyen), y lista esas excepciones completas para revisión.

2. "condicionalmente exequible" (88 filas): cuenta el total, la
   distribución de estado_vigencia actual, y aísla las candidatas
   seguras a un estado nuevo ("condicionado") — solo las que hoy son
   'vigente' (las 'modificado'/'derogado' se excluyen a propósito, ver
   razón en app/ingest/notas_vigencia_adicionales.py).

3. Muestra el dry-run (antes/después) de ambos cambios propuestos, SIN
   escribir nada — usa exactamente las mismas funciones que usarán los
   scripts de escritura real (aplicar_estado_sustituido_a_modificado.py
   y aplicar_estado_condicionalmente_a_condicionado.py), para que no
   haya drift entre lo que se aprueba acá y lo que se aplica.

No modifica la BD. No toca estado_vigencia. No toca VIGENCIA_RE.

Uso:
    python scripts/verificar_sustituido_y_condicionalmente.py
"""

import re

from app.database import SessionLocal
from app.ingest.notas_vigencia_adicionales import (
    RE_COLA_NUEVO_TEXTO,
    encontrar_filas_afectadas,
    filas_condicionalmente_vigente,
    filas_sustituido_seguras,
)

N_EJEMPLOS = 10
LIMITE_CHARS = 4000


def main() -> None:
    db = SessionLocal()
    filas_afectadas = encontrar_filas_afectadas(db)

    print("=== 1. SUSTITUIDO: ¿reemplazo total de texto, como 'modificado'? ===\n")

    filas_sustituido = []
    for norma, notas in filas_afectadas.values():
        notas_sustituido = [n for n in notas if re.search(r"sustituid[oa]", n, re.IGNORECASE)]
        if notas_sustituido:
            filas_sustituido.append((norma, notas_sustituido))

    print(f"Total de filas con nota 'sustituido': {len(filas_sustituido)}\n")

    con_cola_nuevo_texto = 0
    sin_cola_nuevo_texto = []
    for _norma, notas_sustituido in filas_sustituido:
        for nota in notas_sustituido:
            if RE_COLA_NUEVO_TEXTO.search(nota):
                con_cola_nuevo_texto += 1
            else:
                sin_cola_nuevo_texto.append((_norma, nota))

    seguras = filas_sustituido_seguras(filas_afectadas)
    ids_seguras = {n.id for n in seguras}
    filas_excluidas = [n for n, _ in filas_sustituido if n.id not in ids_seguras]

    total_notas_sustituido = sum(len(n) for _, n in filas_sustituido)
    print(f"Notas 'sustituido' que terminan en 'el nuevo texto es el siguiente:': {con_cola_nuevo_texto}")
    print(f"Notas 'sustituido' que NO terminan así (revisar manualmente): {len(sin_cola_nuevo_texto)}")
    print(f"Total de notas 'sustituido' (una fila puede tener más de una): {total_notas_sustituido}\n")
    print(f"FILAS candidatas seguras a 'modificado' (TODAS sus notas confirman el patrón): {len(seguras)}")
    print(f"FILAS excluidas (al menos una nota no confirma el patrón): {len(filas_excluidas)}\n")

    if sin_cola_nuevo_texto:
        ids_no_confirmadas = sorted({n.id for n, _ in sin_cola_nuevo_texto})
        print(
            f"--- TODAS las notas 'sustituido' SIN la cola esperada "
            f"({len(sin_cola_nuevo_texto)} notas, {len(ids_no_confirmadas)} filas distintas: {ids_no_confirmadas}) ---"
        )
        for norma, nota in sin_cola_nuevo_texto:
            print(f"  id={norma.id} fuente={norma.fuente!r}")
            print(f"    nota completa: {nota!r}")
        print()

    distribucion_seguras: dict[str, int] = {}
    for norma in seguras:
        distribucion_seguras[norma.estado_vigencia] = distribucion_seguras.get(norma.estado_vigencia, 0) + 1
    print(f"Distribución de estado_vigencia ACTUAL entre las filas seguras: {distribucion_seguras}\n")

    print(f"--- {N_EJEMPLOS} ejemplos completos de filas 'sustituido' (artículo completo) ---\n")
    for norma, notas_sustituido in filas_sustituido[:N_EJEMPLOS]:
        print(f"  id={norma.id}")
        print(f"  fuente: {norma.fuente}")
        print(f"  url_fuente: {norma.url_fuente}")
        print(f"  estado_vigencia actual: {norma.estado_vigencia!r}")
        print(f"  nota(s) 'sustituido' encontrada(s): {notas_sustituido}")
        texto = norma.texto
        if len(texto) > LIMITE_CHARS:
            print(f"  texto ({len(texto)} chars, truncado a {LIMITE_CHARS}):")
            print(f"    {texto[:LIMITE_CHARS]!r}")
        else:
            print(f"  texto completo ({len(texto)} chars):")
            print(f"    {texto!r}")
        print()

    print("\n=== 2. CONDICIONALMENTE EXEQUIBLE: conteo y ejemplos ===\n")

    filas_condicionalmente = []
    for norma, notas in filas_afectadas.values():
        notas_cond = [n for n in notas if re.search(r"condicionalmente\s+exequible", n, re.IGNORECASE)]
        if notas_cond:
            filas_condicionalmente.append((norma, notas_cond))

    print(f"Total de filas con nota 'condicionalmente exequible': {len(filas_condicionalmente)}\n")

    distribucion_estado_actual: dict[str, int] = {}
    for norma, _ in filas_condicionalmente:
        distribucion_estado_actual[norma.estado_vigencia] = (
            distribucion_estado_actual.get(norma.estado_vigencia, 0) + 1
        )
    print(f"Distribución de estado_vigencia ACTUAL entre esas filas: {distribucion_estado_actual}\n")

    seguras_cond = filas_condicionalmente_vigente(filas_afectadas)
    print(f"Candidatas seguras a 'condicionado' (hoy 'vigente'): {len(seguras_cond)}")
    print("(las 'modificado'/'derogado' se excluyen a propósito — ver razón en el módulo compartido)\n")

    print(f"--- {N_EJEMPLOS} ejemplos completos de filas 'condicionalmente exequible' ---\n")
    for norma, notas_cond in filas_condicionalmente[:N_EJEMPLOS]:
        print(f"  id={norma.id}")
        print(f"  fuente: {norma.fuente}")
        print(f"  url_fuente: {norma.url_fuente}")
        print(f"  estado_vigencia actual: {norma.estado_vigencia!r}")
        print(f"  nota_vigencia actual (ya con la captura previa aplicada): {norma.nota_vigencia!r}")
        print(f"  nota(s) 'condicionalmente exequible': {notas_cond}")
        texto = norma.texto
        if len(texto) > LIMITE_CHARS:
            print(f"  texto ({len(texto)} chars, truncado a {LIMITE_CHARS}):")
            print(f"    {texto[:LIMITE_CHARS]!r}")
        else:
            print(f"  texto completo ({len(texto)} chars):")
            print(f"    {texto!r}")
        print()

    print("\n=== 3. Propuesta de escritura (DRY RUN, no escribe nada) ===\n")

    print(f"--- SUSTITUIDO -> 'modificado': muestra de {min(N_EJEMPLOS, len(seguras))} de {len(seguras)} filas seguras ---\n")
    for norma in seguras[:N_EJEMPLOS]:
        print(f"  id={norma.id} fuente={norma.fuente!r}")
        print(f"    estado_vigencia ANTES:   {norma.estado_vigencia!r}")
        print("    estado_vigencia DESPUÉS: 'modificado'")

    print(
        f"\n--- CONDICIONALMENTE EXEQUIBLE -> 'condicionado': "
        f"muestra de {min(N_EJEMPLOS, len(seguras_cond))} de {len(seguras_cond)} filas seguras ---\n"
    )
    for norma in seguras_cond[:N_EJEMPLOS]:
        print(f"  id={norma.id} fuente={norma.fuente!r}")
        print(f"    estado_vigencia ANTES:   {norma.estado_vigencia!r}")
        print("    estado_vigencia DESPUÉS: 'condicionado'")

    db.close()


if __name__ == "__main__":
    main()
