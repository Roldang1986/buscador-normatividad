-- Tercer corpus dentro de la MISMA base Neon/pgvector del RAG
-- tributario/SFC. No crea un proyecto ni una base de datos aparte.
-- A diferencia de documentos_sfc (doctrina, no vinculante), normas_cbf es
-- norma vigente, de obligatorio cumplimiento — ver la distinción de tres
-- niveles en el prompt de sistema (app/agent.py) y en Ingest/CBF/README.md.

CREATE TABLE IF NOT EXISTS normas_cbf (
    id                    BIGSERIAL PRIMARY KEY,

    -- Jerarquía Parte/Capítulo/Sección (más plana que la CBJ: sin Título
    -- ni Numeral/Subnumeral como niveles de jerarquía/TOC — ver README).
    parte                 INTEGER NOT NULL CHECK (parte BETWEEN 1 AND 4),
    nombre_parte          TEXT,
    -- NULL solo para los 2 anexos "de cierre" heredados de la CBCF
    -- (Parte 4, ej. idFile 1000238/1000239 — ver README) que no cuelgan
    -- de ningún capítulo puntual. Todo lo demás sí trae numero_capitulo.
    numero_capitulo       INTEGER,
    nombre_capitulo       TEXT,
    seccion               TEXT,               -- no todos los capítulos tienen secciones

    -- 'articulo': fragmento de texto narrativo fragmentado por numeral
    --   (el caso normal, con texto/embedding).
    -- 'anexo_zip': un Anexo real es un .zip (plantillas/formatos, NO
    --   .docx — confirmado en el dry-run, ver README), fuera de alcance
    --   de la fragmentación por numeral. Se registra la fila (parte,
    --   capítulo, url_archivo) para no perder el rastro de que existe,
    --   pero SIN texto/embedding — se decide más adelante si algún día
    --   se procesa aparte.
    -- 'reservado': el capítulo/sección existe en la tabla de la CBF pero
    --   su contenido real es un placeholder ("Espacio reservado" — ver
    --   Parte 3 / Capítulo 3 en el README). Se ingiere igual (no se
    --   excluye), marcado explícitamente para que el agente RAG no lo
    --   trate como si fuera texto normativo real.
    tipo_registro         TEXT NOT NULL DEFAULT 'articulo'
                              CHECK (tipo_registro IN ('articulo', 'anexo_zip', 'reservado')),

    -- Distingue el fragmento dentro de un capítulo fragmentado por numeral
    -- interno del texto (ej. "2.9.1", "2.9.2" — ver
    -- prototipo_fragmentacion_numeral_cbf.py). Mismo patrón que
    -- norma.numeral (app/models.py) para el corpus tributario. NULL para
    -- capítulos no fragmentados.
    numeral               TEXT,

    -- idFile real de loader.php (?lServicio=Tools2&lTipo=descargas&
    -- lFuncion=descargar&idFile=<N>) — NO un id de "apiCbf", que no existe
    -- (ver README, "Investigado hasta ahora"). Permite volver a
    -- descargar/depurar un archivo puntual sin recorrer las 4 Partes.
    -- Ej. 1081456 para Parte 2 / Capítulo 9 (versión vigente).
    id_archivo_cbf        INTEGER,

    -- Permite representar DOS registros para el mismo capítulo cuando
    -- aplica el patrón de Parte 2 / Capítulo 9 (vigente hoy + versión
    -- futura ya conocida) — ver excepcion_p2c9_vigencia.json. 'vigente'
    -- para el resto de capítulos, que no tienen versión futura conocida.
    version               TEXT NOT NULL DEFAULT 'vigente'
                              CHECK (version IN ('vigente', 'futura')),

    -- Ej. "Circular Básica Financiera Parte 2 Capítulo 9 (EPR)"
    fuente                TEXT NOT NULL,
    -- URL de descarga real del archivo (loader.php?...idFile=<N>), no un
    -- id de API — mismo nombre de columna que documentos_sfc.url_archivo
    -- para mantener la convención entre corpus.
    url_archivo           TEXT,

    -- NULL permitido solo para tipo_registro != 'articulo' (ver arriba):
    -- un anexo_zip no tiene texto que extraer, y un reservado puede
    -- guardar el placeholder o dejarse NULL, a decidir en ingest_pilot.py.
    texto                 TEXT,

    -- 'vigente': aplica hoy sin condición.
    -- 'vigencia_futura': ya se conoce el texto pero aún no rige (ej. la
    --   versión 2028 de P2.C9) — el prompt debe advertirlo explícitamente,
    --   nunca presentarlo como aplicable hoy (ver README).
    -- 'vigencia_condicionada': rige sujeto a una condición que no es
    --   simplemente una fecha (ej. hasta que ocurra un evento, o mientras
    --   dure un régimen de transición puntual).
    estado_vigencia       TEXT NOT NULL
                              CHECK (estado_vigencia IN (
                                  'vigente', 'vigencia_futura',
                                  'vigencia_condicionada'
                              )),
    fecha_vigencia_inicio DATE,
    fecha_vigencia_fin    DATE,
    -- Nota administrativa corta (ej. "Versión del capítulo 9 que entrará a
    -- regir el 1 de enero de 2028 en virtud de lo expuesto en la Circular
    -- Externa 021 de 2025"), separada del texto completo de la versión
    -- futura cuando aplica el patrón P2.C9 — NUNCA el HTML crudo de
    -- notaVigencia sin depurar (ver README, motivo del caso especial).
    nota_vigencia         TEXT,

    -- Mismo modelo/dimensión de embeddings que el resto del RAG
    -- (voyage-3.5 -> 1024 dimensiones).
    embedding             VECTOR(1024),

    fecha_ingesta         TIMESTAMPTZ NOT NULL DEFAULT now(),
    creado_en             TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Un 'articulo' siempre debe traer texto real; un 'anexo_zip' o
    -- 'reservado' puede no traerlo (ver comentario de tipo_registro).
    CONSTRAINT chk_normas_cbf_texto_segun_tipo
        CHECK (tipo_registro != 'articulo' OR texto IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_normas_cbf_parte_capitulo
    ON normas_cbf (parte, numero_capitulo);
CREATE INDEX IF NOT EXISTS idx_normas_cbf_estado_vigencia
    ON normas_cbf (estado_vigencia);
-- Índice vectorial: usa el mismo tipo (ivfflat/hnsw) y parámetros que ya
-- elegiste para las otras tablas del RAG, para mantener consistencia
-- operativa entre los tres corpus.
-- CREATE INDEX idx_normas_cbf_embedding ON normas_cbf USING hnsw (embedding vector_cosine_ops);

-- Evita duplicados si vuelves a correr el scraper/ingest: un mismo
-- (capítulo, sección, numeral, versión) no debería insertarse dos veces.
-- COALESCE también en numero_capitulo por los 2 anexo_zip de cierre de la
-- Parte 4 sin capítulo (ver comentario de la columna) — de paso, el
-- índice usa id_archivo_cbf en vez de numeral para las filas anexo_zip/
-- reservado, que no tienen numeral real.
CREATE UNIQUE INDEX IF NOT EXISTS uq_normas_cbf_capitulo_numeral_version
    ON normas_cbf (
        parte, COALESCE(numero_capitulo, -1), COALESCE(seccion, ''),
        COALESCE(numeral, ''), COALESCE(id_archivo_cbf, -1), version
    );
