"""Diagnóstico de solo lectura (no borra ni inserta nada): identifica,
para un documento ya ingerido, los casos EXACTOS donde
_resolver_numeros_duplicados() detecta que la ocurrencia 1 de un
numero_articulo es una cita cruzada espuria (no empieza con un título
real en mayúsculas) y una ocurrencia posterior sí es el header real —
es decir, los casos donde el contenido YA ALMACENADO en la BD bajo ese
numero_articulo es el equivocado y debe reemplazarse.

No incluye los duplicados genuinos ya resueltos con sufijo sintético
(esos no cambian de dueño, solo se les agrega contenido nuevo con un
numero_articulo distinto) — solo los casos de INTERCAMBIO real, que son
los únicos donde hace falta borrar una fila existente antes de insertar
la correcta. Correr siempre antes de
scripts/aplicar_correccion_colisiones_headers.py, nunca junto con él.

Uso:
    python scripts/diagnosticar_colisiones_headers.py <url_documento>
"""

import json
import sys

from app.database import SessionLocal
from app.ingest.dian_scraper import verificar_colisiones_headers


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    db = SessionLocal()
    try:
        resultado = verificar_colisiones_headers(db, sys.argv[1])
    finally:
        db.close()

    print("\n=== Diagnóstico de colisiones de header (solo lectura, nada borrado ni insertado) ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
