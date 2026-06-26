"""NIVEL 2 — 3 Sub-orquestadores independientes.

Cada supervisor en su propia carpeta para asegurar aislamiento:
- operaciones/ → no conoce a comunicaciones/ ni datos_auto/
- comunicaciones/ → no conoce a operaciones/ ni datos_auto/
- datos_auto/ → no conoce a operaciones/ ni comunicaciones/

Solo el HATRouter (Nivel 1) conoce a los 3.
"""
from src.hat.level2_supervisors.operaciones import OperacionesSupervisor
from src.hat.level2_supervisors.comunicaciones import ComunicacionesSupervisor
from src.hat.level2_supervisors.datos_auto import DatosAutoSupervisor

__all__ = [
    "OperacionesSupervisor",
    "ComunicacionesSupervisor",
    "DatosAutoSupervisor",
]
