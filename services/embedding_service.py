import json
import sys
sys.path.append('..')
import asyncio

from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput
from db import db
from google.cloud.firestore_v1.vector import Vector

# --- Configuración Inicial ---
# Asegúrate de que 'db' sea una instancia de firestore.Client()
# Para que este script funcione, necesitas tener configuradas tus credenciales de Google Cloud.
# La forma más común para desarrollo local es:
# 1. Instalar Google Cloud CLI.
# 2. Autenticar: `gcloud auth application-default login`
# O configurar la variable de entorno GOOGLE_APPLICATION_CREDENTIALS apuntando a tu archivo JSON de clave de cuenta de servicio.

# --- Inicialización de Vertex AI (Necesario para los modelos más nuevos) ---
# Aquí asumimos que ya tienes las variables de entorno de tu proyecto configuradasfrom vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

# De lo contrario, descomenta y reemplaza con tu PROJECT_ID y la localización adecuada
# aiplatform.init(project='YOUR_PROJECT_ID', location='us-central1')

"""
recordar generar el índice vectorial en Firestore para la colección 'practicas_embeddings_test'. Solo es necesario una vez por collection, debera volverse a ejecutar si se muda de colección o cuenta gcp:
ejecutamos el siguiente codigo en GOOGLE SHELL!:
gcloud alpha firestore indexes composite create \
  --collection-group=practicas_embeddings_test \
  --query-scope=COLLECTION \
  --field-config='field-path=embedding,vector-config={"dimension": "2048", "flat": {}}' \
  --project=jobs-update-e3e63

"""

print("Cargando el modelo de embeddings 'gemini-embedding-001'...")
try:
    embedding_model = TextEmbeddingModel.from_pretrained("gemini-embedding-001")
    print("Modelo de embeddings cargado exitosamente.")
except Exception as e:
    print(f"Error al cargar el modelo de embeddings: {e}")
    print("Asegúrate de que la API de Vertex AI esté habilitada en tu proyecto de Google Cloud y que tus credenciales sean correctas.")
    exit()

from typing import List, Union

from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

async def get_embedding_from_text(text: str) -> Vector | None:
    """
    Genera un embedding para el texto dado con task='SEMANTIC_SIMILARITY' de forma asíncrona.
    Retorna un objeto Vector que puede guardarse directamente en Firestore.
    """
    if not text or not text.strip():
        print("⚠️ Texto vacío.")
        return None

    try:
        def sync_call():
            """Llamada sincrónica al modelo de embeddings."""
            input_data = [TextEmbeddingInput(text, task_type="SEMANTIC_SIMILARITY")]
            embedding_model = TextEmbeddingModel.from_pretrained("gemini-embedding-001")
            embeddings = embedding_model.get_embeddings(input_data, output_dimensionality=2048)
            if embeddings and len(embeddings) > 0:
                return Vector(embeddings[0].values)
            return None

        # Ejecutar en un hilo separado para no bloquear el loop
        return await asyncio.to_thread(sync_call)

    except Exception as e:
        print(f"❌ Error generando embedding: {e}")
        return None

def metadata_to_string(metadata: dict) -> str:
    """
    Convierte el objeto metadata a un string JSON formateado para embedding.
    
    Args:
        metadata: Diccionario completo con todos los campos incluyendo job_level
    
    Returns:
        String JSON con toda la información del metadata
    """
    if not metadata:
        return ""
    
    # Convertir a JSON string con formato compacto
    return json.dumps(metadata, ensure_ascii=False, separators=(',', ':'))


### Lógica principal

async def generate_embeddings_for_collection(collection_name=None, overwrite_existing=False):
    """
    Genera embeddings para todas las prácticas y los guarda en la colección de embeddings.
    
    Args:
        collection_name (str): Nombre de la colección de Firestore a procesar (REQUERIDO)
        overwrite_existing (bool): Si True, sobrescribe embeddings existentes. Por defecto False.
    """
    if not collection_name:
        raise ValueError("collection_name es requerido. Especifica el nombre de la colección de Firestore a procesar.")
    
    print(f"Iniciando generación de embeddings para colección '{collection_name}' (sobrescribir: {overwrite_existing})...")
    
    practicas_ref = db.collection(collection_name)
    embeddings_ref = db.collection(collection_name)  # Usar la misma colección

    try:
        practicas_docs = list(practicas_ref.stream())
        print(f"📝 {len(practicas_docs)} documentos encontrados.")
    except Exception as e:
        print(f"❌ Error leyendo colección: {e}")
        return

    batch = db.batch()
    batch_size = 10
    processed = 0
    skipped = 0

    for doc in practicas_docs:
        data = doc.to_dict()
        metadata = data.get("metadata")
        job_level = data.get("job_level")
        
        # Verificar si ya tiene embedding (solo saltar si no queremos sobrescribir)
        if not overwrite_existing and "embedding" in data and data["embedding"]:
            skipped += 1
            continue
        
        if not metadata:
            print(f"⚠️ Sin metadata para '{doc.id}', omitido.")
            continue

        # Crear metadata completo: combinar metadata original + job_level
        complete_metadata = metadata.copy()
        if job_level:
            complete_metadata["job_level"] = job_level
        
        # Convertir metadata completo a string JSON para embedding
        metadata_text = metadata_to_string(complete_metadata)
        if not metadata_text:
            print(f"⚠️ Metadata vacío para '{doc.id}', omitido.")
            continue

        print(f"📝 Procesando '{doc.id}': {metadata_text[:100]}...")

        # Generar embedding del metadata
        vector = await get_embedding_from_text(metadata_text)
        if not vector:
            print(f"⚠️ Embedding fallido para '{doc.id}', omitido.")
            continue

        # Actualizar documento con embedding y texto JSON
        update_data = {
            "embedding": vector
        }
        
        # Si es sobrescritura, actualizar solo los campos necesarios
        if overwrite_existing:
            batch.update(embeddings_ref.document(doc.id), update_data)
        else:
            # Si es nuevo, incluir todos los datos
            new_doc_data = {
                "embedding": vector,
                **data
            }
            batch.set(embeddings_ref.document(doc.id), new_doc_data)
        
        processed += 1

        if processed % batch_size == 0:
            print(f"📦 Enviando batch... (procesados: {processed}, saltados: {skipped})")
            batch.commit()
            batch = db.batch()

    if processed % batch_size != 0:
        print("📤 Enviando último batch...")
        batch.commit()

    print(f"✅ Proceso completado:")
    print(f"   - Documentos procesados: {processed}")
    print(f"   - Documentos saltados (ya tenían embedding): {skipped}")

# --- Punto de entrada principal para ejecutar el script ---
if __name__ == "__main__":
    asyncio.run(generate_embeddings_for_collection(collection_name="practicas_embeddings_test", overwrite_existing=False))
