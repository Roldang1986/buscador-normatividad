const CORPUS = [
  { id: "tributario", etiqueta: "Tributario" },
  { id: "sfc", etiqueta: "SFC — Circular Básica Financiera y conceptos" },
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
          {opcion.etiqueta}
        </button>
      ))}
    </div>
  );
}
