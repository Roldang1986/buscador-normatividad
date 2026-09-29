"""MODO DE ESCRITURA: aplica estado_vigencia="modificado" a las filas
"sustituido" cuya nota confirma, en TODAS sus notas de esa categoría, el
patrón de reemplazo total de texto ("...el nuevo texto es el
siguiente:") — el mismo patrón que VIGENCIA_RE ya asume para
"modificado".

Usa exactamente la misma lógica que scripts/verificar_sustituido_y_condicionalmente.py
(vía app/ingest/notas_vigencia_adicionales.filas_sustituido_seguras) —
correr ese script primero (dry-run, solo lectura) para revisar el
alcance y la muestra antes/después.

Alcance (confirmado con evidencia real antes de escribir): de 468 filas
con nota "sustituido", 437 confirman el patrón en TODAS sus notas — esas
son las únicas que esta escritura toca. Las 31 restantes (formularios/
anexos/capítulos sustituidos sin esa cola, y al menos una variante con
significado invertido — "el texto vigente HASTA esta fecha es el
siguiente:", donde el cuerpo mostrado es el texto YA SUPERADO, no el
nuevo) quedan EXCLUIDAS a propósito: mantienen su estado_vigencia
actual, apoyándose en el texto ya capturado en nota_vigencia para que el
agente pueda advertir sobre ellas.

No toca nota_vigencia (ya se capturó por separado). No toca VIGENCIA_RE.
No toca ninguna otra categoría (compilado/no compilado/tachado
NULO/condicionalmente exequible).

Idempotente: si una fila ya está en estado_vigencia="modificado", no
cuenta como cambio real.

Uso:
    python scripts/aplicar_estado_sustituido_a_modificado.py
"""

from app.database import SessionLocal
from app.ingest.notas_vigencia_adicionales import encontrar_filas_afectadas, filas_sustituido_seguras


def main() -> None:
    db = SessionLocal()

    filas_afectadas = encontrar_filas_afectadas(db)
    seguras = filas_sustituido_seguras(filas_afectadas)

    print(f"Filas candidatas seguras a 'modificado' (nota 'sustituido' con patrón confirmado): {len(seguras)}")

    actualizadas = 0
    sin_cambio_real = 0
    distribucion_antes: dict[str, int] = {}

    for norma in seguras:
        distribucion_antes[norma.estado_vigencia] = distribucion_antes.get(norma.estado_vigencia, 0) + 1
        if norma.estado_vigencia == "modificado":
            sin_cambio_real += 1
            continue
        norma.estado_vigencia = "modificado"
        actualizadas += 1

    db.commit()

    print(f"Distribución de estado_vigencia ANTES de escribir: {distribucion_antes}")
    print(f"Filas con estado_vigencia actualizado a 'modificado': {actualizadas}")
    print(f"Filas ya en 'modificado' (sin cambio real): {sin_cambio_real}")
    print("nota_vigencia no fue tocada por este script.")
    print("Ninguna otra categoría (compilado/no compilado/tachado NULO/condicionalmente exequible) fue modificada.")

    db.close()


if __name__ == "__main__":
    main()
