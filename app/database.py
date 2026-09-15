import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL no está definida. Configúrala en el entorno (ver .env.example)."
    )

# pool_pre_ping: verifica la conexión con un SELECT 1 antes de cada uso y
# la descarta/reabre si ya fue cerrada del lado del servidor, en vez de
# fallar con "SSL connection has been closed unexpectedly" — Neon cierra
# conexiones inactivas del pooler sin avisar al cliente. pool_recycle
# descarta preventivamente cualquier conexión con más de 300s de vida,
# por debajo del timeout de inactividad del pooler de Neon.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
