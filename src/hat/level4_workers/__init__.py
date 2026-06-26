"""NIVEL 4 — Workers (más extenso que N3, 1+ por specialist).

Distribución por especialidad:
- operaciones/{crm,invoice,inventory}/
- comunicaciones/{notification,email,chat}/
- datos_auto/{data,api,code}/

Workers auto-generados al startup por WorkerFactory.
"""
from src.hat.level4_workers.base import ToolWorker, WorkerFactory, WorkerRegistry
from src.hat.level4_workers.circuit_breaker import CircuitBreakerLayer

__all__ = ["ToolWorker", "WorkerFactory", "WorkerRegistry", "CircuitBreakerLayer"]
