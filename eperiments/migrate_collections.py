import asyncio
from db import db
from google.cloud.firestore_v1 import FieldFilter

async def migrate_collections(source: str, target: str, job_level: str):
    """
    Migra documentos de una colección fuente a una colección destino,
    agregando el campo 'job_level' especificado.
    
    Args:
        source (str): Nombre de la colección fuente
        target (str): Nombre de la colección destino  
        job_level (str): Valor del job_level a agregar a los documentos
    
    Evita sobrescritura verificando la existencia por ID del documento.
    Usa el mismo ID del documento original en el destino.
    """
    print(f"\n🚀 Iniciando migración: {source} → {target} (job_level: '{job_level}')...")
    
    source_collection = db.collection(source)
    target_collection = db.collection(target)
    
    try:
        # Obtener todos los documentos de la colección fuente
        source_docs = list(source_collection.stream())
        total_docs = len(source_docs)
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        
        print(f"Total de documentos encontrados en '{source}': {total_docs}")
        
        if total_docs == 0:
            print(f"⚠️  No se encontraron documentos en la colección '{source}'")
            return
        
        for i, doc in enumerate(source_docs, 1):
            doc_data = doc.to_dict()
            original_id = doc.id
            
            try:
                # Verificar si el documento ya existe en el destino usando el ID
                target_ref = target_collection.document(original_id)
                
                if target_ref.get().exists:
                    skipped_count += 1
                    if i % 50 == 0:
                        print(f"Progreso: {i}/{total_docs} | ✅ {migrated_count} | ⏭️ {skipped_count} | ❌ {error_count}")
                    continue
                
                # Agregar job_level al documento (o actualizarlo si ya existe)
                doc_data["job_level"] = job_level
                
                # Crear el documento en la colección destino con el mismo ID
                target_ref.set(doc_data)
                migrated_count += 1
                
                # Rate limiting para evitar sobrecargar Firestore
                if migrated_count % 10 == 0:
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                print(f"Error al migrar documento {original_id}: {e}")
                error_count += 1
            
            # Log de progreso cada 50 documentos
            if i % 50 == 0:
                print(f"Progreso: {i}/{total_docs} | ✅ {migrated_count} | ⏭️ {skipped_count} | ❌ {error_count}")
        
        # Resumen final
        print(f"\n🎉 Migración completada: {source} → {target}")
        print(f"   - Total de documentos procesados: {total_docs}")
        print(f"   - Migrados exitosamente: {migrated_count}")
        print(f"   - Saltados (ya existían): {skipped_count}")
        print(f"   - Errores: {error_count}")
        
        return {
            "total": total_docs,
            "migrated": migrated_count,
            "skipped": skipped_count,
            "errors": error_count
        }
        
    except Exception as e:
        print(f"Error crítico en migración {source} → {target}: {e}")
        return None

# Ejemplo de uso:
# await migrate_collections("practicasanalistas", "practicas_embeddings_test", "analista")
# await migrate_collections("practicas", "practicas_embeddings_test", "practicante")

if __name__ == "__main__":
    asyncio.run(main())
