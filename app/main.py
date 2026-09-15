import os

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
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

# El frontend (PWA React/Vite) corre en un origen distinto al backend
# (Railway) — sin CORS, el navegador bloquea las llamadas desde el
# navegador aunque el backend responda bien. CORS_ALLOWED_ORIGINS es una
# lista separada por comas; por defecto solo habilita el puerto de
# desarrollo de Vite. En producción hay que agregar la URL real donde
# quede publicado el frontend.
CORS_ALLOWED_ORIGINS = [
    origen.strip()
    for origen in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origen.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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


@app.get("/norma/{norma_id}", response_model=NormaRead)
def obtener_norma(norma_id: int, db: Session = Depends(get_db)) -> Norma:
    """Devuelve una fila de `norma` completa (incluye `texto` íntegro) —
    usado por el frontend para el botón "Ver texto completo" de cada
    fuente citada, ya que FuenteCitada (la respuesta de /consulta) no
    trae el texto completo, solo metadata."""
    norma = db.get(Norma, norma_id)
    if norma is None:
        raise HTTPException(status_code=404, detail="Norma no encontrada")
    return norma


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
