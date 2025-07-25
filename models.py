from db import db
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import openai
from dotenv import load_dotenv
import os
import requests
import fitz
from io import BytesIO
import asyncio
import json
from functools import lru_cache
import time

load_dotenv()

# Inicializar el cliente de OpenAI
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def manejar_error(error: Exception, mensaje: str = "Ocurrió un error"):
    return JSONResponse(status_code=500, content={"error": mensaje, "details": str(error)})


# ==========================================
# OPTIMIZACIÓN 4: CACHE PARA TEXTO DE PDF
# ==========================================
@lru_cache(maxsize=100)
def obtener_texto_pdf_cached(cv_url: str):
    """Cache del texto extraído del PDF para evitar descargas repetidas"""
    return obtener_texto_pdf_de_url(cv_url)


# ==========================================
# FUNCIONES BÁSICAS (SIN CAMBIOS)
# ==========================================
def obtener_practicas():
    practicas_ref = db.collection('practicas')
    practicas = practicas_ref.stream()
    practicas_data = []
    for practica in practicas:
        practica_dict = practica.to_dict()
        if 'fecha_agregado' in practica_dict:
            fecha_agregado = practica_dict['fecha_agregado']
            if isinstance(fecha_agregado, datetime):
                practica_dict['fecha_agregado'] = fecha_agregado.isoformat()
        # Agregar el id real del documento de Firestore
        practica_dict['id'] = practica.id
        practicas_data.append(practica_dict)

    return JSONResponse(content=practicas_data)


# ==========================================
# OPTIMIZACIÓN 3: QUERY FIRESTORE OPTIMIZADA
# ==========================================
def obtener_practicas_recientes():
    """Optimización: Filtrar directamente en Firestore en lugar de en memoria"""
    fecha_actual = datetime.utcnow().replace(tzinfo=None)
    fecha_limite = fecha_actual - timedelta(days=5)

    # ANTES: Traía todas las prácticas y filtraba en memoria
    # AHORA: Filtra directamente en la query de Firestore
    try:
        practicas_ref = db.collection('practicas').where('fecha_agregado', '>=', fecha_limite)
        practicas = practicas_ref.stream()
        
        practicas_recientes = []
        for practica in practicas:
            practica_dict = practica.to_dict()
            if 'fecha_agregado' in practica_dict:
                fecha_agregado = practica_dict['fecha_agregado']
                if isinstance(fecha_agregado, datetime):
                    practica_dict['fecha_agregado'] = fecha_agregado.isoformat()
            # Agregar el id real del documento de Firestore
            practica_dict['id'] = practica.id
            practicas_recientes.append(practica_dict)
        
        return practicas_recientes
    except Exception as e:
        # Fallback al método original si la query falla
        print(f"Warning: Query optimizada falló, usando método original: {e}")
        return obtener_practicas_recientes_original()


def obtener_practicas_recientes_original():
    """Método original como fallback"""
    fecha_actual = datetime.utcnow().replace(tzinfo=None)
    fecha_limite = fecha_actual - timedelta(days=5)

    practicas_ref = db.collection('practicas')
    practicas = practicas_ref.stream()

    practicas_recientes = []
    for practica in practicas:
        practica_dict = practica.to_dict()
        if 'fecha_agregado' in practica_dict:
            fecha_agregado = practica_dict['fecha_agregado']
            if isinstance(fecha_agregado, datetime):
                fecha_agregado = fecha_agregado.replace(tzinfo=None)
                if fecha_agregado >= fecha_limite:
                    practica_dict['fecha_agregado'] = fecha_agregado.isoformat()
                    practicas_recientes.append(practica_dict)

    return practicas_recientes


# ==========================================
# OPTIMIZACIÓN 6: MODELO MÁS RÁPIDO
# ==========================================
def obtener_respuesta_chatgpt(prompt: str, model: str = "gpt-3.5-turbo"):
    """Optimización: Usar el modelo más rápido por defecto"""
    try:
        # Usar el modelo de ChatGPT correcto para 'gpt-3.5-turbo'
        if model == "gpt-3.5-turbo":
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500  # Aumentado para respuestas más complejas
            )
            respuesta = response.choices[0].message.content.strip()
        else:
            # Mantener compatibilidad con el modelo de completaciones
            response = client.completions.create(
                model=model,
                prompt=prompt,
                temperature=0.7,
                max_tokens=500
            )
            respuesta = response.choices[0].text.strip()
        
        return respuesta
    except Exception as e:
        return f"Error al obtener respuesta de ChatGPT: {e}"


def obtener_texto_pdf_de_url(cv_url: str):
    """Función original para extraer texto de PDF"""
    try:
        response = requests.get(cv_url)
        if response.status_code != 200:
            return "Error al descargar el archivo."

        pdf_file = BytesIO(response.content)
        doc = fitz.open(stream=pdf_file)

        texto = ""
        for page in doc:
            texto += page.get_text()

        return texto.strip()
    except Exception as e:
        return f"Error al leer el PDF: {str(e)}"


# ==========================================
# OPTIMIZACIÓN 1: PROMPT UNIFICADO DE CHATGPT
# ==========================================
# ==========================================
# FUNCION CON NUEVO CRITERIO DE SIMILITUD
# ==========================================
async def procesar_practica_con_prompt_unificado(cv_texto: str, practica: dict, puesto: str):
    """
    Optimización: Evaluar la compatibilidad con criterios más detallados.
    Los criterios ahora están más alineados con la descripción de requisitos.
    """
    descripcion = practica['descripcion']
    title = practica['title']
    
    # Prompt unificado con los nuevos criterios de evaluación
    prompt_unificado = f"""Analiza la compatibilidad entre este CV y esta práctica laboral según los siguientes criterios:

1. Requisitos técnicos (10%): Evalúa si el CV cumple con lo mínimo que pide la empresa. Se consideran cosas como idiomas requeridos, herramientas técnicas y nivel de estudios.
2. Similitud con el puesto (40%): Evalúa qué tan alineado está el perfil con el puesto solicitado. Mide si el estudiante tiene experiencia o formación relevante, o si el puesto tiene relación con su trayectoria o intereses.
3. Afinidad con el sector o tipo de empresa (15%): Evalúa si el estudiante tiene vínculo con el sector de la empresa.
4. Similitud semántica general (25%): Compara todo el contenido del CV con la descripción de la vacante utilizando NLP o embeddings.
5. Juicio del sistema (10%): Un puntaje de ajuste basado en los criterios anteriores y evalúa si el perfil tiene sentido para esta práctica.

IMPORTANTE: Responde ÚNICAMENTE con un JSON válido con esta estructura exacta (sin texto adicional), SI O SI DEBE SER UN JSON PERFECTO ASI COMO TE DOY EL EJEMPLO, Generame como te di en el ejemplo, debe ser un json:

{{
  "requisitos_tecnicos": [número entre 0-10],
  "similitud_puesto": [número entre 0-40],
  "afinidad_sector": [número entre 0-15],
  "similitud_semantica": [número entre 0-25],
  "juicio_sistema": [número entre 0-10],
  "justificacion_requisitos": "[justificación de los requisitos técnicos]",
  "justificacion_puesto": "[justificación de la similitud con el puesto]",
  "justificacion_afinidad": "[justificación de la afinidad con el sector]",
  "justificacion_semantica": "[justificación semántica general]",
  "justificacion_juicio": "[justificación del juicio final del sistema]"
}}

DATOS PARA ANALIZAR:

CV del candidato:
{cv_texto}

Descripción de la práctica:
{descripcion}

Título de la práctica:
{title}

Puesto solicitado:
{puesto}

CRITERIOS:
- requisitos_tecnicos: Cumplimiento de requisitos básicos de la práctica.
- similitud_puesto: Relación entre el perfil y el puesto solicitado.
- afinidad_sector: Compatibilidad con el sector o tipo de empresa.
- similitud_semantica: Coincidencias semánticas entre el CV y la vacante.
- juicio_sistema: Puntaje de ajuste general.
"""

    try:
        # Una sola llamada async a ChatGPT
        respuesta_json = await asyncio.to_thread(obtener_respuesta_chatgpt, prompt_unificado)
        
        # Limpiar la respuesta en caso de que tenga texto extra no deseado
        respuesta_limpia = respuesta_json.strip()

        # Buscar el primer { y último } para extraer solo el JSON
        start_index = respuesta_limpia.find("{")
        end_index = respuesta_limpia.rfind("}")
        
        if start_index != -1 and end_index != -1 and end_index > start_index:
            respuesta_limpia = respuesta_limpia[start_index:end_index + 1]
        else:
            raise ValueError("La respuesta no contiene un JSON válido")

        # Intentamos asegurar que la respuesta sea un JSON válido
        if respuesta_limpia.startswith("{") and respuesta_limpia.endswith("}"):
            try:
                # Intentar parsear la respuesta JSON
                resultado = json.loads(respuesta_limpia)
                
                # Verificar que todos los campos estén presentes en el resultado
                campos_requeridos = [
                    'requisitos_tecnicos', 'similitud_puesto', 'afinidad_sector', 
                    'similitud_semantica', 'juicio_sistema', 'justificacion_requisitos', 
                    'justificacion_puesto', 'justificacion_afinidad', 'justificacion_semantica',
                    'justificacion_juicio'
                ]
                
                # Verificar si los campos están vacíos y dar justificación detallada
                for campo in campos_requeridos:
                    if campo not in resultado or resultado[campo] in [None, '']:
                        # Asignar un valor detallado en vez de "No disponible"
                        print(f"Campo {campo} no presente o vacío en la respuesta")
                        resultado[campo] = f"Campo '{campo}' no proporcionado por el modelo de ChatGPT."

                # Asegurar que los valores numéricos sean válidos
                resultado['requisitos_tecnicos'] = max(0, min(10, float(resultado.get('requisitos_tecnicos', 0))))
                resultado['similitud_puesto'] = max(0, min(40, float(resultado.get('similitud_puesto', 0))))
                resultado['afinidad_sector'] = max(0, min(15, float(resultado.get('afinidad_sector', 0))))
                resultado['similitud_semantica'] = max(0, min(25, float(resultado.get('similitud_semantica', 0))))
                resultado['juicio_sistema'] = max(0, min(10, float(resultado.get('juicio_sistema', 0))))

            except json.JSONDecodeError as e:
                print(f"Error parsing JSON response: {e}")
                print(f"Raw response: {respuesta_limpia}")
                # Calcular valores por defecto basados en similitud de embedding
                similitud_embedding = practica.get('similitud_embedding', 0)
                puntaje_base = int(similitud_embedding * 50)  # Convertir a escala 0-50
                
                resultado = {
                    'requisitos_tecnicos': max(3, min(8, puntaje_base // 10)),
                    'similitud_puesto': max(5, min(20, puntaje_base // 3)),
                    'afinidad_sector': max(2, min(10, puntaje_base // 15)),
                    'similitud_semantica': max(5, min(20, puntaje_base // 3)),
                    'juicio_sistema': max(3, min(8, puntaje_base // 10)),
                    'justificacion_requisitos': f"Análisis basado en similitud de embedding ({similitud_embedding:.2f}). Se requiere análisis manual para evaluación completa.",
                    'justificacion_puesto': f"Evaluación automática basada en similitud vectorial. Se recomienda revisión manual del perfil.",
                    'justificacion_afinidad': f"Análisis automático de similitud. Se sugiere evaluación manual del sector.",
                    'justificacion_semantica': f"Similitud calculada automáticamente. Se requiere análisis semántico manual.",
                    'justificacion_juicio': f"Puntaje basado en similitud de embedding. Se recomienda evaluación manual completa."
                }
            except ValueError as e:
                print(f"Error al convertir los valores: {e}")
                # Calcular valores por defecto basados en similitud de embedding
                similitud_embedding = practica.get('similitud_embedding', 0)
                puntaje_base = int(similitud_embedding * 50)
                
                resultado = {
                    'requisitos_tecnicos': max(3, min(8, puntaje_base // 10)),
                    'similitud_puesto': max(5, min(20, puntaje_base // 3)),
                    'afinidad_sector': max(2, min(10, puntaje_base // 15)),
                    'similitud_semantica': max(5, min(20, puntaje_base // 3)),
                    'juicio_sistema': max(3, min(8, puntaje_base // 10)),
                    'justificacion_requisitos': f"Análisis automático basado en similitud ({similitud_embedding:.2f}). Error en procesamiento de ChatGPT.",
                    'justificacion_puesto': f"Evaluación automática. Error en análisis detallado de ChatGPT.",
                    'justificacion_afinidad': f"Análisis automático. Error en evaluación de sector.",
                    'justificacion_semantica': f"Similitud automática. Error en análisis semántico.",
                    'justificacion_juicio': f"Puntaje automático. Error en juicio final de ChatGPT."
                }

        else:
            # Si no es un JSON válido, asignar valores basados en similitud de embedding
            similitud_embedding = practica.get('similitud_embedding', 0)
            puntaje_base = int(similitud_embedding * 50)
            
            resultado = {
                'requisitos_tecnicos': max(3, min(8, puntaje_base // 10)),
                'similitud_puesto': max(5, min(20, puntaje_base // 3)),
                'afinidad_sector': max(2, min(10, puntaje_base // 15)),
                'similitud_semantica': max(5, min(20, puntaje_base // 3)),
                'juicio_sistema': max(3, min(8, puntaje_base // 10)),
                'justificacion_requisitos': f"Análisis automático basado en similitud ({similitud_embedding:.2f}). Respuesta inválida de ChatGPT.",
                'justificacion_puesto': f"Evaluación automática. Respuesta inválida de ChatGPT.",
                'justificacion_afinidad': f"Análisis automático. Respuesta inválida de ChatGPT.",
                'justificacion_semantica': f"Similitud automática. Respuesta inválida de ChatGPT.",
                'justificacion_juicio': f"Puntaje automático. Respuesta inválida de ChatGPT."
            }

        # Agregar los resultados a la práctica
        practica_con_resultados = practica.copy()
        practica_con_resultados.update(resultado)
        
        return practica_con_resultados
        
    except Exception as e:
        print(f"Error procesando práctica {practica.get('title', 'Unknown')}: {e}")
        # Retornar un error detallado si ocurre una excepción
        return {"error": f"Error procesando práctica: {str(e)}"}

# ==========================================
# OPTIMIZACIÓN 2: PARALELIZACIÓN COMPLETA
# ==========================================
async def comparar_practicas_con_cv(cv_texto: str, practicas: list, puesto: str):
    """
    Optimización: Procesar todas las prácticas en paralelo
    Esto debería reducir el tiempo en un 50-70% adicional
    """
    print(f"🚀 Iniciando procesamiento optimizado de {len(practicas)} prácticas...")
    start_time = time.time()
    
    # ANTES: Loop secuencial - una práctica por vez
    # AHORA: Todas las prácticas en paralelo
    tasks = [
        procesar_practica_con_prompt_unificado(cv_texto, practica, puesto) 
        for practica in practicas
    ]
    
    # Ejecutar todas las tareas en paralelo
    practicas_con_similitud = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filtrar errores y mantener solo resultados válidos
    resultados_validos = []
    for i, resultado in enumerate(practicas_con_similitud):
        if isinstance(resultado, dict) and 'error' in resultado:
            print(f"Error procesando práctica {i}: {resultado['error']}")
            # Agregar mensaje de error en caso de fallo
            practica_error = practicas[i].copy()
            practica_error.update({
                'similitud_requisitos': 0,
                'similitud_puesto': 0,
                'afinidad_sector': 0,
                'similitud_semantica': 0,
                'juicio_sistema': 0,
                'justificacion_requisitos': f"Error: {resultado['error']}",
                'justificacion_puesto': f"Error: {resultado['error']}",
                'justificacion_afinidad': f"Error: {resultado['error']}",
                'justificacion_semantica': f"Error: {resultado['error']}",
                'justificacion_juicio': f"Error: {resultado['error']}",
                'similitud_total': 0  # Similitud total en caso de error
            })
            resultados_validos.append(practica_error)
        else:
            # Calcular similitud total sumando los 5 criterios
            similitud_total = sum([
                resultado.get('requisitos_tecnicos', 0),
                resultado.get('similitud_puesto', 0),
                resultado.get('afinidad_sector', 0),
                resultado.get('similitud_semantica', 0),
                resultado.get('juicio_sistema', 0)
            ])
            
            # Agregar la similitud total a la práctica
            resultado['similitud_total'] = similitud_total
            
            # Agregar el resultado procesado a la lista
            resultados_validos.append(resultado)

    # Ordenar por similitud_total (de mayor a menor)
    resultados_validos.sort(key=lambda x: x.get('similitud_total', 0), reverse=True)
    
    end_time = time.time()
    tiempo_total = end_time - start_time
    print(f"✅ Procesamiento completado en {tiempo_total:.2f} segundos")
    print(f"📊 Promedio por práctica: {tiempo_total/len(practicas):.2f} segundos")
    
    return resultados_validos

# ==========================================
# FUNCIÓN ASYNC HELPER (MANTENER COMPATIBILIDAD)
# ==========================================
async def obtener_similitud_async(prompt: str):
    """Función helper para mantener compatibilidad con código existente"""
    return await asyncio.to_thread(obtener_respuesta_chatgpt, prompt)



def embeber_practicas_guardadas():
    """
    Obtiene todas las prácticas guardadas, genera un embedding para cada una
    y lo almacena en el campo 'embedding' de la práctica en Firestore.
    """
    try:
        # Solo obtener prácticas de los últimos 5 días
        practicas_recientes = obtener_practicas_recientes()
        print(f"🔄 Iniciando embebido de {len(practicas_recientes)} prácticas recientes...")
        count = 0
        for practica_dict in practicas_recientes:
            descripcion = practica_dict.get('descripcion', '')
            title = practica_dict.get('title', '')
            company = practica_dict.get('company', '')
            practica_id = practica_dict.get('id')
            # Concatenar los campos para el embedding
            texto_embedding = f"{descripcion}\n{title}\n{company}"

            # No embeber si ya tiene el campo 'embedding' en la colección original
            if practica_dict.get('embedding') is not None:
                continue

            try:
                embedding_response = client.embeddings.create(
                    input=texto_embedding,
                    model="text-embedding-ada-002"
                )
                embedding = embedding_response.data[0].embedding
                # Guarda la práctica y su embedding en una colección separada y marca como embebida
                db.collection('practicas_embeddings').document(practica_id).set({
                    **practica_dict,
                    "embedding": embedding
                })
                # Marca la práctica original como embebida
                db.collection('practicas').document(practica_id).update({"embebida": True})
                count += 1
            except Exception as e:
                print(f"Error generando embedding para práctica {practica_id}: {e}")
        return JSONResponse(content={"mensaje": f"Embeddings generados y guardados en colección 'practicas_embeddings' para {count} prácticas recientes."})
    except Exception as e:
        return manejar_error(e, "Error al embeber las prácticas guardadas.")
