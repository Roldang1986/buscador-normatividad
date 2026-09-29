# Ingesta de la Circular Básica Jurídica (CBJ) — plan

Cuarto corpus del RAG (paso 7 del plan en `Ingest/CBF/README.md`), mismo
stack que la CBF: Postgres/pgvector en Neon, FastAPI, Voyage AI, Claude.
Como `normas_cbf`, `normas_cbj` es **norma vigente**, no doctrina, y no se
mezcla en las mismas búsquedas que `norma` (tributario) ni `documentos_sfc`.

Este README se escribe antes del código (schema/scraper aún no existen) para
que lo verificado quede en disco. Todo lo de abajo se comprobó en vivo el
2026-09-29; nada se tomó de sesiones anteriores sin re-verificar.

## Fuente de datos (verificado 2026-09-29)

**No se parece a la CBF.** La CBJ se publica en un visualizador Angular
(`https://www.superfinanciera.gov.co/visualizadorCBJ/`) respaldado por una
API REST:

- Base: `https://www.superfinanciera.gov.co/sfcservices/api-circular-basica/api-circular-basica/apiCircularBasica`
- Header `api-key` estático, el mismo que usa el visualizador en cualquier
  navegador: está en `https://www.superfinanciera.gov.co/visualizadorCBJ/main.js`,
  en el objeto `environment` (campo `apikey`, junto a `serviceHost`); el
  interceptor HTTP del bundle lo envía como header `api-key`. Sin él o con
  uno falso: 401. Leerlo de ahí en cada corrida en vez de fijarlo en el
  código, por si rota.
- Jerarquía: 3 Partes, 17 Títulos (la Parte III tiene **dos** Títulos
  numerados 3, ids 117 y 121, que el API consulta por número y devuelve
  iguales), 85 capítulos, 397 numerales, 6.602 subnumerales.
- **Orden de argumentos: de lo más específico a lo más general.** Al revés
  el API responde 200 con OTRO capítulo, sin error:
  - `consultarTitulosXParte/{parte}`
  - `consultarCapituloXTitulo/{titulo}/{parte}`
  - `consultarNumeralbyCapitulo/{capitulo}/{titulo}/{parte}`
  - `consultarSubnumeralbyCapitulo/{numeral}/{capitulo}/{titulo}/{parte}`
    (devuelve todos los descendientes del numeral, aplanados)
- Texto: campo `descripcion` de capítulo/numeral/subnumeral, en base64 de un
  JSON de Quill (`{"ops":[{"insert": ...}]}`, a veces doblemente
  serializado). Los `numero` pueden traer espacios sobrantes
  (`' 4.2.2.2.1.4.1'`, `'4.2.4.3.1.5 '`): hacer `strip()` antes de usarlos
  como clave u ordenar.
- Descarga masiva: `download-zip/{idParte}` con el **id** de la Parte
  (280/284/285), no su número. Un valor desconocido (1, 2, 0, 99) responde
  200 con el ZIP de **otra** Parte — validar la carpeta `Parte X` del ZIP.
  Cada capítulo trae `.docx` + `.pdf`.

### API vs `.docx`: fidelidad verificada

Muestra de 8 capítulos (P1.T1.C2, P1.T3.C1, P1.T4.C4, P2.T2.C1, P2.T3.C2,
P3.T1.C2, P3.T4.C6, P3.T6.C1; ~151.800 tokens del `.docx`): el texto de
`descripcion` decodificado, ordenado por numeral, es **idéntico carácter por
carácter al del `.docx` ignorando espacios**, en los 8. Cero diferencias de
contenido. Las únicas diferencias (26) son palabras que el `.docx` pega
("microcréditopara") y el API separa: el API es igual o más limpio.

El API además cubre lo que el ZIP no: el `.docx` de **P2.T4.C2**
(aseguradoras y reaseguradoras) viene de 0 bytes en el ZIP oficial, pero su
texto está en el API (288.237 caracteres en 596 de 643 elementos) y en el
PDF del ZIP (112 páginas con capa de texto; coincide con el API en 39/40
frases muestreadas).

## Limitaciones conocidas

### Cambios aún no vigentes sin marca en la fuente (limitación estructural)

**El texto de la CBJ puede incluir modificaciones que todavía no rigen, sin
ninguna nota ni marca que lo indique.** No es un caso aislado que se pueda
corregir a mano; es cómo la SFC publica la fuente:

- **CE 008 de 2026** (1-sep-2026) rige desde el **30-oct-2026** (instrucción
  CUARTA). Su instrucción PRIMERA (inciso en P3.T1.C2 subnumeral 2.1) está
  solo en la nota de vigencia; pero las instrucciones SEGUNDA y TERCERA
  (subnumerales 2.2.5, 2.4 y 2.5 del mismo capítulo) **ya están incorporadas
  en el texto base** (API y `.docx`), sin nota, un mes antes de regir.
- Las notas de vigencia del API (`notaVigencia`) tampoco son un inventario
  completo ni necesariamente actualizado: **CE 006 de 2026** (11-may-2026)
  aplazó al 1-ene-2028 las instrucciones CUARTA/QUINTA/SEXTA de la CE 013 de
  2025 sobre P2.T4.C2, pero ninguna nota cita la CE 006, y 7 de las 132
  notas de derogatoria todavía dicen "1 de enero de 2027".
- Los campos de fecha del API (`inicioVigencia`, `finVigencia`) **no son
  una fuente válida de vigencia**: P3.T3.C4 está derogado por la CE 014 de
  2025 con `finVigencia = null`; hay `finVigencia = 2188-12-31` en
  P2.T4.C2 s3.4.6.1.2.1.

Consecuencias de diseño:

- El estado de vigencia se deriva del texto de la nota **y** de la circular
  que la origina, verificado caso por caso; nunca se infiere de un campo de
  fecha del API.
- Aun así, un fragmento sin nota puede no estar vigente. Por eso
  `app/agent.py` lleva la advertencia `ADVERTENCIA_VIGENCIA_CBJ` **en toda
  respuesta que cite la CBJ**, no solo cuando hay nota: regla 9 de
  `SYSTEM_PROMPT_SFC` y, como garantía en código,
  `_asegurar_advertencia_cbj`, que la antepone si el modelo la omite. Es más
  fuerte que la limitación de la CBF (que es condicional y solo de prompt).

  > "El texto de la Circular Básica Jurídica puede incluir modificaciones
  > recientes que aún no han entrado en vigencia, sin ninguna marca que lo
  > indique en la fuente. Para decisiones donde la fecha exacta de vigencia
  > sea crítica, verifica directamente contra las circulares externas más
  > recientes de la SFC."

- **No investigado a fondo (decisión explícita, 2026-09-29):** detectar
  sistemáticamente otras circulares con cambios ya incorporados sin nota
  exigiría revisar todas las circulares externas recientes de la SFC que
  modifican la CBJ. Queda documentado como limitación, no resuelto.

### Régimen de transición (heredada del plan de la CBF)

El plan de la CBF pedía repetir aquí su limitación: "Este corpus no captura
circulares puntuales de 2023-2024 que puedan mantener vigencia residual bajo
la cláusula de salvaguarda de la Circular Externa 006 de 2025 (régimen de
transición)…". Esa CE 006 de 2025 es de la CBF; **no se ha confirmado** si
existe una cláusula equivalente para la CBJ.

## Inventario de notas de vigencia (barrido completo, 2026-09-29)

504 llamadas al API, todos los niveles. 170 notas no vacías en 13
capítulos, ninguna a nivel de Parte ni de Título, todas con la circular que
las origina (enlazada en la nota, `loader.php?...idFile=<N>`):

| Circular | Notas | Capítulos | Rige (según la circular) |
|---|---|---|---|
| CE 014 de 2025 (`idFile=1079278`) | 31 | 12 | 2-oct-2026 (instrucción DÉCIMA QUINTA) |
| CE 013 de 2025 (`idFile=1079068`) | 138 | P2.T4.C2 | 1-ene-2028 (aplazada por CE 006 de 2026) |
| CE 008 de 2026 (`idFile=1083377`) | 1 | P3.T1.C2 | 30-oct-2026 (instrucción CUARTA) |

Los PDF de las circulares son escaneados (sin capa de texto): se leen como
imagen.

## Numerales en el texto

Numeración local por capítulo al inicio de línea (`1.`, `1.1.`, … hasta 6
niveles); 6.053 en los `.docx`. El detector de la CBF
(`Ingest/CBF/scraper.py:posiciones_numerales`) encuentra **0** en la CBJ
(espera prefijo `{parte}.{capitulo}.` y numerales al final de encabezado):
si la fuente es el `.docx` hace falta un detector nuevo; si es el API, la
fragmentación viene dada por los propios numerales/subnumerales.

## Pendiente

1. Decidir fuente principal (API `descripcion` vs `.docx`) — la evidencia
   de arriba favorece el API.
2. `schema.sql`, scraper, dry-run de fragmentación, `ingest_pilot.py`,
   integración en `app/agent.py` (mismo orden que la CBF).
