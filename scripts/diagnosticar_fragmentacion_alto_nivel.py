"""Diagnóstico de SOLO REPORTE (no escribe nada, ni siquiera lee la BD):
descarga el documento real y aplica
_fragmentar_documento_por_secciones_alto_nivel() — la variante GRUESA de
fragmentación (secciones romanas "II."/"III."/"IV." y "ANEXO NO. N.",
sin descender a numeral ni a literal), pensada para documentos sin
numero_articulo cuyo formato interno es demasiado inconsistente para la
fragmentación fina por numeral (ver
DOCUMENTOS_CON_FRAGMENTACION_POR_SECCION_ALTO_NIVEL_HABILITADA en
app/ingest/dian_scraper.py, confirmado con el texto real de OA. 4 de
1989, sección "1.8. Orden administrativa").

Mismo chequeo de colisión de etiquetas que
diagnosticar_fragmentacion_multiple.py, aplicado acá a las etiquetas de
sección/anexo en vez de a las de numeral.

No modifica la BD. No aplica nada — solo reporta.

Uso:
    python scripts/diagnosticar_fragmentacion_alto_nivel.py <url_documento>
"""

import json
import sys
from collections import Counter

from app.ingest.dian_scraper import (
    _debe_fragmentarse_por_secciones_alto_nivel,
    _extraer_articulos,
    _fragmentar_documento_por_secciones_alto_nivel,
    _resolver_numeros_duplicados,
    _texto_plano,
    descargar_html,
)

# Mismo umbral que UMBRAL_LONGITUD_DILUCION en diagnosticar_seccion.py —
# longitud del art. 879 antes de fragmentarlo, el umbral de dilución de
# embedding ya confirmado con evidencia real. Distinto de
# UMBRAL_LONGITUD_FRAGMENTACION_NUMERAL (8000, el umbral bajo que decide
# SI fragmentar) — acá lo que importa es si algún fragmento RESULTANTE
# sigue siendo demasiado grande.
UMBRAL_LONGITUD_DILUCION = 26627


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    url_base = sys.argv[1].split("#")[0]

    html = descargar_html(url_base)
    texto = _texto_plano(html)
    fragmentos, _ = _resolver_numeros_duplicados(_extraer_articulos(texto))
    texto_por_numero = dict(fragmentos)

    texto_documento = texto_por_numero.get(None)
    if texto_documento is None:
        print(
            json.dumps(
                {
                    "url_documento": url_base,
                    "error": (
                        "este documento SÍ tiene encabezados ARTICULO N. "
                        "(numero_articulo != None) — la fragmentación por "
                        "sección de alto nivel es para documentos sin "
                        "artículos, no aplica acá."
                    ),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    califica = _debe_fragmentarse_por_secciones_alto_nivel(texto_documento)
    fragmentos_nuevos = _fragmentar_documento_por_secciones_alto_nivel(texto_documento)

    etiquetas = [e for e, _ in fragmentos_nuevos] if califica else []
    conteo_etiquetas = Counter(etiquetas)
    etiquetas_duplicadas = {e: c for e, c in conteo_etiquetas.items() if c > 1}

    longitudes = [len(t) for _, t in fragmentos_nuevos] if califica else []

    resultado = {
        "url_documento": url_base,
        "umbral_longitud_dilucion": UMBRAL_LONGITUD_DILUCION,
        "longitud_texto_completo": len(texto_documento),
        "califica_para_fragmentar": califica,
        "total_fragmentos_resultantes": len(fragmentos_nuevos) if califica else 1,
        "etiquetas_en_orden": etiquetas,
        "colision_de_etiquetas": bool(etiquetas_duplicadas),
        "etiquetas_duplicadas": etiquetas_duplicadas,
        "rango_longitud_fragmentos": (
            {"minimo": min(longitudes), "maximo": max(longitudes)} if longitudes else None
        ),
        "fragmentos_sobre_umbral_dilucion": (
            [
                {"etiqueta": e, "longitud": len(t)}
                for e, t in fragmentos_nuevos
                if len(t) >= UMBRAL_LONGITUD_DILUCION
            ]
            if califica
            else None
        ),
        "longitud_por_fragmento": (
            [{"etiqueta": e, "longitud": len(t)} for e, t in fragmentos_nuevos] if califica else None
        ),
    }
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
