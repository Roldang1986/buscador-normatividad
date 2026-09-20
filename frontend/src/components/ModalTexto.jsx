import { useEffect, useState } from "react";
import { obtenerDocumentoSFCCompleto, obtenerNormaCompleta } from "../api";

export default function ModalTexto({ documentoId, corpus = "tributario", onCerrar }) {
  const [documento, setDocumento] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelado = false;
    setCargando(true);
    setError(null);
    setDocumento(null);

    const obtener = corpus === "sfc" ? obtenerDocumentoSFCCompleto : obtenerNormaCompleta;

    obtener(documentoId)
      .then((datos) => {
        if (!cancelado) setDocumento(datos);
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
  }, [documentoId, corpus]);

  return (
    <div className="modal-fondo" onClick={onCerrar}>
      <div className="modal-contenido" onClick={(evento) => evento.stopPropagation()}>
        <button className="modal-cerrar" onClick={onCerrar} aria-label="Cerrar">
          ×
        </button>
        {cargando && <p>Cargando texto completo…</p>}
        {error && <p className="modal-error">{error}</p>}
        {documento && corpus === "sfc" && (
          <>
            <h3>{documento.titulo || `Concepto ${documento.numero_documento || ""}`}</h3>
            <p className="modal-meta">
              {documento.tipo_documento}
              {documento.fecha_texto ? ` — ${documento.fecha_texto}` : ""}
            </p>
            <pre className="modal-texto">
              {documento.texto_completo || documento.resumen || "Sin texto completo disponible."}
            </pre>
            <p className="modal-meta">{documento.fuente_atribucion}</p>
          </>
        )}
        {documento && corpus !== "sfc" && (
          <>
            <h3>{documento.fuente}</h3>
            <p className="modal-meta">
              Estado: {documento.estado_vigencia}
              {documento.nota_vigencia ? ` — ${documento.nota_vigencia}` : ""}
            </p>
            <pre className="modal-texto">{documento.texto}</pre>
          </>
        )}
      </div>
    </div>
  );
}
