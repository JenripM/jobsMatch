from db import db
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta

import openai
from dotenv import load_dotenv
import os

import requests
import fitz 
from io import BytesIO


load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")


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



def obtener_practicas_recientes():
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
    
    return practicas_recientes  # Devolvemos solo la lista de prácticas recientes


def obtener_respuesta_chatgpt(prompt: str):
    try:
        # Llamada a la API de OpenAI utilizando el modelo gpt-3.5-turbo y la interfaz de messages
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Modelo que deseas utilizar
            messages=[{"role": "user", "content": prompt}],  # Formato de mensajes
            temperature=0.7,  # Controla la creatividad de la respuesta
            max_tokens=150  # Máximo de tokens en la respuesta
        )
        
        # Obtener el texto de la respuesta
        respuesta = response['choices'][0]['message']['content'].strip()
        return respuesta
    except Exception as e:
        return f"Error al obtener respuesta de ChatGPT: {e}"


def obtener_texto_pdf_de_url(cv_url: str):
    try:
        # Descargar el archivo PDF desde la URL
        response = requests.get(cv_url)
        if response.status_code != 200:
            return "Error al descargar el archivo."

        # Abrir el archivo PDF en memoria como un flujo de bytes
        pdf_file = BytesIO(response.content)
        doc = fitz.open(stream=pdf_file)  # Cambiar 'pdf_file' a un flujo de bytes válido

        # Extraer todo el texto del PDF
        texto = ""
        for page in doc:
            texto += page.get_text()

        return texto.strip()  # Devuelve el texto extraído del PDF
    except Exception as e:
        return f"Error al leer el PDF: {str(e)}"


def comparar_practicas_con_cv(cv_texto: str, practicas: list, puesto: str):
    practicas_con_similitud = []
    
    for practica in practicas:
        descripcion = practica['descripcion']
        title = practica['title']
        
        # Similitud de los requisitos
        prompt_similitud = f"Compara el siguiente CV con la descripción de la práctica laboral y proporciona un porcentaje de similitud entre 0 y 50 basado en la relación entre las habilidades descritas en el CV y las requeridas en la práctica:\n\nCV:\n{cv_texto}\n\nDescripción de la práctica:\n{descripcion}\n\nPorcentaje de similitud:"
        respuesta_similitud = obtener_respuesta_chatgpt(prompt_similitud)
        
        try:
            porcentaje_similitud = float(respuesta_similitud.replace("%", "").strip())
        except ValueError:
            porcentaje_similitud = 0 

        # Justificación de los requisitos
        prompt_justificacion = f"Explica por qué el porcentaje de similitud entre el siguiente CV y la descripción de la práctica laboral es {porcentaje_similitud}%:\n\nCV:\n{cv_texto}\n\nDescripción de la práctica:\n{descripcion}\n\nJustificación de la similitud:"
        respuesta_justificacion = obtener_respuesta_chatgpt(prompt_justificacion)
        
        # Similitud entre el título de la práctica y el puesto
        prompt_similitud_titulo = f"Compara el siguiente puesto con el título de la práctica laboral y proporciona un porcentaje de similitud entre 0 y 20 basado en la relación entre las responsabilidades y habilidades descritas en el puesto y el título de la práctica:\n\nPuesto:\n{puesto}\n\nTítulo de la práctica:\n{title}\n\nPorcentaje de similitud:"
        respuesta_similitud_titulo = obtener_respuesta_chatgpt(prompt_similitud_titulo)
        
        try:
            porcentaje_similitud_titulo = float(respuesta_similitud_titulo.replace("%", "").strip())
        except ValueError:
            porcentaje_similitud_titulo = 0  

        # Justificación entre el título y el puesto
        prompt_justificacion_titulo = f"Explica por qué el porcentaje de similitud entre el puesto y el título de la práctica laboral es {porcentaje_similitud_titulo}%:\n\nPuesto:\n{puesto}\n\nTítulo de la práctica:\n{title}\n\nJustificación de la similitud:"
        respuesta_justificacion_titulo = obtener_respuesta_chatgpt(prompt_justificacion_titulo)
        
        # Similitud de la experiencia en startups
        prompt_similitud_experiencia = f"Analiza el siguiente CV y determina si menciona experiencia en una startup o en una organización similar que se adapte al puesto descrito. Proporciona un porcentaje de similitud entre 0 y 10 para indicar la relación entre la experiencia mencionada en el CV y el puesto solicitado:\n\nCV:\n{cv_texto}\n\nPuesto:\n{puesto}\n\nPorcentaje de similitud en experiencia:"
        respuesta_similitud_experiencia = obtener_respuesta_chatgpt(prompt_similitud_experiencia)
        
        try:
            porcentaje_similitud_experiencia = float(respuesta_similitud_experiencia.replace("%", "").strip())
        except ValueError:
            porcentaje_similitud_experiencia = 0  

        # Justificación de la experiencia en startups
        prompt_justificacion_experiencia = f"Explica por qué el porcentaje de similitud en experiencia entre el siguiente CV y el puesto laboral es {porcentaje_similitud_experiencia}%:\n\nCV:\n{cv_texto}\n\nPuesto:\n{puesto}\n\nJustificación de la similitud en experiencia en alguna startup:"
        respuesta_justificacion_experiencia = obtener_respuesta_chatgpt(prompt_justificacion_experiencia)
        
        # Similitud macro
        prompt_similitud_macro = f"Compara de manera macro el siguiente CV con la práctica laboral en general (sin enfocarse en detalles específicos). Proporciona un porcentaje de similitud entre 0 y 20 basado en la relación global entre el perfil del CV y los requisitos generales de la práctica:\n\nCV:\n{cv_texto}\n\nDescripción de la práctica:\n{descripcion}\n\nPorcentaje de similitud macro:"
        respuesta_similitud_macro = obtener_respuesta_chatgpt(prompt_similitud_macro)
        
        try:
            porcentaje_similitud_macro = float(respuesta_similitud_macro.replace("%", "").strip())
        except ValueError:
            porcentaje_similitud_macro = 0  

        # Justificación de la similitud macro
        prompt_justificacion_macro = f"Explica por qué el porcentaje de similitud macro entre el CV y la práctica laboral es {porcentaje_similitud_macro}%:\n\nCV:\n{cv_texto}\n\nDescripción de la práctica:\n{descripcion}\n\nJustificación de la similitud macro:"
        respuesta_justificacion_macro = obtener_respuesta_chatgpt(prompt_justificacion_macro)
        
        # Calculando la similitud total
        similitud_total = porcentaje_similitud + porcentaje_similitud_titulo + porcentaje_similitud_experiencia + porcentaje_similitud_macro
        
        # Asignando los valores a la práctica
        practica['similitud_requisitos'] = porcentaje_similitud
        practica['justificacion_requisitos'] = respuesta_justificacion
        practica['similitud_titulo'] = porcentaje_similitud_titulo
        practica['justificacion_titulo'] = respuesta_justificacion_titulo
        practica['similitud_experiencia'] = porcentaje_similitud_experiencia
        practica['justificacion_experiencia'] = respuesta_justificacion_experiencia
        practica['similitud_macro'] = porcentaje_similitud_macro
        practica['justificacion_macro'] = respuesta_justificacion_macro
        practica['similitud_total'] = similitud_total
        
        practicas_con_similitud.append(practica)

    # Ordenar las prácticas por similitud total de mayor a menor
    practicas_con_similitud.sort(key=lambda x: x['similitud_total'], reverse=True)
    
    return practicas_con_similitud
