"""Scraper de normograma.dian.gov.co: descubre e ingiere normas tributarias.

IMPORTANTE — escrito sin poder inspeccionar el DOM real del sitio en vivo
desde esta sesión: el proxy de red de este entorno de Claude Code bloquea
normograma.dian.gov.co, así que todo lo de abajo viene de lo que el
usuario reportó tras inspeccionar el sitio con acceso real (fuera de esta
sesión) y de un primer run de prueba fallido que sirvió de diagnóstico —
no de verificación directa por quien escribió este código. Sigue habiendo
partes heurísticas sin validar (marcadas AJUSTAR), sobre todo
`_extraer_articulos` y `_estado_y_nota_vigencia` para documentos distintos
al artículo 420 del Estatuto Tributario (ese sí se validó manualmente).

Confirmado con acceso real al sitio (no heurístico):
- URL del índice tributario: t_1_normativa_tributaria.html cuelga
  directamente de /dian/compilacion/, sin /docs/ ni query params.
- El encabezado de cada sección (ej. "1.1. Estatuto Tributario") sí está
  en el HTML estático — no requiere esperar a JavaScript para aparecer.
- Los enlaces a documentos individuales SÍ requieren expandir la sección
  primero (de ahí el uso de Playwright solo para esta parte): el control
  para expandir es un ÍCONO (<img alt="Ver Más">) cercano al encabezado,
  no un nodo de texto "Ver Más". Confirmado con capturas de pantalla que
  el clic sí expande la sección visualmente, pero los enlaces resultantes
  no quedan anidados dentro de ningún ancestro cercano al encabezado/
  ícono — por eso `descubrir_urls_seccion` compara los enlaces de toda la
  página antes/después del clic en vez de acotar a un contenedor.
- Los documentos individuales son HTML plano, con enlaces cruzados a
  otras normas por nombre de archivo (ej. ley_2068_2020.htm,
  decreto_1742_2020.htm) y anclas a artículos específicos
  (ej. estatuto_tributario.htm#420).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from sqlalchemy.orm import Session

from app.embeddings import embed_document
from app.models import Norma

logger = logging.getLogger(__name__)

DOMINIO = "normograma.dian.gov.co"
INDEX_URL = "https://normograma.dian.gov.co/dian/compilacion/t_1_normativa_tributaria.html"

# Patrón del ícono "Ver Más": es una <img alt="Ver Más">, no un nodo de
# texto — confirmado con acceso real al sitio.
VER_MAS_ALT_RE = re.compile(r"ver\s*m[aá]s", re.IGNORECASE)

USER_AGENT = "buscador-normatividad-bot/0.1 (+ingesta de normatividad tributaria publica)"
REQUEST_DELAY_SECONDS = 1.0

# Encabezado de artículo al inicio de línea: "ARTÍCULO 420.", "Artículo 5o.",
# "ARTÍCULO 631-1." (numeración de artículos "adicionados", muy común en el
# Estatuto Tributario: 631-1 a 631-6, 869-1, 108-1, etc. — el grupo
# "(?:-[0-9]+)*" captura el/los sufijo(s) numérico(s) completos en vez de
# cortarse en el guión, que era el bug original: [A-Za-z°ºo\-]* no incluía
# dígitos, así que "631-1", "631-2"... "631-6" colapsaban todos en
# numero_articulo="631-" y se descartaban como duplicados del primero).
# No captura menciones de "artículo" a mitad de párrafo porque exige
# inicio de línea (^) — pero el corte de líneas del HTML real puede no
# coincidir exactamente con esta suposición; ajustar si un run produce
# fragmentos mal cortados.
ARTICULO_HEADER_RE = re.compile(
    r"(?im)^\s*(?:ART[ÍI]CULO|ART\.)\s+([0-9]+(?:-[0-9]+)*[A-Za-zºo°]*)\s*\.?[\-–—]?\s*"
)

# Nota de vigencia esperada justo después del encabezado del artículo, ej.
# "(Modificado por el artículo 57 de la Ley 2277 de 2022)".
VIGENCIA_RE = re.compile(
    r"\((Modificad[oa]|Derogad[oa]|Adicionad[oa]|Subrogad[oa])[^)]{0,300}\)",
    re.IGNORECASE,
)

# Enlaces cruzados a otras normas dentro de un documento (por nombre de
# archivo), para descubrimiento adicional sin depender del buscador propio
# del sitio.
DOC_LINK_RE = re.compile(
    r"/(ley|decreto|resolucion|concepto|estatuto)[\w\-]*\.html?$", re.IGNORECASE
)


@dataclass
class DocumentoDescubierto:
    url: str
    titulo: str = ""


def _tipo_norma_desde_url(url: str) -> str:
    nombre = urlparse(url).path.rsplit("/", 1)[-1].lower()
    if "estatuto_tributario" in nombre:
        return "articulo_et"
    if nombre.startswith("ley_"):
        return "ley"
    if nombre.startswith("decreto_"):
        return "decreto"
    if nombre.startswith("concepto"):
        return "concepto_dian"
    if nombre.startswith("resolucion"):
        return "resolucion"
    return "otro"


def _fuente_desde_url(url: str, tipo_norma: str, numero_articulo: str | None) -> str:
    nombre = urlparse(url).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if tipo_norma == "articulo_et":
        base = "Estatuto Tributario"
    else:
        m = re.match(r"(ley|decreto|resolucion|concepto)_(\d+)_(\d+)", nombre)
        if m:
            tipo, numero, anio = m.groups()
            base = f"{tipo.capitalize()} {numero} de {anio}"
        else:
            base = nombre.replace("_", " ").strip().capitalize()
    if numero_articulo:
        return f"{base}, artículo {numero_articulo}"
    return base


def _extraer_articulos(texto_completo: str) -> list[tuple[str | None, str]]:
    """Divide el texto de un documento en (numero_articulo, texto) por artículo.

    Si no se encuentra ningún encabezado de artículo, devuelve el documento
    completo como un solo fragmento con numero_articulo=None (ej. para
    documentos cortos como conceptos o resoluciones sin articulado).
    """
    matches = list(ARTICULO_HEADER_RE.finditer(texto_completo))
    if not matches:
        return [(None, texto_completo.strip())]

    fragmentos: list[tuple[str | None, str]] = []
    for i, m in enumerate(matches):
        inicio = m.start()
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(texto_completo)
        numero = m.group(1).rstrip(".")
        fragmentos.append((numero, texto_completo[inicio:fin].strip()))
    return fragmentos


def _estado_y_nota_vigencia(texto_articulo: str) -> tuple[str, str | None]:
    m = VIGENCIA_RE.search(texto_articulo[:400])
    if not m:
        return "vigente", None
    nota = m.group(0).strip("() ")
    palabra = m.group(1).lower()
    if palabra.startswith("derogad"):
        return "derogado", nota
    return "modificado", nota


def _localizar_icono_ver_mas(seccion_heading):
    """Sube por los ancestros del encabezado de sección hasta encontrar el
    ícono "Ver Más" (una <img alt="Ver Más">, no un nodo de texto) más
    cercano, y lo devuelve.

    Camina nivel por nivel en vez de fijar una profundidad concreta porque
    no se pudo verificar en vivo si el ícono es hermano directo del
    encabezado o cuelga de un ancestro un poco más arriba.
    """
    for nivel in range(1, 6):
        contenedor = seccion_heading.locator(f"xpath=ancestor::*[{nivel}]")
        icono = contenedor.get_by_alt_text(VER_MAS_ALT_RE)
        if icono.count() >= 1:
            return icono.first
    return None


def _enlaces_documento_en_pagina(page) -> dict[str, str]:
    """Devuelve {href: texto_visible} de todos los <a href*=".htm"> de TODA
    la página, sin acotar a ningún contenedor — confirmado con capturas de
    pantalla que el clic en "Ver Más" sí expande la sección visualmente,
    pero los enlaces resultantes no quedan anidados dentro de ningún
    ancestro cercano al encabezado/ícono."""
    enlaces = page.locator('a[href*=".htm"]')
    resultado: dict[str, str] = {}
    for i in range(enlaces.count()):
        el = enlaces.nth(i)
        href = el.get_attribute("href")
        if href:
            resultado.setdefault(href, (el.inner_text() or "").strip())
    return resultado


def descubrir_urls_seccion(
    seccion_titulo: str,
    limite: int | None = None,
    directorio_capturas: str | None = None,
) -> list[DocumentoDescubierto]:
    """Usa Playwright para expandir "Ver Más" en una sección del índice
    tributario y devolver las URLs de documentos individuales encontradas.

    Compara los enlaces a documentos (`a[href*=".htm"]`) de toda la página
    antes y después del clic, y se queda con los que aparecen nuevos — en
    vez de buscar dentro de un contenedor cercano al encabezado/ícono,
    porque se confirmó (con capturas de un run anterior) que el clic sí
    expande la sección visualmente pero los enlaces resultantes no quedan
    anidados ahí.

    Si se pasa `directorio_capturas`, guarda capturas de pantalla antes y
    después del clic (diagnóstico visual adicional).
    """
    documentos: list[DocumentoDescubierto] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.set_default_timeout(20000)
        page.goto(INDEX_URL, wait_until="domcontentloaded")

        seccion_heading = page.get_by_text(seccion_titulo, exact=False).first
        seccion_heading.wait_for(state="visible")

        if directorio_capturas:
            page.screenshot(
                path=f"{directorio_capturas}/01_antes_del_clic.png", full_page=True
            )

        enlaces_antes = _enlaces_documento_en_pagina(page)

        icono = _localizar_icono_ver_mas(seccion_heading)
        if icono is not None:
            logger.info("Ícono 'Ver Más' localizado para %r, haciendo clic...", seccion_titulo)
            icono.click()
            logger.info("Clic ejecutado sin excepción.")
        else:
            logger.warning(
                "No se encontró el ícono 'Ver Más' cerca del encabezado de "
                "la sección %r tras revisar 5 niveles de ancestros; puede "
                "que ya esté expandida o que la estructura real difiera "
                "más de lo esperado.",
                seccion_titulo,
            )

        # Sondea la página completa hasta 8s esperando que aparezcan
        # enlaces nuevos (en vez de un contenedor o un sleep fijo).
        deadline = time.time() + 8
        enlaces_nuevos: dict[str, str] = {}
        while time.time() < deadline:
            enlaces_actuales = _enlaces_documento_en_pagina(page)
            enlaces_nuevos = {
                href: texto
                for href, texto in enlaces_actuales.items()
                if href not in enlaces_antes
            }
            if enlaces_nuevos:
                break
            page.wait_for_timeout(300)

        if not enlaces_nuevos:
            logger.warning(
                "No aparecieron enlaces nuevos en toda la página tras el "
                "clic (8s de espera)."
            )
        else:
            logger.info("Aparecieron %d enlaces nuevos tras el clic.", len(enlaces_nuevos))

        if directorio_capturas:
            page.screenshot(
                path=f"{directorio_capturas}/02_despues_del_clic.png", full_page=True
            )

        for href, titulo in enlaces_nuevos.items():
            if href.startswith("#"):
                continue
            url_absoluta = urljoin(INDEX_URL, href)
            if url_absoluta not in {d.url for d in documentos}:
                documentos.append(DocumentoDescubierto(url=url_absoluta, titulo=titulo))
            if limite and len(documentos) >= limite:
                break

        browser.close()

    logger.info(
        "Descubiertos %d documentos en la sección %r", len(documentos), seccion_titulo
    )
    return documentos


def descubrir_enlaces_cruzados(html: str, base_url: str) -> list[str]:
    """Extrae URLs de otras normas referenciadas dentro de un documento ya
    descargado (ej. ley_2068_2020.htm citada desde el Estatuto Tributario)."""
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") or href.startswith("mailto:"):
            continue
        url_absoluta = urljoin(base_url, href).split("#")[0]
        parsed = urlparse(url_absoluta)
        if parsed.netloc != DOMINIO:
            continue
        if DOC_LINK_RE.search(parsed.path):
            urls.add(url_absoluta)
    return sorted(urls)


def descargar_html(url: str) -> str:
    resp = requests.get(url.split("#")[0], headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def _texto_plano(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup.get_text("\n")


def _norma_existe(db: Session, url_fuente: str) -> bool:
    return db.query(Norma).filter(Norma.url_fuente == url_fuente).first() is not None


def limpiar_numeros_articulo_truncados(db: Session) -> int:
    """Borra normas cuyo numero_articulo quedó truncado con un guión al
    final (ej. "631-" en vez de "631-1") por el bug de ARTICULO_HEADER_RE
    anterior a la corrección: la clase de caracteres del sufijo no incluía
    dígitos, así que "631-1", "631-2"... "631-6" colapsaban todos en
    numero_articulo="631-" y solo el primero se insertaba (los demás se
    descartaban como duplicados de esa misma URL truncada).

    Un numero_articulo real nunca termina en guión con el regex corregido,
    así que "termina en '-'" es una señal segura de este bug específico.
    Devuelve cuántas filas borró."""
    borrados = (
        db.query(Norma)
        .filter(Norma.numero_articulo.like("%-"))
        .delete(synchronize_session=False)
    )
    db.commit()
    return borrados


def ingestar_documento(db: Session, url: str) -> int:
    """Descarga, parsea e inserta los fragmentos (artículos) de un
    documento. Devuelve cuántos fragmentos nuevos insertó (0 si ya
    existían todos, para que el scraper sea seguro de re-ejecutar)."""
    html = descargar_html(url)
    texto_completo = _texto_plano(html)
    tipo_norma = _tipo_norma_desde_url(url)
    fragmentos = _extraer_articulos(texto_completo)

    insertados = 0
    for numero_articulo, texto in fragmentos:
        if not texto or len(texto) < 20:
            continue

        url_base = url.split("#")[0]
        url_fuente = f"{url_base}#{numero_articulo}" if numero_articulo else url_base
        if _norma_existe(db, url_fuente):
            logger.info("Ya existe, se omite: %s", url_fuente)
            continue

        estado_vigencia, nota_vigencia = _estado_y_nota_vigencia(texto)
        fuente = _fuente_desde_url(url, tipo_norma, numero_articulo)
        embedding = embed_document(texto)

        norma = Norma(
            tipo_norma=tipo_norma,
            numero_articulo=numero_articulo,
            fuente=fuente,
            url_fuente=url_fuente,
            texto=texto,
            estado_vigencia=estado_vigencia,
            nota_vigencia=nota_vigencia,
            embedding=embedding,
        )
        db.add(norma)
        db.commit()
        insertados += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    return insertados


def scrapear_seccion(
    db: Session,
    seccion_titulo: str,
    limite_documentos: int | None = None,
    seguir_enlaces_cruzados: bool = False,
    directorio_capturas: str | None = None,
) -> dict:
    """Punto de entrada: descubre documentos de una sección del índice
    tributario, los ingiere, y opcionalmente sigue sus enlaces cruzados
    como fuente adicional de descubrimiento (sin depender del buscador
    propio del sitio)."""
    resumen: dict = {
        "seccion": seccion_titulo,
        "documentos_encontrados_en_indice": 0,
        "documentos_procesados": 0,
        "fragmentos_insertados": 0,
        "errores": [],
    }

    documentos = descubrir_urls_seccion(
        seccion_titulo, limite=limite_documentos, directorio_capturas=directorio_capturas
    )
    resumen["documentos_encontrados_en_indice"] = len(documentos)

    vistos = {d.url for d in documentos}
    pendientes = list(documentos)

    while pendientes:
        doc = pendientes.pop(0)
        try:
            insertados = ingestar_documento(db, doc.url)
            resumen["documentos_procesados"] += 1
            resumen["fragmentos_insertados"] += insertados
            logger.info("Procesado %s: %d fragmentos insertados", doc.url, insertados)

            if seguir_enlaces_cruzados:
                html = descargar_html(doc.url)
                for nueva_url in descubrir_enlaces_cruzados(html, doc.url):
                    if nueva_url not in vistos:
                        vistos.add(nueva_url)
                        pendientes.append(DocumentoDescubierto(url=nueva_url))
        except Exception as exc:
            # Un documento roto o con estructura inesperada no debe tumbar
            # el resto del batch.
            logger.exception("Error procesando %s", doc.url)
            resumen["errores"].append(f"{doc.url}: {exc}")

        time.sleep(REQUEST_DELAY_SECONDS)

    return resumen
