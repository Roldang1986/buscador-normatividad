const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "https://buscador-normatividad-production.up.railway.app";

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
