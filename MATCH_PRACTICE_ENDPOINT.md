# Endpoint `/match-practice`

## Descripción

El endpoint `/match-practice` calcula el match entre el CV de un usuario y una práctica específica. Este endpoint se utiliza desde la ruta frontend `/job_offers/{job_offer_id}` y devuelve una sola práctica con su score de match calculado.

## Diferencias con `/match-practices`

| Aspecto | `/match-practices` | `/match-practice` |
|---------|-------------------|-------------------|
| **Propósito** | Obtener múltiples prácticas con match | Obtener una práctica específica con match |
| **Ruta Frontend** | `/portal-trabajo` | `/job_offers/{job_offer_id}` |
| **Cantidad** | Lista de prácticas | Una sola práctica |
| **Cache** | Usa sistema de cache | No usa cache (siempre calcula) |
| **Streaming** | Soporta streaming NDJSON | Respuesta JSON tradicional |

## Endpoint

### POST `/match-practice`

Calcula el match entre el CV de un usuario y una práctica específica.

#### Request Body

```json
{
  "user_id": "string",
  "practice_id": "string"
}
```

#### Parámetros

- `user_id` (string, requerido): ID del usuario
- `practice_id` (string, requerido): ID de la práctica específica

#### Response

```json
{
  "practica": {
    "id": "string",
    "title": "string",
    "company": "string",
    "location": "string",
    "description": "string",
    "requirements": "string",
    "salary": "string",
    "fecha_agregado": "string",
    "match_scores": {
      "hard_skills": 85.5,
      "soft_skills": 72.3,
      "sector_affinity": 68.9,
      "general": 78.2,
      "total": 76.2
    },
    "raw_similarities": {
      "general": 0.782,
      "category": 0.689,
      "hard_skills": 0.855,
      "soft_skills": 0.723
    }
  },
  "metadata": {
    "practice_id": "string",
    "user_id": "string",
    "total_time": 0.0456,
    "search_matching_time": 0.0234
  }
}
```

#### Códigos de Estado

- `200 OK`: Práctica encontrada y match calculado exitosamente
- `400 Bad Request`: Faltan parámetros requeridos (`user_id` o `practice_id`)
- `404 Not Found`: Usuario no encontrado o práctica no encontrada
- `500 Internal Server Error`: Error interno del servidor

## Implementación Técnica

### Servicio: `obtener_practica_por_id_y_calcular_match`

La función principal se encuentra en `services/job_service.py`:

```python
async def obtener_practica_por_id_y_calcular_match(
    practica_id: str, 
    cv_embeddings: dict = None
) -> dict
```

#### Proceso de Cálculo

1. **Obtención de Práctica**: Busca la práctica específica por ID en Firestore
2. **Cálculo de Similitudes**: Calcula similitud coseno para cada aspecto del CV:
   - Hard Skills (35% del peso total)
   - Soft Skills (25% del peso total)
   - Sector Affinity (25% del peso total)
   - General (15% del peso total)
3. **Normalización**: Aplica normalización lineal con penalización de similitudes bajas
4. **Cálculo Final**: Calcula score total ponderado

#### Aspectos de Embedding

El sistema utiliza embeddings multi-aspecto del CV:

```python
cv_embeddings = {
    'hard_skills': vector<2048>,
    'soft_skills': vector<2048>,
    'category': vector<2048>,  # sector/industry affinity
    'general': vector<2048>    # toda la metadata
}
```

## Uso en Frontend

### Ejemplo de Llamada

```javascript
// Desde /job_offers/{job_offer_id}
const response = await fetch('/match-practice', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    user_id: 'user_123',
    practice_id: 'practice_456'
  })
});

const data = await response.json();
const { practica, metadata } = data;

// Mostrar información de la práctica
console.log(`Match: ${practica.match_scores.total}%`);
console.log(`Hard Skills: ${practica.match_scores.hard_skills}%`);
console.log(`Soft Skills: ${practica.match_scores.soft_skills}%`);
```

### Integración con React

```jsx
import { useState, useEffect } from 'react';

function JobOfferDetail({ jobOfferId, userId }) {
  const [matchData, setMatchData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMatch = async () => {
      try {
        const response = await fetch('/match-practice', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            practice_id: jobOfferId
          })
        });
        
        const data = await response.json();
        setMatchData(data);
      } catch (error) {
        console.error('Error fetching match:', error);
      } finally {
        setLoading(false);
      }
    };

    if (userId && jobOfferId) {
      fetchMatch();
    }
  }, [userId, jobOfferId]);

  if (loading) return <div>Cargando match...</div>;
  if (!matchData) return <div>Error al cargar match</div>;

  const { practica } = matchData;
  
  return (
    <div>
      <h2>{practica.title}</h2>
      <p>{practica.company}</p>
      <div className="match-score">
        <h3>Match Score: {practica.match_scores.total}%</h3>
        <div className="score-breakdown">
          <span>Hard Skills: {practica.match_scores.hard_skills}%</span>
          <span>Soft Skills: {practica.match_scores.soft_skills}%</span>
          <span>Sector: {practica.match_scores.sector_affinity}%</span>
        </div>
      </div>
    </div>
  );
}
```

## Testing

### Script de Prueba

Se incluye un script de prueba en `test_match_single_practice.py`:

```bash
python test_match_single_practice.py
```

### Configuración de Prueba

Edita las variables en el script:

```python
BASE_URL = "http://localhost:8000"
TEST_USER_ID = "tu_user_id_valido"
TEST_PRACTICE_ID = "tu_practice_id_valido"
```

## Consideraciones de Rendimiento

- **Sin Cache**: Este endpoint no utiliza cache para mantener consistencia
- **Cálculo Directo**: Siempre calcula el match en tiempo real
- **Optimización**: Usa la misma lógica de normalización que `/match-practices`
- **Tiempo Esperado**: ~50-100ms para una práctica

## Mantenimiento

### Logs

El endpoint genera logs detallados:

```
🚀 Obteniendo práctica practice_123 y calculando match...
⏱️  Paso 1: Obteniendo práctica por ID...
✅ Paso 1 completado en 0.0123 segundos - Práctica obtenida
⏱️  Paso 2: Calculando similitudes vectoriales...
✅ Similitud general: 0.782
✅ Similitud category: 0.689
✅ Similitud hard_skills: 0.855
✅ Similitud soft_skills: 0.723
✅ Paso 2 completado en 0.0234 segundos - Similitudes calculadas
⏱️  Paso 3: Normalizando puntajes y calculando similitud total...
✅ Paso 3 completado en 0.0012 segundos - Similitud total: 76.20%
⏱️  Paso 4: Formateando respuesta...
✅ Paso 4 completado en 0.0008 segundos
🎆 TIEMPO TOTAL: 0.0377 segundos
```

### Monitoreo

Monitorea los siguientes aspectos:

- Tiempo de respuesta promedio
- Tasa de errores 404 (prácticas no encontradas)
- Tasa de errores 500 (errores internos)
- Uso de memoria durante el cálculo de similitudes

