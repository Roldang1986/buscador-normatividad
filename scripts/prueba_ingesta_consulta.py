"""Prueba manual de extremo a extremo: ingesta del artículo 420 ET y dos consultas RAG.

Se ejecuta desde el workflow de GitHub Actions
`.github/workflows/prueba-ingesta-consulta.yml` (workflow_dispatch), ya con
`alembic upgrade head` corrido y DATABASE_URL / ANTHROPIC_API_KEY /
VOYAGE_API_KEY disponibles en el entorno.

IMPORTANTE: el texto en scripts/data/articulo_420_et.txt es una
reconstrucción hecha sin acceso a normograma.dian.gov.co (el proxy de red de
la sesión que lo generó bloqueó ese dominio y otras fuentes legales
alternativas). Verifica el texto contra la fuente oficial antes de tratar
este resultado como una prueba definitiva.
"""

import json
import pathlib

from starlette.testclient import TestClient

from app.main import app

DATA_DIR = pathlib.Path(__file__).parent / "data"

NORMA_PRUEBA = {
    "tipo_norma": "articulo_et",
    "numero_articulo": "420",
    "fuente": "Estatuto Tributario, artículo 420",
    "texto": (DATA_DIR / "articulo_420_et.txt").read_text(encoding="utf-8").strip(),
    "estado_vigencia": "vigente",
    "url_fuente": "https://normograma.dian.gov.co/dian/compilacion/docs/estatuto_tributario.htm",
}

PREGUNTA_INDEXADA = "¿qué operaciones están gravadas con IVA según el Estatuto Tributario?"
PREGUNTA_NO_INDEXADA = (
    "¿cuál es la tarifa de retención en la fuente por dividendos no gravados "
    "pagados a una sociedad nacional?"
)


def _imprimir(titulo: str, payload: dict) -> None:
    print(f"\n=== {titulo} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def main() -> None:
    client = TestClient(app)

    resp = client.post("/ingesta/norma", json=NORMA_PRUEBA)
    resp.raise_for_status()
    _imprimir("POST /ingesta/norma", resp.json())

    resp = client.post("/consulta", json={"pregunta": PREGUNTA_INDEXADA})
    resp.raise_for_status()
    _imprimir(f"POST /consulta (indexada): {PREGUNTA_INDEXADA}", resp.json())

    resp = client.post("/consulta", json={"pregunta": PREGUNTA_NO_INDEXADA})
    resp.raise_for_status()
    _imprimir(f"POST /consulta (NO indexada): {PREGUNTA_NO_INDEXADA}", resp.json())


if __name__ == "__main__":
    main()
