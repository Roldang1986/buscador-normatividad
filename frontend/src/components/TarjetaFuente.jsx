const ESTADOS_DESTACADOS = new Set(["modificado", "derogado"]);

const ETIQUETAS_TIPO_DOCUMENTO_SFC = {
  concepto: "Doctrina (concepto, no vinculante)",
  fallo: "Fallo (vinculante para las partes)",
  jurisprudencia: "Jurisprudencia (vinculante para las partes)",
};

function TarjetaFuenteSFC({ fuente, onVerTextoCompleto }) {
  const etiquetaTipo = ETIQUETAS_TIPO_DOCUMENTO_SFC[fuente.tipo_documento] || fuente.tipo_documento;

  return (
    <div className="tarjeta-fuente">
      <div className="tarjeta-fuente__encabezado">
        <span className="tarjeta-fuente__articulo">
          {fuente.numero_documento ? `Concepto ${fuente.numero_documento}` : etiquetaTipo}
        </span>
        <span className="tarjeta-fuente__estado">{etiquetaTipo}</span>
      </div>
      <p className="tarjeta-fuente__nombre">{fuente.titulo || fuente.fecha_texto}</p>
      <div className="tarjeta-fuente__acciones">
        <button type="button" onClick={() => onVerTextoCompleto(fuente.id)}>
          Ver texto completo
        </button>
      </div>
    </div>
  );
}

export default function TarjetaFuente({ fuente, corpus = "tributario", onVerTextoCompleto }) {
  if (corpus === "sfc") {
    return <TarjetaFuenteSFC fuente={fuente} onVerTextoCompleto={onVerTextoCompleto} />;
  }

  const destacado = ESTADOS_DESTACADOS.has(fuente.estado_vigencia);

  return (
    <div className={`tarjeta-fuente${destacado ? " tarjeta-fuente--alerta" : ""}`}>
      <div className="tarjeta-fuente__encabezado">
        <span className="tarjeta-fuente__articulo">
          {fuente.numero_articulo ? `Art. ${fuente.numero_articulo}` : fuente.tipo_norma}
        </span>
        <span
          className={`tarjeta-fuente__estado tarjeta-fuente__estado--${fuente.estado_vigencia}`}
        >
          {fuente.estado_vigencia}
        </span>
      </div>
      <p className="tarjeta-fuente__nombre">{fuente.fuente}</p>
      <div className="tarjeta-fuente__acciones">
        <button type="button" onClick={() => onVerTextoCompleto(fuente.id)}>
          Ver texto completo
        </button>
        {fuente.url_fuente && (
          <a href={fuente.url_fuente} target="_blank" rel="noopener noreferrer">
            Ver fuente oficial
          </a>
        )}
      </div>
    </div>
  );
}
