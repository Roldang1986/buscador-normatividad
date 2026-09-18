"""Diagnóstico de SOLO LECTURA (no toca la BD): descarga un documento
real, extrae sus artículos con la misma lógica ya corregida
(_extraer_articulos + _resolver_numeros_duplicados) e imprime el texto
COMPLETO de un numero_articulo puntual, sin truncar — para inspeccionar
a mano un caso puntual (ej. confirmar si una mención de "modificado"
fuera de "<...>" es una nota de vigencia real o solo texto sustantivo
citando que OTRA norma fue modificada).

Uso:
    python scripts/imprimir_articulo_completo.py <url_documento> <numero_articulo>
"""

import sys

from app.ingest.dian_scraper import (
    _extraer_articulos,
    _resolver_numeros_duplicados,
    _texto_plano,
    descargar_html,
)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1].split("#")[0]
    numero = sys.argv[2]

    html = descargar_html(url)
    texto = _texto_plano(html)
    fragmentos, _ = _resolver_numeros_duplicados(_extraer_articulos(texto))

    candidatos = [t for n, t in fragmentos if n == numero]
    if not candidatos:
        print(f"No se encontró numero_articulo={numero!r} en {url}")
        sys.exit(1)

    texto_articulo = candidatos[0]
    print(f"\n=== Texto completo de numero_articulo={numero!r} (longitud {len(texto_articulo)} chars) ===\n")
    print(texto_articulo)


if __name__ == "__main__":
    main()
