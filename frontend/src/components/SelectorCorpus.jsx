const CORPUS = [
  { id: "tributario", etiqueta: "Tributario", etiquetaCorta: "Tributario" },
  {
    id: "sfc",
    etiqueta: "SFC — Circular Básica Financiera y conceptos",
    etiquetaCorta: "SFC · CBF y conceptos",
  },
];

export default function SelectorCorpus({ corpus, onCambiar, disabled }) {
  return (
    <div className="selector-corpus" role="tablist" aria-label="Corpus de normatividad">
      {CORPUS.map((opcion) => (
        <button
          key={opcion.id}
          type="button"
          role="tab"
          aria-selected={corpus === opcion.id}
          className={`selector-corpus__boton${
            corpus === opcion.id ? " selector-corpus__boton--activo" : ""
          }`}
          disabled={disabled}
          onClick={() => onCambiar(opcion.id)}
        >
          {/* En móvil (≤480px) el CSS muestra solo la etiqueta corta. */}
          <span className="selector-corpus__etiqueta-larga">{opcion.etiqueta}</span>
          <span className="selector-corpus__etiqueta-corta">{opcion.etiquetaCorta}</span>
        </button>
      ))}
    </div>
  );
}
