# Buscador de Normatividad Tributaria (Colombia)

Backend FastAPI para un sistema de búsqueda normativa tributaria colombiana
basado en RAG (Retrieval-Augmented Generation). Este repositorio contiene
por ahora solo el scaffolding inicial: no hay endpoints, autenticación ni
conexión a datos reales.

## Estructura

```
app/
├── main.py       # instancia de FastAPI (sin endpoints todavía)
├── models.py     # modelos SQLAlchemy (tabla `norma`)
├── database.py   # engine + sesión, lee DATABASE_URL del entorno
├── schemas.py    # esquemas Pydantic
└── ingest/       # futuros scrapers de fuentes normativas (vacío)

alembic/          # migraciones de base de datos
```

## Requisitos

- Python 3.11+
- Una base de datos Postgres con la extensión [pgvector](https://github.com/pgvector/pgvector)
  disponible (ej. [Neon](https://neon.tech))

## Setup local

1. Crear y activar un entorno virtual:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Instalar dependencias:

   ```bash
   pip install -r requirements.txt
   ```

3. Copiar `.env.example` a `.env` y completar los valores reales:

   ```bash
   cp .env.example .env
   ```

   - `DATABASE_URL`: cadena de conexión Postgres (ej. de Neon).
   - `ANTHROPIC_API_KEY`: API key de Claude (Anthropic).

   **No** subas `.env` al repositorio (ya está en `.gitignore`).

4. Exportar las variables de entorno (o usar un gestor como `direnv` /
   `python-dotenv` según tu flujo) y correr las migraciones:

   ```bash
   export $(cat .env | xargs)
   alembic upgrade head
   ```

   La migración inicial crea la extensión `vector` y la tabla `norma`.

5. Levantar el servidor de desarrollo:

   ```bash
   uvicorn app.main:app --reload
   ```

## Modelo principal: `norma`

Representa un fragmento de contenido normativo (artículo del Estatuto
Tributario, decreto, concepto DIAN, etc.) junto con su embedding para
búsqueda semántica:

| Campo             | Descripción                                                   |
|--------------------|----------------------------------------------------------------|
| `id`               | Identificador                                                  |
| `tipo_norma`       | Ej. `articulo_et`, `decreto`, `concepto_dian`                  |
| `numero_articulo`  | Número de artículo (opcional)                                  |
| `fuente`           | Ej. "Estatuto Tributario art. 420"                              |
| `url_fuente`       | URL de la fuente original                                      |
| `texto`            | Contenido completo                                              |
| `estado_vigencia`  | Ej. `vigente`, `modificado`, `derogado`                         |
| `nota_vigencia`    | Ej. "modificado por art. 57 Ley 2277 de 2022"                   |
| `fecha_ingesta`    | Fecha de ingesta del registro                                   |
| `embedding`        | Vector de embedding (pgvector) para búsqueda semántica          |

## Pendiente

- Endpoints de la API (búsqueda, ingesta, etc.)
- Autenticación
- Scrapers en `app/ingest/`
- Pipeline de generación de embeddings y RAG con Claude
- Conexión real a base de datos (Neon) y despliegue
