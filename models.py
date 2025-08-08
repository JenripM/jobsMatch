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
from services.embedding_service import get_embedding_from_text
from google.cloud.firestore_v1.vector import Vector
from texttable import Texttable  

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
        return obtener_practicas()


    
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


async def cv_to_embeddings(cv_url: str, desired_position: str | None):
    """
    Genera embeddings múltiples de un CV a partir de su URL y muestra reporte de tiempos
    agrupado en tres grandes secciones.
    """
    tiempos = {}
    t_inicio_total = time.perf_counter()

    print(f"🚀 Generando embeddings múltiples para CV: {cv_url}")

    try:
        from services.user_metadata_service import extract_metadata_with_gemini

        # 1️⃣ Extracción de texto del PDF
        t0 = time.perf_counter()
        cv_texto = obtener_texto_pdf_de_url(cv_url)
        tiempos["Extracción texto PDF"] = time.perf_counter() - t0

        if "Error" in cv_texto:
            return None

        # 2️⃣ Generar metadata (incluye todo lo relacionado a la extracción y preparación de metadata)
        t0 = time.perf_counter()
        metadata = await extract_metadata_with_gemini(
            description=cv_texto,
            desired_position=desired_position
        )
        tiempos["Generar metadata"] = time.perf_counter() - t0

        if not metadata:
            return None

        print(f"🚀 Metadata extraída: {metadata}")

        # 3️⃣ Generar todos embeddings (incluye preparar aspectos + generar embeddings + construir diccionario)
        t_emb_total = time.perf_counter()

        # Preparar aspectos
        aspects = {
            'hard_skills': metadata.get('hard_skills', []),
            'soft_skills': metadata.get('soft_skills', []),
            'sector_afinnity': None,
            'general': None
        }
        job_data = {
            'related_degrees': metadata.get('related_degrees', []),
            'desired_position': desired_position or '',
            'category': metadata.get('category', [])
        }
        aspects['sector_afinnity'] = json.dumps(job_data, ensure_ascii=False)

        metadata_with_position = {
            "desired_position": desired_position or "No especificado",
            **metadata,
        }
        general_metadata_string = json.dumps(metadata_with_position, ensure_ascii=False, indent=2)
        aspects['general'] = general_metadata_string

        print(f"🚀 Generando embeddings para {len(aspects)} aspectos...\n")

        async def generate_aspect_embeddings(aspect_name, aspect_data):
            try:
                if not aspect_data:
                    aspect_text = f"Sin {aspect_name} especificado"
                else:
                    if aspect_name == 'general':
                        aspect_text = aspect_data
                    elif isinstance(aspect_data, list):
                        aspect_text = ", ".join(str(item) for item in aspect_data)
                    else:
                        aspect_text = str(aspect_data)

                preview_text = aspect_text[:100] if aspect_name != 'general' else f"JSON metadata ({len(aspect_text)} chars)"
                print(f"  - {aspect_name}: {preview_text}...")

                embedding = await get_embedding_from_text(aspect_text)

                if embedding and len(embedding) == 2048:
                    return aspect_name, list(embedding._value)
                else:
                    print(f"⚠️  Warning: Embedding inválido para {aspect_name}")
                    return aspect_name, None
            except Exception as e:
                print(f"❌ Error generando embedding para {aspect_name}: {e}")
                return aspect_name, None

        results = await asyncio.gather(*[
            generate_aspect_embeddings(name, data) for name, data in aspects.items()
        ])

        embeddings_dict = {name: emb for name, emb in results if emb is not None}

        tiempos["Generar todos embeddings"] = time.perf_counter() - t_emb_total

        # Tiempo total final
        tiempos["⏱️ Tiempo total"] = time.perf_counter() - t_inicio_total

        # === Reporte en tabla ===
        print("\n==== 📊 REPORTE DE TIEMPOS ====")
        table = Texttable()
        table.set_cols_align(["l", "r"])
        table.add_rows([["Sección", "Segundos"]] + [
            [etapa, f"{duracion:.4f}"] for etapa, duracion in tiempos.items()
        ])
        print(table.draw())

        return embeddings_dict

    except Exception as e:
        print(f"❌ Error en cv_to_embeddings: {e}")
        return None

