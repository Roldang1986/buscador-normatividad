"""Diagnóstico de SOLO LECTURA (no modifica la BD): para un documento ya
ingerido (por url_base), mide sobre lo YA ALMACENADO en la BD:
- si algún fragmento (numero_articulo/numeral) supera el umbral de
  dilución por longitud (mismo criterio que el art. 879/477 del ET), y
- una muestra representativa de numero_articulo reales, para confirmar a
  simple vista qué formato de numeración quedó extraído (jerárquico con
  puntos vs. simple).

No descarga nada de la fuente — todo se mide sobre el texto ya
almacenado en `norma`.

Uso:
    python scripts/diagnosticar_documento_ingerido.py <url_documento> [--umbral 26627] [--top 10] [--muestra 10]
"""

import argparse
import json

from app.database import SessionLocal
from app.models import Norma


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="URL base del documento ya ingerido")
    parser.add_argument("--umbral", type=int, default=26627)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--muestra", type=int, default=10)
    args = parser.parse_args()

    url_base = args.url.split("#")[0]

    db = SessionLocal()
    try:
        filas = db.query(Norma).filter(Norma.url_fuente.like(f"{url_base}%")).order_by(Norma.id).all()
    finally:
        db.close()

    con_longitud = [(len(f.texto or ""), f) for f in filas]
    con_longitud_desc = sorted(con_longitud, key=lambda t: t[0], reverse=True)
    sobre_umbral = [t for t in con_longitud_desc if t[0] >= args.umbral]

    resultado = {
        "url_documento": url_base,
        "total_fragmentos_en_bd": len(filas),
        "umbral_caracteres": args.umbral,
        "fragmentos_en_o_sobre_umbral": len(sobre_umbral),
        "top_por_longitud": [
            {
                "numero_articulo": f.numero_articulo,
                "numeral": f.numeral,
                "longitud_texto": longitud,
                "estado_vigencia": f.estado_vigencia,
                "supera_umbral": longitud >= args.umbral,
            }
            for longitud, f in con_longitud_desc[: args.top]
        ],
        "muestra_numero_articulo_en_orden_de_extraccion": [
            {
                "numero_articulo": f.numero_articulo,
                "numeral": f.numeral,
                "longitud_texto": len(f.texto or ""),
                "estado_vigencia": f.estado_vigencia,
            }
            for f in filas[: args.muestra]
        ],
    }
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
