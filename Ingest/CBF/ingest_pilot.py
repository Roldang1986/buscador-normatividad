"""Ingesta real de la Circular Básica Financiera (CBF) — paso 4 del
pipeline (ver README.md). A diferencia de
prototipo_fragmentacion_numeral_cbf.py (solo reporte), este script SÍ
inserta en Neon (tabla normas_cbf): raspa las 4 Partes, descarga cada
archivo, fragmenta por numeral, embebe con Voyage e inserta.

Reglas ya decididas en schema.sql (ver README, "Resultado del dry-run" y
"Esquema"):
  - 'anexo_zip': se registra sin texto/embedding — un Anexo real es un
    .zip de plantillas/formatos, no texto narrativo.
  - 'reservado': capítulos con contenido placeholder (ej. "[ ] Espacio
    reservado", Parte 3 / Capítulo 3) se ingieren igual, marcados
    explícitamente, sin fragmentar por numeral y sin embedding (no hay
    nada que buscar semánticamente en un placeholder).
  - Parte 2 / Capítulo 9 (patrón de dos-versiones, único caso conocido
    hoy): la versión "futura" usa el texto ya verificado a mano en
    excepcion_p2c9_vigencia.json en vez de re-derivar
    scraper.separar_nota_futura en caliente en cada corrida — decisión
    explícita en schema.sql. Un tipo="version_futura" sin excepción
    conocida hace fallar la ingesta en vez de asumir el patrón general.
  - Ningún umbral de longitud fragmenta/recorta un numeral: las tablas
    largas embebidas (ver README, "fragmentos largos") se dejan íntegras
    dentro de su propio fragmento; el truncado de abajo solo acorta el
    INPUT del embedding, nunca la columna `texto`.

CÓMO CORRERLO:

    python ingest_pilot.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from sqlalchemy import text

from app.database import engine
from app.embeddings import embed_document

import scraper

# Límite de caracteres del texto dentro del input de embedding, mismo
# criterio que Ingest/SFC/ingest_pilot.py para no acercarse al límite de
# tokens de voyage-3.5 en un solo request. El fragmento más largo visto
# en el dry-run mide 14.514 caracteres (tabla embebida en P2.C7, ver
# README) — sin este truncado ese único fragmento arriesgaría el límite.
TRUNCADO_TEXTO_EMBEDDING = 12000

_RUTA_EXCEPCION_P2C9 = Path(__file__).resolve().parent / "excepcion_p2c9_vigencia.json"

# Un capítulo/sección "reservado" (ver README, Parte 3 / Capítulo 3) mide
# 158 caracteres reales en el sitio — el umbral deja margen amplio sin
# arriesgar confundir un capítulo corto pero real con un placeholder.
_UMBRAL_LONGITUD_RESERVADO = 500
_RE_RESERVADO = re.compile(r"espacio\s+reservado", re.IGNORECASE)

_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_RE_FECHA_ES = re.compile(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", re.IGNORECASE)


def _cargar_excepcion_version_futura() -> dict[tuple[int, int], dict]:
    """{(parte, numero_capitulo): version_futura_dict} para los
    capítulos con patrón de dos-versiones ya verificados a mano. Solo
    P2.C9 existe hoy (ver README) — deliberadamente no se generaliza:
    un tipo="version_futura" para cualquier otro (parte, capítulo) debe
    fallar fuerte en procesar_archivo, no re-derivarse en caliente."""
    datos = json.loads(_RUTA_EXCEPCION_P2C9.read_text())
    cap = datos["capitulo"]
    futura = next(v for v in datos["versiones"] if v["version"] == "futura")
    return {(cap["parte"], cap["numero_capitulo"]): futura}


EXCEPCIONES_VERSION_FUTURA = _cargar_excepcion_version_futura()

# Correcciones puntuales de numeral para errores reales de numeración del
# propio .docx fuente de la SFC — mismo patrón que
# Ingest/SFC/ingest_pilot.py:CORRECCIONES_NUMERO_DOCUMENTO (verificadas
# individualmente contra el contexto real del documento, no una
# heurística general). Sin esto, el índice único (parte, capítulo,
# sección, numeral, id_archivo_cbf, version) trata el numeral repetido
# como duplicado del primero y ON CONFLICT DO NOTHING lo descarta en
# silencio, perdiendo ese fragmento de texto.
#
# idFile=1081481 (Parte 3 / Capítulo 11 / Sección 2, "Fondos voluntarios
# de pensión"): "3.11.2.7." aparece DOS VECES como línea propia en el
# .docx. Secuencia real completa alrededor: ...2.6, 2.7, 2.8, 2.9,
# 2.7(repetido), 2.10... — un error de numeración real del documento
# fuente (confirmado 2026-09-22 descargando y revisando el .docx), pero
# a diferencia del caso análogo de Ingest/SFC (donde el número correcto
# era inequívoco por el registro vecino), acá NO hay un número real
# "correcto" que asignarle: 2.8 y 2.9 ya están tomados por sus propios
# numerales, así que la 2a ocurrencia de "2.7" no es una version mal
# tecleada de ningún otro numeral de la lista — es simplemente una
# repetición espuria del compilador. Se le da un sufijo sintético para
# desambiguar sin inventar un número que no está en el documento (mismo
# criterio que dian_scraper._resolver_numeros_duplicados para casos sin
# resolución inequívoca).
# Clave: (id_archivo_cbf, numeral tal como lo devuelve el parser,
# n-ésima ocurrencia dentro del archivo, 1-based).
CORRECCIONES_NUMERAL: dict[tuple[int, str, int], str] = {
    (1081481, "3.11.2.7", 2): "3.11.2.7-bis",
}


def _aplicar_correccion_numeral(
    id_archivo: int, fragmentos: list[tuple[str | None, str]]
) -> list[tuple[str | None, str]]:
    conteo: dict[str, int] = {}
    corregidos = []
    for etiqueta, texto_fragmento in fragmentos:
        if etiqueta is not None:
            conteo[etiqueta] = conteo.get(etiqueta, 0) + 1
            etiqueta = CORRECCIONES_NUMERAL.get((id_archivo, etiqueta, conteo[etiqueta]), etiqueta)
        corregidos.append((etiqueta, texto_fragmento))
    return corregidos


def _parsear_fecha_es(texto: str | None) -> date | None:
    if not texto:
        return None
    m = _RE_FECHA_ES.search(texto)
    if not m:
        return None
    dia, mes_txt, anio = m.groups()
    mes = _MESES_ES.get(mes_txt.lower())
    if mes is None:
        return None
    return date(int(anio), mes, int(dia))


def _es_reservado(texto: str) -> bool:
    return len(texto) < _UMBRAL_LONGITUD_RESERVADO and bool(_RE_RESERVADO.search(texto))


def _fragmentar_por_numeral(texto: str, prefijo: str) -> list[tuple[str | None, str]]:
    """Divide el texto de un capítulo/sección en (numeral, fragmento),
    replicando el criterio ya validado en
    prototipo_fragmentacion_numeral_cbf.py._numerales_y_fragmentos: un
    marcador de línea propia tipo "N.N.N[.N]" solo cuenta como numeral
    real si además empieza con el prefijo "{parte}.{capitulo}." del
    propio archivo — filtra tablas de taxonomía embebidas con su propia
    numeración interna que de otro modo se cuentan como numerales
    (bug real encontrado en el dry-run, ver README). Sin ningún numeral
    detectado, devuelve el texto completo como fragmento único
    (numeral=None) en vez de perder el contenido."""
    lineas = texto.split("\n")
    posiciones: list[tuple[int, str]] = []
    offset = 0
    for linea in lineas:
        l = linea.strip()
        if scraper._RE_NUMERAL_LINEA.match(l) and l.startswith(prefijo):
            posiciones.append((offset, l.rstrip(".")))
        offset += len(linea) + 1  # +1 por el "\n" que junta las líneas

    if not posiciones:
        return [(None, texto)]

    preambulo = texto[: posiciones[0][0]].strip()
    fragmentos: list[tuple[str | None, str]] = []
    for i, (pos, etiqueta) in enumerate(posiciones):
        fin = posiciones[i + 1][0] if i + 1 < len(posiciones) else len(texto)
        cuerpo = texto[pos:fin].strip()
        texto_fragmento = f"{preambulo}\n\n{cuerpo}" if preambulo else cuerpo
        fragmentos.append((etiqueta, texto_fragmento))
    return fragmentos


def _fuente_str(archivo: scraper.ArchivoCBF) -> str:
    partes = [f"Circular Básica Financiera Parte {archivo.parte}"]
    if archivo.numero_capitulo is not None:
        capitulo = f"Capítulo {archivo.numero_capitulo}"
        if archivo.nombre_capitulo:
            capitulo += f" ({archivo.nombre_capitulo})"
        partes.append(capitulo)
    elif archivo.titulo:
        partes.append(archivo.titulo)
    if archivo.seccion:
        partes.append(f"Sección: {archivo.seccion}")
    return " ".join(partes)


def _url_archivo(id_archivo: int) -> str:
    return (
        f"{scraper.URL_LOADER}?lServicio=Tools2&lTipo=descargas"
        f"&lFuncion=descargar&idFile={id_archivo}"
    )


def procesar_archivo(session: requests.Session, archivo: scraper.ArchivoCBF) -> list[dict]:
    """Devuelve una o más filas listas para insertar (sin `embedding`
    todavía — lo agrega el llamador solo para tipo_registro='articulo',
    ver ingestar()) para un ArchivoCBF. Un 'anexo' produce 1 fila
    tipo_registro='anexo_zip' sin descargar nada (es un .zip, no texto).
    Un capítulo/sección produce 1 fila 'reservado' (placeholder) o N
    filas 'articulo' (una por numeral fragmentado, o una sola si el
    capítulo no tiene numerales detectables)."""
    base = {
        "parte": archivo.parte,
        "nombre_parte": archivo.nombre_parte,
        "numero_capitulo": archivo.numero_capitulo,
        "nombre_capitulo": archivo.nombre_capitulo,
        "seccion": archivo.seccion,
        "id_archivo_cbf": archivo.id_archivo,
        "version": "futura" if archivo.tipo == "version_futura" else "vigente",
        "fuente": _fuente_str(archivo),
        "url_archivo": _url_archivo(archivo.id_archivo),
        "estado_vigencia": archivo.estado_vigencia,
        "fecha_vigencia_inicio": _parsear_fecha_es(archivo.fecha_vigencia_inicio),
        "fecha_vigencia_fin": None,
        "nota_vigencia": archivo.nota_vigencia,
    }

    if archivo.tipo == "anexo":
        return [{**base, "tipo_registro": "anexo_zip", "numeral": None, "texto": None}]

    if archivo.tipo == "version_futura":
        clave = (archivo.parte, archivo.numero_capitulo)
        excepcion = EXCEPCIONES_VERSION_FUTURA.get(clave)
        if excepcion is None:
            raise ValueError(
                f"tipo='version_futura' sin excepción verificada para "
                f"Parte {archivo.parte} / Capítulo {archivo.numero_capitulo} "
                f"(idFile={archivo.id_archivo}) — no se re-deriva en caliente "
                "(ver README, 'Investigado hasta ahora'). Verificar a mano y "
                "agregar un archivo de excepción antes de reintentar."
            )
        texto_completo = excepcion["texto"]
        # Fechas del JSON ya están en ISO (ver excepcion_p2c9_vigencia.json),
        # no en el formato "D de MES de YYYY" que parsea _parsear_fecha_es.
        base["fecha_vigencia_inicio"] = (
            date.fromisoformat(excepcion["fecha_vigencia_inicio"])
            if excepcion.get("fecha_vigencia_inicio")
            else None
        )
        base["fecha_vigencia_fin"] = (
            date.fromisoformat(excepcion["fecha_vigencia_fin"])
            if excepcion.get("fecha_vigencia_fin")
            else None
        )
        base["nota_vigencia"] = excepcion.get("nota_administrativa_original")
    else:
        contenido = scraper.descargar_archivo(session, archivo.id_archivo)
        texto_completo = scraper.extraer_texto_docx(contenido)

    if _es_reservado(texto_completo):
        return [{**base, "tipo_registro": "reservado", "numeral": None, "texto": texto_completo}]

    prefijo = f"{archivo.parte}.{archivo.numero_capitulo}."
    fragmentos = _fragmentar_por_numeral(texto_completo, prefijo)
    fragmentos = _aplicar_correccion_numeral(archivo.id_archivo, fragmentos)
    return [
        {**base, "tipo_registro": "articulo", "numeral": numeral, "texto": texto_fragmento}
        for numeral, texto_fragmento in fragmentos
    ]


def _texto_para_embedding(fila: dict) -> str:
    encabezado = [fila["fuente"]]
    texto = (fila.get("texto") or "")[:TRUNCADO_TEXTO_EMBEDDING]
    return "\n".join(encabezado + [texto])


INSERT_SQL = text(
    """
    INSERT INTO normas_cbf (
        parte, nombre_parte, numero_capitulo, nombre_capitulo, seccion,
        tipo_registro, numeral, id_archivo_cbf, version, fuente,
        url_archivo, texto, estado_vigencia, fecha_vigencia_inicio,
        fecha_vigencia_fin, nota_vigencia, embedding
    ) VALUES (
        :parte, :nombre_parte, :numero_capitulo, :nombre_capitulo, :seccion,
        :tipo_registro, :numeral, :id_archivo_cbf, :version, :fuente,
        :url_archivo, :texto, :estado_vigencia, :fecha_vigencia_inicio,
        :fecha_vigencia_fin, :nota_vigencia, :embedding
    )
    ON CONFLICT (
        parte, COALESCE(numero_capitulo, -1), COALESCE(seccion, ''),
        COALESCE(numeral, ''), COALESCE(id_archivo_cbf, -1), version
    )
    DO NOTHING
    RETURNING id
    """
)


def ingestar(pausa: float = 0.3) -> dict:
    """Commit por archivo (no una única transacción para las 4 Partes):
    con solo 62 archivos descargables (frente a las ~750 páginas de
    SFC), el costo de perder el archivo en curso ante una falla es bajo,
    y la inserción ya es idempotente vía ON CONFLICT DO NOTHING — una
    corrida repetida desde cero no duplica nada, así que no se necesita
    un flag de reanudación como --pagina-inicial en Ingest/SFC."""
    session = requests.Session()
    html = scraper.obtener_tabla_cbf(session)
    archivos = scraper.parse_tabla_cbf(html)
    print(f"{len(archivos)} archivos a procesar...")

    insertados = 0
    omitidos_duplicados = 0
    con_error: list[tuple[scraper.ArchivoCBF, str]] = []

    for i, archivo in enumerate(archivos, start=1):
        try:
            filas = procesar_archivo(session, archivo)
        except Exception as e:  # noqa: BLE001 — un archivo con error no debe tumbar el resto de la corrida
            con_error.append((archivo, f"{type(e).__name__}: {e}"))
            print(f"  [{i}/{len(archivos)}] ERROR idFile={archivo.id_archivo}: {e}")
            time.sleep(pausa)
            continue

        with engine.begin() as conn:
            for fila in filas:
                fila["embedding"] = (
                    "[" + ",".join(repr(x) for x in embed_document(_texto_para_embedding(fila))) + "]"
                    if fila["tipo_registro"] == "articulo"
                    else None
                )
                resultado = conn.execute(INSERT_SQL, fila)
                if resultado.fetchone() is not None:
                    insertados += 1
                else:
                    omitidos_duplicados += 1

        print(
            f"  [{i}/{len(archivos)}] P{archivo.parte}.C{archivo.numero_capitulo} "
            f"idFile={archivo.id_archivo} '{archivo.tipo}': {len(filas)} fila(s) — commit OK "
            f"(acumulado: {insertados} insertados, {omitidos_duplicados} duplicados)"
        )
        time.sleep(pausa)

    return {
        "archivos_procesados": len(archivos),
        "insertados": insertados,
        "omitidos_duplicados": omitidos_duplicados,
        "errores": [(a.id_archivo, msg) for a, msg in con_error],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pausa", type=float, default=0.3, help="segundos entre archivos")
    args = ap.parse_args()

    resumen = ingestar(args.pausa)
    print(resumen)
