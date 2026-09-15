const ESTADOS_DESTACADOS = new Set(["modificado", "derogado"]);

export default function TarjetaFuente({ fuente, onVerTextoCompleto }) {
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
