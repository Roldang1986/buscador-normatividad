import { useState } from "react";
import CajaPregunta from "./components/CajaPregunta";
import Respuesta from "./components/Respuesta";
import ModalTexto from "./components/ModalTexto";
import Historial from "./components/Historial";
import SelectorCorpus from "./components/SelectorCorpus";
import { consultarPregunta, consultarPreguntaSFC } from "./api";
import { useHistorial } from "./useHistorial";
import "./App.css";

export default function App() {
  const [corpus, setCorpus] = useState("tributario");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [documentoIdModal, setDocumentoIdModal] = useState(null);
  const [historialAbierto, setHistorialAbierto] = useState(false);
  const { historial, agregar, borrar } = useHistorial();

  async function manejarConsulta(pregunta) {
    setCargando(true);
    setError(null);
    try {
      const datos =
        corpus === "sfc" ? await consultarPreguntaSFC(pregunta) : await consultarPregunta(pregunta);
      setResultado(datos);
      agregar(pregunta, datos, corpus);
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  function manejarSeleccionHistorial(entrada) {
    setCorpus(entrada.corpus || "tributario");
    setResultado(entrada.resultado);
    setHistorialAbierto(false);
  }

  function manejarCambioCorpus(nuevoCorpus) {
    setCorpus(nuevoCorpus);
    setResultado(null);
    setError(null);
  }

  return (
    <div className="app">
      <header className="app__encabezado">
        <h1>Buscador de Normatividad Tributaria</h1>
        <button type="button" onClick={() => setHistorialAbierto((abierto) => !abierto)}>
          Historial ({historial.length})
        </button>
      </header>

      <main className="app__principal">
        <SelectorCorpus corpus={corpus} onCambiar={manejarCambioCorpus} disabled={cargando} />
        <CajaPregunta onEnviar={manejarConsulta} cargando={cargando} />
        {error && <p className="app__error">{error}</p>}
        {cargando && <p className="app__cargando">Buscando en la normatividad…</p>}
        <Respuesta resultado={resultado} corpus={corpus} onVerTextoCompleto={setDocumentoIdModal} />
      </main>

      <Historial
        historial={historial}
        onSeleccionar={manejarSeleccionHistorial}
        onBorrar={borrar}
        abierto={historialAbierto}
        onCerrar={() => setHistorialAbierto(false)}
      />

      {documentoIdModal !== null && (
        <ModalTexto
          documentoId={documentoIdModal}
          corpus={corpus}
          onCerrar={() => setDocumentoIdModal(null)}
        />
      )}
    </div>
  );
}
