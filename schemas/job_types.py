"""
Tipos de datos para ofertas de empleo (Jobs)

Este módulo define los schemas Pydantic relacionados con ofertas de empleo
y metadatos derivados de estas.
"""

from typing import List, Optional
from pydantic import BaseModel, Field



class JobMetadata(BaseModel):
    """Schema para los metadatos de una oferta de empleo"""
    category: List[str] = Field(
        description="Lista de categorías del puesto. Máximo 2 categorías de la lista permitida."
    )
    hard_skills: List[str] = Field(
        description="Lista de habilidades técnicas y herramientas de software mencionadas"
    )
    soft_skills: List[str] = Field(
        description="Lista de habilidades interpersonales o blandas inferidas"
    )
    language_requirements: Optional[str] = Field(
        default=None,
        description="Requisitos de idioma mencionados o null si no se especifica",
    )
    related_degrees: List[str] = Field(
        description="Lista de carreras o campos de estudio mencionados"
    )


