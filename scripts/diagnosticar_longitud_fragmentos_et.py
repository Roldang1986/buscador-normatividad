"""Diagnóstico de solo lectura: mide la longitud de texto (y por lo tanto
el riesgo de dilución del embedding) de los fragmentos YA ALMACENADOS del
Estatuto Tributario, para evaluar el alcance del problema encontrado en
el artículo 879 (un solo embedding para un fragmento de 26,627
caracteres con ~31 numerales heterogéneos, que diluye cualquier
sub-tema puntual) antes de decidir si vale la pena fragmentar por
numeral.

No modifica nada en la BD. No descarga nada de la fuente — todo se mide
sobre el texto ya almacenado.

Uso:
    python scripts/diagnosticar_longitud_fragmentos_et.py [--umbral 26627] [--top 10] [--numero-articulo 476]
"""

import argparse
import json

from app.database import SessionLocal
from app.models import Norma


def _titulo(texto: str) -> str:
    primera_linea = (texto or "").split("\n", 1)[0].strip()
    return primera_linea[:150]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--umbral",
        type=int,
        default=26627,
        help="Longitud mínima (en caracteres) para contar como 'mismo patrón que el 879' (default: 26627, la longitud exacta del 879)",
    )
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--numero-articulo", default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        filas = db.query(Norma).filter(Norma.tipo_norma == "articulo_et").all()
    finally:
        db.close()

    con_longitud = [(len(f.texto or ""), f) for f in filas]
    con_longitud.sort(key=lambda t: t[0], reverse=True)

    total = len(con_longitud)
    en_o_sobre_umbral = [t for t in con_longitud if t[0] >= args.umbral]

    resultado = {
        "total_articulos_et_en_bd": total,
        "umbral_caracteres": args.umbral,
        "articulos_en_o_sobre_umbral": len(en_o_sobre_umbral),
        "top": [
            {
                "posicion": i + 1,
                "numero_articulo": f.numero_articulo,
                "longitud_texto": longitud,
                "titulo": _titulo(f.texto),
                "estado_vigencia": f.estado_vigencia,
                "url_fuente": f.url_fuente,
            }
            for i, (longitud, f) in enumerate(con_longitud[: args.top])
        ],
    }

    print("\n=== Longitud de fragmentos del ET (riesgo de dilución del embedding) ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))

    if args.numero_articulo:
        fila = next((f for longitud, f in con_longitud if f.numero_articulo == args.numero_articulo), None)
        if fila:
            longitud = len(fila.texto or "")
            posicion = next(
                i + 1 for i, (l, f) in enumerate(con_longitud) if f.numero_articulo == args.numero_articulo
            )
            print(f"\n=== Artículo {args.numero_articulo!r} ===")
            print(
                json.dumps(
                    {
                        "numero_articulo": fila.numero_articulo,
                        "longitud_texto": longitud,
                        "posicion_por_longitud_entre_todos_los_articulos_et": f"{posicion} de {total}",
                        "supera_umbral": longitud >= args.umbral,
                        "titulo": _titulo(fila.texto),
                        "estado_vigencia": fila.estado_vigencia,
                        "url_fuente": fila.url_fuente,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(f"\nNo se encontró numero_articulo={args.numero_articulo!r} con tipo_norma='articulo_et'.")


if __name__ == "__main__":
    main()
