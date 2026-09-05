"""Diagnóstico de solo lectura para el caso positivo confirmado por el
usuario: ley_1943_2018.htm (Ley 1943 de 2018, declarada INEXEQUIBLE por
la Corte Constitucional, Sentencia C-481-19, efectos desde el 1 de enero
de 2020) — confirmado visualmente marcada con el ícono rojo de derogado
en el índice, pero descubir_urls_seccion() la evaluó con
indice_marca_derogado=false en un run real (ver
run 33990989831 del workflow, límite 100).

No inserta nada en la BD ni modifica ninguna lógica: solo junta la
evidencia real necesaria para diagnosticar dos cosas por separado, sin
adivinar:

1. El texto real del documento alrededor de "INEXEQUIBLE" — para saber
   el patrón exacto (paréntesis, corchetes angulares u otra cosa) antes
   de tocar VIGENCIA_RE.
2. El markup HTML real alrededor del enlace a ley_1943_2018.htm
   (confirmado derogado) comparado con el de un enlace confirmado
   vigente (ley_2380_2024.htm) en el mismo HTML ya volcado por
   descubrir_urls_seccion() — para ver qué distingue realmente al ícono
   rojo en el DOM, en vez de asumir que el problema está en
   DEROGADO_ICON_RE o en dónde se busca el <img>.

Uso:
    python scripts/diagnosticar_caso_vigencia.py scraper-debug
"""

import sys

from bs4 import BeautifulSoup

from app.ingest.dian_scraper import _texto_plano, descargar_html

URL_CASO_DEROGADO = "https://normograma.dian.gov.co/dian/compilacion/docs/ley_1943_2018.htm"
HREF_CASO_DEROGADO = "ley_1943_2018"
HREF_CASO_VIGENTE = "ley_2380_2024"


def mostrar_contexto_inexequible() -> None:
    print(f"\n=== Descargando {URL_CASO_DEROGADO} para ver el patrón real de vigencia ===")
    html = descargar_html(URL_CASO_DEROGADO)
    texto = _texto_plano(html)
    idx = texto.upper().find("INEXEQUIBLE")
    if idx == -1:
        print("'INEXEQUIBLE' NO aparece en el texto plano extraído del documento.")
        print("Primeros 1000 caracteres del documento (para inspección manual):")
        print(repr(texto[:1000]))
        return
    inicio = max(0, idx - 150)
    fin = min(len(texto), idx + 250)
    print(f"Contexto real alrededor de 'INEXEQUIBLE' (offset {idx} en el texto plano):")
    print(repr(texto[inicio:fin]))


def comparar_markup_iconos(directorio: str) -> None:
    ruta = f"{directorio}/02_despues_del_clic.html"
    try:
        with open(ruta, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print(f"\n(no existe {ruta}, se omite la comparación de markup)")
        return

    soup = BeautifulSoup(html, "html.parser")
    for href_fragmento, etiqueta in (
        (HREF_CASO_DEROGADO, "DEROGADO/INEXEQUIBLE (confirmado por el usuario)"),
        (HREF_CASO_VIGENTE, "VIGENTE (control, sin marca conocida)"),
    ):
        print(f"\n=== Markup real alrededor de {href_fragmento!r} — caso {etiqueta} ===")
        enlaces = [a for a in soup.find_all("a", href=True) if href_fragmento in a["href"]]
        if not enlaces:
            print(f"  (no se encontró ningún enlace con {href_fragmento!r} en el href)")
            continue
        nodo = enlaces[0].parent
        for nivel in range(1, 4):
            if nodo is None or getattr(nodo, "name", None) is None:
                print(f"  nivel {nivel}: (sin más ancestros)")
                break
            print(f"--- ancestro nivel {nivel}: <{nodo.name} class={nodo.get('class')!r}> ---")
            marcado = str(nodo)
            print(marcado[:2000])
            nodo = nodo.parent


def main() -> None:
    directorio = sys.argv[1] if len(sys.argv) > 1 else "scraper-debug"
    mostrar_contexto_inexequible()
    comparar_markup_iconos(directorio)


if __name__ == "__main__":
    main()
