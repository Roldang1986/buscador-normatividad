"""Diagnóstico de solo lectura (no borra ni inserta nada): identifica,
para un documento ya ingerido, los casos EXACTOS donde
_resolver_numeros_duplicados() detecta que la ocurrencia 1 de un
numero_articulo es una cita cruzada espuria (no empieza con un título
real en mayúsculas) y una ocurrencia posterior sí es el header real —
es decir, los casos donde el contenido YA ALMACENADO en la BD bajo ese
numero_articulo es el equivocado y debe reemplazarse.

No incluye los ~85 casos de duplicados genuinos ya resueltos con sufijo
sintético (esos no cambian de dueño, solo se les agrega contenido nuevo
con un numero_articulo distinto) — solo los casos de INTERCAMBIO real,
que son los únicos donde hace falta borrar una fila existente antes de
insertar la correcta.

Uso:
    python scripts/diagnosticar_colisiones_headers.py <url_documento>
"""

import json
import re
import sys

from app.database import SessionLocal
from app.ingest.dian_scraper import (
    Norma,
    _extraer_articulos,
    _resolver_numeros_duplicados,
    _texto_plano,
    descargar_html,
)

PATRON_ADVERTENCIA_INTERCAMBIO = re.compile(
    r"^numero_articulo '([^']+)': la ocurrencia 1 no parece un encabezado real"
)


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1]
    url_base = url.split("#")[0]

    html = descargar_html(url_base)
    texto = _texto_plano(html)
    fragmentos = _extraer_articulos(texto)
    resultado, advertencias = _resolver_numeros_duplicados(fragmentos)

    numeros_intercambiados = [
        m.group(1)
        for adv in advertencias
        if (m := PATRON_ADVERTENCIA_INTERCAMBIO.match(adv))
    ]

    contenido_nuevo_por_numero = {n: t for n, t in resultado if n in numeros_intercambiados}

    db = SessionLocal()
    try:
        casos = []
        for numero in numeros_intercambiados:
            url_fuente = f"{url_base}#{numero}"
            fila_actual = (
                db.query(Norma)
                .filter(Norma.url_fuente == url_fuente)
                .first()
            )
            texto_nuevo = contenido_nuevo_por_numero.get(numero, "")
            casos.append(
                {
                    "numero_articulo": numero,
                    "url_fuente": url_fuente,
                    "fila_actual_existe_en_bd": fila_actual is not None,
                    "id_fila_actual": fila_actual.id if fila_actual else None,
                    "estado_vigencia_actual": fila_actual.estado_vigencia if fila_actual else None,
                    "contenido_actual_a_borrar_primeros_300_chars": (
                        (fila_actual.texto or "")[:300] if fila_actual else None
                    ),
                    "contenido_nuevo_que_lo_reemplazaria_primeros_300_chars": texto_nuevo[:300],
                    "longitud_contenido_nuevo": len(texto_nuevo),
                }
            )
    finally:
        db.close()

    print("\n=== Diagnóstico de colisiones de header (solo lectura, nada borrado ni insertado) ===")
    print(
        json.dumps(
            {
                "url_documento": url_base,
                "total_casos_de_intercambio_real": len(casos),
                "casos": casos,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
