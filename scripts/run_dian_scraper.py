"""Punto de entrada del workflow scraper-dian.yml: scrapea un subconjunto
pequeño de normograma.dian.gov.co e inserta los fragmentos en la BD.

Uso:
    python scripts/run_dian_scraper.py "1.1. Estatuto Tributario" --limite 3
"""

import argparse
import json
import logging
import pathlib

from app.database import SessionLocal
from app.ingest.dian_scraper import scrapear_seccion

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "seccion", help="Texto del encabezado de la sección del índice a scrapear"
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=3,
        help="Máximo de documentos a descubrir en la sección (default: 3)",
    )
    parser.add_argument(
        "--seguir-enlaces-cruzados",
        action="store_true",
        help="Además de la sección, sigue los enlaces cruzados dentro de cada documento",
    )
    parser.add_argument(
        "--capturas-dir",
        default=None,
        help=(
            "Directorio donde guardar capturas de pantalla de diagnóstico "
            "(antes/después del clic en 'Ver Más'). Si no se pasa, no se "
            "toman capturas."
        ),
    )
    args = parser.parse_args()

    if args.capturas_dir:
        pathlib.Path(args.capturas_dir).mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        resumen = scrapear_seccion(
            db,
            seccion_titulo=args.seccion,
            limite_documentos=args.limite,
            seguir_enlaces_cruzados=args.seguir_enlaces_cruzados,
            directorio_capturas=args.capturas_dir,
        )
    finally:
        db.close()

    print("\n=== Resumen del scraper ===")
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
