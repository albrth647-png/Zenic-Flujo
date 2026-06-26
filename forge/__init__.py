"""
Code-Forge v1.0 — Zenic-Flujo Edition
======================================
Framework de ingeniería para agentes de IA: sandbox, run ledger,
memoria persistente, y 12 gates de calidad bilingües (Python + TypeScript).

Basado en:
  - TDAD paper (arXiv Mar 2026): TDD contextual
  - Reflexion (NeurIPS 2023): verbal reinforcement
  - developersdigest: Run Ledger pattern
  - Google SRE: canary release pattern
  - Anthropic CC Oct 2025: sandboxing dual

Uso:
    from forge import RunLedger, PersistentMemory, ForgeSandbox, GateRunner
"""

from forge.run_ledger import RunLedger
from forge.memory import PersistentMemory
from forge.sandbox import ForgeSandbox
from forge.gates import GateRunner

__all__ = [
    "RunLedger",
    "PersistentMemory",
    "ForgeSandbox",
    "GateRunner",
]
