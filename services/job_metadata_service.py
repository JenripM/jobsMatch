import asyncio
import json
from typing import List, Optional, Union
from google.cloud import aiplatform
from langchain_google_vertexai import ChatVertexAI
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
import os
import sys
sys.path.append('..')
from db import db

# --- Configuración Inicial ---
# Asegúrate de que 'db' sea una instancia de firestore.Client()
# Para que este script funcione, necesitas tener configuradas tus credenciales de Google Cloud.
# La forma más común para desarrollo local es:
# 1. Instalar Google Cloud CLI.
# 2. Autenticar: `gcloud auth application-default login`
# O configurar la variable de entorno GOOGLE_APPLICATION_CREDENTIALS apuntando a tu archivo JSON de clave de cuenta de servicio.

# --- Definición del Schema con Pydantic ---
class JobMetadata(BaseModel):
    """Schema para los metadatos de una oferta de empleo"""
    category: List[str] = Field(
        description="Lista de categorías del puesto. Máximo 2 categorías de la lista permitida."
    )
    hard_skills: List[str] = Field(
        description="Lista de habilidades técnicas y herramientas de software mencionadas"
    )
    soft_skills: List[str] = Field(
        description="Lista de habilidades interpersonales o blandas inferidas"
    )
    language_requirements: Optional[str] = Field(
        default=None,
        description="Requisitos de idioma mencionados o null si no se especifica"
    )
    related_degrees: List[str] = Field(
        description="Lista de carreras o campos de estudio mencionados"
    )

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

# Definir el prompt template
prompt_template = """
Actúa como un extractor y clasificador de datos de ofertas de empleo. Recibirás el texto completo de una oferta laboral. Tu única tarea es analizar este texto y devolver un objeto JSON que contenga los metadatos de la oferta. No incluyas ningún otro campo, solo el objeto metadata.

El JSON de salida debe tener esta estructura:
{{
  "category": ["String"],
  "hard_skills": ["String"],
  "soft_skills": ["String"],
  "language_requirements": "String o Null",
  "related_degrees": ["String"]
}}

Instrucciones para inferir cada campo:

- Sé extremadamente estricto con el formato de los valores. Para los nombres de carreras y títulos, usa SIEMPRE el nombre completo y formal, con mayúscula inicial en cada palabra, sin abreviaturas, diminutivos ni sinónimos. Ejemplo correcto: "Ingeniería Industrial". Ejemplo incorrecto: "Ing. Industrial", "ing. industrial", "Industrial Engineering".
- Usa este mismo criterio de formato para cualquier campo de tipo lista de nombres o títulos.
- No inventes información. Solo incluye datos que estén textualmente presentes en el texto o que sean evidentemente obvios según el contexto. Si no es explícito ni obvio, deja el campo vacío o null según corresponda.
- Si tienes dudas, prefiere ser conservador y omitir información dudosa.
- No incluyas explicaciones, solo el objeto JSON.

1. category: Debes inferir la(s) categoría(s) del puesto basándote en el título y la descripción. El resultado debe ser una lista de cadenas. Idealmente, escoge la categoría principal. Si el puesto abarca claramente dos áreas, puedes seleccionar un máximo de dos categorías de la siguiente lista. No uses ningún valor fuera de esta lista.
   * Administración
   * Finanzas
   * Recursos Humanos
   * Marketing
   * Comunicaciones
   * Ventas
   * Logística
   * Tecnología
   * Ingeniería
   * Legal
   * Operaciones
   * Diseño
   * Construcción
   * Salud
   * Educación
   * Banca
   * Consultoría
   * Turismo
   * Retail
   * Servicio al Cliente

2. hard_skills: Extrae todas las habilidades técnicas y herramientas de software que se mencionen. Busca términos como "Excel", "Power BI", "SAP", "Office", "SQL", lenguajes de programación, etc. Si se especifica un nivel (`avanzado`, `intermedio`), inclúyelo en el valor (ej: "Excel Avanzado"). El resultado debe ser una lista de cadenas.

3. soft_skills: Infiere las habilidades interpersonales o blandas basándote en las funciones y responsabilidades. Busca habilidades como Coordinación, Organización, Comunicación, Liderazgo, Atención al detalle, Resolución de problemas. El resultado debe ser una lista de cadenas.

4. language_requirements: Busca cualquier mención de idiomas requeridos. Si la oferta pide un idioma, extrae el idioma y el nivel (ej: "Inglés Avanzado"). Si no se menciona ningún idioma, el valor debe ser `null`. El resultado debe ser una cadena o el valor `null`.

5. related_degrees: Identifica las carreras o campos de estudio mencionados en la sección de "Requisitos" (ej: "Administración, Negocios Internacionales, Ingeniería Industrial, Economía y afines."). Enumera cada una de estas carreras en una lista de cadenas. Usa siempre el nombre largo y formal (por ejemplo, "Ingeniería Industrial").

Importante: La respuesta debe ser solo el objeto JSON que contiene los metadatos, sin ninguna explicación o texto adicional.

{format_instructions}

Título de la oferta: {title}
Descripción de la oferta: {description}
"""

prompt = PromptTemplate(
    template=prompt_template,
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
        
        # Parsear la respuesta usando Pydantic
        parsed_metadata = parser.parse(response.content)
        
        # Convertir a diccionario
        return parsed_metadata.model_dump()
        
    except Exception as e:
        print(f"Error al extraer metadatos con Gemini: {e}")
        print(f"Respuesta recibida: {response.content if 'response' in locals() else 'No response'}")
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
    
    practicas_ref = db.collection(collection_name)
    
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

# --- Punto de entrada principal para ejecutar el script ---
if __name__ == "__main__":
    asyncio.run(generate_metadata_for_collection(collection_name="practicas_embeddings_test", overwrite_existing=False))
