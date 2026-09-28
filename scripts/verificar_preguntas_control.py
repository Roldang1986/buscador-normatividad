"""Regresión manual de solo lectura: corre un set fijo de "preguntas de
control" contra POST /consulta (TestClient in-process, misma BD real,
mismo patrón que scripts/consulta_ad_hoc.py) y verifica que cada una
siga citando la fuente esperada entre 'fuentes'. No modifica la BD.

Motivación real: el 22 de septiembre de 2026, la pregunta "¿Las
operaciones simultáneas tienen GMF?" — usada repetidas veces en esta
sesión para validar el diseño de citación estricta — dejó de citar el
artículo 879 numeral 5 del Estatuto Tributario (la norma sustantiva de
la exención) porque el corpus creció y ese fragmento salió del top-5
semántico. Se descubrió por casualidad, no por una verificación
deliberada. Este script existe para que correr esta comprobación sea un
comando, no una casualidad — pensado para correrlo a mano después de
cada sección nueva que se escale a ingesta completa.

No está conectado a CI todavía (deliberado, ver PR) — es un comando
manual. Termina con código de salida 1 si alguna pregunta de control
falla, 0 si todas pasan.

Uso:
    python scripts/verificar_preguntas_control.py
"""

import sys

from starlette.testclient import TestClient

from app.main import app

# Cada entrada: la pregunta exacta y el (tipo_norma, numero_articulo) que
# DEBE aparecer entre 'fuentes' de la respuesta. Agregar una entrada
# nueva acá cada vez que se valide una pregunta de control puntual
# durante el desarrollo — ese es el punto de este archivo.
PREGUNTAS_CONTROL = [
    {
        "pregunta": "¿Las operaciones simultáneas tienen GMF?",
        "tipo_norma_esperado": "articulo_et",
        "numero_articulo_esperado": "879",
        "nota": (
            "Debe citar el Estatuto Tributario, artículo 879 (numeral 5, "
            "la exención del GMF para operaciones simultáneas entre "
            "entidades vigiladas). Regresión real detectada el 22 de "
            "septiembre de 2026 cuando el crecimiento del corpus sacó "
            "este fragmento del top-5 semántico — resuelto subiendo "
            "TOP_K a 10 en app/agent.py."
        ),
    },
]


def main() -> None:
    client = TestClient(app)
    resultados = []

    for caso in PREGUNTAS_CONTROL:
        resp = client.post("/consulta", json={"pregunta": caso["pregunta"]})
        resp.raise_for_status()
        fuentes = resp.json().get("fuentes", [])

        encontrada = any(
            f.get("tipo_norma") == caso["tipo_norma_esperado"]
            and f.get("numero_articulo") == caso["numero_articulo_esperado"]
            for f in fuentes
        )
        resultados.append({"caso": caso, "paso": encontrada, "fuentes_obtenidas": fuentes})

    print("\n=== Verificación de preguntas de control ===")
    algun_fallo = False
    for r in resultados:
        caso = r["caso"]
        estado = "OK" if r["paso"] else "FALLÓ"
        if not r["paso"]:
            algun_fallo = True
        print(f"\n[{estado}] {caso['pregunta']!r}")
        print(
            f"  esperado: tipo_norma={caso['tipo_norma_esperado']!r}, "
            f"numero_articulo={caso['numero_articulo_esperado']!r}"
        )
        print(f"  nota: {caso['nota']}")
        if not r["paso"]:
            print(f"  fuentes obtenidas: {r['fuentes_obtenidas']}")

    total = len(resultados)
    fallidos = sum(1 for r in resultados if not r["paso"])
    print(f"\n=== Resumen: {total - fallidos}/{total} preguntas de control OK ===")

    if algun_fallo:
        sys.exit(1)


if __name__ == "__main__":
    main()
