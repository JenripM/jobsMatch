from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from schemas import Match, PromptRequest
from models import obtener_practicas, obtener_practicas_recientes, obtener_respuesta_chatgpt, obtener_texto_pdf_de_url, comparar_practicas_con_cv

app = FastAPI()

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir solicitudes de cualquier origen, ajusta según sea necesario
    allow_credentials=True,
    allow_methods=["*"],  # Permitir todos los métodos HTTP
    allow_headers=["*"],  # Permitir todos los encabezados
)

@app.post("/match-practices")
async def match_practices(match: Match):
    # Obtener el texto del CV a partir de la URL
    cv_texto = obtener_texto_pdf_de_url(match.cv_url)

    if "Error" in cv_texto:
        return {"error": cv_texto}  # Si hubo un error en la lectura del PDF

    # Obtener las prácticas recientes
    practicas = obtener_practicas_recientes()

    # Comparar las prácticas con el CV extraído
    practicas_con_similitud = comparar_practicas_con_cv(cv_texto, practicas, match.puesto)

    return {"practicas": practicas_con_similitud}

@app.get("/practicas")
def get_practicas():
    return obtener_practicas()

@app.get("/practicas-recientes")
def get_practicas():
    return obtener_practicas_recientes()

@app.post("/chatgpt")
async def chatgpt_response(request: PromptRequest):
    respuesta = obtener_respuesta_chatgpt(request.prompt)
    return {"respuesta": respuesta}
