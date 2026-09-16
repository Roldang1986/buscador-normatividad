"""
Parser para el catálogo jurídico (ABCD / CDS-ISIS) de la Superintendencia
Financiera de Colombia.

IMPORTANTE — qué está validado y qué no:
  - Los NOMBRES DE CAMPO en español ("Concepto:", "Fallo:", "Resumen:",
    "Temas/Materias:", etc.) fueron observados directamente en páginas
    reales del sitio (fetches hechos a mano contra buscar_integrada.php).
    Son confiables.
  - La ESTRUCTURA EXACTA DE ETIQUETAS HTML (qué es <table>, qué clase CSS,
    anidamiento) NO fue verificada contra el HTML crudo — solo vimos una
    extracción a Markdown. Por eso este parser busca las etiquetas de campo
    como texto dentro de cualquier celda, en vez de depender de selectores
    CSS específicos. Es más robusto a esa incertidumbre, pero de todas
    formas corre `validar_muestra()` contra un HTML real antes de lanzar
    el scraper completo.

Tipos de documento detectados por el rótulo en negrilla que antecede cada
registro:
  - "DOCTRINA Y CONCEPTOS"        -> tipo_documento = "concepto"
  - "FALLO FUNCIONES JURISDICCIONALES" -> tipo_documento = "fallo"
  - "JURISPRUDENCIA FINANCIERA" (o similar; AÚN NO CONFIRMADO en una
    muestra real) -> tipo_documento = "jurisprudencia"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, Tag

TIPO_POR_ROTULO = {
    "DOCTRINA Y CONCEPTOS": "concepto",
    "FALLO FUNCIONES JURISDICCIONALES": "fallo",
    "JURISPRUDENCIA FINANCIERA": "jurisprudencia",
}

# Etiquetas de campo observadas realmente en el sitio. El valor es el nombre
# normalizado que usamos en el registro resultante.
CAMPOS_CONOCIDOS = {
    "Concepto:": "numero_documento",
    "Fallo:": "numero_documento",
    "Expediente/Radicado:": "expediente_radicado",
    "Autor Corporativo:": "autor_corporativo",
    "Título de la norma:": "titulo",
    "Documento fuente:": "documento_fuente",
    "Resumen:": "resumen",
    "Notas:": "notas",
    "Temas/Materias:": "materias",  # se procesa aparte (lista)
    "Otras formas físicas:": "otras_formas_fisicas",
    "Acceso web (URL):": "acceso_web",  # se procesa aparte (url + tipo_archivo)
}


@dataclass
class RegistroSFC:
    tipo_documento: str  # concepto | fallo | jurisprudencia
    numero_documento: Optional[str] = None
    fecha_texto: Optional[str] = None  # tal como aparece, ej. "5 de febrero de 2021"
    expediente_radicado: Optional[str] = None
    autor_corporativo: Optional[str] = None
    titulo: Optional[str] = None
    documento_fuente: Optional[str] = None
    resumen: Optional[str] = None
    notas: Optional[str] = None
    materias: list[str] = field(default_factory=list)
    url_archivo: Optional[str] = None
    tipo_archivo: Optional[str] = None  # "texto" | "audio" | None
    tiene_texto_completo: bool = False
    texto_completo: Optional[str] = None  # se llena en un paso posterior


def _split_numero_y_fecha(valor: str) -> tuple[Optional[str], Optional[str]]:
    """'2020311455 - 001 del 5 de febrero de 2021' -> (numero, fecha)."""
    m = re.match(r"(.+?)\s+del\s+(.+)", valor.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return valor.strip(), None


def _parse_bloque(tipo_documento: str, tabla: Tag) -> RegistroSFC:
    registro = RegistroSFC(tipo_documento=tipo_documento)
    celdas = tabla.find_all(["td", "th"])

    i = 0
    while i < len(celdas):
        texto_celda = celdas[i].get_text(strip=True)
        if texto_celda in CAMPOS_CONOCIDOS and i + 1 < len(celdas):
            campo = CAMPOS_CONOCIDOS[texto_celda]
            valor_celda = celdas[i + 1]
            valor_texto = valor_celda.get_text(" ", strip=True)

            if campo == "numero_documento":
                numero, fecha = _split_numero_y_fecha(valor_texto)
                registro.numero_documento = numero
                registro.fecha_texto = fecha
            elif campo == "materias":
                registro.materias = [
                    a.get_text(strip=True) for a in valor_celda.find_all("a")
                ] or [valor_texto]
            elif campo == "acceso_web":
                enlace = valor_celda.find("a")
                if enlace and enlace.get("href"):
                    registro.url_archivo = enlace["href"]
                    etiqueta = enlace.get_text(strip=True).lower()
                    if "audio" in etiqueta:
                        registro.tipo_archivo = "audio"
                    elif "texto" in etiqueta:
                        registro.tipo_archivo = "texto"
            else:
                setattr(registro, campo, valor_texto)
            i += 2
        else:
            i += 1

    registro.tiene_texto_completo = registro.tipo_archivo == "texto"
    return registro


def parse_pagina_resultados(html: str) -> list[RegistroSFC]:
    """
    Recibe el HTML YA DECODIFICADO (ver nota de encoding en scraper.py) de
    una página de resultados de buscar_integrada.php y devuelve la lista
    de registros encontrados en ella.
    """
    soup = BeautifulSoup(html, "html.parser")
    registros: list[RegistroSFC] = []

    # Cada registro empieza con una celda en negrilla que contiene uno de
    # los rótulos de tipo. Buscamos esas celdas y tomamos la tabla que las
    # contiene como el "bloque" completo del registro.
    for negrilla in soup.find_all(["b", "strong"]):
        rotulo = negrilla.get_text(strip=True)
        if rotulo in TIPO_POR_ROTULO:
            tabla = negrilla.find_parent("table")
            if tabla is None:
                continue
            registros.append(_parse_bloque(TIPO_POR_ROTULO[rotulo], tabla))

    return registros


def validar_muestra(html: str) -> None:
    """
    Corre el parser sobre un HTML de muestra e imprime lo encontrado, sin
    tocar la base de datos. Úsalo primero contra 2-3 páginas reales de
    cada colección (ac, af, aj) antes de lanzar el scraper completo.
    """
    registros = parse_pagina_resultados(html)
    print(f"Registros encontrados: {len(registros)}")
    for r in registros[:5]:
        print("-" * 60)
        print(f"tipo: {r.tipo_documento} | numero: {r.numero_documento} | fecha: {r.fecha_texto}")
        print(f"titulo: {r.titulo}")
        print(f"materias: {r.materias}")
        print(f"archivo: {r.tipo_archivo} -> {r.url_archivo}")
        if r.notas:
            print(f"notas: {r.notas}")
