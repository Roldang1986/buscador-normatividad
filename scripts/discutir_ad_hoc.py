"""Corre una sola pregunta contra POST /discutir usando la BD real, sin
necesidad de levantar un servidor HTTP aparte (TestClient in-process,
mismo patrón que scripts/consulta_ad_hoc.py, pero contra el modo
DISCUSIÓN en vez del modo de consulta estricta).

Se ejecuta desde el workflow .github/workflows/discutir-ad-hoc.yml
(workflow_dispatch), ya con alembic upgrade head corrido y
DATABASE_URL / ANTHROPIC_API_KEY / VOYAGE_API_KEY disponibles en el
entorno. No inserta ni modifica nada en la BD.

Uso:
    python scripts/discutir_ad_hoc.py "¿pregunta a probar?"
"""

import json
import sys

from starlette.testclient import TestClient

from app.main import app


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    pregunta = sys.argv[1]
    client = TestClient(app)
    resp = client.post("/discutir", json={"pregunta": pregunta})
    resp.raise_for_status()

    print(f"\n=== POST /discutir: {pregunta} ===")
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
