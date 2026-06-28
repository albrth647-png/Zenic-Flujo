"""
ORBITAL — Motor orbital de auditoría Any
========================================

Adapta el sistema de antipatrones `Any` (any_audit.py + codemods + baseline)
al motor determinista circular Orbital.

Mapeo conceptual:
  - Cada módulo con deuda → VariableOrbital
    θ = fase de deuda (proporción de deuda real vs total)
    A = amplitud (count absoluto de Any)
    ω = velocidad de reducción (defaults a 0.1, baja si refactor estable)

  - Cada antipatrón → VariableOrbital (grupo "antipatterns")
    θ = proporción del antipatrón en el módulo
    A = frecuencia absoluta

  - Justificaciones (`# legítimo:`) reducen la amplitud efectiva
    (no son deuda, son decisión consciente)

  - CicloOrbital agrupa módulos correlacionados (connectors↔sdk,
    api_v2↔mobile, etc.) para detectar resonancia de deuda

  - TOR(módulo_i, módulo_j) = tensión de deuda: si ambos tienen
    deuda alta, hay resonancia → hotspot prioritario

  - RCC detecta ciclos resonantes = hotspots que se retroalimentan

  - COD colapsa a recomendación determinista: orden de ataque óptimo

  - Espectro genera reporte multimodal: módulos prioritarios,
    antipatrones dominantes, estrategia de refactor

  - Retroalimentación: cada tick actualiza θ de los módulos
    según evolución del baseline (deuda baja → θ avanza → A baja)

Este módulo NO reemplaza any_audit.py: lo envuelve y lo orquesta
como un caso de uso real del motor Orbital.
"""
from __future__ import annotations

from src.orbital.any_audit.adapter import OrbitalAnyAuditEngine
from src.orbital.any_audit.mapper import AnyAuditMapper

__all__ = ["OrbitalAnyAuditEngine", "AnyAuditMapper"]
