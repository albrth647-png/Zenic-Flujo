"""
ORBITAL — Motor Determinista Circular (Fase 3: ACTIVACION COMPLETA)
====================================================================

5 Pilares del motor ORBITAL:
1. OVC  (Orbita Variable Circular)  — Variables con fase, amplitud y velocidad orbital
2. TOR  (Tension Orbital Reciproca) — Fuerza computable entre variables orbitantes
3. RCC  (Resonancia Ciclo Cerrado)  — Deteccion de resonancia determinista
4. COD  (Colapso Orbital Determinista) — Convergencia garantizada via punto fijo
5. ESPECTRO (Espectro Orbital)      — Salida multimodal determinista que retroalimenta

OrbitalContext — Singleton compartido:
- OVC unificado entre TODOS los componentes del sistema
- Lo que un componente retroalimenta, todos los demas lo ven
- Estado orbital coherente: una sola fuente de verdad

Componentes Integrados (Motor Unico — OVC Compartido):
- WorkflowEngine     → Orbital (OVC compartido via OrbitalContext)
- StepExecutor       → Orbital (OVC compartido via OrbitalContext)
- EventBus           → Orbital (OVC compartido via OrbitalContext)
- ConditionEvaluator → ResonanceDetector (OVC compartido via OrbitalContext)
- BranchHandler      → OrbitalDivergence (OVC compartido via OrbitalContext)
- LoopHandler        → OrbitalConvergence (OVC compartido via OrbitalContext)
- ErrorHandler       → OrbitalRecovery (OVC compartido via OrbitalContext)
- OrbitalCompiler    → Compilacion orbital (reemplaza NLU 13 etapas)
- OrbitalAdapter     → Adaptador de herramientas de negocio
- OrbitalRepository  → Conversion y almacenamiento orbital

Paradigma: CIRCULAR — Las variables orbitan mutuamente, el output retroalimenta el input.
Diferencia clave vs lineal: No hay cadena causa→efecto unidireccional.
Todo es reciproco, todo converge, todo retroalimenta.
"""

from src.orbital.cod import COD
from src.orbital.context import OrbitalContext
from src.orbital.engine import OrbitalEngine
from src.orbital.espectro import EspectroOrbital
from src.orbital.models import (
    CicloOrbital,
    CODResult,
    EspectroEstado,
    OrbitalResult,
    RCCResult,
    TORResult,
    VariableOrbital,
)
from src.orbital.orbital_adapter import OrbitalAdapter
from src.orbital.orbital_compiler import OrbitalCompiler
from src.orbital.orbital_repository import OrbitalRepository
from src.orbital.ovc import OVC
from src.orbital.rcc import RCC
from src.orbital.tor import TOR

__all__ = [
    "COD",
    "OVC",
    "RCC",
    "TOR",
    "CODResult",
    "CicloOrbital",
    "EspectroEstado",
    "EspectroOrbital",
    "OrbitalAdapter",
    "OrbitalCompiler",
    "OrbitalContext",
    "OrbitalEngine",
    "OrbitalRepository",
    "OrbitalResult",
    "RCCResult",
    "TORResult",
    "VariableOrbital",
]

__version__ = "3.1.0"
