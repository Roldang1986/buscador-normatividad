from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NormaBase(BaseModel):
    tipo_norma: str
    numero_articulo: str | None = None
    fuente: str
    url_fuente: str | None = None
    texto: str
    estado_vigencia: str
    nota_vigencia: str | None = None


class NormaCreate(NormaBase):
    pass


class NormaRead(NormaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_ingesta: datetime


class ConsultaRequest(BaseModel):
    pregunta: str


class FuenteCitada(BaseModel):
    id: int
    tipo_norma: str
    numero_articulo: str | None = None
    fuente: str
    url_fuente: str | None = None
    estado_vigencia: str


class ConsultaResponse(BaseModel):
    respuesta: str
    fuentes: list[FuenteCitada]
