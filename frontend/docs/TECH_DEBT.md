# Frontend — Deuda Técnica Conocida

## react-hooks/set-state-in-effect (NEW-BUG-3)

**Estado**: Deuda técnica documentada (Sprint 5)
**Severidad**: P2 (no afecta runtime ni seguridad)
**Conteo actual**: 33 ocurrencias en 25 archivos

### Qué es

La regla `react-hooks/set-state-in-effect` de ESLint avisa cuando un `useEffect`
llama a `setState` directamente, porque puede causar renders extra y loops
potenciales. React 19 con la regla `react-hooks/configs.flat.recommended`
activa esta verificación.

### Por qué no se ha refactorizado

Refactorizar cada ocurrencia requiere:
1. Identificar si el state es derivado (→ `useMemo`)
2. Si no es derivado, usar patrón `setState((prev) => prev !== new ? new : prev)` para idempotencia
3. Validar que no se rompe el comportamiento (cada caso es distinto)

Con 33 ocurrencias en 25 archivos, esto es ~6-8h de trabajo cuidadoso con
testing manual de cada página. No bloquea el score 95% ni la seguridad.

### Dónde están

```bash
grep -rl "react-hooks/set-state-in-effect" src/
```

### Plan de refactor (Sprint 6 opcional)

Para cada ocurrencia:
1. **Si el state es derivado** (ej: `dirty` en Editor.tsx que ya se refactorizó en Sprint 4):
   - Convertir a `useMemo` si NO lee refs durante render
   - Si lee refs, usar `useState` + `useEffect` con `setState((prev) => prev !== new ? new : prev)` (idempotente)
2. **Si el state NO es derivado** (carga asíncrona de datos):
   - Mantener `useEffect` pero usar AbortController para cancelar fetchs en unmount
   - El `setState` es legítimo aquí, silenciar warning con justificación en comentario

### Validación post-refactor

```bash
cd frontend
npx eslint . --max-warnings 0
npx tsc -b
npx vitest run
```
