"""NIVEL 1 — Orquestador central Orbital.

Punto de entrada único al sistema HAT. Contiene:
- HATRouter.handle() — entry point principal
- FSM de estados (IDLE → ROUTING → DISPATCHING → CONSOLIDATING → RESPONDING)
- Intent hashing (sha256 determinista)
- Routing por resonancia RCC + fallback keywords
- Ledger (memoria entre sesiones: facts, hypotheses, progress)
- Anti-dup cascade (3 capas: exact_match, idempotency, ttl_freshness)
- DispatchTracer (OpenTelemetry spans)
- API FastAPI: POST /api/hat/chat
"""
from src.hat.level1_orchestrator.tick_router import HATRouter

__all__ = ["HATRouter"]
