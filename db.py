import os
import firebase_admin
from firebase_admin import credentials, firestore
import vertexai
from google.auth.exceptions import GoogleAuthError

# --- Configuración y logs de autenticación para Firebase ---
# La ruta del archivo de credenciales de Firebase.
cred_path = "jobs-update-e3e63-firebase-adminsdk-fbsvc-4ff0cc214d.json"

print("--- Verificando credenciales de Firebase ---")
print(f"🔍 Buscando archivo Firebase en: {os.path.abspath(cred_path)}")
print(f"📁 Archivo existe: {os.path.exists(cred_path)}")

if os.path.exists(cred_path):
    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Conexión con Firebase exitosa.")
    except Exception as e:
        print(f"❌ Error al inicializar Firebase: {e}")
        raise
else:
    print("❌ Archivo de credenciales de Firebase no encontrado.")
    raise FileNotFoundError(f"No se encontró el archivo de credenciales de Firebase en: {os.path.abspath(cred_path)}")

print("-" * 50)


# --- Configuración y logs de autenticación para Vertex AI ---
print("--- Verificando credenciales de Vertex AI ---")

# La librería de Vertex AI usa la variable de entorno GOOGLE_APPLICATION_CREDENTIALS
# para encontrar las credenciales. Es crucial que esta variable esté configurada
# correctamente en Render y apunte a la ruta del archivo.
print(f"Variable de entorno GOOGLE_APPLICATION_CREDENTIALS: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")

try:
    # Se recomienda usar las variables de entorno de tu proyecto de GCP
    # Aquí se inicializa la API de Vertex AI. La librería buscará las credenciales
    # automáticamente en la ruta especificada por GOOGLE_APPLICATION_CREDENTIALS.
    vertexai.init(project="jobs-update-e3e63", location="us-central1")
    print("✅ Conexión con Vertex AI exitosa.")

except GoogleAuthError as e:
    print(f"❌ Error de autenticación de Google Cloud (Vertex AI): {e}")
    print("Por favor, asegúrate de que la variable de entorno GOOGLE_APPLICATION_CREDENTIALS está configurada correctamente en Render y apunta al archivo JSON de credenciales.")
    raise
except Exception as e:
    print(f"❌ Error inesperado al inicializar Vertex AI: {e}")
    raise

print("-" * 50)