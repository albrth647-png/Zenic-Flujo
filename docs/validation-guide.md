# ORBITAL v3.2 — Guía de Validación Independiente

## Objetivo

Verificar que el motor ORBITAL cumple sus garantías de convergencia determinista.

## Prerrequisitos

```bash
git clone <repo>
cd zenic-flujo
pip install -r requirements.txt
```

## Validación 1: Convergencia Determinista

**Prueba:** Mismas condiciones iniciales → mismo estado final.

```python
from src.orbital.engine import OrbitalEngine

engine = OrbitalEngine()
engine.create_variable("X", theta=0.0, amplitude=10.0, velocity=0.15)
engine.create_variable("Y", theta=0.5, amplitude=20.0, velocity=0.08)
engine.create_cycle("Test", ["X", "Y"], threshold=0.3)

result1 = engine.run_tick()
result2 = engine.run_tick()
```

**Criterio:** `result1.cod_results[0].converged == True`

## Validación 2: Amplitudes Extremas

```python
engine = OrbitalEngine()
engine.create_variable("A", theta=0.0, amplitude=10000, velocity=0.2)
engine.create_variable("B", theta=1.0, amplitude=8000, velocity=0.15)
engine.create_cycle("Extreme", ["A", "B"], threshold=0.3)

result = engine.run_tick()
```

**Criterio:** Converge en <100 iteraciones.

## Validación 3: Benchmarks

```bash
python -m src.orbital.benchmarks
```

**Criterio:** TODOS los benchmarks completan sin error.

## Validación 4: Tests

```bash
python -m pytest src/tests/ --ignore=src/tests/test_ui_playwright.py -q --tb=short
```

**Criterio:** Tests > 90% pass rate.

## Validación 5: Seguridad

```bash
pip install semgrep
semgrep --config auto --severity ERROR src/
```

**Criterio:** 0 findings críticos de seguridad.
