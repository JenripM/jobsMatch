from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from schemas import Match, PromptRequest
from models import obtener_practicas, obtener_practicas_recientes
from buscar_practicas_afines import buscar_practicas_afines
from pydantic import BaseModel
from google.cloud.firestore_v1.vector import Vector
import json
import time
import asyncio
from typing import AsyncGenerator
import logging
import os

# Configuración para streaming puro (sin compresión)
STREAMING_CHUNK_SIZE = 1   # 1 práctica por chunk para máxima velocidad
STREAMING_ENABLED = True   # Flag para habilitar/deshabilitar streaming
USE_PURE_STREAMING = True  # Streaming sin compresión para latencia mínima

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Request schema for the new endpoint
class CVEmbeddingRequest(BaseModel):
    cv_url: str
    desired_position: str | None

app = FastAPI()

# Configuración de CORS (SIN GZipMiddleware para streaming puro)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import gzip
import json
from datetime import datetime
from fastapi import Request, Response
from google.api_core.datetime_helpers import DatetimeWithNanoseconds





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
            logger.info(f"📦 Enviando práctica {practica_index + 1}/{total_practicas}")
            
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
    Endpoint optimizado para matching de prácticas
    Mejoras implementadas:
    - Soporte para cv_url O cv_embeddings como parámetros
    - Si se pasa cv_embeddings, se ejecuta directamente la búsqueda vectorial ( mas rapido )
    - Si se pasa cv_url, se genera el embedding y luego se procede a hacer la búsqueda vectorial ( mas lento )
    - Soporte para compresión gzip bidireccional (request y response)
    - Medición detallada de tiempos por etapa
    """
    # Iniciar medición de tiempo total
    start_total = time.time()
    timing_stats = {}
    
    try:
        # 1. ETAPA: Descompresión de request
        start_decompress = time.time()
        content_encoding = request.headers.get("content-encoding", "").lower()
        
        if content_encoding == "gzip":
            # Leer datos comprimidos
            compressed_data = await request.body()
            print(f"🗜️ Datos comprimidos recibidos: {len(compressed_data)} bytes")
            
            # Descomprimir usando gzip
            decompressed_data = gzip.decompress(compressed_data)
            raw_data = json.loads(decompressed_data.decode('utf-8'))
            print(f"📦 Datos descomprimidos: {len(decompressed_data)} bytes")
            
        else:
            # Datos sin comprimir (fallback)
            raw_data = await request.json()
            print(f"📄 Datos sin comprimir recibidos")
        
        timing_stats['request_decompression'] = time.time() - start_decompress
        
        # 2. ETAPA: Procesamiento de datos
        start_processing = time.time()
        
        print(f"🔍 DATOS RAW DEL FRONTEND:")
        print(f"   - Campos enviados: {list(raw_data.keys())}")
        
        # Crear objeto Match manualmente desde los datos descomprimidos
        match = Match(**raw_data)
        
        timing_stats['data_processing'] = time.time() - start_processing
        
        print(f"\n🔄 Iniciando matching para puesto: {match.puesto}")
        print(f"📋 Parámetros PROCESADOS por Pydantic:")
        print(f"   - cv_url: {match.cv_url}")
        print(f"   - puesto: {match.puesto}")
        print(f"   - cv_embeddings: {'✅ Presente' if match.cv_embeddings else '❌ Ausente'}")

        if match.cv_embeddings:
            print(f"   - cv_embeddings tipo: diccionario multi-aspecto")
            print(f"   - aspectos disponibles: {list(match.cv_embeddings.keys())}")
            for aspect, embedding in match.cv_embeddings.items():
                print(f"   - {aspect}: {len(embedding)} dimensiones")
        
        # 3. ETAPA: Búsqueda/Matching
        start_search = time.time()
        
        # Llamar a la función con los parámetros apropiados
        if match.cv_embeddings:
            print(f"📊 Usando embeddings multi-aspecto proporcionados directamente")
            practicas_con_similitud = await buscar_practicas_afines(
                cv_url=None,
                cv_embeddings=match.cv_embeddings, 
                puesto=match.puesto,
                #devolver practicas solo mayores a 0%
                percentage_threshold= 0,
                #solo buscar prácticas recientes (ultimos 5 dias)
                sinceDays=5,
            )
        else:
            print(f"🔗 Usando URL del CV: {match.cv_url}")
            practicas_con_similitud = await buscar_practicas_afines(
                cv_url=match.cv_url, 
                cv_embeddings=None,
                puesto=match.puesto,
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
        print(f"   - Descompresión request: {timing_stats['request_decompression']:.4f}s")
        print(f"   - Procesamiento datos: {timing_stats['data_processing']:.4f}s")
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
            response_data = {
                "practicas": practicas_con_similitud[:match.limit],
                "metadata": {
                    "total_practicas_procesadas": len(practicas_con_similitud),
                    "total_practicas_devueltas": match.limit,
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



@app.post("/chatgpt")
async def chatgpt_response(request: PromptRequest):
    respuesta = "SI ESTAS VIENDO ESTO, POR FAVOR NOTIFICANOS. ¿EN QUE REPOSITORIO ESTAS EJECUTANDO EL CÓDIGO QUE NECESITA ESTE ENDPOINT? \n\natt: Hector 07/08/2025"
    return {"respuesta": respuesta}



@app.post("/cvFileUrl_to_embedding")
async def cv_file_url_to_embedding(request: CVEmbeddingRequest):
    """
    Endpoint que genera embeddings múltiples de un CV.
    
    Args:
        request: CVEmbeddingRequest con cv_url y desired_position opcional
    
    Returns:
        dict: JSON con embeddings por aspecto o error
        {
            'embeddings': {
                'hard_skills': vector<2048>,
                'category': vector<2048>,
                'related_degrees': vector<2048>,
                'soft_skills': vector<2048>
            }
        }
    """
    print("🚀 POST /cvFileUrl_to_embedding")
    
    # Import lazy de cv_to_embeddings solo cuando se necesite
    from models import cv_to_embeddings
    embeddings_dict = await cv_to_embeddings(request.cv_url, request.desired_position)
    
    if embeddings_dict is None:
        return {"error": "No se pudo generar los embeddings del CV"}
    
    # Convertir cada embedding a Vector para la respuesta
    embeddings_response = {}
    for aspect_name, embedding in embeddings_dict.items():
        embeddings_response[aspect_name] = Vector(embedding)
    
    return {
        "embeddings": embeddings_response,
        "aspects_count": len(embeddings_response),
        "available_aspects": list(embeddings_response.keys())
    }
