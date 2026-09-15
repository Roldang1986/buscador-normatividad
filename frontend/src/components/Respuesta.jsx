import TarjetaFuente from "./TarjetaFuente";

export default function Respuesta({ resultado, onVerTextoCompleto }) {
  if (!resultado) return null;

  return (
    <section className="respuesta">
      <p className="respuesta__texto">{resultado.respuesta}</p>
      {resultado.fuentes.length > 0 && (
        <div className="respuesta__fuentes">
          <h3>Fuentes citadas</h3>
          <div className="respuesta__fuentes-lista">
            {resultado.fuentes.map((fuente) => (
              <TarjetaFuente
                key={fuente.id}
                fuente={fuente}
                onVerTextoCompleto={onVerTextoCompleto}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
