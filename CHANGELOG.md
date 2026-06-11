# Changelog

## v1.0.0 (2026-06-10)

### Added
- Motor ORBITAL v3.2 completo (OVC, TOR, RCC, COD, Espectro)
- OrbitalContext singleton con OVC compartido
- Benchmarks del motor ORBITAL
- Sistema WebSocket para dashboard en tiempo real
- Tema oscuro/claro con persistencia localStorage
- Chat mejorado con markdown y sugerencias
- API documentada con OpenAPI 3.0
- API Key authentication system
- Webhooks de salida
- Rate limiting por API key y por IP
- RBAC (admin, editor, viewer)
- CI/CD con GitHub Actions
- Instalador Windows/Linux con GUI tkinter

### Fixed
- 7 bugs críticos de Fase 0 (OrbitalContext, COD, secrets, eval, etc.)
- Migración nlp → nlu completada
- 101+ tests nuevos para seguridad y testing
- SQL injection prevention (parameterized queries)
- XSS protection mejorada
- Cookie security (httpOnly, SameSite)
