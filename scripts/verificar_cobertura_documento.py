"""Diagnóstico de solo lectura: para un documento ya ingerido (por url_base),
descarga el texto REAL, extrae sus artículos con la misma lógica de
ingestar_documento (ARTICULO_HEADER_RE + _resolver_numeros_duplicados), y
compara ese conjunto de numero_articulo contra lo que hay efectivamente en
la BD (filtrando por url_fuente que empiece con esa url_base).

No descarga nada más que el HTML del documento (sin Playwright, sin tocar
la BD en escritura). Pensado para responder preguntas puntuales tipo
"¿el artículo N está indexado?" y, si no lo está, cuántos y cuáles otros
artículos reales del documento tampoco lo están.

Uso:
    python scripts/verificar_cobertura_documento.py <url_documento> [--articulo <numero>]
"""

import argparse
import json

from app.database import SessionLocal
from app.ingest.dian_scraper import (
    Norma,
    _extraer_articulos,
    _resolver_numeros_duplicados,
    _texto_plano,
    descargar_html,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="URL del documento (sin fragmento #, o se ignora)")
    parser.add_argument(
        "--articulo",
        default=None,
        help="numero_articulo puntual a verificar (ej. 879)",
    )
    args = parser.parse_args()

    url_base = args.url.split("#")[0]

    html = descargar_html(url_base)
    texto = _texto_plano(html)
    fragmentos = _extraer_articulos(texto)
    fragmentos, advertencias_resolucion = _resolver_numeros_duplicados(fragmentos)

    numeros_reales_en_orden = [n for n, _ in fragmentos if n]

    db = SessionLocal()
    try:
        filas_db = db.query(Norma).filter(Norma.url_fuente.like(f"{url_base}%")).all()
    finally:
        db.close()

    numeros_db = {f.numero_articulo for f in filas_db if f.numero_articulo}
    numeros_reales_unicos = set(numeros_reales_en_orden)

    faltantes_en_orden = [n for n in numeros_reales_en_orden if n not in numeros_db]

    resultado = {
        "url_documento": url_base,
        "total_articulos_reales_en_el_documento": len(numeros_reales_unicos),
        "total_filas_en_bd_para_este_documento": len(filas_db),
        "total_articulos_reales_sin_indexar": len(faltantes_en_orden),
        "advertencias_resolucion_duplicados": advertencias_resolucion,
    }

    if args.articulo:
        fila = next((f for f in filas_db if f.numero_articulo == args.articulo), None)
        if fila:
            resultado["articulo_consultado"] = {
                "numero_articulo": fila.numero_articulo,
                "estado_vigencia": fila.estado_vigencia,
                "nota_vigencia": fila.nota_vigencia,
                "url_fuente": fila.url_fuente,
                "indexado": True,
            }
        else:
            existe_en_el_documento_real = args.articulo in numeros_reales_unicos
            resultado["articulo_consultado"] = {
                "numero_articulo": args.articulo,
                "indexado": False,
                "existe_en_el_texto_real_del_documento": existe_en_el_documento_real,
            }

    resultado["articulos_faltantes"] = faltantes_en_orden

    print("\n=== Cobertura de indexación (solo lectura) ===")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
