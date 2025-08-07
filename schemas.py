from pydantic import BaseModel, validator
from typing import Optional, Dict, List

class Match(BaseModel):
    cv_url: Optional[str] = None
    cv_embeddings: Optional[Dict[str, List[float]]] = None
    puesto: str
    
    @validator('cv_embeddings', pre=False, always=True)
    def validate_parameters(cls, cv_embeddings, values):
        cv_url = values.get('cv_url')
        
        # Debug: mostrar qué está recibiendo el validator
        print(f"🔧 VALIDATOR DEBUG:")
        print(f"   - cv_embeddings recibido: {'✅ Presente' if cv_embeddings else '❌ Ausente'}")
        print(f"   - cv_url en values: {cv_url}")
        
        if cv_embeddings:
            if not isinstance(cv_embeddings, dict):
                raise ValueError('cv_embeddings debe ser un diccionario multi-aspecto')
                
            print(f"   - cv_embeddings tipo: diccionario multi-aspecto")
            print(f"   - aspectos disponibles: {list(cv_embeddings.keys())}")
            
            # Aspectos esperados en el nuevo formato
            expected_aspects = ['hard_skills', 'category', 'soft_skills', 'sector_afinnity', 'general']
            
            # Validar que cada aspecto tenga un embedding válido
            for aspect, embedding in cv_embeddings.items():
                if not isinstance(embedding, list) or len(embedding) != 2048:
                    raise ValueError(f'El embedding para {aspect} debe ser una lista de 2048 números')
            
            # Informar sobre aspectos faltantes (no es error, solo informativo)
            missing_aspects = [asp for asp in expected_aspects if asp not in cv_embeddings]
            if missing_aspects:
                print(f"   - aspectos faltantes: {missing_aspects} (se usarán valores por defecto)")
        
        if not cv_url and not cv_embeddings:
            raise ValueError('Se debe proporcionar cv_url O cv_embeddings')
            
        return cv_embeddings


class PromptRequest(BaseModel):
    prompt: str