import numpy as np
from embeddings import EmbeddingService
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from schemas import Match, PromptRequest
from models import embeber_practicas_guardadas, obtener_practicas, obtener_practicas_recientes, obtener_respuesta_chatgpt, obtener_texto_pdf_cached, comparar_practicas_con_cv
import time
from db import db

app = FastAPI()

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# CONTROLADOR PARA MATCHING USANDO EMBEDDINGS
# ==========================================
@app.post("/match-practices-embedding")
async def match_practices_embedding(match: Match):
    """
    Endpoint híbrido que combina:
    1. Filtrado rápido con embeddings
    2. Análisis detallado con ChatGPT de las mejores coincidencias
    """
    print(f"🔄 Iniciando matching híbrido para puesto: {match.puesto}")
    start_time = time.time()
    
    # Paso 1: Extraer texto del CV
    cv_texto = obtener_texto_pdf_cached(match.cv_url)
    if "Error" in cv_texto:
        return {"error": cv_texto}

    # Paso 2: Usar embeddings para filtrado inicial rápido
    print("🔍 Filtrado inicial con embeddings...")
    embedding_service = EmbeddingService()
    cv_embedding = embedding_service.get_embedding(cv_texto)

    # Obtener prácticas embebidas
    practicas_ref = db.collection('practicas_embeddings')
    practicas = practicas_ref.stream()
    practicas_con_embedding = []
    
    for p in practicas:
        d = p.to_dict()
        if 'embedding' in d and isinstance(d['embedding'], list):
            d['id'] = p.id
            # Calcular similitud de embedding
            d['similitud_embedding'] = EmbeddingService.cosine_similarity(cv_embedding, d['embedding'])
            practicas_con_embedding.append(d)

    # Ordenar por similitud de embedding y tomar las top 30
    practicas_con_embedding.sort(key=lambda x: x['similitud_embedding'], reverse=True)
    top_practicas = practicas_con_embedding[:30]  # Top 30 para análisis detallado
    
    print(f"📊 Top {len(top_practicas)} prácticas seleccionadas para análisis detallado")

    # Paso 3: Análisis detallado con ChatGPT solo de las mejores coincidencias
    print("🤖 Analizando con ChatGPT...")
    practicas_analizadas = await comparar_practicas_con_cv(cv_texto, top_practicas, match.puesto)
    
    # Paso 4: Combinar resultados: similitud de embedding + análisis ChatGPT
    for i, practica in enumerate(practicas_analizadas):
        # Peso: 30% embedding + 70% ChatGPT
        similitud_embedding = practica.get('similitud_embedding', 0)
        similitud_chatgpt = practica.get('similitud_total', 0)
        
        # Normalizar similitud de embedding a escala 0-100
        similitud_embedding_normalizada = similitud_embedding * 100
        
        # Combinar puntajes
        puntaje_final = (similitud_embedding_normalizada * 0.3) + (similitud_chatgpt * 0.7)
        practica['puntaje_final'] = round(puntaje_final, 2)
        
        # Agregar información del enfoque híbrido
        practica['metodo_analisis'] = 'híbrido'
        practica['peso_embedding'] = round(similitud_embedding_normalizada * 0.3, 2)
        practica['peso_chatgpt'] = round(similitud_chatgpt * 0.7, 2)
        
        # Eliminar campos innecesarios
        if 'embedding' in practica:
            del practica['embedding']

    # Ordenar por puntaje final
    practicas_analizadas.sort(key=lambda x: x['puntaje_final'], reverse=True)

    end_time = time.time()
    tiempo_total = end_time - start_time
    
    print(f"✅ Matching híbrido completado en {tiempo_total:.2f} segundos")
    
    return {
        "practicas": practicas_analizadas,
        "metadata": {
            "tiempo_procesamiento_segundos": round(tiempo_total, 2),
            "total_practicas_analizadas": len(practicas_analizadas),
            "metodo": "híbrido (embeddings + ChatGPT)",
            "filtrado_inicial": len(practicas_con_embedding),
            "analisis_detallado": len(top_practicas),
            "promedio_por_practica": round(tiempo_total / len(practicas_analizadas) if practicas_analizadas else 0, 2)
        }
    }

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

@app.post("/match-practices-hybrid-custom")
async def match_practices_hybrid_custom(match: Match, peso_embedding: float = 0.3, peso_chatgpt: float = 0.7, top_practicas: int = 30):
    """
    Endpoint híbrido personalizable que permite ajustar los pesos y número de prácticas
    """
    print(f"🔄 Iniciando matching híbrido personalizado para puesto: {match.puesto}")
    print(f"⚖️ Pesos: Embedding={peso_embedding}, ChatGPT={peso_chatgpt}")
    print(f"📊 Top prácticas a analizar: {top_practicas}")
    start_time = time.time()
    
    # Paso 1: Extraer texto del CV
    cv_texto = obtener_texto_pdf_cached(match.cv_url)
    if "Error" in cv_texto:
        return {"error": cv_texto}

    # Paso 2: Filtrado inicial con embeddings
    print("🔍 Filtrado inicial con embeddings...")
    embedding_service = EmbeddingService()
    cv_embedding = embedding_service.get_embedding(cv_texto)

    practicas_ref = db.collection('practicas_embeddings')
    practicas = practicas_ref.stream()
    practicas_con_embedding = []
    
    for p in practicas:
        d = p.to_dict()
        if 'embedding' in d and isinstance(d['embedding'], list):
            d['id'] = p.id
            d['similitud_embedding'] = EmbeddingService.cosine_similarity(cv_embedding, d['embedding'])
            practicas_con_embedding.append(d)

    # Ordenar y tomar las top prácticas
    practicas_con_embedding.sort(key=lambda x: x['similitud_embedding'], reverse=True)
    top_practicas_seleccionadas = practicas_con_embedding[:top_practicas]
    
    print(f"📊 Top {len(top_practicas_seleccionadas)} prácticas seleccionadas")

    # Paso 3: Análisis con ChatGPT
    print("🤖 Analizando con ChatGPT...")
    practicas_analizadas = await comparar_practicas_con_cv(cv_texto, top_practicas_seleccionadas, match.puesto)
    
    # Paso 4: Combinar con pesos personalizados
    for practica in practicas_analizadas:
        similitud_embedding = practica.get('similitud_embedding', 0)
        similitud_chatgpt = practica.get('similitud_total', 0)
        
        # Normalizar embedding a escala 0-100
        similitud_embedding_normalizada = similitud_embedding * 100
        
        # Combinar con pesos personalizados
        puntaje_final = (similitud_embedding_normalizada * peso_embedding) + (similitud_chatgpt * peso_chatgpt)
        practica['puntaje_final'] = round(puntaje_final, 2)
        practica['metodo_analisis'] = 'híbrido_personalizado'
        practica['peso_embedding'] = round(similitud_embedding_normalizada * peso_embedding, 2)
        practica['peso_chatgpt'] = round(similitud_chatgpt * peso_chatgpt, 2)
        
        if 'embedding' in practica:
            del practica['embedding']

    # Ordenar por puntaje final
    practicas_analizadas.sort(key=lambda x: x['puntaje_final'], reverse=True)

    end_time = time.time()
    tiempo_total = end_time - start_time
    
    return {
        "practicas": practicas_analizadas,
        "metadata": {
            "tiempo_procesamiento_segundos": round(tiempo_total, 2),
            "metodo": "híbrido_personalizado",
            "peso_embedding": peso_embedding,
            "peso_chatgpt": peso_chatgpt,
            "top_practicas_analizadas": top_practicas,
            "total_practicas_analizadas": len(practicas_analizadas),
            "promedio_por_practica": round(tiempo_total / len(practicas_analizadas) if practicas_analizadas else 0, 2)
        }
    }

@app.post("/match-practices-configurable")
async def match_practices_configurable(
    match: Match, 
    num_practicas: int = 30,
    peso_embedding: float = 0.3, 
    peso_chatgpt: float = 0.7,
    incluir_justificaciones: bool = True
):
    """
    Endpoint completamente configurable para matching de prácticas
    """
    print(f"🔄 Iniciando matching configurable para puesto: {match.puesto}")
    print(f"📊 Configuración: {num_practicas} prácticas, Embedding={peso_embedding}, ChatGPT={peso_chatgpt}")
    start_time = time.time()
    
    # Paso 1: Extraer texto del CV
    cv_texto = obtener_texto_pdf_cached(match.cv_url)
    if "Error" in cv_texto:
        return {"error": cv_texto}

    # Paso 2: Filtrado inicial con embeddings
    print("🔍 Filtrado inicial con embeddings...")
    embedding_service = EmbeddingService()
    cv_embedding = embedding_service.get_embedding(cv_texto)

    practicas_ref = db.collection('practicas_embeddings')
    practicas = practicas_ref.stream()
    practicas_con_embedding = []
    
    for p in practicas:
        d = p.to_dict()
        if 'embedding' in d and isinstance(d['embedding'], list):
            d['id'] = p.id
            d['similitud_embedding'] = EmbeddingService.cosine_similarity(cv_embedding, d['embedding'])
            practicas_con_embedding.append(d)

    # Ordenar y tomar las top prácticas
    practicas_con_embedding.sort(key=lambda x: x['similitud_embedding'], reverse=True)
    top_practicas_seleccionadas = practicas_con_embedding[:num_practicas]
    
    print(f"📊 Top {len(top_practicas_seleccionadas)} prácticas seleccionadas")

    # Paso 3: Análisis con ChatGPT
    print("🤖 Analizando con ChatGPT...")
    practicas_analizadas = await comparar_practicas_con_cv(cv_texto, top_practicas_seleccionadas, match.puesto)
    
    # Paso 4: Combinar con pesos personalizados
    for practica in practicas_analizadas:
        similitud_embedding = practica.get('similitud_embedding', 0)
        similitud_chatgpt = practica.get('similitud_total', 0)
        
        # Normalizar embedding a escala 0-100
        similitud_embedding_normalizada = similitud_embedding * 100
        
        # Combinar con pesos personalizados
        puntaje_final = (similitud_embedding_normalizada * peso_embedding) + (similitud_chatgpt * peso_chatgpt)
        practica['puntaje_final'] = round(puntaje_final, 2)
        practica['metodo_analisis'] = 'configurable'
        practica['peso_embedding'] = round(similitud_embedding_normalizada * peso_embedding, 2)
        practica['peso_chatgpt'] = round(similitud_chatgpt * peso_chatgpt, 2)
        
        # Eliminar campos innecesarios
        if 'embedding' in practica:
            del practica['embedding']
        
        # Opcional: eliminar justificaciones si no se requieren
        if not incluir_justificaciones:
            campos_a_eliminar = [
                'justificacion_requisitos', 'justificacion_puesto', 
                'justificacion_afinidad', 'justificacion_semantica', 'justificacion_juicio'
            ]
            for campo in campos_a_eliminar:
                if campo in practica:
                    del practica[campo]

    # Ordenar por puntaje final
    practicas_analizadas.sort(key=lambda x: x['puntaje_final'], reverse=True)

    end_time = time.time()
    tiempo_total = end_time - start_time
    
    return {
        "practicas": practicas_analizadas,
        "metadata": {
            "tiempo_procesamiento_segundos": round(tiempo_total, 2),
            "metodo": "configurable",
            "configuracion": {
                "num_practicas": num_practicas,
                "peso_embedding": peso_embedding,
                "peso_chatgpt": peso_chatgpt,
                "incluir_justificaciones": incluir_justificaciones
            },
            "total_practicas_analizadas": len(practicas_analizadas),
            "promedio_por_practica": round(tiempo_total / len(practicas_analizadas) if practicas_analizadas else 0, 2)
        }
    }

@app.post("/compare-methods")
async def compare_methods(match: Match):
    """
    Endpoint para comparar los tres métodos de matching
    """
    print(f"🔄 Comparando métodos para puesto: {match.puesto}")
    start_time = time.time()
    
    cv_texto = obtener_texto_pdf_cached(match.cv_url)
    if "Error" in cv_texto:
        return {"error": cv_texto}

    # Método 1: Solo embeddings
    print("🔍 Método 1: Solo embeddings...")
    embedding_service = EmbeddingService()
    cv_embedding = embedding_service.get_embedding(cv_texto)
    
    practicas_ref = db.collection('practicas_embeddings')
    practicas = practicas_ref.stream()
    practicas_embedding = []
    
    for p in practicas:
        d = p.to_dict()
        if 'embedding' in d and isinstance(d['embedding'], list):
            d['id'] = p.id
            d['similitud_embedding'] = EmbeddingService.cosine_similarity(cv_embedding, d['embedding'])
            if 'embedding' in d:
                del d['embedding']
            practicas_embedding.append(d)
    
    practicas_embedding.sort(key=lambda x: x['similitud_embedding'], reverse=True)
    practicas_embedding = practicas_embedding[:10]  # Top 10

    # Método 2: Solo ChatGPT (usando prácticas recientes)
    print("🤖 Método 2: Solo ChatGPT...")
    practicas_recientes = obtener_practicas_recientes()
    practicas_chatgpt = await comparar_practicas_con_cv(cv_texto, practicas_recientes[:10], match.puesto)

    # Método 3: Híbrido
    print("⚡ Método 3: Híbrido...")
    practicas_hibrido = await match_practices_hybrid_custom(match, 0.3, 0.7, 10)

    end_time = time.time()
    tiempo_total = end_time - start_time
    
    return {
        "comparacion": {
            "solo_embeddings": {
                "practicas": practicas_embedding[:5],
                "tiempo": "muy rápido",
                "costo": "bajo"
            },
            "solo_chatgpt": {
                "practicas": practicas_chatgpt[:5],
                "tiempo": "lento",
                "costo": "alto"
            },
            "hibrido": {
                "practicas": practicas_hibrido["practicas"][:5],
                "tiempo": "medio",
                "costo": "medio"
            }
        },
        "metadata": {
            "tiempo_total_comparacion": round(tiempo_total, 2),
            "recomendacion": "El método híbrido ofrece el mejor balance entre velocidad, costo y precisión"
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

# ==========================================
# CONTROLADOR PARA EMBEBER PRÁCTICAS GUARDADAS
# ==========================================
@app.get("/embeber-practicas-guardadas")
def embeber_practicas_guardadas2():
    return embeber_practicas_guardadas()
