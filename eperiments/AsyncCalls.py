import os
import time
import json
import io
import openai
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# ==========================================
# OPTIMIZACIÓN 6: MODELO MÁS RÁPIDO
# ==========================================
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



# ==========================================
# FUNCION CON NUEVO CRITERIO DE SIMILITUD
# ==========================================
async def procesar_practica_con_prompt_unificado(cv_texto: str, practica: dict, puesto: str):
    global concurrent_tasks, max_concurrent_tasks
    # Incrementar contador concurrente de manera segura
    async with concurrent_tasks_lock:
        concurrent_tasks += 1
        if concurrent_tasks > max_concurrent_tasks:
            max_concurrent_tasks = concurrent_tasks
        print(f"[DEBUG] Tareas concurrentes activas: {concurrent_tasks} (máximo: {max_concurrent_tasks})")
    """
    Optimización: Evaluar la compatibilidad con criterios más detallados.
    Los criterios ahora están más alineados con la descripción de requisitos.
    """
    descripcion = practica['descripcion']
    title = practica['title']
    try:
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

        # Llamada asíncrona directa a OpenAI
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo-16k",
            messages=[{"role": "user", "content": prompt_unificado}],
            temperature=0.7,
            max_tokens=500
        )
        respuesta_json = response.choices[0].message.content.strip()

        # Limpiar la respuesta en caso de que tenga texto extra no deseado
        respuesta_limpia = respuesta_json.strip()

        # Si la respuesta contiene texto no estructurado antes de un JSON, extraemos solo el JSON
        if respuesta_limpia.startswith('-'):
            start_index = respuesta_limpia.find("{")
            if start_index != -1:
                respuesta_limpia = respuesta_limpia[start_index:]
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
                resultado = {
                    'requisitos_tecnicos': 0,
                    'similitud_puesto': 0,
                    'afinidad_sector': 0,
                    'similitud_semantica': 0,
                    'juicio_sistema': 0,
                    'justificacion_requisitos': "Error en la justificación de los requisitos técnicos.",
                    'justificacion_puesto': "Error en la justificación del puesto.",
                    'justificacion_afinidad': "Error en la afinidad con el sector.",
                    'justificacion_semantica': "Error en la similitud semántica.",
                    'justificacion_juicio': "Error en el juicio del sistema."
                }
            except ValueError as e:
                print(f"Error al convertir los valores: {e}")
                resultado = {
                    'requisitos_tecnicos': 0,
                    'similitud_puesto': 0,
                    'afinidad_sector': 0,
                    'similitud_semantica': 0,
                    'juicio_sistema': 0,
                    'justificacion_requisitos': "Error al calcular los requisitos técnicos.",
                    'justificacion_puesto': "Error al calcular la similitud con el puesto.",
                    'justificacion_afinidad': "Error al calcular la afinidad con el sector.",
                    'justificacion_semantica': "Error al calcular la similitud semántica.",
                    'justificacion_juicio': "Error al calcular el juicio final."
                }

        else:
            resultado = {
                'requisitos_tecnicos': 0,
                'similitud_puesto': 0,
                'afinidad_sector': 0,
                'similitud_semantica': 0,
                'juicio_sistema': 0,
                'justificacion_requisitos': "Respuesta inválida o incompleta de ChatGPT.",
                'justificacion_puesto': "Respuesta inválida o incompleta de ChatGPT.",
                'justificacion_afinidad': "Respuesta inválida o incompleta de ChatGPT.",
                'justificacion_semantica': "Respuesta inválida o incompleta de ChatGPT.",
                'justificacion_juicio': "Respuesta inválida o incompleta de ChatGPT."
            }


        practica_con_resultados = practica.copy()
        practica_con_resultados.update(resultado)
        return practica_con_resultados

    except Exception as e:
        print(f"Error procesando práctica {practica.get('title', 'Unknown')}: {e}")
        return {"error": f"Error procesando práctica: {str(e)}"}
    finally:
        # Decrementar contador concurrente de manera segura
        async with concurrent_tasks_lock:
            concurrent_tasks -= 1
            print(f"[DEBUG] Tarea finalizada. Tareas concurrentes activas: {concurrent_tasks}")

# ==========================================
# OPTIMIZACIÓN 2: PARALELIZACIÓN COMPLETA
# ==========================================
async def comparar_practicas_con_cv(cv_texto: str, practicas: list, puesto: str, ):
    """
    Optimización: Procesar todas las prácticas en paralelo
    Esto debería reducir el tiempo en un 50-70% adicional
    """
    # Limitar el número de prácticas si se especifica practicas_limite
    practicas_limite = 5  # Puedes establecer un límite aquí si es necesario
    if practicas_limite is not None:
        practicas = practicas[:practicas_limite]
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
    
    resultados_validos = []
    for i, resultado in enumerate(practicas_con_similitud):
        if isinstance(resultado, dict):
            if 'error' in resultado:
                print(f"Error procesando práctica {i}: {resultado['error']}")
                practica_error = practicas[i].copy()
                practica_error.update({
                    'requisitos_tecnicos': 0,
                    'similitud_puesto': 0,
                    'afinidad_sector': 0,
                    'similitud_semantica': 0,
                    'juicio_sistema': 0,
                    'justificacion_requisitos': f"Error: {resultado['error']}",
                    'justificacion_puesto': f"Error: {resultado['error']}",
                    'justificacion_afinidad': f"Error: {resultado['error']}",
                    'justificacion_semantica': f"Error: {resultado['error']}",
                    'justificacion_juicio': f"Error: {resultado['error']}",
                    'similitud_total': 0.0
                })
                resultados_validos.append(practica_error)
            else:
                # Calcular similitud total sumando los 5 criterios si son numéricos
                try:
                    similitud_total = sum([
                        float(resultado.get('requisitos_tecnicos', 0)),
                        float(resultado.get('similitud_puesto', 0)),
                        float(resultado.get('afinidad_sector', 0)),
                        float(resultado.get('similitud_semantica', 0)),
                        float(resultado.get('juicio_sistema', 0))
                    ])
                except Exception as e:
                    print(f"Error calculando similitud_total en práctica {i}: {e}")
                    similitud_total = 0.0
                if isinstance(resultado, dict):
                    resultado['similitud_total'] = float(similitud_total)
                resultados_validos.append(resultado)
        else:
            # Si resultado es una excepción u otro tipo, registrar y crear error
            print(f"Error inesperado procesando práctica {i}: {resultado}")
            practica_error = practicas[i].copy()
            practica_error.update({
                'requisitos_tecnicos': 0,
                'similitud_puesto': 0,
                'afinidad_sector': 0,
                'similitud_semantica': 0,
                'juicio_sistema': 0,
                'justificacion_requisitos': f"Error inesperado: {resultado}",
                'justificacion_puesto': f"Error inesperado: {resultado}",
                'justificacion_afinidad': f"Error inesperado: {resultado}",
                'justificacion_semantica': f"Error inesperado: {resultado}",
                'justificacion_juicio': f"Error inesperado: {resultado}",
                'similitud_total': 0.0
            })
            resultados_validos.append(practica_error)

    # Ordenar por similitud_total (de mayor a menor)
    resultados_validos.sort(key=lambda x: x.get('similitud_total', 0), reverse=True)

    end_time = time.time()
    tiempo_total = end_time - start_time
    print(f"✅ Procesamiento completado en {tiempo_total:.2f} segundos")
    print(f"📊 Promedio por práctica: {tiempo_total/len(practicas):.2f} segundos")
    global max_concurrent_tasks
    print(f"🚦 Máximo de tareas concurrentes alcanzado: {max_concurrent_tasks}")
    # Reiniciar el máximo para futuras llamadas
    max_concurrent_tasks = 0
    return resultados_validos

# ==============