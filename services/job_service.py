from fastapi.responses import JSONResponse
from db import db_jobs
from datetime import datetime, timedelta
import time
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from datetime import datetime, timedelta, timezone

async def buscar_practicas_afines(percentage_threshold: float = 0.5, sinceDays: int = 5, cv_embeddings: dict = None ):
    """
    Función que usa búsqueda vectorial multi-aspecto para encontrar prácticas afines
    
    Args:
        percentage_threshold (float): Umbral de porcentaje minimo para devolver una práctica. Solo se devuelven las prácticas con porcentaje mayor o igual al umbral
        sinceDays (int): Número de días hacia atrás para filtrar prácticas
        cv_embeddings (dict, optional): Diccionario de embeddings pre-calculados del CV
            {
                'hard_skills': vector<2048>,
                'soft_skills': vector<2048>,
                'sector_afinnity': vector<2048>,  # JSON: related_degrees
                'general': vector<2048>  # toda la metadata
            }
        cv_data (dict, optional): Datos estructurados del CV que se convertirán a JSON string para usar con extract_metadata_with_gemini
    
    Note:
        Se debe proporcionar cv_embeddings O cv_data
    """
    print(f"🚀 Iniciando búsqueda vectorial...")
    start_time = time.time()
    
    try:
        if cv_embeddings is None:
            print(f"❌ No se proporcionaron embeddings del CV")
            return []
        
        
        # 1. Obtener embeddings del CV
        # Usar embeddings proporcionados directamente
        print(f"⏱️  Paso 1: Usando embeddings proporcionados directamente...")
        step1_start = time.time()
        query_embeddings = cv_embeddings
        step1_time = time.time() - step1_start
        print(f"✅ Paso 1 completado en {step1_time:.4f} segundos (embeddings directos)")

        
        print(f"📊 Aspectos de embedding disponibles: {list(query_embeddings.keys())}")
        
        # 2. Ejecutar búsqueda vectorial principal usando el embedding 'general'
        print(f"⏱️  Paso 2: Ejecutando búsqueda vectorial principal...")
        step2_start = time.time()
        practicas_ref = db_jobs.collection("practicas_embeddings_test")
    
        
        # Ejecutar búsqueda principal usando el embedding 'general'
        query_vector = Vector(query_embeddings.get('general', []))
        vector_query = practicas_ref.find_nearest(
            vector_field="embedding",
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
                'justificacion_afinidad': f"Afinidad laboral: {sim_sector:.1f}% (job embedding: estudios + categoría)",
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


def obtener_practicas():
    practicas_ref = db_jobs.collection('practicas_embeddings_test')
    practicas = practicas_ref.stream()
    practicas_data = []
    for practica in practicas:
        practica_dict = practica.to_dict()
        if 'fecha_agregado' in practica_dict:
            fecha_agregado = practica_dict['fecha_agregado']
            if isinstance(fecha_agregado, datetime):
                practica_dict['fecha_agregado'] = fecha_agregado.isoformat()
        practica_dict['id'] = practica.id
        practicas_data.append(practica_dict)

    return JSONResponse(content=practicas_data)


def obtener_practicas_recientes():
    """Optimización: Filtrar directamente en Firestore en lugar de en memoria"""
    fecha_actual = datetime.utcnow().replace(tzinfo=None)
    fecha_limite = fecha_actual - timedelta(days=5)

    # ANTES: Traía todas las prácticas y filtraba en memoria
    # AHORA: Filtra directamente en la query de Firestore
    try:
        practicas_ref = db_jobs.collection('practicas_embeddings_test').where('fecha_agregado', '>=', fecha_limite)
        practicas = practicas_ref.stream()
        
        practicas_recientes = []
        for practica in practicas:
            practica_dict = practica.to_dict()
            if 'fecha_agregado' in practica_dict:
                fecha_agregado = practica_dict['fecha_agregado']
                if isinstance(fecha_agregado, datetime):
                    practica_dict['fecha_agregado'] = fecha_agregado.isoformat()
                    practicas_recientes.append(practica_dict)
        
        return practicas_recientes
    except Exception as e:
        # Fallback al método original si la query falla
        print(f"Warning: Query optimizada falló, usando método original: {e}")
        return obtener_practicas()


import asyncio
import json
from langchain_google_vertexai import ChatVertexAI
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from schemas.job_types import JobMetadata
from prompts.job_prompts import JOB_METADATA_PROMPT
import time

# --- Configuración Inicial ---
# Asegúrate de que 'db' sea una instancia de firestore.Client()
# Para que este script funcione, necesitas tener configuradas tus credenciales de Google Cloud.
# La forma más común para desarrollo local es:
# 1. Instalar Google Cloud CLI.
# 2. Autenticar: `gcloud auth application-default login`
# O configurar la variable de entorno GOOGLE_APPLICATION_CREDENTIALS apuntando a tu archivo JSON de clave de cuenta de servicio.

print("Inicializando el modelo de Gemini para generación de metadatos...")
try:
    # Configurar el modelo de LangChain con Gemini
    llm = ChatVertexAI(
        model="gemini-2.5-flash-lite",
        temperature=0,  # Máxima determinismo
        max_tokens=None,
        max_retries=6,
        stop=None,
    )
    print("Modelo de Gemini cargado exitosamente.")
except Exception as e:
    print(f"Error al cargar el modelo de Gemini: {e}")
    print("Asegúrate de que la API de Vertex AI esté habilitada en tu proyecto de Google Cloud y que tus credenciales sean correctas.")
    exit()

# Configurar el parser de Pydantic
parser = PydanticOutputParser(pydantic_object=JobMetadata)

# Definir el prompt template importado
prompt = PromptTemplate(
    template=JOB_METADATA_PROMPT,
    input_variables=["title", "description"],
    partial_variables={"format_instructions": parser.get_format_instructions()}
)

async def extract_metadata_with_gemini(title: str | None, description: str | None) -> dict | None:
    """
    Usa Gemini para extraer metadatos estructurados de una oferta de empleo.
    Retorna un diccionario con los metadatos o None si hay error.
    """
    if not title and not description:
        return None

    print(f"Generando metadatos para la oferta: '{(title or 'Sin título')[:50]}...'")
    
    try:
        # Crear el prompt con los datos de entrada
        _input = prompt.format_prompt(
            title=title or "No especificado",
            description=description or "No especificada"
        )
        
        # Llamar al modelo
        response = await llm.ainvoke(_input.to_string())
        
        # Log de la respuesta para debugging
        print(f"🔍 Respuesta del modelo: {response.content[:200]}...")
        
        # Intentar limpiar la respuesta si tiene caracteres extra
        cleaned_content = response.content.strip()
        
        # Si la respuesta no comienza con {, intentar encontrar el JSON
        if not cleaned_content.startswith('{'):
            # Buscar el primer { y el último }
            start_idx = cleaned_content.find('{')
            end_idx = cleaned_content.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                cleaned_content = cleaned_content[start_idx:end_idx + 1]
                print(f"🔧 Contenido limpiado: {cleaned_content[:200]}...")
        
        # Parsear la respuesta usando Pydantic
        try:
            parsed_metadata = parser.parse(cleaned_content)
            
            # Log de los metadatos parseados
            print(f"🔍 Metadatos parseados: {parsed_metadata}")
            
            # Convertir a diccionario
            result = parsed_metadata.model_dump()
            print(f"🔍 Diccionario resultante: {result}")
            
            return result
            
        except Exception as parse_error:
            print(f"⚠️ Error al parsear con Pydantic: {parse_error}")
            print("🔄 Intentando parseo manual del JSON...")
            
            # Intentar parseo manual del JSON
            try:
                import json
                # Intentar parsear como JSON puro
                json_data = json.loads(cleaned_content)
                
                # Validar que tenga la estructura esperada
                required_fields = ["category", "hard_skills", "soft_skills", "language_requirements", "related_degrees"]
                if all(field in json_data for field in required_fields):
                    print(f"✅ Parseo manual exitoso: {json_data}")
                    return json_data
                else:
                    print(f"❌ JSON no tiene la estructura esperada. Campos encontrados: {list(json_data.keys())}")
                    return None
                    
            except json.JSONDecodeError as json_error:
                print(f"❌ Error al parsear JSON manualmente: {json_error}")
                return None
        
    except Exception as e:
        print(f"Error al extraer metadatos con Gemini: {e}")
        if 'response' in locals():
            print(f"Respuesta recibida: {response.content}")
            print(f"Longitud de la respuesta: {len(response.content)}")
            print(f"Primeros 500 caracteres: {response.content[:500]}")
        else:
            print("Respuesta recibida: No response")
        return None

async def generate_metadata_for_collection(collection_name=None, overwrite_existing=False):
    """
    Función principal: procesa todas las prácticas de Firestore,
    genera metadatos usando Gemini y los guarda en Firestore.
    Maneja errores y usa rate limiting para evitar saturación.
    
    Args:
        collection_name (str): Nombre de la colección de Firestore a procesar (REQUERIDO)
        overwrite_existing (bool): Si True, sobrescribe metadatos existentes. Por defecto False.
    """
    if not collection_name:
        raise ValueError("collection_name es requerido. Especifica el nombre de la colección de Firestore a procesar.")
    
    print(f"Iniciando generación de metadatos para colección '{collection_name}' (sobrescribir: {overwrite_existing})...")
    
    practicas_ref = db_jobs.collection(collection_name)
    
    # Contadores y manejo de errores
    processed_count = 0
    error_count = 0
    skipped_count = 0
    failed_docs = []  # Stack para documentos que fallaron
    
    try:
        # Obtener todos los documentos
        docs = list(practicas_ref.stream())
        total_docs = len(docs)
        print(f"Total de documentos encontrados: {total_docs}")
        
        for i, doc in enumerate(docs, 1):
            doc_data = doc.to_dict()
            doc_id = doc.id
            
            # Verificar si ya tiene metadatos (solo saltar si no queremos sobrescribir)
            if not overwrite_existing and "metadata" in doc_data and doc_data["metadata"]:
                skipped_count += 1
                if i % 50 == 0:  # Log cada 50 documentos
                    print(f"Progreso: {i}/{total_docs} | ✅ {processed_count} | ❌ {error_count} | ⏭️ {skipped_count}")
                continue
            
            # Extraer título y descripción
            title = doc_data.get("title", doc_data.get("titulo", None))
            description = doc_data.get("description", doc_data.get("descripcion", None))
            
            if not title and not description:
                skipped_count += 1
                if i % 50 == 0:
                    print(f"Progreso: {i}/{total_docs} | ✅ {processed_count} | ❌ {error_count} | ⏭️ {skipped_count}")
                continue
            
            # Generar metadatos
            metadata = await extract_metadata_with_gemini(title, description)
            
            if metadata:
                # Actualizar el documento en Firestore
                try:
                    doc_ref = practicas_ref.document(doc_id)
                    doc_ref.update({"metadata": metadata})
                    processed_count += 1
                    
                    # Pequeña pausa para evitar rate limiting
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"Error al guardar metadatos para {doc_id}: {e}")
                    failed_docs.append({"id": doc_id, "title": title, "error": str(e)})
                    error_count += 1
            else:
                failed_docs.append({"id": doc_id, "title": title, "error": "No se pudieron generar metadatos"})
                error_count += 1
            
            # Rate limiting - pausa cada 10 documentos procesados
            if (processed_count + error_count) % 10 == 0:
                await asyncio.sleep(2)  # Pausa de 2 segundos
            
            # Log de progreso cada 50 documentos
            if i % 50 == 0:
                print(f"Progreso: {i}/{total_docs} | ✅ {processed_count} | ❌ {error_count} | ⏭️ {skipped_count}")
        
        # Resumen final
        print(f"\n🎉 Proceso completado:")
        print(f"   - Total de documentos: {total_docs}")
        print(f"   - Procesados exitosamente: {processed_count}")
        print(f"   - Errores: {error_count}")
        print(f"   - Saltados (ya tenían metadatos o sin contenido): {skipped_count}")
        
        # Guardar documentos fallidos para reintentos
        if failed_docs:
            print(f"\n⚠️  Documentos que fallaron ({len(failed_docs)}):")
            with open("failed_metadata_docs.json", "w", encoding="utf-8") as f:
                json.dump(failed_docs, f, indent=2, ensure_ascii=False)
            print(f"   - Lista guardada en: failed_metadata_docs.json")
            print(f"   - Puedes usar esta lista para reintentar más tarde")
        
    except Exception as e:
        print(f"Error crítico al acceder a la colección de Firestore: {e}")
        return
