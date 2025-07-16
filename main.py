from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from schemas import Match, PromptRequest
from models import obtener_practicas, obtener_practicas_recientes, obtener_respuesta_chatgpt, obtener_texto_pdf_cached, comparar_practicas_con_cv
import time

app = FastAPI()

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
    start_time = time.time()
    
    # OPTIMIZACIÓN 4: Usar cache para el texto del CV
    print("📄 Extrayendo texto del CV...")
    cv_texto = obtener_texto_pdf_cached(match.cv_url)

    if "Error" in cv_texto:
        return {"error": cv_texto}  # Si hubo un error en la lectura del PDF

    # OPTIMIZACIÓN 3: Obtener prácticas con query optimizada
    print("🔍 Obteniendo prácticas recientes...")
    practicas = obtener_practicas_recientes()
    print(f"📊 Se encontraron {len(practicas)} prácticas para procesar")

    # OPTIMIZACIÓN 1 y 2: Comparar con prompts unificados y procesamiento paralelo
    practicas_con_similitud = await comparar_practicas_con_cv(cv_texto, practicas, match.puesto)

    end_time = time.time()
    tiempo_total = end_time - start_time
    print(f"✅ Matching completado en {tiempo_total:.2f} segundos")
    
    return {
        "practicas": practicas_con_similitud,
        "metadata": {
            "tiempo_procesamiento_segundos": round(tiempo_total, 2),
            "total_practicas_procesadas": len(practicas_con_similitud),
            "promedio_por_practica": round(tiempo_total / len(practicas_con_similitud) if practicas_con_similitud else 0, 2)
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
