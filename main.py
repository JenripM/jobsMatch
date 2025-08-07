from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from schemas import Match, PromptRequest
from models import obtener_practicas, obtener_practicas_recientes, obtener_respuesta_chatgpt, cv_to_embedding, obtener_texto_pdf_de_url
from buscar_practicas_afines import buscar_practicas_afines
from pydantic import BaseModel

import time

# Request schema for the new endpoint
class CVEmbeddingRequest(BaseModel):
    cv_url: str
    desired_position: str = None

app = FastAPI()

# Configuración de compresión (debe ir ANTES de CORS)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/match-practices")
async def match_practices(match: Match):
    """
    Endpoint optimizado para matching de prácticas
    Mejoras implementadas:
    - Cache de PDF para evitar descargas repetidas
    - Prompts unificados (8 llamadas → 1 llamada por práctica)
    - Procesamiento paralelo de todas las prácticas
    - Query optimizada a Firestore
    - Modelo más rápido de OpenAI
    """
    print(f"🔄 Iniciando matching para puesto: {match.puesto}")
    practicas_con_similitud = await buscar_practicas_afines(match.cv_url, match.puesto)
    return {
        "practicas": practicas_con_similitud,
        "metadata": {

            "total_practicas_procesadas": len(practicas_con_similitud),
        }
    }


@app.get("/practicas")
def get_all_practicas():
    return obtener_practicas()

@app.get("/practicas-recientes")
def get_recent_practicas():
    return obtener_practicas_recientes()

@app.post("/chatgpt")
async def chatgpt_response(request: PromptRequest):
    respuesta = obtener_respuesta_chatgpt(request.prompt)
    return {"respuesta": respuesta}

@app.post("/cvFileUrl_to_embedding")
async def cv_file_url_to_embedding(request: CVEmbeddingRequest):
    """
    Endpoint que genera embedding de un CV.
    
    Args:
        request: CVEmbeddingRequest con cv_url y desired_position opcional
    
    Returns:
        list: Embedding como lista de números, o dict con error
    """
    embedding = await cv_to_embedding(request.cv_url, request.desired_position)
    
    if embedding is None:
        return {"error": "No se pudo generar el embedding del CV"}
    
    return embedding

