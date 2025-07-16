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
openai.api_key = os.getenv("OPENAI_API_KEY")


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
def obtener_respuesta_chatgpt(prompt: str, model: str = "gpt-3.5-turbo-instruct"):
    """Optimización: Usar modelo más rápido por defecto"""
    try:
        # Usar el modelo más rápido por defecto
        if model == "gpt-3.5-turbo-instruct":
            response = openai.Completion.create(
                model=model,
                prompt=prompt,
                temperature=0.7,
                max_tokens=500  # Aumentado para respuestas JSON más complejas
            )
            respuesta = response['choices'][0]['text'].strip()
        else:
            # Mantener compatibilidad con chat models
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            respuesta = response['choices'][0]['message']['content'].strip()
        
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
async def procesar_practica_con_prompt_unificado(cv_texto: str, practica: dict, puesto: str):
    """
    Optimización: Una sola llamada a ChatGPT en lugar de 8 llamadas separadas
    Esto debería reducir el tiempo en un 75-87%
    """
    descripcion = practica['descripcion']
    title = practica['title']
    
    # Prompt unificado que obtiene toda la información de una vez
    prompt_unificado = f"""Analiza la compatibilidad entre este CV y esta práctica laboral.

IMPORTANTE: Responde ÚNICAMENTE con un JSON válido con esta estructura exacta (sin texto adicional):

{{
  "similitud_requisitos": [número entre 0-50],
  "similitud_titulo": [número entre 0-20],
  "similitud_experiencia": [número entre 0-10],
  "similitud_macro": [número entre 0-20],
  "justificacion_requisitos": "[justificación de similitud entre CV y requisitos de la práctica]",
  "justificacion_titulo": "[justificación de similitud entre puesto y título de la práctica]", 
  "justificacion_experiencia": "[justificación de experiencia en startup o similar]",
  "justificacion_macro": "[justificación de compatibilidad general]"
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
- similitud_requisitos: Compatibilidad entre habilidades del CV y requisitos (0-50)
- similitud_titulo: Relación entre puesto solicitado y título de práctica (0-20)
- similitud_experiencia: Experiencia en startups o organizaciones similares (0-10)
- similitud_macro: Compatibilidad general del perfil (0-20)
"""

    try:
        # Una sola llamada async a ChatGPT
        respuesta_json = await asyncio.to_thread(obtener_respuesta_chatgpt, prompt_unificado)
        
        # Intentar parsear la respuesta JSON
        try:
            # Limpiar la respuesta en caso de que tenga texto extra
            respuesta_limpia = respuesta_json.strip()
            if respuesta_limpia.startswith('```json'):
                respuesta_limpia = respuesta_limpia[7:]
            if respuesta_limpia.endswith('```'):
                respuesta_limpia = respuesta_limpia[:-3]
            
            resultado = json.loads(respuesta_limpia)
            
            # Validar que tenemos todos los campos necesarios
            campos_requeridos = [
                'similitud_requisitos', 'similitud_titulo', 'similitud_experiencia', 
                'similitud_macro', 'justificacion_requisitos', 'justificacion_titulo',
                'justificacion_experiencia', 'justificacion_macro'
            ]
            
            for campo in campos_requeridos:
                if campo not in resultado:
                    resultado[campo] = 0 if 'similitud' in campo else "No disponible"
            
            # Asegurar que los valores numéricos sean válidos
            resultado['similitud_requisitos'] = max(0, min(50, float(resultado['similitud_requisitos'])))
            resultado['similitud_titulo'] = max(0, min(20, float(resultado['similitud_titulo'])))
            resultado['similitud_experiencia'] = max(0, min(10, float(resultado['similitud_experiencia'])))
            resultado['similitud_macro'] = max(0, min(20, float(resultado['similitud_macro'])))
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"Error parsing JSON response: {e}")
            print(f"Raw response: {respuesta_json}")
            # Valores por defecto en caso de error
            resultado = {
                'similitud_requisitos': 0,
                'similitud_titulo': 0, 
                'similitud_experiencia': 0,
                'similitud_macro': 0,
                'justificacion_requisitos': f"Error al procesar respuesta: {str(e)}",
                'justificacion_titulo': "Error al procesar respuesta",
                'justificacion_experiencia': "Error al procesar respuesta", 
                'justificacion_macro': "Error al procesar respuesta"
            }
        
        # Agregar los resultados a la práctica
        practica_con_resultados = practica.copy()
        practica_con_resultados.update(resultado)
        
        return practica_con_resultados
        
    except Exception as e:
        print(f"Error procesando práctica {practica.get('title', 'Unknown')}: {e}")
        # Retornar práctica con valores por defecto en caso de error
        practica_con_resultados = practica.copy()
        practica_con_resultados.update({
            'similitud_requisitos': 0,
            'similitud_titulo': 0,
            'similitud_experiencia': 0, 
            'similitud_macro': 0,
            'justificacion_requisitos': f"Error: {str(e)}",
            'justificacion_titulo': f"Error: {str(e)}",
            'justificacion_experiencia': f"Error: {str(e)}",
            'justificacion_macro': f"Error: {str(e)}"
        })
        return practica_con_resultados


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
        if isinstance(resultado, Exception):
            print(f"Error procesando práctica {i}: {resultado}")
            # Agregar práctica con valores por defecto
            practica_error = practicas[i].copy()
            practica_error.update({
                'similitud_requisitos': 0,
                'similitud_titulo': 0,
                'similitud_experiencia': 0,
                'similitud_macro': 0,
                'justificacion_requisitos': f"Error: {str(resultado)}",
                'justificacion_titulo': f"Error: {str(resultado)}",
                'justificacion_experiencia': f"Error: {str(resultado)}",
                'justificacion_macro': f"Error: {str(resultado)}"
            })
            resultados_validos.append(practica_error)
        else:
            resultados_validos.append(resultado)
    
    # Ordenar por similitud total (requisitos principalmente)
    resultados_validos.sort(key=lambda x: x['similitud_requisitos'], reverse=True)
    
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
