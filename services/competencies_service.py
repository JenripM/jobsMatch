"""
Servicio de Competencias - Extracción de competencias de CVs usando IA

Este servicio se encarga de:
- Extraer competencias/keywords de un CV usando IA
- Actualizar el campo 'competencies' en la colección 'users'
- Solo actualizar si las nuevas competencias son más largas que las existentes
"""

import asyncio
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from langchain_google_vertexai import ChatVertexAI

# Importar la base de datos
from db import db_users

# Configurar cliente de Gemini (coherente con el resto de la app)
llm = ChatVertexAI(
    model="gemini-2.5-flash-lite",
    temperature=0,
    max_tokens=None,
    max_retries=6,
    stop=None,
)

async def extract_competencies_from_cv(cv_data: Dict[str, Any]) -> List[str]:
    """
    Extrae competencias/keywords de un CV usando IA
    
    Args:
        cv_data: Datos estructurados del CV
        
    Returns:
        Lista de competencias extraídas
    """
    try:
        print(f"🤖 Extrayendo competencias del CV...")
        
        # Convertir cv_data a texto para el prompt
        cv_text = json.dumps(cv_data, ensure_ascii=False, indent=2)
        
        # Llamar a Gemini (coherente con el resto de la app)
        prompt = f"""Extract key professional competencies from this CV. 
        Return ONLY keywords separated by commas, no numbering or additional formatting.
        Include ONLY technical skills, tools, methodologies, software, certifications, and specialized knowledge (NO soft skills).
        Keywords should be maximum 2 words each.
        IMPORTANT: Return ALL competencies in SPANISH, regardless of the CV language.
        Always check for "Inglés" as a key competency if English skills are mentioned.
        Examples: "Photoshop", "Excel", "SAP", "Marketing Digital", "Gestión de Proyectos", "JavaScript", "Inglés".
        
        CV: {cv_text}
        
        Competencias:"""
        
        response = await llm.ainvoke(prompt)
        
        # Procesar respuesta
        competencies_text = response.content.strip()
        competencies = [item.strip() for item in competencies_text.split(",") if item.strip()]
        
        print(f"   ✅ Competencias extraídas: {len(competencies)}")
        print(f"   📝 Competencias: {', '.join(competencies[:5])}{'...' if len(competencies) > 5 else ''}")
        
        return competencies
        
    except Exception as e:
        print(f"❌ Error extrayendo competencias: {e}")
        return []

async def update_user_competencies(user_id: str, new_competencies: List[str]) -> bool:
    """
    Actualiza las competencias del usuario en la colección 'users'
    Solo actualiza si las nuevas competencias son más largas que las existentes
    
    Args:
        user_id: ID del usuario
        new_competencies: Lista de nuevas competencias
        
    Returns:
        True si se actualizó, False si no
    """
    try:
        if not new_competencies:
            print(f"   ⚠️ No hay competencias para actualizar")
            return False
            
        print(f"🔄 Actualizando competencias para usuario {user_id}...")
        
        # Obtener documento del usuario
        user_doc_ref = db_users.collection("users").document(user_id)
        user_doc = user_doc_ref.get()
        
        if not user_doc.exists:
            print(f"   ⚠️ Usuario {user_id} no existe, creando documento...")
            # Crear documento del usuario
            user_doc_ref.set({
                "id": user_id,
                "competencies": new_competencies,
                "createdAt": datetime.now(),
                "updatedAt": datetime.now()
            })
            print(f"   ✅ Usuario creado con {len(new_competencies)} competencias")
            return True
        
        # Obtener competencias existentes
        user_data = user_doc.to_dict() or {}
        existing_competencies = user_data.get("competencies", [])
        
        print(f"   📊 Competencias existentes: {len(existing_competencies)}")
        print(f"   📊 Competencias nuevas: {len(new_competencies)}")
        
        # Solo actualizar si las nuevas competencias son más largas
        if len(new_competencies) > len(existing_competencies):
            user_doc_ref.update({
                "competencies": new_competencies,
                "updatedAt": datetime.now()
            })
            print(f"   ✅ Competencias actualizadas: {len(new_competencies)} (anterior: {len(existing_competencies)})")
            return True
        else:
            print(f"   ⏭️ Competencias no actualizadas: {len(new_competencies)} <= {len(existing_competencies)}")
            return False
            
    except Exception as e:
        print(f"❌ Error actualizando competencias: {e}")
        return False

async def process_cv_competencies_async(user_id: str, cv_data: Dict[str, Any]) -> None:
    """
    Procesa las competencias de un CV de forma asíncrona
    Esta función se ejecuta en paralelo sin bloquear la respuesta del endpoint
    
    Args:
        user_id: ID del usuario
        cv_data: Datos estructurados del CV
    """
    try:
        print(f"🚀 Iniciando procesamiento asíncrono de competencias para usuario {user_id}")
        
        # Extraer competencias
        competencies = await extract_competencies_from_cv(cv_data)
        
        if competencies:
            # Actualizar en la base de datos
            updated = await update_user_competencies(user_id, competencies)
            if updated:
                print(f"✅ Competencias procesadas exitosamente para usuario {user_id}")
            else:
                print(f"ℹ️ Competencias no actualizadas para usuario {user_id} (menos competencias)")
        else:
            print(f"⚠️ No se pudieron extraer competencias para usuario {user_id}")
            
    except Exception as e:
        print(f"❌ Error en procesamiento asíncrono de competencias: {e}")

def start_competencies_processing(user_id: str, cv_data: Dict[str, Any]) -> None:
    """
    Inicia el procesamiento de competencias en paralelo
    Esta función no es async para poder ser llamada desde funciones síncronas
    
    Args:
        user_id: ID del usuario
        cv_data: Datos estructurados del CV
    """
    try:
        # Crear tarea asíncrona
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Si ya hay un loop corriendo, crear una tarea
            asyncio.create_task(process_cv_competencies_async(user_id, cv_data))
        else:
            # Si no hay loop, ejecutar directamente
            asyncio.run(process_cv_competencies_async(user_id, cv_data))
            
    except Exception as e:
        print(f"❌ Error iniciando procesamiento de competencias: {e}")
