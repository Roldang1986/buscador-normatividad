"""Diagnóstico de SOLO LECTURA: para los numero_articulo indicados
(deben estar en ARTICULOS_CON_FRAGMENTACION_NUMERAL_HABILITADA), compara
la fila única actual en BD contra los fragmentos por numeral que
produciría reingerir con la fragmentación habilitada. No modifica nada.

Correr esto ANTES de scripts/aplicar_fragmentacion_numeral.py y revisar
el detalle caso por caso.

Uso:
    python scripts/verificar_fragmentacion_numeral.py <url_documento> <numero_articulo> [numero_articulo ...]
"""

import json
import sys

from app.database import SessionLocal
from app.ingest.dian_scraper import verificar_fragmentacion_numeral


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    url_documento = sys.argv[1]
    articulos = sys.argv[2:]

    db = SessionLocal()
    try:
        resultado = verificar_fragmentacion_numeral(db, url_documento, articulos)
    finally:
        db.close()

    print("\n=== Diagnóstico de fragmentación por numeral (solo lectura) ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
