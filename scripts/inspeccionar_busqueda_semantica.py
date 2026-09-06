"""Diagnóstico de solo lectura: llama directamente a
buscar_fragmentos_relevantes() (sin pasar por responder_pregunta/el
agente, sin llamada a Anthropic) para ver EXACTAMENTE qué candidatos trae
la búsqueda semántica top_k, más allá de lo que el modelo termine citando.

Además, si se pasa --numero-articulo y ese número no aparece entre los
candidatos, imprime el texto completo almacenado de esa norma puntual
(para inspeccionar si el embedding pudo diluirse por longitud del
fragmento, o si el contenido relevante no usa las palabras literales de
la pregunta).

Uso:
    python scripts/inspeccionar_busqueda_semantica.py "pregunta" [--top-k 5] [--numero-articulo 879]
"""

import argparse
import json

from app.agent import TOP_K, buscar_fragmentos_relevantes
from app.database import SessionLocal
from app.embeddings import embed_query
from app.models import Norma


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pregunta")
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--numero-articulo", default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        fragmentos = buscar_fragmentos_relevantes(db, args.pregunta, top_k=args.top_k)

        # Solo para mostrar la distancia coseno de cada candidato (no
        # cambia el resultado de buscar_fragmentos_relevantes, que ya
        # hizo el ORDER BY real en la BD) — mismo vector de la pregunta.
        vector = embed_query(args.pregunta)
        ids_en_orden = [f.id for f in fragmentos]
        distancias = dict(
            db.query(Norma.id, Norma.embedding.cosine_distance(vector))
            .filter(Norma.id.in_(ids_en_orden))
            .all()
        )

        print(f"\n=== buscar_fragmentos_relevantes(top_k={args.top_k}) para: {args.pregunta!r} ===")
        candidatos = []
        for i, f in enumerate(fragmentos, start=1):
            candidatos.append(
                {
                    "posicion": i,
                    "id": f.id,
                    "numero_articulo": f.numero_articulo,
                    "fuente": f.fuente,
                    "estado_vigencia": f.estado_vigencia,
                    "url_fuente": f.url_fuente,
                    "distancia_coseno": round(float(distancias.get(f.id, -1)), 6),
                    "longitud_texto": len(f.texto or ""),
                    "texto_primeros_300_chars": (f.texto or "")[:300],
                }
            )
        print(json.dumps(candidatos, indent=2, ensure_ascii=False))

        if args.numero_articulo:
            numeros_en_candidatos = [f.numero_articulo for f in fragmentos]
            si_esta = args.numero_articulo in numeros_en_candidatos
            print(
                f"\n=== ¿numero_articulo={args.numero_articulo!r} está entre los "
                f"{args.top_k} candidatos? ==="
            )
            print(si_esta)

            if not si_esta:
                fila = (
                    db.query(Norma)
                    .filter(Norma.numero_articulo == args.numero_articulo)
                    .filter(Norma.tipo_norma == "articulo_et")
                    .first()
                )
                if fila:
                    distancia_real = db.query(
                        Norma.embedding.cosine_distance(vector)
                    ).filter(Norma.id == fila.id).scalar()
                    print(f"\n=== Texto completo almacenado de numero_articulo={args.numero_articulo!r} (id={fila.id}) ===")
                    print(
                        json.dumps(
                            {
                                "id": fila.id,
                                "numero_articulo": fila.numero_articulo,
                                "fuente": fila.fuente,
                                "estado_vigencia": fila.estado_vigencia,
                                "nota_vigencia": fila.nota_vigencia,
                                "url_fuente": fila.url_fuente,
                                "longitud_texto": len(fila.texto or ""),
                                "distancia_coseno_a_la_pregunta": round(float(distancia_real), 6),
                                "tiene_embedding": fila.embedding is not None,
                            },
                            indent=2,
                            ensure_ascii=False,
                        )
                    )
                    print("\n--- texto completo ---")
                    print(fila.texto)
                else:
                    print(f"No se encontró ninguna fila con numero_articulo={args.numero_articulo!r} y tipo_norma='articulo_et'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
