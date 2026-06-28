"""
ORBITAL — Pilar 2: TOR (Tension Orbital Reciproca)
====================================================

Calcula la fuerza orbital reciproca entre todas las parejas de variables:

    TOR(i, j) = Ai * Aj * cos(theta_i - theta_j)

Propiedades de TOR:
- Simetrica: TOR(i,j) = TOR(j,i)
- Acotada: |TOR(i,j)| <= Ai * Aj
- Determinista: mismos theta y A → mismo TOR siempre
- Positiva cuando las fases estan alineadas (resonancia)
- Negativa cuando las fases estan opuestas (anti-resonancia)

TOR es la FUERZA que mantiene las variables en orbita mutua.
Sin TOR, las variables serian independientes (lineal).
Con TOR, las variables se influyen recíprocamente (circular).

Ejemplo de uso:
    >>> from src.orbital.ovc import OVC
    >>> from src.orbital.tor import TOR
    >>> ovc = OVC()
    >>> ovc.create_variable("Demanda", theta=0.0, amplitude=10.0)
    >>> ovc.create_variable("Precio", theta=0.3, amplitude=50.0)
    >>> tor = TOR(ovc)
    >>> result = tor.calculate("Demanda", "Precio")
    >>> print(f"TOR = {result.tor_value:.4f}, Alineacion = {result.alignment:.4f}")
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any

from src.core.logging import setup_logging
from src.orbital.models import TORResult, VariableOrbital

logger = setup_logging(__name__)


class TOR:
    """
    Tension Orbital Reciproca — Calculador de fuerzas orbitales.

    Calcula la tension orbital entre parejas de variables, generando
    una matriz de tensiones que describe el estado de las interacciones
    reciprocas en el sistema orbital.

    Incluye cache de tensiones: si las fases de una pareja no han cambiado
    desde el ultimo calculo, retorna el valor cachead en lugar de recalcular.
    Esto reduce el costo computacional de O(N^2) a O(cambios) por tick.

    La tension orbital es la base para:
    - RCC: resonancia cuando TOR > umbral
    - COD: colapso basado en tensiones acumuladas
    - Espectro: modos deterministas derivados de las tensiones
    """

    def __init__(self, ovc):
        """
        Inicializa el calculador TOR.

        Args:
            ovc: Instancia de OVC que contiene las variables orbitales
        """
        self._ovc = ovc
        # ── Cache de tensiones ──────────────────────────────────
        # _cache[(name_i, name_j)] = (phase_diff_hash, tor_value, alignment, is_resonant)
        # Si las fases no cambiaron, se reusa el valor cachead.
        # El hash de fase_diff evita recalcular cos() si la diferencia no cambio.
        self._cache: dict[tuple[str, str], tuple[float, float, float, bool]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    @property
    def cache_stats(self) -> dict[str, Any]:
        """Estadisticas del cache de tensiones."""
        total = self._cache_hits + self._cache_misses
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": round(self._cache_hits / total, 4) if total > 0 else 0,
            "cache_size": len(self._cache),
        }

    def clear_cache(self) -> None:
        """Limpia el cache de tensiones."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    # ── Calculo individual ─────────────────────────────────

    def calculate(self, name_i: str, name_j: str, threshold: float = 0.0) -> TORResult:
        """
        Calcula la tension orbital reciproca entre dos variables.

        TOR(i,j) = Ai * Aj * cos(theta_i - theta_j)

        Args:
            name_i: Nombre de la primera variable
            name_j: Nombre de la segunda variable
            threshold: Umbral para considerar resonancia (0 = sin filtro)

        Returns:
            TORResult con el valor de tension y metadatos

        Raises:
            KeyError: Si alguna variable no existe
        """
        var_i = self._ovc.get_variable(name_i)
        var_j = self._ovc.get_variable(name_j)

        if var_i is None:
            raise KeyError(f"Variable no encontrada: {name_i}")
        if var_j is None:
            raise KeyError(f"Variable no encontrada: {name_j}")

        return self._compute_tor(var_i, var_j, threshold)

    def _compute_tor(self, var_i: VariableOrbital, var_j: VariableOrbital, threshold: float = 0.0) -> TORResult:
        """
        Calculo interno de TOR entre dos VariableOrbital con cache.

        Formula: TOR = Ai * Aj * cos(theta_i - theta_j)

        Cachea resultados por pareja simetrica. Si las fases no cambiaron
        desde el ultimo calculo, retorna el valor cachead (O(1) en vez de
        recalcular cos().
        """
        # Usar clave simetrica: orden alfabetico para cache
        pair_key = (var_i.name, var_j.name) if var_i.name < var_j.name else (var_j.name, var_i.name)
        phase_diff = var_i.theta - var_j.theta
        # Hash de la diferencia de fase (redondeado a 8 decimales)
        phase_hash = round(phase_diff, 8)

        # Cache lookup
        if pair_key in self._cache:
            cached_hash, _cached_value, cached_alignment, _cached_resonant = self._cache[pair_key]
            if cached_hash == phase_hash:
                self._cache_hits += 1
                # Amplitudes pueden cambiar aunque las fases no
                tor_value = var_i.amplitude * var_j.amplitude * cached_alignment
                # Fix bug: threshold=0 debe significar "cualquier tensión > 0 es resonante",
                # no "nunca resonante". Antes: `if threshold > 0 else False` era siempre False con default 0.
                is_resonant = abs(tor_value) > threshold
                result = TORResult(
                    variable_i=var_i.name,
                    variable_j=var_j.name,
                    tor_value=tor_value,
                    phase_diff=phase_diff,
                    alignment=cached_alignment,
                    is_resonant=is_resonant,
                )
                return result

        # Miss — recalcular
        self._cache_misses += 1
        alignment = math.cos(phase_diff)
        tor_value = var_i.amplitude * var_j.amplitude * alignment
        # Fix bug: misma lógica que en el cache hit.
        is_resonant = abs(tor_value) > threshold

        # Actualizar cache
        self._cache[pair_key] = (phase_hash, tor_value, alignment, is_resonant)

        result = TORResult(
            variable_i=var_i.name,
            variable_j=var_j.name,
            tor_value=tor_value,
            phase_diff=phase_diff,
            alignment=alignment,
            is_resonant=is_resonant,
        )

        logger.debug(
            f"TOR({var_i.name}, {var_j.name}) = {tor_value:.4f} (alineacion={alignment:.4f}, resonante={is_resonant})"
        )

        return result

    # ── Calculo de matriz completa ──────────────────────────

    def calculate_matrix(self, threshold: float = 0.0) -> list[TORResult]:
        """
        Calcula TOR para TODAS las parejas de variables.

        Genera la matriz completa de tensiones orbitales reciprocas.
        Para N variables, produce N*(N-1)/2 resultados.

        Args:
            threshold: Umbral de resonancia

        Returns:
            Lista de TORResult, uno por cada pareja
        """
        variables = list(self._ovc.get_all_variables().values())
        results = []

        for var_i, var_j in combinations(variables, 2):
            result = self._compute_tor(var_i, var_j, threshold)
            results.append(result)

        logger.info(f"TOR: Matriz calculada — {len(results)} parejas de {len(variables)} variables")
        return results

    def calculate_for_cycle(self, variable_names: list[str], threshold: float = 0.0) -> list[TORResult]:
        """
        Calcula TOR solo para las variables de un ciclo especifico.

        Args:
            variable_names: Nombres de las variables del ciclo
            threshold: Umbral de resonancia

        Returns:
            Lista de TORResult para las parejas del ciclo
        """
        results = []
        for i in range(len(variable_names)):
            for j in range(i + 1, len(variable_names)):
                name_i = variable_names[i]
                name_j = variable_names[j]
                var_i = self._ovc.get_variable(name_i)
                var_j = self._ovc.get_variable(name_j)
                if var_i and var_j:
                    result = self._compute_tor(var_i, var_j, threshold)
                    results.append(result)
        return results

    # ── Consultas derivadas ────────────────────────────────

    def get_total_tension(self, threshold: float = 0.0) -> float:
        """
        Suma total de todas las tensiones orbitales.

        Representa la "energia" total del sistema orbital.
        Sistema en resonancia: tension total alta.
        Sistema caotico: tension total baja (se cancelan).
        """
        results = self.calculate_matrix(threshold)
        return sum(r.tor_value for r in results)

    def get_average_tension(self, threshold: float = 0.0) -> float:
        """Tension orbital promedio del sistema."""
        results = self.calculate_matrix(threshold)
        if not results:
            return 0.0
        return sum(r.tor_value for r in results) / len(results)

    def get_strongest_pair(self, threshold: float = 0.0) -> TORResult | None:
        """Retorna la pareja con mayor tension orbital absoluta."""
        results = self.calculate_matrix(threshold)
        if not results:
            return None
        return max(results, key=lambda r: abs(r.tor_value))

    def get_resonant_pairs(self, threshold: float) -> list[TORResult]:
        """Retorna solo las parejas en resonancia (|TOR| > threshold)."""
        results = self.calculate_matrix(threshold)
        return [r for r in results if r.is_resonant]

    # ── Aplicacion de tensiones ────────────────────────────

    def apply_tensions_to_ovc(self, tor_results: list[TORResult], dt: float = 1.0, scale: float = 0.01) -> None:
        """
        Aplica los resultados TOR como tensiones moduladoras al OVC.

        Cada variable recibe la suma de tensiones de todas sus parejas,
        escalada por el factor `scale` para mantener estabilidad.

        Esto crea el efecto ORBITAL: las variables se influyen mutuamente
        a traves de sus tensiones reciprocas, cerrando el ciclo.

        Args:
            tor_results: Resultados TOR a aplicar
            dt: Paso temporal
            scale: Factor de escala para las tensiones (evitar divergencia)
        """
        # Acumular tensiones por variable
        tension_accum: dict[str, float] = {}
        for result in tor_results:
            tension_accum[result.variable_i] = tension_accum.get(result.variable_i, 0.0) + result.tor_value
            tension_accum[result.variable_j] = tension_accum.get(result.variable_j, 0.0) + result.tor_value

        # Aplicar tensiones escaladas
        scaled_tensions = {name: t * scale for name, t in tension_accum.items()}
        self._ovc.apply_tensions(scaled_tensions, dt)

        logger.debug(f"TOR: Tensiones aplicadas a {len(scaled_tensions)} variables (scale={scale})")

    # ── Representacion ─────────────────────────────────────

    def __repr__(self) -> str:
        return f"TOR(ovc={self._ovc})"

    def matrix_summary(self, threshold: float = 0.0) -> str:
        """Retorna un resumen legible de la matriz de tensiones."""
        results = self.calculate_matrix(threshold)
        lines = ["TOR — Matriz de Tensiones Orbitales Reciprocas"]
        lines.append(f"  Parejas: {len(results)}")
        if results:
            total = sum(r.tor_value for r in results)
            avg = total / len(results)
            max_r = max(results, key=lambda r: abs(r.tor_value))
            lines.append(f"  Total: {total:.4f} | Promedio: {avg:.4f}")
            lines.append(f"  Max: TOR({max_r.variable_i}, {max_r.variable_j}) = {max_r.tor_value:.4f}")
            for r in sorted(results, key=lambda x: abs(x.tor_value), reverse=True):
                resonant = " ★" if r.is_resonant else ""
                lines.append(
                    f"    TOR({r.variable_i}, {r.variable_j}) = "
                    f"{r.tor_value:8.4f} alineacion={r.alignment:+.4f}"
                    f"{resonant}"
                )
        return "\n".join(lines)
