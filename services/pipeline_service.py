import asyncio
import time
import json
from typing import Dict, Any
from datetime import datetime

from schemas.pipeline_types import PipelineConfig, PipelineStep, PipelineResult, MigrationConfig, PipelineSections
from experiments.migrate_collections import migrate_collections, cleanup_collection
from services.job_service import generate_metadata_for_collection
from services.embedding_service import generate_embeddings_for_collection
from services.cache_service import clear_all_caches

class PipelineService:
    """Servicio para ejecutar el pipeline completo de procesamiento de ofertas laborales"""
    
    # Configuración por defecto para rate limiting y logging
    DEFAULT_MIGRATION_BATCH_SIZE = 50  # Aumentado para mayor eficiencia
    DEFAULT_MIGRATION_DELAY = 0.1  # Reducido para mayor velocidad
    DEFAULT_METADATA_DELAY = 0.2  # Reducido para mayor velocidad
    DEFAULT_METADATA_BATCH_DELAY = 1.0  # Reducido para mayor velocidad
    DEFAULT_EMBEDDING_BATCH_SIZE = 25  # Aumentado para mayor eficiencia
    DEFAULT_VERBOSE = True
    DEFAULT_PROGRESS_INTERVAL = 100  # Aumentado para menos logs
    
    def __init__(self):
        self.logs = []
    
    def log(self, message: str, verbose: bool = True):
        """Agregar log al historial"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        if verbose:
            print(log_entry)
        self.logs.append(log_entry)
    
    def _parse_date_field(self, fecha_value) -> datetime:
        """Convierte diferentes tipos de fecha a datetime"""
        from dateutil import parser
        import re
        
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
    
    async def run_pipeline(self, config: PipelineConfig) -> PipelineResult:
        """
        Ejecuta el pipeline completo de procesamiento de ofertas laborales
        
        Args:
            config: Configuración completa del pipeline
            
        Returns:
            PipelineResult: Resultado detallado del pipeline
        """
        start_total = time.time()
        steps = {}
        
        try:
            self.log("🚀 Iniciando pipeline de procesamiento de ofertas laborales", self.DEFAULT_VERBOSE)
            self.log(f"📁 Configuración:", self.DEFAULT_VERBOSE)
            
            # Mostrar información de migraciones
            if config.migrations:
                self.log(f"   - Migraciones: {len(config.migrations)}", self.DEFAULT_VERBOSE)
                for i, migration in enumerate(config.migrations, 1):
                    self.log(f"     {i}. {migration.source_collection} → {migration.target_collection} ({migration.job_level.value})", self.DEFAULT_VERBOSE)
            else:
                self.log(f"   - Migraciones: Ninguna configurada", self.DEFAULT_VERBOSE)
                if config.sections.enable_metadata or config.sections.enable_embeddings:
                    self.log(f"     → Procesando colección por defecto: practicas", self.DEFAULT_VERBOSE)
            
            self.log(f"   - Secciones habilitadas:", self.DEFAULT_VERBOSE)
            self.log(f"     - Migración: {config.sections.enable_migration}", self.DEFAULT_VERBOSE)
            self.log(f"     - Metadatos: {config.sections.enable_metadata}", self.DEFAULT_VERBOSE)
            self.log(f"     - Embeddings: {config.sections.enable_embeddings}", self.DEFAULT_VERBOSE)
            self.log(f"     - Limpieza cache: {config.sections.enable_cache_clear}", self.DEFAULT_VERBOSE)
            self.log(f"     - Limpieza documentos: {config.sections.enable_cleanup}", self.DEFAULT_VERBOSE)
            self.log(f"   - Sobrescribir metadatos: {config.overwrite_metadata}", self.DEFAULT_VERBOSE)
            self.log(f"   - Sobrescribir embeddings: {config.overwrite_embeddings}", self.DEFAULT_VERBOSE)
            self.log(f"   - Limpiezas: {len(config.cleanups)}", self.DEFAULT_VERBOSE)
            for i, cleanup in enumerate(config.cleanups, 1):
                self.log(f"     {i}. {cleanup.collection_name} (eliminar > {cleanup.since_days} días)", self.DEFAULT_VERBOSE)
            self.log("=" * 50, self.DEFAULT_VERBOSE)
            
            # Paso 1: Migración de colecciones (múltiples)
            if config.sections.enable_migration:
                if not config.migrations:
                    self.log("\n❌ PASO 1: Migración habilitada pero no hay migraciones configuradas", self.DEFAULT_VERBOSE)
                    steps["migration"] = PipelineStep(
                        step_name="Migración de colecciones",
                        status="error",
                        duration=0.0,
                        details={"reason": "Migración habilitada pero no hay migraciones configuradas"}
                    )
                    raise Exception("Migración habilitada pero no hay migraciones configuradas")
                
                step1_start = time.time()
                self.log("\n📝 PASO 1: Migrando colecciones...", self.DEFAULT_VERBOSE)
                
                migration_results = []
                total_migrated = 0
                total_skipped = 0
                total_errors = 0
                
                for i, migration in enumerate(config.migrations, 1):
                    self.log(f"   Migración {i}/{len(config.migrations)}: {migration.source_collection} → {migration.target_collection}", self.DEFAULT_VERBOSE)
                    
                    migration_result = await migrate_collections(
                         source=migration.source_collection,
                         target=migration.target_collection,
                         job_level=migration.job_level.value,
                         days_back=config.days_back
                     )
                    
                    if migration_result:
                        migration_results.append({
                            "migration": f"{migration.source_collection} → {migration.target_collection}",
                            "job_level": migration.job_level.value,
                            "result": migration_result
                        })
                        total_migrated += migration_result['migrated']
                        total_skipped += migration_result['skipped']
                        total_errors += migration_result['errors']
                        
                        self.log(f"     ✅ Completada: {migration_result['migrated']} migrados, {migration_result['skipped']} saltados", self.DEFAULT_VERBOSE)
                    else:
                        self.log(f"     ❌ Falló la migración: {migration.source_collection} → {migration.target_collection}", self.DEFAULT_VERBOSE)
                        raise Exception(f"La migración {migration.source_collection} → {migration.target_collection} falló")
                
                step1_duration = time.time() - step1_start
                
                steps["migration"] = PipelineStep(
                    step_name="Migración de colecciones",
                    status="completed",
                    duration=step1_duration,
                    details={
                        "total_migrations": len(config.migrations),
                        "total_migrated": total_migrated,
                        "total_skipped": total_skipped,
                        "total_errors": total_errors,
                        "migrations": migration_results
                    }
                )
                
                self.log(f"✅ Migración completada en {step1_duration:.2f}s", self.DEFAULT_VERBOSE)
                self.log(f"   - Total migraciones: {len(config.migrations)}", self.DEFAULT_VERBOSE)
                self.log(f"   - Total migrados: {total_migrated}", self.DEFAULT_VERBOSE)
                self.log(f"   - Total saltados: {total_skipped}", self.DEFAULT_VERBOSE)
                self.log(f"   - Total errores: {total_errors}", self.DEFAULT_VERBOSE)
            else:
                self.log("\n⏭️ PASO 1: Migración de colecciones deshabilitada", self.DEFAULT_VERBOSE)
                steps["migration"] = PipelineStep(
                    step_name="Migración de colecciones",
                    status="skipped",
                    duration=0.0,
                    details={"reason": "Sección deshabilitada"}
                )
            
            # Paso 2: Generación de metadatos (múltiples colecciones)
            if config.sections.enable_metadata:
                step2_start = time.time()
                self.log("\n📝 PASO 2: Generando metadatos...", self.DEFAULT_VERBOSE)
                
                metadata_results = []
                total_processed = 0
                total_skipped = 0
                total_errors = 0
                
                # Determinar colecciones a procesar
                if config.sections.enable_migration:
                    # Si hay migración, usar las colecciones destino de las migraciones
                    target_collections = list(set([migration.target_collection for migration in config.migrations]))
                else:
                    # Si no hay migración, asumir que se refiere a practicas
                    target_collections = ["practicas"]
                    self.log(f"   📝 Sin migración configurada, procesando colección por defecto: {target_collections[0]}", self.DEFAULT_VERBOSE)
                
                for i, target_collection in enumerate(target_collections, 1):
                    self.log(f"   Procesando colección {i}/{len(target_collections)}: {target_collection}", self.DEFAULT_VERBOSE)
                    
                    metadata_stats = await self._generate_metadata_with_stats(
                         collection_name=target_collection,
                         overwrite_existing=config.overwrite_metadata,
                         delay=self.DEFAULT_METADATA_DELAY,
                         batch_delay=self.DEFAULT_METADATA_BATCH_DELAY,
                         progress_interval=self.DEFAULT_PROGRESS_INTERVAL,
                         verbose=self.DEFAULT_VERBOSE,
                         days_back=config.days_back
                     )
                    
                    metadata_results.append({
                        "collection": target_collection,
                        "stats": metadata_stats
                    })
                    
                    total_processed += metadata_stats['processed']
                    total_skipped += metadata_stats['skipped']
                    total_errors += metadata_stats['errors']
                    
                    self.log(f"     ✅ Completada: {metadata_stats['processed']} procesados, {metadata_stats['skipped']} saltados", self.DEFAULT_VERBOSE)
                
                step2_duration = time.time() - step2_start
                
                steps["metadata"] = PipelineStep(
                    step_name="Generación de metadatos",
                    status="completed",
                    duration=step2_duration,
                    details={
                        "total_collections": len(target_collections),
                        "total_processed": total_processed,
                        "total_skipped": total_skipped,
                        "total_errors": total_errors,
                        "collections": metadata_results
                    }
                )
                
                self.log(f"✅ Metadatos generados en {step2_duration:.2f}s", self.DEFAULT_VERBOSE)
                self.log(f"   - Total colecciones: {len(target_collections)}", self.DEFAULT_VERBOSE)
                self.log(f"   - Total procesados: {total_processed}", self.DEFAULT_VERBOSE)
                self.log(f"   - Total saltados: {total_skipped}", self.DEFAULT_VERBOSE)
                self.log(f"   - Total errores: {total_errors}", self.DEFAULT_VERBOSE)
            else:
                self.log("\n⏭️ PASO 2: Generación de metadatos deshabilitada", self.DEFAULT_VERBOSE)
                steps["metadata"] = PipelineStep(
                    step_name="Generación de metadatos",
                    status="skipped",
                    duration=0.0,
                    details={"reason": "Sección deshabilitada"}
                )
            
            # Paso 3: Generación de embeddings (múltiples colecciones)
            if config.sections.enable_embeddings:
                step3_start = time.time()
                self.log("\n🧠 PASO 3: Generando embeddings...", self.DEFAULT_VERBOSE)
                
                embedding_results = []
                total_processed = 0
                total_skipped = 0
                total_errors = 0
                
                # Determinar colecciones a procesar
                if config.sections.enable_migration:
                    # Si hay migración, usar las colecciones destino de las migraciones
                    target_collections = list(set([migration.target_collection for migration in config.migrations]))
                else:
                    # Si no hay migración, asumir que se refiere a practicas
                    target_collections = ["practicas"]
                    self.log(f"   🧠 Sin migración configurada, procesando colección por defecto: {target_collections[0]}", self.DEFAULT_VERBOSE)
                
                for i, target_collection in enumerate(target_collections, 1):
                    self.log(f"   Procesando colección {i}/{len(target_collections)}: {target_collection}", self.DEFAULT_VERBOSE)
                    
                    embedding_stats = await self._generate_embeddings_with_stats(
                         collection_name=target_collection,
                         overwrite_existing=config.overwrite_embeddings,
                         batch_size=self.DEFAULT_EMBEDDING_BATCH_SIZE,
                         verbose=self.DEFAULT_VERBOSE,
                         days_back=config.days_back
                     )
                    
                    embedding_results.append({
                        "collection": target_collection,
                        "stats": embedding_stats
                    })
                    
                    total_processed += embedding_stats['processed']
                    total_skipped += embedding_stats['skipped']
                    total_errors += embedding_stats['errors']
                    
                    self.log(f"     ✅ Completada: {embedding_stats['processed']} procesados, {embedding_stats['skipped']} saltados", self.DEFAULT_VERBOSE)
                
                step3_duration = time.time() - step3_start
                
                steps["embeddings"] = PipelineStep(
                    step_name="Generación de embeddings",
                    status="completed",
                    duration=step3_duration,
                    details={
                        "total_collections": len(target_collections),
                        "total_processed": total_processed,
                        "total_skipped": total_skipped,
                        "total_errors": total_errors,
                        "collections": embedding_results
                    }
                )
                
                self.log(f"✅ Embeddings generados en {step3_duration:.2f}s", self.DEFAULT_VERBOSE)
                self.log(f"   - Total colecciones: {len(target_collections)}", self.DEFAULT_VERBOSE)
                self.log(f"   - Total procesados: {total_processed}", self.DEFAULT_VERBOSE)
                self.log(f"   - Total saltados: {total_skipped}", self.DEFAULT_VERBOSE)
            else:
                self.log("\n⏭️ PASO 3: Generación de embeddings deshabilitada", self.DEFAULT_VERBOSE)
                steps["embeddings"] = PipelineStep(
                    step_name="Generación de embeddings",
                    status="skipped",
                    duration=0.0,
                    details={"reason": "Sección deshabilitada"}
                )
            
            # Paso 4: Limpieza de caches (opcional)
            if config.sections.enable_cache_clear:
                step4_start = time.time()
                self.log("\n🧹 PASO 4: Limpiando caches de matches...", self.DEFAULT_VERBOSE)
                
                caches_eliminados = await clear_all_caches()
                
                step4_duration = time.time() - step4_start
                
                steps["cache_clear"] = PipelineStep(
                    step_name="Limpieza de caches",
                    status="completed",
                    duration=step4_duration,
                    details={"caches_removed": caches_eliminados}
                )
                
                self.log(f"✅ {caches_eliminados} caches eliminados en {step4_duration:.2f}s", self.DEFAULT_VERBOSE)
            else:
                 self.log("\n⏭️ PASO 4: Limpieza de caches deshabilitada", self.DEFAULT_VERBOSE)
                 steps["cache_clear"] = PipelineStep(
                     step_name="Limpieza de caches",
                     status="skipped",
                     duration=0.0,
                     details={"reason": "Sección deshabilitada"}
                 )
             
             # Paso 5: Limpieza de documentos antiguos (múltiples colecciones)
            if config.sections.enable_cleanup and config.cleanups:
                 step5_start = time.time()
                 self.log("\n🧹 PASO 5: Limpiando documentos antiguos...", self.DEFAULT_VERBOSE)
                 
                 cleanup_results = []
                 total_deleted = 0
                 total_errors = 0
                 
                 for i, cleanup in enumerate(config.cleanups, 1):
                     self.log(f"   Limpieza {i}/{len(config.cleanups)}: {cleanup.collection_name} (eliminar > {cleanup.since_days} días)", self.DEFAULT_VERBOSE)
                     
                     cleanup_result = await cleanup_collection(
                         collection_name=cleanup.collection_name,
                         since_days=cleanup.since_days
                     )
                     
                     if cleanup_result:
                         cleanup_results.append({
                             "collection": cleanup.collection_name,
                             "since_days": cleanup.since_days,
                             "result": cleanup_result
                         })
                         total_deleted += cleanup_result['deleted']
                         total_errors += cleanup_result['errors']
                         
                         self.log(f"     ✅ Completada: {cleanup_result['deleted']} eliminados, {cleanup_result['errors']} errores", self.DEFAULT_VERBOSE)
                     else:
                         self.log(f"     ❌ Falló la limpieza: {cleanup.collection_name}", self.DEFAULT_VERBOSE)
                         raise Exception(f"La limpieza de {cleanup.collection_name} falló")
                 
                 step5_duration = time.time() - step5_start
                 
                 steps["cleanup"] = PipelineStep(
                     step_name="Limpieza de documentos antiguos",
                     status="completed",
                     duration=step5_duration,
                     details={
                         "total_cleanups": len(config.cleanups),
                         "total_deleted": total_deleted,
                         "total_errors": total_errors,
                         "cleanups": cleanup_results
                     }
                 )
                 
                 self.log(f"✅ Limpieza completada en {step5_duration:.2f}s", self.DEFAULT_VERBOSE)
                 self.log(f"   - Total limpiezas: {len(config.cleanups)}", self.DEFAULT_VERBOSE)
                 self.log(f"   - Total eliminados: {total_deleted}", self.DEFAULT_VERBOSE)
                 self.log(f"   - Total errores: {total_errors}", self.DEFAULT_VERBOSE)
            else:
                 self.log("\n⏭️ PASO 5: Limpieza de documentos deshabilitada", self.DEFAULT_VERBOSE)
                 steps["cleanup"] = PipelineStep(
                     step_name="Limpieza de documentos antiguos",
                     status="skipped",
                     duration=0.0,
                     details={"reason": "Sección deshabilitada o sin configuraciones"}
                 )
             
            # Calcular tiempo total
            total_duration = time.time() - start_total
            
                         # Preparar resumen
            summary = {
                 "total_duration": total_duration,
                 "total_practices_migrated": steps.get("migration").details.get("total_migrated", 0) if steps.get("migration") and steps.get("migration").status == "completed" else 0,
                 "total_metadata_generated": steps.get("metadata").details.get("total_processed", 0) if steps.get("metadata") and steps.get("metadata").status == "completed" else 0,
                 "total_embeddings_generated": steps.get("embeddings").details.get("total_processed", 0) if steps.get("embeddings") and steps.get("embeddings").status == "completed" else 0,
                 "caches_cleared": steps.get("cache_clear").details.get("caches_removed", 0) if steps.get("cache_clear") and steps.get("cache_clear").status == "completed" else 0,
                 "total_documents_deleted": steps.get("cleanup").details.get("total_deleted", 0) if steps.get("cleanup") and steps.get("cleanup").status == "completed" else 0,
                 "logs": self.logs
             }
            
            self.log(f"\n✅ Pipeline completado exitosamente en {total_duration:.2f}s!", self.DEFAULT_VERBOSE)
            
            return PipelineResult(
                success=True,
                total_duration=total_duration,
                steps=steps,
                summary=summary
            )
            
        except Exception as e:
            total_duration = time.time() - start_total
            self.log(f"\n❌ Error en el pipeline: {e}", self.DEFAULT_VERBOSE)
            
            return PipelineResult(
                success=False,
                total_duration=total_duration,
                steps=steps,
                summary={},
                error_message=str(e)
            )
    
    async def _generate_metadata_with_stats(self, collection_name: str, overwrite_existing: bool, 
                                          delay: float, batch_delay: float, progress_interval: int, 
                                          verbose: bool, days_back: int = 5) -> Dict[str, Any]:
        """Genera metadatos y retorna estadísticas detalladas"""
        from db import db_jobs
        from datetime import datetime, timedelta
        
        self.log(f"Iniciando generación de metadatos para colección '{collection_name}' (sobrescribir: {overwrite_existing}, últimos {days_back} días)...", verbose)
        
        practicas_ref = db_jobs.collection(collection_name)
        
        # Calcular fecha límite (últimos N días)
        cutoff_date = datetime.now() - timedelta(days=days_back)
        self.log(f"📅 Solo procesando documentos desde: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}", verbose)
        
        # Contadores y manejo de errores
        processed_count = 0
        error_count = 0
        skipped_count = 0
        failed_docs = []
        
        try:
            # Filtrar documentos por fecha (últimos N días)
            try:
                # Obtener todos los documentos y filtrar por fecha en Python
                all_docs = list(practicas_ref.stream())
                docs = []
                
                for doc in all_docs:
                    doc_data = doc.to_dict()
                    fecha_str = doc_data.get("fecha_agregado")
                    
                    if fecha_str:
                        try:
                            # Convertir fecha a datetime (maneja múltiples formatos)
                            fecha_dt = self._parse_date_field(fecha_str)
                            
                            if fecha_dt >= cutoff_date:
                                docs.append(doc)
                                
                        except Exception as e:
                            self.log(f"⚠️ Error parseando fecha '{fecha_str}': {e}", verbose)
                            continue
                
                self.log(f"✅ Encontrados {len(docs)} documentos de los últimos {days_back} días", verbose)
                
            except Exception as e:
                self.log(f"❌ Error al filtrar por fecha_agregado: {e}", verbose)
                raise
            
            total_docs = len(docs)
            self.log(f"Total de documentos a procesar: {total_docs}", verbose)
            
            for i, doc in enumerate(docs, 1):
                doc_data = doc.to_dict()
                doc_id = doc.id
                
                # Verificar si ya tiene metadatos (solo saltar si no queremos sobrescribir)
                if not overwrite_existing and "metadata" in doc_data and doc_data["metadata"]:
                    skipped_count += 1
                    if i % progress_interval == 0:
                        self.log(f"Progreso: {i}/{total_docs} | ✅ {processed_count} | ❌ {error_count} | ⏭️ {skipped_count}", verbose)
                    continue
                
                # Extraer título y descripción
                title = doc_data.get("title", doc_data.get("titulo", None))
                description = doc_data.get("description", doc_data.get("descripcion", None))
                
                if not title and not description:
                    skipped_count += 1
                    if i % progress_interval == 0:
                        self.log(f"Progreso: {i}/{total_docs} | ✅ {processed_count} | ❌ {error_count} | ⏭️ {skipped_count}", verbose)
                    continue
                
                # Generar metadatos (ahora incluye todos los campos en una sola llamada)
                metadata = await extract_metadata_with_gemini(title, description)
                
                if metadata:
                    # Actualizar el documento en Firestore
                    try:
                        doc_ref = practicas_ref.document(doc_id)
                        doc_ref.update({"metadata": metadata})
                        processed_count += 1
                        
                        # Pequeña pausa para evitar rate limiting
                        await asyncio.sleep(delay)
                        
                    except Exception as e:
                        self.log(f"Error al guardar metadatos para {doc_id}: {e}", verbose)
                        failed_docs.append({"id": doc_id, "title": title, "error": str(e)})
                        error_count += 1
                else:
                    failed_docs.append({"id": doc_id, "title": title, "error": "No se pudieron generar metadatos"})
                    error_count += 1
                
                # Rate limiting - pausa cada 10 documentos procesados
                if (processed_count + error_count) % 10 == 0:
                    await asyncio.sleep(batch_delay)
                
                # Log de progreso
                if i % progress_interval == 0:
                    self.log(f"Progreso: {i}/{total_docs} | ✅ {processed_count} | ❌ {error_count} | ⏭️ {skipped_count}", verbose)
            
            # Guardar documentos fallidos para reintentos
            if failed_docs:
                with open("failed_metadata_docs.json", "w", encoding="utf-8") as f:
                    json.dump(failed_docs, f, indent=2, ensure_ascii=False)
                self.log(f"⚠️ {len(failed_docs)} documentos fallidos guardados en failed_metadata_docs.json", verbose)
            
            return {
                "total": total_docs,
                "processed": processed_count,
                "skipped": skipped_count,
                "errors": error_count,
                "failed_docs_count": len(failed_docs)
            }
            
        except Exception as e:
            self.log(f"Error crítico al acceder a la colección de Firestore: {e}", verbose)
            raise
    
    async def _generate_embeddings_with_stats(self, collection_name: str, overwrite_existing: bool, 
                                            batch_size: int, verbose: bool, days_back: int = 5) -> Dict[str, Any]:
        """Genera embeddings y retorna estadísticas detalladas"""
        from services.embedding_service import get_embedding_from_text, metadata_to_string
        from db import db_jobs
        from datetime import datetime, timedelta
        
        self.log(f"Iniciando generación de embeddings para colección '{collection_name}' (sobrescribir: {overwrite_existing}, últimos {days_back} días)...", verbose)
        
        practicas_ref = db_jobs.collection(collection_name)
        embeddings_ref = db_jobs.collection(collection_name)
        
        # Calcular fecha límite (últimos N días)
        cutoff_date = datetime.now() - timedelta(days=days_back)
        self.log(f"📅 Solo procesando documentos desde: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}", verbose)
        
        try:
            # Filtrar documentos por fecha (últimos N días)
            try:
                # Obtener todos los documentos y filtrar por fecha en Python
                all_docs = list(practicas_ref.stream())
                practicas_docs = []
                
                for doc in all_docs:
                    doc_data = doc.to_dict()
                    fecha_str = doc_data.get("fecha_agregado")
                    
                    if fecha_str:
                        try:
                            # Convertir fecha a datetime (maneja múltiples formatos)
                            fecha_dt = self._parse_date_field(fecha_str)
                            
                            if fecha_dt >= cutoff_date:
                                practicas_docs.append(doc)
                                
                        except Exception as e:
                            self.log(f"⚠️ Error parseando fecha '{fecha_str}': {e}", verbose)
                            continue
                
                self.log(f"✅ Encontrados {len(practicas_docs)} documentos de los últimos {days_back} días", verbose)
                
            except Exception as e:
                self.log(f"❌ Error al filtrar por fecha_agregado: {e}", verbose)
                raise
            
            self.log(f"📝 {len(practicas_docs)} documentos a procesar.", verbose)
        except Exception as e:
            self.log(f"❌ Error leyendo colección: {e}", verbose)
            raise
        
        batch = db_jobs.batch()
        processed = 0
        skipped = 0
        error_count = 0
        
        for doc in practicas_docs:
            data = doc.to_dict()
            metadata = data.get("metadata")
            job_level = data.get("job_level")
            
            # Verificar si ya tiene embedding (solo saltar si no queremos sobrescribir)
            if not overwrite_existing and "embedding" in data and data["embedding"]:
                skipped += 1
                continue
            
            if not metadata:
                self.log(f"⚠️ Sin metadata para '{doc.id}', omitido.", verbose)
                skipped += 1
                continue
            
            # Crear metadata completo: combinar metadata original + job_level
            complete_metadata = metadata.copy()
            if job_level:
                complete_metadata["job_level"] = job_level
            
            # Convertir metadata completo a string JSON para embedding
            metadata_text = metadata_to_string(complete_metadata)
            if not metadata_text:
                self.log(f"⚠️ Metadata vacío para '{doc.id}', omitido.", verbose)
                skipped += 1
                continue
            
            if verbose:
                self.log(f"📝 Procesando '{doc.id}': {metadata_text[:100]}...", verbose)
            
            # Generar embedding del metadata
            vector = await get_embedding_from_text(metadata_text)
            if not vector:
                self.log(f"⚠️ Embedding fallido para '{doc.id}', omitido.", verbose)
                error_count += 1
                continue
            
            # Actualizar documento con embedding
            update_data = {"embedding": vector}
            
            # Si es sobrescritura, actualizar solo los campos necesarios
            if overwrite_existing:
                batch.update(embeddings_ref.document(doc.id), update_data)
            else:
                # Si es nuevo, incluir todos los datos
                new_doc_data = {"embedding": vector, **data}
                batch.set(embeddings_ref.document(doc.id), new_doc_data)
            
            processed += 1
            
            if processed % batch_size == 0:
                self.log(f"📦 Enviando batch... (procesados: {processed}, saltados: {skipped})", verbose)
                batch.commit()
                batch = db_jobs.batch()
        
        if processed % batch_size != 0:
            self.log("📤 Enviando último batch...", verbose)
            batch.commit()
        
        return {
            "total": len(practicas_docs),
            "processed": processed,
            "skipped": skipped,
            "errors": error_count
        }
