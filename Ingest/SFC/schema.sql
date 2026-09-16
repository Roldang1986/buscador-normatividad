-- Segundo corpus dentro de la MISMA base Neon/pgvector del RAG tributario.
-- No crea un proyecto ni una base de datos aparte: es una tabla más, con
-- un selector de corpus en el frontend (tributario vs. sfc).

CREATE TABLE IF NOT EXISTS documentos_sfc (
    id                    BIGSERIAL PRIMARY KEY,
    tipo_documento        TEXT NOT NULL CHECK (tipo_documento IN ('concepto', 'fallo', 'jurisprudencia')),
    numero_documento      TEXT,
    fecha_texto           TEXT,               -- tal como aparece en el sitio; parsear a DATE en un paso posterior si hace falta ordenar/filtrar por fecha
    expediente_radicado   TEXT,
    autor_corporativo     TEXT,
    titulo                TEXT,
    documento_fuente      TEXT,
    resumen               TEXT,
    notas                 TEXT,
    materias              TEXT[],             -- filtro facetado además de la búsqueda semántica
    otros_autores         TEXT[],             -- magistrado(s) ponente(s), sobre todo en jurisprudencia
    url_archivo           TEXT,
    tipo_archivo          TEXT CHECK (tipo_archivo IN ('texto', 'audio')),
    tiene_texto_completo  BOOLEAN NOT NULL DEFAULT FALSE,
    texto_completo        TEXT,               -- NULL cuando tiene_texto_completo es FALSE (ver motivo_sin_texto)
    -- Por qué tiene_texto_completo es FALSE, para no mezclar "sin texto por
    -- diseño" (audio, o el registro no trae ningún archivo) con "sin texto
    -- por fallo de extracción" (había un archivo de texto pero no se pudo
    -- extraer: formato no reconocido, extractor falló puntualmente, o
    -- -caso .doc OLE legado- `antiword` no está instalado en este entorno).
    -- NULL cuando tiene_texto_completo es TRUE. Ver scraper.py:raspar_coleccion.
    motivo_sin_texto      TEXT CHECK (motivo_sin_texto IN (
                              'audio', 'sin_archivo', 'descarga_fallida',
                              'formato_no_reconocido', 'extraccion_fallida'
                          )),
    -- Atribución obligatoria según los "Términos y condiciones" del sitio
    -- (ver Ingest/SFC/README.md): cita textual fija exigida por el sitio +
    -- fecha en que efectivamente se extrajo cada registro (el sitio no
    -- expone una fecha de "última actualización" por registro en el
    -- catálogo, así que fecha_extraccion es lo que controlamos y podemos
    -- mostrar en el frontend junto a la cita).
    fuente_atribucion     TEXT NOT NULL DEFAULT 'Fuente: Superintendencia Financiera de Colombia www.superfinanciera.gov.co',
    fecha_extraccion      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Mismo modelo/dimensión de embeddings que uses en el RAG tributario
    -- (voyage-3.5 -> 1024 dimensiones). Ajusta si allá usaste otra cosa.
    embedding             VECTOR(1024),
    creado_en             TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Migra tablas creadas con una versión anterior de este archivo (antes de
-- otros_autores/motivo_sin_texto/fuente_atribucion/fecha_extraccion):
-- CREATE TABLE IF NOT EXISTS no agrega columnas a una tabla que ya existe,
-- así que sin este ALTER el archivo no es realmente idempotente en un
-- entorno donde documentos_sfc ya existe de una corrida anterior (visto en
-- producción: la corrida de prueba con `paginas=2` falló porque la tabla ya
-- existía sin estas columnas y el CREATE INDEX de motivo_sin_texto más abajo
-- reventó contra una columna inexistente).
ALTER TABLE documentos_sfc ADD COLUMN IF NOT EXISTS otros_autores TEXT[];
ALTER TABLE documentos_sfc ADD COLUMN IF NOT EXISTS motivo_sin_texto TEXT
    CHECK (motivo_sin_texto IN (
        'audio', 'sin_archivo', 'descarga_fallida',
        'formato_no_reconocido', 'extraccion_fallida'
    ));
ALTER TABLE documentos_sfc ADD COLUMN IF NOT EXISTS fuente_atribucion TEXT NOT NULL
    DEFAULT 'Fuente: Superintendencia Financiera de Colombia www.superfinanciera.gov.co';
ALTER TABLE documentos_sfc ADD COLUMN IF NOT EXISTS fecha_extraccion TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_documentos_sfc_tipo ON documentos_sfc (tipo_documento);
CREATE INDEX IF NOT EXISTS idx_documentos_sfc_materias ON documentos_sfc USING GIN (materias);
-- Para monitorear volumen de fallos de extracción por motivo tras una
-- corrida de ingesta (ver motivo_sin_texto arriba), sin escanear la tabla.
CREATE INDEX IF NOT EXISTS idx_documentos_sfc_motivo_sin_texto
    ON documentos_sfc (motivo_sin_texto) WHERE motivo_sin_texto IS NOT NULL;
-- Índice vectorial: usa el mismo tipo (ivfflat/hnsw) y parámetros que ya
-- elegiste para la tabla del Estatuto Tributario, para mantener consistencia
-- operativa entre los dos corpus.
-- CREATE INDEX idx_documentos_sfc_embedding ON documentos_sfc USING hnsw (embedding vector_cosine_ops);

-- Evita duplicados si vuelves a correr el scraper (idempotencia por número
-- de documento + tipo, ya que un mismo número podría repetirse entre
-- colecciones distintas en teoría).
CREATE UNIQUE INDEX IF NOT EXISTS uq_documentos_sfc_tipo_numero
    ON documentos_sfc (tipo_documento, numero_documento)
    WHERE numero_documento IS NOT NULL;
