from db import db
from datetime import datetime, timedelta
import time
from scipy.spatial.distance import cosine
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from google.cloud import firestore
import requests
import fitz
from io import BytesIO




async def buscar_practicas_afines(cv_url: str = None, puesto: str = None, cv_embedding: list = None):
    """
    Función que usa búsqueda vectorial para encontrar prácticas afines
    y devuelve el mismo formato que comparar_practicas_con_cv
    
    Args:
        cv_url (str, optional): URL del CV para generar embedding
        puesto (str): Puesto deseado
        cv_embedding (list, optional): Embedding pre-calculado del CV
    
    Note:
        Se debe proporcionar cv_url O cv_embedding, no ambos
    """
    print(f"🚀 Iniciando búsqueda vectorial...")
    start_time = time.time()
    
    try:
        # Validar parámetros
        if not cv_url and not cv_embedding:
            raise ValueError("Se debe proporcionar cv_url O cv_embedding")
        
        # Si se proporcionan ambos, priorizar el embedding
        if cv_url and cv_embedding:
            print("⚠️  Se proporcionaron tanto cv_url como cv_embedding. Usando cv_embedding...")
            cv_url = None  # Ignorar la URL
        
        if cv_embedding and len(cv_embedding) != 2048:
            raise ValueError(f"El embedding proporcionado tiene {len(cv_embedding)} dimensiones. El embedding debe tener 2048 dimensiones")
        
        # 1. Obtener embedding del CV
        if cv_embedding:
            # Usar embedding proporcionado directamente
            print(f"⏱️  Paso 1: Usando embedding proporcionado directamente...")
            step1_start = time.time()
            query_embedding = cv_embedding
            step1_time = time.time() - step1_start
            print(f"✅ Paso 1 completado en {step1_time:.4f} segundos (embedding directo)")
        else:
            # Generar embedding del CV desde URL
            print(f"⏱️  Paso 1: Generando embedding del CV desde URL...")
            step1_start = time.time()
            from models import cv_to_embedding
            query_embedding = await cv_to_embedding(cv_url, desired_position=puesto)
            
            if not query_embedding:
                print("❌ No se pudo generar el embedding del CV")
                return []
            
            step1_time = time.time() - step1_start
            print(f"✅ Paso 1 completado en {step1_time:.2f} segundos (generación desde URL)")
        
        query_vector = Vector(query_embedding)
        
        # 2. Ejecutar búsqueda vectorial y procesar resultados (streaming)
        print(f"⏱️  Paso 2: Ejecutando búsqueda vectorial y procesando resultados...")
        step2_start = time.time()
        practicas_ref = db.collection("practicas_embeddings_test")
        vector_query = practicas_ref.find_nearest(
            vector_field="embedding",
            query_vector=query_vector,
            distance_measure=DistanceMeasure.COSINE,
            limit=100,
            #distance_threshold=1.0,
            distance_result_field="vector_distance",
        )
        
        resultados_validos = []
        doc_count = 0
        
        for doc in vector_query.stream():
            doc_count += 1
            data = doc.to_dict()
            data['id'] = doc.id
            
            # Obtener la distancia vectorial (menor distancia = mayor similitud)
            vector_distance = data.get('vector_distance', 1.0)
            
            # Convertir distancia a similitud (0-1 scale, donde 1 = perfecta similitud)
            # Distancia 0 = similitud 1.0, distancia 1 = similitud 0.0
            vector_similarity = max(0, 1.0 - vector_distance)
            
            # Calcular criterios individuales con variaciones más realistas
            # Cada criterio en escala 0-100 para mayor granularidad
            
            # Similitud de requisitos: más estricta, penaliza más la distancia
            similitud_requisitos = max(0, min(100, (vector_similarity ** 1.5) * 100))
            
            # Similitud de puesto: criterio principal, usa la similitud directa
            similitud_puesto = max(0, min(100, vector_similarity * 100))
            
            # Afinidad de sector: más permisiva, usa raíz cuadrada para suavizar
            afinidad_sector = max(0, min(100, (vector_similarity ** 0.7) * 100))
            
            # Similitud semántica: la más importante para embeddings
            similitud_semantica = max(0, min(100, (vector_similarity ** 0.8) * 100))
            
            # Juicio del sistema: promedio ponderado de los otros criterios
            juicio_sistema = (similitud_requisitos * 0.25 + similitud_puesto * 0.35 + 
                            afinidad_sector * 0.15 + similitud_semantica * 0.25)
            
            # Similitud total: promedio ponderado de todos los criterios (0-100)
            similitud_total = (
                similitud_requisitos * 0.20 +  # 20% peso requisitos
                similitud_puesto * 0.30 +      # 30% peso puesto (más importante)
                afinidad_sector * 0.15 +       # 15% peso sector
                similitud_semantica * 0.25 +   # 25% peso semántica
                juicio_sistema * 0.10           # 10% peso juicio sistema
            )
            
            # Crear el formato esperado por el endpoint
            campos_excluidos = {'metadata', 'embedding', 'vector_distance'}
            practica_formateada = {k: v for k, v in data.items() if k not in campos_excluidos}
            
            # Agregar campos de similitud mejorados
            practica_formateada.update({
                'similitud_requisitos': round(similitud_requisitos, 1),
                'requisitos_tecnicos': round(similitud_requisitos, 1),
                'similitud_puesto': round(similitud_puesto, 1),
                'afinidad_sector': round(afinidad_sector, 1),
                'similitud_semantica': round(similitud_semantica, 1),
                'juicio_sistema': round(juicio_sistema, 1),
                'similitud_total': round(similitud_total, 1),
                'vector_distance': round(vector_distance, 4),  # Para debugging
                'vector_similarity': round(vector_similarity, 4),  # Para debugging
                'justificacion_requisitos': f"Similitud de requisitos: {similitud_requisitos:.1f}% (distancia vectorial: {vector_distance:.4f})",
                'justificacion_puesto': f"Coincidencia con puesto '{puesto}': {similitud_puesto:.1f}%",
                'justificacion_afinidad': f"Afinidad sectorial: {afinidad_sector:.1f}% (análisis vectorial)",
                'justificacion_semantica': f"Similitud semántica: {similitud_semantica:.1f}% (embedding gemini-001)",
                'justificacion_juicio': f"Evaluación integral: {juicio_sistema:.1f}% (promedio ponderado)"
            })
            
            resultados_validos.append(practica_formateada)
        
        step2_time = time.time() - step2_start
        print(f"✅ Paso 2 completado en {step2_time:.2f} segundos - {doc_count} documentos procesados")
        
        # Verificar si necesitamos ordenar (Firestore debería devolver ordenado por distancia)
        print(f"⏱️  Verificando orden de resultados...")
        step3_start = time.time()
        
        # Verificar si ya están ordenados por vector_distance (menor distancia = mayor similitud)
        is_sorted = all(resultados_validos[i].get('vector_distance', 1) <= resultados_validos[i+1].get('vector_distance', 1) 
                       for i in range(len(resultados_validos)-1))
        
        if not is_sorted:
            print(f"⚠️  Resultados no están ordenados, aplicando ordenamiento...")
            resultados_validos.sort(key=lambda x: x.get('similitud_total', 0), reverse=True)
        else:
            print(f"✅ Resultados ya están ordenados por Firestore")
        
        step3_time = time.time() - step3_start
        
        end_time = time.time()
        tiempo_total = end_time - start_time
        print(f"🎯 RESUMEN DE TIEMPOS:")
        print(f"   - Generación de embedding: {step1_time:.2f}s")
        print(f"   - Búsqueda vectorial: {step2_time:.2f}s")
        print(f"   - Verificación de orden: {step3_time:.4f}s")
        print(f"✅ Búsqueda vectorial completada en {tiempo_total:.2f} segundos TOTAL")
        print(f"📊 {len(resultados_validos)} prácticas procesadas")
        
        return resultados_validos
        
    except Exception as e:
        print(f"❌ ERROR durante la búsqueda vectorial: {e}")
        # En caso de error, devolver lista vacía con el formato esperado
        print(f"Retornando lista vacía debido al error")
        return []
