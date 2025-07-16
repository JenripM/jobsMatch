import firebase_admin
from firebase_admin import credentials, firestore
import os

# Usar el archivo de credenciales correcto
cred_path = "jobs-update-e3e63-firebase-adminsdk-fbsvc-4ff0cc214d.json"
print(f"🔍 Buscando archivo Firebase en: {os.path.abspath(cred_path)}")
print(f"📁 Archivo existe: {os.path.exists(cred_path)}")

if os.path.exists(cred_path):
    print("✅ Usando firebase-credentials.json")
    cred = credentials.Certificate(cred_path)
else:
    print("❌ Archivo firebase-credentials.json no encontrado")
    raise FileNotFoundError(f"No se encontró el archivo de credenciales de Firebase en: {os.path.abspath(cred_path)}")

firebase_admin.initialize_app(cred)
db = firestore.client()
