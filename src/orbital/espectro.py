"""
ORBITAL — Pilar 5: Espectro Orbital
=====================================

Salida multimodal determinista del sistema ORBITAL.
El espectro NO es probabilidad: es el conjunto de ESTADOS del sistema
circular despues del colapso orbital.

Cada modo del espectro representa un estado estable posible del sistema.
El modo primario es el estado con mayor resonancia (mayor alineacion de fases).

Caracteristica clave: el output RETROALIMENTA el input.
Esto cierra el ciclo y hace que el sistema sea genuinamente circular:
    input → OVC → TOR → RCC → COD → Espectro → retro → input

El Espectro Orbital produce:
1. Modos deterministas: estados estables del sistema (no probabilidades)
2. Modo primario: el estado con mayor resonancia
3. Retroalimentacion: output que vuelve al input para el proximo tick

Ejemplo de uso:
    >>> from src.orbital.espectro import EspectroOrbital
    >>> espectro = EspectroOrbital(ovc, tor, rcc, cod)
    >>> estado = espectro.generate(cycle)
    >>> print(estado.primary)  # Estado determinista primario
    >>> print(estado.retrofeedback)  # Valores que retroalimentan
"""

from __future__ import annotations

import math
from typing import Any

from src.core.logging import setup_logging
from src.orbital.models import (
    TWO_PI,
    CicloOrbital,
    CODResult,
    EspectroEstado,
    RCCResult,
)

logger = setup_logging(__name__)


class EspectroOrbital:
    """
    Espectro Orbital — Generador de estados deterministas multimodales.

    Genera el espectro de estados del sistema orbital despues del colapso.
    Cada modo representa un estado determinista (no probabilistico) del
    sistema circular.

    El espectro retroalimenta el input, cerrando el ciclo ORBITAL completo:
    Las variables orbitan → generan tension → resonan → colapsan →
    producen espectro → el espectro retroalimenta las variables →
    y el ciclo se repite.
    """

    def __init__(self, ovc, tor, rcc, cod):
        """
        Inicializa el generador de espectro orbital.

        Args:
            ovc: Instancia de OVC
            tor: Instancia de TOR
            rcc: Instancia de RCC
            cod: Instancia de COD
        """
        self._ovc = ovc
        self._tor = tor
        self._rcc = rcc
        self._cod = cod
        self._tick: int = 0
        self._history: list[EspectroEstado] = []

    # ── Generacion de espectro ─────────────────────────────

    def generate(self, cycle: CicloOrbital, retrofeed_damping: float = 0.3) -> EspectroEstado:
        """
        Genera el espectro orbital para un ciclo.

        Proceso:
        1. Verificar resonancia (RCC)
        2. Colapsar el ciclo (COD)
        3. Generar modos del espectro a partir del estado colapsado
        4. Seleccionar modo primario (mayor resonancia)
        5. Calcular retroalimentacion
        6. Aplicar retroalimentacion al OVC (cierra el ciclo)

        Args:
            cycle: CicloOrbital a analizar
            retrofeed_damping: Factor de amortiguacion de retroalimentacion

        Returns:
            EspectroEstado con los modos y retroalimentacion
        """
        self._tick += 1

        # 1. Verificar resonancia
        rcc_result = self._rcc.detect(cycle)

        # 2. Colapsar (con retroalimentacion)
        cod_result = self._cod.collapse_with_retrofeedback(cycle, retrofeed_damping=retrofeed_damping)

        # 3. Generar modos del espectro
        modes = self._generate_modes(cycle, cod_result, rcc_result)

        # 4. Seleccionar modo primario
        primary_mode = self._select_primary_mode(modes, rcc_result)

        # 5. Calcular retroalimentacion
        retrofeedback = self._calculate_retrofeedback(cod_result, rcc_result, retrofeed_damping)

        # 6. Crear estado del espectro
        estado = EspectroEstado(
            modes=modes,
            primary_mode=primary_mode,
            retrofeedback=retrofeedback,
            tick=self._tick,
        )

        # Guardar en historial
        self._history.append(estado)

        logger.info(
            f"Espectro: Tick {self._tick} — {len(modes)} modos, "
            f"primario={primary_mode}, resonancia={rcc_result.resonance_strength:.4f}, "
            f"convergio={cod_result.converged}"
        )

        return estado

    def generate_all(self, retrofeed_damping: float = 0.3) -> list[EspectroEstado]:
        """
        Genera espectro para TODOS los ciclos registrados.

        Args:
            retrofeed_damping: Factor de retroalimentacion

        Returns:
            Lista de EspectroEstado, uno por ciclo
        """
        estados = []
        for cycle in self._rcc._cycles.values():
            estado = self.generate(cycle, retrofeed_damping)
            estados.append(estado)
        return estados

    # ── Generacion de modos ────────────────────────────────

    def _generate_modes(
        self,
        cycle: CicloOrbital,
        cod_result: CODResult,
        rcc_result: RCCResult,
    ) -> list[dict[str, float]]:
        """
        Genera los modos deterministas del espectro.

        Un modo es un estado completo del sistema: {variable: valor}.
        Se generan multiples modos a partir del estado colapsado:

        1. Modo colapsado: estado despues del COD (modo primario)
        2. Modo anti-fase: fases desplazadas pi/2 (ortogonal)
        3. Modo opuesto: fases desplazadas pi (anti-alineado)

        Estos NO son probabilidades: son estados DETERMINISTAS del sistema.
        El sistema puede estar en cualquiera de estos estados segun su
        trayectoria orbital.
        """
        if not cod_result.final_values:
            return [{}]

        # Modo 1: Estado colapsado (primario)
        primary_mode = dict(cod_result.final_values)

        # Modo 2: Estado con fases desplazadas pi/2 (ortogonal)
        orthogonal_mode = {}
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                orthogonal_theta = (var.theta + math.pi / 2) % TWO_PI
                orthogonal_mode[var_name] = var.amplitude * math.cos(orthogonal_theta)

        # Modo 3: Estado con fases desplazadas pi (opuesto)
        opposite_mode = {}
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                opposite_theta = (var.theta + math.pi) % TWO_PI
                opposite_mode[var_name] = var.amplitude * math.cos(opposite_theta)

        modes = [primary_mode, orthogonal_mode, opposite_mode]

        # Modo 4: Estado de maxima resonancia (si hay resonancia)
        if rcc_result.is_resonant:
            max_resonance_mode = {}
            for var_name in cycle.variable_ids:
                var = self._ovc.get_variable(var_name)
                if var:
                    # En maxima resonancia, todas las variables tienen la misma fase
                    # Usamos la fase de la variable con mayor amplitud como referencia
                    max_resonance_mode[var_name] = var.amplitude  # cos(0) = 1
            modes.append(max_resonance_mode)

        return modes

    def _select_primary_mode(self, modes: list[dict[str, float]], rcc_result: RCCResult) -> int:
        """
        Selecciona el modo primario del espectro.

        Criterio: el modo con mayor "energia" (suma de valores absolutos),
        ponderado por la fuerza de resonancia. Si hay resonancia activa,
        el modo de maxima resonancia es preferido.
        """
        if not modes:
            return 0

        best_idx = 0
        best_score = float("-inf")

        for i, mode in enumerate(modes):
            if not mode:
                continue
            energy = sum(abs(v) for v in mode.values())
            # Bonus para el modo de maxima resonancia (ultimo si hay resonancia)
            bonus = rcc_result.resonance_strength if (i == len(modes) - 1 and rcc_result.is_resonant) else 0.0
            score = energy + bonus * 10  # peso fuerte a la resonancia
            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx

    def _calculate_retrofeedback(
        self,
        cod_result: CODResult,
        rcc_result: RCCResult,
        damping: float,
    ) -> dict[str, float]:
        """
        Calcula los valores de retroalimentacion del espectro al OVC.

        La retroalimentacion es proporcional a:
        - Los valores del estado colapsado
        - La fuerza de resonancia (mas resonancia = mas retroalimentacion)
        - El factor de amortiguacion

        Esto CIERRA EL CICLO: output → retro → input
        """
        retrofeedback = {}
        for var_name, value in cod_result.final_values.items():
            # Retroalimentacion = valor * resonancia * damping * escala
            retro_value = value * rcc_result.resonance_strength * damping * 0.01
            retrofeedback[var_name] = retro_value

        return retrofeedback

    # ── Consultas ──────────────────────────────────────────

    def get_history(self, limit: int = 10) -> list[EspectroEstado]:
        """Retorna los ultimos N estados del espectro."""
        return self._history[-limit:]

    def get_latest(self) -> EspectroEstado | None:
        """Retorna el ultimo estado del espectro."""
        return self._history[-1] if self._history else None

    @property
    def tick(self) -> int:
        """Tick orbital actual del espectro."""
        return self._tick

    @property
    def history_length(self) -> int:
        """Numero de estados en el historial."""
        return len(self._history)

    # ── Analisis de tendencia ──────────────────────────────

    def analyze_trend(self, window: int = 5) -> dict[str, Any]:
        """
        Analiza la tendencia del espectro en los ultimos N ticks.

        Detecta si el sistema esta:
        - Convergiendo: los modos se estabilizan
        - Oscilando: los modos alternan entre estados
        - Divergiendo: los modos se separan

        Returns:
            Diccionario con metricas de tendencia
        """
        if len(self._history) < 2:
            return {"trend": "insufficient_data", "ticks": len(self._history)}

        recent = self._history[-window:]

        # Calcular variacion del modo primario entre ticks consecutivos
        deltas = []
        for i in range(1, len(recent)):
            prev = recent[i - 1].primary
            curr = recent[i].primary
            if prev and curr:
                common_keys = set(prev.keys()) & set(curr.keys())
                if common_keys:
                    avg_delta = sum(abs(curr[k] - prev[k]) for k in common_keys) / len(common_keys)
                    deltas.append(avg_delta)

        if not deltas:
            return {"trend": "no_data", "ticks": len(recent)}

        avg_delta = sum(deltas) / len(deltas)

        if avg_delta < 0.001:
            trend = "converging"
        elif avg_delta < 0.1:
            trend = "oscillating"
        else:
            trend = "diverging"

        return {
            "trend": trend,
            "avg_delta": avg_delta,
            "ticks_analyzed": len(recent),
            "min_delta": min(deltas),
            "max_delta": max(deltas),
        }

    # ── Reset ──────────────────────────────────────────────

    def reset(self) -> None:
        """Reinicia el espectro y su historial."""
        self._tick = 0
        self._history.clear()
        logger.info("Espectro: Reset completo")

    # ── Representacion ─────────────────────────────────────

    def __repr__(self) -> str:
        return f"EspectroOrbital(tick={self._tick}, history={self.history_length})"

    def spectrum_summary(self) -> str:
        """Retorna un resumen legible del ultimo estado del espectro."""
        estado = self.get_latest()
        if not estado:
            return "Espectro Orbital — Sin estados generados"

        lines = ["Espectro Orbital — Estado Actual"]
        lines.append(f"  Tick: {estado.tick}")
        lines.append(f"  Modos: {len(estado.modes)}")
        lines.append(f"  Modo primario: #{estado.primary_mode}")
        lines.append("  Estado primario:")
        for name, value in estado.primary.items():
            lines.append(f"    {name}: {value:.4f}")
        if estado.retrofeedback:
            lines.append("  Retroalimentacion:")
            for name, value in estado.retrofeedback.items():
                lines.append(f"    {name} ← {value:.6f}")

        # Tendencia
        trend = self.analyze_trend()
        lines.append(f"  Tendencia: {trend.get('trend', '?')} (delta={trend.get('avg_delta', 0):.6f})")

        return "\n".join(lines)
