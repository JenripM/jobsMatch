import os
import firebase_admin
from firebase_admin import credentials, firestore
import vertexai
from google.auth.exceptions import GoogleAuthError

# --- Configuración y logs de autenticación para Firebase ---
print("--- Verificando credenciales de Firebase ---")

# Rutas de los archivos de credenciales
jobs_cred_path = "firebase_jobs_credentials.json"
users_cred_path = "firebase_users_credentials.json"

# Inicializar la aplicación para 'jobs'
if os.path.exists(jobs_cred_path):
    try:
        cred_jobs = credentials.Certificate(jobs_cred_path)
        app_jobs = firebase_admin.initialize_app(cred_jobs, name='jobs_app')
        db_jobs = firestore.client(app=app_jobs)
        print(f"✅ Conexión con Firebase 'jobs' exitosa. Path: {os.path.abspath(jobs_cred_path)}")
    except Exception as e:
        print(f"❌ Error al inicializar Firebase 'jobs': {e}")
        raise
else:
    print(f"❌ Archivo de credenciales de Firebase 'jobs' no encontrado en: {os.path.abspath(jobs_cred_path)}")
    raise FileNotFoundError(f"No se encontró el archivo de credenciales de Firebase 'jobs'.")

# Inicializar la aplicación para 'users'
if os.path.exists(users_cred_path):
    try:
        cred_users = credentials.Certificate(users_cred_path)
        app_users = firebase_admin.initialize_app(cred_users, name='users_app')
        db_users = firestore.client(app=app_users)
        print(f"✅ Conexión con Firebase 'users' exitosa. Path: {os.path.abspath(users_cred_path)}")
    except Exception as e:
        print(f"❌ Error al inicializar Firebase 'users': {e}")
        raise
else:
    print(f"❌ Archivo de credenciales de Firebase 'users' no encontrado en: {os.path.abspath(users_cred_path)}")
    raise FileNotFoundError(f"No se encontró el archivo de credenciales de Firebase 'users'.")

print("-" * 50)

# --- Configuración y logs de autenticación para Vertex AI ---
print("--- Verificando credenciales de Vertex AI ---")
print(f"Variable de entorno GOOGLE_APPLICATION_CREDENTIALS: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")

try:
    vertexai.init(project="jobs-update-e3e63", location="us-central1")
    print("✅ Conexión con Vertex AI exitosa.")
except GoogleAuthError as e:
    print(f"❌ Error de autenticación de Google Cloud (Vertex AI): {e}")
    print("Asegúrate de que la variable de entorno GOOGLE_APPLICATION_CREDENTIALS está configurada correctamente.")
    raise
except Exception as e:
    print(f"❌ Error inesperado al inicializar Vertex AI: {e}")
    raise

print("-" * 50)

# Ahora puedes usar db_jobs para el proyecto 'jobs' y db_users para el proyecto 'users'.
# No hay un único 'db' global.
# Ejemplo de uso:
# doc_ref_jobs = db_jobs.collection('coleccion_de_jobs').document('documento_ejemplo')
# doc_ref_users = db_users.collection('coleccion_de_users').document('documento_ejemplo')