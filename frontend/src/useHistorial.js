import { useCallback, useEffect, useState } from "react";

const CLAVE_STORAGE = "buscador-normatividad:historial";
const MAX_ENTRADAS = 20;

function leerHistorialInicial() {
  try {
    const crudo = localStorage.getItem(CLAVE_STORAGE);
    return crudo ? JSON.parse(crudo) : [];
  } catch {
    // localStorage puede fallar (modo privado, cuota llena, deshabilitado) —
    // la app sigue funcionando, solo sin historial persistente.
    return [];
  }
}

export function useHistorial() {
  const [historial, setHistorial] = useState(leerHistorialInicial);

  useEffect(() => {
    try {
      localStorage.setItem(CLAVE_STORAGE, JSON.stringify(historial));
    } catch {
      // Ver comentario en leerHistorialInicial.
    }
  }, [historial]);

  const agregar = useCallback((pregunta, resultado) => {
    const entrada = {
      id: crypto.randomUUID(),
      pregunta,
      resultado,
      fecha: new Date().toISOString(),
    };
    setHistorial((actual) => [entrada, ...actual].slice(0, MAX_ENTRADAS));
  }, []);

  const borrar = useCallback(() => setHistorial([]), []);

  return { historial, agregar, borrar };
}
