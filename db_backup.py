import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("jobs-update-e3e63-firebase-adminsdk-fbsvc-4ff0cc214d.json")
firebase_admin.initialize_app(cred)

db = firestore.client()
