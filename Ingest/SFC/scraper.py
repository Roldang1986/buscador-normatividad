"""
Scraper del catálogo jurídico de la Superfinanciera (ABCD / CDS-ISIS).

CÓMO CORRERLO:

    pip install requests beautifulsoup4 pypdf --break-system-packages
    sudo apt-get install -y antiword   # requerido para texto completo de .doc legado
    python scraper.py --dry-run --paginas 1 --coleccion ac

VALIDADO contra el sitio real el 2026-09-16 (parser.py y paginación):

  - URL base y parámetro de colección:
      https://www.superfinanciera.gov.co/ABCD/superfinanciera/php/buscar_integrada.php
      ?base=juris&Opcion=libre&coleccion=<codigo>|<etiqueta>|TM_
    codigo: "ac" (Doctrina y conceptos), "af" (Fallos jurisdiccionales),
            "aj" (Jurisprudencia financiera)
  - El HTML llega en ISO-8859-1, no UTF-8 (charset confirmado en la
    respuesta real). Hay que decodificar explícitamente.
  - Estructura de campos por registro validada contra HTML crudo real de
    las tres colecciones, incluida su última página (ver parser.py).
  - Conteo real de registros por colección (leído del texto "N registros"
    que trae cada página de resultados):
      ac: 3.431 | af: 14.466 | aj: 807  (total: 18.704)
  - Paginación: el enlace "Próxima" (`javascript:ProximaPagina(pagina,
    offset)`) resultó ser cosmético — la función JS que lo respalda no
    existe en ninguno de los scripts que carga la página (se buscó en los
    4 <script src> y en los <script> inline). Lo que sí funciona, replicado
    y confirmado contra la página 1, una página intermedia y la última
    página de las tres colecciones, es un POST directo a
    buscar_integrada.php con los mismos campos ocultos del formulario
    `forma1` de la página de resultados, cambiando `desde`:
      desde=<offset 1-based>, count=25, base=juris, Opcion=libre,
      coleccion=<codigo>|<etiqueta>|TM_, indice_base=0,
      Formato=opac.pft, alcance=or, prefijo_col=<Xac|Xaf|Xaj>, Diccio=0,
      Sub_Expresion=""
    `count` es fijo en 25 registros por página en el sitio real (visto en
    el propio HTML). `offset` avanza de 25 en 25 (1, 26, 51, ...); no hay
    que confiar en los offsets que trae el paginador de la página 1 más
    allá de eso (se detectaron saltos no lineales cerca del final de la
    colección "ac", probablemente por registros fusionados/eliminados en
    el catálogo ISIS) — por eso `raspar_coleccion` para de avanzar cuando
    una página ya no trae registros nuevos, no cuando cree haber llegado
    al offset "correcto".

  - Extracción de texto completo: "Acceso web" con tipo_archivo="texto" NO
    sirve texto plano pese al nombre — sirve un archivo binario
    (Content-Type application/octet-stream, sin indicar el formato real
    de forma confiable). Decodificarlo como ISO-8859-1 sin más corrompe
    el contenido (confirmado: produce bytes NUL y basura binaria, y
    falla al insertarlo en Postgres). Hay que detectar el formato real
    por firma de bytes y extraer texto según corresponda — ver
    `extraer_texto_archivo`. Censo completo (no muestra) de los 3.431
    registros de `ac` (ver README, sección "Censo de formatos"): docx
    (914, sobre todo 2010-2026), doc_ole (898, en dos bloques separados
    1994-1998 y 2009-2013 — confirmado contra archivos reales, no es
    error de detección), html (798, 1999-2005) y pdf (809, sobre todo
    2006-2008). Los 4 formatos tienen extractor y están validados contra
    14 archivos reales descargados (ver README). `extraer_texto_archivo`
    sigue devolviendo None ante contenido irreconocible o si el
    extractor de un formato soportado falla puntualmente, en vez de
    producir texto corrupto.

Pendiente antes de escalar a las ~750 páginas totales:
  - Revisar robots.txt / términos de uso del sitio antes de lanzar el
    scraper a escala completa.
  - Confirmar que `antiword` (dependencia de sistema para doc_ole) esté
    disponible en el entorno de producción — ver README.
  - Extender el censo de formatos a `af`/`aj` (por ahora solo se censó
    `ac`) antes de ingerir texto completo de esas dos colecciones.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import time
import zipfile
from dataclasses import asdict
from io import BytesIO
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from parser import parse_pagina_resultados

_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

BASE_URL = "https://www.superfinanciera.gov.co/ABCD/superfinanciera/php/buscar_integrada.php"

COLECCIONES = {
    "ac": "Doctrina y conceptos",
    "af": "Fallos jurisdiccionales",
    "aj": "Jurisprudencia financiera",
}

# Requerido por el POST de paginación (ver docstring del módulo); confirmado
# contra el HTML real de cada colección (input hidden "prefijo_col").
PREFIJO_COL = {
    "ac": "Xac",
    "af": "Xaf",
    "aj": "Xaj",
}

RESULTADOS_POR_PAGINA = 25

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; investigacion-normativa/0.1)"
}

_RE_TOTAL_REGISTROS = re.compile(r"([\d.,]+)\s*registros", re.IGNORECASE)


def extraer_total_registros(html: str) -> int | None:
    """Lee el conteo total ('N registros') que el sitio muestra en cada
    página de resultados. Devuelve None si no se encuentra el texto."""
    m = _RE_TOTAL_REGISTROS.search(html)
    if not m:
        return None
    return int(m.group(1).replace(".", "").replace(",", ""))


def obtener_pagina(session: requests.Session, coleccion: str, desde: int = 1) -> str:
    """Trae una página de resultados (1-based `desde`, 25 registros por
    página) para una colección y la decodifica correctamente (el sitio
    responde en ISO-8859-1, no UTF-8).

    Se usa POST porque es el mecanismo confirmado contra el sitio real
    (ver docstring del módulo) tanto para la página 1 como para avanzar.
    """
    data = {
        "desde": desde,
        "count": RESULTADOS_POR_PAGINA,
        "base": "juris",
        "Opcion": "libre",
        "coleccion": f"{coleccion}|{COLECCIONES[coleccion]}|TM_",
        "indice_base": "0",
        "Formato": "opac.pft",
        "alcance": "or",
        "prefijo_col": PREFIJO_COL[coleccion],
        "Diccio": "0",
        "Sub_Expresion": "",
    }
    resp = session.post(BASE_URL, data=data, headers=HEADERS, timeout=30)
    resp.encoding = "ISO-8859-1"
    return resp.text


def descargar_archivo(session: requests.Session, url: str) -> bytes:
    """Descarga el 'Archivo de texto' o 'Archivo de audio' asociado a un
    registro. Para audio, por ahora no se transcribe (decisión tomada:
    los fallos sin texto se guardan solo con resumen)."""
    resp = session.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.content


def _extraer_texto_docx(contenido: bytes) -> str:
    with zipfile.ZipFile(BytesIO(contenido)) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    parrafos = []
    for p in root.iter(f"{_DOCX_NS}p"):
        texto = "".join(t.text or "" for t in p.iter(f"{_DOCX_NS}t"))
        if texto.strip():
            parrafos.append(texto)
    return "\n".join(parrafos)


def _extraer_texto_html(contenido: bytes) -> str:
    """Los archivos "texto" en formato html (colección `ac`, 1999-2005) son
    en realidad páginas ISO-8859-1 con un único registro: una tabla de
    cabecera cosmética, el cuerpo del concepto/fallo en párrafos <font>/<P>,
    y un enlace de navegación "atrás" al final (ver README). Se descarta
    script/style y se colapsan las líneas en blanco que deja el layout con
    tablas.
    """
    soup = BeautifulSoup(contenido.decode("ISO-8859-1"), "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    lineas = (linea.strip() for linea in soup.get_text(separator="\n").splitlines())
    return "\n".join(linea for linea in lineas if linea)


def _extraer_texto_pdf(contenido: bytes) -> str:
    """Los pdf de la colección `ac` (2006-2008) traen capa de texto real
    (no son escaneos), confirmado contra 4 muestras reales de 2008 — pypdf
    extrae la misma estructura título/Concepto/Síntesis/cuerpo que docx y
    html. Puede dejar espacios sueltos dentro de alguna palabra acentuada
    por el kerning del PDF original; se deja así (no se puede corregir sin
    heurísticas de palabras que arriesgan corromper texto real).
    """
    reader = PdfReader(BytesIO(contenido))
    lineas = (
        linea.strip()
        for pagina in reader.pages
        for linea in (pagina.extract_text() or "").splitlines()
    )
    return "\n".join(linea for linea in lineas if linea)


def _extraer_texto_doc_ole(contenido: bytes) -> str | None:
    """.doc binario legado (formato OLE), visto en `ac` en dos bloques no
    contiguos, 1994-1998 y 2009-2013 (ver README: la SFC volvió a guardar
    como .doc por varios años antes de pasar a .docx en 2014 — confirmado
    contra el sitio real, no es un error de detección).

    No hay librería pura Python confiable para este formato binario; se usa
    `antiword` (paquete del sistema — ver requisitos en el README) vía
    subprocess con el contenido por stdin. Validado contra 6 muestras reales
    de ambas épocas. Si el binario no está instalado o falla contra un
    archivo puntual, se devuelve None en vez de reventar el scraping.
    """
    try:
        resultado = subprocess.run(
            ["antiword", "-w", "0", "-"],
            input=contenido,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    if resultado.returncode != 0:
        return None
    lineas = (linea.strip() for linea in resultado.stdout.decode("utf-8", errors="replace").splitlines())
    return "\n".join(linea for linea in lineas if linea)


def extraer_texto_archivo(contenido: bytes) -> tuple[str | None, str | None]:
    """Detecta el formato real del archivo por firma de bytes (el sitio no
    lo indica de forma confiable: Content-Type siempre
    application/octet-stream) y extrae texto plano.

    Devuelve (texto, motivo_si_no_hay_texto). `motivo` es None si `texto`
    no es None; si no, distingue "formato_no_reconocido" (ninguna firma de
    bytes conocida) de "extraccion_fallida" (el formato sí se reconoció
    pero el extractor no produjo texto — p.ej. `antiword` no instalado o
    un archivo puntual corrupto) para no mezclar ambos bajo el mismo
    "sin texto" que el caso de audio (ver parser.py:motivo_sin_texto). No
    se guarda texto_completo en ninguno de los dos casos — mejor no
    guardar nada que basura binaria decodificada a ciegas como ISO-8859-1
    (ver nota del docstring del módulo).
    """
    if contenido[:4] == b"PK\x03\x04":
        texto = _extraer_texto_docx(contenido)
    elif contenido[:4] == b"%PDF":
        texto = _extraer_texto_pdf(contenido)
    elif contenido[:4] == b"\xd0\xcf\x11\xe0":
        texto = _extraer_texto_doc_ole(contenido)
    elif contenido.lstrip()[:1] == b"<":
        texto = _extraer_texto_html(contenido)
    else:
        return None, "formato_no_reconocido"
    return (texto, None) if texto else (None, "extraccion_fallida")


def raspar_coleccion(
    coleccion: str, max_paginas: int, dry_run: bool, pausa: float = 1.0
) -> list[dict]:
    """Recorre la colección en páginas de `RESULTADOS_POR_PAGINA` registros,
    avanzando `desde` por POST (ver `obtener_pagina`). Se detiene cuando:
      - se alcanza `max_paginas`,
      - una página ya no trae registros, o
      - `desde` supera el total de registros reportado por el sitio.
    No confía en los offsets del paginador de la página 1 más allá del
    tamaño de página fijo (ver nota de paginación en el docstring del
    módulo): siempre avanza en incrementos de `RESULTADOS_POR_PAGINA`.
    """
    if not dry_run and shutil.which("antiword") is None:
        print(
            "  ! antiword no está instalado en este entorno: los registros "
            "en formato .doc legado (OLE) quedarán sin texto_completo "
            "(motivo_sin_texto='extraccion_fallida'). Ver README."
        )

    session = requests.Session()
    resultado: list[dict] = []

    desde = 1
    pagina_num = 0
    total_registros: int | None = None

    while True:
        html = obtener_pagina(session, coleccion, desde=desde)
        if total_registros is None:
            total_registros = extraer_total_registros(html)
            if total_registros is not None:
                print(f"Colección '{coleccion}': {total_registros} registros en total.")

        registros = parse_pagina_resultados(html)
        if not registros:
            break

        pagina_num += 1
        print(f"  página {pagina_num} (desde={desde}): {len(registros)} registros")
        for r in registros:
            registro_dict = asdict(r)
            if not dry_run and r.tipo_archivo == "texto" and r.url_archivo:
                try:
                    contenido = descargar_archivo(session, r.url_archivo)
                except requests.RequestException as e:
                    print(f"  ! No se pudo descargar {r.url_archivo}: {e}")
                    registro_dict["tiene_texto_completo"] = False
                    registro_dict["motivo_sin_texto"] = "descarga_fallida"
                else:
                    texto, motivo = extraer_texto_archivo(contenido)
                    if texto is None:
                        print(f"  ! Sin texto ({motivo}): {r.url_archivo}")
                    registro_dict["texto_completo"] = texto
                    registro_dict["tiene_texto_completo"] = texto is not None
                    registro_dict["motivo_sin_texto"] = motivo
            resultado.append(registro_dict)

        if pagina_num >= max_paginas:
            break
        desde += RESULTADOS_POR_PAGINA
        if total_registros is not None and desde > total_registros:
            break
        time.sleep(pausa)

    return resultado


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coleccion", choices=COLECCIONES.keys(), default="ac")
    ap.add_argument("--paginas", type=int, default=1)
    ap.add_argument(
        "--pausa",
        type=float,
        default=1.0,
        help="Segundos de espera entre páginas (cortesía con el sitio).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo parsea metadatos, no descarga archivos de texto completo.",
    )
    args = ap.parse_args()

    registros = raspar_coleccion(args.coleccion, args.paginas, args.dry_run, args.pausa)
    print(f"\n{len(registros)} registros procesados de la colección '{args.coleccion}'.")
    for r in registros[:3]:
        print("-" * 60)
        print(r["tipo_documento"], "|", r["numero_documento"], "|", r["titulo"])


if __name__ == "__main__":
    main()
