"""
Configuración centralizada del sistema JobsMatch
"""

import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# =============================
# CONFIGURACIÓN DE CACHE
# =============================

# El cache no expira automáticamente
# Se elimina manualmente cuando se suben nuevas prácticas

# =============================
# CONFIGURACIÓN DE STREAMING
# =============================

# Configuración para streaming puro (sin compresión)
STREAMING_CHUNK_SIZE = int(os.getenv("STREAMING_CHUNK_SIZE", "3"))
STREAMING_ENABLED = os.getenv("STREAMING_ENABLED", "true").lower() == "true"
USE_PURE_STREAMING = os.getenv("USE_PURE_STREAMING", "true").lower() == "true"

# =============================
# CONFIGURACIÓN DE BÚSQUEDA
# =============================

# Días hacia atrás para buscar prácticas recientes
DEFAULT_SINCE_DAYS = int(os.getenv("DEFAULT_SINCE_DAYS", "5"))

# Umbral mínimo de similitud (porcentaje)
DEFAULT_PERCENTAGE_THRESHOLD = float(os.getenv("DEFAULT_PERCENTAGE_THRESHOLD", "0"))

# =============================
# CONFIGURACIÓN DE LÍMITES
# =============================

# Límite por defecto de prácticas a devolver
DEFAULT_PRACTICES_LIMIT = int(os.getenv("DEFAULT_PRACTICES_LIMIT", "100"))

# =============================
# CONFIGURACIÓN DE LOGGING
# =============================

# Nivel de logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
