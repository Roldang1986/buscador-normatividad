from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class DocumentoSFCRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo_documento: str
    numero_documento: str | None = None
    fecha_texto: str | None = None
    titulo: str | None = None
    resumen: str | None = None
    texto_completo: str | None = None
    url_archivo: str | None = None
    fuente_atribucion: str


class FuenteCitadaSFC(BaseModel):
    origen: Literal["documentos_sfc"] = "documentos_sfc"
    id: int
    tipo_documento: str
    numero_documento: str | None = None
    fecha_texto: str | None = None
    titulo: str | None = None
    fuente_atribucion: str


class FuenteCitadaCBF(BaseModel):
    origen: Literal["normas_cbf"] = "normas_cbf"
    id: int
    fuente: str
    numeral: str | None = None
    estado_vigencia: str
    url_archivo: str | None = None


class NormaCBFRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parte: int
    nombre_parte: str | None = None
    numero_capitulo: int | None = None
    nombre_capitulo: str | None = None
    seccion: str | None = None
    numeral: str | None = None
    version: str
    fuente: str
    url_archivo: str | None = None
    texto: str | None = None
    estado_vigencia: str
    fecha_vigencia_inicio: date | None = None
    fecha_vigencia_fin: date | None = None
    nota_vigencia: str | None = None


class ConsultaSFCResponse(BaseModel):
    respuesta: str
    # /consulta-sfc mezcla dos tablas; "origen" discrimina el tipo de fuente.
    fuentes: list[
        Annotated[FuenteCitadaSFC | FuenteCitadaCBF, Field(discriminator="origen")]
    ]
