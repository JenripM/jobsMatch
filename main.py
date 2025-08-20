from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import json
import time
import asyncio
import logging
from datetime import datetime
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from dotenv import load_dotenv
import os

# Cargar variables de entorno desde .env
load_dotenv()

# Configuración centralizada
from config import (
    STREAMING_CHUNK_SIZE,
    STREAMING_ENABLED,
    USE_PURE_STREAMING,
    DEFAULT_SINCE_DAYS,
    DEFAULT_PERCENTAGE_THRESHOLD,
    DEFAULT_PRACTICES_LIMIT,
    LOG_LEVEL
)

# Servicios
from services.job_service import (
    obtener_practicas,
    obtener_practicas_recientes,
    buscar_practicas_afines,
    obtener_practica_por_id_y_calcular_match,
)
from services.user_service import (
    fetch_user_cv,
    save_cv as save_cv_service,
    update_cv as update_cv_service,
    get_user_cvs as get_user_cvs_service,
    upload_cv_to_database,
    delete_cv as delete_cv_service,
    get_cv_by_id,
)
from services.cache_service import (
    get_cached_matches,
    save_cached_matches,
    clear_all_caches,
)
from services.pipeline_service import PipelineService
from schemas.pipeline_types import PipelineConfig, MigrationConfig, PipelineSections

# Configurar logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger(__name__)

app = FastAPI()

# Configuración de CORS (SIN GZipMiddleware para streaming puro)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)







def custom_json_serializer(obj):
    """Serializer personalizado para manejar tipos especiales de Firestore"""
    if isinstance(obj, DatetimeWithNanoseconds):
        return obj.isoformat()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

async def generate_ndjson_streaming_practices(practicas: list, timing_stats: dict) -> AsyncGenerator[str, None]:
    """
    Generador asíncrono que produce prácticas en formato NDJSON streaming puro.
    
    NDJSON STREAMING: Cada práctica se envía como una línea JSON separada.
    El frontend puede procesar cada línea inmediatamente sin esperar el JSON completo.
    
    Args:
        practicas: Lista de prácticas a enviar
        timing_stats: Estadísticas de tiempo del procesamiento
    
    Yields:
        str: Líneas NDJSON (una práctica por línea + metadata al final)
    """
    logger.info(f"🚀 Iniciando NDJSON streaming de {len(practicas)} prácticas")
    logger.info(f"📝 Formato: Una línea JSON por práctica")
    
    try:
        # Procesar prácticas individualmente como líneas NDJSON
        total_practicas = len(practicas)
        
        for practica_index, practica in enumerate(practicas):
            #logger.info(f"📦 Enviando práctica {practica_index + 1}/{total_practicas}")
            
            # Serializar práctica individual como línea JSON
            practica_json = json.dumps(practica, ensure_ascii=False, default=custom_json_serializer)
            
            # Enviar práctica como línea NDJSON (con salto de línea)
            yield f"{practica_json}\n"
            
            # Pausa mínima para permitir procesamiento progresivo
            await asyncio.sleep(0.05)  # 50ms por práctica
        
        # Preparar metadata como última línea NDJSON
        metadata = {
            "metadata": {
                "total_practicas_procesadas": len(practicas),
                "streaming": True,
                "chunk_size": STREAMING_CHUNK_SIZE,
                "timing_stats": timing_stats
            }
        }
        
        # Enviar metadata como última línea NDJSON
        metadata_json = json.dumps(metadata, ensure_ascii=False, default=custom_json_serializer)
        yield f"{metadata_json}\n"
        
        logger.info(f"✅ NDJSON streaming completado exitosamente - {len(practicas)} prácticas + metadata enviadas")
        
    except Exception as e:
        logger.error(f"❌ Error durante NDJSON streaming: {e}")
        # Enviar error como línea NDJSON
        error_data = {
            "error": {
                "message": f"Error durante streaming: {str(e)}",
                "streaming": True,
                "format": "ndjson"
            }
        }
        error_json = json.dumps(error_data, ensure_ascii=False, default=custom_json_serializer)
        yield f"{error_json}\n"


@app.post("/match-practices")
async def match_practices(request: Request):
    """
    Endpoint optimizado para matching de prácticas usando CV seleccionado
    Mejoras implementadas:
    - Sistema de cache para evitar recalcular matches cuando el CV no ha cambiado
    - Usa cv_selected_id para consultar CV directamente en la base de datos
    - Si el CV tiene embeddings, los usa directamente (más rápido)
    - Si no tiene embeddings, usa el campo data para generar embeddings
    - Soporte para compresión gzip bidireccional (request y response)
    - Medición detallada de tiempos por etapa
    """
    # Iniciar medición de tiempo total
    start_total = time.time()
    timing_stats = {}
    
    try:
        # Leer el body del request y parsear JSON
        body = await request.body()
        request_data = json.loads(body)
        
        print("------ Inputs ------ ")
        print("user_id: ", request_data.get("user_id", None))
        print("limit: ", request_data.get("limit", None))

        user_id = request_data.get("user_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id es requerido")

        # Obtener el CV del usuario
        cv_user = await fetch_user_cv(user_id)
        
        if not cv_user:
            raise HTTPException(status_code=404, detail="No se pudo obtener el CV del usuario. Verifique que el usuario existe y tiene un CV válido.")

        # Obtener la URL del archivo CV para usar como clave de cache
        cv_file_url = cv_user.get("fileUrl")
        if not cv_file_url:
            print("⚠️ CV no tiene fileUrl, no se puede usar cache")
            cv_file_url = "no_file_url"

        # Verificar cache antes de procesar
        cached_matches = await get_cached_matches(user_id, cv_file_url)
        if cached_matches:
            print(f"🚀 Devolviendo {len(cached_matches.get('practices', []))} prácticas desde cache")
            
            # Calcular tiempos para respuesta desde cache
            timing_stats['cache_hit'] = True
            timing_stats['total_time'] = time.time() - start_total
            
            # Usar streaming si está habilitado
            if STREAMING_ENABLED and len(cached_matches.get('practices', [])) > 0:
                print(f"📡 Usando STREAMING PURO desde cache - {len(cached_matches['practices'])} prácticas")
                
                return StreamingResponse(
                    generate_ndjson_streaming_practices(cached_matches['practices'], timing_stats),
                    media_type="application/x-ndjson",
                    headers={
                        "Content-Type": "application/x-ndjson",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive"
                    }
                )
            else:
                print(f"📄 Usando respuesta JSON tradicional desde cache - {len(cached_matches['practices'])} prácticas")
                
                limit = request_data.get("limit", DEFAULT_PRACTICES_LIMIT)
                response_data = {
                    "practicas": cached_matches['practices'][:limit],
                    "metadata": {
                        "total_practicas_procesadas": len(cached_matches['practices']),
                        "total_practicas_devueltas": min(limit, len(cached_matches['practices'])),
                        "streaming": False,
                        "cache_hit": True,
                        "timing_stats": timing_stats
                    }
                }
                
                return response_data

        # Si no hay cache, calcular matches
        print("🔍 No se encontró cache, calculando matches")
        
        if not cv_user.get("embeddings", None):
            # Retrocompatibilidad con versiones antiguas de la web
            # Este escenario casi nunca deberia ocurrir. Actualmente se maneja la generacion de embeddings desde que se sube el mismo CV. la unica posibilidad de que alguien tenga CVData pero no embeddings es que haya creado su cv previo a la release del dia 15 de agosto de 2025
            # Generar embeddings del CV desde datos estructurados usando extract_metadata_with_gemini
            print(f"⏱️  Paso 1: Generando embeddings del CV desde datos estructurados...")
            step1_start = time.time()
            from services.user_service import generate_cv_embeddings
            
            # Convertir cv_data a string usando json.dumps
            cv_text = json.dumps(cv_user.get("data", None), ensure_ascii=False)
            embeddings = await generate_cv_embeddings(cv_text)
            cv_user["embeddings"] = embeddings
            print(f"✅ Paso 1 completado en {time.time() - step1_start:.2f} segundos (generación desde datos estructurados)")
            #actualizar el cv en la base de datos
            await update_cv_service(cv_user.get("id"), cv_user)
        
        # Iniciar medición de búsqueda
        start_search = time.time()
        
        practicas_con_similitud = await buscar_practicas_afines(
            cv_embeddings=cv_user.get("embeddings", None),
            #devolver practicas solo mayores al umbral configurado
            percentage_threshold=DEFAULT_PERCENTAGE_THRESHOLD,
            #solo buscar prácticas recientes según configuración
            sinceDays=DEFAULT_SINCE_DAYS,
        )
        
        timing_stats['search_matching'] = time.time() - start_search
        
        # Guardar en cache si se encontraron prácticas
        if practicas_con_similitud and len(practicas_con_similitud) > 0:
            await save_cached_matches(user_id, cv_file_url, practicas_con_similitud)
        
        # 4. ETAPA: Preparación de respuesta
        start_response_prep = time.time()
        
        # Calcular tiempo total hasta ahora
        timing_stats['total_processing'] = time.time() - start_total
        timing_stats['response_preparation'] = time.time() - start_response_prep
        timing_stats['total_time'] = time.time() - start_total
        timing_stats['cache_hit'] = False
        
        print(f"\n⏱️ ESTADÍSTICAS DE TIEMPO:")
        print(f"   - Búsqueda/Matching: {timing_stats['search_matching']:.4f}s")
        print(f"   - Preparación respuesta: {timing_stats['response_preparation']:.4f}s")
        print(f"   - 🎆 TIEMPO TOTAL: {timing_stats['total_time']:.4f}s")
        
        # Usar siempre streaming puro sin compresión
        if STREAMING_ENABLED and len(practicas_con_similitud) > 0:
            print(f"📡 Usando STREAMING PURO - {len(practicas_con_similitud)} prácticas")
            
            # Retornar StreamingResponse sin compresión
            return StreamingResponse(
                generate_ndjson_streaming_practices(practicas_con_similitud, timing_stats),
                media_type="application/x-ndjson",
                headers={
                    "Content-Type": "application/x-ndjson",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
            )
        else:
            print(f"📄 Usando respuesta JSON tradicional - {len(practicas_con_similitud)} prácticas")
            
            # Respuesta tradicional sin compresión
            limit = request_data.get("limit", DEFAULT_PRACTICES_LIMIT)
            response_data = {
                "practicas": practicas_con_similitud[:limit],
                "metadata": {
                    "total_practicas_procesadas": len(practicas_con_similitud),
                    "total_practicas_devueltas": min(limit, len(practicas_con_similitud)),
                    "streaming": False,
                    "cache_hit": False,
                    "timing_stats": timing_stats
                }
            }
            
            return response_data
            
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Error al parsear JSON")
    except Exception as e:
        print(f"❌ Error en match_practices: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@app.post("/match-practice")
async def match_single_practice(request: Request):
    """
    Endpoint para calcular el match entre el CV de un usuario y una práctica específica.
    
    Este endpoint se utiliza desde la ruta frontend /job_offers/{job_offer_id}
    y devuelve una sola práctica con su score de match calculado.
    
    Args:
        request: Request con JSON body que debe contener:
            - user_id: ID del usuario
            - practice_id: ID de la práctica específica
    
    Returns:
        dict: Práctica con scores de match calculados
    """
    # Iniciar medición de tiempo total
    start_total = time.time()
    timing_stats = {}
    
    try:
        # Leer el body del request y parsear JSON
        body = await request.body()
        request_data = json.loads(body)
        
        print("------ Inputs ------ ")
        print("user_id: ", request_data.get("user_id", None))
        print("practice_id: ", request_data.get("practice_id", None))

        user_id = request_data.get("user_id")
        practice_id = request_data.get("practice_id")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id es requerido")
        
        if not practice_id:
            raise HTTPException(status_code=400, detail="practice_id es requerido")

        # Obtener el CV del usuario
        cv_user = await fetch_user_cv(user_id)
        
        if not cv_user:
            raise HTTPException(status_code=404, detail="No se pudo obtener el CV del usuario. Verifique que el usuario existe y tiene un CV válido.")

        # Verificar que el CV tenga embeddings
        if not cv_user.get("embeddings", None):
            # Retrocompatibilidad con versiones antiguas de la web
            print(f"⏱️  Generando embeddings del CV desde datos estructurados...")
            step1_start = time.time()
            from services.user_service import generate_cv_embeddings
            
            # Convertir cv_data a string usando json.dumps
            cv_text = json.dumps(cv_user.get("data", None), ensure_ascii=False)
            embeddings = await generate_cv_embeddings(cv_text)
            cv_user["embeddings"] = embeddings
            print(f"✅ Embeddings generados en {time.time() - step1_start:.2f} segundos")
            #actualizar el cv en la base de datos
            await update_cv_service(cv_user.get("id"), cv_user)
        
        # Iniciar medición de búsqueda
        start_search = time.time()
        
        # Obtener la práctica específica y calcular match
        practica_con_match = await obtener_practica_por_id_y_calcular_match(
            practica_id=practice_id,
            cv_embeddings=cv_user.get("embeddings", None)
        )
        
        timing_stats['search_matching'] = time.time() - start_search
        
        if not practica_con_match:
            raise HTTPException(status_code=404, detail=f"Práctica con ID {practice_id} no encontrada")
        
        # Calcular tiempo total
        timing_stats['total_time'] = time.time() - start_total
        
        print(f"\n⏱️ ESTADÍSTICAS DE TIEMPO:")
        print(f"   - Búsqueda/Matching: {timing_stats['search_matching']:.4f}s")
        print(f"   - 🎆 TIEMPO TOTAL: {timing_stats['total_time']:.4f}s")
        
        # Preparar respuesta
        response_data = {
            "practica": practica_con_match,
            "metadata": {
                "practice_id": practice_id,
                "user_id": user_id,
                "total_time": timing_stats['total_time'],
                "search_matching_time": timing_stats['search_matching']
            }
        }
        
        return response_data
            
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Error al parsear JSON")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error en match_single_practice: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@app.get("/practicas")
def get_all_practicas():
    return obtener_practicas()

@app.get("/practicas-recientes")
def get_recent_practicas():
    return obtener_practicas_recientes()

@app.post("/upload-cv")
async def upload_cv(cv_pdf_file: UploadFile = File(...), user_id: str = Form(...)):
    """
    Endpoint para subir un CV a la base de datos del usuario.
    
    Proceso:
    1. Recibe el archivo PDF como multipart/form-data
    2. Extrae el texto del PDF directamente del archivo
    3. En paralelo:
       - Genera embeddings multi-aspecto usando IA
       - Extrae y estructura los datos del CV usando IA
    4. Guarda todo en la colección "userCVs" de la base de datos del usuario
    
    Args:
        cv_pdf_file: Archivo PDF del CV subido como multipart/form-data
        user_id: ID del usuario como form field
        
    Returns:
        dict: Información del CV subido exitosamente
        {
            "success": true,
            "cv_id": "string",
            "cv_info": {
                "title": "string",
                "full_name": "string", 
                "email": "string",
                "created_at": "string",
                "template": "string"
            }
            "timing_stats": {
                "pdf_extraction": number,
                "parallel_processing": number,
                "document_preparation": number,
                "database_save": number,
                "response_preparation": number,
                "total_time": number
            }
        }
    """
    print("🚀 POST /upload-cv")
    print(f"   - Nombre del archivo: {cv_pdf_file.filename}")
    print(f"   - Tipo de contenido: {cv_pdf_file.content_type}")
    print(f"   - User ID: {user_id}")
    
    try:
        # Validar que sea un archivo PDF
        if not cv_pdf_file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")
        
        if cv_pdf_file.content_type != 'application/pdf':
            raise HTTPException(status_code=400, detail="El archivo debe ser de tipo application/pdf")
        
        # Leer el contenido del archivo
        file_content = await cv_pdf_file.read()
        print(f"   - Tamaño del archivo: {len(file_content)} bytes")
        
        # Procesar la subida del CV
        result = await upload_cv_to_database(file_content, user_id)
        
        print(f"✅ CV subido exitosamente: {result['cv_id']}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error en upload_cv: {e}")
        raise HTTPException(status_code=500, detail=f"Error al subir CV: {str(e)}")

# endpoint para crear un CV en la base de datos del usuario
@app.post("/cv")
async def create_cv(cv: dict):
    """
    Crea un CV a partir de un JSON con al menos 'userId' y 'data'.
    """
    result = await save_cv_service(cv)
    print(f"✅ CV subido exitosamente: {result['cv_id']}")
    return result

# endpoint para actualizar un CV (el servicio maneja la lógica de embeddings)
@app.put("/cv/{cv_id}")
async def update_user_cv(cv_id: str, cv: dict):
    """
    Actualiza un CV existente. 
    - El servicio detecta automáticamente si el 'data' ha cambiado y recalcula embeddings
    - Si se incluyen 'embeddings', los usa directamente
    - Si solo se actualiza 'title', 'template' u otros campos, mantiene embeddings existentes
    """
    try:
        result = await update_cv_service(cv_id, cv)
        
        # Mostrar información sobre lo que se hizo
        if result.get("embeddings_generated"):
            if result.get("data_changed"):
                print(f"🔄 CV actualizado con nuevos embeddings y PDF (data cambió): {result['cv_id']}")
            else:
                print(f"🔍 CV actualizado con nuevos embeddings (no tenía): {result['cv_id']}")
        else:
            print(f"📝 CV actualizado sin regenerar embeddings: {result['cv_id']}")
        
        # Mostrar información sobre PDF si se generó
        if result.get("pdf_generated"):
            print(f"📄 Nuevo PDF generado y subido: {result.get('file_url', 'N/A')}")
        
        return result
        
    except ValueError as e:
        print(f"❌ CV no encontrado: {cv_id}")
        raise HTTPException(status_code=404, detail=f"CV no encontrado: {str(e)}")
    except Exception as e:
        print(f"❌ Error en update_user_cv: {e}")
        raise HTTPException(status_code=500, detail=f"Error al actualizar CV: {str(e)}")

@app.get("/user-cvs/{user_id}")
async def list_user_cvs(user_id: str):
    """
    Obtiene todos los CVs de un usuario.
    """
    print(f"🚀 GET /user-cvs/{user_id}")

    try:
        cvs = await get_user_cvs_service(user_id)

        print(f"✅ CVs obtenidos: {len(cvs)} CVs encontrados")
        return {
            "success": True,
            "user_id": user_id,
            "total_cvs": len(cvs),
            "cvs": cvs,
        }

    except Exception as e:
        print(f"❌ Error en get_user_cvs: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener CVs: {str(e)}")


@app.get("/cv/{cv_id}")
async def get_cv(cv_id: str):
    """
    Obtiene un CV específico por su ID.
    """
    print(f"🚀 GET /cv/{cv_id}")

    try:
        cv = await get_cv_by_id(cv_id)
        
        # Quitar los embeddings para no enviarlos al frontend
        cv["embeddings"] = None
        
        print(f"✅ CV obtenido: {cv.get('title', 'Sin título')}")
        return cv

    except ValueError as e:
        print(f"❌ CV no encontrado: {cv_id}")
        raise HTTPException(status_code=404, detail=f"CV no encontrado: {str(e)}")
    except Exception as e:
        print(f"❌ Error en get_cv: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener CV: {str(e)}")


@app.delete("/cv/{cv_id}")
async def delete_user_cv(cv_id: str):
    """
    Elimina un CV por `cv_id`. Si el usuario tenía ese CV como seleccionado,
    se reasigna al más reciente o se limpia el campo si no hay más.
    """
    print(f"🚀 DELETE /cv/{cv_id}")
    
    try:
        if not cv_id or cv_id.strip() == "":
            raise HTTPException(status_code=400, detail="cv_id es requerido y no puede estar vacío")
        
        result = await delete_cv_service(cv_id)
        print(f"✅ CV eliminado exitosamente: {cv_id}")
        return result
        
    except ValueError as e:
        print(f"❌ Error de validación en delete_user_cv: {e}")
        raise HTTPException(status_code=404, detail=f"CV no encontrado: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error inesperado en delete_user_cv: {e}")
        import traceback
        print(f"   Stack trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error interno al eliminar CV: {str(e)}")


@app.post("/clear-all-caches")
async def clear_all_caches_endpoint():
    """
    Endpoint para limpiar todos los caches manualmente.
    Útil cuando se suben nuevas prácticas y se necesita invalidar todo el cache.
    """
    try:
        total_count = await clear_all_caches()
        return {
            "success": True,
            "message": f"Limpieza completa completada",
            "total_caches_removed": total_count
        }
    except Exception as e:
        print(f"❌ Error al limpiar todos los caches: {e}")
        raise HTTPException(status_code=500, detail=f"Error al limpiar caches: {str(e)}")


@app.post("/process-jobs-pipeline")
async def process_jobs_pipeline(config: PipelineConfig):
    """
    Endpoint para ejecutar el pipeline completo de procesamiento de ofertas laborales.
    
    Este endpoint reemplaza la ejecución manual del script process_new_jobs_postings_pipeline.py
    y permite configurar todos los parámetros del pipeline.
    
    Args:
        config: Configuración completa del pipeline incluyendo:
            - source_collection: Colección fuente de prácticas
            - target_collection: Colección destino para embeddings
            - job_level: Nivel de trabajo (practicante, analista, senior, junior)
            - overwrite_metadata: Si sobrescribir metadatos existentes
            - overwrite_embeddings: Si sobrescribir embeddings existentes
            - Rate limiting y configuración de batches
            - Configuración de cache y logging
    
    Returns:
        PipelineResult: Resultado detallado del pipeline con estadísticas de cada paso
    """
    print("🚀 POST /process-jobs-pipeline")
    print(f"   - Configuración recibida: {config.dict()}")
    
    try:
        # Crear instancia del servicio de pipeline
        pipeline_service = PipelineService()
        
        # Ejecutar el pipeline
        result = await pipeline_service.run_pipeline(config)
        
        if result.success:
            print(f"✅ Pipeline completado exitosamente en {result.total_duration:.2f}s")
            print(f"   - Prácticas migradas: {result.summary.get('total_practices_migrated', 0)}")
            print(f"   - Metadatos generados: {result.summary.get('total_metadata_generated', 0)}")
            print(f"   - Embeddings generados: {result.summary.get('total_embeddings_generated', 0)}")
            print(f"   - Caches limpiados: {result.summary.get('caches_cleared', 0)}")
        else:
            print(f"❌ Pipeline falló: {result.error_message}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error en process_jobs_pipeline: {e}")
        import traceback
        print(f"   Stack trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error interno del pipeline: {str(e)}")




