import { useEffect, useState } from "react";
import { obtenerNormaCompleta } from "../api";

export default function ModalTexto({ normaId, onCerrar }) {
  const [norma, setNorma] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelado = false;
    setCargando(true);
    setError(null);
    setNorma(null);

    obtenerNormaCompleta(normaId)
      .then((datos) => {
        if (!cancelado) setNorma(datos);
      })
      .catch((err) => {
        if (!cancelado) setError(err.message);
      })
      .finally(() => {
        if (!cancelado) setCargando(false);
      });

    return () => {
      cancelado = true;
    };
  }, [normaId]);

  return (
    <div className="modal-fondo" onClick={onCerrar}>
      <div className="modal-contenido" onClick={(evento) => evento.stopPropagation()}>
        <button className="modal-cerrar" onClick={onCerrar} aria-label="Cerrar">
          ×
        </button>
        {cargando && <p>Cargando texto completo…</p>}
        {error && <p className="modal-error">{error}</p>}
        {norma && (
          <>
            <h3>{norma.fuente}</h3>
            <p className="modal-meta">
              Estado: {norma.estado_vigencia}
              {norma.nota_vigencia ? ` — ${norma.nota_vigencia}` : ""}
            </p>
            <pre className="modal-texto">{norma.texto}</pre>
          </>
        )}
      </div>
    </div>
  );
}
