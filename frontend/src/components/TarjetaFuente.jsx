const ESTADOS_DESTACADOS = new Set(["modificado", "derogado"]);
const ESTADOS_DESTACADOS_CBF = new Set(["vigencia_futura", "vigencia_condicionada"]);

const ETIQUETAS_ESTADO_CBF = {
  vigente: "Norma vigente",
  vigencia_futura: "Vigencia futura (aún no rige)",
  vigencia_condicionada: "Vigencia condicionada",
};

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
        <button type="button" onClick={() => onVerTextoCompleto(fuente.id, "documentos_sfc")}>
          Ver texto completo
        </button>
      </div>
    </div>
  );
}

function TarjetaFuenteCBF({ fuente, onVerTextoCompleto }) {
  const destacado = ESTADOS_DESTACADOS_CBF.has(fuente.estado_vigencia);

  return (
    <div className={`tarjeta-fuente${destacado ? " tarjeta-fuente--alerta" : ""}`}>
      <div className="tarjeta-fuente__encabezado">
        <span className="tarjeta-fuente__articulo">
          {fuente.numeral ? `CBF numeral ${fuente.numeral}` : "Circular Básica Financiera"}
        </span>
        <span
          className={`tarjeta-fuente__estado tarjeta-fuente__estado--${fuente.estado_vigencia}`}
        >
          {ETIQUETAS_ESTADO_CBF[fuente.estado_vigencia] || fuente.estado_vigencia}
        </span>
      </div>
      <p className="tarjeta-fuente__nombre">{fuente.fuente}</p>
      <div className="tarjeta-fuente__acciones">
        <button type="button" onClick={() => onVerTextoCompleto(fuente.id, "normas_cbf")}>
          Ver texto completo
        </button>
        {fuente.url_archivo && (
          <a href={fuente.url_archivo} target="_blank" rel="noopener noreferrer">
            Descargar capítulo oficial
          </a>
        )}
      </div>
    </div>
  );
}

export default function TarjetaFuente({ fuente, corpus = "tributario", onVerTextoCompleto }) {
  // /consulta-sfc mezcla dos tablas; las entradas viejas del historial (antes
  // de la CBF) no traen "origen" y son todas de documentos_sfc.
  if (corpus === "sfc" && fuente.origen === "normas_cbf") {
    return <TarjetaFuenteCBF fuente={fuente} onVerTextoCompleto={onVerTextoCompleto} />;
  }
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
