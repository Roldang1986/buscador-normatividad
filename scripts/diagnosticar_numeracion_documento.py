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
import re
import sys

from app.ingest.dian_scraper import (
    ARTICULO_HEADER_RE,
    _estado_y_nota_vigencia,
    _extraer_articulos,
    _texto_plano,
    descargar_html,
)

# Busca anclas HTML reales (<a name="...">, <a id="...">, o id="..." en
# cualquier otra etiqueta) para verificar si url_fuente="{url}#{numero}"
# corresponde a un ancla real navegable en la página, o si es un
# identificador puramente sintético inventado por este scraper para
# unicidad interna (_norma_existe filtra por url_fuente, no por navegar
# realmente a esa ancla).
ANCLA_RE = re.compile(r'<a[^>]+(?:name|id)\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def inspeccionar_anclas_reales(html: str, numeros_de_interes: list[str]) -> None:
    anclas = ANCLA_RE.findall(html)
    print(f"\n=== Anclas HTML reales (<a name=/id=>) en el documento ===")
    print(f"Total de anclas encontradas: {len(anclas)}")
    if not anclas:
        print(
            "  No hay NINGUNA ancla name=/id= en el HTML crudo. Esto confirma que "
            "'#numero_articulo' en url_fuente NO es un ancla real navegable de la "
            "página — es un identificador sintético que este scraper inventa "
            "únicamente para tener una url_fuente única por artículo dentro del "
            "mismo documento. Un sufijo '-2' tiene exactamente el mismo estatus "
            "(sintético) que el propio '#numero_articulo' sin sufijo: ninguno de "
            "los dos lleva a ningún lado en un navegador real, pero ambos sirven "
            "igual de bien como clave de unicidad interna."
        )
        return
    print("Primeras 15 anclas encontradas (valor):", anclas[:15])
    for numero in numeros_de_interes:
        coincidencias = [a for a in anclas if a == numero]
        if coincidencias:
            print(f"  Ancla exacta para {numero!r}: SÍ existe ({len(coincidencias)} vez/veces)")
        else:
            print(f"  Ancla exacta para {numero!r}: NO existe ninguna coincidencia literal")


def diagnosticar_documento(url: str) -> None:
    print(f"\n=== {url} ===")
    html = descargar_html(url)
    texto = _texto_plano(html)

    matches = list(ARTICULO_HEADER_RE.finditer(texto))
    numeros_todos = [m.group(1) for m in matches]
    numeros_unicos = sorted(set(numeros_todos), key=numeros_todos.index)
    print(f"Encabezados de artículo detectados (ARTICULO_HEADER_RE): {len(matches)}")
    print(f"numero_articulo ÚNICOS entre esos encabezados: {len(numeros_unicos)}")
    if len(numeros_unicos) < len(matches):
        print(
            f"  (¡{len(matches) - len(numeros_unicos)} encabezados comparten numero_articulo "
            "con otro — posible colapso/truncamiento!)"
        )
        from collections import Counter

        repetidos = {n: c for n, c in Counter(numeros_todos).items() if c > 1}
        print(f"  numero_articulo repetidos ({len(repetidos)} valores distintos) — texto completo de cada caso:")
        for numero, veces in repetidos.items():
            posiciones = [i for i, n in enumerate(numeros_todos) if n == numero]
            print(f"\n  --- {numero!r} aparece {veces} veces ---")
            for i in posiciones:
                m = matches[i]
                fin = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
                fragmento_completo = texto[m.end() : fin].strip()
                print(f"    pos {i}: {fragmento_completo[:400]!r}")

        inspeccionar_anclas_reales(html, list(repetidos.keys()))
    print("Primeros 15 números detectados (en orden, con repetidos si los hay):", numeros_todos[:15])

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

    # Muestra repartida a lo largo de TODO el documento (no solo el
    # principio) para confirmar visualmente que la numeración jerárquica
    # se extrae bien también en artículos avanzados, no solo al inicio.
    if matches:
        paso = max(1, len(matches) // 8)
        indices_muestra = list(range(0, len(matches), paso))[:8]
        print("\nMuestra de headers repartida a lo largo del documento:")
        for i in indices_muestra:
            m = matches[i]
            contexto = texto[m.end() : m.end() + 60].replace("\n", " ").strip()
            print(f"  [{i}] numero_articulo={m.group(1)!r}  texto_siguiente={contexto!r}")

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
