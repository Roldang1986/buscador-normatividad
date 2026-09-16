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
    url_archivo           TEXT,
    tipo_archivo          TEXT CHECK (tipo_archivo IN ('texto', 'audio')),
    tiene_texto_completo  BOOLEAN NOT NULL DEFAULT FALSE,
    texto_completo        TEXT,               -- NULL para fallos en audio (decisión tomada: solo resumen por ahora)
    -- Mismo modelo/dimensión de embeddings que uses en el RAG tributario
    -- (voyage-3.5 -> 1024 dimensiones). Ajusta si allá usaste otra cosa.
    embedding             VECTOR(1024),
    creado_en             TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documentos_sfc_tipo ON documentos_sfc (tipo_documento);
CREATE INDEX IF NOT EXISTS idx_documentos_sfc_materias ON documentos_sfc USING GIN (materias);
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
