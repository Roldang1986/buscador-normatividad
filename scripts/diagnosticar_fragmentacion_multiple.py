"""Diagnóstico de SOLO REPORTE (no escribe nada, ni siquiera lee la BD):
descarga el documento real UNA vez y aplica _fragmentar_articulo_por_numeral()
a varios numero_articulo a la vez — mismo criterio y misma lógica que
scripts/prototipo_fragmentacion_numeral.py (usado para validar 879 y
477), pero en lote y con un chequeo explícito de colisión de etiquetas
de numeral dentro de cada artículo (mismo problema confirmado en 260-11:
dos listas independientes bajo literales "A."/"B." que reutilizaban la
misma numeración "1.", "2." — eso produciría etiquetas duplicadas si se
fragmentara tal cual).

Si se llama SIN ningún numero_articulo (solo la URL), diagnostica el
DOCUMENTO COMPLETO como un solo "artículo" (numero_articulo=None) —
modo agregado para la extensión de fragmentación por numeral a
documentos sin encabezados "ARTÍCULO N." (ver
DOCUMENTOS_SIN_ARTICULO_CON_FRAGMENTACION_NUMERAL_HABILITADA en
app/ingest/dian_scraper.py, confirmado con la sección "1.8. Orden
administrativa"): _fragmentar_articulo_por_numeral() es agnóstica a si
el texto que recibe es un artículo o el documento entero, así que no
hace falta lógica nueva, solo permitir el caso numero_articulo=None.

No modifica la BD. No aplica nada — solo reporta.

Uso:
    python scripts/diagnosticar_fragmentacion_multiple.py <url_documento> [numero_articulo ...]
    (sin numero_articulo = diagnostica el documento completo)
"""

import json
import sys
from collections import Counter

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
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url_base = sys.argv[1].split("#")[0]
    articulos_objetivo = sys.argv[2:] or [None]

    html = descargar_html(url_base)
    texto = _texto_plano(html)
    fragmentos = _extraer_articulos(texto)
    fragmentos, _ = _resolver_numeros_duplicados(fragmentos)
    texto_por_numero = dict(fragmentos)

    resultado = {
        "url_documento": url_base,
        "umbral_longitud": UMBRAL_LONGITUD_FRAGMENTACION_NUMERAL,
        "umbral_numerales": UMBRAL_NUMERALES_FRAGMENTACION,
        "casos": [],
    }

    for numero in articulos_objetivo:
        texto_articulo = texto_por_numero.get(numero)
        if texto_articulo is None:
            resultado["casos"].append(
                {"numero_articulo": numero, "error": "no encontrado en el documento real"}
            )
            continue

        matches = _detectar_numerales(texto_articulo)
        califica = _debe_fragmentarse_por_numeral(texto_articulo)
        fragmentos_nuevos = _fragmentar_articulo_por_numeral(texto_articulo)

        etiquetas = [e for e, _ in fragmentos_nuevos] if califica else []
        conteo_etiquetas = Counter(etiquetas)
        etiquetas_duplicadas = {e: c for e, c in conteo_etiquetas.items() if c > 1}

        longitudes = [len(t) for _, t in fragmentos_nuevos] if califica else []

        caso = {
            "numero_articulo": numero,
            "longitud_texto_completo": len(texto_articulo),
            "numerales_detectados": len(matches),
            "califica_para_fragmentar": califica,
            "total_fragmentos_resultantes": len(fragmentos_nuevos) if califica else 1,
            "etiquetas_en_orden": etiquetas,
            "colision_de_etiquetas": bool(etiquetas_duplicadas),
            "etiquetas_duplicadas": etiquetas_duplicadas,
            "rango_longitud_fragmentos": (
                {"minimo": min(longitudes), "maximo": max(longitudes)} if longitudes else None
            ),
            "longitud_por_fragmento": (
                [{"etiqueta": e, "longitud": len(t)} for e, t in fragmentos_nuevos] if califica else None
            ),
        }
        resultado["casos"].append(caso)

    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
