"""
Módulo de prompts - Templates para IA

Este módulo contiene todos los prompts utilizados para:
- Extracción de datos de CVs
- Generación de metadatos
- Procesamiento de texto
"""

from .cv_prompts import (
    CV_FIELDS_INFERENCE_PROMPT,
    CV_METADATA_INFERENCE_PROMPT
)

__all__ = [
    "CV_FIELDS_INFERENCE_PROMPT",
    "CV_METADATA_INFERENCE_PROMPT"
]
