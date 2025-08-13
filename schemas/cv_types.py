"""
Tipos para datos de CV - Schemas Pydantic

Este módulo contiene todos los tipos de datos relacionados con CVs:
- Información personal
- Educación
- Experiencia laboral
- Habilidades
- Proyectos
- Certificaciones
- Voluntariado
- Idiomas
- Referencias
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class PersonalInfo(BaseModel):
    fullName: str = Field(description="Nombre completo")
    email: str = Field(description="Correo electrónico profesional")
    phone: str = Field(description="Número de teléfono")
    address: str = Field(description="Ciudad y País")
    linkedIn: Optional[str] = Field(default="", description="Perfil de LinkedIn")
    website: Optional[str] = Field(default="", description="Sitio web personal o portafolio")
    summary: str = Field(description="Resumen profesional conciso")

class Education(BaseModel):
    id: str = Field(description="ID único")
    institution: str = Field(description="Nombre de la institución")
    degree: str = Field(description="Título obtenido")
    fieldOfStudy: Optional[str] = Field(default="", description="Campo de estudio específico")
    startDate: str = Field(description="Fecha de inicio")
    endDate: str = Field(description="Fecha de finalización")
    current: bool = Field(description="Si está en curso")
    gpa: Optional[str] = Field(default="", description="GPA o promedio académico")
    honors: Optional[str] = Field(default="", description="Honores académicos")
    relevantCourses: Optional[List[str]] = Field(default=[], description="Cursos relevantes")
    achievements: Optional[List[str]] = Field(default=[], description="Logros académicos")
    location: Optional[str] = Field(default="", description="Ciudad y país de la institución")

class WorkExperience(BaseModel):
    id: str = Field(description="ID único")
    company: str = Field(description="Nombre de la empresa")
    position: str = Field(description="Cargo o posición")
    startDate: str = Field(description="Fecha de inicio")
    endDate: str = Field(description="Fecha de finalización")
    current: bool = Field(description="Si es el trabajo actual")
    location: Optional[str] = Field(default="", description="Ciudad y país")
    description: Optional[str] = Field(default="", description="Breve descripción del rol")
    achievements: List[str] = Field(description="Logros cuantificables y medibles")
    technologies: Optional[List[str]] = Field(default=[], description="Tecnologías utilizadas")
    responsibilities: Optional[List[str]] = Field(default=[], description="Responsabilidades principales")
    projects: Optional[List[str]] = Field(default=[], description="Proyectos destacados")
    sections: Optional[List[Dict[str, Any]]] = Field(default=[], description="Subsecciones del trabajo")

class Skill(BaseModel):
    id: str = Field(description="ID único")
    name: str = Field(description="Nombre de la habilidad")
    level: Optional[str] = Field(default="", description="Nivel: Básico, Intermedio, Avanzado, o Proficiente")
    category: str = Field(description="Categoría: Technical, Analytical, Leadership, Communication, Research, o Language")
    proficiency: Optional[int] = Field(default=0, description="Nivel de competencia (1-5)")
    certifications: Optional[List[str]] = Field(default=[], description="Certificaciones relacionadas")

class Project(BaseModel):
    id: str = Field(description="ID único")
    name: str = Field(description="Nombre del proyecto")
    description: str = Field(description="Descripción detallada")
    technologies: str = Field(description="Tecnologías utilizadas")
    startDate: str = Field(description="Fecha de inicio")
    endDate: str = Field(description="Fecha de finalización")
    current: bool = Field(description="Si está en curso")
    url: Optional[str] = Field(default="", description="Enlace al proyecto")
    highlights: List[str] = Field(description="Logros y resultados destacados")
    role: Optional[str] = Field(default="", description="Rol en el proyecto")
    teamSize: Optional[int] = Field(default=0, description="Tamaño del equipo")
    methodology: Optional[str] = Field(default="", description="Metodología utilizada")

class Certification(BaseModel):
    id: str = Field(description="ID único")
    name: str = Field(description="Nombre de la certificación")
    issuer: str = Field(description="Entidad emisora")
    date: str = Field(description="Fecha de obtención")
    expiryDate: Optional[str] = Field(default="", description="Fecha de vencimiento")
    credentialId: Optional[str] = Field(default="", description="ID de la credencial")
    url: Optional[str] = Field(default="", description="URL de verificación")
    score: Optional[str] = Field(default="", description="Calificación obtenida")
    description: Optional[str] = Field(default="", description="Descripción breve")

class Volunteer(BaseModel):
    id: str = Field(description="ID único")
    organization: str = Field(description="Organización")
    position: str = Field(description="Posición")
    startDate: str = Field(description="Fecha de inicio")
    endDate: str = Field(description="Fecha de finalización")
    currentlyVolunteering: bool = Field(description="Si está actualmente como voluntario")
    description: str = Field(description="Descripción")
    skills: List[str] = Field(description="Habilidades utilizadas")
    impact: Optional[str] = Field(default="", description="Impacto o logros")
    location: Optional[str] = Field(default="", description="Ubicación")

class Language(BaseModel):
    id: str = Field(description="ID único")
    language: str = Field(description="Idioma")
    proficiency: str = Field(description="Nivel de competencia")
    certifications: Optional[List[str]] = Field(default=[], description="Certificaciones de idiomas")
    writingLevel: Optional[str] = Field(default="", description="Nivel de escritura")
    speakingLevel: Optional[str] = Field(default="", description="Nivel de conversación")

class Reference(BaseModel):
    id: str = Field(description="ID único")
    name: str = Field(description="Nombre completo")
    position: str = Field(description="Cargo actual")
    company: str = Field(description="Empresa actual")
    email: str = Field(description="Correo electrónico")
    phone: str = Field(description="Teléfono")
    relationship: Optional[str] = Field(default="", description="Relación profesional")
    yearsKnown: Optional[int] = Field(default=0, description="Años de conocimiento")
    preferredContact: Optional[str] = Field(default="", description="Método de contacto preferido")

class CVData(BaseModel):
    personalInfo: PersonalInfo
    education: List[Education]
    workExperience: List[WorkExperience]
    skills: List[Skill]
    projects: List[Project]
    certifications: List[Certification]
    volunteer: List[Volunteer]
    languages: Optional[List[Language]] = Field(default=[])
    references: Optional[List[Reference]] = Field(default=[])
    hobbies: Optional[List[str]] = Field(default=[])

class UserMetadata(BaseModel):
    """Schema para los metadatos de un usuario basado en su CV"""
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
        description="Requisitos de idioma mencionados o null si no se especifica"
    )
    related_degrees: List[str] = Field(
        description="Lista de carreras o campos de estudio mencionados"
    )
