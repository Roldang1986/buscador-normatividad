"""MODO DE ESCRITURA: borra las filas identificadas por
verificar_colisiones_headers() / scripts/diagnosticar_colisiones_headers.py
(casos donde una cita cruzada espuria u otro falso positivo de
ARTICULO_HEADER_RE "robó" un numero_articulo que le correspondía a un
header real) y vuelve a ingerir el documento para reinsertar tanto el
contenido correcto como cualquier otro fragmento que faltara.

Correr scripts/diagnosticar_colisiones_headers.py primero y revisar el
detalle caso por caso — deliberadamente no se puede combinar con el
diagnóstico en la misma invocación.

Uso:
    python scripts/aplicar_correccion_colisiones_headers.py <url_documento>
"""

import json
import sys

from app.database import SessionLocal
from app.ingest.dian_scraper import aplicar_correccion_colisiones_headers


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    db = SessionLocal()
    try:
        resultado = aplicar_correccion_colisiones_headers(db, sys.argv[1])
    finally:
        db.close()

    print("\n=== Corrección de colisiones de header aplicada ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
