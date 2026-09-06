"""Investigación de SOLO LECTURA (no toca la BD): descarga el documento
real, localiza un numero_articulo puntual, y muestra el detalle crudo de
_detectar_numerales() (cada match con su posición y línea completa) más
el contenido íntegro de uno de los fragmentos resultantes de
_fragmentar_articulo_por_numeral() — para confirmar si una etiqueta de
numeral "desaparecida" quedó absorbida dentro de otro fragmento o
genuinamente no existe en el texto original.

Uso:
    python scripts/investigar_numeral_faltante.py <url_documento> <numero_articulo> <etiqueta_a_mostrar>

Ej.:
    python scripts/investigar_numeral_faltante.py \\
        https://normograma.dian.gov.co/dian/compilacion/docs/estatuto_tributario.htm 260-11 2
"""

import sys

from app.ingest.dian_scraper import (
    _detectar_numerales,
    _extraer_articulos,
    _fragmentar_articulo_por_numeral,
    _resolver_numeros_duplicados,
    _texto_plano,
    descargar_html,
)


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    url_base = sys.argv[1].split("#")[0]
    numero_objetivo = sys.argv[2]
    etiqueta_objetivo = sys.argv[3]

    html = descargar_html(url_base)
    texto = _texto_plano(html)
    fragmentos = _extraer_articulos(texto)
    fragmentos, _ = _resolver_numeros_duplicados(fragmentos)

    candidatos = [t for n, t in fragmentos if n == numero_objetivo]
    if not candidatos:
        print(f"No se encontró numero_articulo={numero_objetivo!r} en {url_base}")
        sys.exit(1)
    texto_articulo = candidatos[0]

    print(f"\n=== Artículo {numero_objetivo!r}: longitud total {len(texto_articulo)} chars ===")

    matches = _detectar_numerales(texto_articulo)
    print(f"\n=== {len(matches)} matches crudos de _detectar_numerales(), en orden ===")
    for i, m in enumerate(matches):
        linea_fin = texto_articulo.find("\n", m.end())
        if linea_fin == -1:
            linea_fin = min(m.end() + 120, len(texto_articulo))
        contexto = texto_articulo[m.start() : min(linea_fin, m.start() + 150)]
        print(f"[{i}] pos={m.start()}-{m.end()} etiqueta={m.group(1)!r} linea={contexto!r}")

    # Búsqueda manual de posibles apariciones literales de la etiqueta
    # objetivo que el regex pudo no haber capturado (para distinguir
    # "no matcheado" de "genuinamente ausente del documento").
    print(f"\n=== Búsqueda literal de posibles apariciones de {etiqueta_objetivo!r} no capturadas por el regex ===")
    import re

    patron_libre = re.compile(
        r"(?m)^.{0,10}\b" + re.escape(etiqueta_objetivo) + r"\b.{0,10}"
    )
    ocurrencias = list(patron_libre.finditer(texto_articulo))
    if not ocurrencias:
        print(f"(ninguna ocurrencia de {etiqueta_objetivo!r} en el texto del artículo, ni siquiera como substring suelto)")
    else:
        for m in ocurrencias:
            print(f"pos={m.start()} -> {m.group(0)!r}")

    resultado = _fragmentar_articulo_por_numeral(texto_articulo)

    print(f"\n=== Etiquetas resultantes de _fragmentar_articulo_por_numeral(): {[e for e, _ in resultado]} ===")

    encontrado = False
    for etiqueta, texto_fragmento in resultado:
        if etiqueta == etiqueta_objetivo:
            encontrado = True
            print(f"\n=== CONTENIDO COMPLETO del fragmento numeral {etiqueta!r} (longitud {len(texto_fragmento)} chars) ===")
            print(texto_fragmento)
    if not encontrado:
        print(f"\n(No hay ningún fragmento con etiqueta {etiqueta_objetivo!r} tras fragmentar)")


if __name__ == "__main__":
    main()
