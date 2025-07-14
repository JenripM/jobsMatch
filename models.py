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

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")


def manejar_error(error: Exception, mensaje: str = "Ocurrió un error"):
    return JSONResponse(status_code=500, content={"error": mensaje, "details": str(error)})


async def obtener_similitud_async(prompt: str):
    return await asyncio.to_thread(obtener_respuesta_chatgpt, prompt)


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

    return practicas_recientes


def obtener_respuesta_chatgpt(prompt: str):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=150
        )
        respuesta = response['choices'][0]['message']['content'].strip()
        return respuesta
    except Exception as e:
        return f"Error al obtener respuesta de ChatGPT: {e}"


def obtener_texto_pdf_de_url(cv_url: str):
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


async def comparar_practicas_con_cv(cv_texto: str, practicas: list, puesto: str):
    practicas_con_similitud = []

    for practica in practicas:
        descripcion = practica['descripcion']
        title = practica['title']

        # Crear una lista de tareas para cada uno de los prompts
        tasks = []

        prompts = {
            "similitud": f"Compara el siguiente CV con la descripción de la práctica laboral y proporciona un porcentaje de similitud entre 0 y 50 basado en la relación entre las habilidades descritas en el CV y las requeridas en la práctica:\n\nCV:\n{cv_texto}\n\nDescripción de la práctica:\n{descripcion}\n\nPorcentaje de similitud:",
            "justificacion": f"Explica por qué el porcentaje de similitud entre el siguiente CV y la descripción de la práctica laboral es {{similitud}}%\n\nCV:\n{cv_texto}\n\nDescripción de la práctica:\n{descripcion}\n\nJustificación de la similitud:",
            "similitud_titulo": f"Compara el siguiente puesto con el título de la práctica laboral y proporciona un porcentaje de similitud entre 0 y 20 basado en la relación entre las responsabilidades y habilidades descritas en el puesto y el título de la práctica:\n\nPuesto:\n{puesto}\n\nTítulo de la práctica:\n{title}\n\nPorcentaje de similitud:",
            "justificacion_titulo": f"Explica por qué el porcentaje de similitud entre el puesto y el título de la práctica laboral es {{similitud_titulo}}%\n\nPuesto:\n{puesto}\n\nTítulo de la práctica:\n{title}\n\nJustificación de la similitud:",
            "similitud_experiencia": f"Analiza el siguiente CV y determina si menciona experiencia en una startup o en una organización similar que se adapte al puesto descrito. Proporciona un porcentaje de similitud entre 0 y 10 para indicar la relación entre la experiencia mencionada en el CV y el puesto solicitado:\n\nCV:\n{cv_texto}\n\nPuesto:\n{puesto}\n\nPorcentaje de similitud en experiencia:",
            "justificacion_experiencia": f"Explica por qué el porcentaje de similitud en experiencia entre el siguiente CV y el puesto laboral es {{similitud_experiencia}}%\n\nCV:\n{cv_texto}\n\nPuesto:\n{puesto}\n\nJustificación de la similitud en experiencia en alguna startup:",
            "similitud_macro": f"Compara de manera macro el siguiente CV con la práctica laboral en general. Proporciona un porcentaje de similitud entre 0 y 20 basado en la relación global entre el perfil del CV y los requisitos generales de la práctica:\n\nCV:\n{cv_texto}\n\nDescripción de la práctica:\n{descripcion}\n\nPorcentaje de similitud macro:",
            "justificacion_macro": f"Explica por qué el porcentaje de similitud macro entre el CV y la práctica laboral es {{similitud_macro}}%\n\nCV:\n{cv_texto}\n\nDescripción de la práctica:\n{descripcion}\n\nJustificación de la similitud macro:"
        }

        # Lanzar las tareas para los diferentes prompts
        for key, prompt in prompts.items():
            task = obtener_similitud_async(prompt)
            tasks.append(task)

        # Ahora esperamos todas las tareas de manera independiente para cada práctica
        respuestas = await asyncio.gather(*tasks)

        # Asignar las respuestas a los campos correspondientes
        try:
            similitud_requisitos = float(respuestas[0].replace("%", "").strip())  # Similarity percentage
        except ValueError:
            similitud_requisitos = 0

        try:
            justificacion_requisitos = respuestas[1].strip()
        except ValueError:
            justificacion_requisitos = "No se pudo obtener la justificación."

        try:
            similitud_titulo = float(respuestas[2].replace("%", "").strip())
        except ValueError:
            similitud_titulo = 0

        try:
            justificacion_titulo = respuestas[3].strip()
        except ValueError:
            justificacion_titulo = "No se pudo obtener la justificación."

        try:
            similitud_experiencia = float(respuestas[4].replace("%", "").strip())
        except ValueError:
            similitud_experiencia = 0

        try:
            justificacion_experiencia = respuestas[5].strip()
        except ValueError:
            justificacion_experiencia = "No se pudo obtener la justificación."

        try:
            similitud_macro = float(respuestas[6].replace("%", "").strip())
        except ValueError:
            similitud_macro = 0

        try:
            justificacion_macro = respuestas[7].strip()
        except ValueError:
            justificacion_macro = "No se pudo obtener la justificación."

        # Asignar los resultados a la práctica
        practica['similitud_requisitos'] = similitud_requisitos
        practica['justificacion_requisitos'] = justificacion_requisitos
        practica['similitud_titulo'] = similitud_titulo
        practica['justificacion_titulo'] = justificacion_titulo
        practica['similitud_experiencia'] = similitud_experiencia
        practica['justificacion_experiencia'] = justificacion_experiencia
        practica['similitud_macro'] = similitud_macro
        practica['justificacion_macro'] = justificacion_macro

        practicas_con_similitud.append(practica)

    # Ordenar las prácticas por similitud total
    practicas_con_similitud.sort(key=lambda x: x['similitud_requisitos'], reverse=True)

    return practicas_con_similitud
