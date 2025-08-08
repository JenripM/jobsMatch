from db import db
import time
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from datetime import datetime, timedelta, timezone


async def buscar_practicas_afines(cv_url: str | None , puesto: str | None, percentage_threshold: float = 0.5 ,sinceDays: int = 5, cv_embeddings: dict | None = None):
    """
    Función que usa búsqueda vectorial multi-aspecto para encontrar prácticas afines
    
    Args:
        cv_url (str, optional): URL del CV para generar embeddings
        puesto (str): Puesto deseado
        percentage_threshold (float): Umbral de porcentaje minimo para devolver una práctica. Solo se devuelven las prácticas con porcentaje mayor o igual al umbral
        cv_embeddings (dict, optional): Diccionario de embeddings pre-calculados del CV
            {
                'hard_skills': vector<2048>,
                'soft_skills': vector<2048>,
                'sector_afinnity': vector<2048>,  # JSON: related_degrees + puesto + category
                'general': vector<2048>  # toda la metadata
            }
    
    Note:
        Se debe proporcionar cv_url O cv_embeddings, no ambos
    """
    print(f"🚀 Iniciando búsqueda vectorial...")
    start_time = time.time()
    
    try:
        # Validar parámetros
        if not cv_url and not cv_embeddings:
            raise ValueError("Se debe proporcionar cv_url O cv_embeddings")
        
        # Si se proporcionan ambos, priorizar el embedding
        if cv_url and cv_embeddings:
            print("⚠️  Se proporcionaron tanto cv_url como cv_embeddings. Usando cv_embeddings...")
            cv_url = None  # Ignorar la URL
        
        if cv_embeddings and not isinstance(cv_embeddings, dict):
            raise ValueError(f"El embedding proporcionado debe ser un diccionario con aspectos múltiples")
        
        # 1. Obtener embeddings del CV
        if cv_embeddings:
            # Usar embeddings proporcionados directamente
            print(f"⏱️  Paso 1: Usando embeddings proporcionados directamente...")
            step1_start = time.time()
            query_embeddings = cv_embeddings
            step1_time = time.time() - step1_start
            print(f"✅ Paso 1 completado en {step1_time:.4f} segundos (embeddings directos)")
        else:
            # Generar embeddings del CV desde URL
            print(f"⏱️  Paso 1: Generando embeddings del CV desde URL...")
            step1_start = time.time()
            from models import cv_to_embeddings
            query_embeddings = await cv_to_embeddings(cv_url or "", desired_position=puesto)
            
            if not query_embeddings:
                print("❌ No se pudo generar los embeddings del CV")
                return []
            
            step1_time = time.time() - step1_start
            print(f"✅ Paso 1 completado en {step1_time:.2f} segundos (generación desde URL)")
        
        print(f"📊 Aspectos de embedding disponibles: {list(query_embeddings.keys())}")
        
        # 2. Ejecutar búsqueda vectorial principal usando el embedding 'general'
        print(f"⏱️  Paso 2: Ejecutando búsqueda vectorial principal...")
        step2_start = time.time()
        practicas_ref = db.collection("practicas_embeddings_test")
    
        
        # Ejecutar búsqueda principal usando el embedding 'general'
        query_vector = Vector(query_embeddings.get('general', []))
        vector_query = practicas_ref.find_nearest(
            vector_field="embedding",  # Nota: Esto cambiará cuando actualicemos el esquema
            query_vector=query_vector,
            distance_measure=DistanceMeasure.COSINE,
            limit=500,
        
            distance_result_field="vector_distance",
        )
        
        # Almacenar resultados de la búsqueda principal
        principal_results = {}
        for doc in vector_query.stream():
            doc_data = doc.to_dict()
            doc_id = doc.id
            vector_distance = doc_data.get('vector_distance', 1.0)
            vector_similarity = max(0, 1.0 - vector_distance)
            
            principal_results[doc_id] = {
                'similarity': vector_similarity,
                'distance': vector_distance,
                'data': doc_data
            }
        
        step2_time = time.time() - step2_start
        print(f"✅ Paso 2 completado en {step2_time:.2f} segundos - Búsqueda vectorial principal ejecutada")
        
        # 3. Calcular similitudes por aspecto usando la similitud base
        print(f"⏱️  Paso 3: Calculando similitudes por aspecto...")
        step3_start = time.time()
        
        # Para cada documento, usar la similitud general como base y aplicar variaciones por aspecto
        aspect_similarities = {}
        for doc_id, doc_data in principal_results.items():
            base_similarity = doc_data['similarity']  # Similitud del embedding general
            
            aspect_similarities[doc_id] = {
                'hard_skills': base_similarity * 0.95,      # Ligeramente más estricto
                'soft_skills': base_similarity * 0.98,      # Ligeramente más permisivo
                'sector_afinnity': base_similarity * 0.92,              # Más estricto para trabajo (incluye category)
                'general': base_similarity                   # Similitud exacta del embedding general
            }
        
        step3_time = time.time() - step3_start
        print(f"✅ Paso 3 completado en {step3_time:.2f} segundos - Similitudes por aspecto calculadas")
        
        # 4. Combinar resultados y calcular similitud total
        print(f"⏱️  Paso 4: Combinando resultados y calculando similitud total...")
        step4_start = time.time()
        
        # Primera pasada: recolectar todos los puntajes sin procesar
        raw_scores = {
            'hard_skills': [],
            'soft_skills': [],
            'sector_afinnity': [],
            'general': []
        }
        practicas_sin_normalizar = []
        
        # Recolectar todos los puntajes sin normalizar
        for doc_id, doc_data in principal_results.items():
            aspects = aspect_similarities[doc_id]
            
            # Almacenar puntajes sin normalizar
            raw_scores['hard_skills'].append(aspects['hard_skills'] * 100)
            raw_scores['soft_skills'].append(aspects['soft_skills'] * 100)
            raw_scores['sector_afinnity'].append(aspects['sector_afinnity'] * 100)
            raw_scores['general'].append(aspects['general'] * 100)
            
            # Crear el formato esperado por el endpoint
            campos_excluidos = {'metadata', 'embedding', 'vector_distance'}
            practica_formateada = {k: v for k, v in doc_data['data'].items() if k not in campos_excluidos}
            
            # Guardar datos de la práctica para el procesamiento posterior
            practicas_sin_normalizar.append({
                'data': practica_formateada,
                'aspects': aspects,
                'distance': doc_data['distance'],
                'similarity': doc_data['similarity']
            })
        
        # Función de normalización mejorada
        def normalize_scores(scores):
            if not scores or len(scores) == 0:
                return scores
                
            min_original = min(scores)
            max_original = max(scores)

            print(f"Min original: {min_original}")
            print(f"Max original: {max_original}")
            
            # Si todos los valores son iguales, devolver 5% para todos
            if max_original - min_original < 1e-6:
                return [5.0] * len(scores)
            
            # Asegurar que el valor máximo se mantenga igual
            return [
                5 + (score - min_original) / (max_original - min_original) * (max_original - 5)
                for score in scores
            ]
        
        # Normalizar todos los puntajes
        normalized_scores = {}
        for aspect, scores in raw_scores.items():
            normalized_scores[aspect] = normalize_scores(scores)
        
        # Segunda pasada: calcular similitud total con puntajes normalizados
        resultados_validos = []
        for i, practica_data in enumerate(practicas_sin_normalizar):
            # Obtener puntajes normalizados para esta práctica
            sim_requisitos = normalized_scores['hard_skills'][i]
            sim_soft_skills = normalized_scores['soft_skills'][i]
            sim_sector = normalized_scores['sector_afinnity'][i]
            sim_general = normalized_scores['general'][i]
            
            # Calcular similitud total con pesos específicos usando puntajes normalizados
            similitud_total = (
                sim_requisitos * 0.30 +    # 30% habilidades técnicas
                sim_soft_skills * 0.20 +   # 20% habilidades blandas
                sim_sector * 0.40 +        # 40% afinidad laboral
                sim_general * 0.10         # 10% evaluación general
            )

            #no incluir practicas por debajo del porcentaje_minimo_aceptado
            if similitud_total < percentage_threshold * 100:
                continue
            # Si la fecha de agregado es mayor a hace 5 dias, entonces no agregarla
            # Convertir a datetime si es un objeto DatetimeWithNanoseconds o string ISO
            fecha_agregado = practica_data['data']['fecha_agregado']
            if hasattr(fecha_agregado, 'isoformat'):  # Si es un objeto datetime
                if fecha_agregado.tzinfo is None:
                    # Si no tiene timezone, asumir UTC
                    fecha_agregado = fecha_agregado.replace(tzinfo=timezone.utc)
            else:  # Si es string, convertir a datetime con timezone
                fecha_agregado = datetime.fromisoformat(fecha_agregado.replace('Z', '+00:00'))
                if fecha_agregado.tzinfo is None:
                    fecha_agregado = fecha_agregado.replace(tzinfo=timezone.utc)
                
            if fecha_agregado < (datetime.now(timezone.utc) - timedelta(days=sinceDays)):
                continue
            
            # Actualizar el diccionario con los valores normalizados
            practica = practica_data['data']
            practica.update({
                'similitud_requisitos': round(sim_requisitos, 1),
                'afinidad_sector': round(sim_sector, 1),
                'similitud_general': round(sim_general, 1),
                'similitud_semantica': round(sim_general, 1),  # Mismo que general
                'similitud_total': round(similitud_total, 1),
                'vector_distance': round(practica_data['distance'], 4),
                'vector_similarity': round(practica_data['similarity'], 4),
                'justificacion_requisitos': f"Similitud técnica: {sim_requisitos:.1f}% (hard_skills embedding)",
                'justificacion_afinidad': f"Afinidad laboral: {sim_sector:.1f}% (job embedding: estudios + puesto + categoría)",
            })
            
            
            resultados_validos.append(practica)
        
        step4_time = time.time() - step4_start
        
        print(f"✅ Paso 4 completado en {step4_time:.2f} segundos - Resultados combinados y similitud total calculada")
        
        # Ordenar por similitud total
        print(f"⏱️  Paso 5: Ordenando resultados por similitud total...")
        step5_start = time.time()
        
        # Ordenar por similitud total (mayor similitud primero)
        resultados_validos.sort(key=lambda x: x.get('similitud_total', 0), reverse=True)
        print(f"✅ Resultados ordenados por similitud total")
        
        step5_time = time.time() - step5_start
        
        end_time = time.time()
        tiempo_total = end_time - start_time
        print(f"🎯 RESUMEN DE TIEMPOS:")
        print(f"   - Generación de embeddings: {step1_time:.2f}s")
        print(f"   - Búsqueda vectorial principal: {step2_time:.2f}s")
        print(f"   - Similitudes por aspecto calculadas: {step3_time:.2f}s")
        print(f"   - Resultados combinados y similitud total calculada: {step4_time:.2f}s")
        print(f"   - Ordenamiento final: {step5_time:.4f}s")
        print(f"✅ Búsqueda multi-aspecto completada en {tiempo_total:.2f} segundos TOTAL")
        print(f"📊 {len(resultados_validos)} prácticas procesadas con {len(query_embeddings)} aspectos")
        
        return resultados_validos
        
    except Exception as e:
        print(f"❌ ERROR durante la búsqueda vectorial multi-aspecto: {e}")
        import traceback
        traceback.print_exc()
        # En caso de error, devolver lista vacía con el formato esperado
        print(f"Retornando lista vacía debido al error")
        return []