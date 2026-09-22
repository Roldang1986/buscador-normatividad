"""Piloto de ingesta: raspa, descarga texto completo, embebe e inserta en
Neon (tabla documentos_sfc) un subconjunto de la colección `ac` (Doctrina y
conceptos). Solo para validar el flujo completo antes del scraping masivo —
no es el pipeline de producción.

Reutiliza app.embeddings.embed_document (mismo modelo/dimensión Voyage que
el corpus tributario) para que ambos corpus sean comparables si en algún
momento se necesita, aunque las búsquedas del frontend nunca los mezclan.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from sqlalchemy import text

from app.database import engine
from app.embeddings import embed_document
from scraper import raspar_coleccion

FUENTE_ATRIBUCION = "Fuente: Superintendencia Financiera de Colombia www.superfinanciera.gov.co"

# Correcciones puntuales de `numero_documento` para registros de `ac` donde
# el propio catálogo de la SFC tiene el campo estructurado mal cargado (con
# el valor de otro registro adyacente en la lista, típicamente el anterior),
# mientras que el número citado en el texto del título es el correcto. Sin
# esto, el índice único `(tipo_documento, numero_documento)` los trataría
# como duplicados del registro vecino y `ON CONFLICT DO NOTHING` descartaría
# en silencio el documento con el campo mal cargado.
#
# Confirmadas de forma individual (no es una heurística general — cada una
# se verificó contra el registro anterior en el orden del catálogo, o contra
# una lectura manual del título) durante la investigación de la brecha
# ac: catálogo=3.431 vs `documentos_sfc`=3.392 (2026-09-18, ver README). NO
# cubre todos los casos de esa brecha: quedan casos ambiguos sin corregir,
# documentados en el README bajo "Casos conocidos sin corregir".
#
# Clave: (numero_documento tal como lo devuelve el parser, url_archivo) —
# numero_documento solo no alcanza porque es justamente el valor duplicado
# entre los dos registros que colisionan.
CORRECCIONES_NUMERO_DOCUMENTO: dict[tuple[str, str], str] = {
    ("2011082287 - 002", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/Conceptos2011/2011055880.doc"): "2011055880 - 001",
    ("2008038350 - 001", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/Conceptos2008/2008063686.pdf"): "2008063686 - 001",
    ("2008020774 - 001", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/Conceptos2008/2008046316.pdf"): "2008046316 - 001",
    ("2003029670 - 1", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/doctrinas2003/sistemgralpens099.htm"): "2003038262 - 3",
    ("2002007416 - 2", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/doctrinas2002/sistemagralpen118.htm"): "2001079683 - 1",
    ("97020097 - 1", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/doctrinas1994-8/97003336.doc"): "97003336 - 2",
    ("2019078353 - 004", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&idFile=1039738"): "2019078535 - 004",
    ("2010058231 - 00", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/Conceptos2010/2010058231.doc"): "2010058231 - 003",
    ("2008022419 - 00", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/Conceptos2008/2008022419.pdf"): "2008022419 - 001",
    ("2008039332 - 00", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/Conceptos2008/2008039332.pdf"): "2008039332 - 003",
    ("2008066040 - 00", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/Conceptos2008/2008066040.pdf"): "2008066040 - 001",
    ("2007000231 - 00", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/Conceptos2007/2007000231.pdf"): "2007000231 - 001",
    ("999039821 - 2", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/doctrinas1999/evaluacioncartera0069.htm"): "1999039821 - 2",
    ("94013223 - 2", "https://www.superfinanciera.gov.co/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=downloadSFCant&file=/Normativa/doctrinas1994-8/97401323.doc"): "97013223 - 2",
}

# Límite de caracteres del texto completo dentro del input de embedding,
# para no acercarse al límite de tokens de voyage-3.5 en un solo request.
TRUNCADO_TEXTO_COMPLETO = 12000


def _texto_para_embedding(registro: dict) -> str:
    partes = [
        registro.get("titulo") or "",
        "Materias: " + ", ".join(registro.get("materias") or []),
        "Resumen: " + (registro.get("resumen") or ""),
    ]
    texto_completo = registro.get("texto_completo")
    if texto_completo:
        partes.append(texto_completo[:TRUNCADO_TEXTO_COMPLETO])
    return "\n\n".join(p for p in partes if p.strip())


INSERT_SQL = text(
    """
    INSERT INTO documentos_sfc (
        tipo_documento, numero_documento, fecha_texto, expediente_radicado,
        autor_corporativo, titulo, documento_fuente, resumen, notas,
        materias, otros_autores, url_archivo, tipo_archivo,
        tiene_texto_completo, texto_completo, motivo_sin_texto,
        fuente_atribucion, embedding
    ) VALUES (
        :tipo_documento, :numero_documento, :fecha_texto, :expediente_radicado,
        :autor_corporativo, :titulo, :documento_fuente, :resumen, :notas,
        :materias, :otros_autores, :url_archivo, :tipo_archivo,
        :tiene_texto_completo, :texto_completo, :motivo_sin_texto,
        :fuente_atribucion, :embedding
    )
    ON CONFLICT (tipo_documento, numero_documento) WHERE numero_documento IS NOT NULL
    DO NOTHING
    RETURNING id
    """
)


def ingestar_pilotos(
    coleccion: str, max_paginas: int, pausa: float = 1.0, pagina_inicial: int = 1
) -> dict:
    """Embebe e inserta con **commit por página**, no una única transacción
    para toda la colección: cada página raspada (~25 registros) se confirma
    en Neon antes de pasar a la siguiente. Si el proceso se cancela o falla
    a mitad de una corrida larga, lo ya confirmado queda en la base — solo
    se pierde, como mucho, la página que estaba en curso — y la corrida se
    puede retomar con `pagina_inicial` en vez de rasear/embeber todo de
    nuevo (ver corrida cancelada en página 110, 2026-09-16, README).
    """
    raspados = 0
    insertados = 0
    omitidos_sin_texto = 0
    omitidos_duplicados = 0

    for pagina_num, registros_pagina in raspar_coleccion(
        coleccion, max_paginas=max_paginas, dry_run=False, pausa=pausa, pagina_inicial=pagina_inicial
    ):
        raspados += len(registros_pagina)
        with engine.begin() as conn:
            for r in registros_pagina:
                texto_embedding = _texto_para_embedding(r)
                if not texto_embedding.strip():
                    omitidos_sin_texto += 1
                    continue

                vector = embed_document(texto_embedding)

                numero_documento = CORRECCIONES_NUMERO_DOCUMENTO.get(
                    (r["numero_documento"], r["url_archivo"]), r["numero_documento"]
                )

                resultado = conn.execute(
                    INSERT_SQL,
                    {
                        "tipo_documento": r["tipo_documento"],
                        "numero_documento": numero_documento,
                        "fecha_texto": r["fecha_texto"],
                        "expediente_radicado": r["expediente_radicado"],
                        "autor_corporativo": r["autor_corporativo"],
                        "titulo": r["titulo"],
                        "documento_fuente": r["documento_fuente"],
                        "resumen": r["resumen"],
                        "notas": r["notas"],
                        "materias": r["materias"],
                        "otros_autores": r["otros_autores"],
                        "url_archivo": r["url_archivo"],
                        "tipo_archivo": r["tipo_archivo"],
                        "tiene_texto_completo": r["tiene_texto_completo"],
                        "texto_completo": r.get("texto_completo"),
                        "motivo_sin_texto": r.get("motivo_sin_texto"),
                        "fuente_atribucion": FUENTE_ATRIBUCION,
                        "embedding": "[" + ",".join(repr(x) for x in vector) + "]",
                    },
                )
                if resultado.fetchone() is not None:
                    insertados += 1
                else:
                    omitidos_duplicados += 1
        print(
            f"  página {pagina_num}: commit OK "
            f"(acumulado: {insertados} insertados, {omitidos_duplicados} duplicados, "
            f"{omitidos_sin_texto} sin texto para embedding)"
        )

    return {
        "raspados": raspados,
        "insertados": insertados,
        "omitidos_sin_texto_para_embedding": omitidos_sin_texto,
        "omitidos_duplicados": omitidos_duplicados,
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--coleccion", default="ac")
    ap.add_argument("--paginas", type=int, default=1)
    ap.add_argument("--pausa", type=float, default=1.0)
    ap.add_argument(
        "--pagina-inicial",
        type=int,
        default=1,
        help="Página (1-based) por la que empezar, para retomar una corrida cancelada/fallida.",
    )
    args = ap.parse_args()

    resumen = ingestar_pilotos(args.coleccion, args.paginas, args.pausa, args.pagina_inicial)
    print(resumen)
