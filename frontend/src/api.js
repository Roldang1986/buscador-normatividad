const RAILWAY_FALLBACK_URL = "https://buscador-normatividad-production.up.railway.app";

function resolverApiBaseUrl() {
  const configurada = import.meta.env.VITE_API_BASE_URL;
  if (configurada) return configurada;

  if (import.meta.env.PROD) {
    // Build de producción sin VITE_API_BASE_URL fijada (ej. `vite build`
    // corrido sin que ningún paso de CI la setee): cae a la URL conocida de
    // Railway en vez de dejar el sitio desplegado apuntando a nada.
    return RAILWAY_FALLBACK_URL;
  }

  // En desarrollo (`npm run dev`) NO hay fallback silencioso a producción:
  // sin frontend/.env configurado, esto debe fallar fuerte y visible acá
  // mismo, en vez de que alguien crea que está hablando con su backend
  // local cuando en realidad está pegándole a producción sin darse cuenta.
  throw new Error(
    "VITE_API_BASE_URL no está configurada. Copiá frontend/.env.example a " +
      "frontend/.env y apuntala a tu backend local (ver ese archivo para el " +
      "patrón de URL reenviada de Codespaces) antes de correr `npm run dev`."
  );
}

const API_BASE_URL = resolverApiBaseUrl();

export async function consultarPregunta(pregunta) {
  const respuesta = await fetch(`${API_BASE_URL}/consulta`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta }),
  });
  if (!respuesta.ok) {
    throw new Error(`No se pudo consultar (HTTP ${respuesta.status})`);
  }
  return respuesta.json();
}

export async function obtenerNormaCompleta(id) {
  const respuesta = await fetch(`${API_BASE_URL}/norma/${id}`);
  if (!respuesta.ok) {
    throw new Error(`No se pudo obtener el texto completo (HTTP ${respuesta.status})`);
  }
  return respuesta.json();
}

export async function consultarPreguntaSFC(pregunta) {
  const respuesta = await fetch(`${API_BASE_URL}/consulta-sfc`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta }),
  });
  if (!respuesta.ok) {
    throw new Error(`No se pudo consultar (HTTP ${respuesta.status})`);
  }
  return respuesta.json();
}

export async function obtenerNormaCBFCompleta(id) {
  const respuesta = await fetch(`${API_BASE_URL}/norma-cbf/${id}`);
  if (!respuesta.ok) {
    throw new Error(`No se pudo obtener el texto completo (HTTP ${respuesta.status})`);
  }
  return respuesta.json();
}

export async function obtenerDocumentoSFCCompleto(id) {
  const respuesta = await fetch(`${API_BASE_URL}/documento-sfc/${id}`);
  if (!respuesta.ok) {
    throw new Error(`No se pudo obtener el texto completo (HTTP ${respuesta.status})`);
  }
  return respuesta.json();
}
