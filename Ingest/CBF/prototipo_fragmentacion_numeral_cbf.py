"""
Dry-run de SOLO REPORTE sobre las 4 Partes completas de la CBF — paso 3
del pipeline (ver README.md). No inserta nada en Neon ni escribe en
ningún lado: descarga los .docx reales, extrae texto y mide la densidad
de numerales por capítulo/archivo para calibrar umbrales de fragmentación
antes de escribir ingest_pilot.py (paso 4).

Qué reporta:
  - Numerales por archivo (patrón "P.C.N" tipo "2.9.1." como línea propia,
    confirmado contra el .docx real de P2.C9 — ver README).
  - Longitud de fragmento (numeral -> siguiente numeral) min/max/promedio,
    y cuáles caen fuera de un rango razonable (posibles numerales mal
    detectados o fragmentos que en realidad deberían subdividirse más).
  - Archivos sin ningún numeral detectado (¿el capítulo no usa esa
    numeración, o el detector falló?).
  - Archivos que se parecen al patrón P2.C9 (encabezado del capítulo
    repetido 2+ veces en el texto — indicio de nota de vigencia embebida
    que habría que separar con `separar_nota_futura`, aunque el archivo
    no esté marcado tipo="version_futura").

CÓMO CORRERLO:

    python prototipo_fragmentacion_numeral_cbf.py
"""

from __future__ import annotations

import argparse
import statistics
import time
from dataclasses import dataclass

import requests

import scraper

_LARGO_MIN_RAZONABLE = 40  # caracteres; por debajo, sospechoso de numeral mal detectado
_LARGO_MAX_RAZONABLE = 4000  # caracteres; por encima, candidato a sub-fragmentar


@dataclass
class ReporteArchivo:
    archivo: scraper.ArchivoCBF
    largo_texto: int
    n_numerales: int
    largos_fragmentos: list[int]
    repeticiones_encabezado: int
    error: str | None = None


def _numerales_y_fragmentos(
    texto: str, prefijo: str, patron=scraper._RE_NUMERAL_LINEA
) -> tuple[int, list[int]]:
    """`prefijo` = "{parte}.{capitulo}." — un marcador solo cuenta como
    numeral real del capítulo si empieza con el prefijo Parte.Capítulo del
    propio archivo. Sin este filtro, tablas de clasificación/taxonomía
    embebidas dentro de un numeral (ej. la taxonomía de tipo de evento de
    riesgo operativo de Basilea en P1.C1 Sección 3, con su propia
    numeración interna "1.2.1", "2.2.2", etc. que por casualidad matchea
    el mismo patrón "N.N.N") se cuentan como numerales del capítulo,
    partiendo la tabla en fragmentos falsos — bug real encontrado en el
    dry-run: 76 de 331 "numerales" en ese archivo eran en realidad de esa
    taxonomía interna, no del capítulo (ver README)."""
    lineas = texto.split("\n")
    posiciones = []
    offset = 0
    for linea in lineas:
        l = linea.strip()
        if patron.match(l) and l.startswith(prefijo):
            posiciones.append(offset)
        offset += len(linea) + 1  # +1 por el "\n" que junta las líneas
    if not posiciones:
        return 0, []
    posiciones.append(len(texto))
    largos = [posiciones[i + 1] - posiciones[i] for i in range(len(posiciones) - 1)]
    return len(posiciones) - 1, largos


def analizar_archivo(session: requests.Session, archivo: scraper.ArchivoCBF) -> ReporteArchivo:
    try:
        contenido = scraper.descargar_archivo(session, archivo.id_archivo)
        texto = scraper.extraer_texto_docx(contenido)
    except Exception as e:  # noqa: BLE001 — es un dry-run de reporte, un archivo con error no debe tumbar el resto
        return ReporteArchivo(archivo, 0, 0, [], 0, error=f"{type(e).__name__}: {e}")

    cuerpo = texto
    if archivo.tipo == "version_futura" and archivo.nombre_capitulo:
        try:
            _nota, cuerpo = scraper.separar_nota_futura(texto, archivo.nombre_capitulo)
        except ValueError as e:
            return ReporteArchivo(archivo, len(texto), 0, [], 0, error=str(e))

    prefijo = f"{archivo.parte}.{archivo.numero_capitulo}."
    n_numerales, largos = _numerales_y_fragmentos(cuerpo, prefijo)
    repeticiones = texto.count(archivo.nombre_capitulo) if archivo.nombre_capitulo else 0
    return ReporteArchivo(archivo, len(texto), n_numerales, largos, repeticiones)


def _fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def imprimir_reporte(reportes: list[ReporteArchivo]) -> None:
    print(f"\n{'='*78}\nREPORTE — {len(reportes)} archivos analizados\n{'='*78}\n")

    con_error = [r for r in reportes if r.error]
    sin_numerales = [r for r in reportes if not r.error and r.n_numerales == 0]
    con_numerales = [r for r in reportes if not r.error and r.n_numerales > 0]
    sospechosos_p2c9 = [r for r in reportes if not r.error and r.repeticiones_encabezado >= 2]

    print(f"Con error de descarga/extracción: {len(con_error)}")
    for r in con_error:
        a = r.archivo
        print(f"  [{a.tipo}] P{a.parte}.C{a.numero_capitulo} idFile={a.id_archivo} '{a.titulo}': {r.error}")

    print(f"\nSin numerales detectados (patrón 'P.C.N'): {len(sin_numerales)}")
    for r in sin_numerales:
        a = r.archivo
        print(f"  [{a.tipo}] P{a.parte}.C{a.numero_capitulo}"
              f"{' S:' + a.seccion if a.seccion else ''} idFile={a.id_archivo}"
              f" '{a.nombre_capitulo}' — {r.largo_texto} caracteres")

    print(f"\nParecen el patrón P2.C9 (encabezado repetido 2+ veces, "
          f"indicio de nota de vigencia embebida): {len(sospechosos_p2c9)}")
    for r in sospechosos_p2c9:
        a = r.archivo
        print(f"  [{a.tipo}] P{a.parte}.C{a.numero_capitulo} idFile={a.id_archivo}"
              f" '{a.nombre_capitulo}' — encabezado aparece {r.repeticiones_encabezado} veces"
              f" (estado_vigencia={a.estado_vigencia})")

    print(f"\nCon numerales detectados: {len(con_numerales)}")
    print(f"{'Parte.Cap':<10} {'Sección':<45} {'idFile':<9} {'#num':<6} {'min':<7} {'max':<7} {'prom':<7} anomalías")
    total_numerales = 0
    todos_los_largos: list[int] = []
    for r in sorted(con_numerales, key=lambda r: (r.archivo.parte or 0, r.archivo.numero_capitulo or 0)):
        a = r.archivo
        total_numerales += r.n_numerales
        todos_los_largos.extend(r.largos_fragmentos)
        cortos = sum(1 for l in r.largos_fragmentos if l < _LARGO_MIN_RAZONABLE)
        largos_ = sum(1 for l in r.largos_fragmentos if l > _LARGO_MAX_RAZONABLE)
        anomalia = []
        if cortos:
            anomalia.append(f"{cortos} corto(s) <{_LARGO_MIN_RAZONABLE}c")
        if largos_:
            anomalia.append(f"{largos_} largo(s) >{_LARGO_MAX_RAZONABLE}c")
        pc = f"P{a.parte}.C{a.numero_capitulo}"
        sec = (a.seccion or "")[:43]
        print(f"{pc:<10} {sec:<45} {a.id_archivo:<9} {r.n_numerales:<6} "
              f"{min(r.largos_fragmentos):<7} {max(r.largos_fragmentos):<7} "
              f"{_fmt(statistics.mean(r.largos_fragmentos)):<7} {', '.join(anomalia)}")

    print(f"\n{'='*78}")
    print(f"TOTAL numerales detectados: {total_numerales}")
    if todos_los_largos:
        print(f"Longitud de fragmento — min: {min(todos_los_largos)}  "
              f"max: {max(todos_los_largos)}  "
              f"promedio: {_fmt(statistics.mean(todos_los_largos))}  "
              f"mediana: {_fmt(statistics.median(todos_los_largos))}")
    print(f"{'='*78}\n")


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pausa", type=float, default=0.3, help="segundos entre descargas")
    args = parser.parse_args()

    session = requests.Session()
    html = scraper.obtener_tabla_cbf(session)
    archivos = scraper.parse_tabla_cbf(html)
    print(f"{len(archivos)} archivos a analizar...")

    reportes = []
    for i, a in enumerate(archivos, start=1):
        reportes.append(analizar_archivo(session, a))
        if i % 10 == 0 or i == len(archivos):
            print(f"  {i}/{len(archivos)}...")
        time.sleep(args.pausa)

    imprimir_reporte(reportes)


if __name__ == "__main__":
    _cli()
