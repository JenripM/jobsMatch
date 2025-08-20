# API Documentation: `/match-practice` Endpoint

## Overview

The `/match-practice` endpoint calculates the match score between a user's CV and a specific job practice. This endpoint is used in the frontend route `/job_offers/{job_offer_id}` to display detailed match information for a single job offer.

## Endpoint Details

- **URL**: `POST /match-practice`
- **Content-Type**: `application/json`
- **Authentication**: Not required (uses user_id in request body)

## Request

### Request Body

```json
{
  "user_id": "string",
  "practice_id": "string"
}
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | ✅ | The unique identifier of the user |
| `practice_id` | string | ✅ | The unique identifier of the job practice |

### Example Request

```javascript
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
```

## Response

### Success Response (200 OK)

```json
{
  "practica": {
    "id": "practice_456",
    "title": "Software Engineer Intern",
    "company": "Tech Corp",
    "location": "San Francisco, CA",
    "description": "We are looking for a talented software engineer...",
    "requirements": "Python, JavaScript, React experience...",
    "salary": "$25-35/hour",
    "fecha_agregado": "2024-01-15T10:30:00Z",
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
    "practice_id": "practice_456",
    "user_id": "user_123",
    "total_time": 0.0456,
    "search_matching_time": 0.0234
  }
}
```

### Response Fields

#### `practica` Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | **Firestore document ID** - Unique identifier from Firestore |
| `title` | string | Job title |
| `company` | string | Company name |
| `location` | string | Job location |
| `description` | string | Job description |
| `requirements` | string | Job requirements |
| `salary` | string | Salary information |
| `fecha_agregado` | string | Date when practice was added (ISO 8601) |
| `match_scores` | object | Calculated match scores (see below) |
| `raw_similarities` | object | Raw similarity values (see below) |

#### `match_scores` Object

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `hard_skills` | number | 0-100 | Match score for technical skills |
| `soft_skills` | number | 0-100 | Match score for soft skills |
| `sector_affinity` | number | 0-100 | Match score for industry/sector fit |
| `general` | number | 0-100 | General match score |
| `total` | number | 0-100 | **Weighted average of all scores** |

#### `raw_similarities` Object

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `general` | number | 0-1 | Raw similarity for general aspect |
| `category` | number | 0-1 | Raw similarity for category/sector |
| `hard_skills` | number | 0-1 | Raw similarity for hard skills |
| `soft_skills` | number | 0-1 | Raw similarity for soft skills |

#### `metadata` Object

| Field | Type | Description |
|-------|------|-------------|
| `practice_id` | string | Practice ID from request |
| `user_id` | string | User ID from request |
| `total_time` | number | Total processing time in seconds |
| `search_matching_time` | number | Time spent on matching calculation |

### Error Responses

#### 400 Bad Request
```json
{
  "detail": "user_id es requerido"
}
```
```json
{
  "detail": "practice_id es requerido"
}
```

#### 404 Not Found
```json
{
  "detail": "No se pudo obtener el CV del usuario. Verifique que el usuario existe y tiene un CV válido."
}
```
```json
{
  "detail": "Práctica con ID practice_456 no encontrada"
}
```

#### 500 Internal Server Error
```json
{
  "detail": "Error interno: [error message]"
}
```

## Frontend Integration Examples

### React Hook Example

```jsx
import { useState, useEffect } from 'react';

const useMatchPractice = (userId, practiceId) => {
  const [matchData, setMatchData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchMatch = async () => {
      if (!userId || !practiceId) return;

      setLoading(true);
      setError(null);

      try {
        const response = await fetch('/match-practice', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, practice_id: practiceId })
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to fetch match');
        }

        const data = await response.json();
        setMatchData(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchMatch();
  }, [userId, practiceId]);

  return { matchData, loading, error };
};
```

### React Component Example

```jsx
import React from 'react';
import { useMatchPractice } from './hooks/useMatchPractice';

const JobOfferDetail = ({ jobOfferId, userId }) => {
  const { matchData, loading, error } = useMatchPractice(userId, jobOfferId);

  if (loading) {
    return (
      <div className="loading-container">
        <div className="spinner"></div>
        <p>Calculating match score...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-container">
        <h3>Error</h3>
        <p>{error}</p>
      </div>
    );
  }

  if (!matchData) {
    return <div>No match data available</div>;
  }

  const { practica } = matchData;
  const { match_scores } = practica;

  return (
    <div className="job-offer-detail">
      <header className="job-header">
        <h1>{practica.title}</h1>
        <h2>{practica.company}</h2>
        <p className="location">{practica.location}</p>
      </header>

      <div className="match-score-section">
        <div className="match-score-card">
          <h3>Match Score</h3>
          <div className="total-score">
            <span className="score-number">{match_scores.total.toFixed(1)}%</span>
            <span className="score-label">Total Match</span>
          </div>
        </div>

        <div className="score-breakdown">
          <div className="score-item">
            <span className="score-label">Hard Skills</span>
            <span className="score-value">{match_scores.hard_skills.toFixed(1)}%</span>
          </div>
          <div className="score-item">
            <span className="score-label">Soft Skills</span>
            <span className="score-value">{match_scores.soft_skills.toFixed(1)}%</span>
          </div>
          <div className="score-item">
            <span className="score-label">Sector Affinity</span>
            <span className="score-value">{match_scores.sector_affinity.toFixed(1)}%</span>
          </div>
          <div className="score-item">
            <span className="score-label">General</span>
            <span className="score-value">{match_scores.general.toFixed(1)}%</span>
          </div>
        </div>
      </div>

      <div className="job-content">
        <section className="description">
          <h3>Description</h3>
          <p>{practica.description}</p>
        </section>

        <section className="requirements">
          <h3>Requirements</h3>
          <p>{practica.requirements}</p>
        </section>

        <section className="salary">
          <h3>Salary</h3>
          <p>{practica.salary}</p>
        </section>
      </div>
    </div>
  );
};
```

### TypeScript Types

```typescript
interface MatchScores {
  hard_skills: number;
  soft_skills: number;
  sector_affinity: number;
  general: number;
  total: number;
}

interface RawSimilarities {
  general: number;
  category: number;
  hard_skills: number;
  soft_skills: number;
}

interface Practice {
  id: string;
  title: string;
  company: string;
  location: string;
  description: string;
  requirements: string;
  salary: string;
  fecha_agregado: string;
  match_scores: MatchScores;
  raw_similarities: RawSimilarities;
}

interface MatchMetadata {
  practice_id: string;
  user_id: string;
  total_time: number;
  search_matching_time: number;
}

interface MatchPracticeResponse {
  practica: Practice;
  metadata: MatchMetadata;
}

interface MatchPracticeRequest {
  user_id: string;
  practice_id: string;
}
```

### Error Handling

```jsx
const handleMatchError = (error) => {
  switch (error.status) {
    case 400:
      return 'Invalid request parameters. Please check user_id and practice_id.';
    case 404:
      return 'Practice not found or user CV not available.';
    case 500:
      return 'Server error. Please try again later.';
    default:
      return 'An unexpected error occurred.';
  }
};
```

### Loading States

```jsx
const MatchScoreIndicator = ({ score, loading }) => {
  if (loading) {
    return (
      <div className="score-indicator loading">
        <div className="score-skeleton"></div>
      </div>
    );
  }

  const getScoreColor = (score) => {
    if (score >= 80) return 'excellent';
    if (score >= 60) return 'good';
    if (score >= 40) return 'fair';
    return 'poor';
  };

  return (
    <div className={`score-indicator ${getScoreColor(score)}`}>
      <span className="score">{score.toFixed(1)}%</span>
    </div>
  );
};
```

## Score Consistency

The `/match-practice` endpoint uses the same scoring algorithm as `/match-practices` to ensure consistency:

### Scoring Algorithm
- **Hard Skills**: 40% weight (technical skills matching)
- **Soft Skills**: 10% weight (soft skills matching)
- **Sector Affinity**: 30% weight (industry/sector fit)
- **General**: 20% weight (overall semantic similarity)

### Normalization
- For single practice matching, raw similarity scores (0-1) are converted to percentages (0-100)
- Low similarity scores (< 10%) are penalized to maintain consistency with batch processing
- The same weighting formula is applied in both endpoints

### Verification
Use the provided test script `test_score_consistency.py` to verify that scores are consistent between endpoints.

## Performance Considerations

- **Response Time**: Typically 50-100ms for a single practice
- **No Caching**: Each request calculates match in real-time
- **Error Recovery**: Implement retry logic for network failures
- **Loading States**: Always show loading indicators during API calls

## Best Practices

1. **Always handle loading states** - Show spinners or skeletons while fetching
2. **Implement error boundaries** - Catch and display errors gracefully
3. **Use TypeScript** - Define proper types for better development experience
4. **Debounce requests** - Avoid multiple rapid requests for the same practice
5. **Cache user data** - Store user_id locally to avoid repeated input
6. **Validate inputs** - Check that user_id and practice_id are valid before making requests

## Testing

```jsx
// Example test with React Testing Library
import { render, screen, waitFor } from '@testing-library/react';
import { rest } from 'msw';
import { setupServer } from 'msw/node';
import JobOfferDetail from './JobOfferDetail';

const server = setupServer(
  rest.post('/match-practice', (req, res, ctx) => {
    return res(
      ctx.json({
        practica: {
          id: 'test-practice',
          title: 'Test Job',
          company: 'Test Company',
          match_scores: { total: 85.5 }
        },
        metadata: { total_time: 0.05 }
      })
    );
  })
);

test('displays match score correctly', async () => {
  render(<JobOfferDetail jobOfferId="test-practice" userId="test-user" />);
  
  await waitFor(() => {
    expect(screen.getByText('85.5%')).toBeInTheDocument();
  });
});
```
