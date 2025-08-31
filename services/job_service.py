from fastapi.responses import JSONResponse
from db import db_jobs
from datetime import datetime, timedelta
import time
import asyncio
import json
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from datetime import datetime, timedelta, timezone
import re
from concurrent.futures import ThreadPoolExecutor

# --- Normalización determinística compartida con parámetros específicos por aspecto ---
def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))

def normalize_cosine_similarity(similarity: float, min_sim: float = 0.87, max_sim: float = 0.98) -> float:
    """Normalización lineal simple: [min_sim, max_sim] → [0, 100]
    
    Args:
        similarity: Similitud coseno (0-1)
        min_sim: Similitud mínima observada
        max_sim: Similitud máxima posible
    
    Returns:
        Porcentaje normalizado (0-100)
    """
    if similarity <= min_sim:
        return 0.2
    if similarity >= max_sim:
        return 99.0
    
    # Normalización lineal: (s - min) / (max - min) * 100
    return ((similarity - min_sim) / (max_sim - min_sim)) * 100.0

def normalize_similarity_by_aspect(aspect_name: str, similarity: float) -> float:
    """Normalización unificada con parámetros específicos por aspecto"""
    if aspect_name in ['hard_skills', 'soft_skills']:
        # Habilidades técnicas y blandas: más estrictas
        normalized = normalize_cosine_similarity(similarity, min_sim=0.8, max_sim=1)
    elif aspect_name == 'sector_affinity':
        # Sector affinity: parámetros intermedios
        normalized = normalize_cosine_similarity(similarity, min_sim=0.8, max_sim=1)
    else:
        # General: más permisiva
        normalized = normalize_cosine_similarity(similarity, min_sim=0.8, max_sim=1)
    
    # Aplicar límite mínimo de 1%
    return max(1.0, normalized)

def calculate_total_similarity(hard_skills: float, soft_skills: float, sector_affinity: float, general: float) -> float:
    """
    Función unificada para calcular la similitud total ponderada.
    Usada tanto en buscar_practicas_afines como en obtener_practica_por_id_y_calcular_match
    para garantizar consistencia.
    
    Args:
        hard_skills: Similitud normalizada de habilidades técnicas (0-100)
        soft_skills: Similitud normalizada de habilidades blandas (0-100)
        sector_affinity: Similitud normalizada de afinidad sectorial (0-100)
        general: Similitud normalizada general (0-100)
    
    Returns:
        float: Similitud total ponderada (0-100)
    """
    # Pesos unificados para ambos endpoints
    similitud_total = (
        hard_skills * 0.40 +      # 40% habilidades técnicas
        soft_skills * 0.10 +      # 10% habilidades blandas
        sector_affinity * 0.30 +  # 30% afinidad laboral
        general * 0.20            # 20% evaluación general
    )
    
    return similitud_total

def normalize_list_cosine(similarities: list[float]) -> list[float]:
    """Normaliza una lista de similitudes coseno usando la función lineal"""
    return [normalize_cosine_similarity(s) for s in similarities]

async def buscar_practicas_afines(percentage_threshold: float = 0, sinceDays: int = 5, cv_embeddings: dict = None ):
    """
    Función que usa búsqueda vectorial multi-aspecto para encontrar prácticas afines
    
    Args:
        percentage_threshold (float): Umbral de porcentaje minimo para devolver una práctica. Solo se devuelven las prácticas con porcentaje mayor o igual al umbral
        sinceDays (int): Número de días hacia atrás para filtrar prácticas
        cv_embeddings (dict, optional): Diccionario de embeddings pre-calculados del CV
            {
                'hard_skills': vector<2048>,
                'soft_skills': vector<2048>,
                'category': vector<2048>,  # sector/industry affinity
                'general': vector<2048>  # toda la metadata
            }
        cv_data (dict, optional): Datos estructurados del CV que se convertirán a JSON string para usar con extract_metadata_with_gemini
    
    Note:
        Se debe proporcionar cv_embeddings O cv_data
    """
    print(f"🚀 Iniciando búsqueda vectorial multi-aspecto...")
    start_time = time.time()
    
    try:
        if cv_embeddings is None:
            print(f"❌ No se proporcionaron embeddings del CV")
            return []
        
        
        # 1. Obtener embeddings del CV
        print(f"⏱️  Paso 1: Usando embeddings proporcionados directamente...")
        step1_start = time.time()
        query_embeddings = cv_embeddings
        step1_time = time.time() - step1_start
        print(f"✅ Paso 1 completado en {step1_time:.4f} segundos (embeddings directos)")

        
        print(f"📊 Aspectos de embedding disponibles: {list(query_embeddings.keys())}")
        
        # 2. Ejecutar búsquedas vectoriales en paralelo para cada aspecto
        print(f"⏱️  Paso 2: Ejecutando búsquedas vectoriales en paralelo...")
        step2_start = time.time()
        practicas_ref = db_jobs.collection("practicas_embeddings_test")
        
        def search_aspect_sync(aspect_name, cv_embedding):
            """Función auxiliar para buscar por un aspecto específico (síncrona)"""
            if not cv_embedding:
                print(f"⚠️  No hay embedding para {aspect_name}")
                return {}
            
            query_vector = Vector(cv_embedding)
            vector_query = practicas_ref.find_nearest(
                vector_field="embedding",
                query_vector=query_vector,
                distance_measure=DistanceMeasure.COSINE,
                limit=500,
                distance_result_field="vector_distance",
            )
            
            results = {}
            for doc in vector_query.stream():
                doc_data = doc.to_dict()
                doc_id = doc.id
                vector_distance = doc_data.get('vector_distance', 1.0)
                vector_similarity = max(0, 1.0 - vector_distance)
                
                results[doc_id] = {
                    'similarity': vector_similarity,
                    'distance': vector_distance,
                    'data': doc_data
                }
            
            print(f"✅ Búsqueda {aspect_name} completada: {len(results)} resultados")
            return results
        
        # Ejecutar todas las búsquedas en paralelo usando ThreadPoolExecutor
        print(f"🚀 Iniciando búsquedas vectoriales paralelas...")
        with ThreadPoolExecutor(max_workers=4) as executor:
            search_tasks = [
                executor.submit(search_aspect_sync, 'general', query_embeddings.get('general')),
                executor.submit(search_aspect_sync, 'category', query_embeddings.get('category')),  # sector_affinity
                executor.submit(search_aspect_sync, 'hard_skills', query_embeddings.get('hard_skills')),
                executor.submit(search_aspect_sync, 'soft_skills', query_embeddings.get('soft_skills'))
            ]
            
            # Esperar a que todas las búsquedas terminen
            search_results = [task.result() for task in search_tasks]
        
        # Organizar resultados por aspecto
        aspect_results = {
            'general': search_results[0],
            'sector_affinity': search_results[1],  # category
            'hard_skills': search_results[2],
            'soft_skills': search_results[3]
        }
        
        step2_time = time.time() - step2_start
        print(f"✅ Paso 2 completado en {step2_time:.2f} segundos - Búsquedas vectoriales paralelas ejecutadas")
        
        # 3. Combinar todos los documentos únicos encontrados
        print(f"⏱️  Paso 3: Combinando documentos únicos...")
        step3_start = time.time()
        
        all_doc_ids = set()
        for aspect_name, results in aspect_results.items():
            all_doc_ids.update(results.keys())
        
        print(f"📊 Total de documentos únicos encontrados: {len(all_doc_ids)}")
        
        step3_time = time.time() - step3_start
        print(f"✅ Paso 3 completado en {step3_time:.2f} segundos - Documentos únicos combinados")
        
        # 4. Calcular similitudes por aspecto para cada documento
        print(f"⏱️  Paso 4: Calculando similitudes por aspecto...")
        step4_start = time.time()
        
        # Primera pasada: recolectar todos los puntajes sin procesar
        raw_scores = {
            'hard_skills': [],
            'soft_skills': [],
            'sector_affinity': [],
            'general': []
        }
        practicas_sin_normalizar = []
        
        # Para cada documento único, obtener similitudes de todos los aspectos
        for doc_id in all_doc_ids:
            # Obtener similitudes de cada aspecto (0 si no existe)
            general_sim = aspect_results['general'].get(doc_id, {}).get('similarity', 0)
            sector_sim = aspect_results['sector_affinity'].get(doc_id, {}).get('similarity', 0)
            hard_skills_sim = aspect_results['hard_skills'].get(doc_id, {}).get('similarity', 0)
            soft_skills_sim = aspect_results['soft_skills'].get(doc_id, {}).get('similarity', 0)
            
            # Usar el documento del aspecto general como base (o el primero disponible)
            base_doc_data = None
            for aspect_name in ['general', 'sector_affinity', 'hard_skills', 'soft_skills']:
                if doc_id in aspect_results[aspect_name]:
                    base_doc_data = aspect_results[aspect_name][doc_id]['data']
                    break
            
            if base_doc_data is None:
                continue
            
            # Almacenar puntajes sin normalizar
            raw_scores['hard_skills'].append(hard_skills_sim * 100)
            raw_scores['soft_skills'].append(soft_skills_sim * 100)
            raw_scores['sector_affinity'].append(sector_sim * 100)
            raw_scores['general'].append(general_sim * 100)
            
            # Crear el formato esperado por el endpoint de manera robusta
            campos_excluidos = {'metadata', 'embedding', 'vector_distance'}
            practica_formateada = {k: v for k, v in base_doc_data.items() if k not in campos_excluidos}
            
            # Agregar el ID de Firestore como campo 'id'
            practica_formateada['id'] = doc_id
            
            # Si 'fecha_agregado' no está en data pero sí en el documento raíz, incluirlo
            if 'fecha_agregado' not in practica_formateada and 'fecha_agregado' in base_doc_data:
                practica_formateada['fecha_agregado'] = base_doc_data['fecha_agregado']
            
            # Guardar datos de la práctica para el procesamiento posterior
            practicas_sin_normalizar.append({
                'data': practica_formateada,
                'aspects': {
                    'hard_skills': hard_skills_sim,
                    'soft_skills': soft_skills_sim,
                    'sector_affinity': sector_sim,
                    'general': general_sim
                },
                'distance': aspect_results['general'].get(doc_id, {}).get('distance', 1.0),
                'similarity': general_sim
            })
        
        step4_time = time.time() - step4_start
        print(f"✅ Paso 4 completado en {step4_time:.2f} segundos - Similitudes por aspecto calculadas")
        
        # 5. Normalizar puntajes y calcular similitud total
        print(f"⏱️  Paso 5: Normalizando puntajes y calculando similitud total...")
        step5_start = time.time()
        
        # Normalización determinística usando función unificada por aspecto
        def normalize_scores_by_aspect(aspect_name, scores):
            # Convertir de vuelta a similitudes coseno (0-1) y normalizar usando función unificada
            similarities = [s / 100.0 for s in scores]  # Convertir de 0-100 a 0-1
            return [normalize_similarity_by_aspect(aspect_name, s) for s in similarities]
        
        # Normalizar todos los puntajes usando función unificada
        normalized_scores = {}
        for aspect, scores in raw_scores.items():
            normalized_scores[aspect] = normalize_scores_by_aspect(aspect, scores)
        
        # DEBUG: Encontrar la similitud coseno más baja para establecer umbral
        min_similarities = {}
        for aspect_name in ['hard_skills', 'soft_skills', 'sector_affinity', 'general']:
            if aspect_name in raw_scores and raw_scores[aspect_name]:
                min_sim = min(raw_scores[aspect_name]) / 100.0  # Convertir de vuelta a 0-1
                min_similarities[aspect_name] = min_sim
                print(f"🔍 {aspect_name}: similitud mínima = {min_sim:.4f}")
        
        # Encontrar el mínimo global
        if min_similarities:
            global_min = min(min_similarities.values())
            print(f"🎯 SIMILITUD COSENO MÍNIMA GLOBAL: {global_min:.4f}")
            print(f"   (Este valor debería ser el umbral para colapsar a 5%)")
        
        # Helper: parseo tolerante de fecha_agregado (ISO, Firestore y formatos en español)
        def parse_fecha_agregado(fecha_val):
            if fecha_val is None:
                return None
            # Firestore Timestamp u objeto datetime-like
            if hasattr(fecha_val, 'isoformat'):
                try:
                    dt = fecha_val
                    if getattr(dt, 'tzinfo', None) is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    return None
            # Cadenas
            if isinstance(fecha_val, str):
                s = fecha_val.strip()
                # Intento 1: ISO 8601 (con o sin 'Z')
                try:
                    iso = s.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(iso)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    pass
                # Intento 2: Formato español típico: "15 de agosto de 2025, 11:14:27 a.m. UTC-5"
                try:
                    pattern = r"^(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(\d{4}),\s+(\d{1,2}):(\d{2}):(\d{2})\s*(a\.m\.|p\.m\.)?\s*UTC([+-]\d{1,2})$"
                    m = re.match(pattern, s)
                    if not m:
                        return None
                    day = int(m.group(1))
                    month_name = m.group(2).lower()
                    year = int(m.group(3))
                    hour = int(m.group(4))
                    minute = int(m.group(5))
                    second = int(m.group(6))
                    ampm = m.group(7)
                    tz_off = int(m.group(8))
                    meses = {
                        'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
                        'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
                        'noviembre': 11, 'diciembre': 12
                    }
                    month = meses.get(month_name)
                    if month is None:
                        return None
                    if ampm:
                        ampm_lower = ampm.lower()
                        if 'p.m' in ampm_lower and hour < 12:
                            hour += 12
                        if 'a.m' in ampm_lower and hour == 12:
                            hour = 0
                    tzinfo = timezone(timedelta(hours=tz_off))
                    dt_local = datetime(year, month, day, hour, minute, second, tzinfo=tzinfo)
                    return dt_local.astimezone(timezone.utc)
                except Exception:
                    return None
            return None

        # Calcular similitud total con puntajes normalizados
        resultados_validos = []
        for i, practica_data in enumerate(practicas_sin_normalizar):
            # Obtener puntajes normalizados para esta práctica (por aspecto)
            sim_requisitos = normalized_scores['hard_skills'][i]
            sim_soft_skills = normalized_scores['soft_skills'][i]
            sim_sector = normalized_scores['sector_affinity'][i]
            sim_general = normalized_scores['general'][i]
            
            # Calcular similitud total usando función unificada
            similitud_total = calculate_total_similarity(
                hard_skills=sim_requisitos,
                soft_skills=sim_soft_skills,
                sector_affinity=sim_sector,
                general=sim_general
            )

            #no incluir practicas por debajo del porcentaje_minimo_aceptado
            if similitud_total < percentage_threshold * 100:
                continue
            # Filtro de recencia estricto: excluir prácticas sin fecha válida
            fecha_raw = practica_data.get('data', {}).get('fecha_agregado')
            fecha_dt = parse_fecha_agregado(fecha_raw)
            if fecha_dt is None:
                # Si no hay fecha o no se puede parsear, excluir la práctica
                continue
            if fecha_dt < (datetime.now(timezone.utc) - timedelta(days=sinceDays)):
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
                'justificacion_afinidad': f"Afinidad laboral: {sim_sector:.1f}% (category embedding)",
            })
            
            
            resultados_validos.append(practica)
        
        step5_time = time.time() - step5_start
        
        print(f"✅ Paso 5 completado en {step5_time:.2f} segundos - Resultados combinados y similitud total calculada")
        
        # Ordenar por similitud total
        print(f"⏱️  Paso 6: Ordenando resultados por similitud total...")
        step6_start = time.time()
        
        # Ordenar por similitud total (mayor similitud primero)
        resultados_validos.sort(key=lambda x: x.get('similitud_total', 0), reverse=True)
        print(f"✅ Resultados ordenados por similitud total")
        
        step6_time = time.time() - step6_start
        
        end_time = time.time()
        tiempo_total = end_time - start_time
        print(f"🎯 RESUMEN DE TIEMPOS:")
        print(f"   - Generación de embeddings: {step1_time:.2f}s")
        print(f"   - Búsquedas vectoriales paralelas: {step2_time:.2f}s")
        print(f"   - Combinación de documentos únicos: {step3_time:.2f}s")
        print(f"   - Similitudes por aspecto calculadas: {step4_time:.2f}s")
        print(f"   - Resultados combinados y similitud total calculada: {step5_time:.2f}s")
        print(f"   - Ordenamiento final: {step6_time:.4f}s")
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
from concurrent.futures import ThreadPoolExecutor

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

async def obtener_practica_por_id_y_calcular_match(practica_id: str, cv_embeddings: dict = None):
    """
    Obtiene una práctica específica por ID y calcula su match con el CV del usuario
    
    Args:
        practica_id (str): ID de la práctica a obtener
        cv_embeddings (dict, optional): Diccionario de embeddings pre-calculados del CV
            {
                'hard_skills': vector<2048>,
                'soft_skills': vector<2048>,
                'category': vector<2048>,  # sector/industry affinity
                'general': vector<2048>  # toda la metadata
            }
    
    Returns:
        dict: Práctica con scores de match calculados, o None si no se encuentra
    """
    print(f"🚀 Obteniendo práctica {practica_id} y calculando match...")
    start_time = time.time()
    
    try:
        if cv_embeddings is None:
            print(f"❌ No se proporcionaron embeddings del CV")
            return None
        
        # 1. Obtener la práctica específica
        print(f"⏱️  Paso 1: Obteniendo práctica por ID...")
        step1_start = time.time()
        
        practicas_ref = db_jobs.collection("practicas_embeddings_test")
        doc_ref = practicas_ref.document(practica_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            print(f"❌ Práctica {practica_id} no encontrada")
            return None
        
        practica_data = doc.to_dict()
        step1_time = time.time() - step1_start
        print(f"✅ Paso 1 completado en {step1_time:.4f} segundos - Práctica obtenida")
        
        # 2. Calcular similitudes vectoriales para cada aspecto
        print(f"⏱️  Paso 2: Calculando similitudes vectoriales...")
        step2_start = time.time()
        
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
        from google.cloud.firestore_v1.vector import Vector
        
        aspect_similarities = {}
        
        # Calcular similitud para cada aspecto del CV
        for aspect_name, cv_embedding in cv_embeddings.items():
            if not cv_embedding:
                print(f"⚠️  No hay embedding para {aspect_name}")
                aspect_similarities[aspect_name] = 0.0
                continue
            
            # Obtener el embedding de la práctica para este aspecto
            practica_embedding = practica_data.get('embedding')
            if not practica_embedding:
                print(f"⚠️  La práctica no tiene embedding para {aspect_name}")
                aspect_similarities[aspect_name] = 0.0
                continue
            
            # Calcular similitud coseno
            try:
                query_vector = Vector(cv_embedding)
                target_vector = Vector(practica_embedding)
                
                # Calcular distancia coseno
                distance = 1 - (sum(a * b for a, b in zip(cv_embedding, practica_embedding)) / 
                               (sum(a * a for a in cv_embedding) ** 0.5 * 
                                sum(b * b for b in practica_embedding) ** 0.5))
                
                similarity = max(0, 1.0 - distance)
                aspect_similarities[aspect_name] = similarity
                
                print(f"✅ Similitud {aspect_name}: {similarity:.4f}")
                
            except Exception as e:
                print(f"❌ Error calculando similitud para {aspect_name}: {e}")
                aspect_similarities[aspect_name] = 0.0
        
        step2_time = time.time() - step2_start
        print(f"✅ Paso 2 completado en {step2_time:.4f} segundos - Similitudes calculadas")
        
        # 3. Normalizar puntajes y calcular similitud total
        print(f"⏱️  Paso 3: Normalizando puntajes y calculando similitud total...")
        step3_start = time.time()
        
        # Mapear nombres de aspectos para consistencia
        aspect_mapping = {
            'general': 'general',
            'category': 'sector_affinity',
            'hard_skills': 'hard_skills',
            'soft_skills': 'soft_skills'
        }
        
        # Obtener puntajes sin normalizar
        raw_scores = {}
        for cv_aspect, practica_aspect in aspect_mapping.items():
            if cv_aspect in aspect_similarities:
                raw_scores[practica_aspect] = [aspect_similarities[cv_aspect] * 100]
        
        # Normalización determinística usando función unificada por aspecto
        sim_requisitos = normalize_similarity_by_aspect('hard_skills', aspect_similarities.get('hard_skills', 0))
        sim_soft_skills = normalize_similarity_by_aspect('soft_skills', aspect_similarities.get('soft_skills', 0))
        sim_sector = normalize_similarity_by_aspect('sector_affinity', aspect_similarities.get('category', 0))  # category = sector_affinity
        sim_general = normalize_similarity_by_aspect('general', aspect_similarities.get('general', 0))
        
        # Usar función unificada para calcular similitud total
        similitud_total = calculate_total_similarity(
            hard_skills=sim_requisitos,
            soft_skills=sim_soft_skills,
            sector_affinity=sim_sector,
            general=sim_general
        )
        
        step3_time = time.time() - step3_start
        print(f"✅ Paso 3 completado en {step3_time:.4f} segundos - Similitud total: {similitud_total:.2f}%")
        
        # 4. Formatear respuesta
        print(f"⏱️  Paso 4: Formateando respuesta...")
        step4_start = time.time()
        
        # Excluir campos internos de la respuesta
        campos_excluidos = {'metadata', 'embedding', 'vector_distance'}
        practica_formateada = {k: v for k, v in practica_data.items() if k not in campos_excluidos}
        
        # Agregar el ID de Firestore como campo 'id'
        practica_formateada['id'] = practica_id
        
        # Agregar scores de match
        practica_formateada['match_scores'] = {
            'hard_skills': sim_requisitos,
            'soft_skills': sim_soft_skills,
            'sector_affinity': sim_sector,
            'general': sim_general,
            'total': similitud_total
        }
        
        # Agregar similitudes raw para debugging
        practica_formateada['raw_similarities'] = aspect_similarities
        
        step4_time = time.time() - step4_start
        total_time = time.time() - start_time
        
        print(f"✅ Paso 4 completado en {step4_time:.4f} segundos")
        print(f"🎆 TIEMPO TOTAL: {total_time:.4f} segundos")
        
        return practica_formateada
        
    except Exception as e:
        print(f"❌ Error en obtener_practica_por_id_y_calcular_match: {e}")
        import traceback
        print(f"   Stack trace: {traceback.format_exc()}")
        return None
