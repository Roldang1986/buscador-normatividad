"""MODO DE ESCRITURA: aplica estado_vigencia="condicionado" (valor
nuevo, no existía antes en la BD) a las filas "condicionalmente
exequible" cuyo estado_vigencia actual es "vigente".

Usa exactamente la misma lógica que scripts/verificar_sustituido_y_condicionalmente.py
(vía app/ingest/notas_vigencia_adicionales.filas_condicionalmente_vigente)
— correr ese script primero (dry-run, solo lectura) para revisar el
alcance y la muestra antes/después.

Viabilidad de esquema (verificada antes de escribir): estado_vigencia
es `String(50)` sin CHECK ni enum a nivel de BD (alembic/versions/
0001_create_norma_table.py), y no hay validación cerrada en
app/schemas.py ni en ningún otro punto del código — solo comparaciones
directas contra strings ("vigente"/"modificado"/"derogado"). Un valor
nuevo como "condicionado" (12 caracteres) no rompe nada a nivel de
esquema ni de escritura/lectura.

Alcance (confirmado con evidencia real antes de escribir): de 88 filas
"condicionalmente exequible", solo 62 están hoy en "vigente" — esas son
las únicas que esta escritura toca. Las 25 que ya son "modificado" y la
1 que es "derogado" quedan EXCLUIDAS a propósito:
  - Las "modificado" ya tienen una señal más operativa (indica que hay
    una redacción nueva a buscar) — bajarlas a "condicionado" la
    perdería sin necesidad.
  - La "derogado" (id=5767, Ley 685/2001 art. 35) tiene, en el mismo
    artículo, un literal "CONDICIONALMENTE exequible" y otro "tachado
    INEXEQUIBLE" — es decir, el artículo está genuinamente derogado en
    parte; reclasificarlo como "condicionado" ocultaría esa anulación
    real.

NOTA para quien revise: el SYSTEM_PROMPT del agente (app/agent.py,
regla 5) hoy solo reacciona explícitamente a los valores "modificado" y
"derogado" al advertir al usuario. Este script NO actualiza esa regla —
"condicionado" quedará en la BD y visible en el contexto de cada
fragmento, pero el agente no lo señalará con la misma regla explícita
hasta que se decida actualizar el prompt (fuera del alcance pedido
acá).

No toca nota_vigencia (ya se capturó por separado). No toca VIGENCIA_RE.
No toca ninguna otra categoría (compilado/no compilado/tachado
NULO/sustituido).

Idempotente: si una fila ya está en estado_vigencia="condicionado", no
cuenta como cambio real.

Uso:
    python scripts/aplicar_estado_condicionalmente_a_condicionado.py
"""

from app.database import SessionLocal
from app.ingest.notas_vigencia_adicionales import encontrar_filas_afectadas, filas_condicionalmente_vigente


def main() -> None:
    db = SessionLocal()

    filas_afectadas = encontrar_filas_afectadas(db)
    seguras = filas_condicionalmente_vigente(filas_afectadas)

    print(f"Filas candidatas seguras a 'condicionado' (hoy 'vigente'): {len(seguras)}")

    actualizadas = 0
    sin_cambio_real = 0

    for norma in seguras:
        if norma.estado_vigencia == "condicionado":
            sin_cambio_real += 1
            continue
        norma.estado_vigencia = "condicionado"
        actualizadas += 1

    db.commit()

    print(f"Filas con estado_vigencia actualizado a 'condicionado': {actualizadas}")
    print(f"Filas ya en 'condicionado' (sin cambio real): {sin_cambio_real}")
    print("nota_vigencia no fue tocada por este script.")
    print("Ninguna otra categoría (compilado/no compilado/tachado NULO/sustituido) fue modificada.")
    print("Las filas 'condicionalmente exequible' con estado_vigencia='modificado' o 'derogado' NO fueron tocadas (decisión explícita, ver docstring).")

    db.close()


if __name__ == "__main__":
    main()
