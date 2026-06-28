# HAT-ORBITAL — API Reference

## Base URL

```
http://localhost:5000/api/hat
```

## Endpoints

### POST /chat

Procesa un mensaje del usuario a través del pipeline HAT-ORBITAL completo.

**Request:**

```json
{
    "user_id": "string (required, min_length=1)",
    "session_id": "string (required, min_length=1)",
    "message": "string (required, min_length=1)",
    "context": {
        "max_results": 5,
        "lang": "es"
    }
}
```

**Response 200:**

```json
{
    "dispatch_id": "disp_abc123def456",
    "domain": "research",
    "response": "Generé 3 queries para búsqueda: buscar python, buscar python3, buscar cpython",
    "orbital_resonance": 0.4143,
    "anti_dup_layer_hit": "none",
    "duration_ms": 3,
    "facts_updated": [],
    "status": "completed"
}
```

**Response 200 (anti-dup blocked):**

```json
{
    "dispatch_id": "disp_abc123def456",
    "domain": "research",
    "response": "Detectamos un doble-click. Ignorando la solicitud duplicada (capa: ttl_freshness).",
    "orbital_resonance": 0.0,
    "anti_dup_layer_hit": "ttl_freshness",
    "duration_ms": 1,
    "facts_updated": [],
    "status": "anti_dup_blocked"
}
```

**Response 422 (validation error):**

Falta `user_id`, `session_id`, o `message` (o están vacíos).

**Response 500 (internal error):**

```json
{
    "detail": "Error interno HAT: database is locked"
}
```

### GET /health

Health check del endpoint HAT.

**Response 200:**

```json
{
    "status": "ok",
    "module": "hat",
    "version": "f0-d7"
}
```

## Status codes

| Status | Descripción |
|--------|-------------|
| `completed` | Dispatch ejecutado exitosamente |
| `clarify` | FSM no pudo desambiguar — pedir aclaración al usuario |
| `failed` | Error durante la ejecución del supervisor |
| `anti_dup_blocked` | Anti-dup cascade detectó duplicado |

## Anti-dup layers

| Layer | Action | Descripción |
|-------|--------|-------------|
| `exact_match` | `return_cache` | Hash idéntico ya completado → devuelve cache |
| `idempotency` | `subscribe` | Hash en ejecución → suscríbete al resultado |
| `ttl_freshness` | `discard` | Doble-click <5s → descarta |
| `semantic_dedup` | `confirm` | Similitud >0.85 → pide confirmación |
| `circuit_breaker` | `fallback` | ≥3 fallos consecutivos → fallback graceful |
| `none` | `proceed` | Todas las capas pasaron → ejecutar normally |

## Dominios

| Dominio | Supervisor | Specialists |
|---------|------------|-------------|
| `research` | ResearchSupervisor | WebResearcher |
| `build` | BuildSupervisor | CodeGenerator, TestEngineer, DeployAgent |
| `operate` | OperateSupervisor | MonitorAgent, LogAnalyzer, IncidentResponder |
| `clarify` | (ninguno) | FSM no resolvió — pedir aclaración |
