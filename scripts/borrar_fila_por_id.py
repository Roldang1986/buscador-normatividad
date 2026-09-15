"""MODO DE ESCRITURA: borra una fila puntual de `norma` por id, después de
verificar que su contenido coincide EXACTAMENTE con lo esperado — protección
contra borrar la fila equivocada por un id mal tecleado. Pensado para
limpiar filas de prueba insertadas manualmente (ej. la fila usada para
verificar la autenticación de POST /ingesta/norma en producción).

Si el contenido no coincide, aborta sin borrar nada.

Uso:
    python scripts/borrar_fila_por_id.py <id> <tipo_norma_esperado> <texto_esperado>
"""

import sys

from app.database import SessionLocal
from app.models import Norma


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    id_fila = int(sys.argv[1])
    tipo_norma_esperado = sys.argv[2]
    texto_esperado = sys.argv[3]

    db = SessionLocal()
    try:
        fila = db.query(Norma).get(id_fila)
        if fila is None:
            print(f"No existe ninguna fila con id={id_fila}. Nada que borrar.")
            sys.exit(1)

        print(
            f"Fila encontrada: id={fila.id}, tipo_norma={fila.tipo_norma!r}, "
            f"fuente={fila.fuente!r}, texto={fila.texto!r}, "
            f"estado_vigencia={fila.estado_vigencia!r}, "
            f"fecha_ingesta={fila.fecha_ingesta}"
        )

        if fila.tipo_norma != tipo_norma_esperado or fila.texto != texto_esperado:
            print(
                "ABORTADO: el contenido de la fila no coincide con lo esperado "
                f"(tipo_norma_esperado={tipo_norma_esperado!r}, "
                f"texto_esperado={texto_esperado!r}). No se borró nada."
            )
            sys.exit(1)

        db.delete(fila)
        db.commit()
        print(f"Borrada: id={id_fila}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
