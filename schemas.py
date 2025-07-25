from pydantic import BaseModel

class Match(BaseModel):
    cv_url: str
    puesto: str


class PromptRequest(BaseModel):
    prompt: str

class Practica(BaseModel):
    id: str
    descripcion: str
    fecha_agregado: object
    company: str
    url: str
    location: str
    salary: str