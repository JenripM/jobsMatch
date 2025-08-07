from pydantic import BaseModel, validator
from typing import Optional, List

class Match(BaseModel):
    cv_url: Optional[str] = None
    cv_embedding: Optional[List[float]] = None
    puesto: str
    
    @validator('cv_embedding', pre=False, always=True)
    def validate_parameters(cls, cv_embedding, values):
        cv_url = values.get('cv_url')
        
        # Debug: mostrar qué está recibiendo el validator
        print(f"🔧 VALIDATOR DEBUG:")
        print(f"   - cv_embedding recibido: {'✅ Presente' if cv_embedding else '❌ Ausente'}")
        print(f"   - cv_url en values: {cv_url}")
        if cv_embedding:
            print(f"   - cv_embedding longitud: {len(cv_embedding)}")
        
        if not cv_url and not cv_embedding:
            raise ValueError('Se debe proporcionar cv_url O cv_embedding')
            
        return cv_embedding


class PromptRequest(BaseModel):
    prompt: str