from pydantic import BaseModel

class Match(BaseModel):
    cv_url: str
    puesto: str


class PromptRequest(BaseModel):
    prompt: str