import os

import voyageai

# Anthropic no expone un endpoint de embeddings propio; se usa Voyage AI
# (partner de embeddings recomendado por Anthropic). Debe coincidir con
# EMBEDDING_DIM en app/models.py y con la migración de la tabla `norma`.
VOYAGE_EMBEDDING_MODEL = os.environ.get("VOYAGE_EMBEDDING_MODEL", "voyage-3.5")
VOYAGE_EMBEDDING_DIM = int(os.environ.get("VOYAGE_EMBEDDING_DIM", "1024"))

_client: voyageai.Client | None = None


def _get_client() -> voyageai.Client:
    global _client
    if _client is None:
        _client = voyageai.Client()
    return _client


def embed_document(texto: str) -> list[float]:
    """Embedding para texto que se va a indexar (fragmentos de normatividad)."""
    result = _get_client().embed(
        [texto],
        model=VOYAGE_EMBEDDING_MODEL,
        input_type="document",
        output_dimension=VOYAGE_EMBEDDING_DIM,
    )
    return result.embeddings[0]


def embed_query(pregunta: str) -> list[float]:
    """Embedding para una pregunta de usuario (búsqueda semántica)."""
    result = _get_client().embed(
        [pregunta],
        model=VOYAGE_EMBEDDING_MODEL,
        input_type="query",
        output_dimension=VOYAGE_EMBEDDING_DIM,
    )
    return result.embeddings[0]
