"""
Scraper de la Circular Básica Financiera (CBF) — Superintendencia
Financiera de Colombia.

CÓMO CORRERLO:

    pip install requests beautifulsoup4 --break-system-packages
    python scraper.py --dry-run

VALIDADO contra el sitio real el 2026-09-22 (ver Ingest/CBF/README.md,
sección "Investigado hasta ahora" para el detalle completo):

  - NO hay ningún API dinámico ("apiCbf", "capituloXParteBorrador",
    "download-zip" no existen — se investigó en vivo y se descartó). Es
    una página CMS estática normal, mismo patrón que
    app/ingest/dian_scraper.py: sin JS, sin API key.
  - Las 4 Partes completas (Administración de riesgos; Controles de ley y
    asuntos prudenciales; Información financiera y esquemas de reporte;
    Otras disposiciones) viven en UNA SOLA página:
      https://www.superfinanciera.gov.co/publicaciones/10116084/
      circular-basica-financiera-circular-externa-004-de-2026/
    como una tabla HTML con jerarquía Parte→Capítulo→Sección vía
    `rowspan`. Se reconstruye con `_reconstruir_grid` resolviendo los
    rowspan reales (contar <td> por fila NO alcanza: las filas de Anexo
    de cierre de la Parte 4 rompen ese patrón — ver README).
  - Cada capítulo/sección/anexo descargable es un link
    `loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&
    idFile=<N>` a un `.docx` real (confirmado: Content-Disposition con
    filename real, firma de bytes ZIP/Word 2007+).
  - Notas de vigencia como texto plano junto al link del capítulo,
    en tres patrones observados (ver `_RE_FECHA_FIJA`,
    `_RE_CONDICIONADA`, `_RE_VERSION_FUTURA`):
      (a) fecha fija: "...y entra en vigencia el 3 de abril de 2027."
      (b) condicionada a un decreto, sin fecha fija: "...en los términos
          previstos en el Decreto 0219 de 2026..."
      (c) dos `.docx` separados para el mismo capítulo — vigente + un
          segundo link "Versión del capítulo X que entrará a regir el
          [fecha]..." (patrón P2.C9, el único caso de este tipo visto en
          la tabla actual). Se detecta contando los `<p>` hijos directos
          de la celda del capítulo: 2+ implica el patrón de dos-versiones
          (confirmado: la celda de P2.C9 tiene exactamente 2 `<p>`, todas
          las demás celdas de capítulo tienen 0 o 1).
  - El `.docx` de una "versión futura" (ej. idFile=1081457 para P2.C9) NO
    viene limpio: trae una nota administrativa corta duplicada varias
    veces antes de repetir el encabezado del capítulo por segunda vez, y
    ahí sí empieza el cuerpo real. `separar_nota_futura` corta en la
    SEGUNDA aparición del encabezado (nombre del capítulo), no en un
    offset fijo — ver excepcion_p2c9_vigencia.json para el caso ya
    verificado a mano.

Pendiente antes de escalar:
  - Revisar robots.txt / términos de uso (mismo dominio que Ingest/SFC,
    ya revisado allá — confirmar que la autorización de Ley 1712 de 2014
    aplica igual a /publicaciones/ y /loader.php, no asumirlo).
  - La Circular Básica Jurídica (CBJ) tiene niveles Título y
    Numeral/Subnumeral adicionales en su jerarquía — su página real no se
    ha investigado; no asumir que usa la misma URL/estructura de tabla.
"""

from __future__ import annotations

import argparse
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

URL_TABLA_CBF = (
    "https://www.superfinanciera.gov.co/publicaciones/10116084/"
    "circular-basica-financiera-circular-externa-004-de-2026/"
)
URL_LOADER = "https://www.superfinanciera.gov.co/loader.php"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; investigacion-normativa/0.1)"}

NOMBRES_PARTE = {
    1: "Administración de riesgos",
    2: "Controles de Ley y asuntos prudenciales",
    3: "Información financiera y esquemas de reporte",
    4: "Otras disposiciones",
}

_RE_IDFILE = re.compile(r"idFile=(\d+)")
_RE_PARTE = re.compile(r"^\s*Parte\s+(\d+)", re.IGNORECASE)
_RE_CAPITULO = re.compile(r"Cap[ií]tulo\s+(\d+)", re.IGNORECASE)
_RE_FECHA_FIJA = re.compile(
    r"entra(?:r[áa])?\s+(?:a regir|en vigencia)\s+el\s+"
    r"(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
    re.IGNORECASE,
)
_RE_CONDICIONADA = re.compile(r"en los t[ée]rminos previstos en el Decreto", re.IGNORECASE)
_RE_VERSION_FUTURA = re.compile(r"Versi[oó]n del cap[ií]tulo", re.IGNORECASE)
_RE_ANEXO = re.compile(r"^Anexos?(\s+\d+)?$", re.IGNORECASE)

# Marcador de numeral como párrafo propio dentro del .docx, ej. "2.9.1."
# (Parte.Capítulo.Numeral, profundidad 3) — confirmado contra el .docx
# real de P2.C9. La profundidad NO es fija: capítulos con Sección usan un
# nivel más, ej. "2.4.2.1." (Parte.Capítulo.Sección.Numeral, profundidad
# 4) — confirmado contra P2.C4 Sección 2 en el dry-run (ver README/
# reporte: sin este rango, esas secciones reportaban 0 numerales). Se deja
# un margen hasta profundidad 5 por si aparece Subnumeral en algún
# capítulo no muestreado todavía.
#
# OJO: este regex por sí solo NO basta. Algunos numerales embeben tablas
# de clasificación/taxonomía con su propia numeración interna que también
# matchea "N.N.N" (ej. la taxonomía de tipo de evento de riesgo operativo
# en P1.C1 Sección 3 — ver README, "Resultado del dry-run"). Un marcador
# solo cuenta como numeral real del capítulo si además empieza con el
# prefijo "{parte}.{capitulo}." del propio archivo — ver
# prototipo_fragmentacion_numeral_cbf.py:_numerales_y_fragmentos.
_RE_NUMERAL_LINEA = re.compile(r"^\d{1,2}(\.\d{1,3}){2,4}\.?$")

# Segunda forma real del marcador: el numeral al FINAL de una línea, pegado
# (con espacio o \xa0) a un encabezado en mayúsculas — a veces con el
# párrafo anterior en la misma línea. Visto en la versión futura de P2.C9
# (excepcion_p2c9_vigencia.json), donde 10 de sus 30 numerales vienen así y
# _RE_NUMERAL_LINEA no los veía (bug real, 2026-09-28, ver README):
#   "INTRODUCCIÓN\xa02.9.1."
#   "…escenario.\xa0PRUEBAS DE RESISTENCIA INVERSAS\xa02.9.19."
#   "…entorno económico y sectorial.GOBIERNO DEL EPR\xa02.9.25."
# Lo que lo distingue de una referencia dentro del texto ("…del párrafo
# 2.9.30. del presente Capítulo") es el encabezado en mayúsculas justo
# antes y que el numeral cierra la línea. El encabezado debe empezar en un
# límite de palabra y tener al menos 4 letras, para no tomar una sigla
# suelta ("…la SFC 2.9.3.") como encabezado.
_RE_NUMERAL_FIN_ENCABEZADO = re.compile(
    r"(?<![A-Za-zÁÉÍÓÚÜÑáéíóúüñ])"
    r"(?P<encabezado>[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ0-9 \xa0,()«»\-–]*?)\s+"
    r"(?P<numeral>\d{1,2}(?:\.\d{1,3}){2,4})\.?$"
)


def posiciones_numerales(texto: str, prefijo: str) -> list[tuple[int, str]]:
    """[(offset en `texto` donde empieza el marcador, numeral sin punto
    final)] en orden de aparición. Reconoce las dos formas del marcador:
    línea propia ("2.9.3.") y final de línea tras un encabezado en
    mayúsculas ("INTRODUCCIÓN 2.9.1."). Solo cuenta un marcador que empieza
    con `prefijo` ("{parte}.{capitulo}.") — ver el OJO de arriba sobre las
    tablas de taxonomía con numeración propia. Pensada para reutilizarse
    tal cual en la CBJ (paso 7)."""
    posiciones: list[tuple[int, str]] = []
    offset = 0
    for linea in texto.split("\n"):
        l = linea.strip()
        inicio_l = offset + (len(linea) - len(linea.lstrip()))
        if _RE_NUMERAL_LINEA.match(l):
            if l.startswith(prefijo):
                posiciones.append((inicio_l, l.rstrip(".")))
        else:
            m = _RE_NUMERAL_FIN_ENCABEZADO.search(l)
            if (
                m
                and m.group("numeral").startswith(prefijo)
                and sum(c.isalpha() for c in m.group("encabezado")) >= 4
            ):
                posiciones.append((inicio_l + m.start("numeral"), m.group("numeral")))
        offset += len(linea) + 1  # +1 por el "\n" que junta las líneas
    return posiciones


@dataclass
class ArchivoCBF:
    id_archivo: int
    titulo: str
    parte: int | None
    nombre_parte: str | None
    numero_capitulo: int | None
    nombre_capitulo: str | None
    seccion: str | None
    tipo: str  # "capitulo" | "seccion" | "anexo" | "version_futura"
    estado_vigencia: str  # "vigente" | "vigencia_futura" | "vigencia_condicionada"
    fecha_vigencia_inicio: str | None
    nota_vigencia: str | None


def obtener_tabla_cbf(session: requests.Session) -> str:
    """Trae la página única con las 4 Partes completas. No hay
    paginación ni API: todo vive en este solo GET."""
    resp = session.get(URL_TABLA_CBF, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def _texto_celda(td) -> str:
    return td.get_text(" ", strip=True)


def _reconstruir_grid(tbody) -> list[list]:
    """Reconstruye la tabla como grid de 3 columnas (Parte, Capítulo,
    Sección) resolviendo los `rowspan` reales del HTML. Contar <td> por
    fila NO alcanza: las filas de Anexo de cierre de la Parte 4 tienen 3
    <td> igual que una fila de Parte nueva, sin serlo (ver README) — por
    eso se resuelve por rowspan real, no por conteo posicional.

    Cada celda va como (td, es_nueva): es_nueva es False cuando la celda
    se repite por `rowspan` desde una fila anterior — el llamador debe
    usarlo para no reprocesar/duplicar el contenido de esa celda una vez
    por cada fila que cubre (bug real encontrado en el dry-run: sin esto,
    un capítulo con 5 secciones duplicaba su link de "Anexos" 5 veces)."""
    filas = []
    pendientes: dict[int, list] = {}
    for tr in tbody.find_all("tr", recursive=False):
        tds = iter(tr.find_all("td", recursive=False))
        fila = []
        for col in range(3):
            pendiente = pendientes.get(col)
            if pendiente and pendiente[1] > 0:
                fila.append((pendiente[0], False))
                pendiente[1] -= 1
                continue
            td = next(tds, None)
            fila.append((td, True) if td is not None else (None, False))
            if td is not None:
                rowspan = int(td.get("rowspan", 1) or 1)
                if rowspan > 1:
                    pendientes[col] = [td, rowspan - 1]
        filas.append(fila)
    return filas


def _bloques_de_celda(td) -> list:
    """Un bloque por cada <p> hijo directo si hay 2 o más (patrón de
    dos-versiones, ej. P2.C9); si no, toda la celda es un único bloque."""
    parrafos = td.find_all("p", recursive=False)
    return parrafos if len(parrafos) >= 2 else [td]


def _vigencia_de_bloque(texto: str) -> tuple[str, str | None]:
    if _RE_VERSION_FUTURA.search(texto):
        m = _RE_FECHA_FIJA.search(texto)
        return "vigencia_futura", (m.group(1) if m else None)
    if _RE_CONDICIONADA.search(texto):
        return "vigencia_condicionada", None
    m = _RE_FECHA_FIJA.search(texto)
    if m:
        return "vigencia_futura", m.group(1)
    return "vigente", None


def _nombre_capitulo_de_bloque(texto: str, numero_capitulo: int | None) -> str:
    if numero_capitulo is not None:
        texto = re.sub(rf"^.*?Cap[ií]tulo\s+{numero_capitulo}\s*-?\s*", "", texto, count=1)
    for corte in (" - Anexo", " - Este capítulo fue", " - Versión del capítulo", " Este capítulo entra", " Versión del capítulo"):
        idx = texto.find(corte)
        if idx != -1:
            texto = texto[:idx]
    return texto.strip(" -")


def _archivos_de_bloque_capitulo(
    bloque,
    parte: int | None,
    nombre_parte: str | None,
    numero_capitulo_forzado: int | None = None,
    nombre_capitulo_forzado: str | None = None,
) -> tuple[int | None, str | None, str, str | None, list[ArchivoCBF]]:
    """`*_forzado` se usa para el bloque de "versión futura" (ej. P2.C9):
    su propio texto es "Versión del capítulo N que entrará a regir..."
    -- no el título real del capítulo -- así que el número/nombre se
    heredan del bloque principal (vigente) de la misma celda en vez de
    derivarse de este bloque. Sin esto, separar_nota_futura recibía un
    nombre_capitulo incorrecto y fallaba en encontrarlo repetido en el
    texto (bug real encontrado en el dry-run)."""
    texto = bloque.get_text(" ", strip=True).replace("\xa0", " ")
    texto = re.sub(r"\s+", " ", texto).strip()
    m_cap = _RE_CAPITULO.search(texto)
    numero_capitulo = numero_capitulo_forzado if numero_capitulo_forzado is not None else (
        int(m_cap.group(1)) if m_cap else None
    )
    estado, fecha = _vigencia_de_bloque(texto)
    nombre_capitulo = nombre_capitulo_forzado or _nombre_capitulo_de_bloque(texto, numero_capitulo)
    nota = texto if estado != "vigente" else None

    archivos = []
    links = [a for a in bloque.find_all("a") if _RE_IDFILE.search(a.get("href", ""))]
    for a in links:
        titulo_link = a.get_text(strip=True)
        id_archivo = int(_RE_IDFILE.search(a["href"]).group(1))
        if _RE_ANEXO.match(titulo_link):
            tipo = "anexo"
        elif _RE_VERSION_FUTURA.search(texto) and _RE_CAPITULO.search(titulo_link):
            tipo = "version_futura"
        elif "circular externa" in titulo_link.lower() or "decreto" in titulo_link.lower():
            continue  # cita normativa, no es contenido de la CBF en sí
        else:
            tipo = "capitulo"
        archivos.append(
            ArchivoCBF(
                id_archivo=id_archivo,
                titulo=titulo_link,
                parte=parte,
                nombre_parte=nombre_parte,
                numero_capitulo=numero_capitulo,
                nombre_capitulo=nombre_capitulo,
                seccion=None,
                tipo=tipo,
                estado_vigencia=estado,
                fecha_vigencia_inicio=fecha,
                nota_vigencia=nota,
            )
        )
    return numero_capitulo, nombre_capitulo, estado, fecha, archivos


def parse_tabla_cbf(html: str) -> list[ArchivoCBF]:
    """Parsea la tabla real de las 4 Partes en una lista plana de
    archivos descargables, con jerarquía y vigencia resueltas. Ver
    docstring del módulo para el mecanismo validado contra el sitio."""
    soup = BeautifulSoup(html, "html.parser")
    tabla = None
    for t in soup.find_all("table"):
        th = t.find("th")
        if th and "Partes" in th.get_text():
            tabla = t
            break
    if tabla is None:
        raise RuntimeError("No se encontró la tabla de Partes/Capítulos/Secciones")

    filas = _reconstruir_grid(tabla.find("tbody"))

    resultado: list[ArchivoCBF] = []
    parte_actual: int | None = None
    nombre_parte_actual: str | None = None
    capitulo_actual: int | None = None
    nombre_capitulo_actual: str | None = None
    estado_capitulo_actual = "vigente"
    fecha_capitulo_actual = None

    for (parte_td, parte_nueva), (capitulo_td, capitulo_nueva), (seccion_td, seccion_nueva) in filas:
        if parte_td is not None and parte_nueva:
            if not _RE_PARTE.match(_texto_celda(parte_td)):
                # Filas de Anexo de cierre de la Parte 4 (ver README): no
                # traen rowspan de Parte, así que el grid las lee como si
                # fueran (Parte, Capítulo, Sección) nuevas sin serlo en
                # realidad — son en verdad (Anexo, descripción) con la
                # Parte de la fila anterior. Se corrige el corrimiento de
                # columna en vez de perder el archivo silenciosamente.
                capitulo_td, capitulo_nueva = parte_td, True
                seccion_td, seccion_nueva = None, False
                parte_td = None
            else:
                m = _RE_PARTE.match(_texto_celda(parte_td))
                parte_actual = int(m.group(1))
                nombre_parte_actual = NOMBRES_PARTE.get(parte_actual)

        if capitulo_td is not None and capitulo_nueva:
            numero_capitulo_celda = None
            nombre_capitulo_celda = None
            for bloque in _bloques_de_celda(capitulo_td):
                numero_capitulo, nombre_capitulo, estado, fecha, archivos = (
                    _archivos_de_bloque_capitulo(
                        bloque, parte_actual, nombre_parte_actual,
                        numero_capitulo_celda, nombre_capitulo_celda,
                    )
                )
                if numero_capitulo_celda is None:
                    numero_capitulo_celda = numero_capitulo
                    nombre_capitulo_celda = nombre_capitulo
                # Se actualiza el contexto de capítulo aunque el bloque no
                # tenga link propio (ej. un capítulo cuyo contenido vive
                # solo en sus Secciones, como el Capítulo 10 de la Parte 2
                # — bug real encontrado en el dry-run: antes esto se
                # gateaba en `archivos` no vacío y las Secciones del
                # capítulo siguiente quedaban mal atribuidas al anterior).
                if archivos and archivos[0].tipo == "version_futura":
                    pass  # no mover el contexto "actual" por la versión futura
                else:
                    capitulo_actual = numero_capitulo
                    nombre_capitulo_actual = nombre_capitulo
                    estado_capitulo_actual = estado
                    fecha_capitulo_actual = fecha
                resultado.extend(archivos)

        if seccion_td is not None and seccion_nueva:
            texto_seccion = _texto_celda(seccion_td).replace("\xa0", " ").strip()
            if texto_seccion:
                for a in seccion_td.find_all("a"):
                    href = a.get("href", "")
                    m_id = _RE_IDFILE.search(href)
                    if not m_id:
                        continue
                    resultado.append(
                        ArchivoCBF(
                            id_archivo=int(m_id.group(1)),
                            titulo=a.get_text(strip=True),
                            parte=parte_actual,
                            nombre_parte=nombre_parte_actual,
                            numero_capitulo=capitulo_actual,
                            nombre_capitulo=nombre_capitulo_actual,
                            seccion=texto_seccion,
                            tipo="seccion",
                            estado_vigencia=estado_capitulo_actual,
                            fecha_vigencia_inicio=fecha_capitulo_actual,
                            nota_vigencia=None,
                        )
                    )
    return resultado


def descargar_archivo(session: requests.Session, id_archivo: int) -> bytes:
    resp = session.get(
        URL_LOADER,
        params={
            "lServicio": "Tools2",
            "lTipo": "descargas",
            "lFuncion": "descargar",
            "idFile": id_archivo,
        },
        headers=HEADERS,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


def extraer_texto_docx(contenido: bytes) -> str:
    with zipfile.ZipFile(BytesIO(contenido)) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    parrafos = []
    for p in root.iter(f"{_DOCX_NS}p"):
        texto = "".join(t.text or "" for t in p.iter(f"{_DOCX_NS}t"))
        if texto.strip():
            parrafos.append(texto)
    return "\n".join(parrafos)


def separar_nota_futura(texto: str, nombre_capitulo: str) -> tuple[str, str]:
    """Para el .docx de una 'versión futura' (ej. patrón P2.C9): el
    encabezado del capítulo aparece dos veces, con la nota administrativa
    corta (duplicada varias veces) entre la primera y la segunda
    aparición. Corta en la SEGUNDA aparición del encabezado — no en un
    offset fijo, porque la longitud de la nota no es constante entre
    capítulos. Devuelve (nota_administrativa, cuerpo_real).
    Lanza ValueError si el encabezado no se repite (formato inesperado:
    revisar a mano, no asumir el patrón)."""
    patron_encabezado = re.compile(re.escape(nombre_capitulo), re.IGNORECASE)
    apariciones = list(patron_encabezado.finditer(texto))
    if len(apariciones) < 2:
        raise ValueError(
            f"El encabezado '{nombre_capitulo}' no se repite en el texto "
            "(se esperaba 2 apariciones: header inicial + inicio del "
            "cuerpo real tras la nota) — revisar a mano."
        )
    corte = apariciones[1].start()
    return texto[:corte].strip(), texto[corte:].strip()


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Solo parsea y reporta, no descarga texto completo")
    args = parser.parse_args()

    session = requests.Session()
    html = obtener_tabla_cbf(session)
    archivos = parse_tabla_cbf(html)

    print(f"{len(archivos)} archivos descargables encontrados en las 4 Partes\n")
    por_tipo: dict[str, int] = {}
    for a in archivos:
        por_tipo[a.tipo] = por_tipo.get(a.tipo, 0) + 1
    for tipo, n in sorted(por_tipo.items()):
        print(f"  {tipo}: {n}")

    if not args.dry_run:
        print("\n(usa --dry-run; la descarga completa vive en "
              "prototipo_fragmentacion_numeral_cbf.py / ingest_pilot.py)")


if __name__ == "__main__":
    _cli()
