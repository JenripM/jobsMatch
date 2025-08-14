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

# Servicios
from services.job_service import (
    obtener_practicas,
    obtener_practicas_recientes,
    buscar_practicas_afines,
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

# Configuración para streaming puro (sin compresión)
STREAMING_CHUNK_SIZE = 3   # 1 práctica por chunk para máxima velocidad
STREAMING_ENABLED = True   # Flag para habilitar/deshabilitar streaming
USE_PURE_STREAMING = True  # Streaming sin compresión para latencia mínima

# Configurar logging
logging.basicConfig(level=logging.INFO)
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

        # Obtener el CV del usuario
        cv_user = await fetch_user_cv(request_data.get("user_id"))
        
        if not cv_user:
            raise HTTPException(status_code=404, detail="No se pudo obtener el CV del usuario. Verifique que el usuario existe y tiene un CV válido.")

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
            #devolver practicas solo mayores a 0%
            percentage_threshold= 0,
            #solo buscar prácticas recientes (ultimos 5 dias)
            sinceDays=5,
        )
        
        timing_stats['search_matching'] = time.time() - start_search
        
        # 4. ETAPA: Preparación de respuesta
        start_response_prep = time.time()
        
        # Calcular tiempo total hasta ahora
        timing_stats['total_processing'] = time.time() - start_total
        timing_stats['response_preparation'] = time.time() - start_response_prep
        timing_stats['total_time'] = time.time() - start_total
        
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
            limit = request_data.get("limit", 100)
            response_data = {
                "practicas": practicas_con_similitud[:limit],
                "metadata": {
                    "total_practicas_procesadas": len(practicas_con_similitud),
                    "total_practicas_devueltas": min(limit, len(practicas_con_similitud)),
                    "streaming": False,
                    "timing_stats": timing_stats
                }
            }
            
            return response_data
            
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Error al parsear JSON")
    except Exception as e:
        print(f"❌ Error en match_practices: {e}")
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


