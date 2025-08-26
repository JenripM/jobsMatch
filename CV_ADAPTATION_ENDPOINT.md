# Endpoint de Adaptación de CV - `/adapt-cv-summary`

## Descripción

Este endpoint permite adaptar el resumen ejecutivo de un CV para una oferta laboral específica usando IA (Gemini 2.5 Flash). El proceso mantiene todos los demás datos del CV original y solo modifica el resumen ejecutivo para que sea más relevante para el puesto objetivo.

## Características Principales

- **Adaptación Sutil**: Solo modifica el resumen ejecutivo, manteniendo la autenticidad del resto del CV
- **Reutilización de Embeddings**: Usa los embeddings originales del CV (no los recalcula)
- **Generación de PDF**: Crea automáticamente un nuevo PDF con el resumen adaptado
- **Almacenamiento en Firestore**: Guarda el CV adaptado como un nuevo documento
- **Medición de Tiempos**: Proporciona estadísticas detalladas de rendimiento

## Endpoint

```
POST /adapt-cv-summary
```

## Parámetros de Entrada

### Body (JSON)

```json
{
  "user_id": "string (requerido)",
  "cv_id": "string (requerido)",
  "job_context": {
    "jobTitle": "string (requerido)",
    "company": "string (opcional)",
    "description": "string (opcional)"
  }
}
```

### Parámetros

- **user_id**: ID del usuario propietario del CV
- **cv_id**: ID del CV específico a adaptar (requerido)
- **job_context**: Contexto de la oferta laboral
  - **jobTitle**: Título del puesto (requerido)
  - **company**: Nombre de la empresa (opcional)
  - **description**: Descripción del puesto (opcional)

## Respuesta

### Éxito (200)

```json
{
  "success": true,
  "adapted_cv_id": "string",
  "adapted_cv": {
    "id": "string",
    "title": "string",
    "summary": "string",
    "file_url": "string",
    "created_at": "string",
    "template": "string"
  },
  "job_context": {
    "job_title": "string",
    "company": "string",
    "description": "string"
  },
  "original_cv": {
    "id": "string",
    "title": "string",
    "summary": "string"
  },
  "timing_stats": {
    "prompt_preparation": 0.0012,
    "ai_generation": 2.3456,
    "cv_preparation": 0.0234,
    "pdf_generation": 1.2345,
    "database_save": 0.1234,
    "response_preparation": 0.0123,
    "total_time": 3.7394
  }
}
```

### Campos de Respuesta

- **adapted_cv_id**: ID del nuevo CV adaptado en Firestore
- **adapted_cv**: Información del CV adaptado
  - **id**: ID del documento
  - **title**: Título del CV adaptado
  - **summary**: Resumen ejecutivo adaptado
  - **file_url**: URL del PDF generado
  - **created_at**: Fecha de creación
  - **template**: Plantilla utilizada
- **job_context**: Contexto de la oferta laboral procesada
- **original_cv**: Información del CV original
- **timing_stats**: Estadísticas de tiempo por etapa

## Errores

### 400 - Bad Request
- `user_id es requerido`
- `cv_id es requerido`
- `job_context es requerido`
- `job_context.jobTitle es requerido`
- `El CV no tiene datos estructurados para adaptar`
- `El CV no tiene embeddings. Debe tener embeddings para poder adaptarlo`

### 403 - Forbidden
- `El CV no pertenece al usuario especificado`

### 404 - Not Found
- `CV no encontrado`

### 500 - Internal Server Error
- Errores internos del servidor

## Ejemplo de Uso

### Request

```bash
curl -X POST "http://localhost:8000/adapt-cv-summary" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "cv_id": "cv_original_456",
    "job_context": {
      "jobTitle": "Desarrollador Full Stack Senior",
      "company": "TechCorp",
      "description": "Buscamos un desarrollador experimentado en React, Node.js y bases de datos. Requisitos: 5+ años de experiencia, React, Node.js, MongoDB"
    }
  }'
```

### Response

```json
{
  "success": true,
  "adapted_cv_id": "uuid"
}
```

## Flujo de Procesamiento

1. **Validación**: Verifica que todos los parámetros requeridos están presentes
2. **Obtención del CV**: Recupera el CV específico por ID
3. **Verificación de Propiedad**: Confirma que el CV pertenece al usuario especificado
4. **Preparación del Prompt**: Construye el prompt para Gemini con el contexto del puesto
5. **Generación IA**: Usa Gemini 2.5 Flash para generar el resumen adaptado
6. **Preparación del CV**: Crea una copia del CV con el resumen adaptado
7. **Generación de PDF**: Crea un nuevo PDF con el resumen adaptado
8. **Almacenamiento**: Guarda el CV adaptado en Firestore
9. **Respuesta**: Retorna la información del CV adaptado

## Consideraciones Técnicas

- **Embeddings**: Se mantienen los embeddings originales del CV para preservar la funcionalidad de matching
- **PDF**: Se genera automáticamente un nuevo PDF con el resumen adaptado
- **Almacenamiento**: El CV adaptado se guarda como un nuevo documento en Firestore
- **Rendimiento**: El proceso completo típicamente toma entre 3-5 segundos
- **IA**: Utiliza Gemini 2.5 Flash para la generación del resumen adaptado

## Integración con Frontend

Este endpoint se puede usar desde el frontend para:

1. **Adaptación Automática**: Cuando un usuario ve una oferta laboral
2. **Previsualización**: Mostrar cómo se vería el CV adaptado antes de guardarlo
3. **Aplicación Directa**: Crear un CV adaptado para aplicar a una oferta específica
4. **Comparación**: Mostrar las diferencias entre el CV original y el adaptado

## Seguridad

- Verifica que el CV pertenece al usuario especificado
- Valida todos los parámetros de entrada
- Maneja errores de forma segura sin exponer información sensible
- Registra logs detallados para auditoría
