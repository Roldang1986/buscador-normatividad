import os

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import agent
from app.database import get_db
from app.embeddings import embed_document
from app.models import Norma
from app.schemas import ConsultaRequest, ConsultaResponse, NormaCreate, NormaRead

app = FastAPI(
    title="Buscador de Normatividad Tributaria",
    description="API RAG para búsqueda normativa tributaria colombiana.",
    version="0.1.0",
)

INGESTA_API_KEY = os.environ.get("INGESTA_API_KEY")


def verificar_api_key_ingesta(x_api_key: str | None = Header(None)) -> None:
    """Protege /ingesta/norma con un API key simple por header (no es
    autenticación de usuario real, solo evita inserciones anónimas en
    `norma` desde internet). Falla cerrado: si INGESTA_API_KEY no está
    configurada en el entorno, todo request se rechaza — nunca queda el
    endpoint abierto por un despliegue sin la variable seteada."""
    if not INGESTA_API_KEY or x_api_key != INGESTA_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o faltante (header X-API-Key)",
        )


@app.post("/consulta", response_model=ConsultaResponse)
def consultar(payload: ConsultaRequest, db: Session = Depends(get_db)) -> ConsultaResponse:
    resultado = agent.responder_pregunta(db, payload.pregunta)
    return ConsultaResponse(**resultado)


@app.post(
    "/ingesta/norma",
    response_model=NormaRead,
    status_code=201,
    dependencies=[Depends(verificar_api_key_ingesta)],
)
def ingestar_norma(payload: NormaCreate, db: Session = Depends(get_db)) -> Norma:
    embedding = embed_document(payload.texto)
    norma = Norma(**payload.model_dump(), embedding=embedding)
    db.add(norma)
    db.commit()
    db.refresh(norma)
    return norma
