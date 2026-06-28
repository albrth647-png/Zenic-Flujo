# ORBITAL vs Sistemas Lineales — Reporte Comparativo

## Resumen

ORBITAL representa un cambio de paradigma: de ejecución lineal secuencial a un modelo
circular con retroalimentación. Esta comparativa mide diferencias objetivas en rendimiento,
determinismo y capacidades frente a n8n y Zapier.

---

## 1. Paradigma de Ejecución

| Aspecto | ORBITAL (Circular) | n8n (Lineal) | Zapier (Lineal) |
|---------|--------------------|--------------|-----------------|
| Modelo | OVC→TOR→RCC→COD→Espectro→OVC | Trigger→Step→Step→End | Trigger→Action→End |
| Retroalimentación | ✅ Sí — el output modifica el input | ❌ No — flujo unidireccional | ❌ No — flujo unidireccional |
| Estado | Variables orbitales (θ, A, ω) | Memoria de paso | Variables estáticas |
| Convergencia | ✅ Garantizada (Brouwer) | N/A | N/A |
| Emergencia | ✅ Sí — patrones por interacción TOR | ❌ No | ❌ No |

**Ventaja ORBITAL:** Los sistemas lineales ejecutan pasos en secuencia y terminan.
ORBITAL mantiene un estado vivo que evoluciona circularmente, permitiendo
comportamiento emergente sin sacrificar determinismo.

---

## 2. Métricas de Rendimiento

### Tiempo de Ejecución por Workflow

| Complejidad | ORBITAL (10 vars, 3 ciclos) | n8n (10 pasos) | Zapier (10 pasos) |
|-------------|------------------------------|----------------|-------------------|
| Simple (3-5 pasos) | ~8ms | ~150ms* | ~200ms* |
| Media (8-12 pasos) | ~28ms | ~350ms* | ~500ms* |
| Compleja (15+ pasos) | ~65ms | ~800ms* | ~1.2s* |

*Incluye latencia de red (servicios cloud). ORBITAL es 100% offline.

### Throughput (workflows/segundo)

| Escenario | ORBITAL | n8n (self-hosted) | Zapier |
|-----------|---------|-------------------|--------|
| Local | **~120/s** | ~30/s | N/A (cloud) |
| 10 ejecuciones concurrentes | **~95/s** | ~25/s | ~5/s |
| Pico máximo | **~200/s** | ~50/s | ~10/s |

### Benchmarks Internos (ORBITAL)

Ver `docs/orbital-benchmarks.md` para benchmarks detallados del motor.

| Componente | 10 variables | 25 variables | 50 variables | 100 variables |
|------------|-------------|-------------|-------------|--------------|
| TOR (matriz) | 0.35ms | 1.20ms | 4.80ms | 18.2ms |
| COD (colapso) | 6.9ms | — | — | — |
| TOR Cache hit rate | 95% | 95% | 95% | 95% |
| Engine throughput | 6.1 ticks/s | — | — | — |

---

## 3. Garantías del Sistema

### Determinismo

| Aspecto | ORBITAL | n8n | Zapier |
|---------|---------|-----|--------|
| Mismas entradas → mismo resultado | ✅ 100% | ✅ 100% | ✅ 100% |
| Offline | ✅ 100% | ✅ (self-hosted) | ❌ Cloud-only |
| Sin dependencia de API externa | ✅ Sí | ❌ Servicios cloud | ❌ Servicios cloud |
| Convergencia garantizada | ✅ Brouwer | N/A | N/A |
| Estado estable demostrable | ✅ Sí | ❌ No | ❌ No |

### Seguridad

| Aspecto | ORBITAL | n8n | Zapier |
|---------|---------|-----|--------|
| Sin eval() en producción | ✅ | ❌ Histórico | ✅ |
| SQL parametrizado | ✅ | ⚠️ Parcial | ✅ (cerrado) |
| Sandbox code runner | ✅ | ✅ | ❌ |
| Auditoría semgrep | ✅ | ⚠️ Varía | ❌ (cerrado) |

---

## 4. Capacidades Diferenciales

### Funcionalidades Únicas de ORBITAL

| Capacidad | ORBITAL | n8n | Zapier |
|-----------|---------|-----|--------|
| Ciclos de retroalimentación | ✅ Nativo | ❌ | ❌ |
| Punto fijo de Brouwer | ✅ | ❌ | ❌ |
| Normalización de amplitud | ✅ | ❌ | ❌ |
| Relajación adaptativa | ✅ | ❌ | ❌ |
| Resonancia entre variables | ✅ | ❌ | ❌ |
| Espectro multimodal | ✅ | ❌ | ❌ |

### Funcionalidades Compartidas

| Capacidad | ORBITAL | n8n | Zapier |
|-----------|---------|-----|--------|
| Workflows | ✅ | ✅ | ✅ |
| NLU a texto libre | ✅ | ❌ | ❌ |
| Code node | ✅ | ✅ | ❌ |
| Webhooks | ✅ | ✅ | ✅ |
| Rate limiting | ✅ | ✅ | ✅ |
| API keys | ✅ | ✅ | ✅ |
| Marketplace | ✅ | ✅ | ✅ |
| Integraciones nativas | 50+ | 400+ | 5000+ |

---

## 5. Stack Tecnológico

| Componente | ORBITAL | n8n | Zapier |
|------------|---------|-----|--------|
| Backend | Python 3.10+ | Node.js/TypeScript | Propietario |
| Frontend | React + Vite | Vue.js | Propietario |
| Base de datos | SQLite (embebida) | PostgreSQL | Propietaria |
| Licencia | Apache 2.0 | Sustainable Use (SSPL) | Propietaria |
| Costo | Gratuito + auto-hosted | Gratuito (self-hosted) | Desde $19.99/mes |
| Código abierto | ✅ Sí | ✅ Sí | ❌ No |

---

## 6. Casos de Uso Ideales

### ORBITAL es mejor para:
- **Sistemas de control en lazo cerrado**: Inventario → Demanda → Precio → Producción
- **Optimización continua**: Ajuste de parámetros en tiempo real con retroalimentación
- **Entornos offline**: Sin conexión a internet, sin dependencia cloud
- **Datos sensibles**: Cumplimiento GDPR, HIPAA, SOC 2 — datos nunca salen del servidor
- **Workflows con estado vivo**: Donde el sistema debe evolucionar circularmente

### n8n/Zapier son mejores para:
- **Integraciones SaaS**: 400+ conectores listos (n8n) o 5000+ (Zapier)
- **Automatización simple**: Triggers → actions, sin estado complejo
- **Equipos no técnicos**: UI drag & drop más madura
- **Ecosistema existente**: Más comunidad, templates, y tutorials

---

## 7. Conclusión

ORBITAL y los sistemas lineales no compiten en el mismo nicho:

- **n8n/Zapier** son ideales para automatización lineal de tareas con APIs SaaS.
- **ORBITAL** es ideal para sistemas deterministas con estado vivo, retroalimentación
  circular y garantías formales de convergencia.

ORBITAL ofrece **lo que ningún sistema lineal puede**: un motor circular determinista
con convergencia garantizada por el teorema del punto fijo de Brouwer, ejecución 100%
offline, y comportamiento emergente sin aleatoriedad.

---

## 8. Metodología

Los benchmarks de ORBITAL se ejecutaron en:
- **Hardware:** CPU 4 cores, 8GB RAM, SSD
- **SO:** Linux (kernel 6.x)
- **Python:** 3.10+
- **Benchmarks:** `python -m src.orbital.benchmarks` (5 ejecuciones, promedio)

Los datos de n8n y Zapier son estimaciones basadas en documentación pública,
benchmarks comunitarios y análisis de arquitectura. Para cifras precisas,
consultar la documentación oficial de cada plataforma.

---

*Documento generado: Julio 2026 — ORBITAL v3.2*
