"""
Prompts para procesamiento de CVs

Este módulo contiene todos los prompts utilizados para:
- Extracción de datos estructurados del CV
- Extracción de metadatos del usuario
"""

# =============================
# PROMPT PARA EXTRACCIÓN DE DATOS ESTRUCTURADOS DEL CV
# =============================

CV_FIELDS_INFERENCE_PROMPT = """
Actúa como un analizador y estructurador de datos de currículums. Recibirás el texto completo de un currículum. Tu tarea es analizar este texto e inferir todos los campos y secciones del CV organizados según el formato especificado.

El JSON de salida debe tener esta estructura exacta:
{{
  "personalInfo": {{
    "fullName": "string",
    "email": "string", 
    "phone": "string",
    "address": "string",
    "linkedIn": "string (vacío si no hay)",
    "website": "string (vacío si no hay)",
    "summary": "string"
  }},
  "education": [
    {{
      "id": "string único",
      "institution": "string",
      "degree": "string",
      "fieldOfStudy": "string (vacío si no hay)",
      "startDate": "string (formato: YYYY-MM)",
      "endDate": "string (formato: YYYY-MM)",
      "current": boolean,
      "gpa": "string (vacío si no hay)",
      "honors": "string (vacío si no hay)",
      "relevantCourses": ["string"] (array vacío si no hay),
      "achievements": ["string"] (array vacío si no hay),
      "location": "string (vacío si no hay)"
    }}
  ],
  "workExperience": [
    {{
      "id": "string único",
      "company": "string",
      "position": "string",
      "startDate": "string (formato: YYYY-MM)",
      "endDate": "string (formato: YYYY-MM)",
      "current": boolean,
      "location": "string (vacío si no hay)",
      "description": "string (vacío si no hay)",
      "achievements": ["string"],
      "technologies": ["string"] (array vacío si no hay),
      "responsibilities": ["string"] (array vacío si no hay),
      "projects": ["string"] (array vacío si no hay),
      "sections": [
        {{
          "title": "string",
          "achievements": ["string"]
        }}
      ] (array vacío si no hay)
    }}
  ],
  "skills": [
    {{
      "id": "string único",
      "name": "string",
      "level": "Básico|Intermedio|Avanzado|Proficiente (vacío si no se puede inferir)",
      "category": "Technical|Analytical|Leadership|Communication|Research|Language",
      "proficiency": número (0 si no hay),
      "certifications": ["string"] (array vacío si no hay)
    }}
  ],
  "projects": [
    {{
      "id": "string único",
      "name": "string",
      "description": "string",
      "technologies": "string",
      "startDate": "string (formato: YYYY-MM)",
      "endDate": "string (formato: YYYY-MM)",
      "current": boolean,
      "url": "string (vacío si no hay)",
      "highlights": ["string"],
      "role": "string (vacío si no hay)",
      "teamSize": número (0 si no hay),
      "methodology": "string (vacío si no hay)"
    }}
  ],
  "certifications": [
    {{
      "id": "string único",
      "name": "string",
      "issuer": "string",
      "date": "string (formato: YYYY-MM)",
      "expiryDate": "string (vacío si no hay)",
      "credentialId": "string (vacío si no hay)",
      "url": "string (vacío si no hay)",
      "score": "string (vacío si no hay)",
      "description": "string (vacío si no hay)"
    }}
  ],
  "volunteer": [
    {{
      "id": "string único",
      "organization": "string",
      "position": "string",
      "startDate": "string (formato: YYYY-MM)",
      "endDate": "string (formato: YYYY-MM)",
      "currentlyVolunteering": boolean,
      "description": "string",
      "skills": ["string"],
      "impact": "string (vacío si no hay)",
      "location": "string (vacío si no hay)"
    }}
  ],
  "languages": [
    {{
      "id": "string único",
      "language": "string",
      "proficiency": "Básico|Intermedio|Intermedio-Avanzado|Avanzado|Proficiente|Nativo",
      "certifications": ["string"] (array vacío si no hay),
      "writingLevel": "string (vacío si no hay)",
      "speakingLevel": "string (vacío si no hay)"
    }}
  ] o null,
  "references": [
    {{
      "id": "string único",
      "name": "string",
      "position": "string",
      "company": "string",
      "email": "string",
      "phone": "string",
      "relationship": "string (vacío si no hay)",
      "yearsKnown": número (0 si no hay),
      "preferredContact": "email|phone (vacío si no hay)"
    }}
  ] (array vacío si no hay),
  "hobbies": ["string"] (array vacío si no hay)
}}

Instrucciones importantes:
1. Genera IDs únicos para cada elemento (puedes usar formatos como "edu_1", "work_1", "skill_1", etc.)
2. Para las fechas, usa el formato YYYY-MM. Si solo hay año, usa YYYY-01
3. No inventes información. Solo incluye datos que estén textualmente presentes en el CV
4. Para campos opcionales de texto, usa string vacío ("") en lugar de null si no hay información
5. Para campos opcionales de lista, usa array vacío ([]) en lugar de null si no hay información
6. Para campos opcionales numéricos, usa 0 en lugar de null si no hay información
7. Para los niveles de habilidad, infiere basándote en el contexto y experiencia mencionada
8. Sé consistente con el formato de fechas y la estructura de datos
9. No incluyas explicaciones, solo el objeto JSON

Texto del CV:
{cv_text}

{format_instructions}
"""

# =============================
# PROMPT PARA EXTRACCIÓN DE METADATOS DEL USUARIO
# =============================

CV_METADATA_INFERENCE_PROMPT = """
Actúa como un analizador y clasificador de currículums. Recibirás el texto completo de un currículum de un postulante. Tu única tarea es analizar este texto e inferir los metadatos de las habilidades y experiencia del candidato basándote en el contenido del CV. No incluyas ningún otro campo, solo el objeto de metadatos.

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
