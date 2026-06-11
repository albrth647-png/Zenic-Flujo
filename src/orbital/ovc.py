"""
ORBITAL — Pilar 1: OVC (Orbita Variable Circular)
===================================================

La unidad fundamental del motor ORBITAL. Cada variable tiene:
- Fase theta: posicion angular actual en [0, 2pi)
- Amplitud A: magnitud de la variable (> 0)
- Velocidad omega: tasa de cambio de fase (rad/tick)

Las variables NO son estaticas como en un sistema lineal.
Orbitan mutuamente: el cambio en una variable afecta la fase de las demas
a traves de la tension orbital (TOR).

Ejemplo de uso:
    >>> from src.orbital.ovc import OVC
    >>> ovc = OVC()
    >>> demanda = ovc.create_variable("Demanda", theta=0.0, amplitude=10.0, velocity=0.15)
    >>> precio = ovc.create_variable("Precio", theta=math.pi/4, amplitude=50.0, velocity=0.08)
    >>> ovc.advance_all(dt=1.0)
    >>> print(demanda.value, precio.value)
"""

from __future__ import annotations

from typing import Any

from src.orbital.models import DEFAULT_AMPLITUDE, DEFAULT_VELOCITY, VariableOrbital
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class OVC:
    """
    Orbita Variable Circular — Gestor de variables orbitales.

    Mantiene el registro de todas las variables orbitales del sistema,
    gestiona su avance de fase y proporciona consultas sobre el estado
    orbital actual.

    Responsabilidades:
    - Crear y registrar variables orbitales
    - Avanzar la fase de todas las variables (o seleccionadas)
    - Aplicar tension orbital a variables especificas
    - Retroalimentar outputs a inputs (cerrar el ciclo)
    - Consultar estado actual de las variables
    """

    def __init__(self):
        self._variables: dict[str, VariableOrbital] = {}
        self._tick: int = 0

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
        Crea una nueva variable orbital y la registra en el sistema.

        Args:
            name: Nombre descriptivo de la variable
            theta: Fase inicial en radianes [0, 2pi)
            amplitude: Amplitud (magnitud) de la variable
            velocity: Velocidad orbital en radianes/tick
            orbit_group: Grupo orbital para clasificacion
            metadata: Datos adicionales

        Returns:
            VariableOrbital creada

        Raises:
            ValueError: Si ya existe una variable con ese nombre
        """
        if name in self._variables:
            raise ValueError(f"Variable orbital ya existe: {name}")

        var = VariableOrbital(
            name=name,
            theta=theta,
            amplitude=amplitude,
            velocity=velocity,
            orbit_group=orbit_group,
            metadata=metadata or {},
        )
        self._variables[name] = var
        logger.info(f"OVC: Variable creada '{name}' θ={var.phase_degrees:.1f}° A={amplitude:.2f} ω={velocity:.3f}")
        return var

    def create_variables_batch(self, specs: list[dict[str, Any]]) -> list[VariableOrbital]:
        """
        Crea multiples variables orbitales de una vez.

        Args:
            specs: Lista de diccionarios con los parametros de cada variable

        Returns:
            Lista de VariableOrbital creadas

        Ejemplo:
            >>> ovc.create_variables_batch([
            ...     {"name": "Demanda", "theta": 0.0, "amplitude": 10.0, "velocity": 0.15},
            ...     {"name": "Precio", "theta": 0.785, "amplitude": 50.0, "velocity": 0.08},
            ...     {"name": "Oferta", "theta": 1.571, "amplitude": 8.0, "velocity": 0.12},
            ... ])
        """
        created = []
        for spec in specs:
            var = self.create_variable(**spec)
            created.append(var)
        return created

    # ── Avance orbital ─────────────────────────────────────

    def advance_all(self, dt: float = 1.0) -> None:
        """
        Avanza la fase orbital de TODAS las variables.

        Cada variable avanza: theta += omega * dt
        Despues se normaliza a [0, 2pi).

        Args:
            dt: Paso temporal (1.0 = un tick orbital)
        """
        self._tick += 1
        for var in self._variables.values():
            var.advance(dt)
        logger.debug(f"OVC: Tick {self._tick} — todas las variables avanzadas (dt={dt})")

    def advance_variable(self, name: str, dt: float = 1.0) -> None:
        """Avanza solo una variable orbital especifica."""
        if name not in self._variables:
            raise KeyError(f"Variable no encontrada: {name}")
        self._variables[name].advance(dt)

    # ── Aplicacion de tension ──────────────────────────────

    def apply_tension(self, name: str, tension: float, dt: float = 1.0) -> None:
        """
        Aplica tension orbital a una variable.

        La tension modula la velocidad orbital via tanh:
            theta += tanh(tension) * omega * dt

        Esto mantiene el sistema acotado y determinista.

        Args:
            name: Nombre de la variable
            tension: Valor de tension (positivo = acelera, negativo = desacelera)
            dt: Paso temporal
        """
        if name not in self._variables:
            raise KeyError(f"Variable no encontrada: {name}")
        self._variables[name].apply_tension(tension, dt)
        logger.debug(f"OVC: Tension {tension:.4f} aplicada a '{name}'")

    def apply_tensions(self, tensions: dict[str, float], dt: float = 1.0) -> None:
        """
        Aplica tensiones orbitales a multiples variables simultaneamente.

        Args:
            tensions: Diccionario {nombre_variable: valor_tension}
            dt: Paso temporal
        """
        for name, tension in tensions.items():
            if name in self._variables:
                self._variables[name].apply_tension(tension, dt)

    # ── Retroalimentacion ──────────────────────────────────

    def retrofeed(self, outputs: dict[str, float], damping: float = 0.3) -> None:
        """
        Retroalimenta outputs al input del sistema (CIERRA EL CICLO).

        Esta es la diferencia fundamental con un sistema lineal:
        el output vuelve a modificar el input, creando un ciclo cerrado.

        Args:
            outputs: Diccionario {nombre_variable: valor_retroalimentacion}
            damping: Factor de amortiguacion [0, 1] (0=sin efecto, 1=efecto total)
        """
        for name, output_value in outputs.items():
            if name in self._variables:
                self._variables[name].retrofeed(output_value, damping)
        logger.info(f"OVC: Retroalimentacion aplicada a {len(outputs)} variables (damping={damping})")

    # ── Consultas ──────────────────────────────────────────

    def get_variable(self, name: str) -> VariableOrbital | None:
        """Obtiene una variable orbital por nombre."""
        return self._variables.get(name)

    def get_all_variables(self) -> dict[str, VariableOrbital]:
        """Retorna todas las variables orbitales registradas."""
        return dict(self._variables)

    def get_variables_by_group(self, group: str) -> list[VariableOrbital]:
        """Filtra variables por grupo orbital."""
        return [v for v in self._variables.values() if v.orbit_group == group]

    def get_variable_names(self) -> list[str]:
        """Retorna los nombres de todas las variables."""
        return list(self._variables.keys())

    def get_phase_snapshot(self) -> dict[str, float]:
        """
        Retorna un snapshot de las fases actuales de todas las variables.

        Returns:
            Diccionario {nombre_variable: theta_actual}
        """
        return {name: var.theta for name, var in self._variables.items()}

    def get_value_snapshot(self) -> dict[str, float]:
        """
        Retorna un snapshot de los valores actuales de todas las variables.

        Returns:
            Diccionario {nombre_variable: valor_actual = A*cos(theta)}
        """
        return {name: var.value for name, var in self._variables.items()}

    # ── Propiedades ────────────────────────────────────────

    @property
    def tick(self) -> int:
        """Tick orbital actual."""
        return self._tick

    @property
    def variable_count(self) -> int:
        """Numero de variables orbitales registradas."""
        return len(self._variables)

    # ── Reset ──────────────────────────────────────────────

    def reset(self) -> None:
        """Elimina todas las variables y reinicia el tick."""
        self._variables.clear()
        self._tick = 0
        logger.info("OVC: Reset completo")

    # ── Representacion ─────────────────────────────────────

    def __repr__(self) -> str:
        return f"OVC(variables={self.variable_count}, tick={self._tick})"

    def status_summary(self) -> str:
        """Retorna un resumen legible del estado OVC."""
        lines = [f"OVC — Tick: {self._tick} | Variables: {self.variable_count}"]
        for name, var in self._variables.items():
            lines.append(
                f"  {name}: θ={var.phase_degrees:6.1f}° "
                f"A={var.amplitude:6.2f} val={var.value:7.3f} "
                f"ω={var.velocity:.3f}"
            )
        return "\n".join(lines)
