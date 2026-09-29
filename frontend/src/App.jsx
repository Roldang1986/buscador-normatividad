import { useRef, useState } from "react";
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
  const [documentoModal, setDocumentoModal] = useState(null);
  const [historialAbierto, setHistorialAbierto] = useState(false);
  const { historial, agregar, borrar } = useHistorial();
  // Corpus vigente en pantalla, legible desde una consulta ya en curso: el
  // Historial sigue activo mientras `cargando` y puede cambiar el corpus
  // antes de que llegue la respuesta.
  const corpusActual = useRef(corpus);
  corpusActual.current = corpus;

  async function manejarConsulta(pregunta) {
    const corpusConsulta = corpus;
    setCargando(true);
    setError(null);
    try {
      const datos =
        corpusConsulta === "sfc"
          ? await consultarPreguntaSFC(pregunta)
          : await consultarPregunta(pregunta);
      // La respuesta se guarda igual en el historial, con su corpus, pero no
      // se muestra si el usuario ya cambió de corpus: pisaría la pantalla con
      // fuentes de la forma equivocada (con/sin `origen`).
      agregar(pregunta, datos, corpusConsulta);
      if (corpusActual.current === corpusConsulta) {
        setResultado(datos);
      }
    } catch (err) {
      if (corpusActual.current === corpusConsulta) {
        setError(err.message);
      }
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
        <h1>Buscador de Normatividad</h1>
        <button type="button" onClick={() => setHistorialAbierto((abierto) => !abierto)}>
          Historial ({historial.length})
        </button>
      </header>

      <main className="app__principal">
        <SelectorCorpus corpus={corpus} onCambiar={manejarCambioCorpus} disabled={cargando} />
        <CajaPregunta corpus={corpus} onEnviar={manejarConsulta} cargando={cargando} />
        {error && <p className="app__error">{error}</p>}
        {cargando && <p className="app__cargando">Buscando en la normatividad…</p>}
        <Respuesta
          resultado={resultado}
          corpus={corpus}
          onVerTextoCompleto={(id, origen) => setDocumentoModal({ id, origen })}
        />
      </main>

      <Historial
        historial={historial}
        onSeleccionar={manejarSeleccionHistorial}
        onBorrar={borrar}
        abierto={historialAbierto}
        onCerrar={() => setHistorialAbierto(false)}
      />

      {documentoModal !== null && (
        <ModalTexto
          documentoId={documentoModal.id}
          corpus={corpus}
          origen={documentoModal.origen}
          onCerrar={() => setDocumentoModal(null)}
        />
      )}
    </div>
  );
}
