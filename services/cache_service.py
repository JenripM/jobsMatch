"""
Servicio de Cache para Matches de Prácticas

Este servicio maneja el cache de matches de prácticas para evitar recalcular
embeddings y búsquedas cuando el CV no ha cambiado.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from db import db_jobs

async def get_cached_matches(user_id: str, cv_file_url: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene matches cacheados para un usuario y CV específico.
    
    Args:
        user_id: ID del usuario
        cv_file_url: URL del archivo CV (se usa como clave de cache)
        
    Returns:
        Dict con los matches cacheados o None si no existe
    """
    try:
        # Buscar en la colección cache_matches
        cache_query = db_jobs.collection("cache_matches").where("user_id", "==", user_id).where("cvFileUrl", "==", cv_file_url).limit(1).get()
        
        if not cache_query:
            print("🔍 No se encontró cache en cache_matches")
            return None
            
        cache_doc = cache_query[0]
        cache_data = cache_doc.to_dict()
        
        print(f"✅ Se encontró cache en cache_matches, devolviendo prácticas desde cache")
        return cache_data
        
    except Exception as e:
        print(f"❌ Error al obtener cache: {e}")
        return None

async def save_cached_matches(user_id: str, cv_file_url: str, practices: List[Dict[str, Any]]) -> bool:
    """
    Guarda matches en el cache.
    
    Args:
        user_id: ID del usuario
        cv_file_url: URL del archivo CV
        practices: Lista de prácticas encontradas
        
    Returns:
        bool: True si se guardó exitosamente, False en caso contrario
    """
    try:
        cache_data = {
            "user_id": user_id,
            "cvFileUrl": cv_file_url,
            "practices": practices,
            "created_at": datetime.now()
        }
        
        # Guardar en la colección cache_matches
        db_jobs.collection("cache_matches").add(cache_data)
        
        print(f"💾 Cache guardado exitosamente para user_id: {user_id}")
        return True
        
    except Exception as e:
        print(f"❌ Error al guardar cache: {e}")
        return False

async def delete_cached_matches(cache_id: str) -> bool:
    """
    Elimina un cache específico por ID.
    
    Args:
        cache_id: ID del documento de cache
        
    Returns:
        bool: True si se eliminó exitosamente, False en caso contrario
    """
    try:
        db_jobs.collection("cache_matches").document(cache_id).delete()
        print(f"🗑️ Cache eliminado: {cache_id}")
        return True
        
    except Exception as e:
        print(f"❌ Error al eliminar cache: {e}")
        return False

async def clear_all_caches() -> int:
    """
    Limpia todos los caches (útil cuando se suben nuevas prácticas).
    
    Returns:
        int: Número de caches eliminados
    """
    try:
        # Buscar todos los caches
        cache_docs = db_jobs.collection("cache_matches").get()
        total_count = len(cache_docs)
        
        # Eliminar todos los caches
        for doc in cache_docs:
            doc.reference.delete()
        
        if total_count > 0:
            print(f"🧹 Limpieza completa de cache: {total_count} caches eliminados")
        
        return total_count
        
    except Exception as e:
        print(f"❌ Error al limpiar todos los caches: {e}")
        return 0
