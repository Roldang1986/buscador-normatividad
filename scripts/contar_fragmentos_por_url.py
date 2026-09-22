"""Diagnóstico de SOLO LECTURA (no escribe nada en la BD): dado un conjunto
de URLs base de documentos ya (parcial o totalmente) ingeridos, cuenta
cuántas filas de `norma` existen realmente en la BD para cada una
(filtrando por url_fuente que empiece con esa url_base) y el total.

Pensado para confirmar, después de cancelar una corrida del scraper a
mitad de camino, cuántos fragmentos quedaron efectivamente persistidos
(cada fragmento se inserta con su propio db.commit() individual — ver
ingestar_documento en app/ingest/dian_scraper.py — así que una
cancelación a mitad de un documento no revierte los fragmentos de los
documentos ya completados).

Uso:
    python scripts/contar_fragmentos_por_url.py <url1> <url2> ...
"""

import json
import sys

from app.database import SessionLocal
from app.ingest.dian_scraper import Norma


def main() -> None:
    urls = [u.split("#")[0] for u in sys.argv[1:]]
    if not urls:
        print(__doc__)
        sys.exit(1)

    db = SessionLocal()
    try:
        por_url = {}
        for url_base in urls:
            filas = db.query(Norma).filter(Norma.url_fuente.like(f"{url_base}%")).all()
            por_url[url_base] = {
                "total_filas": len(filas),
                "estados_vigencia": sorted({f.estado_vigencia for f in filas}),
            }
        total = sum(v["total_filas"] for v in por_url.values())
    finally:
        db.close()

    resultado = {
        "documentos_consultados": len(urls),
        "total_fragmentos_en_bd": total,
        "por_documento": por_url,
    }
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
