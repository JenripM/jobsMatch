"""
Módulo de tipos - Schemas Pydantic para el proyecto

Este módulo contiene todos los tipos de datos utilizados en el proyecto:
- Tipos de CV
- Tipos de usuario
- Tipos de metadatos
"""

from .cv_types import (
    PersonalInfo,
    Education,
    WorkExperience,
    Skill,
    Project,
    Certification,
    Volunteer,
    Language,
    Reference,
    CVData,
    UserMetadata
)

__all__ = [
    "PersonalInfo",
    "Education", 
    "WorkExperience",
    "Skill",
    "Project",
    "Certification",
    "Volunteer",
    "Language",
    "Reference",
    "CVData",
    "UserMetadata"
]
