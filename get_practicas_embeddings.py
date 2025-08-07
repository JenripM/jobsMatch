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
from scipy.spatial.distance import cosine
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from google.cloud import firestore

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


async def convert_query_to_embedding(text: str):
    """Convierte el texto a embedding con Vertex AI."""
    model = TextEmbeddingModel.from_pretrained("gemini-embedding-001")
    inputs = [TextEmbeddingInput(text=text, task_type="SEMANTIC_SIMILARITY")]
    embeddings = model.get_embeddings(inputs, output_dimensionality=2048)
    return embeddings[0].values


async def obtener_practicas_afines(cv_url: str):
    tiempos = {}
    t0 = time.perf_counter()

    # 1. Generar embedding del CV
    t1 = time.perf_counter()
    cv_texto = obtener_texto_pdf_de_url(cv_url)
    query_embedding = await convert_query_to_embedding(cv_texto)
    tiempos["1. Generar embedding"] = time.perf_counter() - t1

    # 2. Preparar vector y referencia a colección
    t2 = time.perf_counter()
    query_vector = Vector(query_embedding)
    practicas_ref = db.collection("practicas_embeddings_test")
    tiempos["2. Preparar vector y colección"] = time.perf_counter() - t2

    # 3. Ejecutar búsqueda vectorial Y procesar resultados
    t3 = time.perf_counter()
    resultados = []
    print("\n--- 🧠 Prácticas afines encontradas ---")
    print("(Menor distancia = mayor afinidad)\n")
    try:
        vector_query = practicas_ref.find_nearest(
            vector_field="embedding",
            query_vector=query_vector,
            distance_measure=DistanceMeasure.COSINE,
            limit=200,
            distance_threshold=1.0,
            distance_result_field="vector_distance",
        )
        doc_count = 0
        for doc in vector_query.stream():
            doc_count += 1
            data = doc.to_dict()
            data['id'] = doc.id
            company = data.get('company', 'Empresa Desconocida')
            title = data.get('title', 'Título Desconocido')
            distance = data.get('vector_distance', None)

            print(f"🔹 [{doc_count}] Empresa: {company} | Título: {title} | Distancia: {distance:.4f} | ID: {data['id']}")
            resultados.append(data)
    except Exception as e:
        print(f"❌ ERROR durante la búsqueda o el procesamiento: {e}")
    tiempos["3. Ejecutar y procesar búsqueda vectorial"] = time.perf_counter() - t3

    tiempos["⏱️ Tiempo total"] = time.perf_counter() - t0

    # Mostrar tabla de tiempos
    print("\n==== ⏱️ TIEMPOS DE EJECUCIÓN POR SECCIÓN ====")
    ancho = max(len(k) for k in tiempos.keys())
    for k, v in tiempos.items():
        print(f"{k.ljust(ancho)} : {v:.4f} segundos")
    print("============================================\n")

    return resultados


cv_string = """
{
  "searching": "Practicas Marketing",
  "category": [
    "Administración",
    "Marketing"
  ],
  "hard_skills": [
    "Microsoft Office Intermedio/Avanzado",
    "Word",
    "Power Point",
    "Excel Intermedio/Avanzado",
    "Adobe Illustrator Intermedio",
    "Adobe Photoshop Intermedio",
    "Power BI Intermedio",
    "SAP",
    "CONCUR"
  ],
  "soft_skills": [
    "Coordinación",
    "Organización",
    "Comunicación",
    "Atención al detalle",
    "Resolución de problemas",
    "Análisis de datos",
    "Liderazgo",
    "Negociación",
    "Trabajo en equipo"
  ],
  "language_requirements": "Inglés Intermedio - Avanzado",
  "related_degrees": [
    "Administración de Empresas"
  ]
}
"""

cv_url = "https://pub-a950f98665ac41c49a6bdc63fff76a40.r2.dev/cvs/1749502511712.pdf"

async def main():
    print("🚀 Buscando prácticas afines...")
    await obtener_practicas_afines(cv_url)

if __name__ == "__main__":
    asyncio.run(main())
