"""Diagnóstico de solo lectura: descarga uno o más documentos reales (sin
insertar nada en la BD) y aplica ARTICULO_HEADER_RE / _extraer_articulos /
_estado_y_nota_vigencia en memoria, para verificar si el formato de
numeración de artículos y las notas de vigencia de una sección nueva
calzan con los regex ya corregidos, antes de ingerir en volumen.

Pensado en particular para el Decreto Único Reglamentario (Decreto 1625
de 2016), cuya numeración compilada de artículos suele ser del estilo
"1.2.1.7.1" (con puntos) en vez de un número simple como en el Estatuto
Tributario — ARTICULO_HEADER_RE solo captura dígitos y guiones
("631-1"), así que un punto en medio del número cortaría el match ahí,
el mismo tipo de bug (silencioso, sin excepción) que el de "631-" antes
de corregirse para guiones.

Uso:
    python scripts/diagnosticar_numeracion_documento.py <url> [<url2> ...]
"""

import json
import sys

from app.ingest.dian_scraper import (
    ARTICULO_HEADER_RE,
    _estado_y_nota_vigencia,
    _extraer_articulos,
    _texto_plano,
    descargar_html,
)


def diagnosticar_documento(url: str) -> None:
    print(f"\n=== {url} ===")
    html = descargar_html(url)
    texto = _texto_plano(html)

    matches = list(ARTICULO_HEADER_RE.finditer(texto))
    print(f"Encabezados de artículo detectados (ARTICULO_HEADER_RE): {len(matches)}")
    print("Primeros 15 números detectados:", [m.group(1) for m in matches[:15]])

    # Señal de posible truncamiento: el número detectado termina en punto u
    # guión, o el texto inmediatamente después del match sigue con un
    # dígito o un punto (indicaría que el regex se detuvo a mitad de un
    # número compuesto, ej. "1.2.1" detectado como "1" con ".2.1" después).
    sospechosos = []
    for m in matches[:300]:
        numero = m.group(1)
        resto_inmediato = texto[m.end() : m.end() + 4]
        si_sospechoso = (
            numero.endswith("-")
            or numero.endswith(".")
            or resto_inmediato[:1].isdigit()
            or resto_inmediato[:1] == "."
        )
        if si_sospechoso:
            sospechosos.append({"numero_detectado": numero, "texto_siguiente": resto_inmediato})

    if sospechosos:
        print(f"\nPOSIBLES TRUNCAMIENTOS ({len(sospechosos)} de los primeros {min(300, len(matches))}):")
        for s in sospechosos[:10]:
            print(" ", json.dumps(s, ensure_ascii=False))
    else:
        print(f"\nSin señales de truncamiento en los primeros {min(300, len(matches))} encabezados.")

    fragmentos = _extraer_articulos(texto)
    print(f"\nFragmentos que produciría _extraer_articulos: {len(fragmentos)}")

    resumen_estados: dict[str, int] = {}
    muestra_notas = []
    for numero, frag in fragmentos[:400]:
        estado, nota = _estado_y_nota_vigencia(frag[:400])
        resumen_estados[estado] = resumen_estados.get(estado, 0) + 1
        if nota and len(muestra_notas) < 8:
            muestra_notas.append({"numero_articulo": numero, "estado": estado, "nota": nota})

    print(
        "\nResumen de estado_vigencia (primeros",
        min(400, len(fragmentos)),
        "fragmentos):",
        json.dumps(resumen_estados, ensure_ascii=False),
    )
    print("Muestra de notas de vigencia detectadas:")
    for n in muestra_notas:
        print(" ", json.dumps(n, ensure_ascii=False))
    if not muestra_notas:
        print("  (ninguna nota de vigencia detectada en los primeros 400 fragmentos)")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for url in sys.argv[1:]:
        diagnosticar_documento(url)


if __name__ == "__main__":
    main()
