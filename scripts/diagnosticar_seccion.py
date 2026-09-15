"""Diagnóstico de SOLO LECTURA (no inserta nada en la BD): descubre hasta
`--limite` documentos de una sección del índice tributario y, para cada
uno, descarga y parsea el texto real con la misma lógica ya corregida de
ingestar_documento (ARTICULO_HEADER_RE, VIGENCIA_RE, _resolver_numeros_duplicados
con namespace por literal, _debe_fragmentarse_por_numeral) SIN escribir
nada — pensado para explorar una sección nueva antes de escalar la
ingesta real.

Reporta, por documento:
- indice_marca_derogado (ícono del índice) vs. la distribución de
  estado_vigencia detectada en el texto de sus artículos.
- Posibles patrones de encabezado de artículo o nota de vigencia que NO
  calzan con los regex actuales (documento con 0-1 fragmentos pese a
  tener contenido largo; palabras clave de vigencia fuera de "<...>").
- Artículos que superan el umbral de dilución por longitud (>=26,627
  caracteres, el tamaño del art. 879 antes de fragmentarlo) y/o que ya
  calificarían para _debe_fragmentarse_por_numeral().

Uso:
    python scripts/diagnosticar_seccion.py "1.2. Otras leyes con contenido tributario" --limite 5
"""

import argparse
import json
import re

from app.ingest.dian_scraper import (
    VIGENCIA_RE,
    _debe_fragmentarse_por_numeral,
    _detectar_numerales,
    _estado_y_nota_vigencia,
    _extraer_articulos,
    _resolver_numeros_duplicados,
    _texto_plano,
    contar_marca_derogado,
    descargar_html,
    descubrir_urls_seccion,
)

# Longitud del art. 879 antes de fragmentarlo — el umbral de dilución de
# embedding ya confirmado con evidencia real esta sesión.
UMBRAL_LONGITUD_DILUCION = 26627

# Palabras clave de vigencia — si aparecen FUERA de lo que VIGENCIA_RE ya
# capturó, es señal de un formato de nota nuevo que el regex no cubre.
PALABRAS_VIGENCIA_RE = re.compile(
    r"\b(derogad[oa]|modificad[oa]|adicionad[oa]|subrogad[oa]|inexequible|inconstitucional)\b",
    re.IGNORECASE,
)


def _posibles_notas_no_capturadas(texto_articulo: str) -> list[str]:
    ventana = texto_articulo[:400]
    capturado = VIGENCIA_RE.search(ventana)
    rango_capturado = capturado.span() if capturado else None

    hallazgos = []
    for m in PALABRAS_VIGENCIA_RE.finditer(ventana):
        if rango_capturado and rango_capturado[0] <= m.start() < rango_capturado[1]:
            continue
        hallazgos.append(ventana[max(0, m.start() - 40) : m.end() + 40])
    return hallazgos


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("seccion")
    parser.add_argument("--limite", type=int, default=5)
    args = parser.parse_args()

    documentos = descubrir_urls_seccion(args.seccion, limite=args.limite)

    print(f"\n=== {len(documentos)} documentos descubiertos en {args.seccion!r} ===")
    print(json.dumps(contar_marca_derogado(documentos), indent=2, ensure_ascii=False))

    reporte = []
    for doc in documentos:
        entrada = {
            "url": doc.url,
            "titulo": doc.titulo,
            "indice_marca_derogado": doc.indice_marca_derogado,
        }
        try:
            html = descargar_html(doc.url)
        except Exception as exc:
            entrada["error_descarga"] = str(exc)
            reporte.append(entrada)
            continue

        texto = _texto_plano(html)
        fragmentos_crudos = _extraer_articulos(texto)
        fragmentos, advertencias = _resolver_numeros_duplicados(fragmentos_crudos)

        entrada["longitud_texto_completo"] = len(texto)
        entrada["total_fragmentos"] = len(fragmentos)
        entrada["advertencias_duplicados"] = advertencias

        distribucion_vigencia: dict[str, int] = {}
        articulos_sobre_umbral = []
        notas_no_capturadas = []

        for numero, texto_articulo in fragmentos:
            estado, _nota = _estado_y_nota_vigencia(texto_articulo)
            distribucion_vigencia[estado] = distribucion_vigencia.get(estado, 0) + 1

            longitud = len(texto_articulo)
            califica_fragmentacion = _debe_fragmentarse_por_numeral(texto_articulo)
            if longitud >= UMBRAL_LONGITUD_DILUCION or califica_fragmentacion:
                articulos_sobre_umbral.append(
                    {
                        "numero_articulo": numero,
                        "longitud": longitud,
                        "supera_26627": longitud >= UMBRAL_LONGITUD_DILUCION,
                        "calificaria_fragmentacion_por_numeral": califica_fragmentacion,
                        "numerales_detectados": len(_detectar_numerales(texto_articulo)),
                    }
                )

            hallazgos = _posibles_notas_no_capturadas(texto_articulo)
            if hallazgos:
                notas_no_capturadas.append({"numero_articulo": numero, "hallazgos": hallazgos})

        entrada["distribucion_estado_vigencia_texto"] = distribucion_vigencia
        entrada["articulos_sobre_umbral_dilucion"] = articulos_sobre_umbral
        entrada["posibles_notas_vigencia_no_capturadas"] = notas_no_capturadas
        # Documento con contenido sustancial pero 0-1 fragmentos sugiere
        # que ARTICULO_HEADER_RE no reconoce el formato de numeración real.
        entrada["posible_numeracion_no_reconocida"] = len(fragmentos) <= 1 and len(texto) > 3000

        reporte.append(entrada)

    print("\n=== Reporte por documento ===")
    print(json.dumps(reporte, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
