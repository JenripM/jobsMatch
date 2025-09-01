#!/usr/bin/env python3
"""
Script para limpiar la colección legacy 'practicas_embeddings'.
Este script solo elimina esta colección específica sin tocar las demás.
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

async def delete_collection_safely(collection_name):
    """
    Borra una colección documento por documento para evitar "Transaction too big"
    
    Args:
        collection_name (str): Nombre de la colección a borrar
        
    Returns:
        bool: True si se borró exitosamente, False en caso contrario
    """
    print(f"🗑️  Borrando colección '{collection_name}' documento por documento...")
    
    try:
        collection_ref = db_jobs.collection(collection_name)
        
        # Obtener todos los documentos
        docs = list(collection_ref.stream())
        
        if not docs:
            print(f"   ℹ️  La colección '{collection_name}' ya está vacía o no existe")
            return True
        
        print(f"   📊 Encontrados {len(docs)} documentos para borrar")
        print(f"   🐌 Eliminando uno por uno (más lento pero seguro)")
        
        total_deleted = 0
        
        for i, doc in enumerate(docs):
            try:
                # Eliminar documento individual
                doc.reference.delete()
                total_deleted += 1
                
                # Mostrar progreso cada 10 documentos
                if (i + 1) % 10 == 0:
                    print(f"   📝 Progreso: {i + 1}/{len(docs)} documentos eliminados")
                
                # Pausa mínima entre eliminaciones
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"   ⚠️  Error al eliminar documento {doc.id}: {e}")
                # Continuar con el siguiente documento
                continue
        
        print(f"   🎯 Total de documentos borrados: {total_deleted}")
        return True
        
    except Exception as e:
        print(f"   ❌ Error al borrar colección '{collection_name}': {e}")
        return False

async def verify_collection_deleted(collection_name):
    """
    Verifica que una colección haya sido eliminada completamente
    """
    try:
        collection_ref = db_jobs.collection(collection_name)
        docs = list(collection_ref.stream())
        
        if not docs:
            print(f"   ✅ Verificación exitosa: '{collection_name}' fue eliminada completamente")
            return True
        else:
            print(f"   ❌ Verificación fallida: '{collection_name}' aún tiene {len(docs)} documentos")
            return False
            
    except Exception as e:
        print(f"   ❌ Error al verificar '{collection_name}': {e}")
        return False

async def main():
    """Función principal de limpieza"""
    print_separator("LIMPIEZA DE COLECCIÓN LEGACY")
    print(f"⏰ Iniciado en: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🎯 Objetivo: Eliminar solo 'practicas_embeddings' (colección legacy)")
    
    # Confirmación del usuario
    print("\n🔒 ¿Estás seguro de que quieres eliminar 'practicas_embeddings'?")
    print("   Esta colección:")
    print("   - Es legacy (sin embeddings ni metadata)")
    print("   - Tiene 200 documentos")
    print("   - Será eliminada PERMANENTEMENTE")
    
    response = input("\n   Escribe 'ELIMINAR' para proceder: ")
    
    if response != "ELIMINAR":
        print("❌ Operación cancelada por el usuario")
        return
    
    print("\n🚀 Iniciando limpieza...")
    
    # PASO 1: Verificar estado actual
    print("\n🔹 PASO 1: Verificando estado actual")
    print("-" * 50)
    
    try:
        collection_ref = db_jobs.collection("practicas_embeddings")
        docs = list(collection_ref.stream())
        
        if docs:
            print(f"   📊 'practicas_embeddings' existe con {len(docs)} documentos")
            print(f"   📝 IDs de ejemplo: {[doc.id for doc in docs[:3]]}")
        else:
            print(f"   ℹ️  'practicas_embeddings' ya está vacía o no existe")
            print("   ✅ No hay nada que limpiar")
            return
            
    except Exception as e:
        print(f"   ❌ Error al verificar 'practicas_embeddings': {e}")
        return
    
    # PASO 2: Eliminar la colección
    print("\n🔹 PASO 2: Eliminando 'practicas_embeddings'")
    print("-" * 50)
    
    success = await delete_collection_safely("practicas_embeddings")
    
    if not success:
        print("❌ La eliminación falló. Revisa los errores anteriores.")
        return
    
    # PASO 3: Verificación
    print("\n🔹 PASO 3: Verificando eliminación")
    print("-" * 50)
    
    verification_success = await verify_collection_deleted("practicas_embeddings")
    
    # Resumen final
    print_separator("RESUMEN DE LIMPIEZA")
    
    if verification_success:
        print("✅ LIMPIEZA COMPLETADA EXITOSAMENTE")
        print("   - Colección 'practicas_embeddings' eliminada completamente")
        print("   - 200 documentos legacy removidos")
        print("\n🎯 Próximo paso: Regenerar embeddings en 'practicas'")
    else:
        print("❌ LA LIMPIEZA NO SE COMPLETÓ COMPLETAMENTE")
        print("   - Algunos documentos pueden haber quedado")
        print("   - Revisa manualmente en Firebase Console")
    
    print(f"\n⏰ Finalizado en: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Operación interrumpida por el usuario")
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        print(f"Stack trace: {traceback.format_exc()}")
