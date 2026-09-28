"""MODO DE ESCRITURA: aplica en la BD real la captura de nota_vigencia
para las notas "compilado en el"/"NO compilado en el"/"tachado NULO"/
"sustituido"/"condicionalmente exequible" que VIGENCIA_RE nunca
reconoce.

Usa exactamente la misma lógica que scripts/proponer_captura_nota_vigencia.py
(vía app/ingest/notas_vigencia_adicionales.py) — correr ese script
primero (dry-run, solo lectura) para revisar el alcance y la muestra
antes/después.

Por fila afectada:
  - Si nota_vigencia está vacía: se asigna directamente el texto de
    la(s) nota(s) encontrada(s), en el orden en que aparecen en el
    artículo.
  - Si nota_vigencia ya tiene contenido (capturado antes por
    VIGENCIA_RE): se combina — el texto existente más la(s) nota(s)
    nueva(s), separadas con "; ". Nunca se sobrescribe.
  - Si una misma fila tiene varias notas nuevas simultáneas (ej. un
    artículo "sustituido" que además tiene un "Aparte tachado NULO"),
    se concatenan TODAS, no solo la primera que matchea.
  - Idempotente: si se corre dos veces, no duplica una nota que ya
    esté presente textualmente en nota_vigencia.

NO toca estado_vigencia — queda en su valor actual sin cambios, incluso
si es impreciso, hasta la decisión de mapeo posterior. NO toca
VIGENCIA_RE.

Uso:
    python scripts/aplicar_captura_nota_vigencia.py
"""

from app.database import SessionLocal
from app.ingest.notas_vigencia_adicionales import calcular_nota_final, encontrar_filas_afectadas


def main() -> None:
    db = SessionLocal()

    filas_afectadas = encontrar_filas_afectadas(db)
    print(f"Filas afectadas a actualizar: {len(filas_afectadas)}")

    actualizadas = 0
    sin_cambio_real = 0

    for norma, notas_nuevas in filas_afectadas.values():
        nota_final = calcular_nota_final(norma.nota_vigencia, notas_nuevas)
        if nota_final == (norma.nota_vigencia or ""):
            # Ya tenía exactamente estas notas (corrida repetida) — no
            # hace falta escribir ni contar como cambio.
            sin_cambio_real += 1
            continue
        norma.nota_vigencia = nota_final
        actualizadas += 1

    db.commit()

    print(f"Filas con nota_vigencia actualizada: {actualizadas}")
    print(f"Filas ya al día (sin cambio, corrida repetida): {sin_cambio_real}")
    print("estado_vigencia no fue modificado en ninguna fila.")

    db.close()


if __name__ == "__main__":
    main()
