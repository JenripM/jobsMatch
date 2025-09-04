"""
Prompts para procesamiento de ofertas de empleo (Jobs)

Este módulo contiene los prompts utilizados para extraer metadatos
estructurados de descripciones de ofertas laborales.
"""

JOB_METADATA_PROMPT = """
Actúa como un extractor y clasificador de datos de ofertas de empleo. Recibirás el texto completo de una oferta laboral. Tu única tarea es analizar este texto y devolver un objeto JSON válido que contenga los metadatos de la oferta.

IMPORTANTE: Tu respuesta debe ser ÚNICAMENTE un objeto JSON válido, sin texto adicional, explicaciones, o caracteres extra. El JSON debe comenzar con {{ y terminar con }}.

El JSON de salida debe tener exactamente esta estructura:
{{
  "category": ["String"],
  "hard_skills": ["String"],
  "soft_skills": ["String"],
  "language_requirements": "String o null",
  "related_degrees": ["String"],
  "required_competencies": ["String"],
  "target_field": "String"
}}

Instrucciones para inferir cada campo:

- Sé extremadamente estricto con el formato de los valores. Para los nombres de carreras y títulos, usa SIEMPRE el nombre completo y formal, con mayúscula inicial en cada palabra, sin abreviaturas, diminutivos ni sinónimos. Ejemplo correcto: "Ingeniería Industrial". Ejemplo incorrecto: "Ing. Industrial", "ing. industrial", "Industrial Engineering".
- Usa este mismo criterio de formato para cualquier campo de tipo lista de nombres o títulos.
- No inventes información. Solo incluye datos que estén textualmente presentes en el texto o que sean evidentemente obvios según el contexto. Si no es explícito ni obvio, deja el campo vacío o null según corresponda.
- Si tienes dudas, prefiere ser conservador y omitir información dudosa.
- NO incluyas explicaciones, NO incluyas texto adicional, SOLO el objeto JSON.

1. category: Debes inferir la(s) categoría(s) del puesto basándote en el título y la descripción. El resultado debe ser una lista de cadenas. Idealmente, escoge la categoría principal. Si el puesto abarca claramente dos áreas, puedes seleccionar un máximo de dos categorías de la siguiente lista. No uses ningún valor fuera de esta lista.
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

3. soft_skills: Infiere las habilidades interpersonales o blandas basándote en las funciones y responsabilidades. Busca habilidades como Coordinación, Organización, Comunicación, Liderazgo, Atención al detalle, Resolución de problemas. El resultado debe ser una lista de cadenas.

4. language_requirements: Busca cualquier mención de idiomas requeridos. Si la oferta pide un idioma, extrae el idioma y el nivel (ej: "Inglés Avanzado"). Si no se menciona ningún idioma, el valor debe ser null (sin comillas). El resultado debe ser una cadena o el valor null.

5. related_degrees: Identifica las carreras o campos de estudio mencionados en la sección de "Requisitos" (ej: "Administración, Negocios Internacionales, Ingeniería Industrial, Economía y afines."). Enumera cada una de estas carreras en una lista de cadenas. Usa siempre el nombre largo y formal (por ejemplo, "Ingeniería Industrial").

6. required_competencies: Extrae las competencias técnicas clave requeridas para este puesto. Incluye SOLO habilidades técnicas, herramientas, metodologías, software, certificaciones y conocimientos especializados (NO soft skills). Las competencias deben ser máximo 2 palabras cada una. IMPORTANTE: Devuelve TODAS las competencias en ESPAÑOL, independientemente del idioma de la oferta. Siempre verifica si se mencionan habilidades de "Inglés" como competencia clave. Ejemplos: "Photoshop", "Excel", "SAP", "Marketing Digital", "Gestión de Proyectos", "JavaScript", "Inglés".

7. target_field: Analiza la oferta y selecciona el campo de estudio MÁS RELEVANTE de la siguiente lista. Devuelve SOLO el nombre del campo más apropiado, sin texto adicional. Selecciona únicamente 1 campo que mejor coincida con los requisitos del puesto.
   Campos disponibles: Programming, Networks_Telecommunications, Civil_Engineering, Mechanical_Engineering, Electrical_Engineering, Chemical_Engineering, Industrial_Engineering, Textile_Engineering, Medicine, Dentistry, Psychology, Nursing, Veterinary, Business_Administration, Economics, Accounting, Marketing, Finance, Human_Resources, Law, Education, Social_Work, Mathematics, Physics, Chemistry, Biology, Architecture, Design, Communications, International_Relations, Tourism

CRÍTICO: Tu respuesta debe ser SOLO el objeto JSON, sin ningún texto antes o después. El JSON debe ser sintácticamente válido y comenzar exactamente con {{.

{format_instructions}

Título de la oferta: {title}
Descripción de la oferta: {description}
"""


