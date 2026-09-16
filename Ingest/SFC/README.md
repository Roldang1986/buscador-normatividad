# Scraper de conceptos/fallos/jurisprudencia — Superfinanciera

Segundo corpus para el mismo stack del RAG tributario (Postgres/pgvector en
Neon, FastAPI, Voyage AI, Claude Sonnet), no un proyecto aparte.

## Ya validado contra el sitio real

- El catálogo jurídico vive en un sistema ABCD/CDS-ISIS (bibliotecario, no
  una API), en `buscar_integrada.php`. Es HTML estático server-rendered —
  no hace falta Playwright.
- URL + parámetro real de filtrado por colección:
  `?base=juris&Opcion=libre&coleccion=<codigo>|<etiqueta>|TM_`
  con `ac` = Doctrina y conceptos, `af` = Fallos jurisdiccionales,
  `aj` = Jurisprudencia financiera.
- **Fallos jurisdiccionales: 14.466 registros.** Total combinado de las
  tres colecciones: 18.707 (así que `ac` + `aj` ≈ 4.241 juntos — falta
  el desglose exacto).
- La mayoría de los Fallos (~80% en la muestra revisada) tienen como
  "Acceso web" un **archivo de audio**, no texto — es la grabación de la
  audiencia. Decisión tomada: para esos, guardar solo el resumen
  (`tiene_texto_completo = false`), sin transcripción por ahora.
- El HTML llega en **ISO-8859-1**, no UTF-8. Hay que decodificar
  explícitamente o las tildes/Ñ salen corruptas.
- Estructura de campos por tipo de registro confirmada (ver `parser.py`):
  Concepto/Fallo, Expediente/Radicado, Autor Corporativo, Título de la
  norma, Documento fuente, Resumen, Notas, Temas/Materias, Acceso web.

## Pendiente — necesita correrse desde Codespaces (este sandbox no tiene
salida de red hacia superfinanciera.gov.co)

1. **Paginación real.** El enlace "Próxima" es un
   `javascript:ProximaPagina(pagina, offset)` — no expone una URL plana en
   el HTML extraído que pude ver. Es muy probable que someta un formulario
   con campos ocultos (típico de sistemas ISIS/ABCD). Hay que:
   - Abrir la página en un navegador, DevTools → Network, clic en
     "Próxima", y ver la request real (método, parámetros/campos).
   - Reemplazar `avanzar_pagina()` en `scraper.py` con esa lógica.
2. **Conteo exacto de `ac` y `aj` por separado** (correr
   `obtener_pagina()` con cada uno y leer "Mostrando del 1 al 25 de N
   registros").
3. **Revisar robots.txt y términos de uso** del sitio antes de lanzar el
   scraper contra cientos de páginas.
4. **Validar el parser contra HTML crudo real**, no solo contra el
   Markdown que yo pude ver. Corre:
   ```
   python -c "from scraper import obtener_pagina; import requests; \
       print(obtener_pagina(requests.Session(), 'ac')[:2000])"
   ```
   y confirma que `parser.parse_pagina_resultados()` encuentra los
   registros esperados antes de escalar.

## Cómo seguir

```
pip install requests beautifulsoup4 --break-system-packages
python scraper.py --dry-run --coleccion ac --paginas 1
```

Una vez el parser esté validado contra HTML real y la paginación
resuelta, aplica `schema.sql` en la misma base Neon del RAG tributario y
conecta el pipeline de embeddings (mismo modelo Voyage, mismo cliente
Claude para generación) apuntando a `documentos_sfc` como segundo corpus.
