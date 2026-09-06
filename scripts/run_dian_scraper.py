"""Punto de entrada del workflow scraper-dian.yml: scrapea un subconjunto
pequeño de normograma.dian.gov.co e inserta los fragmentos en la BD.

Uso:
    python scripts/run_dian_scraper.py "1.1. Estatuto Tributario" --limite 3
"""

import argparse
import json
import logging
import pathlib

from app.database import SessionLocal
from app.ingest.dian_scraper import (
    aplicar_correccion_vigencia,
    contar_marca_derogado,
    descubrir_urls_seccion,
    limpiar_numeros_articulo_truncados,
    scrapear_seccion,
    verificar_icono_vs_texto,
    verificar_numeracion_articulos,
    verificar_vigencia_texto_almacenado,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "seccion",
        nargs="?",
        default=None,
        help="Texto del encabezado de la sección del índice a scrapear",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=3,
        help="Máximo de documentos a descubrir en la sección (default: 3)",
    )
    parser.add_argument(
        "--limite-fragmentos-por-documento",
        type=int,
        default=None,
        help=(
            "Trunca cada documento a sus primeros N fragmentos (artículos) "
            "antes de insertarlos. Distinto de --limite: ese acota cuántos "
            "documentos del índice se descubren, este acota el tamaño de "
            "cada documento individual — necesario para documentos "
            "consolidados grandes como el Estatuto Tributario compilado "
            "(~1000+ artículos en un solo documento), donde --limite no "
            "ayuda porque cuenta documentos del índice, no artículos."
        ),
    )
    parser.add_argument(
        "--seguir-enlaces-cruzados",
        action="store_true",
        help="Además de la sección, sigue los enlaces cruzados dentro de cada documento",
    )
    parser.add_argument(
        "--capturas-dir",
        default=None,
        help=(
            "Directorio donde guardar capturas de pantalla de diagnóstico "
            "(antes/después del clic en 'Ver Más'). Si no se pasa, no se "
            "toman capturas."
        ),
    )
    parser.add_argument(
        "--limpiar-truncados",
        action="store_true",
        help=(
            "Antes de scrapear, borra normas con numero_articulo truncado "
            "en un guión (ej. '631-' en vez de '631-1') dejadas por el bug "
            "de ARTICULO_HEADER_RE anterior a la corrección."
        ),
    )
    parser.add_argument(
        "--solo-verificar-numeracion",
        action="store_true",
        help=(
            "No scrapea nada: solo corre el diagnóstico de "
            "verificar_numeracion_articulos() sobre la BD actual e "
            "imprime el resultado. Ignora 'seccion' y '--limite'."
        ),
    )
    parser.add_argument(
        "--solo-verificar-vigencia",
        action="store_true",
        help=(
            "No scrapea nada: reaplica el VIGENCIA_RE corregido sobre el "
            "texto ya almacenado de cada norma con estado_vigencia="
            "'vigente' en la BD, e imprime cuántas deberían cambiar de "
            "estado según el texto real. Solo lectura, no modifica la BD. "
            "Ignora 'seccion' y '--limite'."
        ),
    )
    parser.add_argument(
        "--corregir-vigencia",
        action="store_true",
        help=(
            "MODO DE ESCRITURA: aplica en la BD la corrección de "
            "estado_vigencia/nota_vigencia calculada por "
            "verificar_vigencia_texto_almacenado(). Solo toca esas dos "
            "columnas (nunca url_fuente, texto ni embedding). Correr "
            "--solo-verificar-vigencia primero y revisar la muestra antes "
            "de usar este flag — deliberadamente no se puede combinar con "
            "--solo-verificar-vigencia en la misma corrida."
        ),
    )
    parser.add_argument(
        "--verificar-icono-vs-texto",
        action="store_true",
        help=(
            "No inserta ni modifica nada en la BD: vuelve a descubrir los "
            "documentos de 'seccion' (con el heurístico de ícono ya "
            "corregido, <span> en vez de <img>) y compara "
            "indice_marca_derogado contra el estado_vigencia YA "
            "CORREGIDO de sus fragmentos ya almacenados. Imprime el "
            "conteo True/False/None del ícono y los casos puntuales de "
            "desacuerdo. Usa 'seccion' y '--limite' igual que "
            "--solo-descubrir."
        ),
    )
    parser.add_argument(
        "--solo-descubrir",
        action="store_true",
        help=(
            "No descarga ni inserta nada en la BD: solo corre el "
            "descubrimiento en el índice (Playwright) sobre 'seccion' y "
            "imprime los documentos encontrados (url, titulo, "
            "indice_marca_derogado) y el conteo True/False/None de esa "
            "señal. Usar junto con --capturas-dir para guardar también "
            "capturas y el HTML del DOM antes/después del clic."
        ),
    )
    args = parser.parse_args()

    if args.solo_verificar_vigencia and args.corregir_vigencia:
        parser.error(
            "--solo-verificar-vigencia y --corregir-vigencia no se pueden "
            "combinar: corré primero el modo de solo lectura, revisá la "
            "muestra, y solo después corré --corregir-vigencia por separado."
        )

    if (
        not args.solo_verificar_numeracion
        and not args.solo_verificar_vigencia
        and not args.corregir_vigencia
        and not args.seccion
    ):
        parser.error(
            "'seccion' es obligatorio salvo con --solo-verificar-numeracion, "
            "--solo-verificar-vigencia o --corregir-vigencia"
        )

    if args.capturas_dir:
        pathlib.Path(args.capturas_dir).mkdir(parents=True, exist_ok=True)

    if args.solo_descubrir:
        documentos = descubrir_urls_seccion(
            args.seccion, limite=args.limite, directorio_capturas=args.capturas_dir
        )
        resultado = {
            "documentos_encontrados": len(documentos),
            "conteo_marca_derogado": contar_marca_derogado(documentos),
            "detalle": [
                {
                    "url": d.url,
                    "titulo": d.titulo,
                    "indice_marca_derogado": d.indice_marca_derogado,
                }
                for d in documentos
            ],
        }
        print("\n=== Descubrimiento (solo lectura, no se insertó nada) ===")
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
        return

    db = SessionLocal()
    try:
        if args.solo_verificar_numeracion:
            diagnostico = verificar_numeracion_articulos(db)
            print("\n=== Diagnóstico de numeración de artículos ===")
            print(json.dumps(diagnostico, indent=2, ensure_ascii=False))
            return

        if args.solo_verificar_vigencia:
            diagnostico = verificar_vigencia_texto_almacenado(db)
            print("\n=== Diagnóstico de vigencia sobre texto ya almacenado ===")
            print(json.dumps(diagnostico, indent=2, ensure_ascii=False))
            return

        if args.corregir_vigencia:
            resultado = aplicar_correccion_vigencia(db)
            print("\n=== Corrección de vigencia aplicada (estado_vigencia/nota_vigencia) ===")
            print(json.dumps(resultado, indent=2, ensure_ascii=False))
            return

        if args.verificar_icono_vs_texto:
            diagnostico = verificar_icono_vs_texto(db, args.seccion, limite=args.limite)
            print("\n=== Ícono del índice vs. estado_vigencia ya corregido ===")
            print(json.dumps(diagnostico, indent=2, ensure_ascii=False))
            return

        if args.limpiar_truncados:
            borrados = limpiar_numeros_articulo_truncados(db)
            print(f"Borrados {borrados} fragmentos con numero_articulo truncado.")

        resumen = scrapear_seccion(
            db,
            seccion_titulo=args.seccion,
            limite_documentos=args.limite,
            seguir_enlaces_cruzados=args.seguir_enlaces_cruzados,
            directorio_capturas=args.capturas_dir,
            limite_fragmentos_por_documento=args.limite_fragmentos_por_documento,
        )
    finally:
        db.close()

    print("\n=== Resumen del scraper ===")
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
