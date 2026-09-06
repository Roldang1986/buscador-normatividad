"""MODO DE ESCRITURA: borra la fila única actual de cada numero_articulo
indicado (deben estar en ARTICULOS_CON_FRAGMENTACION_NUMERAL_HABILITADA)
y reingiere el documento completo — ingestar_documento() es idempotente
por url_fuente, así que solo reinserta esos artículos (ahora fragmentados
por numeral) y no toca ningún otro ya existente.

Requiere que la columna `numeral` ya exista en la BD (alembic upgrade
head con la migración 0002 aplicada).

Correr scripts/verificar_fragmentacion_numeral.py primero y revisar el
detalle — deliberadamente no se puede combinar con el diagnóstico en la
misma invocación.

Uso:
    python scripts/aplicar_fragmentacion_numeral.py <url_documento> <numero_articulo> [numero_articulo ...]
"""

import json
import sys

from app.database import SessionLocal
from app.ingest.dian_scraper import aplicar_fragmentacion_numeral


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    url_documento = sys.argv[1]
    articulos = sys.argv[2:]

    db = SessionLocal()
    try:
        resultado = aplicar_fragmentacion_numeral(db, url_documento, articulos)
    finally:
        db.close()

    print("\n=== Fragmentación por numeral aplicada ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
