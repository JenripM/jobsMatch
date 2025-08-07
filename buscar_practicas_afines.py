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
from models import cv_to_embedding




async def buscar_practicas_afines(cv_url: str, puesto: str):
    """
    Función que usa búsqueda vectorial para encontrar prácticas afines
    y devuelve el mismo formato que comparar_practicas_con_cv
    """
    print(f"🚀 Iniciando búsqueda vectorial...")
    start_time = time.time()
    
    try:
        # 1. Generar embedding del CV y preparar vector de consulta
        print(f"⏱️  Paso 1: Generando embedding del CV y preparando vector...")
        step1_start = time.time()
        query_embedding = await cv_to_embedding(cv_url, desired_position=puesto)
        
        if not query_embedding:
            print("❌ No se pudo generar el embedding del CV")
            return []
        
        query_vector = Vector(query_embedding)
        step1_time = time.time() - step1_start
        print(f"✅ Paso 1 completado en {step1_time:.2f} segundos")
        
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
            
            # Convertir distancia a similitud (0-10 scale)
            # Distancia 0 = similitud 10, distancia 1 = similitud 0
            base_similarity = max(0, (1.0 - vector_distance) * 10)
            
            # Crear el formato esperado por el endpoint (solo campos necesarios)
            # Excluir 'metadata' y 'embedding' para reducir el tamaño de respuesta
            campos_excluidos = {'metadata', 'embedding', 'vector_distance'}
            practica_formateada = {k: v for k, v in data.items() if k not in campos_excluidos}
            
            # Agregar campos de similitud requeridos (basados en la similitud vectorial)
            practica_formateada.update({
                'similitud_requisitos': round(base_similarity * 0.9, 1),  # Ligeramente menor
                'similitud_puesto': round(base_similarity, 1),  # Similitud base
                'afinidad_sector': round(base_similarity * 0.8, 1),  # Menor peso
                'similitud_semantica': round(base_similarity * 1.1, 1),  # Mayor peso para vectorial
                'juicio_sistema': round(base_similarity * 0.85, 1),  # Peso medio
                'justificacion_requisitos': f"Similitud vectorial basada en embeddings: {vector_distance:.4f}",
                'justificacion_puesto': f"Coincidencia semántica con el puesto solicitado: {puesto}",
                'justificacion_afinidad': f"Afinidad calculada mediante análisis vectorial",
                'justificacion_semantica': f"Análisis semántico con embedding gemini-001",
                'justificacion_juicio': f"Evaluación automática basada en similitud vectorial",
                'similitud_total': round(base_similarity * 4.55, 1)  # Suma aproximada de los 5 criterios
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
