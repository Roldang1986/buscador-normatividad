"""MODO DE ESCRITURA: ingiere UN documento puntual completo (no una
sección) llamando directamente a ingestar_documento() — pensado para
casos como OA. 4 de 1989 (sección "1.8. Orden administrativa"), donde
solo ESE documento de la sección ya está habilitado en una allowlist de
fragmentación (ej. DOCUMENTOS_CON_FRAGMENTACION_POR_SECCION_ALTO_NIVEL_HABILITADA)
y los otros documentos de la misma sección NO deben insertarse todavía
porque su fragmentación no tiene diseño aprobado. Correr scrapear_seccion()
para la sección completa insertaría también esos otros documentos sin
fragmentar (dilución no aprobada) — este script evita eso, tocando solo
la URL puntual indicada.

ingestar_documento() es idempotente por url_fuente: si el documento (o
alguno de sus fragmentos) ya existe, no lo reinserta ni lo modifica.

Uso:
    python scripts/ingerir_documento_puntual.py <url_documento> [indice_marca_derogado]

`indice_marca_derogado` es opcional: "true" o "false" (cualquier otro
valor u omitirlo se trata como None — sin señal del índice).
"""

import json
import sys

from app.database import SessionLocal
from app.ingest.dian_scraper import ingestar_documento


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1]
    indice_marca_derogado = None
    if len(sys.argv) >= 3:
        if sys.argv[2].lower() == "true":
            indice_marca_derogado = True
        elif sys.argv[2].lower() == "false":
            indice_marca_derogado = False

    db = SessionLocal()
    try:
        insertados, advertencias = ingestar_documento(db, url, indice_marca_derogado=indice_marca_derogado)
    finally:
        db.close()

    print("\n=== Documento puntual ingerido ===")
    print(
        json.dumps(
            {
                "url": url,
                "indice_marca_derogado": indice_marca_derogado,
                "fragmentos_insertados": insertados,
                "advertencias": advertencias,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
