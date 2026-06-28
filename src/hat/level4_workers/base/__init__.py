"""NIVEL 4 — Base compartida de workers.

Contiene:
- ToolWorker (ABC con circuit breaker + idempotency integrados)
- WorkerFactory (auto-genera workers por introspección de tools)
- WorkerRegistry (lookup por tool+action)
- compute_worker_hash (hash determinista para idempotency)
"""
from src.hat.level4_workers.base.idempotency import compute_worker_hash
from src.hat.level4_workers.base.registry import WorkerRegistry
from src.hat.level4_workers.base.tool_worker import ToolWorker
from src.hat.level4_workers.base.worker_factory import WorkerFactory

__all__ = ["ToolWorker", "WorkerFactory", "WorkerRegistry", "compute_worker_hash"]
