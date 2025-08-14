# Sistema de Cache para Matches de Prácticas

## Descripción

El sistema de cache implementado en el endpoint `/match-practices` permite evitar recalcular embeddings y búsquedas cuando el CV del usuario no ha cambiado, mejorando significativamente el rendimiento de las consultas repetidas.

## Funcionamiento

### Clave de Cache
- **user_id**: ID del usuario
- **cvFileUrl**: URL del archivo CV (se actualiza cada vez que se modifica el CV)

### Duración del Cache
- **Sin expiración**: El cache dura indefinidamente hasta que se elimine manualmente
- **Invalidación manual**: Se elimina cuando se suben nuevas prácticas

### Flujo de Cache

1. **Verificación de Cache**: Al recibir una solicitud, el sistema verifica si existe un cache válido para el usuario y CV específico.

2. **Cache Hit**: Si se encuentra un cache válido:
   - Se devuelven las prácticas desde el cache
   - Se omite el cálculo de embeddings y búsqueda
   - Se registra en logs: `"✅ Se encontró cache en cache_matches, devolviendo prácticas desde cache"`

3. **Cache Miss**: Si no se encuentra cache:
   - Se calculan los embeddings del CV
   - Se realiza la búsqueda de prácticas afines
   - Se guarda el resultado en cache
   - Se registra en logs: `"🔍 No se encontró cache, calculando matches"`

4. **Invalidación Manual**: El cache se invalida cuando:
   - El CV se actualiza (cambia `cvFileUrl`)
   - Se suben nuevas prácticas (eliminación manual)
   - Se ejecuta limpieza manual

## Estructura de Datos

### Colección: `cache_matches`

```json
{
  "user_id": "string",
  "cvFileUrl": "string",
  "practices": [
    {
      "id": "string",
      "title": "string",
      "company": "string",
      "similarity_percentage": 85.5,
      // ... otros campos de la práctica
    }
  ],
  "created_at": "datetime"
}
```

## Configuración

### Variables de Entorno

```bash
# Configuración de streaming
STREAMING_ENABLED=true
STREAMING_CHUNK_SIZE=3

# Configuración de búsqueda
DEFAULT_SINCE_DAYS=5
DEFAULT_PERCENTAGE_THRESHOLD=0
DEFAULT_PRACTICES_LIMIT=100
```

## Endpoints

### `/match-practices` (POST)
- **Funcionalidad**: Matching de prácticas con sistema de cache integrado
- **Parámetros**: `user_id`, `limit` (opcional)
- **Respuesta**: Incluye campo `cache_hit` en metadata

### `/clear-all-caches` (POST)
- **Funcionalidad**: Limpia todos los caches manualmente
- **Respuesta**: Número total de caches eliminados

## Logs del Sistema

### Cache Hit
```
✅ Se encontró cache en cache_matches, devolviendo prácticas desde cache
🚀 Devolviendo 25 prácticas desde cache
```

### Cache Miss
```
🔍 No se encontró cache, calculando matches
💾 Cache guardado exitosamente para user_id: user123
```

### Limpieza de Cache
```
🧹 Limpieza completa de cache: 25 caches eliminados
```

## Ventajas

1. **Rendimiento**: Reducción significativa en tiempo de respuesta para consultas repetidas
2. **Escalabilidad**: Menor carga en el sistema de embeddings y búsqueda
3. **Flexibilidad**: Configuración centralizada y fácil de ajustar
4. **Automatización**: Invalidación automática basada en cambios de CV
5. **Mantenimiento**: Limpieza manual cuando se suben nuevas prácticas

## Consideraciones

- El cache se basa en `cvFileUrl`, que cambia cada vez que se actualiza el CV
- Los caches no expiran automáticamente, duran hasta que se eliminen manualmente
- El sistema maneja casos donde el CV no tiene `fileUrl`
- La limpieza de todos los caches se puede ejecutar manualmente cuando se suben nuevas prácticas

## Monitoreo

Para monitorear el uso del cache, revisar los logs del sistema:
- Cache hits vs misses
- Tiempo de respuesta con y sin cache
- Número de caches eliminados manualmente
