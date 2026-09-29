import { useState } from "react";

const EJEMPLO_POR_CORPUS = {
  tributario: "Ej. ¿Cuál es la tarifa general del IVA?",
  sfc: "Ej. ¿Qué exige la CBF sobre el sistema de administración de riesgo de liquidez?",
};

export default function CajaPregunta({ corpus, onEnviar, cargando }) {
  const [pregunta, setPregunta] = useState("");

  function manejarEnvio(evento) {
    evento.preventDefault();
    const texto = pregunta.trim();
    if (!texto || cargando) return;
    onEnviar(texto);
  }

  return (
    <form className="caja-pregunta" onSubmit={manejarEnvio}>
      <textarea
        value={pregunta}
        onChange={(evento) => setPregunta(evento.target.value)}
        placeholder={EJEMPLO_POR_CORPUS[corpus]}
        rows={3}
        disabled={cargando}
      />
      <button type="submit" disabled={cargando || !pregunta.trim()}>
        {cargando ? "Consultando…" : "Enviar"}
      </button>
    </form>
  );
}
