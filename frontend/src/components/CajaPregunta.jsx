import { useState } from "react";

export default function CajaPregunta({ onEnviar, cargando }) {
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
        placeholder="Ej. ¿Cuál es la tarifa general del IVA?"
        rows={3}
        disabled={cargando}
      />
      <button type="submit" disabled={cargando || !pregunta.trim()}>
        {cargando ? "Consultando…" : "Enviar"}
      </button>
    </form>
  );
}
