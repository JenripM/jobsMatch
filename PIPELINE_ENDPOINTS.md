# Endpoints de Pipeline de Procesamiento de Ofertas Laborales

Este documento describe los nuevos endpoints que reemplazan la ejecución manual del script `process_new_jobs_postings_pipeline.py`.

## Endpoints Disponibles

### 1. `/process-jobs-pipeline` (Configuración Completa)

Endpoint principal que permite configurar todos los parámetros del pipeline.

**Método:** `POST`

**Body (JSON):**
```json
{
  "migrations": [
    {
      "source_collection": "practicas",
      "target_collection": "practicas_embeddings_test",
      "job_level": "practicante"
    },
    {
      "source_collection": "practicas_analistas",
      "target_collection": "analistas_embeddings_test",
      "job_level": "analista"
    }
  ],
  "cleanups": [
    {
      "collection_name": "practicas",
      "since_days": 5
    },
    {
      "collection_name": "practicas_embeddings_test",
      "since_days": 7
    }
  ],
  "sections": {
    "enable_migration": true,
    "enable_metadata": true,
    "enable_embeddings": true,
    "enable_cache_clear": true,
    "enable_cleanup": true
  },
  "overwrite_metadata": false,
  "overwrite_embeddings": false,
  "days_back": 5
}
```

**Parámetros de Configuración:**

| Parámetro | Tipo | Descripción | Valor por Defecto |
|-----------|------|-------------|-------------------|
| `migrations` | array | Lista de configuraciones de migración | `[]` (Opcional si solo se quieren generar metadata/embeddings) |
| `migrations[].source_collection` | string | Colección fuente de prácticas | Requerido si hay migraciones |
| `migrations[].target_collection` | string | Colección destino para embeddings | Requerido si hay migraciones |
| `migrations[].job_level` | enum | Nivel de trabajo: `practicante`, `analista`, `senior`, `junior` | Requerido si hay migraciones |
| `sections` | object | Configuración de secciones a ejecutar | `{}` |
| `sections.enable_migration` | boolean | Ejecutar migración de colecciones | `true` |
| `sections.enable_metadata` | boolean | Ejecutar generación de metadatos | `true` |
| `sections.enable_embeddings` | boolean | Ejecutar generación de embeddings | `true` |
| `sections.enable_cache_clear` | boolean | Ejecutar limpieza de caches | `true` |
| `sections.enable_cleanup` | boolean | Ejecutar limpieza de documentos antiguos | `false` |
| `cleanups` | array | Lista de configuraciones de limpieza | `[]` |
| `cleanups[].collection_name` | string | Nombre de la colección a limpiar | Requerido |
| `cleanups[].since_days` | integer | Eliminar documentos más antiguos que N días | Requerido |
| `overwrite_metadata` | boolean | Sobrescribir metadatos existentes | `false` |
| `overwrite_embeddings` | boolean | Sobrescribir embeddings existentes | `false` |
| `days_back` | integer | Solo procesar documentos de los últimos N días | `5` |

**Nota:** Los parámetros de rate limiting, batch sizes, delays y logging están configurados internamente con valores optimizados por defecto.

**Comportamiento Inteligente:**
- Si `enable_migration: false` y no hay migraciones configuradas, el sistema automáticamente asume que se refiere a `practicas_embeddings_test` para metadata y embeddings
- Esto permite generar metadata y embeddings sin necesidad de configurar migraciones



## Respuesta del Pipeline

El endpoint retorna un objeto `PipelineResult` con la siguiente estructura:

```json
{
  "success": true,
  "total_duration": 45.23,
  "steps": {
    "migration": {
      "step_name": "Migración de colecciones",
      "status": "completed",
      "duration": 12.34,
      "details": {
        "total_migrations": 2,
        "total_migrated": 25,
        "total_skipped": 125,
        "total_errors": 0,
        "migrations": [
          {
            "migration": "practicas → practicas_embeddings_test",
            "job_level": "practicante",
            "result": { "total": 100, "migrated": 15, "skipped": 85, "errors": 0 }
          },
          {
            "migration": "practicas_analistas → analistas_embeddings_test", 
            "job_level": "analista",
            "result": { "total": 50, "migrated": 10, "skipped": 40, "errors": 0 }
          }
        ]
      }
    },
    "metadata": {
      "step_name": "Generación de metadatos",
      "status": "completed",
      "duration": 18.45,
      "details": {
        "total_collections": 2,
        "total_processed": 30,
        "total_skipped": 120,
        "total_errors": 0,
        "collections": [
          {
            "collection": "practicas_embeddings_test",
            "stats": { "total": 100, "processed": 20, "skipped": 80, "errors": 0 }
          },
          {
            "collection": "analistas_embeddings_test",
            "stats": { "total": 50, "processed": 10, "skipped": 40, "errors": 0 }
          }
        ]
      }
    },
    "embeddings": {
      "step_name": "Generación de embeddings",
      "status": "completed",
      "duration": 14.44,
      "details": {
        "total_collections": 2,
        "total_processed": 35,
        "total_skipped": 115,
        "total_errors": 0,
        "collections": [
          {
            "collection": "practicas_embeddings_test",
            "stats": { "total": 100, "processed": 25, "skipped": 75, "errors": 0 }
          },
          {
            "collection": "analistas_embeddings_test",
            "stats": { "total": 50, "processed": 10, "skipped": 40, "errors": 0 }
          }
        ]
      }
    },
    "cache_clear": {
      "step_name": "Limpieza de caches",
      "status": "completed",
      "duration": 0.12,
      "details": {
        "caches_removed": 45
      }
    },
    "cleanup": {
      "step_name": "Limpieza de documentos antiguos",
      "status": "completed",
      "duration": 2.34,
      "details": {
        "total_cleanups": 2,
        "total_deleted": 150,
        "total_errors": 0,
        "cleanups": [
          {
            "collection": "practicas",
            "since_days": 5,
            "result": { "total": 100, "deleted": 80, "errors": 0 }
          },
          {
            "collection": "practicas_embeddings_test",
            "since_days": 7,
            "result": { "total": 70, "deleted": 70, "errors": 0 }
          }
        ]
      }
    }
  },
  "summary": {
    "total_duration": 45.23,
    "total_practices_migrated": 25,
    "total_metadata_generated": 30,
    "total_embeddings_generated": 35,
    "caches_cleared": 45,
    "total_documents_deleted": 150,
    "logs": [
      "[14:30:15] 🚀 Iniciando pipeline de procesamiento de ofertas laborales",
      "[14:30:15] 📁 Configuración:",
      "[14:30:15]    - Migraciones: 2",
      "[14:30:15]      1. practicas → practicas_embeddings_test (practicante)",
      "[14:30:15]      2. practicas_analistas → analistas_embeddings_test (analista)",
      "[14:30:15]    - Secciones habilitadas:",
      "[14:30:15]      - Migración: true",
      "[14:30:15]      - Metadatos: true",
      "[14:30:15]      - Embeddings: true",
      "[14:30:15]      - Limpieza cache: true",
      // ... más logs
    ]
  }
}
```

## Pasos del Pipeline

El pipeline ejecuta los siguientes pasos en orden:

1. **Migración de Colecciones**: Copia documentos de la colección fuente a la destino, agregando el campo `job_level`
2. **Generación de Metadatos**: Usa IA (Gemini) para extraer metadatos estructurados de título y descripción
3. **Generación de Embeddings**: Convierte los metadatos a vectores para búsqueda semántica
4. **Limpieza de Caches** (opcional): Invalida todos los caches de matches para que los usuarios vean las nuevas prácticas
5. **Limpieza de Documentos Antiguos** (opcional): Elimina documentos más antiguos que el número de días especificado

## Ejemplos de Uso

### Ejemplo 1: Configuración Completa
```bash
curl -X POST "http://localhost:8000/process-jobs-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "migrations": [
      {
        "source_collection": "practicas",
        "target_collection": "practicas_embeddings_test",
        "job_level": "practicante"
      },
      {
        "source_collection": "practicas_analistas",
        "target_collection": "analistas_embeddings_test",
        "job_level": "analista"
      }
    ],
    "cleanups": [
      {
        "collection_name": "practicas",
        "since_days": 5
      },
      {
        "collection_name": "practicas_embeddings_test",
        "since_days": 7
      }
    ],
    "sections": {
      "enable_migration": true,
      "enable_metadata": true,
      "enable_embeddings": true,
      "enable_cache_clear": true,
      "enable_cleanup": true
    },
    "overwrite_metadata": false,
    "overwrite_embeddings": false,
    "days_back": 5
  }'
```



### Ejemplo 3: Solo Limpieza de Documentos Antiguos
```bash
curl -X POST "http://localhost:8000/process-jobs-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "migrations": [
      {
        "source_collection": "practicas",
        "target_collection": "practicas_embeddings_test",
        "job_level": "practicante"
      }
    ],
    "cleanups": [
      {
        "collection_name": "practicas",
        "since_days": 5
      },
      {
        "collection_name": "practicas_embeddings_test",
        "since_days": 7
      }
    ],
    "sections": {
      "enable_migration": false,
      "enable_metadata": false,
      "enable_embeddings": false,
      "enable_cache_clear": false,
      "enable_cleanup": true
    },
    "overwrite_metadata": false,
    "overwrite_embeddings": false,
    "days_back": 5
  }'
```

### Ejemplo 4: Sobrescribir Todo
```bash
curl -X POST "http://localhost:8000/process-jobs-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "migrations": [
      {
        "source_collection": "practicas",
        "target_collection": "practicas_embeddings_test",
        "job_level": "practicante"
      }
    ],
    "sections": {
      "enable_migration": true,
      "enable_metadata": true,
      "enable_embeddings": true,
      "enable_cache_clear": true,
      "enable_cleanup": false
    },
    "overwrite_metadata": true,
    "overwrite_embeddings": true,
    "days_back": 5
  }'
```

## Casos de Uso

### Caso 1: Procesamiento Semanal Normal
- Usar configuración por defecto
- No sobrescribir metadatos/embeddings existentes
- Limpiar caches al finalizar

### Caso 2: Reprocesamiento Completo
- Sobrescribir metadatos y embeddings
- Útil cuando se actualiza el modelo de IA o se cambia la estructura

### Caso 3: Procesamiento Silencioso
- Configurar `verbose: false` para logs mínimos
- Útil para ejecuciones automáticas

### Caso 4: Procesamiento Rápido
- Reducir delays y aumentar batch sizes
- Útil para pruebas o procesamiento urgente

### Caso 5: Solo Migración
- Ejecutar solo la migración de colecciones
- Útil cuando solo se quieren copiar datos sin procesar

### Caso 6: Solo Metadatos y Embeddings
- Saltar la migración y ejecutar solo procesamiento
- Útil cuando los datos ya están migrados
- **Nuevo:** No requiere configuración de migraciones, automáticamente usa `practicas_embeddings_test`

### Caso 7: Múltiples Colecciones
- Procesar múltiples fuentes de datos en una sola ejecución
- Útil para consolidar diferentes tipos de ofertas laborales

### Caso 8: Solo Limpieza de Cache
- Ejecutar solo la limpieza de caches
- Útil cuando se necesita invalidar caches sin reprocesar datos

## Ejemplos de Casos de Uso Específicos

### Solo Migración
```bash
curl -X POST "http://localhost:8000/process-jobs-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "migrations": [
      {
        "source_collection": "practicas",
        "target_collection": "practicas_embeddings_test",
        "job_level": "practicante"
      }
    ],
    "sections": {
      "enable_migration": true,
      "enable_metadata": false,
      "enable_embeddings": false,
      "enable_cache_clear": false
    }
  }'
```

### Solo Metadatos y Embeddings (Nuevo - Sin migraciones)
```bash
curl -X POST "http://localhost:8000/process-jobs-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "sections": {
      "enable_migration": false,
      "enable_metadata": true,
      "enable_embeddings": true,
      "enable_cache_clear": false,
      "enable_cleanup": false
    },
    "overwrite_metadata": false,
    "overwrite_embeddings": false,
    "days_back": 5
  }'
```

**Nota:** En este caso, el sistema automáticamente asume que se refiere a `practicas_embeddings_test` sin necesidad de configurar migraciones.

### Solo Metadatos y Embeddings (Formato anterior)
```bash
curl -X POST "http://localhost:8000/process-jobs-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "migrations": [
      {
        "source_collection": "practicas",
        "target_collection": "practicas_embeddings_test",
        "job_level": "practicante"
      }
    ],
    "sections": {
      "enable_migration": false,
      "enable_metadata": true,
      "enable_embeddings": true,
      "enable_cache_clear": true
    }
  }'
```

### Múltiples Colecciones
```bash
curl -X POST "http://localhost:8000/process-jobs-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "migrations": [
      {
        "source_collection": "practicas",
        "target_collection": "practicas_embeddings_test",
        "job_level": "practicante"
      },
      {
        "source_collection": "practicas_analistas",
        "target_collection": "analistas_embeddings_test",
        "job_level": "analista"
      },
      {
        "source_collection": "practicas_senior",
        "target_collection": "senior_embeddings_test",
        "job_level": "senior"
      }
    ],
    "sections": {
      "enable_migration": true,
      "enable_metadata": true,
      "enable_embeddings": true,
      "enable_cache_clear": true
    }
  }'
```

### Solo Limpieza de Cache
```bash
curl -X POST "http://localhost:8000/process-jobs-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "migrations": [
      {
        "source_collection": "practicas",
        "target_collection": "practicas_embeddings_test",
        "job_level": "practicante"
      }
    ],
    "sections": {
      "enable_migration": false,
      "enable_metadata": false,
      "enable_embeddings": false,
      "enable_cache_clear": true
    }
  }'
```

## Notas Importantes

1. **Rate Limiting**: Los delays están configurados para evitar saturar las APIs de IA y Firestore
2. **Idempotencia**: El pipeline es idempotente - puede ejecutarse múltiples veces sin efectos secundarios
3. **Logs**: Los logs completos se incluyen en la respuesta para debugging
4. **Errores**: Los documentos que fallan se guardan en `failed_metadata_docs.json` para reintentos
5. **Cache**: Siempre se recomienda limpiar caches al finalizar para que los usuarios vean las nuevas prácticas

## Migración desde el Script Manual

Para migrar desde la ejecución manual del script:

**Antes:**
```bash
python process_new_jobs_postings_pipeline.py
```

**Después:**
```bash
curl -X POST "http://localhost:8000/process-jobs-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "migrations": [
      {
        "source_collection": "practicas",
        "target_collection": "practicas_embeddings_test",
        "job_level": "practicante"
      }
    ],
    "sections": {
      "enable_migration": true,
      "enable_metadata": true,
      "enable_embeddings": true,
      "enable_cache_clear": true
    }
  }'
```
