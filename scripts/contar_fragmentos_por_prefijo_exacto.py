"""Diagnóstico de SOLO LECTURA (no modifica la BD): cuenta y lista las
filas de `norma` cuyo url_fuente empieza EXACTAMENTE con el prefijo
dado, sin recortar nada en '#' — a diferencia de
contar_fragmentos_por_url.py (pensado para URLs de documento completo),
este script sirve para verificar un artículo puntual ya fragmentado,
donde el prefijo relevante SÍ incluye el '#numero_articulo'
(ej. '.../estatuto_tributario.htm#260-11').

Uso:
    python scripts/contar_fragmentos_por_prefijo_exacto.py <prefijo_url_fuente>
"""

import json
import sys

from app.database import SessionLocal
from app.ingest.dian_scraper import Norma


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    prefijo = sys.argv[1]

    db = SessionLocal()
    try:
        filas = db.query(Norma).filter(Norma.url_fuente.like(f"{prefijo}%")).order_by(Norma.id).all()
    finally:
        db.close()

    resultado = {
        "prefijo": prefijo,
        "total_filas": len(filas),
        "filas": [
            {
                "id": f.id,
                "numero_articulo": f.numero_articulo,
                "numeral": f.numeral,
                "url_fuente": f.url_fuente,
                "longitud_texto": len(f.texto or ""),
                "estado_vigencia": f.estado_vigencia,
            }
            for f in filas
        ],
    }
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
