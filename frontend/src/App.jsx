import { useState } from "react";
import CajaPregunta from "./components/CajaPregunta";
import Respuesta from "./components/Respuesta";
import ModalTexto from "./components/ModalTexto";
import Historial from "./components/Historial";
import { consultarPregunta } from "./api";
import { useHistorial } from "./useHistorial";
import "./App.css";

export default function App() {
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [normaIdModal, setNormaIdModal] = useState(null);
  const [historialAbierto, setHistorialAbierto] = useState(false);
  const { historial, agregar, borrar } = useHistorial();

  async function manejarConsulta(pregunta) {
    setCargando(true);
    setError(null);
    try {
      const datos = await consultarPregunta(pregunta);
      setResultado(datos);
      agregar(pregunta, datos);
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  function manejarSeleccionHistorial(entrada) {
    setResultado(entrada.resultado);
    setHistorialAbierto(false);
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
        <CajaPregunta onEnviar={manejarConsulta} cargando={cargando} />
        {error && <p className="app__error">{error}</p>}
        {cargando && <p className="app__cargando">Buscando en la normatividad…</p>}
        <Respuesta resultado={resultado} onVerTextoCompleto={setNormaIdModal} />
      </main>

      <Historial
        historial={historial}
        onSeleccionar={manejarSeleccionHistorial}
        onBorrar={borrar}
        abierto={historialAbierto}
        onCerrar={() => setHistorialAbierto(false)}
      />

      {normaIdModal !== null && (
        <ModalTexto normaId={normaIdModal} onCerrar={() => setNormaIdModal(null)} />
      )}
    </div>
  );
}
