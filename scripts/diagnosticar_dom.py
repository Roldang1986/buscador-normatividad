"""Diagnóstico de solo lectura sobre los dumps HTML que ya guarda
descubrir_urls_seccion() (01_antes_del_clic.html / 02_despues_del_clic.html).

No abre Playwright ni la red: lee del disco los HTML que el paso anterior
del workflow ya dejó en --capturas-dir y los parsea con BeautifulSoup para
imprimir en el log (texto plano, sin necesidad de descargar el artifact
binario) evidencia real sobre:

1. Si el enlace a estatuto_tributario.htm ya existe en el HTML ANTES del
   clic en "Ver Más" (lo que explicaría por qué el diff antes/después
   nunca lo detecta como "nuevo": no lo es).
2. La cadena de ancestros del encabezado de la sección, con el conteo de
   enlaces a documentos (a[href*=".htm"]) dentro de cada nivel, antes y
   después del clic — para encontrar en qué nivel (si alguno) el conteo
   sube de forma acotada a la sección, en vez de a toda la página.

Uso:
    python scripts/diagnosticar_dom.py scraper-debug "1.1. Estatuto Tributario"
"""

import re
import sys

from bs4 import BeautifulSoup

MAX_NIVELES = 10


def _reporte_enlace_estatuto(nombre_html: str, soup: BeautifulSoup) -> None:
    enlaces = [
        a
        for a in soup.find_all("a", href=True)
        if "estatuto_tributario" in a["href"].lower()
    ]
    print(f"\n--- {nombre_html}: enlaces con 'estatuto_tributario' en href ---")
    if not enlaces:
        print("  (ninguno encontrado en este HTML)")
        return
    for a in enlaces:
        clases_ancestros = []
        nodo = a
        for _ in range(5):
            nodo = nodo.parent
            if nodo is None or getattr(nodo, "name", None) is None:
                break
            clases_ancestros.append(
                f"<{nodo.name} id={nodo.get('id')!r} class={nodo.get('class')!r}>"
            )
        print(f"  href={a['href']!r} texto={a.get_text(strip=True)!r}")
        print(f"    ancestros: {' < '.join(clases_ancestros)}")


def _reporte_ancestros_encabezado(
    nombre_html: str, soup: BeautifulSoup, seccion_titulo: str
) -> None:
    patron = re.compile(re.escape(seccion_titulo), re.IGNORECASE)
    nodo_texto = soup.find(string=patron)
    print(f"\n--- {nombre_html}: ancestros del encabezado {seccion_titulo!r} ---")
    if nodo_texto is None:
        print("  (texto del encabezado no encontrado en este HTML)")
        return

    nodo = nodo_texto.parent
    for nivel in range(1, MAX_NIVELES + 1):
        if nodo is None or getattr(nodo, "name", None) is None:
            print(f"  nivel {nivel}: (sin más ancestros)")
            break
        enlaces_doc = nodo.find_all("a", href=re.compile(r"\.htm"))
        tiene_estatuto = any(
            "estatuto_tributario" in a["href"].lower() for a in enlaces_doc
        )
        print(
            f"  nivel {nivel}: <{nodo.name} id={nodo.get('id')!r} "
            f"class={nodo.get('class')!r}> "
            f"enlaces_htm={len(enlaces_doc)} contiene_estatuto={tiene_estatuto}"
        )
        nodo = nodo.parent


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    directorio, seccion_titulo = sys.argv[1], sys.argv[2]

    for nombre in ("01_antes_del_clic.html", "02_despues_del_clic.html"):
        ruta = f"{directorio}/{nombre}"
        try:
            with open(ruta, encoding="utf-8") as f:
                html = f.read()
        except FileNotFoundError:
            print(f"\n(no existe {ruta}, se omite)")
            continue
        soup = BeautifulSoup(html, "html.parser")
        total_enlaces_htm = len(soup.find_all("a", href=re.compile(r"\.htm")))
        print(f"\n=== {nombre}: total a[href*=.htm] en TODO el documento: {total_enlaces_htm} ===")
        _reporte_enlace_estatuto(nombre, soup)
        _reporte_ancestros_encabezado(nombre, soup, seccion_titulo)


if __name__ == "__main__":
    main()
