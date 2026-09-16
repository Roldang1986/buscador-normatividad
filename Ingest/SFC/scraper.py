"""
Scraper del catálogo jurídico de la Superfinanciera (ABCD / CDS-ISIS).

CÓMO CORRERLO (desde tu Codespaces — este sandbox no tiene salida de red
hacia superfinanciera.gov.co):

    pip install requests beautifulsoup4 --break-system-packages
    python scraper.py --dry-run --paginas 1 --coleccion ac

Lo que YA está resuelto (confirmado contra el sitio real):
  - URL base y parámetro de colección:
      https://www.superfinanciera.gov.co/ABCD/superfinanciera/php/buscar_integrada.php
      ?base=juris&Opcion=libre&coleccion=<codigo>|<etiqueta>|TM_
    codigo: "ac" (Doctrina y conceptos), "af" (Fallos jurisdiccionales),
            "aj" (Jurisprudencia financiera)
  - El HTML llega en ISO-8859-1, no UTF-8 (charset confirmado en la
    respuesta real). Hay que decodificar explícitamente.
  - Estructura de campos por registro (ver parser.py).

Lo que FALTA CONFIRMAR antes de raspar las 749+ páginas (no lo pude
verificar desde aquí porque la navegación de página siguiente es un
`javascript:ProximaPagina(pagina, offset)` que no expone una URL plana
en el HTML extraído — probablemente envía un formulario con campos
ocultos, típico de sistemas ISIS/ABCD):

  1. Abre la página de resultados en un navegador real, abre las
     herramientas de desarrollador -> pestaña Network, haz clic en
     "Próxima" y mira qué request sale (GET o POST, y qué parámetros
     lleva). Reemplaza `avanzar_pagina()` más abajo con esa lógica real.
  2. Confirma el conteo real de "ac" y "aj" por separado (el de "af" ya
     lo confirmamos: 14.466).
  3. Revisa robots.txt / términos de uso del sitio antes de lanzar el
     scraper a escala completa.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import asdict

import requests

from parser import parse_pagina_resultados

BASE_URL = "https://www.superfinanciera.gov.co/ABCD/superfinanciera/php/buscar_integrada.php"

COLECCIONES = {
    "ac": "Doctrina y conceptos",
    "af": "Fallos jurisdiccionales",
    "aj": "Jurisprudencia financiera",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; investigacion-normativa/0.1)"
}


def obtener_pagina(session: requests.Session, coleccion: str) -> str:
    """Trae la página 1 de resultados para una colección y la decodifica
    correctamente (el sitio responde en ISO-8859-1, no UTF-8)."""
    params = {
        "base": "juris",
        "Opcion": "libre",
        "coleccion": f"{coleccion}|{COLECCIONES[coleccion]}|TM_",
    }
    resp = session.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.encoding = "ISO-8859-1"
    return resp.text


def avanzar_pagina(session: requests.Session, coleccion: str, pagina: int):
    """
    TODO: sin confirmar. `ProximaPagina(pagina, offset)` en el sitio real
    probablemente somete un formulario oculto en vez de navegar por URL.
    Antes de usar esta función en serio, inspecciona la request real (ver
    docstring del módulo) y reemplaza este cuerpo.
    """
    raise NotImplementedError(
        "Falta confirmar el mecanismo real de paginación contra el sitio "
        "(ver instrucciones al inicio de este archivo)."
    )


def descargar_archivo(session: requests.Session, url: str) -> bytes:
    """Descarga el 'Archivo de texto' o 'Archivo de audio' asociado a un
    registro. Para audio, por ahora no se transcribe (decisión tomada:
    los fallos sin texto se guardan solo con resumen)."""
    resp = session.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.content


def raspar_coleccion(coleccion: str, max_paginas: int, dry_run: bool) -> list[dict]:
    session = requests.Session()
    html = obtener_pagina(session, coleccion)
    registros = parse_pagina_resultados(html)

    resultado = []
    for r in registros:
        registro_dict = asdict(r)
        if not dry_run and r.tipo_archivo == "texto" and r.url_archivo:
            try:
                contenido = descargar_archivo(session, r.url_archivo)
                registro_dict["texto_completo"] = contenido.decode(
                    "ISO-8859-1", errors="replace"
                )
            except requests.RequestException as e:
                print(f"  ! No se pudo descargar {r.url_archivo}: {e}")
        resultado.append(registro_dict)

    if max_paginas > 1:
        print(
            "Aviso: max_paginas > 1 pedido, pero la paginación real aún no "
            "está implementada (ver avanzar_pagina). Se procesó solo la "
            "página 1."
        )

    return resultado


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coleccion", choices=COLECCIONES.keys(), default="ac")
    ap.add_argument("--paginas", type=int, default=1)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo parsea metadatos, no descarga archivos de texto completo.",
    )
    args = ap.parse_args()

    registros = raspar_coleccion(args.coleccion, args.paginas, args.dry_run)
    print(f"\n{len(registros)} registros procesados de la colección '{args.coleccion}'.")
    for r in registros[:3]:
        print("-" * 60)
        print(r["tipo_documento"], "|", r["numero_documento"], "|", r["titulo"])


if __name__ == "__main__":
    main()
