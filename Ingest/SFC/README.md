# Scraper de conceptos/fallos/jurisprudencia — Superfinanciera

Segundo corpus para el mismo stack del RAG tributario (Postgres/pgvector en
Neon, FastAPI, Voyage AI, Claude Sonnet), no un proyecto aparte. Corpus
independiente: no se mezcla en las mismas búsquedas que el tributario.

## Validado contra el sitio real (2026-09-16)

- El catálogo jurídico vive en un sistema ABCD/CDS-ISIS (bibliotecario, no
  una API), en `buscar_integrada.php`. Es HTML estático server-rendered —
  no hace falta Playwright.
- URL + parámetro real de filtrado por colección:
  `?base=juris&Opcion=libre&coleccion=<codigo>|<etiqueta>|TM_`
  con `ac` = Doctrina y conceptos, `af` = Fallos jurisdiccionales,
  `aj` = Jurisprudencia financiera.
- **Conteo exacto por colección** (leído del texto "N registros" que trae
  cada página de resultados): `ac` = 3.431, `af` = 14.466, `aj` = 807.
  Total: 18.704.
- **Paginación resuelta.** El enlace "Próxima" (`javascript:ProximaPagina`)
  es cosmético — esa función no existe en ningún script que carga la
  página. Lo que funciona de verdad (confirmado contra la primera, una
  intermedia y la última página de las tres colecciones) es un POST a
  `buscar_integrada.php` replicando los campos ocultos del formulario de
  resultados, avanzando `desde` de 25 en 25. Implementado en
  `obtener_pagina()` / `raspar_coleccion()` en `scraper.py`.
- **Parser validado contra HTML crudo real** de las tres colecciones,
  incluida su última página. Se encontraron y corrigieron dos huecos
  reales:
  - La colección `aj` usa la etiqueta `Sentencia:` (no `Concepto:`/`Fallo:`)
    para el número de documento — no estaba en `CAMPOS_CONOCIDOS`, así que
    ningún registro de jurisprudencia tenía `numero_documento`/`fecha_texto`.
  - Los `Fallo:` de la colección `af` usan un formato de fecha distinto
    (`"NUMERO de Enero 23 de 2020"`, sin la palabra "del") al de `ac`/`aj`
    (`"NUMERO del 23 de enero de 2020"`); el separador de fecha original
    solo reconocía el segundo formato.
  - De paso se agregó `otros_autores` (magistrado ponente), un campo real
    del sitio que no estaba mapeado.
- La mayoría de los Fallos (~80% en la muestra revisada) tienen como
  "Acceso web" un **archivo de audio**, no texto — es la grabación de la
  audiencia. Decisión tomada: para esos, guardar solo el resumen
  (`tiene_texto_completo = false`), sin transcripción por ahora.
- El HTML llega en **ISO-8859-1**, no UTF-8. Hay que decodificar
  explícitamente o las tildes/Ñ salen corruptas.
- Estructura de campos por tipo de registro confirmada (ver `parser.py`):
  Concepto/Fallo/Sentencia, Expediente/Radicado, Autor Corporativo, Título
  de la norma, Documento fuente, Resumen, Notas, Temas/Materias, Otros
  autores, Acceso web.
- Unas pocas colisiones de título dentro de `aj` (2 de 807 en la muestra
  completa) son registros distintos del propio catálogo (radicados/fechas
  distintos), no duplicados de la paginación — el índice único de
  `schema.sql` sobre `(tipo_documento, numero_documento)` ya los cubre.

## Censo de formatos de `ac` (2026-09-16) y extractores

Antes de ingerir texto completo a escala se hizo un censo completo (no
muestra) de los 3.431 registros de `ac`, detectando el formato real del
archivo por firma de bytes (ver `censo_formatos.py` /
`censo_formatos_ac.jsonl`). Resultado: el formato del archivo sigue la
época de publicación del sitio, **salvo un detalle no obvio** — hay dos
bloques separados de `.doc` binario (OLE), no uno solo:

| Formato | Rango(s) de años | Extractor |
|---|---|---|
| `doc_ole` (.doc binario, OLE) | **1994-1998 y 2009-2013** (dos bloques, no continuo) | `antiword` (sistema) |
| `html` | 1999-2005 | `bs4` |
| `pdf` (con capa de texto real, no escaneado) | 2006-2008 (+ un lote suelto en 2024) | `pypdf` |
| `docx` | 2010-2026 (mayoría del corpus reciente) | `zipfile`/`xml.etree` (stdlib) |

El segundo bloque de `doc_ole` (2009-2013) **no es un error de
clasificación**: se verificó contra 4 archivos reales descargados
(firma de bytes `D0 CF 11 E0 A1 B1 1A E1` + `file` confirmando
"Name of Creating Application: Microsoft Office Word", fechas de
creación reales de 2013). La SFC volvió a guardar como `.doc` durante
esos años antes de pasar a `.docx` en 2014 — un hecho de la fuente, no
un artefacto del censo.

Los 4 extractores (`extraer_texto_archivo` en `scraper.py`, dispatcheado
por firma de bytes) están validados contra 14 archivos reales descargados
del sitio (4 html de 2005, 4 pdf de 2008, 6 doc_ole repartidos entre
1994-1998 y 2009-2013), comparando el texto extraído contra el
título/Concepto/Síntesis/cuerpo visibles en cada archivo original.

**Dependencia nueva y con implicación de despliegue:** `doc_ole` usa
`antiword` (paquete del sistema, no pip) vía subprocess porque no hay
librería pura Python confiable para el formato binario legado de Word.
No hay equivalente puro-Python probado — si el entorno de producción no
puede instalar paquetes del sistema (`apt-get install antiword`), ese
~26% del corpus (898/3.419 documentos con archivo) se ingerirá sin
`texto_completo` (queda `tiene_texto_completo=false`, degradación
silenciosa vía el `try/except` de `_extraer_texto_doc_ole`, no error).
Confirmar esto contra el entorno de despliegue real antes de escalar.

## robots.txt y términos de uso (verificado 2026-09-16)

- `robots.txt` no restringe `/ABCD/` (solo excluye `/ErrorPages`,
  `/backup`, `/info`); el endpoint que usa el scraper
  (`/ABCD/superfinanciera/php/buscar_integrada.php`) no está bloqueado.
- Términos de uso reales (documento .docx enlazado desde la página de
  "Políticas web" del sitio, no la URL genérica `/terminos-y-condiciones`
  que devuelve 500): con base en la Ley 1712 de 2014 (transparencia), los
  datos del portal son públicos y su "uso, aprovechamiento y/o
  transformación" —incluida "extracción" y "compilación"— está
  explícitamente autorizado "de forma libre y sin restricciones", sin
  mención alguna a bots/crawlers/scraping ni límites de frecuencia. La
  única obligación es la **cita textual exacta**: *"Fuente:
  Superintendencia Financiera de Colombia www.superfinanciera.gov.co"* +
  mencionar la fecha de última actualización de los datos cuando el dato
  original la incluya (el catálogo no expone esa fecha por registro, de
  ahí `fecha_extraccion` como proxy — ver `schema.sql`), y no
  "desnaturalizar" ni alterar los metadatos de la fuente.
  `fuente_atribucion` en `schema.sql`/`ingest_pilot.py` **tenía el prefijo
  "Fuente: " faltante** respecto a la cita exigida — corregido.

## Corrida real cancelada en página 110 (2026-09-16, run 35153542138)

Se lanzó la ingesta completa de `ac` (138 páginas) vía `scraper-sfc.yml` y
se canceló manualmente tras llegar a la página 111 (~2.775 registros
raspados). Verificado post-mortem contra Neon y el log del run:

- **`documentos_sfc` sigue en 100 registros**, todos con `embedding` no
  nulo y `texto_completo` completo — cero registros nulos o a medias.
  Esos 100 son de una corrida piloto local anterior (`creado_en` entre
  15:38:31 y 15:39:53 UTC), **no** de esta corrida cancelada: en ese
  momento `ingest_pilot.py` envolvía el loop completo de embed+insert de
  *todas* las páginas raspadas en una sola transacción
  (`with engine.begin() as conn:`), así que cancelar el job a mitad de
  camino hacía rollback atómico — no podía quedar un insert parcial ni un
  embedding nulo, pero tampoco quedaba nada del progreso raspado. **Fix
  aplicado (2026-09-16):** `raspar_coleccion` ahora es un generador que
  yieldea página por página, y `ingestar_pilotos` hace `engine.begin()` +
  commit por página en vez de para toda la corrida — una cancelación
  tardía pierde como mucho una página (~25 registros), no horas de
  trabajo. Además se agregó `--pagina-inicial` (y el input
  `pagina_inicial` en `scraper-sfc.yml`) para retomar una corrida desde
  la página siguiente a la última confirmada, sin volver a
  rasear/descargar/embeber lo ya insertado. La última página confirmada
  se identifica por la línea `página N: commit OK` en el log de la
  corrida anterior.
- **`antiword` confirmado funcionando en ejecución real**, no solo
  instalado: `scraper.py` chequea `shutil.which("antiword")` en tiempo de
  ejecución y loggea si falta — ese warning no apareció en el log; y de
  los ~2.775 registros procesados (incluyendo años `doc_ole`) hubo cero
  líneas de `extraccion_fallida`, solo 13 fallos de descarga (500/502/404/
  DNS, capa de red, no de extracción). El punto de "confirmar antiword"
  del Pendiente pasa de "el paso de instalación existe en el yml" a
  "confirmado en una corrida real".

## Ingesta completa de `ac` (2026-09-17, run 35162789588)

Con el fix de commit-por-página ya en `main`, se relanzó la ingesta
completa de `ac` vía `scraper-sfc.yml` (workflow_dispatch, iniciada
2026-09-16T23:33 UTC, ~1h7m, status success). Verificado directo contra
Neon (2026-09-18): `documentos_sfc` tiene **3.392 registros**, todos
`tipo_documento='concepto'` (= `ac`) y todos con `embedding` no nulo;
3.374 con `tiene_texto_completo=true`, 13 `descarga_fallida`, 5
`sin_archivo`, cero `extraccion_fallida`/`formato_no_reconocido`. El
catálogo reporta 3.431 registros totales para `ac` — la brecha de 39
registros se investigó a fondo (ver siguiente sección): confirmada como
deduplicación real por el índice único, con causa raíz identificada.

## Investigación de la brecha `ac`: 3.431 (catálogo) vs 3.392 (BD) — 2026-09-18

**Causa confirmada:** el censo completo de `numero_documento` tiene
exactamente 39 valores duplicados (3.431 registros → 3.392 valores
únicos), y el índice único `uq_documentos_sfc_tipo_numero` +
`ON CONFLICT ... DO NOTHING` en `ingest_pilot.py` descarta en silencio
el segundo insert de cada par — sin error, sin log, por diseño. Cero
registros con `numero_documento` nulo/vacío, cero inserts fallidos sin
reintentar en el log de la corrida (run 35162789588): el mecanismo es
exactamente el índice único, no un bug de inserción.

**De los 39 pares, no todos son el mismo documento.** Cruzando el
`numero_documento` extraído del campo estructurado del catálogo contra
el número citado dentro del texto del título de cada registro (ej.
"Concepto No. 2008038350-001 del..."), y re-raspando el catálogo
completo (3.431 registros, no solo los pares) para revisar el registro
inmediatamente anterior de cada caso, aparece un **bug de captura del
propio sitio de la SFC**: al cargar una entrada nueva, a veces queda
copiado sin actualizar el valor de la entrada anterior — a veces en el
campo estructurado `numero_documento`, a veces en la cita dentro del
título — nunca en dirección constante. Esto se extendió más allá de
los 39 pares: sobre los 3.431 registros completos hay **35 casos**
donde campo y título no coinciden (27 no formaban parte de los 39
pares originales, porque su `numero_documento` de campo no colisiona
con ningún otro registro existente — el dato queda simplemente
incorrecto, sin causar una fila duplicada visible).

**Corrección aplicada:** 14 de esos casos se verificaron
individualmente contra el registro anterior en el orden del catálogo
(firma inequívoca: el campo corrupto coincide exactamente con el
`numero_documento` del registro previo, o el mismo documento aparece
una sola vez con el campo truncado/con un dígito mal tecleado) y se
cargaron como una lista de excepciones puntual y hardcodeada —
**no una heurística general** — en
`CORRECCIONES_NUMERO_DOCUMENTO` (`ingest_pilot.py`), aplicada por
`(numero_documento, url_archivo)` justo antes del insert. Esto corrige
el dato para una futura re-ingesta (no modifica retroactivamente los
3.392 registros ya cargados en Neon; una re-ingesta completa o un
backfill puntual de estos 14 documentos sigue pendiente de ejecutar).

**Casos conocidos sin corregir (requieren revisión manual, no forzados
a ninguna regla automática):**
- `2002028975-2` vs `2002028975-3` (concepto "Inversiones de las
  entidades financieras"): un dígito de diferencia en el sufijo, sin
  la firma de copia del registro vecino que confirma los otros 14 — no
  hay forma de determinar automáticamente cuál valor es el correcto.
- `2024096444-001` ("Contratos de uso de red" / "Habeas Data"): el
  contenido del título para este registro fue inconsistente entre dos
  raspados hechos la misma noche con minutos de diferencia — posible
  inestabilidad de orden/paginación del catálogo en vivo entre
  corridas, no solo un typo. Necesita re-verificación antes de decidir
  cualquier corrección.
- `"Concepto interno"`: dos (o más) conceptos internos genuinamente
  distintos comparten literalmente esta misma etiqueta genérica sin
  número propio — no es un dato mal tecleado que se pueda "corregir" a
  un número real; requeriría una estrategia de desambiguación distinta
  (ej. una clave artificial) si se decide priorizarlo.
- Quedan además casos dentro de los 39 pares originales que no se
  revisaron en tanto detalle como los 14 corregidos ni como los 3
  anteriores — la investigación se detuvo aquí deliberadamente: el
  problema real afecta a lo sumo ~25-39 documentos de 3.431 (bien por
  debajo del 1% del corpus `ac`), y no justificaba construir
  heurísticas cada vez más específicas la misma noche.

## Pendiente antes de escalar a las ~750 páginas totales (`af`/`aj`)

- `ac` ya está completo — no pendiente. Los 14 documentos recuperables
  por `CORRECCIONES_NUMERO_DOCUMENTO` no están todavía en la BD (el fix
  es para la próxima re-ingesta); ejecutar esa re-ingesta o un backfill
  puntual sigue pendiente si se prioriza.
- Decidir throttling final (`--pausa`, por defecto 1s/página) para no
  saturar el sitio en una corrida de producción a mayor escala.
- Extender el censo de formatos a `af`/`aj` (por ahora solo se censó
  `ac`) antes de ingerir texto completo de esas dos colecciones. El
  mismo bug de captura de `numero_documento` (ver sección anterior)
  probablemente también afecta a `af`/`aj` — conviene tenerlo presente
  al revisar sus censos, aunque no se investigó ahí todavía.
- Casos ambiguos de `ac` sin corregir (ver sección anterior): revisión
  manual pendiente, sin urgencia (<1% del corpus).

## Cómo seguir

```
pip install requests beautifulsoup4 pypdf --break-system-packages
sudo apt-get install -y antiword   # requerido para texto completo de .doc legado
python scraper.py --dry-run --coleccion ac --paginas 3
```

Con el parser, la paginación y los 4 extractores de texto completo ya
validados, el siguiente paso es aplicar `schema.sql` en la misma base
Neon del RAG tributario y conectar el pipeline de embeddings (mismo
modelo Voyage, mismo cliente Claude para generación) apuntando a
`documentos_sfc` como segundo corpus — separado del tributario también a
nivel de backend/frontend (selector de corpus, sin mezclar resultados de
búsqueda).
