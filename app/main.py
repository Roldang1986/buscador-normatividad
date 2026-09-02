from fastapi import Depends, FastAPI
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


@app.post("/consulta", response_model=ConsultaResponse)
def consultar(payload: ConsultaRequest, db: Session = Depends(get_db)) -> ConsultaResponse:
    resultado = agent.responder_pregunta(db, payload.pregunta)
    return ConsultaResponse(**resultado)


# TODO: proteger este endpoint (autenticación/autorización) antes de exponerlo
# públicamente. Por ahora existe solo para poder probar el flujo completo de
# ingesta + búsqueda semántica + RAG sin tener el scraper real (app/ingest/).
@app.post("/ingesta/norma", response_model=NormaRead, status_code=201)
def ingestar_norma(payload: NormaCreate, db: Session = Depends(get_db)) -> Norma:
    embedding = embed_document(payload.texto)
    norma = Norma(**payload.model_dump(), embedding=embedding)
    db.add(norma)
    db.commit()
    db.refresh(norma)
    return norma
