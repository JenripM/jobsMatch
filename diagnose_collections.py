#!/usr/bin/env python3
"""
Script de diagnóstico para verificar el estado actual de las colecciones de Firestore
después de un error en la migración.
"""

import asyncio
from datetime import datetime
from db import db_jobs

def print_separator(title=""):
    """Imprime un separador visual"""
    if title:
        print(f"\n{'='*60}")
        print(f" {title}")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")

async def get_collection_info(collection_name):
    """
    Obtiene información detallada de una colección
    
    Returns:
        dict: Información de la colección o None si no existe
    """
    try:
        collection_ref = db_jobs.collection(collection_name)
        docs = list(collection_ref.stream())
        
        if not docs:
            return {
                "exists": False,
                "count": 0,
                "sample_ids": [],
                "sample_data": []
            }
        
        # Obtener algunos IDs de ejemplo
        sample_ids = [doc.id for doc in docs[:5]]
        
        # Obtener datos de ejemplo para verificar campos
        sample_data = []
        for doc in docs[:3]:  # Solo 3 para no saturar la salida
            doc_dict = doc.to_dict()
            sample_data.append({
                "id": doc.id,
                "has_embeddings": "embeddings" in doc_dict and doc_dict["embeddings"] is not None,
                "has_metadata": "metadata" in doc_dict and doc_dict["metadata"] is not None,
                "fields": list(doc_dict.keys())
            })
        
        return {
            "exists": True,
            "count": len(docs),
            "sample_ids": sample_ids,
            "sample_data": sample_data
        }
    except Exception as e:
        print(f"❌ Error al obtener información de '{collection_name}': {e}")
        return None

async def check_document_fields(collection_name, sample_size=5):
    """
    Verifica los campos de algunos documentos para entender la estructura
    """
    try:
        collection_ref = db_jobs.collection(collection_name)
        docs = list(collection_ref.stream())
        
        if not docs:
            print(f"   ℹ️  Colección '{collection_name}' está vacía")
            return
        
        print(f"   📊 Analizando {min(sample_size, len(docs))} documentos de '{collection_name}':")
        
        for i, doc in enumerate(docs[:sample_size]):
            doc_dict = doc.to_dict()
            print(f"      📄 Documento {i+1} (ID: {doc.id}):")
            print(f"         - Campos: {list(doc_dict.keys())}")
            print(f"         - Tiene embeddings: {'✅' if 'embeddings' in doc_dict and doc_dict['embeddings'] else '❌'}")
            print(f"         - Tiene metadata: {'✅' if 'metadata' in doc_dict and doc_dict['metadata'] else '❌'}")
            
            # Mostrar algunos campos específicos si existen
            if 'title' in doc_dict:
                print(f"         - Título: {doc_dict['title'][:50]}...")
            if 'company' in doc_dict:
                print(f"         - Empresa: {doc_dict['company']}")
            
            print()
            
    except Exception as e:
        print(f"   ❌ Error al analizar campos de '{collection_name}': {e}")

async def main():
    """Función principal de diagnóstico"""
    print_separator("DIAGNÓSTICO DE COLECCIONES FIRESTORE")
    print(f"⏰ Ejecutado en: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🔍 Verificando estado actual después del error de migración...")
    
    # Colecciones a verificar
    collections_to_check = [
        "practicas", 
        "practicas_embeddings", 
        "practicas_embeddings_test"
    ]
    
    print("\n📊 ESTADO ACTUAL DE LAS COLECCIONES:")
    print("=" * 50)
    
    collection_status = {}
    
    for collection_name in collections_to_check:
        print(f"\n🔍 Verificando '{collection_name}':")
        info = await get_collection_info(collection_name)
        
        if info:
            if info["exists"]:
                print(f"   ✅ EXISTE: {info['count']} documentos")
                print(f"   📝 IDs de ejemplo: {info['sample_ids']}")
                collection_status[collection_name] = info
            else:
                print(f"   ❌ NO EXISTE o está vacía")
                collection_status[collection_name] = info
        else:
            print(f"   ❌ ERROR al verificar")
            collection_status[collection_name] = None
    
    # Análisis detallado de campos
    print("\n🔍 ANÁLISIS DETALLADO DE CAMPOS:")
    print("=" * 50)
    
    for collection_name in collections_to_check:
        if collection_status.get(collection_name, {}).get("exists"):
            await check_document_fields(collection_name)
    
    # Análisis de situación
    print("\n🔍 ANÁLISIS DE SITUACIÓN:")
    print("=" * 50)
    
    practicas_exists = collection_status.get("practicas", {}).get("exists", False)
    practicas_count = collection_status.get("practicas", {}).get("count", 0)
    embeddings_exists = collection_status.get("practicas_embeddings", {}).get("exists", False)
    test_exists = collection_status.get("practicas_embeddings_test", {}).get("exists", False)
    
    if practicas_exists and practicas_count > 0:
        print("✅ La colección 'practicas' existe y tiene documentos")
        
        # Verificar si tiene embeddings
        practicas_info = collection_status.get("practicas", {})
        if practicas_info.get("sample_data"):
            has_embeddings = any(doc["has_embeddings"] for doc in practicas_info["sample_data"])
            has_metadata = any(doc["has_metadata"] for doc in practicas_info["sample_data"])
            
            if has_embeddings and has_metadata:
                print("🎯 'practicas' parece contener documentos con embeddings y metadata")
                print("   Esto sugiere que la migración se ejecutó parcialmente")
            elif has_embeddings:
                print("⚠️  'practicas' tiene algunos embeddings pero no metadata completa")
            else:
                print("❌ 'practicas' no tiene embeddings - migración falló")
        else:
            print("⚠️  No se pudieron analizar los campos de 'practicas'")
    else:
        print("❌ La colección 'practicas' no existe o está vacía")
    
    if embeddings_exists:
        print("⚠️  'practicas_embeddings' aún existe - no se borró completamente")
    else:
        print("✅ 'practicas_embeddings' fue borrada exitosamente")
    
    if test_exists:
        print("⚠️  'practicas_embeddings_test' aún existe - no se renombró")
    else:
        print("✅ 'practicas_embeddings_test' fue procesada (borrada o renombrada)")
    
    # Recomendaciones
    print("\n💡 RECOMENDACIONES:")
    print("=" * 50)
    
    if practicas_exists and practicas_count > 0:
        print("1. ✅ La colección 'practicas' existe y tiene documentos")
        print("2. 🔍 Verifica que todos los documentos tengan embeddings y metadata")
        print("3. 🧹 Si hay documentos sin embeddings, considera limpiarlos")
        
        if embeddings_exists or test_exists:
            print("4. 🗑️  Ejecuta el script de limpieza para borrar colecciones residuales")
        else:
            print("4. 🎯 La migración parece estar completa")
    else:
        print("1. ❌ La migración falló completamente")
        print("2. 🔄 Necesitas restaurar desde backup y ejecutar nuevamente")
        print("3. ⚠️  NO ejecutes más scripts hasta restaurar")
    
    print(f"\n⏰ Diagnóstico completado en: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Diagnóstico interrumpido por el usuario")
    except Exception as e:
        print(f"\n❌ Error inesperado durante diagnóstico: {e}")
        import traceback
        print(f"Stack trace: {traceback.format_exc()}")
