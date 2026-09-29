# Ingesta de la Circular Básica Financiera (CBF) — plan

Tercer corpus para el mismo stack del RAG tributario/SFC (Postgres/pgvector
en Neon, FastAPI, Voyage AI, Claude Sonnet). Corpus independiente: no se
mezcla en las mismas búsquedas semánticas que `norma` (tributario) ni
`documentos_sfc` (doctrina/jurisprudencia). A diferencia de `documentos_sfc`
(doctrina, no vinculante), `normas_cbf` es **norma vigente**, de obligatorio
cumplimiento.

Este README se escribe antes de ejecutar el pipeline (no solo de memoria)
para que el plan quede en disco y sobreviva a un reinicio de sesión.

## Investigado hasta ahora

**Corrección importante (2026-09-22): `apiCbf`/`capituloXParteBorrador`/
`download-zip` NO EXISTEN.** Se investigó en vivo contra el sitio real
(navegando la página pública de la CBF y descargando los archivos) y no
hay ningún API dinámico: es una página CMS estática normal, igual de
simple que el mecanismo de `app/ingest/dian_scraper.py`. Confirmado:

> **Actualización (2026-09-29): `apiCbf` sí existe, pero no compite con
> el mecanismo de arriba.** Está definido en el bundle Angular del
> visualizador de la CBJ (`/visualizadorCBJ/main.js`, `CBF_ENPOINT =
> serviceHost + '/apiCbf'`, con `capituloXParteBorrador`, `download-zip`,
> etc.) y responde 200 con el header `api-key` estático del visualizador
> (`.../sfcservices/api-circular-basica/api-circular-basica/apiCbf/...`).
> Verificado en vivo: `consultarPartesActivas/1` devuelve solo metadata
> de la Parte (título, fechas, `descripcion: "N/A"`), y
> `capituloXParteBorrador/1` devuelve los 4 capítulos de la Parte 1 con
> `descripcion` vacía — índice + notas de vigencia (P1.C4 trae la suya),
> sin texto narrativo a nivel de capítulo. No se revisaron los niveles
> inferiores (sección/agrupador) ni `download-zip` de `apiCbf`. Lo de
> 2026-09-22 ("no existen") fue una conclusión errada sobre la existencia
> del API; la página CMS + `.docx` vía `loader.php` sigue siendo la
> fuente usada y verificada, y no se cambia.

- Las 4 Partes completas (con sus capítulos y secciones) viven en **una
  sola página**: `.../publicaciones/10116084/circular-basica-financiera-
  circular-externa-004-de-2026/`, como una tabla HTML con jerarquía
  Parte→Capítulo→Sección vía `rowspan` (sin JS, sin API, sin API key).
  Cada capítulo/sección/anexo es un link `loader.php?lServicio=Tools2&
  lTipo=descargas&lFuncion=descargar&idFile=<N>` a un `.docx` real
  (confirmado: `Content-Disposition: attachment; filename="P2.C9 -
  Esquema de Pruebas de Resistencia (EPR).docx"`, formato Word 2007+).
- Las notas de vigencia (futura/condicionada) están como **texto plano
  server-rendered** junto al link del capítulo/sección, en tres patrones
  observados: (a) fecha fija — "...y entra en vigencia el 3 de abril de
  2027." (P1.C4, P2.C11); (b) condicionada a un decreto, sin fecha fija —
  "...entra en vigencia en los términos previstos en el Decreto 0219 de
  2026..." (P2.C3, P3.C8); (c) **dos archivos separados** para el mismo
  capítulo — el vigente y un segundo link explícito "Versión del capítulo
  X que entrará a regir el [fecha]..." (patrón P2.C9, el único caso de
  este tipo en la tabla actual).
- El caso especial de Parte 2 / Capítulo 9 (Esquema de Pruebas de
  Resistencia) ya se investigó a fondo: hay literalmente **dos `.docx`
  separados y limpios** en la tabla (`idFile=1081456` vigente,
  `idFile=1081457` futuro) — no un solo campo HTML mezclado como asumía
  `excepcion_p2c9_vigencia.json` originalmente (esa suposición resultó
  estar basada en un mecanismo — `apiCbf` — que nunca existió). Se
  descargaron y verificaron ambos directamente:
  - `idFile=1081456` (vigente): 14.791 caracteres extraídos — coincide
    (±diferencias de espaciado) con el texto ya guardado en
    `excepcion_p2c9_vigencia.json`.
  - `idFile=1081457` (futuro): 31.953 caracteres extraídos, pero el
    `.docx` en sí trae embebida una nota administrativa corta ("Este
    capítulo entra en vigencia el 1 de enero de 2028 en virtud de lo
    expuesto en la Circular Externa 021 de 2025. Entre tanto, se
    mantienen las instrucciones vigentes en materia de pruebas de
    resistencia.") **duplicada tres veces seguidas** (y la propia frase
    duplicada dentro del mismo párrafo — artefacto del documento fuente,
    no de la extracción) entre el encabezado y el cuerpo real, que repite
    el encabezado ("PARTE 2 / CONTROLES DE LEY... / CAPÍTULO 9 /
    ESQUEMA...") una segunda vez justo antes de "INTRODUCCIÓN 2.9.1.".
    Punto de corte robusto: la **segunda aparición** del encabezado del
    capítulo, no un offset fijo — ver `scraper.py:separar_nota_futura`.
- El texto de la versión "vigente" se descarga directo del `.docx` vía
  `loader.php?...idFile=<N>`, sin pasar por ninguna API intermedia.

## Fuente de datos

Una sola página HTML estática con las 4 Partes completas (Administración
de riesgos; Controles de ley y asuntos prudenciales; Información
financiera y esquemas de reporte; Otras disposiciones), parseada por
jerarquía `rowspan` para reconstruir Parte→Capítulo→Sección, más descarga
directa de cada `.docx` vía `loader.php?...idFile=<N>`. Sin API, sin
`download-zip`, sin `capituloXParteBorrador` — ver corrección arriba.

## Esquema — `normas_cbf` (`schema.sql`)

Tabla espejo de `documentos_sfc`, con jerarquía Parte/Capítulo/Sección (más
plana que la CBJ, que además tiene Título y Numeral/Subnumeral). Campos
clave:

- `parte`, `numero_capitulo`, `seccion` (jerarquía; sin Título ni
  Numeral/Subnumeral a diferencia de CBJ).
- `fecha_vigencia_inicio`, `fecha_vigencia_fin`.
- `estado_vigencia`: `vigente` | `vigencia_futura` | `vigencia_condicionada`.
- Debe poder representar **dos registros** para el mismo capítulo cuando
  aplica el patrón de dos-archivos (visto hoy solo en P2.C9: vigente +
  versión futura ya publicada como `.docx` separado), usando
  `excepcion_p2c9_vigencia.json` como fuente ya verificada para ese caso
  puntual en vez de re-derivar la separación nota/cuerpo en caliente en
  cada ingesta (ver "Investigado hasta ahora").
- `id_archivo_cbf`: el `idFile` real de `loader.php` (no un id de API que
  no existe) — permite volver a descargar/depurar un archivo puntual sin
  recorrer las 4 Partes completas.
- `tipo_registro` (decidido 2026-09-22, tras revisar el dry-run):
  `articulo` (texto narrativo fragmentado por numeral, el caso normal) |
  `anexo_zip` (un Anexo real es un `.zip` de plantillas/formatos, no
  `.docx` — confirmado en el dry-run; se registra la fila con
  `url_archivo`/`parte`/`numero_capitulo` para no perder el rastro de que
  existe, pero sin `texto`/`embedding`) | `reservado` (el capítulo existe
  en la tabla de la CBF pero su contenido real es un placeholder "Espacio
  reservado", ej. Parte 3 / Capítulo 3 — se ingiere igual, marcado
  explícitamente, no se excluye).
- `numero_capitulo` es nullable: los 2 anexos "de cierre" heredados de la
  CBCF (Parte 4, `idFile` 1000238/1000239) no cuelgan de ningún capítulo.

## Pipeline (`Ingest/CBF/`)

1. `schema.sql` — la tabla de arriba.
2. `scraper.py` — descarga vía `download-zip` + detección de vigencia vía
   `capituloXParteBorrador`.
3. `prototipo_fragmentacion_numeral_cbf.py` — dry-run de **solo reporte**
   sobre las 4 Partes completas, para calibrar umbrales de fragmentación y
   detectar capítulos problemáticos antes de fragmentar de verdad:
   numerales por capítulo, fragmentos anormalmente largos/cortos, y
   cualquier caso que se parezca al patrón de P2.C9. **Punto de parada**:
   se revisa el reporte con el usuario antes de tocar `ingest_pilot.py`.
4. `ingest_pilot.py` — ingesta real, usando `excepcion_p2c9_vigencia.json`
   para ese caso especial en vez de derivar del `notaVigencia` en caliente.
5. `app/models.py` — modelo `NormaCBF` de solo lectura (espejo de
   `DocumentoSFC`).
6. `app/agent.py` — `buscar_fragmentos_relevantes_cbf` +
   `_formatear_contexto_cbf` + `_fuente_dict_cbf`, integrados en
   `responder_pregunta_sfc`. Puede integrarse ya con CBF solo, dejando el
   bloque CBJ vacío/condicional hasta que exista esa tabla.
7. Repetir los pasos 1-5 para la Circular Básica Jurídica (CBJ) una vez
   validado el enfoque de fragmentación con su propio dry-run.

## Prompt de sistema combinado

Reemplaza `SYSTEM_PROMPT_SFC` (mismo endpoint `/consulta-sfc`):

- Distinción de tres niveles: `documentos_sfc` (`tipo_documento="concepto"`)
  es doctrina, no vinculante; `normas_cbf`/`normas_cbj` es norma vigente,
  de obligatorio cumplimiento.
- Cuando un concepto interpreta una norma relacionada: si la pregunta del
  usuario es sobre el **contenido o alcance de una norma**, cita la norma
  primero y el concepto como interpretación después. Si la pregunta es
  sobre **qué ha interpretado o resuelto la Superfinanciera en un caso
  concreto**, el concepto encabeza la respuesta y la norma aparece como su
  fundamento — no invertir ese orden mecánicamente en todos los casos; el
  criterio es el tipo de pregunta, no una regla fija de qué va primero.
- La regla de `estado_vigencia` ya existente para `norma` (tributario) se
  extiende igual a `normas_cbf`/`normas_cbj`: si es `vigencia_futura` o
  `vigencia_condicionada`, advertirlo explícitamente, nunca presentarlo
  como aplicable hoy.
- Limitación del régimen de transición, como regla **explícita en el
  prompt** (no solo en este README, porque el modelo no lee el README en
  tiempo de respuesta): "Este corpus no captura circulares puntuales de
  2023-2024 que puedan mantener vigencia residual bajo la cláusula de
  salvaguarda de la Circular Externa 006 de 2025 (régimen de transición).
  Si la pregunta del usuario depende de vigencia normativa reciente o de un
  régimen de transición específico, menciona esta limitación explícitamente
  antes de responder con lo que sí está indexado."
- El mismo texto de limitación va también en `Ingest/CBJ/README.md` cuando
  se cree esa ingesta, sección "Limitaciones conocidas".

## Resultado del dry-run (paso 3, 2026-09-22)

`prototipo_fragmentacion_numeral_cbf.py` corrió contra las 4 Partes reales
(62 archivos descargables). Dos bugs reales del parser se encontraron y
corrigieron **durante** este dry-run (exactamente su propósito) — ver
`scraper.py` para el detalle:

- El grid-reconstruction repetía el link de "Anexos" una vez por cada fila
  cubierta por el `rowspan` de un capítulo con secciones (ej. 5 veces para
  un capítulo de 5 secciones) — corregido con seguimiento de identidad de
  celda (`es_nueva`).
- Un capítulo sin link propio (contenido solo en sus Secciones, ej.
  Capítulo 10 de la Parte 2) no actualizaba el "capítulo actual", así que
  sus Secciones quedaban mal atribuidas al capítulo anterior — corregido
  desacoplando el tracking de `numero_capitulo`/`nombre_capitulo` de si el
  bloque tiene o no un archivo descargable propio.

Hallazgos sobre el contenido real (para calibrar `ingest_pilot.py`):

- **La profundidad de los numerales no es fija.** La mayoría de capítulos
  usa "Parte.Capítulo.Numeral" (3 niveles, ej. "2.9.1."), pero los
  capítulos con Sección usan un nivel más: "Parte.Capítulo.Sección.Numeral"
  (4 niveles, ej. "2.4.2.1." — confirmado en Parte 2 / Capítulo 4 /
  Sección 2). El regex de detección se ajustó a profundidad variable
  (3 a 5 niveles) — ver `scraper._RE_NUMERAL_LINEA`.
- **Los "Anexos" NO son `.docx`** — son `.zip` (confirmado: firma `PK`,
  `Content-Disposition` con nombres como `"Anexos parte1 cap1.zip"`,
  `"ANEXO1.zip"` de hasta 10 MB). Son plantillas/formatos tabulares, no
  texto narrativo — quedan **fuera de alcance** de la fragmentación por
  numeral y de `normas_cbf` tal como está diseñada la tabla; si se quieren
  indexar en el futuro necesitan su propio tratamiento (probablemente
  fuera del RAG semántico, son formularios, no texto).
- **Parte 3 / Capítulo 3** ("Esquemas de reporte de información a la SFC")
  está genuinamente **vacío/reservado**: 158 caracteres, contenido literal
  "[ ] Espacio reservado" repetido — no un fallo de extracción. No
  ingerir como si tuviera texto real.
- **3.110 numerales detectados** en 51 de los 52 archivos narrativos
  (min 13, máx 14.514, promedio 544, mediana 398 caracteres por
  fragmento). Fragmentos "anormalmente largos" (>4.000 caracteres, un
  umbral inicial arbitrario para el reporte, no necesariamente el umbral
  final de ingesta) aparecen en ~15 archivos — típicamente un solo
  fragmento atípico por archivo (ej. un numeral con una tabla larga
  embebida), no un patrón sistemático de mala detección.
- Parte 1 / Capítulo 1 / Sección 3 tiene 20 fragmentos <40 caracteres —
  el único caso con varios fragmentos cortos a la vez; vale la pena
  revisarlo a mano antes de decidir si el umbral mínimo del reporte
  (40 caracteres) es real o esos numerales son legítimamente cortos
  (ej. definiciones de una línea).
- El patrón de dos-versiones (P2.C9) sigue siendo el **único** caso de su
  tipo en las 4 Partes — el detector genérico ("encabezado repetido 2+
  veces") no encontró ningún otro candidato.

**Revisión de los "fragmentos largos" y "cortos" con el usuario
(2026-09-22), con ejemplos reales — no se decidió un umbral en abstracto:**

- Los 3 fragmentos largos revisados (P2.C7 14.514c, P1.C1 Sec3 9.710c,
  P2.C4 Sec2 6.114c) son **tablas reales embebidas dentro de un solo
  numeral**: una tabla de ponderación de activos por riesgo (P2.C7), la
  tabla de clasificación de líneas de negocio tipo Basilea (P1.C1 Sec3),
  y una tabla de componentes del patrimonio básico (P2.C4 Sec2). No es un
  bug del detector — partir estas tablas a la mitad rompería su
  coherencia. Conclusión: no forzar un tope de longitud que fragmente
  tablas; un umbral "largo" sirve solo para **reportar** casos a revisar,
  no para recortar automáticamente.
- Los 20 fragmentos cortos de P1.C1 Sección 3 eran en su mayoría (19/20)
  un **falso positivo real del detector**: una tabla de taxonomía de tipo
  de evento de riesgo operativo (categorías "1." a "7.", con subitems
  "X.Y"/"X.Y.Z") embebida dentro de un numeral real de la sección, cuya
  numeración interna también matcheaba el patrón "N.N.N" del detector.
  **Corregido**: un marcador solo cuenta como numeral real si además
  empieza con el prefijo `{parte}.{capítulo}.` del propio archivo (ver
  `scraper._RE_NUMERAL_LINEA` y
  `prototipo_fragmentacion_numeral_cbf.py:_numerales_y_fragmentos`). Tras
  el fix: 3.034 numerales totales (antes 3.110; -76 de ruido de
  taxonomía), P1.C1 Sec3 pasó de 20 a 1 fragmento corto.
  - **Limitación conocida sin resolver**: queda 1 falso positivo residual
    (`1.1.3` "Operaciones no autorizadas") porque coincide justo con el
    prefijo `1.1.` de la propia sección (Parte 1, Capítulo 1) — la
    primera categoría de esa misma taxonomía interna. Caso raro (1 de
    331 en ese archivo); no se construyó una heurística adicional para
    este único caso, queda para revisión manual si se prioriza.

## Pendiente

- ~~Confirmar en el paso 2 la forma exacta de `apiCbf`~~ — resuelto
  2026-09-22: no existe, ver "Investigado hasta ahora".
- ~~Ejecutar el dry-run del paso 3~~ — resuelto 2026-09-22, ver "Resultado
  del dry-run" arriba.
- Decisiones tomadas 2026-09-22 tras revisar el dry-run con ejemplos
  reales (no en abstracto) — ver "Esquema" arriba para cómo quedaron en
  `schema.sql`:
  - ~~Umbral de fragmento largo/corto~~ — no se fija un tope que
    fragmente tablas; el umbral del reporte (40/4.000 caracteres) queda
    como señal de "revisar", no como recorte automático en la ingesta.
  - ~~Anexos `.zip`~~ — se registran en `normas_cbf` como
    `tipo_registro='anexo_zip'` (parte, capítulo, `url_archivo`, sin
    texto/embedding), no se descartan ni se procesan como texto.
  - ~~Parte 3 / Capítulo 3 (reservado)~~ — se ingiere, marcado
    `tipo_registro='reservado'`, no se excluye.
- ~~Escribir `ingest_pilot.py` (paso 4)~~ — resuelto 2026-09-22:
  implementado con las reglas de `schema.sql`. Reutiliza el criterio de
  fragmentación de `prototipo_fragmentacion_numeral_cbf.py` (prefijo
  `{parte}.{capítulo}.`), detecta `reservado` por longitud+contenido
  placeholder, usa `excepcion_p2c9_vigencia.json` para la versión futura
  (falla fuerte si aparece otro `tipo="version_futura"` sin excepción
  conocida, en vez de re-derivar) y no fragmenta/recorta ningún numeral
  (solo el input de embedding se trunca a 12.000 caracteres, nunca la
  columna `texto`). Validado en seco contra el sitio real (las 4 Partes,
  62 archivos, sin escribir en Neon ni llamar a Voyage): 0 errores,
  10 `anexo_zip`, 1 `reservado` (P3.C3, 158 caracteres — coincide con lo
  documentado arriba), 3.024 `articulo` (vs. 3.034 numerales del dry-run
  de reporte — la diferencia esperada está en P2.C9 futura, cuyo texto
  viene del JSON verificado a mano en vez de derivarse en vivo; no se
  investigó numeral por numeral, la escala de la diferencia es
  consistente con esa única fuente distinta). **Corrección 2026-09-28:**
  esa explicación era incorrecta — la diferencia de 10 era un bug del
  detector de numerales, ver "Detector de numerales en línea de
  encabezado" más abajo.
## Ingesta real (2026-09-22)

`schema.sql` se aplicó en Neon (ya era idempotente desde el inicio —
`CREATE TABLE`/`INDEX IF NOT EXISTS`, sin `ALTER TABLE`, a diferencia de
`documentos_sfc` que necesitó un fix aparte para eso). Se corrió
`python ingest_pilot.py` sin flags contra las 4 Partes reales: 62/62
archivos procesados, 0 errores. Verificado directo contra Neon:
**3.035 filas** en `normas_cbf` — 3.024 `articulo` (todas con
`embedding` no nulo, 1024 dimensiones), 10 `anexo_zip` y 1 `reservado`
(ambos sin `embedding`, por diseño — nada que buscar semánticamente).

**Bug real de numeración encontrado y corregido durante la
verificación:** el conteo inicial dio 3.034, no 3.035 — un fragmento se
perdió por `ON CONFLICT DO NOTHING` (mismo mecanismo silencioso que la
brecha `ac` de SFC). Investigado: `idFile=1081481` (Parte 3 / Capítulo
11 / Sección 2, "Fondos voluntarios de pensión") trae el numeral
"3.11.2.7." **dos veces** como línea propia en el `.docx` real —
secuencia completa confirmada descargando el archivo: ...2.6, 2.7, 2.8,
2.9, 2.7(repetido), 2.10... A diferencia del caso análogo en SFC (donde
el número correcto era inequívoco por el registro vecino), acá **no
hay** un número real que asignarle a la repetición: 2.8 y 2.9 ya están
tomados por sus propios numerales legítimos — es una repetición
espuria real del documento fuente de la SFC, sin numeral correcto que
recuperar. Corrección aplicada en `CORRECCIONES_NUMERAL`
(`ingest_pilot.py`, mismo patrón que
`CORRECCIONES_NUMERO_DOCUMENTO` de SFC): la 2a ocurrencia de "3.11.2.7"
en ese archivo se etiqueta `3.11.2.7-bis` (sufijo sintético para
desambiguar sin inventar un número que no está en el documento — mismo
criterio que `dian_scraper._resolver_numeros_duplicados` para casos sin
resolución inequívoca). Backfill puntual de solo ese archivo (no una
re-ingesta completa, para no re-gastar ~3.024 llamadas a Voyage ya
insertadas): 1 fila nueva insertada. Total final confirmado: **3.035
filas**, 0 colisiones residuales, 0 `articulo` con `embedding` nulo.

## Integración en la app (pasos 5-6, 2026-09-22)

- `app/models.py`: `NormaCBF`, modelo de solo lectura sobre `normas_cbf`.
- `app/agent.py`: `responder_pregunta_sfc` ahora embebe la pregunta una
  sola vez y busca top-5 en `normas_cbf` (solo `tipo_registro='articulo'`)
  **y** top-5 en `documentos_sfc`, por separado (nunca un ranking
  mezclado entre tablas). Cada fragmento va al modelo marcado con
  `origen`. `SYSTEM_PROMPT_SFC` reemplazado por el prompt combinado de la
  sección "Prompt de sistema combinado" (tres niveles, criterio de orden
  norma/concepto según el tipo de pregunta, advertencia de
  `vigencia_futura`/`vigencia_condicionada`, y la limitación del régimen
  de transición como regla explícita — `LIMITACION_TRANSICION_CBF`).
- `app/schemas.py` / `app/main.py`: `/consulta-sfc` devuelve `fuentes`
  con discriminador `origen` (`documentos_sfc` | `normas_cbf`); nuevo
  `GET /norma-cbf/{id}` para "Ver texto completo".
- Frontend: tarjeta y modal propios para fuentes CBF (numeral, estado de
  vigencia, enlace de descarga del capítulo); las entradas viejas del
  historial sin `origen` se siguen tratando como `documentos_sfc`.

Verificado contra Neon + Claude real vía `TestClient`: pregunta sobre el
informe del RTILB → respuesta citando CBF 1.1.3.249/250/251 con texto
entre comillas; `/norma-cbf/{id}` 200 y 404 para un id inexistente.
Observación: una pregunta sobre SARLAFT trae conceptos SFC relevantes
pero fragmentos CBF solo tangenciales — esperable, SARLAFT está en la
CBJ, no en la CBF.

Prueba del criterio de orden (misma materia, dos enfoques —
reestructuración de créditos): la pregunta sobre el contenido de la norma
pone la CBF primero (1.1.2.57-61, 1.1.3.52) y los conceptos después como
interpretación no vinculante; la pregunta sobre qué ha resuelto la SFC
pone los conceptos primero y la CBF después como fundamento. Esa prueba
destapó dos bugs, corregidos: (1) `max_tokens=4096` cortaba el JSON con
10 fragmentos → `MAX_TOKENS_SFC = 12000`; (2) `fuentes` salía siempre en
orden numérico (CBF primero) aunque el texto empezara por los conceptos
→ se pide `fragmentos_citados` en orden de aparición en el texto.

**Regla 7 de `SYSTEM_PROMPT_SFC` (2026-09-22):** la prueba de orden con
provisiones de cartera mostró conceptos de 1998-1999 citando la CE 100/95 y
las CE 24/97 y 44/97 sin advertir que ya no rigen. Se agregó una regla de
prompt (no detección en código): si un concepto cita una norma anterior a la
CBF vigente, advertir que ya no rige y que el criterio puede estar
desactualizado, basándose solo en el texto de los fragmentos. Verificado:
la advertencia aparece tanto en preguntas doctrinales como normativas, y el
orden norma/concepto se mantiene.

## Detector de numerales en línea de encabezado (2026-09-28)

Hallazgo de la revisión de código (`/code-review ultra`): en la versión
futura de P2.C9 (`idFile=1081457`, texto de
`excepcion_p2c9_vigencia.json`) 10 de sus 30 numerales no van en línea
propia sino al final de una línea, pegados a un encabezado en mayúsculas
— a veces con el párrafo anterior en la misma línea:
`"INTRODUCCIÓN\xa02.9.1."`, `"…sectorial.GOBIERNO DEL EPR\xa02.9.25."`.
`_RE_NUMERAL_LINEA` solo reconocía la forma en línea propia, así que
2.9.1, 2.9.2, 2.9.5, 2.9.17-20, 2.9.23, 2.9.25 y 2.9.26 no existían como
filas: su texto quedaba pegado al numeral anterior, y el de 2.9.1 y
2.9.2 (introducción y ámbito de aplicación) entraba al preámbulo y se
repetía en **las 20 filas** del archivo — p. ej. 2.9.9 llevaba el ámbito
de aplicación completo como si fuera suyo.

**Fix en código:** `scraper.posiciones_numerales(texto, prefijo)` reconoce
ambas formas (línea propia, y numeral que cierra la línea tras un
encabezado en mayúsculas de ≥4 letras); una referencia dentro del texto
("…del párrafo 2.9.20. del presente Capítulo") no cuenta, porque no va
precedida de encabezado ni cierra la línea. `_fragmentar_por_numeral` la
usa, y es la función a reutilizar para la CBJ. (`prototipo_fragmentacion_
numeral_cbf.py` sigue con la detección vieja: es solo el reporte
histórico del dry-run, no se usa en la ingesta.)

**Verificado en seco sobre los 62 archivos (sin Voyage ni escritura):**
el detector nuevo solo cambia P2.C9 futura (20 → 30 fragmentos, 2.9.1 a
2.9.30 en orden, sin duplicados); los otros 61 archivos dan exactamente
el mismo número de filas que ya hay en Neon. Total: 3.034 — igual a los
3.034 numerales del dry-run de reporte.

**Reproceso solo de ese archivo en Neon:** en una sola transacción, se
borraron sus 20 filas y se insertaron las 30 nuevas con embedding (ids
3396-3425), todas `vigencia_futura` con la fecha 2028-01-01 y la nota del
JSON. Verificado: 2.9.1 y 2.9.2 son filas propias, ningún otro numeral
contiene su texto, sin numerales duplicados. `normas_cbf` queda en
3.045 filas (3.034 `articulo`, todas con embedding; 10 `anexo_zip`; 1
`reservado`). Prueba end-to-end: "¿a qué entidades aplica el EPR?" cita
2.9.14 vigente y 2.9.2 futura por separado, advirtiendo que la segunda
rige desde 2028.

**Preámbulo repetido — corregido en código, NO en Neon (2026-09-28):**
hasta este fix, `_fragmentar_por_numeral` anteponía a **cada** fragmento
todo el texto anterior al primer numeral del archivo (título del
capítulo y, en algunos, la nota de expedición repetida — P2.C3 la traía
4 veces en cada numeral): 3.003 filas afectadas, promedio 280
caracteres, hasta 1.009, ~33% del texto almacenado en `normas_cbf`.

Fix en `ingest_pilot.py`: el preámbulo ya no se antepone. Si es solo
encabezados (`_es_linea_encabezado`: mayúsculas, "Parte/Capítulo/…", o
subtítulo corto sin punto final) se descarta, porque esa información ya
está en `fuente`. Si tiene prosa va como fragmento propio con
`numeral=None`, primero. En la CBF eso pasa en 6 archivos, todos con la
nota "Este capítulo fue expedido mediante la Circular Externa…" (P1.C4
secciones 1 y 2, P2.C3, P2.C11, P2.C12, P3.C8); en P1.C4 y P2.C12 esa
nota no está en `nota_vigencia`, así que descartarla la perdería. Aplica
también a la CBJ (paso 7).

Verificado en seco sobre los 62 archivos (sin Voyage ni escritura): el
código nuevo produce los mismos 3.034 numerales que hay en Neon, y el
texto de cada uno es exactamente el de Neon sin el preámbulo (0
diferencias); más 6 filas de preámbulo propio → 3.040 filas `articulo`.

**⚠ Código y datos desalineados hasta el próximo re-ingest completo.**
Por decisión explícita, las filas en Neon **no** se regeneraron:
- 3.003 filas `articulo` en Neon siguen con el preámbulo antepuesto (y
  su embedding calculado sobre ese texto); el código actual las
  generaría sin él.
- Las 6 filas de preámbulo propio (`numeral=None`) no existen en Neon.
- Excepción: P2.C9 futura (`idFile=1081457`, 30 filas) se reprocesó con
  el fix del detector, pero todavía con el preámbulo antepuesto (~110
  caracteres de título) — también desalineada.
- Ojo: `ingest_pilot.py` inserta con `ON CONFLICT DO NOTHING`, así que
  correrlo encima de lo que hay **no** reemplaza el texto de las filas
  existentes (solo agregaría las 6 de preámbulo). El re-ingest real
  exige borrar y reinsertar `normas_cbf` (o hacer `UPDATE` de `texto` +
  `embedding`), ~3.040 llamadas a Voyage — hacerlo cuando se decida un
  re-ingest completo por otra razón.

**`fragmentos_citados` incompleto — investigado y corregido
(2026-09-28):** en la prueba de arriba la respuesta cita 2.9.3 (que sí
estaba en el contexto recuperado) pero no aparece en `fuentes`. Causa:
no es parseo — el código solo descarta índices fuera de rango y la
salida nunca vino cortada (`stop_reason=end_turn`) —, ni la regla 5: es
el modelo, que no siempre lista en `fragmentos_citados` todo lo que
nombra en el texto (repitiendo la misma pregunta 5 veces, 2 corridas
omitieron un numeral mencionado, a veces de pasada entre paréntesis). La
instrucción solo pedía "los que respaldan tu respuesta" y dejaba ese
criterio a juicio del modelo.

Fix en `app/agent.py` (dos capas): (1) el prompt exige listar todo
fragmento mencionado por numeral o número de documento; (2)
`_completar_fragmentos_citados` agrega, en orden de aparición, cualquier
fragmento del contexto cuya etiqueta esté en el texto y falte en la
lista. Si una etiqueta corresponde a más de un fragmento del contexto
(mismo numeral vigente y futuro), no se agrega: mejor omitir la tarjeta
que mostrar la versión equivocada. Verificado: 5/5 corridas seguidas con
`fuentes` completas; en una el modelo volvió a omitir 2.9.1 pese al
prompt y lo agregó el código — la capa de código es necesaria.

**Nota para CBJ (paso 7):** el mismo tipo de error de numeración del
documento fuente puede repetirse ahí — no asumir que la fragmentación
por numeral es libre de este tipo de bug sin verificar total de filas
insertadas vs. total de numerales detectados en el dry-run, como se
hizo acá.

- Repetir el proceso para CBJ (paso 7) una vez validado el enfoque con CBF
  — la CBJ sí tiene niveles Título y Numeral/Subnumeral adicionales en su
  jerarquía (ver "Esquema" arriba), y su página real (estructura de tabla,
  URL) no se ha investigado todavía; no asumir que es idéntica a la de CBF
  sin verificarlo primero.
