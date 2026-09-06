"""Prototipo de SOLO REPORTE (no escribe nada, ni siquiera lee la BD):
descarga el documento real, localiza un numero_articulo puntual, y
muestra cómo quedarían sus fragmentos si se aplicara
_fragmentar_articulo_por_numeral() — para validar el criterio de
detección y el regex de numerales contra texto real antes de decidir si
se implementa en volumen.

Uso:
    python scripts/prototipo_fragmentacion_numeral.py <url_documento> <numero_articulo>

Ej.:
    python scripts/prototipo_fragmentacion_numeral.py \\
        https://normograma.dian.gov.co/dian/compilacion/docs/estatuto_tributario.htm 879
"""

import json
import sys

from app.ingest.dian_scraper import (
    UMBRAL_LONGITUD_FRAGMENTACION_NUMERAL,
    UMBRAL_NUMERALES_FRAGMENTACION,
    _debe_fragmentarse_por_numeral,
    _detectar_numerales,
    _extraer_articulos,
    _fragmentar_articulo_por_numeral,
    _resolver_numeros_duplicados,
    _texto_plano,
    descargar_html,
)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    url_base = sys.argv[1].split("#")[0]
    numero_objetivo = sys.argv[2]

    html = descargar_html(url_base)
    texto = _texto_plano(html)
    fragmentos = _extraer_articulos(texto)
    fragmentos, _ = _resolver_numeros_duplicados(fragmentos)

    candidatos = [t for n, t in fragmentos if n == numero_objetivo]
    if not candidatos:
        print(f"No se encontró numero_articulo={numero_objetivo!r} (tras resolver duplicados) en {url_base}")
        sys.exit(1)
    texto_articulo = candidatos[0]

    matches = _detectar_numerales(texto_articulo)
    califica = _debe_fragmentarse_por_numeral(texto_articulo)

    print(f"\n=== Prototipo de fragmentación por numeral: artículo {numero_objetivo!r} ===")
    print(
        json.dumps(
            {
                "url_documento": url_base,
                "numero_articulo": numero_objetivo,
                "longitud_texto_completo": len(texto_articulo),
                "umbral_longitud": UMBRAL_LONGITUD_FRAGMENTACION_NUMERAL,
                "numerales_detectados": len(matches),
                "umbral_numerales": UMBRAL_NUMERALES_FRAGMENTACION,
                "califica_para_fragmentar": califica,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    print(f"\nEtiquetas de numeral detectadas, en orden: {[m.group(1).strip() for m in matches]}")

    resultado = _fragmentar_articulo_por_numeral(texto_articulo)

    if resultado[0][0] is None:
        print("\n(No se fragmentó — no cumple el criterio. resultado = [(None, texto_completo)])")
        return

    print(f"\n=== {len(resultado)} fragmentos resultantes ===")
    for etiqueta, texto_fragmento in resultado:
        print(f"\n--- numeral {etiqueta!r} (longitud {len(texto_fragmento)} chars) ---")
        print(texto_fragmento[:400])
        if len(texto_fragmento) > 400:
            print("... [truncado para este reporte, el fragmento completo es más largo] ...")


if __name__ == "__main__":
    main()
