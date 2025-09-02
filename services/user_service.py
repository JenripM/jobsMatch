"""
Servicio de Usuario - Gestión completa de CVs y metadatos de usuarios

Este servicio consolida todas las funcionalidades relacionadas con usuarios:
- Extracción y procesamiento de CVs
- Generación de embeddings y metadatos
- Gestión de CVs en base de datos
- Consulta de información de usuario

Funciones deprecadas migradas desde:
- cv_upload_service.py
- user_metadata_service.py  
- models.py (solo funciones de usuario)
"""

import asyncio
import json
import time
import io
from typing import Dict, List, Optional, Any
from datetime import datetime
from google.cloud import aiplatform
from langchain_google_vertexai import ChatVertexAI
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
import os
import sys
import pypdf
import traceback
from texttable import Texttable
import time

# Importar el servicio de almacenamiento R2
from services.storage_service import r2_storage, ALLOWED_FILE_TYPES, FILE_SIZE_LIMITS

sys.path.append('..')
from db import db_users
from services.embedding_service import get_embedding_from_text
from schemas.cv_types import CVData, UserMetadata
from prompts.cv_prompts import CV_FIELDS_INFERENCE_PROMPT, CV_METADATA_INFERENCE_PROMPT

# =============================
# CONFIGURACIÓN DE IA
# =============================

print("Inicializando el modelo de Gemini para procesamiento de CVs...")
try:
    llm = ChatVertexAI(
        model="gemini-2.5-flash-lite",
        temperature=0,
        max_tokens=None,
        max_retries=6,
        stop=None,
    )
    print("Modelo de Gemini cargado exitosamente.")
except Exception as e:
    print(f"Error al cargar el modelo de Gemini: {e}")
    exit()

# =============================
# CONFIGURACIÓN DE PARSERS
# =============================

cv_parser = PydanticOutputParser(pydantic_object=CVData)
metadata_parser = PydanticOutputParser(pydantic_object=UserMetadata)

# =============================
# FUNCIONES DE PROCESAMIENTO DE PDF
# =============================

def extract_text_from_pdf_file(pdf_file: bytes) -> str:
    """
    Extrae texto de un archivo PDF en memoria
    
    Args:
        pdf_file: Archivo PDF como bytes
        
    Returns:
        str: Texto extraído del PDF
    """
    try:
        # Crear un buffer de memoria con el contenido del PDF
        pdf_buffer = io.BytesIO(pdf_file)
        
        # Crear el lector de PDF
        pdf_reader = pypdf.PdfReader(pdf_buffer)
        
        # Extraer texto de todas las páginas
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        
        return text.strip()
        
    except Exception as e:
        print(f"❌ Error al extraer texto del PDF: {e}")
        raise Exception(f"Error al procesar archivo PDF: {str(e)}")

# =============================
# FUNCIONES DE EXTRACCIÓN DE DATOS
# =============================

async def infer_cv_structured_data(cv_text: str) -> Dict[str, Any]:
    """
    Infiere y estructura los datos del CV usando IA
    
    Args:
        cv_text: Texto completo del CV
        
    Returns:
        Dict con la estructura de datos del CV
    """
    start_time = time.time()
    print(f"🤖 Iniciando extracción de datos estructurados del CV...")
    
    try:
        # Crear el prompt con el texto del CV
        prompt_start = time.time()
        prompt = PromptTemplate(
            template=CV_FIELDS_INFERENCE_PROMPT,
            input_variables=["cv_text"],
            partial_variables={"format_instructions": cv_parser.get_format_instructions()}
        )
        prompt_time = time.time() - prompt_start
        print(f"   ⏱️ Creación del prompt: {prompt_time:.4f}s")
        
        # Generar la respuesta usando IA
        ai_start = time.time()
        chain = prompt | llm | cv_parser
        print(f"   🔗 Cadena de procesamiento creada")
        
        print(f"   🤖 Invocando IA para extraer datos estructurados...")
        cv_data = await chain.ainvoke({"cv_text": cv_text})
        ai_time = time.time() - ai_start
        print(f"   ⏱️ Procesamiento con IA: {ai_time:.4f}s")
        
        # Convertir a diccionario
        dict_start = time.time()
        result = cv_data.dict()
        dict_time = time.time() - dict_start
        print(f"   ⏱️ Conversión a diccionario: {dict_time:.4f}s")
        
        total_time = time.time() - start_time
        print(f"✅ Extracción de datos estructurados completada en {total_time:.4f}s")
        print(f"   📊 Tiempos desglosados:")
        print(f"      - Prompt: {prompt_time:.4f}s")
        print(f"      - IA: {ai_time:.4f}s")
        print(f"      - Conversión: {dict_time:.4f}s")
        
        return result
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ Error al extraer datos estructurados del CV después de {total_time:.4f}s: {e}")
        raise Exception(f"Error al procesar CV con IA: {str(e)}")

async def extract_user_metadata(cv_content: str) -> Dict[str, Any]:
    """
    Extrae metadatos del usuario basado en el contenido del CV
    
    Args:
        cv_content: Contenido del CV como texto
        
    Returns:
        Dict con los metadatos del usuario
        
    Raises:
        ValueError: Si cv_content está vacío o es None
    """
    # Validar entrada
    if not cv_content or not cv_content.strip():
        raise ValueError("cv_content no puede estar vacío o ser None")
    
    print(f"🤖 Generando metadatos para el currículum del usuario")
    
    try:
        # Crear el prompt con los datos de entrada
        prompt = PromptTemplate(
            template=CV_METADATA_INFERENCE_PROMPT,
            input_variables=["description"],
            partial_variables={"format_instructions": metadata_parser.get_format_instructions()}
        )
        
        _input = prompt.format_prompt(
            description=cv_content
        )
        
        # Llamar al modelo
        response = await llm.ainvoke(_input.to_string())

        if not response or not response.content:
            print("⚠️ Respuesta vacía del modelo.")
            return None

        # Parsear la respuesta usando Pydantic
        parsed_metadata = metadata_parser.parse(response.content)
        
        # Convertir a diccionario
        return parsed_metadata.model_dump()
        
    except Exception as e:
        print(f"❌ Error al extraer metadatos con Gemini: {e}")
        print(f"Respuesta recibida: {response.content if 'response' in locals() else 'No response'}")
        return None

# =============================
# FUNCIONES DE GENERACIÓN DE EMBEDDINGS
# =============================

async def generate_cv_embeddings(cv_content: str) -> Dict[str, List[float]]:
    """
    Genera embeddings múltiples de un CV a partir de su contenido
    
    Args:
        cv_content: Contenido del CV como texto
        
    Returns:
        Dict con embeddings por aspecto o None si hay error
        
    Raises:
        ValueError: Si cv_content está vacío o es None
    """
    try:
        # 1. Generar metadatos
        metadata = await extract_user_metadata(cv_content)
        if not metadata:
            return None

        print(f"🚀 Metadata extraída: {metadata}")

        # 2. Preparar aspectos para embeddings
        aspects = {
            'hard_skills': ", ".join(metadata.get('hard_skills', [])),
            'soft_skills': ", ".join(metadata.get('soft_skills', [])),
            'category': json.dumps({
                'related_degrees': metadata.get('related_degrees', []),
                'category': metadata.get('category', [])
            }, ensure_ascii=False),
            'general': json.dumps(metadata, ensure_ascii=False, indent=2)
        }

        print(f"🚀 Generando embeddings para {len(aspects)} aspectos...")

        # 3. Generar embeddings en paralelo
        results = await asyncio.gather(*[
            get_embedding_from_text(aspect_text) for aspect_text in aspects.values()
        ])

        # 4. Construir diccionario de resultados
        embeddings_dict = {}
        for i, (aspect_name, embedding) in enumerate(zip(aspects.keys(), results)):
            if embedding and len(embedding) == 2048:
                embeddings_dict[aspect_name] = list(embedding._value)
                print(f"  ✅ {aspect_name}: embedding generado")
            else:
                print(f"  ⚠️ {aspect_name}: embedding inválido")

        return embeddings_dict

    except ValueError as e:
        # Re-lanzar ValueError para que el llamador sepa que es un error de validación
        raise e
    except Exception as e:
        print(f"❌ Error en generate_cv_embeddings: {e}")
        return None

# =============================
# FUNCIONES DE GESTIÓN DE BASE DE DATOS
# =============================

async def upload_cv_to_database(pdf_file_content: bytes, user_id: str) -> Dict[str, Any]:
    """
    Sube un CV a la base de datos del usuario y a R2 Cloudflare
    
    Args:
        pdf_file_content: Contenido del archivo PDF como bytes
        user_id: ID del usuario
        
    Returns:
        Dict con la información del CV subido
    """
    total_start_time = time.time()
    timing_stats = {}
    
    try:
        print(f"🚀 Iniciando subida de CV para usuario {user_id}")
        print(f"   📄 Tamaño del archivo: {len(pdf_file_content)} bytes")
        
        # 1. Generar CV ID primero
        doc_ref = db_users.collection("userCVs").document()
        cv_id = doc_ref.id
        print(f"📄 CV ID generado: {cv_id}")
        
        # 2. Subir PDF a R2 Cloudflare con URL estable
        r2_start = time.time()
        print("☁️ Subiendo PDF a R2 Cloudflare con URL estable...")
        
        # Validar tipo y tamaño del archivo
        if not r2_storage.validate_file_type("cv.pdf", ALLOWED_FILE_TYPES['CV']):
            raise Exception("Tipo de archivo no permitido para CV")
        
        if not r2_storage.validate_file_size(len(pdf_file_content), FILE_SIZE_LIMITS['CV']):
            raise Exception(f"Archivo demasiado grande. Máximo {FILE_SIZE_LIMITS['CV']}MB")
        
        # Generar nombre bonito para el archivo (se usará en Content-Disposition)
        pretty_filename = "cv.pdf"  # Por ahora genérico, se actualizará después con los datos extraídos
        
        # Subir a R2 con clave estable
        stable_key = r2_storage.generate_stable_cv_key(cv_id)
        file_url = await r2_storage.upload_file_to_r2(
            file_data=pdf_file_content,
            file_name=pretty_filename,
            content_type="application/pdf",
            stable_key=stable_key  # Usar clave estable
        )
        r2_time = time.time() - r2_start
        timing_stats['r2_upload'] = r2_time
        print(f"   ⏱️ Subida a R2: {r2_time:.4f}s")
        print(f"   🔗 URL estable del archivo: {file_url}")
        
        # 3. Extraer texto del PDF
        pdf_start = time.time()
        print("📄 Extrayendo texto del PDF...")
        cv_text = extract_text_from_pdf_file(pdf_file_content)
        pdf_time = time.time() - pdf_start
        timing_stats['pdf_extraction'] = pdf_time
        print(f"   ⏱️ Extracción de PDF: {pdf_time:.4f}s")
        print(f"   📝 Longitud del texto: {len(cv_text)} caracteres")
        
        # 4. Procesar en paralelo: embeddings y datos estructurados
        parallel_start = time.time()
        print("⚡ Procesando embeddings y datos en paralelo...")
        
        # Crear tareas asíncronas
        embeddings_task = generate_cv_embeddings(cv_text)
        data_task = infer_cv_structured_data(cv_text)
        
        # Ejecutar en paralelo
        embeddings, cv_data = await asyncio.gather(embeddings_task, data_task)
        parallel_time = time.time() - parallel_start
        timing_stats['parallel_processing'] = parallel_time
        print(f"   ⏱️ Procesamiento paralelo: {parallel_time:.4f}s")
        print(f"   🔗 Embeddings generados: {list(embeddings.keys())}")
        print(f"   📊 Secciones de datos: {list(cv_data.keys())}")
        
        # 4.5. Actualizar Content-Disposition del archivo con nombre bonito
        try:
            pretty_filename = r2_storage.generate_pretty_cv_filename(cv_data)
            if pretty_filename != "cv.pdf":  # Solo actualizar si hay un nombre mejor
                print(f"   📝 Actualizando nombre de descarga a: {pretty_filename}")
                
                # Re-subir solo para actualizar Content-Disposition (R2 soporta esto)
                await r2_storage.upload_file_to_r2(
                    file_data=pdf_file_content,
                    file_name=pretty_filename,
                    content_type="application/pdf",
                    stable_key=stable_key
                )
                print(f"   ✅ Nombre de descarga actualizado")
        except Exception as e:
            print(f"   ⚠️ No se pudo actualizar nombre de descarga: {e}")
            # No fallar por esto, continuar normalmente
        
        # 5. Preparar documento para Firestore
        prep_start = time.time()
        print("📋 Preparando documento para Firestore...")
        now = datetime.now()
        cv_document = {
            "createdAt": now,
            "updatedAt": now,
            "template": "harvard",  # Por ahora siempre harvard
            "title": f"CV de {cv_data['personalInfo']['fullName']}",
            "updatedAt": now,
            "userId": user_id,
            "embeddings": embeddings,
            "data": cv_data,
            "fileUrl": file_url  # Agregar URL del archivo en R2
        }
        prep_time = time.time() - prep_start
        timing_stats['document_preparation'] = prep_time
        print(f"   ⏱️ Preparación del documento: {prep_time:.4f}s")
        print(f"   📄 Título generado: {cv_document['title']}")
        
        # 6. Guardar en Firestore (usando el doc_ref ya creado)
        db_start = time.time()
        print("💾 Guardando en base de datos...")
        doc_ref.set(cv_document)
        db_time = time.time() - db_start
        timing_stats['database_save'] = db_time
        print(f"   ⏱️ Guardado en base de datos: {db_time:.4f}s")
        print(f"   🆔 ID del documento: {doc_ref.id}")
        
        # 7. Verificar si es el primer CV del usuario y actualizar Users
        users_update_start = time.time()
        print("👤 Verificando si es el primer CV del usuario...")
        
        # Buscar CVs existentes del usuario
        existing_cvs = db_users.collection("userCVs").where("userId", "==", user_id).stream()
        existing_cvs_list = list(existing_cvs)
        
        # Si solo hay 1 CV (el que acabamos de crear), es el primer CV
        if len(existing_cvs_list) == 1:
            print(f"   ✅ Es el primer CV del usuario, actualizando colección Users...")
            
            # Actualizar el documento del usuario en la colección Users
            user_doc_ref = db_users.collection("users").document(user_id)
            user_doc = user_doc_ref.get()
            
            if user_doc.exists:
                # El usuario existe, actualizar cvSelectedId
                user_doc_ref.update({
                    "cvSelectedId": doc_ref.id,
                    "updatedAt": datetime.now()
                })
                print(f"   ✅ Usuario actualizado con cvSelectedId: {doc_ref.id}")
            else:
                # El usuario no existe en Users, crear el documento
                user_doc_ref.set({
                    "id": user_id,
                    "cvSelectedId": doc_ref.id,
                    "createdAt": datetime.now(),
                    "updatedAt": datetime.now()
                })
                print(f"   ✅ Usuario creado con cvSelectedId: {doc_ref.id}")
        else:
            print(f"   ℹ️ No es el primer CV del usuario ({len(existing_cvs_list)} CVs existentes)")
        
        users_update_time = time.time() - users_update_start
        timing_stats['users_update'] = users_update_time
        print(f"   ⏱️ Actualización de Users: {users_update_time:.4f}s")
        
        # 8. Preparar respuesta
        response_start = time.time()
        print("📤 Preparando respuesta...")
        
        # Determinar si es el primer CV
        is_first_cv = len(existing_cvs_list) == 1
        
        response = {
            "success": True,
            "cv_id": doc_ref.id,
            "cv_info": {
                "title": cv_document["title"],
                "full_name": cv_data["personalInfo"]["fullName"],
                "email": cv_data["personalInfo"]["email"],
                "created_at": now.isoformat(),
                "template": cv_document["template"],
                "file_url": file_url  # Incluir URL del archivo en la respuesta
            },
            "metadata": {
                "embeddings_aspects": list(embeddings.keys()),
                "data_sections": list(cv_data.keys()),
                "total_education_items": len(cv_data.get("education", [])),
                "total_work_experience_items": len(cv_data.get("workExperience", [])),
                "total_skills": len(cv_data.get("skills", [])),
                "total_projects": len(cv_data.get("projects", []))
            },
            "user_update": {
                "is_first_cv": is_first_cv,
                "cv_selected_id": doc_ref.id if is_first_cv else None,
                "total_user_cvs": len(existing_cvs_list)
            },
            "timing_stats": timing_stats
        }
        response_time = time.time() - response_start
        timing_stats['response_preparation'] = response_time
        print(f"   ⏱️ Preparación de respuesta: {response_time:.4f}s")
        
        # Calcular tiempo total
        total_time = time.time() - total_start_time
        timing_stats['total_time'] = total_time
        
        print(f"✅ CV subido exitosamente con ID: {doc_ref.id}")
        print(f"🎯 TIEMPO TOTAL: {total_time:.4f}s")
        print(f"📊 ESTADÍSTICAS DE TIEMPO:")
        print(f"   - Subida a R2: {timing_stats['r2_upload']:.4f}s")
        print(f"   - Extracción PDF: {timing_stats['pdf_extraction']:.4f}s")
        print(f"   - Procesamiento paralelo: {timing_stats['parallel_processing']:.4f}s")
        print(f"   - Preparación documento: {timing_stats['document_preparation']:.4f}s")
        print(f"   - Guardado en BD: {timing_stats['database_save']:.4f}s")
        print(f"   - Actualización Users: {timing_stats.get('users_update', 0):.4f}s")
        print(f"   - Preparación respuesta: {timing_stats['response_preparation']:.4f}s")
        print(f"   - 🎆 TOTAL: {timing_stats['total_time']:.4f}s")
        
        return response
        
    except Exception as e:
        total_time = time.time() - total_start_time
        print(f"❌ Error al subir CV después de {total_time:.4f}s: {e}")
        raise Exception(f"Error al subir CV: {str(e)}")

async def get_user_cvs(user_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene todos los CVs de un usuario
    
    Args:
        user_id: ID del usuario
        
    Returns:
        Lista de CVs del usuario
    """
    start_time = time.time()
    #print(f"📥 Iniciando consulta de CVs para usuario {user_id}")
    
    try:
        # Consultar CVs en Firestore
        query_start = time.time()
        cvs_ref = db_users.collection("userCVs").where("userId", "==", user_id)
        docs = cvs_ref.stream()
        query_time = time.time() - query_start
        #print(f"   ⏱️ Consulta en Firestore: {query_time:.4f}s")
        
        # Procesar documentos
        process_start = time.time()
        cvs = []
        for doc in docs:
            cv_data = doc.to_dict()
            cv_data["id"] = doc.id
            #quitamos los embeddings para que no se envien a la frontend
            cv_data["embeddings"] = None
            cvs.append(cv_data)
        process_time = time.time() - process_start
        #print(f"   ⏱️ Procesamiento de documentos: {process_time:.4f}s")
        
        total_time = time.time() - start_time
        """
        print(f"✅ Consulta completada en {total_time:.4f}s")
        print(f"   📊 CVs encontrados: {len(cvs)}")
        print(f"   📈 Tiempos desglosados:")
        print(f"      - Consulta: {query_time:.4f}s")
        print(f"      - Procesamiento: {process_time:.4f}s")
        """
        return cvs
        
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ Error al obtener CVs después de {total_time:.4f}s: {e}")
        raise Exception(f"Error al obtener CVs: {str(e)}")

# Funcion para extraer los datos del usuario de la base de datos
async def fetch_user_cv(user_id: str) -> Dict[str, Any]:
    """
    Obtiene el CV seleccionado de un usuario
    
    Args:
        user_id: ID del usuario
        
    Returns:
        Dict con los datos del CV seleccionado o None si no existe
    """
    try:
        # Obtener el documento del usuario
        user_doc = db_users.collection("users").document(user_id).get()
        
        if not user_doc.exists:
            raise ValueError(f"Usuario con ID {user_id} no encontrado en la base de datos.")

        # Convertir el documento a diccionario
        user_data = user_doc.to_dict()
        #print("Obteniendo datos del usuario: ", user_data.get("displayName", None))
        cvSelectedId = user_data.get("cvSelectedId", None)
        #print("cvSelectedId: ", cvSelectedId)

        if cvSelectedId:
            #print(f"Buscando CV con ID específico: {cvSelectedId}")
            cv_doc = db_users.collection("userCVs").document(cvSelectedId).get()
            #print(f"CV encontrado: {cv_doc.exists}")
        else:
            # Si el usuario no tiene un cvSelectedId, tomar cualquier CV disponible
            #print("El usuario no cuenta con el campo cvSelectedId. Seleccionando cualquier CV disponible...")
            cv_query = db_users.collection("userCVs").where("userId", "==", user_id).get()
            
            #print(f"Resultados de la query: {len(cv_query) if cv_query else 0}")
            
            if not cv_query or len(cv_query) == 0:
                raise ValueError(f"El usuario {user_id} no tiene ningún CV en la base de datos")
            
            # Tomar el primer CV disponible (sin ordenar)
            cv_doc = cv_query[0]
            cvSelectedId = cv_doc.id
            #print(f"CV seleccionado automáticamente con ID: {cvSelectedId}")

        if not cv_doc.exists:
            #print(f"❌ CV con ID {cvSelectedId} no existe en la base de datos")
            raise ValueError(f"CV con ID {cvSelectedId} no encontrado en la base de datos")
        
        # Convertir el documento a diccionario
        cv = cv_doc.to_dict()
        # Agregar el ID del documento al CV
        cv["id"] = cv_doc.id
        #print(f"✅ CV encontrado exitosamente: {cv.get('title', 'Sin título')}")
        return cv
        
    except Exception as e:
        print(f"❌ Error al obtener CV seleccionado del usuario: {e}")
        print(f"Tipo de error: {type(e).__name__}")
        print(f"Traceback completo: {traceback.format_exc()}")
        return None


# =============================
# NUEVAS FUNCIONES: GUARDAR/ACTUALIZAR/ELIMINAR CV
# =============================

async def save_cv(cv: Dict[str, Any]) -> Dict[str, Any]:
    """
    Guarda un CV completo en la base de datos (excepto embeddings, que se generan aquí).
    Si se proporciona un archivo PDF, también lo sube a R2 Cloudflare.

    Args:
        cv: Objeto CV completo sin embeddings. Debe contener al menos:
            - userId (str)
            - data (dict) con la estructura del CV
            - fileData (bytes, opcional) contenido del archivo PDF
            - fileName (str, opcional) nombre del archivo

    Returns:
        Dict con información del CV guardado y metadatos del proceso
    """
    total_start_time = time.time()
    timing_stats: Dict[str, float] = {}

    try:
        if not isinstance(cv, dict):
            raise ValueError("cv debe ser un diccionario")

        user_id = cv.get("userId")
        cv_data = cv.get("data")
        file_data = cv.get("fileData")  # Bytes del archivo PDF
        file_name = cv.get("fileName", "cv.pdf")  # Nombre del archivo
        
        if not user_id:
            raise ValueError("Falta el campo obligatorio 'userId' en el CV")
        if not isinstance(cv_data, dict):
            raise ValueError("El campo 'data' del CV debe ser un diccionario")

        print(f"🚀 Añadiendo CV para usuario {user_id}")

        # 1) Generar el documento de Firestore primero para obtener el cv_id
        doc_ref = db_users.collection("userCVs").document()
        cv_id = doc_ref.id
        print(f"📄 CV ID generado: {cv_id}")

        # 2) Si hay archivo PDF, subirlo a R2 con URL estable
        file_url = None
        if file_data and isinstance(file_data, bytes):
            r2_start = time.time()
            print("☁️ Subiendo archivo PDF a R2 Cloudflare con URL estable...")
            
            # Validar tipo y tamaño del archivo
            if not r2_storage.validate_file_type(file_name, ALLOWED_FILE_TYPES['CV']):
                raise Exception("Tipo de archivo no permitido para CV")
            
            if not r2_storage.validate_file_size(len(file_data), FILE_SIZE_LIMITS['CV']):
                raise Exception(f"Archivo demasiado grande. Máximo {FILE_SIZE_LIMITS['CV']}MB")
            
            # Generar nombre bonito si hay datos del CV
            pretty_filename = file_name
            if cv_data:
                pretty_filename = r2_storage.generate_pretty_cv_filename(cv_data)
            
            # Generar clave estable y subir a R2
            stable_key = r2_storage.generate_stable_cv_key(cv_id)
            file_url = await r2_storage.upload_file_to_r2(
                file_data=file_data,
                file_name=pretty_filename,
                content_type="application/pdf",
                stable_key=stable_key  # Usar clave estable
            )
            r2_time = time.time() - r2_start
            timing_stats["r2_upload"] = r2_time
            print(f"   ⏱️ Subida a R2: {r2_time:.4f}s")
            print(f"   🔗 URL estable del archivo: {file_url}")

        # 3) Generar embeddings solo si cv_data no está vacío
        embeddings = None
        if cv_data:  # Solo generar embeddings si hay datos
            emb_start = time.time()
            cv_text = json.dumps(cv_data, ensure_ascii=False)
            embeddings = await generate_cv_embeddings(cv_text)
            emb_time = time.time() - emb_start
            timing_stats["embeddings_generation"] = emb_time
            if not embeddings:
                raise Exception("No se pudieron generar los embeddings del CV")
            print(f"   ⏱️ Embeddings generados en {emb_time:.4f}s; aspectos: {list(embeddings.keys())}")
        else:
            print("   ⏭️ CV data está vacío, saltando generación de embeddings")

        # 4) Preparar documento para Firestore: subir tal cual viene y añadir 'embeddings' y 'fileUrl'
        prep_start = time.time()
        cv_document: Dict[str, Any] = {**cv}
        
        # Solo añadir embeddings si se generaron
        if embeddings:
            cv_document["embeddings"] = embeddings
        
        # Remover campos que no deben ir a la base de datos
        cv_document.pop("fileData", None)  # No guardar los bytes en Firestore
        
        # Agregar fileUrl si se subió a R2
        if file_url:
            cv_document["fileUrl"] = file_url
        # Si no hay fileUrl pero hay cv_data, generar PDF automáticamente con URL estable
        elif cv_data and not file_url:
            try:
                print("   📄 Generando PDF automáticamente desde cvData con URL estable...")
                pdf_start = time.time()
                
                # Importar el generador de PDF
                from services.pdf_generator_service import CVPDFGenerator
                
                # Generar PDF a partir del cvData
                pdf_content, pdf_file_name = CVPDFGenerator.generate_pdf_from_cv_data(cv_data)
                
                # Generar nombre bonito para descarga
                pretty_filename = r2_storage.generate_pretty_cv_filename(cv_data)
                
                # Subir PDF generado a R2 con clave estable
                stable_key = r2_storage.generate_stable_cv_key(cv_id)
                auto_file_url = await r2_storage.upload_file_to_r2(
                    file_data=pdf_content,
                    file_name=pretty_filename,
                    content_type="application/pdf",
                    stable_key=stable_key  # Usar clave estable
                )
                
                # Agregar fileUrl al documento
                cv_document["fileUrl"] = auto_file_url
                file_url = auto_file_url  # Actualizar variable para la respuesta
                
                pdf_time = time.time() - pdf_start
                timing_stats["pdf_generation"] = pdf_time
                print(f"   ⏱️ PDF generado y subido en {pdf_time:.4f}s")
                print(f"   🔗 URL estable del PDF generado: {auto_file_url}")
                
            except Exception as pdf_error:
                print(f"   ⚠️ Error generando PDF automático (continuando sin fileUrl): {pdf_error}")
                # No fallar el proceso completo, continuar sin fileUrl
                pass
            
        prep_time = time.time() - prep_start
        timing_stats["document_preparation"] = prep_time
        print(f"   ⏱️ Documento preparado en {prep_time:.4f}s")

        # 5) Guardar en Firestore (usando el doc_ref ya creado)
        db_start = time.time()
        doc_ref.set(cv_document)
        db_time = time.time() - db_start
        timing_stats["database_save"] = db_time
        print(f"   💾 Guardado en {db_time:.4f}s | ID: {doc_ref.id}")

        # 6) Si es el primer CV del usuario, actualizar la colección Users
        users_update_start = time.time()
        existing_cvs_list = list(db_users.collection("userCVs").where("userId", "==", user_id).stream())
        if len(existing_cvs_list) == 1:
            print("   ✅ Primer CV del usuario. Actualizando 'user.cvSelectedId'...")
            user_doc_ref = db_users.collection("users").document(user_id)
            user_doc = user_doc_ref.get()
            if user_doc.exists:
                user_doc_ref.update({
                    "cvSelectedId": doc_ref.id,
                    "updatedAt": datetime.now(),
                })
            else:
                user_doc_ref.set({
                    "id": user_id,
                    "cvSelectedId": doc_ref.id,
                    "createdAt": datetime.now(),
                    "updatedAt": datetime.now(),
                })
        users_update_time = time.time() - users_update_start
        timing_stats["users_update"] = users_update_time

        # 7) Preparar respuesta
        response_start = time.time()
        is_first_cv = len(existing_cvs_list) == 1
        response: Dict[str, Any] = {
            "success": True,
            "cv_id": doc_ref.id,
            "file_url": file_url,  # Incluir URL del archivo si se subió
            "user_update": {
                "is_first_cv": is_first_cv,
                "cv_selected_id": doc_ref.id if is_first_cv else None,
                "total_user_cvs": len(existing_cvs_list),
            },
            "timing_stats": timing_stats,
        }
        response_time = time.time() - response_start
        timing_stats["response_preparation"] = response_time

        total_time = time.time() - total_start_time
        timing_stats["total_time"] = total_time
        print(f"✅ CV guardado exitosamente con ID: {doc_ref.id} | ⏱️ TOTAL: {total_time:.4f}s")

        return response

    except Exception as e:
        total_time = time.time() - total_start_time
        print(f"❌ Error al guardar CV después de {total_time:.4f}s: {e}")
        raise


async def update_cv(cv_id: str, cv: Dict[str, Any]) -> Dict[str, Any]:
    """
    Actualiza un CV existente generando embeddings solo si no los tiene.
    Si se proporciona fileData, también sube el archivo a R2 y actualiza fileUrl.

    Args:
        cv_id: ID del documento de CV en Firestore
        cv: Objeto CV con los campos a actualizar. Debe contener al menos 'data' (dict).
            - fileData (bytes, opcional) contenido del archivo PDF
            - fileName (str, opcional) nombre del archivo

    Returns:
        Dict con información del CV actualizado
    """
    total_start_time = time.time()
    timing_stats: Dict[str, float] = {}

    try:
        if not cv_id:
            raise ValueError("cv_id es requerido")
        if not isinstance(cv, dict):
            raise ValueError("cv debe ser un diccionario")
        cv_data = cv.get("data")
        file_data = cv.get("fileData")  # Bytes del archivo PDF
        file_name = cv.get("fileName", "cv.pdf")  # Nombre del archivo
        
        if not isinstance(cv_data, dict):
            raise ValueError("El campo 'data' del CV debe ser un diccionario")

        print(f"🚀 Actualizando CV {cv_id}")

        # Validar existencia del documento
        doc_ref = db_users.collection("userCVs").document(cv_id)
        snap = doc_ref.get()
        if not snap.exists:
            raise ValueError("El CV especificado no existe")

        # Obtener el documento actual para verificar si ya tiene embeddings
        current_cv = snap.to_dict()
        has_embeddings = current_cv.get("embeddings") is not None
        
        # Verificar si el data ha cambiado (solo si se está actualizando data)
        data_changed = False
        if cv_data:
            current_data = current_cv.get("data", {})
            # Convertir a JSON strings para comparación exacta
            current_data_str = json.dumps(current_data, sort_keys=True)
            new_data_str = json.dumps(cv_data, sort_keys=True)
            data_changed = current_data_str != new_data_str

        update_payload: Dict[str, Any] = {
            "updatedAt": datetime.now(),
        }
        
        # Agregar todos los campos del CV al payload de actualización
        # Excluir campos especiales que se manejan por separado
        excluded_fields = {"fileData", "fileName", "embeddings"}
        for key, value in cv.items():
            if key not in excluded_fields:
                update_payload[key] = value

        # 1) Si hay archivo PDF, sobrescribir usando URL estable (sin borrar)
        file_url = None
        if file_data and isinstance(file_data, bytes):
            r2_start = time.time()
            print("☁️ Procesando archivo PDF actualizado con URL estable...")
            
            # Validar tipo y tamaño del archivo
            if not r2_storage.validate_file_type(file_name, ALLOWED_FILE_TYPES['CV']):
                raise Exception("Tipo de archivo no permitido para CV")
            
            if not r2_storage.validate_file_size(len(file_data), FILE_SIZE_LIMITS['CV']):
                raise Exception(f"Archivo demasiado grande. Máximo {FILE_SIZE_LIMITS['CV']}MB")
            
            # Subir archivo sobrescribiendo usando clave estable (sin borrar)
            upload_start = time.time()
            print("📤 Sobrescribiendo archivo PDF en R2 con URL estable...")
            
            # Generar nombre bonito si hay datos del CV
            pretty_filename = file_name
            if cv_data:
                pretty_filename = r2_storage.generate_pretty_cv_filename(cv_data)
            
            # Generar clave estable y subir
            stable_key = r2_storage.generate_stable_cv_key(cv_id)
            file_url = await r2_storage.upload_file_to_r2(
                file_data=file_data,
                file_name=pretty_filename,
                content_type="application/pdf",
                stable_key=stable_key  # Usar clave estable
            )
            upload_time = time.time() - upload_start
            timing_stats["r2_upload"] = upload_time
            print(f"   ⏱️ Sobrescritura de archivo: {upload_time:.4f}s")
            print(f"   🔗 URL estable del archivo: {file_url}")
            
            r2_time = time.time() - r2_start
            timing_stats["r2_total"] = r2_time
            print(f"   ⏱️ Tiempo total R2: {r2_time:.4f}s")
            
            # Agregar fileUrl al payload de actualización
            update_payload["fileUrl"] = file_url

        # 2) Generar embeddings si no los tiene O si el data ha cambiado
        should_generate_embeddings = not has_embeddings or data_changed
        
        if should_generate_embeddings:
            if not has_embeddings:
                print(f"   🔍 CV no tiene embeddings, generando...")
            else:
                print(f"   🔄 Data ha cambiado, regenerando embeddings...")
            
            emb_start = time.time()
            cv_text = json.dumps(cv_data, ensure_ascii=False)
            embeddings = await generate_cv_embeddings(cv_text)
            emb_time = time.time() - emb_start
            timing_stats["embeddings_generation"] = emb_time
            if not embeddings:
                raise Exception("No se pudieron generar los embeddings del CV")
            print(f"   ⏱️ Embeddings generados en {emb_time:.4f}s")
            
            update_payload["embeddings"] = embeddings
        else:
            print(f"   ✅ CV ya tiene embeddings y data no cambió, saltando generación")
            timing_stats["embeddings_generation"] = 0.0

        # 3) Verificar si necesitamos migrar a URL estable (compatibilidad hacia atrás)
        current_file_url = current_cv.get("fileUrl")
        should_migrate_to_stable_url = False
        
        if current_file_url and not data_changed:
            # Verificar si la URL actual NO es estable (no sigue el formato cv/{cv_id}.pdf)
            expected_stable_url = r2_storage.generate_stable_cv_url(cv_id)
            if current_file_url != expected_stable_url:
                should_migrate_to_stable_url = True
                print(f"   🔄 Detectada URL no estable, migrando a URL estable...")
                print(f"      URL actual: {current_file_url}")
                print(f"      URL estable: {expected_stable_url}")
        
        # 4) Si el data cambió O necesitamos migrar a URL estable, generar/actualizar PDF
        if data_changed or should_migrate_to_stable_url:
            if data_changed:
                print(f"   📄 Data cambió, generando nuevo PDF con URL estable...")
            else:
                print(f"   📄 Migrando a URL estable, regenerando PDF...")
            pdf_start = time.time()
            
            try:
                # Importar el generador de PDF
                from services.pdf_generator_service import CVPDFGenerator
                
                # Generar PDF a partir del cvData
                pdf_content, pdf_file_name = CVPDFGenerator.generate_pdf_from_cv_data(cv_data)
                
                # Generar nombre bonito para descarga
                pretty_filename = r2_storage.generate_pretty_cv_filename(cv_data)
                
                # Subir nuevo PDF a R2 sobrescribiendo con clave estable
                upload_start = time.time()
                print("   📤 Sobrescribiendo PDF en R2 con URL estable...")
                
                stable_key = r2_storage.generate_stable_cv_key(cv_id)
                new_file_url = await r2_storage.upload_file_to_r2(
                    file_data=pdf_content,
                    file_name=pretty_filename,
                    content_type="application/pdf",
                    stable_key=stable_key  # Usar clave estable
                )
                upload_time = time.time() - upload_start
                timing_stats["r2_upload"] = upload_time
                print(f"      ⏱️ Sobrescritura de PDF: {upload_time:.4f}s")
                print(f"      🔗 URL estable del archivo: {new_file_url}")
                
                # Agregar fileUrl al payload de actualización
                update_payload["fileUrl"] = new_file_url
                file_url = new_file_url
                
                pdf_time = time.time() - pdf_start
                timing_stats["pdf_generation"] = pdf_time
                print(f"   ⏱️ Generación y subida de PDF: {pdf_time:.4f}s")
                
            except Exception as e:
                print(f"   ❌ Error generando PDF: {e}")
                # No fallar la actualización si el PDF falla, solo continuar
                timing_stats["pdf_generation"] = 0.0

        # 5) Actualizar en la base de datos
        db_start = time.time()
        doc_ref.update(update_payload)
        db_time = time.time() - db_start
        timing_stats["database_update"] = db_time
        print(f"   💾 Actualizado en {db_time:.4f}s")

        total_time = time.time() - total_start_time
        timing_stats["total_time"] = total_time
        return {
            "success": True,
            "cv_id": cv_id,
            "updated_fields": list(update_payload.keys()),
            "embeddings_generated": should_generate_embeddings,
            "data_changed": data_changed,
            "pdf_generated": data_changed,  # Si el data cambió, se generó PDF
            "file_url": file_url,  # Incluir URL del archivo si se subió
            "timing_stats": timing_stats,
        }

    except Exception as e:
        total_time = time.time() - total_start_time
        print(f"❌ Error al actualizar CV después de {total_time:.4f}s: {e}")
        raise


async def delete_cv(cv_id: str) -> Dict[str, Any]:
    """
    Elimina un CV por ID. Si era el seleccionado en 'user.cvSelectedId', intenta
    reasignar al CV más reciente del usuario o lo limpia si no hay más.

    Args:
        cv_id: ID del documento de CV en Firestore

    Returns:
        Dict con el resultado de la operación y ajustes en 'users' si aplica
    """
    start_time = time.time()

    try:
        if not cv_id:
            raise ValueError("cv_id es requerido")

        print(f"🗑️ Eliminando CV {cv_id}...")
        doc_ref = db_users.collection("userCVs").document(cv_id)
        snap = doc_ref.get()
        if not snap.exists:
            raise ValueError("El CV especificado no existe")

        cv_doc = snap.to_dict()
        user_id = cv_doc.get("userId")

        # Verificar si era el seleccionado del usuario ANTES de eliminar
        relinked_cv_id: Optional[str] = None
        user_data = {}
        was_selected_cv = False
        
        if user_id:
            user_doc_ref = db_users.collection("users").document(user_id)
            user_snap = user_doc_ref.get()
            if user_snap.exists:
                user_data = user_snap.to_dict() or {}
                was_selected_cv = user_data.get("cvSelectedId") == cv_id
                
                if was_selected_cv:
                    # Buscar otros CVs ANTES de eliminar el actual
                    other_cvs = db_users.collection("userCVs").where("userId", "==", user_id).get()
                    other_cvs_list = [doc for doc in other_cvs if doc.id != cv_id]  # Excluir el CV que vamos a eliminar
                    
                    if other_cvs_list:
                        # Ordenar por createdAt descendente
                        other_cvs_list.sort(key=lambda doc: doc.get("createdAt") or datetime.min, reverse=True)
                        relinked_cv_id = other_cvs_list[0].id
                        print(f"   🔗 Preparando reasignación a {relinked_cv_id}")
                    else:
                        print("   🔗 Preparando limpieza de cvSelectedId (será el último CV)")

        # Eliminar archivo de R2 si existe
        file_url = cv_doc.get("fileUrl")
        file_deleted = False
        if file_url:
            delete_start = time.time()
            print("🗑️ Eliminando archivo de R2...")
            
            try:
                # Extraer nombre del archivo de la URL
                file_name = r2_storage.extract_file_name_from_url(file_url)
                if file_name:
                    deleted = await r2_storage.delete_file_from_r2(file_name)
                    if deleted:
                        print(f"   ✅ Archivo eliminado de R2: {file_name}")
                        file_deleted = True
                    else:
                        print(f"   ℹ️ Archivo no existía en R2: {file_name}")
                else:
                    print(f"   ⚠️ No se pudo extraer nombre del archivo: {file_url}")
            except Exception as file_error:
                print(f"   ⚠️ Error al eliminar archivo de R2: {file_error}")
                # Continuar con la eliminación del CV aunque falle la eliminación del archivo
            
            delete_time = time.time() - delete_start
            print(f"   ⏱️ Eliminación de archivo: {delete_time:.4f}s")
        
        # Borrar el documento
        doc_ref.delete()
        print("   ✅ CV eliminado de la base de datos")

        # Actualizar cvSelectedId si era necesario
        if user_id and was_selected_cv:
            try:
                if relinked_cv_id:
                    user_doc_ref.update({
                        "cvSelectedId": relinked_cv_id,
                        "updatedAt": datetime.now(),
                    })
                    print(f"   🔗 'cvSelectedId' reasignado a {relinked_cv_id}")
                else:
                    user_doc_ref.update({
                        "cvSelectedId": None,
                        "updatedAt": datetime.now(),
                    })
                    print("   🔗 'cvSelectedId' limpiado (sin CVs restantes)")
            except Exception as update_error:
                print(f"   ⚠️ Error al actualizar cvSelectedId: {update_error}")
                # No fallar la operación principal por este error

        total_time = time.time() - start_time
        return {
            "success": True,
            "deleted_cv_id": cv_id,
            "user_id": user_id,
            "was_selected_cv": was_selected_cv,
            "relinked_cv_selected_id": relinked_cv_id,
            "file_deleted": file_deleted,
            "duration_seconds": round(total_time, 4),
        }

    except ValueError as e:
        total_time = time.time() - start_time
        print(f"❌ Error de validación al eliminar CV después de {total_time:.4f}s: {e}")
        raise
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ Error inesperado al eliminar CV después de {total_time:.4f}s: {e}")
        print(f"   Stack trace: {traceback.format_exc()}")
        raise


async def get_cv_by_id(cv_id: str) -> Dict[str, Any]:
    """
    Obtiene un CV por su ID desde la colección `userCVs`.
    Retorna el documento completo si existe.
    """
    try:
        if not cv_id:
            raise ValueError("cv_id es requerido")

        doc_ref = db_users.collection("userCVs").document(cv_id)
        snap = doc_ref.get()
        if not snap.exists:
            raise ValueError("El CV especificado no existe")

        data = snap.to_dict() or {}
        data["id"] = snap.id
        return data

    except Exception as e:
        print(f"❌ Error en get_cv_by_id: {e}")
        raise

async def adapt_cv_summary_for_job(original_cv: Dict[str, Any], job_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapta el resumen ejecutivo de un CV para una oferta laboral específica usando Gemini.
    
    Args:
        original_cv: CV original con todos sus datos
        job_context: Contexto de la oferta laboral con jobTitle, company, description
        
    Returns:
        Dict con el CV adaptado y metadatos del proceso
    """
    total_start_time = time.time()
    timing_stats = {}
    
    try:
        print(f"🚀 Iniciando adaptación de resumen ejecutivo para oferta: {job_context.get('jobTitle', 'N/A')}")
        print(f"   📄 CV original: {original_cv.get('title', 'Sin título')}")
        
        # 1. Construir el prompt de adaptación
        prompt_start = time.time()
        adaptation_prompt = build_adaptation_prompt(original_cv, job_context)
        prompt_time = time.time() - prompt_start
        timing_stats['prompt_preparation'] = prompt_time
        print(f"   ⏱️ Preparación del prompt: {prompt_time:.4f}s")
        
        # 2. Generar resumen adaptado con Gemini
        ai_start = time.time()
        print("🤖 Generando resumen adaptado con Gemini...")
        
        try:
            response = await llm.ainvoke(adaptation_prompt)
            adapted_summary = response.content.strip()
            
            # Limpiar la respuesta de posibles caracteres extra
            import re
            adapted_summary = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', adapted_summary)
            adapted_summary = re.sub(r'^["\']|["\']$', '', adapted_summary)  # Remover comillas si las hay
            
        except Exception as ai_error:
            print(f"❌ Error en la generación con Gemini: {ai_error}")
            raise Exception(f"Error al generar resumen adaptado: {str(ai_error)}")
        
        ai_time = time.time() - ai_start
        timing_stats['ai_generation'] = ai_time
        print(f"   ⏱️ Generación con IA: {ai_time:.4f}s")
        print(f"   📝 Resumen adaptado: {adapted_summary[:100]}...")
        
        # 3. Crear CV adaptado manteniendo embeddings originales
        cv_prep_start = time.time()
        
        # Crear copia del CV original
        adapted_cv = {
            **original_cv,
            "data": {
                **original_cv.get("data", {}),
                "personalInfo": {
                    **original_cv.get("data", {}).get("personalInfo", {}),
                    "summary": adapted_summary  # Solo actualizar el resumen
                }
            }
        }
        
        # Mantener los embeddings originales (no recalcular)
        adapted_cv["embeddings"] = original_cv.get("embeddings")
        
        # Generar nuevo PDF ya que el resumen cambió
        pdf_start = time.time()
        print("📄 Generando nuevo PDF con resumen adaptado...")
        
        try:
            from services.pdf_generator_service import CVPDFGenerator
            
            # Generar PDF a partir del cvData adaptado
            pdf_content, pdf_file_name = CVPDFGenerator.generate_pdf_from_cv_data(adapted_cv["data"])
            
            # Generar CV ID para el nuevo CV adaptado
            adapted_cv_id = db_users.collection("userCVs").document().id
            
            # Generar nombre bonito para descarga
            pretty_filename = r2_storage.generate_pretty_cv_filename(adapted_cv["data"])
            
            # Subir nuevo PDF a R2 con URL estable
            stable_key = r2_storage.generate_stable_cv_key(adapted_cv_id)
            new_file_url = await r2_storage.upload_file_to_r2(
                file_data=pdf_content,
                file_name=pretty_filename,
                content_type="application/pdf",
                stable_key=stable_key  # Usar clave estable
            )
            
            # Actualizar fileUrl en el CV adaptado
            adapted_cv["fileUrl"] = new_file_url
            
            pdf_time = time.time() - pdf_start
            timing_stats['pdf_generation'] = pdf_time
            print(f"   ⏱️ Generación y subida de PDF: {pdf_time:.4f}s")
            print(f"   🔗 URL del nuevo PDF: {new_file_url}")
            
        except Exception as pdf_error:
            print(f"   ⚠️ Error generando PDF (continuando sin fileUrl): {pdf_error}")
            # No fallar el proceso completo, continuar sin fileUrl
            adapted_cv["fileUrl"] = None
            timing_stats['pdf_generation'] = 0.0
        
        cv_prep_time = time.time() - cv_prep_start
        timing_stats['cv_preparation'] = cv_prep_time
        print(f"   ⏱️ Preparación del CV adaptado: {cv_prep_time:.4f}s")
        
        # 4. Guardar CV adaptado en la base de datos
        db_start = time.time()
        print("💾 Guardando CV adaptado en la base de datos...")
        
        # Preparar documento para Firestore
        now = datetime.now()
        adapted_cv["createdAt"] = now
        adapted_cv["updatedAt"] = now
        adapted_cv["title"] = f"CV adaptado - {job_context.get('jobTitle', 'Oferta')}"
        adapted_cv["template"] = original_cv.get("template", "harvard")
        adapted_cv["userId"] = original_cv.get("userId")
        
        # Remover campos que no deben ir a la base de datos
        adapted_cv.pop("id", None)  # No incluir el ID del CV original
        
        # Guardar en Firestore usando el ID ya generado
        doc_ref = db_users.collection("userCVs").document(adapted_cv_id)
        doc_ref.set(adapted_cv)
        
        db_time = time.time() - db_start
        timing_stats['database_save'] = db_time
        print(f"   ⏱️ Guardado en base de datos: {db_time:.4f}s")
        print(f"   🆔 ID del CV adaptado: {doc_ref.id}")
        
        # 5. Preparar respuesta
        response_start = time.time()
        
        total_time = time.time() - total_start_time
        timing_stats['total_time'] = total_time
        
        response = {
            "success": True,
            "adapted_cv_id": doc_ref.id
        }
        
        response_time = time.time() - response_start
        timing_stats['response_preparation'] = response_time
        
        print(f"✅ CV adaptado exitosamente con ID: {doc_ref.id}")
        print(f"🎯 TIEMPO TOTAL: {total_time:.4f}s")
        print(f"📊 ESTADÍSTICAS DE TIEMPO:")
        print(f"   - Preparación prompt: {timing_stats['prompt_preparation']:.4f}s")
        print(f"   - Generación IA: {timing_stats['ai_generation']:.4f}s")
        print(f"   - Preparación CV: {timing_stats['cv_preparation']:.4f}s")
        print(f"   - Generación PDF: {timing_stats['pdf_generation']:.4f}s")
        print(f"   - Guardado BD: {timing_stats['database_save']:.4f}s")
        print(f"   - Preparación respuesta: {timing_stats['response_preparation']:.4f}s")
        print(f"   - 🎆 TOTAL: {timing_stats['total_time']:.4f}s")
        
        return response
        
    except Exception as e:
        total_time = time.time() - total_start_time
        print(f"❌ Error al adaptar CV después de {total_time:.4f}s: {e}")
        raise Exception(f"Error al adaptar CV: {str(e)}")


def build_adaptation_prompt(original_cv: Dict[str, Any], job_context: Dict[str, Any]) -> str:
    """
    Construye el prompt para adaptar el resumen ejecutivo de un CV.
    
    Args:
        original_cv: CV original con todos sus datos
        job_context: Contexto de la oferta laboral
        
    Returns:
        str: Prompt formateado para Gemini
    """
    # Extraer información del CV
    cv_data = original_cv.get("data", {})
    personal_info = cv_data.get("personalInfo", {})
    work_experience = cv_data.get("workExperience", [])
    skills = cv_data.get("skills", [])
    education = cv_data.get("education", [])
    
    # Construir el prompt
    prompt = f"""
GENERA UN RESUMEN EJECUTIVO SUTIL Y NATURAL

CONTEXTO DEL PUESTO:
- Título: {job_context.get('jobTitle', 'No especificado')}
- Empresa: {job_context.get('company', 'No especificada')}
- Descripción: {job_context.get('description', 'No disponible')}

INFORMACIÓN DEL CV:
- Resumen actual: {personal_info.get('summary', 'No tiene resumen')}
- Experiencia laboral: {len(work_experience)} posiciones
- Habilidades principales: {', '.join([s.get('name', '') for s in skills[:5]]) if skills else 'No especificadas'}
- Educación: {', '.join([e.get('degree', '') for e in education]) if education else 'No especificada'}

INSTRUCCIONES CRÍTICAS:
Genera un resumen ejecutivo (2-3 líneas) que sea:
1. NATURAL Y SUTIL: No menciones explícitamente el puesto, empresa o que estás "aplicando"
2. ENFOQUE EN HABILIDADES: Destaca las habilidades del CV que son más relevantes para este tipo de posición
3. EXPERIENCIA REAL: Solo menciona experiencia y logros que estén realmente en el CV
4. LENGUAJE PROFESIONAL: Usa un tono profesional pero no excesivamente formal
5. CONCISO: Máximo 3 líneas, enfocado en lo más importante

REGLAS IMPORTANTES:
- NO menciones la empresa objetivo
- NO seas descarado o obvio en la adaptación
- Solo destaca lo que YA TIENES que sea relevante para este tipo de posición

FORMATO DE SALIDA:
Responde ÚNICAMENTE con el texto del resumen ejecutivo, sin comillas ni formato adicional.

Ejemplo de salida sutil:
Desarrollador con experiencia en múltiples tecnologías web y automatización de procesos. He trabajado en proyectos que optimizaron flujos de trabajo y desarrollé soluciones que mejoraron la eficiencia operacional. Conocimientos sólidos en desarrollo de aplicaciones y integración de sistemas.
"""
    
    return prompt