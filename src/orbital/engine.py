"""
ORBITAL — OrbitalEngine: Coordinador de los 5 pilares
======================================================

El OrbitalEngine coordina los 5 pilares del motor ORBITAL en un ciclo
completo y cerrado:

    OVC → TOR → RCC → COD → Espectro → Retroalimentacion → OVC

Cada tick orbital ejecuta el ciclo completo:
1. OVC: Avanzar fases de las variables orbitales
2. TOR: Calcular tensiones reciprocas entre todas las parejas
3. RCC: Detectar resonancia en los ciclos cerrados
4. COD: Colapsar orbitas a estados deterministas estables
5. Espectro: Generar salida multimodal determinista
6. Retroalimentacion: El espectro retroalimenta el OVC (CIERRA EL CICLO)

Este motor es CIRCULAR: el output retroalimenta el input.
No es lineal como el WorkflowEngine original (step1→step2→...→FIN).
Es orbital: variables→tension→resonancia→colapso→espectro→variables→...

Ejemplo de uso:
    >>> from src.orbital.engine import OrbitalEngine
    >>> engine = OrbitalEngine()
    >>> engine.create_variable("Demanda", theta=0.0, amplitude=10.0, velocity=0.15)
    >>> engine.create_variable("Precio", theta=0.3, amplitude=50.0, velocity=0.08)
    >>> engine.create_variable("Oferta", theta=0.5, amplitude=8.0, velocity=0.12)
    >>> engine.create_cycle("Economico", ["Demanda", "Precio", "Oferta"], threshold=0.5)
    >>> result = engine.run_tick()
    >>> print(result.espectro.primary)
"""

from __future__ import annotations

import time
from typing import Any

from src.orbital.cod import COD
from src.orbital.espectro import EspectroOrbital
from src.orbital.models import (
    DEFAULT_AMPLITUDE,
    DEFAULT_THRESHOLD,
    DEFAULT_VELOCITY,
    RETROFEEDBACK_DAMPING,
    CicloOrbital,
    EspectroEstado,
    OrbitalResult,
    VariableOrbital,
)
from src.orbital.ovc import OVC
from src.orbital.rcc import RCC
from src.orbital.tor import TOR
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class OrbitalEngine:
    """
    Motor Determinista Circular ORBITAL.

    Coordinador de los 5 pilares (OVC, TOR, RCC, COD, Espectro).
    Ejecuta ciclos orbitales completos donde el output retroalimenta el input,
    creando un sistema genuinamente circular y determinista.

    Diferencia con WorkflowEngine (lineal):
    - Lineal: step1→step2→step3→FIN (sin retroalimentacion)
    - ORBITAL: OVC→TOR→RCC→COD→Espectro→OVC→... (retroalimentacion circular)

    Puede inicializarse con instancias externas de los 5 pilares para
    compartir estado con OrbitalContext y otros componentes del sistema.
    Si no se proporcionan, crea sus propias instancias internas.
    """

    def __init__(
        self,
        ovc: OVC | None = None,
        tor: TOR | None = None,
        rcc: RCC | None = None,
        cod: COD | None = None,
        espectro: EspectroOrbital | None = None,
    ):
        """
        Inicializa el motor ORBITAL con los 5 pilares.

        Args:
            ovc: Instancia de OVC (si None, crea una nueva)
            tor: Instancia de TOR (si None, crea una nueva usando self._ovc)
            rcc: Instancia de RCC (si None, crea una nueva usando self._ovc y self._tor)
            cod: Instancia de COD (si None, crea una nueva)
            espectro: Instancia de EspectroOrbital (si None, crea una nueva)

        Cuando OrbitalContext pasa sus propias instancias, el engine
        comparte el mismo OVC con todos los demas componentes del sistema.
        """
        self._ovc = ovc if ovc is not None else OVC()
        self._tor = tor if tor is not None else TOR(self._ovc)
        self._rcc = rcc if rcc is not None else RCC(self._ovc, self._tor)
        self._cod = cod if cod is not None else COD(self._ovc, self._tor, self._rcc)
        self._espectro = (
            espectro if espectro is not None else EspectroOrbital(self._ovc, self._tor, self._rcc, self._cod)
        )
        self._owns_pillars = ovc is None  # True si creamos nuestras propias instancias
        self._global_tick: int = 0
        self._execution_history: list[OrbitalResult] = []

    # ── Propiedades ────────────────────────────────────────

    @property
    def ovc(self) -> OVC:
        """Acceso al modulo OVC."""
        return self._ovc

    @property
    def tor(self) -> TOR:
        """Acceso al modulo TOR."""
        return self._tor

    @property
    def rcc(self) -> RCC:
        """Acceso al modulo RCC."""
        return self._rcc

    @property
    def cod(self) -> COD:
        """Acceso al modulo COD."""
        return self._cod

    @property
    def espectro(self) -> EspectroOrbital:
        """Acceso al modulo Espectro."""
        return self._espectro

    @property
    def tick(self) -> int:
        """Tick orbital global."""
        return self._global_tick

    @property
    def variable_count(self) -> int:
        """Numero de variables orbitales."""
        return self._ovc.variable_count

    @property
    def cycle_count(self) -> int:
        """Numero de ciclos registrados."""
        return len(self._rcc._cycles)

    # ── Creacion de variables ──────────────────────────────

    def create_variable(
        self,
        name: str,
        theta: float = 0.0,
        amplitude: float = DEFAULT_AMPLITUDE,
        velocity: float = DEFAULT_VELOCITY,
        orbit_group: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> VariableOrbital:
        """
        Crea una variable orbital en el motor.

        Args:
            name: Nombre de la variable
            theta: Fase inicial en radianes
            amplitude: Amplitud (magnitud)
            velocity: Velocidad orbital (rad/tick)
            orbit_group: Grupo orbital
            metadata: Datos adicionales

        Returns:
            VariableOrbital creada
        """
        return self._ovc.create_variable(
            name=name,
            theta=theta,
            amplitude=amplitude,
            velocity=velocity,
            orbit_group=orbit_group,
            metadata=metadata,
        )

    def create_variables_batch(self, specs: list[dict[str, Any]]) -> list[VariableOrbital]:
        """Crea multiples variables orbitales de una vez."""
        return self._ovc.create_variables_batch(specs)

    # ── Creacion de ciclos ─────────────────────────────────

    def create_cycle(
        self,
        name: str,
        variable_names: list[str],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> CicloOrbital:
        """
        Crea y registra un ciclo orbital cerrado.

        Args:
            name: Nombre del ciclo
            variable_names: Variables que forman el ciclo
            threshold: Umbral de resonancia RCC

        Returns:
            CicloOrbital creado
        """
        return self._rcc.register_cycle_from_names(name, variable_names, threshold)

    # ── Ejecucion orbital ──────────────────────────────────

    def run_tick(self, dt: float = 1.0, retrofeed_damping: float = RETROFEEDBACK_DAMPING) -> OrbitalResult:
        """
        Ejecuta un tick orbital completo: OVC → TOR → RCC → COD → Espectro → Retro.

        Este es el ciclo central del motor ORBITAL. Cada tick:
        1. OVC: Avanza las fases de todas las variables
        2. TOR: Calcula tensiones reciprocas
        3. RCC: Detecta resonancia en cada ciclo
        4. COD: Colapsa orbitas a estados estables
        5. Espectro: Genera salida multimodal determinista
        6. Retro: El espectro retroalimenta el OVC (CIERRA EL CICLO)

        Args:
            dt: Paso temporal
            retrofeed_damping: Factor de retroalimentacion [0, 1]

        Returns:
            OrbitalResult con el estado completo del sistema
        """
        start_time = time.time()
        self._global_tick += 1

        logger.info(f"=== ORBITAL Tick {self._global_tick} ===")

        # 1. OVC: Avanzar fases
        self._ovc.advance_all(dt)

        # 2. TOR: Calcular matriz de tensiones
        tor_results = self._tor.calculate_matrix()

        # 3. RCC: Detectar resonancia en cada ciclo
        rcc_results = self._rcc.detect_all()

        # 4. COD: Colapsar cada ciclo (con retroalimentacion)
        cod_results = []
        for cycle in self._rcc._cycles.values():
            cod_result = self._cod.collapse_with_retrofeedback(cycle, retrofeed_damping=retrofeed_damping, dt=dt)
            cod_results.append(cod_result)

        # 5. Espectro: Generar salida multimodal para cada ciclo
        espectro_estados = self._espectro.generate_all(retrofeed_damping)

        # 6. Recopilar resultado
        duration_ms = int((time.time() - start_time) * 1000)

        result = OrbitalResult(
            tick=self._global_tick,
            variables=self._ovc.get_all_variables(),
            tor_results=tor_results,
            rcc_results=rcc_results,
            cod_results=cod_results,
            espectro=espectro_estados[0] if espectro_estados else EspectroEstado(),
            duration_ms=duration_ms,
        )

        # Guardar en historial
        self._execution_history.append(result)

        logger.info(
            f"ORBITAL Tick {self._global_tick} completado en {duration_ms}ms — "
            f"TOR={len(tor_results)} RCC={len(rcc_results)} COD={len(cod_results)}"
        )

        return result

    def run_ticks(
        self, n: int, dt: float = 1.0, retrofeed_damping: float = RETROFEEDBACK_DAMPING
    ) -> list[OrbitalResult]:
        """
        Ejecuta N ticks orbitales consecutivos.

        Args:
            n: Numero de ticks a ejecutar
            dt: Paso temporal por tick
            retrofeed_damping: Factor de retroalimentacion

        Returns:
            Lista de OrbitalResult, uno por tick
        """
        results = []
        for _ in range(n):
            result = self.run_tick(dt=dt, retrofeed_damping=retrofeed_damping)
            results.append(result)
        return results

    # ── Consultas ──────────────────────────────────────────

    def get_variable(self, name: str) -> VariableOrbital | None:
        """Obtiene una variable orbital por nombre."""
        return self._ovc.get_variable(name)

    def get_all_variables(self) -> dict[str, VariableOrbital]:
        """Retorna todas las variables orbitales."""
        return self._ovc.get_all_variables()

    def get_value_snapshot(self) -> dict[str, float]:
        """Snapshot de valores actuales de todas las variables."""
        return self._ovc.get_value_snapshot()

    def get_phase_snapshot(self) -> dict[str, float]:
        """Snapshot de fases actuales de todas las variables."""
        return self._ovc.get_phase_snapshot()

    def get_execution_history(self, limit: int = 10) -> list[OrbitalResult]:
        """Retorna los ultimos N resultados de ejecucion."""
        return self._execution_history[-limit:]

    # ── Configuracion ──────────────────────────────────────

    def configure_cod(
        self,
        epsilon: float | None = None,
        max_iterations: int | None = None,
        convergence_scale: float | None = None,
    ) -> None:
        """Configura los parametros del COD."""
        self._cod.configure(epsilon, max_iterations, convergence_scale)

    # ── Reset ──────────────────────────────────────────────

    def reset(self) -> None:
        """Reinicia completamente el motor ORBITAL."""
        self._ovc.reset()
        self._espectro.reset()
        self._global_tick = 0
        self._execution_history.clear()
        # Recrear TOR, RCC, COD con el OVC reseteado (compartido)
        self._tor = TOR(self._ovc)
        self._rcc = RCC(self._ovc, self._tor)
        self._cod = COD(self._ovc, self._tor, self._rcc)
        self._espectro = EspectroOrbital(self._ovc, self._tor, self._rcc, self._cod)
        self._owns_pillars = True  # Ahora somos duenos de las nuevas instancias
        logger.info("OrbitalEngine: Reset completo")

    # ── Representacion ─────────────────────────────────────

    def __repr__(self) -> str:
        return f"OrbitalEngine(tick={self._global_tick}, variables={self.variable_count}, cycles={self.cycle_count})"

    def status_summary(self) -> str:
        """Retorna un resumen completo del estado del motor ORBITAL."""
        lines = [
            "=" * 60,
            "ORBITAL — Motor Determinista Circular",
            "=" * 60,
            f"Tick: {self._global_tick} | Variables: {self.variable_count} | Ciclos: {self.cycle_count}",
            "",
            "OVC — Variables Orbitales:",
        ]
        lines.append(self._ovc.status_summary())
        lines.append("")
        lines.append("TOR — Tensiones Orbitales:")
        lines.append(self._tor.matrix_summary())
        lines.append("")
        lines.append("RCC — Resonancia:")
        lines.append(self._rcc.resonance_report())
        lines.append("")
        lines.append("Espectro Orbital:")
        lines.append(self._espectro.spectrum_summary())
        lines.append("=" * 60)
        return "\n".join(lines)
