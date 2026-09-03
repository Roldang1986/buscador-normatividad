# Buscador de Normatividad Tributaria (Colombia)

Backend FastAPI para un sistema de búsqueda normativa tributaria colombiana
basado en RAG (Retrieval-Augmented Generation). Todavía no tiene autenticación
ni scrapers reales; el endpoint de ingesta es manual, solo para pruebas.

## Estructura

```
app/
├── main.py       # instancia de FastAPI + endpoints (/consulta, /ingesta/norma)
├── agent.py      # agente RAG: búsqueda semántica + llamada a Claude
├── embeddings.py # cliente de embeddings (Voyage AI)
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
- Una API key de Anthropic (Claude) para el agente RAG
- Una API key de Voyage AI para generar embeddings (Anthropic no tiene API de
  embeddings propia; Voyage AI es su partner recomendado)

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

## Endpoints

### `POST /consulta`

Recibe una pregunta, busca los 5 fragmentos más relevantes en `norma` por
similitud coseno (pgvector) y le pide a Claude una respuesta citando fuente
exacta (`tipo_norma`, `numero_articulo`, `fuente`) para cada afirmación. Si
no hay fragmentos suficientes, responde explícitamente que no encontró
normatividad indexada, sin completar con conocimiento general.

```json
// Request
{"pregunta": "¿Cuál es la tarifa general del IVA?"}

// Response
{
  "respuesta": "...",
  "fuentes": [
    {"id": 1, "tipo_norma": "articulo_et", "numero_articulo": "468",
     "fuente": "Estatuto Tributario art. 468", "url_fuente": null,
     "estado_vigencia": "vigente"}
  ]
}
```

### `POST /ingesta/norma`

Inserta manualmente una norma de prueba (calcula su embedding y la guarda).
**Sin autenticación todavía** — ver el `TODO` en `app/main.py`; no debe
exponerse públicamente en este estado.

```json
{
  "tipo_norma": "articulo_et",
  "numero_articulo": "468",
  "fuente": "Estatuto Tributario art. 468",
  "url_fuente": null,
  "texto": "La tarifa general del impuesto sobre las ventas es del 19%.",
  "estado_vigencia": "vigente",
  "nota_vigencia": null
}
```

## Pendiente

- Autenticación (incluyendo proteger `/ingesta/norma`)
- Scrapers reales en `app/ingest/` (hoy la ingesta es manual, vía endpoint)
- Conexión real a base de datos (Neon) y despliegue
