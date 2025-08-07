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
Actúa como un extractor y clasificador de datos de currículums. Recibirás el texto completo de un currículum de un postulante. Tu única tarea es analizar este texto y devolver un objeto JSON que contenga los metadatos de las habilidades y experiencia del candidato. No incluyas ningún otro campo, solo el objeto de metadatos.

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

1. category: Debes inferir la(s) categoría(s) laboral(es) del postulante basándote en su experiencia laboral y su formación. El resultado debe ser una lista de cadenas. Si el candidato abarca claramente dos áreas, puedes seleccionar un máximo de dos categorías de la siguiente lista. No uses ningún valor fuera de esta lista.
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

3. soft_skills: Infiere las habilidades interpersonales o blandas basándote en las descripciones de las funciones y responsabilidades del postulante. Busca habilidades como Coordinación, Organización, Comunicación, Liderazgo, Atención al detalle, Resolución de problemas. El resultado debe ser una lista de cadenas.

4. language_requirements: Busca cualquier mención de idiomas en la sección de "Idiomas" o similar. Si el CV incluye un idioma, extrae el idioma y el nivel (ej: "Inglés Avanzado"). Si no se menciona ningún idioma, el valor debe ser `null`. El resultado debe ser una cadena o el valor `null`.

5. related_degrees: Identifica las carreras o campos de estudio mencionados en la sección de "Educación" o "Formación". Enumera cada una de estas carreras en una lista de cadenas. Usa siempre el nombre largo y formal (por ejemplo, "Ingeniería Industrial").

Importante: La respuesta debe ser solo el objeto JSON que contiene los metadatos, sin ninguna explicación o texto adicional.

{format_instructions}

Descripción del currículum: {description}
"""

prompt = PromptTemplate(
    template=prompt_template,
    input_variables=["description"],
    partial_variables={"format_instructions": parser.get_format_instructions()}
)

async def extract_metadata_with_gemini(desired_position: str | None, description: str | None) -> dict | None:
    """
    Usa Gemini para extraer metadatos estructurados de un currículum.
    Retorna un diccionario con los metadatos o None si hay error.
    """
    if not desired_position and not description:
        return None

    print(f"Generando metadatos para el currículum: '{(desired_position or 'Sin título')[:50]}...'")
    
    try:
        # Crear el prompt con los datos de entrada
        _input = prompt.format_prompt(
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
