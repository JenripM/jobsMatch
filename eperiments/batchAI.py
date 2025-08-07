import os
import time
import json
import io
import openai
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def build_prompt(cv_texto, practica, puesto):
    """Construye el prompt para una práctica."""
    descripcion = practica['descripcion']
    title = practica['title']
    return f"""Analiza la compatibilidad entre este CV y esta práctica laboral según los siguientes criterios:

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

def preparar_jsonl_en_memoria(cv_texto, practicas, puesto):
    """Genera el archivo .jsonl en memoria para la Batch API."""
    buffer = io.StringIO()
    custom_id_map = {}
    for idx, practica in enumerate(practicas):
        custom_id = f"practica-{idx}"
        prompt = build_prompt(cv_texto, practica, puesto)
        request = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "gpt-4.1-nano-2025-04-14",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 500
            }
        }
        buffer.write(json.dumps(request, ensure_ascii=False) + "\n")
        custom_id_map[custom_id] = practica
    buffer.seek(0)
    return buffer, custom_id_map

def subir_archivo_batch(client, buffer):
    """Sube el archivo .jsonl en memoria a OpenAI y retorna el file_id."""
    buffer.seek(0)
    file_obj = io.BytesIO(buffer.read().encode("utf-8"))
    file_obj.name = "batchinput.jsonl"
    file_response = client.files.create(file=file_obj, purpose="batch")
    return file_response.id

def crear_batch(client, file_id):
    """Crea el batch y retorna el batch_id."""
    batch = client.batches.create(
        input_file_id=file_id,
        endpoint="/v1/chat/completions",
        completion_window="24h"
    )
    return batch.id

def esperar_batch(client, batch_id, poll_interval=10, timeout=60*30):
    """Hace polling hasta que el batch esté completo o falle."""
    start = time.time()
    while True:
        batch = client.batches.retrieve(batch_id)
        status = batch.status
        if status == "completed":
            return batch, None
        if status in ("failed", "expired", "cancelled"):
            error_file_id = batch.error_file_id
            error_link = None
            print(f"\n[Batch OpenAI] Estado: {status.upper()}")
            if error_file_id:
                error_link = f"https://api.openai.com/v1/files/{error_file_id}/content"
                print(f"🔗 Descarga el archivo de error aquí (requiere API Key en el header Authorization):")
                print(error_link + "\n")
            # Retornar None y el link de error (si existe)
            return None, error_link
        if time.time() - start > timeout:
            print(f"[Batch OpenAI] Timeout: Batch {batch_id} no completó en {timeout} segundos")
            return None, None
        time.sleep(poll_interval)

def descargar_resultados(client, output_file_id):
    """Descarga el archivo de resultados en memoria y lo retorna como lista de líneas."""
    file_response = client.files.content(output_file_id)
    content = file_response.text
    return content.strip().splitlines()

def procesar_respuesta_json(respuesta):
    """Procesa y valida la respuesta JSON del modelo."""
    try:
        resultado = json.loads(respuesta)
        campos_requeridos = [
            'requisitos_tecnicos', 'similitud_puesto', 'afinidad_sector',
            'similitud_semantica', 'juicio_sistema', 'justificacion_requisitos',
            'justificacion_puesto', 'justificacion_afinidad', 'justificacion_semantica',
            'justificacion_juicio'
        ]
        for campo in campos_requeridos:
            if campo not in resultado or resultado[campo] in [None, '']:
                resultado[campo] = f"Campo '{campo}' no proporcionado por el modelo de ChatGPT."
        resultado['requisitos_tecnicos'] = max(0, min(10, float(resultado.get('requisitos_tecnicos', 0))))
        resultado['similitud_puesto'] = max(0, min(40, float(resultado.get('similitud_puesto', 0))))
        resultado['afinidad_sector'] = max(0, min(15, float(resultado.get('afinidad_sector', 0))))
        resultado['similitud_semantica'] = max(0, min(25, float(resultado.get('similitud_semantica', 0))))
        resultado['juicio_sistema'] = max(0, min(10, float(resultado.get('juicio_sistema', 0))))
        return resultado
    except Exception:
        return {
            'requisitos_tecnicos': 0,
            'similitud_puesto': 0,
            'afinidad_sector': 0,
            'similitud_semantica': 0,
            'juicio_sistema': 0,
            'justificacion_requisitos': "Error procesando la respuesta.",
            'justificacion_puesto': "Error procesando la respuesta.",
            'justificacion_afinidad': "Error procesando la respuesta.",
            'justificacion_semantica': "Error procesando la respuesta.",
            'justificacion_juicio': "Error procesando la respuesta."
        }

def comparar_practicas_con_cv(cv_texto: str, practicas: list, puesto: str):
    """
    Compara el CV con una lista de prácticas usando la Batch API de OpenAI.
    Devuelve una lista de dicts con los campos de similitud y justificación.
    """
    # 1. Preparar archivo .jsonl en memoria
    buffer, custom_id_map = preparar_jsonl_en_memoria(cv_texto, practicas, puesto)
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # 2. Subir archivo y crear batch
    file_id = subir_archivo_batch(client, buffer)
    batch_id = crear_batch(client, file_id)

    # 3. Esperar a que el batch termine
    batch, error_link = esperar_batch(client, batch_id)
    if batch is None:
        print("[Batch OpenAI] No se pudo completar el batch.")
        if error_link:
            print(f"🔗 Link de error del batch: {error_link}")
        else:
            print("No se obtuvo link de error del batch.")
        return []
    output_file_id = batch.output_file_id
    if not output_file_id:
        print("[Batch OpenAI] No se generó archivo de salida para el batch.")
        return []

    # 4. Descargar y procesar resultados
    lines = descargar_resultados(client, output_file_id)
    resultados = []
    for line in lines:
        data = json.loads(line)
        custom_id = data.get("custom_id")
        practica = custom_id_map.get(custom_id, {}).copy()
        error = data.get("error")
        if error:
            # Si hubo error en la petición individual
            resultado = {
                'requisitos_tecnicos': 0,
                'similitud_puesto': 0,
                'afinidad_sector': 0,
                'similitud_semantica': 0,
                'juicio_sistema': 0,
                'justificacion_requisitos': f"Error: {error.get('message', 'Error desconocido')}",
                'justificacion_puesto': f"Error: {error.get('message', 'Error desconocido')}",
                'justificacion_afinidad': f"Error: {error.get('message', 'Error desconocido')}",
                'justificacion_semantica': f"Error: {error.get('message', 'Error desconocido')}",
                'justificacion_juicio': f"Error: {error.get('message', 'Error desconocido')}",
            }
        else:
            # Extraer y procesar la respuesta del modelo
            respuesta = data["response"]["body"]["choices"][0]["message"]["content"].strip()
            resultado = procesar_respuesta_json(respuesta)
        # Calcular similitud_total
        resultado['similitud_total'] = sum([
            float(resultado.get('requisitos_tecnicos', 0)),
            float(resultado.get('similitud_puesto', 0)),
            float(resultado.get('afinidad_sector', 0)),
            float(resultado.get('similitud_semantica', 0)),
            float(resultado.get('juicio_sistema', 0))
        ])
        practica.update(resultado)
        resultados.append(practica)

    # Ordenar por similitud_total
    resultados.sort(key=lambda x: x.get('similitud_total', 0), reverse=True)
    return resultados