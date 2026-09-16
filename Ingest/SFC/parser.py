"""
Parser para el catálogo jurídico (ABCD / CDS-ISIS) de la Superintendencia
Financiera de Colombia.

VALIDADO contra HTML crudo real (página 1 y última página de las tres
colecciones: ac, af, aj) el 2026-09-16. Confirmado:
  - Los NOMBRES DE CAMPO en español y su estructura en celdas <td> dentro
    de una <table> por registro, tal como asume `_parse_bloque`.
  - Los tres rótulos en negrilla de TIPO_POR_ROTULO aparecen tal cual y
    cada uno inicia el bloque <table> de su registro.
  - El campo "numero_documento" usa una ETIQUETA DE CAMPO DISTINTA por
    colección: "Concepto:" (ac), "Fallo:" (af), "Sentencia:" (aj) — las
    tres deben mapearse al mismo campo normalizado.
  - El FORMATO DE VALOR de ese campo varía por colección:
      ac: "2020311455 - 001 del 5 de febrero de 2021"      (" del " + fecha)
      aj: "C-083 del 27 de febrero de 2019"                (" del " + fecha,
           igual que ac, salvo que algunos registros no traen número:
           "del 12 de febrero de 2019")
      af: "2017-1900 de Enero 23 de 2020"                  (" de " + mes en
           español, SIN "del" — formato distinto, ver `_split_numero_y_fecha`)
  - Campo adicional confirmado y antes no mapeado: "Otros autores:" (lista
    de magistrados ponentes, sobre todo en aj) -> `otros_autores`.

Tipos de documento detectados por el rótulo en negrilla que antecede cada
registro:
  - "DOCTRINA Y CONCEPTOS"        -> tipo_documento = "concepto"
  - "FALLO FUNCIONES JURISDICCIONALES" -> tipo_documento = "fallo"
  - "JURISPRUDENCIA FINANCIERA"   -> tipo_documento = "jurisprudencia"
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
    "Sentencia:": "numero_documento",
    "Expediente/Radicado:": "expediente_radicado",
    "Autor Corporativo:": "autor_corporativo",
    "Título de la norma:": "titulo",
    "Documento fuente:": "documento_fuente",
    "Resumen:": "resumen",
    "Notas:": "notas",
    "Temas/Materias:": "materias",  # se procesa aparte (lista)
    "Otros autores:": "otros_autores",  # se procesa aparte (lista)
    "Otras formas físicas:": "otras_formas_fisicas",
    "Acceso web (URL):": "acceso_web",  # se procesa aparte (url + tipo_archivo)
}

_MESES = (
    "Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre"
    "|Octubre|Noviembre|Diciembre"
)
# af: "2017-1900 de Enero 23 de 2020" (mes en español, sin "del").
_RE_NUMERO_DE_MES = re.compile(
    rf"(.+?)\s+de\s+((?:{_MESES})\s+\d{{1,2}}\s+de\s+\d{{4}})", re.IGNORECASE
)
# ac/aj: "2020311455 - 001 del 5 de febrero de 2021".
_RE_NUMERO_DEL_FECHA = re.compile(r"(.+?)\s+del\s+(.+)")
# aj (algunos registros sin número): "del 12 de febrero de 2019".
_RE_SOLO_FECHA = re.compile(r"^del\s+(.+)", re.IGNORECASE)


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
    otros_autores: list[str] = field(default_factory=list)
    url_archivo: Optional[str] = None
    tipo_archivo: Optional[str] = None  # "texto" | "audio" | None
    tiene_texto_completo: bool = False
    texto_completo: Optional[str] = None  # se llena en un paso posterior
    # Por qué tiene_texto_completo es False, para no confundir "sin texto por
    # diseño" (audio, o el registro no trae ningún archivo) con "sin texto
    # por fallo de extracción" (se intentó y no se pudo). None cuando
    # tiene_texto_completo es True. Ver scraper.py:raspar_coleccion, que es
    # quien resuelve el valor final para tipo_archivo == "texto" después de
    # intentar la descarga/extracción real.
    motivo_sin_texto: Optional[str] = None


def _split_numero_y_fecha(valor: str) -> tuple[Optional[str], Optional[str]]:
    """Separa número de documento y fecha textual. El formato varía por
    colección (ver notas de validación al inicio del módulo):
      - 'del 12 de febrero de 2019' (aj, sin número)  -> (None, fecha)
      - '2017-1900 de Enero 23 de 2020' (af)           -> (numero, fecha)
      - '2020311455 - 001 del 5 de febrero de 2021' (ac/aj) -> (numero, fecha)
    """
    valor = valor.strip()

    m = _RE_SOLO_FECHA.match(valor)
    if m:
        return None, m.group(1).strip()

    m = _RE_NUMERO_DE_MES.match(valor)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    m = _RE_NUMERO_DEL_FECHA.match(valor)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    return valor, None


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
            elif campo in ("materias", "otros_autores"):
                valores = [
                    a.get_text(strip=True) for a in valor_celda.find_all("a")
                ] or [valor_texto]
                setattr(registro, campo, valores)
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

    # Solo se resuelve aquí lo que ya se sabe sin descargar nada. El caso
    # tipo_archivo == "texto" queda pendiente (tiene_texto_completo sigue en
    # False, motivo_sin_texto en None) hasta que scraper.py intente
    # realmente la descarga/extracción y sepa el desenlace real.
    if registro.tipo_archivo == "audio":
        registro.motivo_sin_texto = "audio"
    elif registro.tipo_archivo != "texto":
        registro.motivo_sin_texto = "sin_archivo"
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
        if r.otros_autores:
            print(f"otros_autores: {r.otros_autores}")
        print(f"archivo: {r.tipo_archivo} -> {r.url_archivo}")
        if r.notas:
            print(f"notas: {r.notas}")
