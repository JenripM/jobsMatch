from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum

class JobLevel(str, Enum):
    PRACTICANTE = "practicante"
    ANALISTA = "analista"
    SENIOR = "senior"
    JUNIOR = "junior"

class MigrationConfig(BaseModel):
    """Configuración para una migración de colección"""
    source_collection: str = Field(..., description="Colección fuente de prácticas")
    target_collection: str = Field(..., description="Colección destino para embeddings")
    job_level: JobLevel = Field(..., description="Nivel de trabajo para las prácticas migradas")

class CleanupConfig(BaseModel):
    """Configuración para limpieza de colección"""
    collection_name: str = Field(..., description="Nombre de la colección a limpiar")
    since_days: int = Field(..., description="Eliminar documentos más antiguos que N días")

class PipelineSections(BaseModel):
    """Configuración de qué secciones del pipeline se ejecutan"""
    enable_migration: bool = Field(default=True, description="Ejecutar migración de colecciones")
    enable_metadata: bool = Field(default=True, description="Ejecutar generación de metadatos")
    enable_embeddings: bool = Field(default=True, description="Ejecutar generación de embeddings")
    enable_cache_clear: bool = Field(default=True, description="Ejecutar limpieza de caches")
    enable_cleanup: bool = Field(default=False, description="Ejecutar limpieza de documentos antiguos")

class PipelineConfig(BaseModel):
    """Configuración completa para el pipeline de procesamiento de ofertas laborales"""
    
    # Configuración de migración (múltiples colecciones)
    migrations: List[MigrationConfig] = Field(..., description="Lista de migraciones a ejecutar")
    
    # Configuración de limpieza (múltiples colecciones)
    cleanups: List[CleanupConfig] = Field(default=[], description="Lista de limpiezas a ejecutar")
    
    # Configuración de secciones
    sections: PipelineSections = Field(default_factory=PipelineSections, description="Configuración de secciones a ejecutar")
    
    # Configuración de procesamiento
    overwrite_metadata: bool = Field(default=False, description="Sobrescribir metadatos existentes")
    overwrite_embeddings: bool = Field(default=False, description="Sobrescribir embeddings existentes")
    
    # Configuración de filtrado por fecha
    days_back: int = Field(default=5, description="Solo procesar documentos de los últimos N días (default: 5)")
    


class PipelineStep(BaseModel):
    """Información de un paso del pipeline"""
    step_name: str
    status: str  # "completed", "skipped", "error"
    duration: float
    details: Dict[str, Any]

class PipelineResult(BaseModel):
    """Resultado completo del pipeline"""
    success: bool
    total_duration: float
    steps: Dict[str, PipelineStep]
    summary: Dict[str, Any]
    error_message: Optional[str] = None
