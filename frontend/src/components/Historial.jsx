export default function Historial({ historial, onSeleccionar, onBorrar, abierto, onCerrar }) {
  if (!abierto) return null;

  return (
    <aside className="historial">
      <div className="historial__encabezado">
        <h3>Historial</h3>
        <button onClick={onCerrar} aria-label="Cerrar historial">
          ×
        </button>
      </div>
      {historial.length === 0 && <p className="historial__vacio">Sin preguntas todavía.</p>}
      <ul className="historial__lista">
        {historial.map((entrada) => (
          <li key={entrada.id}>
            <button type="button" onClick={() => onSeleccionar(entrada)}>
              {entrada.pregunta}
            </button>
          </li>
        ))}
      </ul>
      {historial.length > 0 && (
        <button type="button" className="historial__borrar" onClick={onBorrar}>
          Borrar historial
        </button>
      )}
    </aside>
  );
}
