import asyncio
from services.job_metadata_service import generate_metadata_for_collection
from services.embedding_service import generate_embeddings_for_collection

# --- Configuración del Pipeline ---
COLLECTION_NAME = "practicas_embeddings_test"
OVERWRITE_METADATA = False  # Cambiar a True para sobrescribir metadatos existentes
OVERWRITE_EMBEDDINGS = False  # Cambiar a True para sobrescribir embeddings existentes

if __name__ == "__main__":
    print("🚀 Pipeline de procesamiento de ofertas laborales")
    print(f"📁 Colección: {COLLECTION_NAME}")
    print(f"🔄 Sobrescribir metadatos: {OVERWRITE_METADATA}")
    print(f"🔄 Sobrescribir embeddings: {OVERWRITE_EMBEDDINGS}")
    print("=" * 50)
    
    async def run_pipeline():
        try:
            # Paso 1: Generar metadatos
            print("\n📝 PASO 1: Generando metadatos...")
            await generate_metadata_for_collection(
                collection_name=COLLECTION_NAME,
                overwrite_existing=OVERWRITE_METADATA
            )
            
            # Paso 2: Generar embeddings
            print("\n🧠 PASO 2: Generando embeddings...")
            generate_embeddings_for_collection(
                collection_name=COLLECTION_NAME,
                overwrite_existing=OVERWRITE_EMBEDDINGS
            )
            
            print("\n✅ Pipeline completado exitosamente!")
            
        except Exception as e:
            print(f"\n❌ Error en el pipeline: {e}")
            raise
    
    asyncio.run(run_pipeline())
