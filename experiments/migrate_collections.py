import asyncio
import re
from datetime import datetime, timedelta
from db import db_jobs
from google.cloud.firestore_v1 import FieldFilter
from dateutil import parser

def parse_date_field(fecha_value) -> datetime:
    """Convierte diferentes tipos de fecha a datetime"""
    # Si ya es un datetime, retornarlo directamente
    if isinstance(fecha_value, datetime):
        return fecha_value.replace(tzinfo=None)
    
    # Si es un string, procesarlo
    if isinstance(fecha_value, str):
        # Mapeo de meses en español
        meses = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
            'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
        }
        
        try:
            # Formato: "1 de agosto de 2025, 1:15:37 p.m. UTC-5"
            pattern = r'(\d+) de (\w+) de (\d+), (\d+):(\d+):(\d+) ([ap])\.m\. UTC-(\d+)'
            match = re.match(pattern, fecha_value)
            
            if match:
                dia = int(match.group(1))
                mes_nombre = match.group(2).lower()
                año = int(match.group(3))
                hora = int(match.group(4))
                minuto = int(match.group(5))
                segundo = int(match.group(6))
                ampm = match.group(7)
                utc_offset = int(match.group(8))
                
                # Convertir mes
                mes = meses.get(mes_nombre)
                if not mes:
                    raise ValueError(f"Mes no reconocido: {mes_nombre}")
                
                # Ajustar hora para formato 24h
                if ampm == 'p' and hora != 12:
                    hora += 12
                elif ampm == 'a' and hora == 12:
                    hora = 0
                
                # Crear datetime
                fecha_dt = datetime(año, mes, dia, hora, minuto, segundo)
                return fecha_dt.replace(tzinfo=None)
            else:
                # Intentar con dateutil como fallback
                return parser.parse(fecha_value).replace(tzinfo=None)
                
        except Exception as e:
            raise ValueError(f"No se pudo parsear la fecha '{fecha_value}': {e}")
    
    # Si es un objeto DatetimeWithNanoseconds de Google
    try:
        # Intentar convertir a datetime usando str() y luego parsear
        fecha_str = str(fecha_value)
        return parser.parse(fecha_str).replace(tzinfo=None)
    except Exception as e:
        raise ValueError(f"No se pudo procesar el tipo de fecha: {type(fecha_value)} - {fecha_value}")

async def main():
    await migrate_collections("practicas", "practicas_embeddings_test", "practicante")
    
async def migrate_collections(source: str, target: str, job_level: str, days_back: int = 5):
    """
    Migra documentos de una colección fuente a una colección destino,
    agregando el campo 'job_level' especificado.
    
    Args:
        source (str): Nombre de la colección fuente
        target (str): Nombre de la colección destino  
        job_level (str): Valor del job_level a agregar a los documentos
        days_back (int): Solo procesar documentos de los últimos N días (default: 5)
    
    Evita sobrescritura verificando la existencia por ID del documento.
    Usa el mismo ID del documento original en el destino.
    """
    print(f"\n🚀 Iniciando migración: {source} → {target} (job_level: '{job_level}', últimos {days_back} días)...")
    
    source_collection = db_jobs.collection(source)
    target_collection = db_jobs.collection(target)
    
    # Calcular fecha límite (últimos N días)
    cutoff_date = datetime.now() - timedelta(days=days_back)
    print(f"📅 Solo procesando documentos desde: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Filtrar documentos por fecha (últimos N días)
        try:
            # Obtener todos los documentos y filtrar por fecha en Python
            all_docs = list(source_collection.stream())
            source_docs = []
            
            for doc in all_docs:
                doc_data = doc.to_dict()
                fecha_str = doc_data.get("fecha_agregado")
                
                if fecha_str:
                    try:
                        # Convertir fecha a datetime (maneja múltiples formatos)
                        fecha_dt = parse_date_field(fecha_str)
                        
                        if fecha_dt >= cutoff_date:
                            source_docs.append(doc)
                            
                    except Exception as e:
                        print(f"⚠️ Error parseando fecha '{fecha_str}': {e}")
                        continue
            
            print(f"✅ Encontrados {len(source_docs)} documentos de los últimos {days_back} días")
            
        except Exception as e:
            print(f"❌ Error al filtrar por fecha_agregado: {e}")
            raise
        
        total_docs = len(source_docs)
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        
        print(f"Total de documentos a procesar: {total_docs}")
        
        if total_docs == 0:
            print(f"⚠️  No se encontraron documentos en la colección '{source}'")
            return {
                "total": 0,
                "migrated": 0,
                "skipped": 0,
                "errors": 0
            }
        
        # Procesar en batches para mayor eficiencia
        batch_size = 50
        batch = db_jobs.batch()
        batch_count = 0
        
        for i, doc in enumerate(source_docs, 1):
            doc_data = doc.to_dict()
            original_id = doc.id
            
            try:
                # Verificar si el documento ya existe en el destino usando el ID
                target_ref = target_collection.document(original_id)
                
                if target_ref.get().exists:
                    skipped_count += 1
                    if i % 100 == 0:
                        print(f"Progreso: {i}/{total_docs} | ✅ {migrated_count} | ⏭️ {skipped_count} | ❌ {error_count}")
                    continue
                
                # Agregar job_level al documento (o actualizarlo si ya existe)
                doc_data["job_level"] = job_level
                
                # Agregar a batch en lugar de escribir individualmente
                batch.set(target_ref, doc_data)
                migrated_count += 1
                batch_count += 1
                
                # Commit batch cuando alcance el tamaño máximo
                if batch_count >= batch_size:
                    batch.commit()
                    batch = db_jobs.batch()
                    batch_count = 0
                    
                    # Rate limiting reducido para mayor velocidad
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                print(f"Error al migrar documento {original_id}: {e}")
                error_count += 1
            
            # Log de progreso cada 100 documentos
            if i % 100 == 0:
                print(f"Progreso: {i}/{total_docs} | ✅ {migrated_count} | ⏭️ {skipped_count} | ❌ {error_count}")
        
        # Commit batch final si quedan documentos
        if batch_count > 0:
            batch.commit()
        
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

async def cleanup_collection(collection_name: str, since_days: int):
    """
    Elimina documentos de una colección que sean más antiguos que N días.
    
    Args:
        collection_name (str): Nombre de la colección a limpiar
        since_days (int): Eliminar documentos más antiguos que N días
    
    Returns:
        dict: Estadísticas de la limpieza
    """
    print(f"\n🧹 Iniciando limpieza de colección: {collection_name} (eliminar documentos > {since_days} días)...")
    
    collection_ref = db_jobs.collection(collection_name)
    
    # Calcular fecha límite (documentos más antiguos que N días)
    cutoff_date = datetime.now() - timedelta(days=since_days)
    print(f"📅 Eliminando documentos anteriores a: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Obtener todos los documentos y filtrar por fecha en Python
        all_docs = list(collection_ref.stream())
        docs_to_delete = []
        
        for doc in all_docs:
            doc_data = doc.to_dict()
            fecha_str = doc_data.get("fecha_agregado")
            
            if fecha_str:
                try:
                    # Convertir fecha a datetime (maneja múltiples formatos)
                    fecha_dt = parse_date_field(fecha_str)
                    
                    if fecha_dt < cutoff_date:
                        docs_to_delete.append(doc)
                        
                except Exception as e:
                    print(f"⚠️ Error parseando fecha '{fecha_str}': {e}")
                    continue
        
        total_docs = len(docs_to_delete)
        deleted_count = 0
        error_count = 0
        
        print(f"📝 Encontrados {total_docs} documentos a eliminar")
        
        if total_docs == 0:
            print(f"✅ No hay documentos antiguos para eliminar en '{collection_name}'")
            return {
                "total": 0,
                "deleted": 0,
                "errors": 0
            }
        
        # Procesar en batches para mayor eficiencia
        batch_size = 50
        batch = db_jobs.batch()
        batch_count = 0
        
        for i, doc in enumerate(docs_to_delete, 1):
            try:
                # Agregar documento a batch para eliminación
                batch.delete(collection_ref.document(doc.id))
                deleted_count += 1
                batch_count += 1
                
                # Commit batch cuando alcance el tamaño máximo
                if batch_count >= batch_size:
                    batch.commit()
                    batch = db_jobs.batch()
                    batch_count = 0
                    
                    # Rate limiting
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                print(f"Error al eliminar documento {doc.id}: {e}")
                error_count += 1
            
            # Log de progreso cada 100 documentos
            if i % 100 == 0:
                print(f"Progreso: {i}/{total_docs} | ✅ {deleted_count} | ❌ {error_count}")
        
        # Commit batch final si quedan documentos
        if batch_count > 0:
            batch.commit()
        
        # Resumen final
        print(f"\n🎉 Limpieza completada: {collection_name}")
        print(f"   - Total de documentos procesados: {total_docs}")
        print(f"   - Eliminados exitosamente: {deleted_count}")
        print(f"   - Errores: {error_count}")
        
        return {
            "total": total_docs,
            "deleted": deleted_count,
            "errors": error_count
        }
        
    except Exception as e:
        print(f"Error crítico en limpieza de {collection_name}: {e}")
        return None

# Ejemplo de uso:
# await migrate_collections("practicasanalistas", "practicas_embeddings_test", "analista")
# await cleanup_collection("practicas", 5)


if __name__ == "__main__":
    asyncio.run(main())
