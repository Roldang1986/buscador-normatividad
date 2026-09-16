"""Censo completo (no muestra) del formato real de archivo de cada registro
"texto" de la colección `ac`, para decidir con datos reales cuánto texto
completo podemos extraer hoy (solo .docx soportado) vs. cuánto necesita un
extractor nuevo (.doc OLE, .pdf, .html) — y en qué rango de fechas cae cada
formato. Descarga solo los primeros bytes de cada archivo (streaming,
cerrando la conexión apenas se identifica la firma) para no bajar cada
documento completo innecesariamente.
"""

from __future__ import annotations

import json
import re
import sys
import time

import requests

from scraper import HEADERS, obtener_pagina
from parser import parse_pagina_resultados

FIRMAS = {
    b"PK\x03\x04": "docx",
    b"%PDF": "pdf",
    b"\xd0\xcf\x11\xe0": "doc_ole",
}


def _detectar_formato(session: requests.Session, url: str) -> str:
    try:
        resp = session.get(url, headers=HEADERS, timeout=30, stream=True)
        chunk = next(resp.iter_content(16), b"")
        resp.close()
    except requests.RequestException as e:
        return f"error({e.__class__.__name__})"

    for firma, nombre in FIRMAS.items():
        if chunk.startswith(firma):
            return nombre
    if chunk[:1] == b"<":
        return "html"
    if not chunk:
        return "vacio"
    return f"desconocido({chunk[:8]!r})"


def _anio(fecha_texto: str | None) -> int | None:
    if not fecha_texto:
        return None
    m = re.search(r"(19|20)\d{2}", fecha_texto)
    return int(m.group(0)) if m else None


def censar(
    coleccion: str = "ac",
    pausa_pagina: float = 0.3,
    pausa_archivo: float = 0.05,
    salida_jsonl: str = "censo_formatos_ac.jsonl",
    desde_inicial: int = 1,
) -> list[tuple[str | None, int | None, str]]:
    """Escribe cada registro en `salida_jsonl` (append, flush inmediato) a
    medida que se detecta su formato, para no perder el censo completo si el
    proceso se interrumpe a mitad de camino (ya pasó una vez: una corrida
    anterior llegó a la página 97/~138 sin persistir nada y se perdió toda
    esa data). `desde_inicial` permite reanudar una corrida cortada sin
    repetir páginas ya cubiertas.
    """
    session = requests.Session()
    resultados = []  # (numero_documento, anio, formato)
    desde = desde_inicial
    pagina_num = 0

    with open(salida_jsonl, "a", encoding="utf-8") as f:
        while True:
            html = obtener_pagina(session, coleccion, desde=desde)
            regs = parse_pagina_resultados(html)
            if not regs:
                break
            pagina_num += 1

            for r in regs:
                anio = _anio(r.fecha_texto)
                if r.tipo_archivo != "texto" or not r.url_archivo:
                    formato = r.tipo_archivo or "sin_archivo"
                else:
                    formato = _detectar_formato(session, r.url_archivo)
                    time.sleep(pausa_archivo)
                fila = (r.numero_documento, anio, formato)
                resultados.append(fila)
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                f.flush()

            print(f"pagina {pagina_num} (desde={desde}) OK, acumulado={len(resultados)}", flush=True)
            desde += 25
            time.sleep(pausa_pagina)

    return resultados


def resumen_por_formato_y_anio(filas: list[tuple]) -> None:
    from collections import Counter

    por_formato = Counter(f for _, _, f in filas)
    print("\n=== Total por formato ===")
    for formato, n in por_formato.most_common():
        print(f"{formato}: {n}")

    print("\n=== Por formato y año (solo docx/pdf/doc_ole/html) ===")
    interes = {"docx", "pdf", "doc_ole", "html"}
    por_formato_anio = Counter((f, a) for _, a, f in filas if f in interes)
    for formato in sorted(interes):
        anios = sorted(
            ((a, n) for (f, a), n in por_formato_anio.items() if f == formato),
            key=lambda x: (x[0] is None, x[0]),
        )
        if not anios:
            continue
        print(f"\n{formato}:")
        for anio, n in anios:
            print(f"  {anio}: {n}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=1, help="Offset 1-based para reanudar una corrida cortada.")
    ap.add_argument("--salida", default="censo_formatos_ac.jsonl")
    args = ap.parse_args()

    datos = censar(desde_inicial=args.desde, salida_jsonl=args.salida)
    print("CENSO_COMPLETO", len(datos))
    resumen_por_formato_y_anio(datos)
