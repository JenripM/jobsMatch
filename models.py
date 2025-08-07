from db import db
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import requests
import fitz
from io import BytesIO
import asyncio
import json
from functools import lru_cache
import time
import openai
from services.embedding_service import get_embedding_from_text
from google.cloud.firestore_v1.vector import Vector

# =============================
# CONTADORES DE CONCURRENCIA
# =============================
concurrent_tasks = 0
max_concurrent_tasks = 0
concurrent_tasks_lock = asyncio.Lock()

load_dotenv()



def manejar_error(error: Exception, mensaje: str = "Ocurrió un error"):
    return JSONResponse(status_code=500, content={"error": mensaje, "details": str(error)})


def obtener_practicas():
    practicas_ref = db.collection('practicas_embeddings_test')
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
        practicas_ref = db.collection('practicas_embeddings_test').where('fecha_agregado', '>=', fecha_limite)
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


async def cv_to_embeddings(cv_url: str, desired_position: str = None):
    """
    Genera embeddings múltiples de un CV a partir de su URL.
    
    Args:
        cv_url: URL del archivo PDF del CV
        desired_position: Puesto deseado (opcional)
    
    Returns:
        dict: Diccionario con embeddings por aspecto, o None si hay error
        {
            'hard_skills': vector<2048>,
            'category': vector<2048>,
            'soft_skills': vector<2048>,
            'sector_afinnity': vector<2048>,  # related_degrees + puesto
            'general': vector<2048>  # toda la metadata (legacy)
        }
    """
    print(f"🚀 Generando embeddings múltiples para CV: {cv_url}")

    try:
        # Import lazy de Gemini solo cuando se necesite
        from services.user_metadata_service import extract_metadata_with_gemini
        import asyncio
        
        # 1. Extracción de texto del PDF
        cv_texto = obtener_texto_pdf_de_url(cv_url)
        
        if "Error" in cv_texto:
            return None
        
        # 2. Generación de metadata
        metadata = await extract_metadata_with_gemini(
            description=cv_texto,
            desired_position=desired_position
        )
        
        if not metadata:
            return None
        
        print(f"🚀 Metadata extraída: {metadata}")
        
        # 3. Definir los aspectos y sus contenidos
        aspects = {
            'hard_skills': metadata.get('hard_skills', []),
            'soft_skills': metadata.get('soft_skills', []),
            'sector_afinnity': None,  # Combinará related_degrees + puesto + category como JSON
            'general': None  # Embedding de toda la metadata (legacy)
        }
        
        # Crear aspecto 'sector_afinnity' como JSON string que incluye related_degrees, puesto y category
        job_data = {
            'related_degrees': metadata.get('related_degrees', []),
            'desired_position': desired_position or '',
            'category': metadata.get('category', [])
        }
        aspects['sector_afinnity'] = json.dumps(job_data, ensure_ascii=False)
        
        # Crear embedding 'general' con toda la metadata (formato legacy)
        metadata_with_position = {
            "desired_position": desired_position or "No especificado",
            **metadata,
        }
        general_metadata_string = json.dumps(metadata_with_position, ensure_ascii=False, indent=2)
        aspects['general'] = general_metadata_string  # Será procesado como string, no lista
        
        # 4. Generar embeddings en paralelo para cada aspecto
        print(f"🚀 Generando embeddings para {len(aspects)} aspectos...")
        
        async def generate_aspect_embeddings(aspect_name, aspect_data):
            """Genera embedding para un aspecto específico"""
            try:
                if not aspect_data:
                    # Si no hay datos, usar un texto por defecto
                    aspect_text = f"Sin {aspect_name} especificado"
                else:
                    # Manejar diferentes tipos de datos
                    if aspect_name == 'general':
                        # Para 'general', aspect_data ya es un string JSON
                        aspect_text = aspect_data
                    elif isinstance(aspect_data, list):
                        # Convertir lista a texto legible
                        aspect_text = ", ".join(str(item) for item in aspect_data)
                    else:
                        aspect_text = str(aspect_data)
                
                # Mostrar preview más corto para 'general'
                preview_text = aspect_text[:100] if aspect_name != 'general' else f"JSON metadata ({len(aspect_text)} chars)"
                print(f"  - {aspect_name}: {preview_text}...")
                
                embedding = get_embedding_from_text(aspect_text)
                
                if embedding and len(embedding) == 2048:
                    return aspect_name, embedding
                else:
                    print(f"⚠️  Warning: Embedding inválido para {aspect_name}")
                    return aspect_name, None
                    
            except Exception as e:
                print(f"❌ Error generando embedding para {aspect_name}: {e}")
                return aspect_name, None
        
        # Ejecutar generación de embeddings en paralelo
        tasks = [generate_aspect_embeddings(name, data) for name, data in aspects.items()]
        results = await asyncio.gather(*tasks)
        
        # 5. Construir diccionario de embeddings
        embeddings_dict = {}
        successful_embeddings = 0
        
        print("Tipos de embeddings")
        for aspect_name, embedding in results:
            "Printear de que tipo es el embedding"
            print(type(embedding))
            #convertir a lista
            print("Convertir a lista")
            embedding = list(embedding._value)
            print(type(embedding))
            if embedding is not None:
                embeddings_dict[aspect_name] = embedding
                successful_embeddings += 1
            else:
                print(f"⚠️  No se pudo generar embedding para {aspect_name}")
        
        if successful_embeddings == 0:
            print(f"❌ No se pudo generar ningún embedding")
            return None
        
        print(f"✅ Embeddings generados exitosamente para {successful_embeddings}/{len(aspects)} aspectos")
        print(f"🚀 Aspectos procesados: {list(embeddings_dict.keys())}")

        #mostrar por consola el json pero con los embeddings limitados a 5

        
        return embeddings_dict
        
    except Exception as e:
        print(f"❌ Error en cv_to_embeddings: {e}")
        return None



def obtener_respuesta_chatgpt(prompt: str, model: str = "gpt-3.5-turbo-16k"):
    """Optimización: Usar el modelo más rápido por defecto"""
    try:
        # Usar el modelo de ChatGPT correcto para 'gpt-3.5-turbo'
        if model == "gpt-3.5-turbo-16k":
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500  # Aumentado para respuestas más complejas
            )
            respuesta = response['choices'][0]['message']['content'].strip()
        else:
            # Mantener compatibilidad con el modelo de completaciones
            response = openai.Completion.create(
                model=model,
                prompt=prompt,
                temperature=0.7,
                max_tokens=500
            )
            respuesta = response['choices'][0]['text'].strip()
        
        return respuesta
    except Exception as e:
        return f"Error al obtener respuesta de ChatGPT: {e}"


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


