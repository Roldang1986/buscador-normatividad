"""Verificación de solo lectura, previa a decidir el mapeo de
estado_vigencia para dos de las cinco categorías descubiertas en la
auditoría de nota_vigencia:

1. "sustituido" (481 filas): ¿el patrón real es reemplazo total de
   texto ("...El nuevo texto es el siguiente:"), igual que "modificado"
   ya trata sus propias notas (que también mezclan artículo completo/
   inciso/numeral bajo un solo estado_vigencia)? Muestra 10 filas
   completas para inspección visual y reporta cuántas de TODAS las 481
   coinciden con ese patrón de cola vs. cuántas no.

2. "condicionalmente exequible": cuenta total de filas (ya sabíamos 88
   por la auditoría anterior, se recalcula aquí para verificar) y
   muestra ejemplos completos.

No modifica la BD. No toca estado_vigencia. No toca VIGENCIA_RE.

Uso:
    python scripts/verificar_sustituido_y_condicionalmente.py
"""

import re

from app.database import SessionLocal
from app.ingest.notas_vigencia_adicionales import encontrar_filas_afectadas

# Mismo patrón de cola que ya usa VIGENCIA_RE para "modificado" — un
# reemplazo total de texto siempre termina en "...siguiente:" antes del
# cierre del bracket.
RE_COLA_NUEVO_TEXTO = re.compile(r"nuevo texto es el siguiente:?\s*$", re.IGNORECASE)

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
    filas_solo_confirmadas = []
    filas_con_alguna_no_confirmada = []
    for norma, notas_sustituido in filas_sustituido:
        todas_confirmadas = True
        for nota in notas_sustituido:
            if RE_COLA_NUEVO_TEXTO.search(nota):
                con_cola_nuevo_texto += 1
            else:
                sin_cola_nuevo_texto.append((norma, nota))
                todas_confirmadas = False
        if todas_confirmadas:
            filas_solo_confirmadas.append(norma)
        else:
            filas_con_alguna_no_confirmada.append(norma)

    total_notas_sustituido = sum(len(n) for _, n in filas_sustituido)
    print(f"Notas 'sustituido' que terminan en 'el nuevo texto es el siguiente:': {con_cola_nuevo_texto}")
    print(f"Notas 'sustituido' que NO terminan así (revisar manualmente): {len(sin_cola_nuevo_texto)}")
    print(f"Total de notas 'sustituido' (una fila puede tener más de una): {total_notas_sustituido}\n")
    print(f"FILAS donde TODAS sus notas 'sustituido' confirman el patrón (candidatas seguras a 'modificado'): {len(filas_solo_confirmadas)}")
    print(f"FILAS con AL MENOS UNA nota 'sustituido' que NO confirma el patrón (excluir de la reclasificación automática): {len(filas_con_alguna_no_confirmada)}\n")

    if sin_cola_nuevo_texto:
        ids_no_confirmadas = sorted({n.id for n, _ in sin_cola_nuevo_texto})
        print(f"--- TODAS las notas 'sustituido' SIN la cola esperada ({len(sin_cola_nuevo_texto)} notas, {len(ids_no_confirmadas)} filas distintas: {ids_no_confirmadas}) ---")
        for norma, nota in sin_cola_nuevo_texto:
            print(f"  id={norma.id} fuente={norma.fuente!r}")
            print(f"    nota completa: {nota!r}")
        print()

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

    db.close()


if __name__ == "__main__":
    main()
