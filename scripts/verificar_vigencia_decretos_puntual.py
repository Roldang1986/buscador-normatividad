"""Auditoría puntual y de solo lectura de la vigencia real de un conjunto
de filas de `norma` por id.

Motivación: `_estado_y_nota_vigencia()` (app/ingest/dian_scraper.py) marca
un artículo como "vigente" cuando NO encuentra una nota `<NOTA DE
VIGENCIA:...>` en los primeros 400 caracteres de su texto — eso es
"no se encontró nota", no "se confirmó que sigue vigente". Para decretos
muy anteriores al Estatuto Tributario de 1989 (Decreto 624), el corpus
depende de que normograma.dian.gov.co sí haya trasladado esa nota al
documento compilado; si no lo hizo (o si la nota vive en otra parte del
documento fuera de los 400 caracteres iniciales del artículo), la fila
queda marcada "vigente" sin que eso sea una confirmación real.

Este script, por cada id:
1. Imprime la fila completa tal como está en la BD (estado_vigencia,
   nota_vigencia, fecha_ingesta, url_fuente).
2. Descarga el HTML real de url_fuente (acceso externo real, no de
   memoria) y busca CUALQUIER coincidencia de VIGENCIA_RE /
   ESTADO_ESPECIAL_SPAN_RE en el documento completo (no solo los primeros
   400 caracteres del artículo) — para distinguir "el documento no tiene
   ninguna nota de vigencia" de "hay una nota pero el heurístico de
   ingesta no la vio".
3. Ubica el header del artículo en el texto plano real y muestra los
   ~800 caracteres siguientes tal cual aparecen en la fuente, para
   inspección visual directa.

No modifica la BD. No re-ingiere nada.

Uso:
    python scripts/verificar_vigencia_decretos_puntual.py <id1> [<id2> ...]
"""

import sys

from app.database import SessionLocal
from app.ingest.dian_scraper import (
    ARTICULO_HEADER_RE,
    ESTADO_ESPECIAL_SPAN_RE,
    VIGENCIA_RE,
    _texto_plano,
    descargar_html,
)
from app.models import Norma

CONTEXTO_CHARS = 800


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    ids = [int(x) for x in sys.argv[1:]]
    db = SessionLocal()

    html_cache: dict[str, str] = {}

    for norma_id in ids:
        print(f"\n{'=' * 70}\nID {norma_id}\n{'=' * 70}")
        norma = db.get(Norma, norma_id)
        if norma is None:
            print("  NO EXISTE en la BD.")
            continue

        print(f"  tipo_norma:       {norma.tipo_norma}")
        print(f"  numero_articulo:  {norma.numero_articulo}")
        print(f"  numeral:          {norma.numeral}")
        print(f"  fuente:           {norma.fuente}")
        print(f"  url_fuente:       {norma.url_fuente}")
        print(f"  estado_vigencia:  {norma.estado_vigencia}")
        print(f"  nota_vigencia:    {norma.nota_vigencia!r}")
        print(f"  fecha_ingesta:    {norma.fecha_ingesta}")
        print(f"  texto[:400]:      {norma.texto[:400]!r}")

        if not norma.url_fuente:
            print("  (sin url_fuente, no se puede verificar contra la fuente en vivo)")
            continue

        base_url = norma.url_fuente.split("#")[0]

        if base_url not in html_cache:
            print(f"\n  Descargando HTML en vivo: {base_url}")
            try:
                html_cache[base_url] = descargar_html(base_url)
            except Exception as exc:  # noqa: BLE001 — diagnóstico, se quiere ver cualquier fallo
                print(f"  ERROR descargando: {exc}")
                html_cache[base_url] = ""

        html = html_cache[base_url]
        if not html:
            continue

        texto_completo = _texto_plano(html)

        # 1. ¿El documento completo tiene ALGUNA nota de vigencia, en
        #    cualquier parte (no solo en los primeros 400 caracteres de
        #    este artículo)?
        matches_vigencia = list(VIGENCIA_RE.finditer(texto_completo))
        matches_span = list(ESTADO_ESPECIAL_SPAN_RE.finditer(texto_completo[:2000]))
        print(f"\n  Notas <VIGENCIA...> encontradas en TODO el documento: {len(matches_vigencia)}")
        for m in matches_vigencia[:10]:
            nota = " ".join(m.group(0).split())
            print(f"    - {nota}")
        print(f"  Coincidencias de span de estado especial (primeros 2000 chars): {len(matches_span)}")

        # 2. Ubicar el header real de este artículo en el documento y
        #    mostrar el contexto crudo que le sigue.
        numero = norma.numero_articulo
        encontrado = False
        for m in ARTICULO_HEADER_RE.finditer(texto_completo):
            if m.group(1) == numero:
                encontrado = True
                inicio = m.start()
                contexto = texto_completo[inicio : inicio + CONTEXTO_CHARS]
                print(f"\n  --- Contexto real en la fuente para artículo {numero} ---")
                print(f"  {contexto}")
                break

        if not encontrado:
            print(f"\n  ADVERTENCIA: no se encontró un header '{numero}' con "
                  f"ARTICULO_HEADER_RE en el HTML actual (pudo cambiar el sitio, "
                  f"o el número no matchea exactamente).")

    db.close()


if __name__ == "__main__":
    main()
