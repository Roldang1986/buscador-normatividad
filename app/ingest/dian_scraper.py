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
  no un nodo de texto "Ver Más".
- Confirmado con un dump real del DOM (antes/después del clic, analizado
  con scripts/diagnosticar_dom.py sobre un run real) que el contenedor
  que aísla exactamente la sección es el ancestro más cercano al
  encabezado con clase "opcion-nueva": antes del clic tiene 0 enlaces a
  documentos dentro, y después del clic tiene exactamente los enlaces
  revelados por esa sección (mismo conteo que el total de enlaces nuevos
  de toda la página en la prueba real), incluido el enlace al documento
  compilado del Estatuto Tributario — que antes de esa prueba se perdía
  porque solo aparece tras el clic (no es que exista desde antes y el
  diff de "solo lo nuevo" lo excluyera). Los ancestros más cercanos
  (título de la sección y su envoltorio inmediato) NO sirven como
  contenedor: se quedan en 0 enlaces incluso después del clic, porque el
  contenido revelado es hermano del título, no descendiente de un
  ancestro más próximo.
- Los documentos individuales son HTML plano, con enlaces cruzados a
  otras normas por nombre de archivo (ej. ley_2068_2020.htm,
  decreto_1742_2020.htm) y anclas a artículos específicos
  (ej. estatuto_tributario.htm#420).
"""

from __future__ import annotations

import logging
import pathlib
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

# AJUSTAR: el usuario confirmó que el índice muestra un ÍCONO ROJO junto a
# cada norma derogada, pero no se pudo verificar en vivo el atributo
# exacto (alt/title/src/clase) que usa ese ícono — esta es una heurística
# por palabras clave sobre alt/title/src/class de cualquier <img> cercana
# al enlace, pensada para validarse comparando contra el estado inferido
# del texto de cada artículo (ver ingestar_documento).
DEROGADO_ICON_RE = re.compile(r"derogad|no\s*vigente", re.IGNORECASE)

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
    # Señal del ícono del índice: True si parece marcado como derogado,
    # False si hay un ícono pero no indica derogado, None si no se pudo
    # determinar (ningún ícono cercano al enlace). Es a nivel de
    # DOCUMENTO completo (la fila del índice), no por artículo individual
    # — ver la nota en ingestar_documento sobre esa limitación.
    indice_marca_derogado: bool | None = None


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


def _detectar_marca_derogado(elemento_enlace) -> bool | None:
    """Busca, dentro del elemento padre del enlace, algún <img> cuyo
    alt/title/src/class sugiera el ícono rojo de "derogado" del índice.

    Devuelve True si encuentra un ícono que matchea DEROGADO_ICON_RE,
    False si encuentra algún ícono pero ninguno matchea (otro estado, ej.
    vigente), o None si no hay ningún ícono cerca del enlace (señal no
    disponible — no se debe interpretar como "vigente")."""
    padre = elemento_enlace.locator("xpath=..")
    iconos = padre.locator("img")
    total = iconos.count()
    if total == 0:
        return None
    for i in range(total):
        icono = iconos.nth(i)
        atributos = " ".join(
            filter(
                None,
                [
                    icono.get_attribute("alt"),
                    icono.get_attribute("title"),
                    icono.get_attribute("src"),
                    icono.get_attribute("class"),
                ],
            )
        )
        if DEROGADO_ICON_RE.search(atributos):
            return True
    return False


def _localizar_contenedor_opcion(seccion_heading):
    """Ancestro más cercano al encabezado de sección con clase
    "opcion-nueva". Confirmado con un dump real del DOM (ver
    scripts/diagnosticar_dom.py) que es el contenedor que aísla
    exactamente la sección: 0 enlaces a documentos antes del clic en
    "Ver Más", y solo los revelados por esa sección después — a
    diferencia de los ancestros más cercanos (título, envoltorio
    inmediato), que se quedan en 0 siempre porque el contenido revelado
    es hermano del título, no descendiente suyo.

    Devuelve None si no se encuentra (ej. estructura distinta en otra
    sección), para que la llamada pueda decidir un fallback en vez de
    fallar en seco."""
    contenedor = seccion_heading.locator(
        "xpath=ancestor::div["
        "contains(concat(' ', normalize-space(@class), ' '), ' opcion-nueva ')"
        "][last()]"
    )
    if contenedor.count() == 0:
        return None
    return contenedor.first


def _enlaces_documento_en_pagina(alcance) -> dict[str, dict]:
    """Devuelve {href: {"titulo": str, "indice_marca_derogado": bool|None}}
    de los <a href*=".htm"> dentro de `alcance` (un Locator de Playwright:
    la página completa, o un contenedor ya acotado a la sección vía
    _localizar_contenedor_opcion)."""
    enlaces = alcance.locator('a[href*=".htm"]')
    resultado: dict[str, dict] = {}
    for i in range(enlaces.count()):
        el = enlaces.nth(i)
        href = el.get_attribute("href")
        if href and href not in resultado:
            resultado[href] = {
                "titulo": (el.inner_text() or "").strip(),
                "indice_marca_derogado": _detectar_marca_derogado(el),
            }
    return resultado


def descubrir_urls_seccion(
    seccion_titulo: str,
    limite: int | None = None,
    directorio_capturas: str | None = None,
) -> list[DocumentoDescubierto]:
    """Usa Playwright para expandir "Ver Más" en una sección del índice
    tributario y devolver las URLs de documentos individuales encontradas.

    Compara los enlaces a documentos (`a[href*=".htm"]`) antes y después
    del clic, acotados al contenedor "opcion-nueva" ancestro del
    encabezado de sección (ver _localizar_contenedor_opcion) — confirmado
    con un dump real del DOM que ese contenedor aísla exactamente la
    sección, sin mezclar enlaces de otras partes del índice. Si por algún
    motivo no se encuentra ese contenedor (ej. estructura distinta en
    otra sección no probada aún), cae de vuelta a comparar toda la
    página y deja constancia con un warning — degradado pero no roto.

    Si se pasa `directorio_capturas`, guarda capturas de pantalla Y el HTML
    completo del DOM (antes/después del clic) — el HTML es lo que permite
    diseñar un selector de aislamiento con evidencia real en vez de
    adivinar, que es más útil que la captura visual para eso.
    """
    documentos: list[DocumentoDescubierto] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.set_default_timeout(20000)
        page.goto(INDEX_URL, wait_until="domcontentloaded")

        seccion_heading = page.get_by_text(seccion_titulo, exact=False).first
        seccion_heading.wait_for(state="visible")

        contenedor = _localizar_contenedor_opcion(seccion_heading)
        if contenedor is not None:
            alcance = contenedor
        else:
            logger.warning(
                "No se encontró el contenedor 'opcion-nueva' ancestro del "
                "encabezado de la sección %r; usando toda la página como "
                "alcance (menos preciso, puede mezclar enlaces de otras "
                "secciones).",
                seccion_titulo,
            )
            alcance = page

        if directorio_capturas:
            page.screenshot(
                path=f"{directorio_capturas}/01_antes_del_clic.png", full_page=True
            )
            pathlib.Path(f"{directorio_capturas}/01_antes_del_clic.html").write_text(
                page.content(), encoding="utf-8"
            )

        enlaces_antes = _enlaces_documento_en_pagina(alcance)

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

        # Sondea el contenedor (o la página, en el fallback) hasta 8s
        # esperando enlaces nuevos, y espera a que el CONTEO se estabilice
        # en dos sondeos consecutivos antes de aceptarlo como definitivo.
        # No basta con romper apenas aparece el primer enlace nuevo: en un
        # run real (limite=100) esa versión anterior capturó solo 2
        # enlaces nuevos en el momento en que rompió el loop, mientras que
        # el HTML volcado después (sin esa carrera) mostraba 212 enlaces
        # nuevos ya renderizados en el contenedor — es decir, la condición
        # de carrera capturaba una foto a medio renderizar del árbol de
        # documentos, lo que explica por qué el conjunto de documentos
        # encontrados variaba de forma no determinista entre corridas.
        deadline = time.time() + 8
        enlaces_nuevos: dict[str, dict] = {}
        conteo_anterior = -1
        while time.time() < deadline:
            enlaces_actuales = _enlaces_documento_en_pagina(alcance)
            enlaces_nuevos = {
                href: info
                for href, info in enlaces_actuales.items()
                if href not in enlaces_antes
            }
            if enlaces_nuevos and len(enlaces_nuevos) == conteo_anterior:
                break
            conteo_anterior = len(enlaces_nuevos)
            page.wait_for_timeout(300)

        if not enlaces_nuevos:
            logger.warning(
                "No aparecieron enlaces nuevos en el alcance acotado tras "
                "el clic (8s de espera)."
            )
        else:
            logger.info("Aparecieron %d enlaces nuevos tras el clic.", len(enlaces_nuevos))

        if directorio_capturas:
            page.screenshot(
                path=f"{directorio_capturas}/02_despues_del_clic.png", full_page=True
            )
            pathlib.Path(f"{directorio_capturas}/02_despues_del_clic.html").write_text(
                page.content(), encoding="utf-8"
            )

        for href, info in enlaces_nuevos.items():
            if href.startswith("#"):
                continue
            url_absoluta = urljoin(INDEX_URL, href)
            if url_absoluta not in {d.url for d in documentos}:
                documentos.append(
                    DocumentoDescubierto(
                        url=url_absoluta,
                        titulo=info["titulo"],
                        indice_marca_derogado=info["indice_marca_derogado"],
                    )
                )
            if limite and len(documentos) >= limite:
                break

        browser.close()

    logger.info(
        "Descubiertos %d documentos en la sección %r", len(documentos), seccion_titulo
    )
    logger.info(
        "Detección de ícono de vigencia en el índice: %s",
        contar_marca_derogado(documentos),
    )
    return documentos


def contar_marca_derogado(documentos: list[DocumentoDescubierto]) -> dict:
    """Cuenta cuántos documentos descubiertos tienen indice_marca_derogado
    en True/False/None. Existe para poder distinguir "el heurístico del
    ícono corrió y no encontró desacuerdos" de "el heurístico nunca
    encuentra ningún ícono" (ambos casos, sin este conteo, se ven iguales:
    0 advertencias)."""
    conteo = {"true": 0, "false": 0, "none": 0}
    for doc in documentos:
        if doc.indice_marca_derogado is True:
            conteo["true"] += 1
        elif doc.indice_marca_derogado is False:
            conteo["false"] += 1
        else:
            conteo["none"] += 1
    return conteo


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


def verificar_numeracion_articulos(db: Session) -> dict:
    """Diagnóstico puntual post-corrección de ARTICULO_HEADER_RE:

    - truncados_restantes: filas con numero_articulo terminado en guión
      (debería ser 0; si no lo es, algo sigue sin corregirse).
    - articulos_631: lista los numero_articulo que empiezan con "631-",
      para confirmar directamente que 631-1..631-6 quedaron como
      registros distintos en vez de colapsados en uno solo.
    - con_letras_no_ordinales: numero_articulo que contienen alguna letra
      fuera del sufijo ordinal esperado ("...o", ej. "5o", "631-1o" no
      existe pero "5o" sí) — para detectar patrones de numeración no
      cubiertos por el regex actual (ej. sufijos de letra tipo "20A").
    """
    truncados = db.query(Norma).filter(Norma.numero_articulo.like("%-")).count()

    articulos_631 = [
        n.numero_articulo
        for n in db.query(Norma)
        .filter(Norma.numero_articulo.like("631-%"))
        .order_by(Norma.numero_articulo)
        .all()
    ]

    con_letras_no_ordinales = [
        n.numero_articulo
        for n in db.query(Norma)
        .filter(Norma.numero_articulo.op("~")("[A-Za-zÀ-ÿ]"))
        .filter(~Norma.numero_articulo.op("~")(r"^[0-9]+(-[0-9]+)*o$"))
        .order_by(Norma.numero_articulo)
        .all()
    ]

    return {
        "truncados_restantes": truncados,
        "articulos_631": articulos_631,
        "numero_articulo_con_letras_no_ordinales": con_letras_no_ordinales,
    }


def ingestar_documento(
    db: Session, url: str, indice_marca_derogado: bool | None = None
) -> tuple[int, list[str]]:
    """Descarga, parsea e inserta los fragmentos (artículos) de un
    documento. Devuelve (insertados, advertencias):
    - insertados: cuántos fragmentos nuevos insertó (0 si ya existían
      todos, para que el scraper sea seguro de re-ejecutar).
    - advertencias: mensajes cuando `indice_marca_derogado` (señal del
      ícono del índice, a nivel de documento completo) no coincide con
      el estado_vigencia inferido del texto de un artículo. Es solo una
      verificación cruzada: nunca sobrescribe estado_vigencia, que sigue
      viniendo del texto.

    LIMITACIÓN CONOCIDA: `indice_marca_derogado` es una señal por
    DOCUMENTO (la fila del índice), no por artículo. Para documentos
    atómicos (una ley/decreto corto) documento y artículo casi siempre
    coinciden. Para un documento consolidado grande como el Estatuto
    Tributario (un solo ícono para todo el documento, que en sí mismo
    nunca está "derogado"), comparar ese único valor contra cada uno de
    sus ~1000+ artículos —muchos legítimamente derogados/modificados en
    el texto— generará muchas advertencias esperables, no indicativas de
    un bug. Revisar el volumen de advertencias con ese contexto."""
    html = descargar_html(url)
    texto_completo = _texto_plano(html)
    tipo_norma = _tipo_norma_desde_url(url)
    fragmentos = _extraer_articulos(texto_completo)

    insertados = 0
    advertencias: list[str] = []
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

        if indice_marca_derogado is not None:
            texto_dice_derogado = estado_vigencia == "derogado"
            if texto_dice_derogado != indice_marca_derogado:
                advertencias.append(
                    f"{url_fuente}: el índice marca "
                    f"{'derogado' if indice_marca_derogado else 'no derogado'} "
                    f"pero el texto sugiere estado_vigencia={estado_vigencia!r} "
                    "— revisar manualmente."
                )

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

    return insertados, advertencias


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
        "advertencias_vigencia_indice_vs_texto": [],
    }

    documentos = descubrir_urls_seccion(
        seccion_titulo, limite=limite_documentos, directorio_capturas=directorio_capturas
    )
    resumen["documentos_encontrados_en_indice"] = len(documentos)
    resumen["deteccion_icono_vigencia_indice"] = contar_marca_derogado(documentos)

    vistos = {d.url for d in documentos}
    pendientes = list(documentos)

    while pendientes:
        doc = pendientes.pop(0)
        try:
            insertados, advertencias = ingestar_documento(
                db, doc.url, indice_marca_derogado=doc.indice_marca_derogado
            )
            resumen["documentos_procesados"] += 1
            resumen["fragmentos_insertados"] += insertados
            resumen["advertencias_vigencia_indice_vs_texto"].extend(advertencias)
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
