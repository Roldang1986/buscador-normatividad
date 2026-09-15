# Buscador de Normatividad Tributaria (Colombia)

Backend FastAPI para un sistema de búsqueda normativa tributaria colombiana
basado en RAG (Retrieval-Augmented Generation). Todavía no tiene autenticación
ni scrapers reales; el endpoint de ingesta es manual, solo para pruebas.

## Estructura

```
app/
├── main.py       # instancia de FastAPI + endpoints (/consulta, /norma/{id}, /ingesta/norma)
├── agent.py      # agente RAG: búsqueda semántica + llamada a Claude
├── embeddings.py # cliente de embeddings (Voyage AI)
├── models.py     # modelos SQLAlchemy (tabla `norma`)
├── database.py   # engine + sesión, lee DATABASE_URL del entorno
├── schemas.py    # esquemas Pydantic
└── ingest/       # scrapers de fuentes normativas
    └── dian_scraper.py  # scraper de normograma.dian.gov.co (ver abajo)

alembic/          # migraciones de base de datos

frontend/         # PWA (React + Vite) — ver "Frontend" más abajo
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

## Despliegue en Railway

El comando de arranque de producción está declarado en `railway.json`
(`deploy.startCommand`), no como parte del código de la app:

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Railway detecta el proyecto como Python vía Nixpacks e instala
`requirements.txt` (que ya incluye `uvicorn[standard]`, necesario para
producción, no solo para `--reload` en desarrollo local).

Variables de entorno a configurar en el servicio de Railway (mismas que
`.env.example`): `DATABASE_URL`, `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`,
`INGESTA_API_KEY` (protege `POST /ingesta/norma`, ver sección Endpoints —
si falta, ese endpoint rechaza todos los requests), `CORS_ALLOWED_ORIGINS`
(necesaria para que el frontend en `frontend/` pueda llamar a la API desde
el navegador — agregar ahí la URL real donde quede publicado, separadas
por comas si hay más de una), y opcionalmente
`VOYAGE_EMBEDDING_MODEL`/`VOYAGE_EMBEDDING_DIM`.

**Las migraciones de Alembic NO se ejecutan automáticamente al arrancar
el servidor** — `startCommand` solo levanta uvicorn, sin `alembic
upgrade head` antes. Correrlas manualmente (una sola vez tras cada
migración nueva) contra la misma `DATABASE_URL` de producción:

```bash
alembic upgrade head
```

ya sea desde un shell/comando one-off de Railway, o localmente con la
`DATABASE_URL` de producción exportada. Este proyecto también corre
migraciones vía GitHub Actions en workflows puntuales (ej.
`diagnosticar-numeracion.yml`, input `ejecutar_migracion_alembic`) — ese
sigue siendo el flujo recomendado para no acoplar el arranque del
servidor web a cambios de esquema.

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

### `GET /norma/{id}`

Devuelve una fila de `norma` completa, incluido el campo `texto` íntegro
(la respuesta de `/consulta` solo trae metadata por fuente, no el texto
completo). Sin autenticación — es lectura pública, igual que `/consulta`.
404 si el id no existe. Usado por el frontend para el botón "Ver texto
completo" de cada fuente citada.

```json
// Response
{
  "id": 468, "tipo_norma": "articulo_et", "numero_articulo": "468",
  "fuente": "Estatuto Tributario art. 468", "url_fuente": null,
  "texto": "La tarifa general del impuesto sobre las ventas es del 19%.",
  "estado_vigencia": "vigente", "nota_vigencia": null,
  "fecha_ingesta": "2026-01-01T00:00:00Z"
}
```

### `POST /ingesta/norma`

Inserta manualmente una norma de prueba (calcula su embedding y la guarda).
Requiere el header `X-API-Key` con el valor de la variable de entorno
`INGESTA_API_KEY`; responde 401 si falta, no coincide, o si la variable no
está configurada en el entorno (falla cerrado, nunca abierto por defecto).
No es autenticación de usuario real — solo evita inserciones anónimas.

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

## Scraper DIAN (`app/ingest/dian_scraper.py`)

Descubre e ingiere documentos de `normograma.dian.gov.co` por sección del
índice tributario (ej. "1.1. Estatuto Tributario"), vía `scripts/
run_dian_scraper.py` (pensado para correr como workflow de GitHub Actions,
ver `.github/workflows/scraper-dian.yml`).

**Limitación estructural conocida (no es un bug, sin fix posible del lado
del scraper):** el ícono/marca de "derogado" del índice es una señal por
DOCUMENTO completo, mientras que `estado_vigencia` se calcula por
artículo individual a partir del texto. Cualquier documento con varios
artículos propios puede tener algunos derogados por normas posteriores
mientras el documento en sí sigue figurando vigente en el índice —
confirmado con datos reales, no solo en el Estatuto Tributario (el caso
extremo: 1306 artículos, 215 derogados, un solo ícono "no derogado"),
sino también a menor escala en leyes de varios artículos (ej. Ley 2277
de 2022: 153 fragmentos, 4 derogados). Un desacuerdo entre el ícono del
índice y el `estado_vigencia` del texto no es automáticamente indicio de
un bug de detección — depende de cuántos artículos propios tenga el
documento. Ver el docstring del módulo para más detalle.

## Frontend (`frontend/`)

PWA en React + Vite (JavaScript plano, sin TypeScript). Primera versión:
caja de pregunta contra `POST /consulta`, tarjetas de fuentes citadas
(con aviso visual si `estado_vigencia` es `modificado`/`derogado`), botón
para ver el texto completo de una fuente (`GET /norma/{id}`) en un modal,
link a la fuente oficial (`url_fuente`), historial de preguntas en
`localStorage` (no hay autenticación de usuario), y manifest +
service worker mínimos para que sea instalable.

Setup local:

```bash
cd frontend
npm install
cp .env.example .env   # ajustar VITE_API_BASE_URL si el backend corre en localhost
npm run dev
```

`VITE_API_BASE_URL` apunta por defecto a la URL de producción en Railway.
Para desarrollo contra un backend local, necesitas correr el backend con
`CORS_ALLOWED_ORIGINS` incluyendo `http://localhost:5173` (ya es el valor
por defecto de `.env.example` del backend).

Estructura:

```
frontend/
├── public/
│   ├── manifest.json   # PWA manifest
│   ├── sw.js           # service worker mínimo (cache-first solo para assets propios)
│   └── icon-*.png      # íconos placeholder — reemplazar antes de producción real
└── src/
    ├── api.js          # llamadas fetch a /consulta y /norma/{id}
    ├── useHistorial.js # hook: historial de preguntas en localStorage
    ├── App.jsx
    └── components/
        ├── CajaPregunta.jsx
        ├── Respuesta.jsx
        ├── TarjetaFuente.jsx
        ├── ModalTexto.jsx   # "Ver texto completo" (GET /norma/{id})
        └── Historial.jsx
```

No incluye ningún llamado a `POST /ingesta/norma` — ese endpoint sigue
siendo solo para uso administrativo/manual con `X-API-Key`.

## Pendiente

- Autenticación de usuario real (lo que hay hoy en `/ingesta/norma` es
  solo un API key compartido por header, no sesiones/usuarios)
- Proteger `/consulta` si se expone a más que el propio frontend
- Pasada de diseño real del frontend (hoy solo tiene layout funcional
  mínimo) e íconos de PWA definitivos (los actuales son placeholders)
