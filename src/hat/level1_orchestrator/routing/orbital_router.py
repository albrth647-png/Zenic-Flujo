"""HAT-ORBITAL Nivel 1 — Orbital Router (cerebro central de routing).

Phase 1: ORBITAL ejecuta su ciclo COMPLETO por cada request:
  OVC → TOR → RCC → COD → Espectro → Retro → OVC

El router ya no calcula TOR manualmente. Ahora:
1. Crea la variable user_intent en el OVC.
2. Registra un ciclo RCC por cada dominio (intent + agent_cards del dominio).
3. Ejecuta ``ctx.run_tick()`` — el motor ORBITAL procesa el ciclo completo:
   - TOR calcula tensiones entre todas las variables.
   - RCC detecta resonancia en cada ciclo de dominio.
   - COD colapsa las fases a un estado determinista estable.
   - Espectro genera la salida multimodal (modo primario = dominio ganador).
   - Retro: el Espectro retroalimenta el OVC para el próximo tick.
4. Lee los resultados RCC de cada ciclo de dominio.
5. Limpia los ciclos de routing (no persisten entre requests).
6. Retorna top-N dominios por resonance_strength.

Esto hace que ORBITAL sea el **cerebro central** de HAT — cada request
pasa por el motor determinista completo, no solo por una calculadora de TOR.

Diseño:
- Stateless entre calls (limpia variables y ciclos al inicio de cada route()).
- Namespacing por session_id para evitar cross-session pollution.
- Filtra cards por ``metadata.type == 'agent_card'``.
- Fallback graceful: si run_tick falla, usa cálculo TOR manual (compat).

Implementado en Phase 1 (ORBITAL como cerebro central).
"""
from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from src.core.logging import setup_logging

if TYPE_CHECKING:
    from src.orbital.context import OrbitalContext

logger = setup_logging(__name__)

# ── Constantes ──────────────────────────────────────────────────────────
ROUTING_ORBIT_GROUP: str = "hat_routing"
INTENT_VAR_TYPE: str = "user_intent"
TOP_N_DOMAINS: int = 3

# Parámetros orbitales del user_intent.
INTENT_THETA: float = 0.0
INTENT_AMPLITUDE: float = 1.0
INTENT_VELOCITY: float = 0.1

# Umbral de resonancia RCC para ciclos de routing (0.0 = detectar cualquier resonancia).
ROUTING_CYCLE_THRESHOLD: float = 0.0

# Damping para retroalimentación del Espectro (0.3 = moderado).
RETROFEED_DAMPING: float = 0.3


class OrbitalRouter:
    """Router por resonancia ORBITAL — cerebro central de routing de HAT.

    Ejecuta el ciclo ORBITAL completo (OVC→TOR→RCC→COD→Espectro→Retro)
    en cada llamada a :meth:`route`. El motor determinista procesa el
    user_intent junto con las Agent Cards y produce un estado convergido
    que determina el dominio ganador.

    Attributes:
        _ctx: OrbitalContext singleton (OVC + TOR + RCC + COD + Espectro).
        _session_id: ID de la sesión actual (para namespacing).
    """

    def __init__(self, ctx: OrbitalContext, session_id: str = "default") -> None:
        """Inicializa el router con contexto orbital y sesión.

        Args:
            ctx: OrbitalContext singleton con los 5 pilares.
            session_id: ID de la sesión (se sanitiza para namespacing).
        """
        self._ctx = ctx
        self._session_id = session_id

    # ── API pública ────────────────────────────────────────────────────

    def set_session(self, session_id: str) -> None:
        """Actualiza el session_id (llamar al inicio de cada handle())."""
        self._session_id = session_id

    def route(self, message: str) -> list[tuple[str, float]]:
        """Rutea un mensaje ejecutando el ciclo ORBITAL completo.

        Flujo (Phase 1 — ORBITAL como cerebro central):
        1. Crear variable OVC user_intent con el mensaje.
        2. Recolectar Agent Cards agrupadas por dominio.
        3. Registrar un ciclo RCC por dominio (intent + cards del dominio).
        4. Ejecutar ``ctx.run_tick()`` — ciclo completo OVC→TOR→RCC→COD→Espectro→Retro.
        5. Leer resonance_strength de cada ciclo RCC (post-COD, post-Espectro).
        6. Limpiar ciclos de routing (no persisten entre requests).
        7. Retornar top-N dominios ordenados desc.

        Args:
            message: Texto del usuario (se almacena en metadata, no se parsea).

        Returns:
            Lista de tuplas ``(domain, resonance_strength)`` ordenada desc.
            Vacía si no hay Agent Cards. ``resonance_strength`` en [0.0, 1.0].
        """
        intent_var_name = self.get_intent_var_name()

        # 1. Limpiar variable user_intent previa y crear la nueva
        self._clear_intent_variable(intent_var_name)
        self._create_intent_variable(intent_var_name, message)

        # 2. Recolectar Agent Cards por dominio
        cards_by_domain = self.collect_cards_by_domain()
        if not cards_by_domain:
            return []

        # 3. Registrar ciclos RCC por dominio
        cycle_names = self._register_routing_cycles(
            intent_var_name, cards_by_domain,
        )

        # 4. Ejecutar ciclo ORBITAL completo
        #    OVC advance → TOR matrix → RCC detect → COD collapse → Espectro → Retro
        try:
            orbital_result = self._ctx.run_tick(
                dt=1.0, retrofeed_damping=RETROFEED_DAMPING,
            )
            logger.info(
                "OrbitalRouter: run_tick completado — tick=%d, "
                "TOR=%d, RCC=%d, COD=%d, espectro_modes=%d",
                orbital_result.tick,
                len(orbital_result.tor_results),
                len(orbital_result.rcc_results),
                len(orbital_result.cod_results),
                len(orbital_result.espectro.modes) if orbital_result.espectro else 0,
            )
        except Exception as exc:
            logger.warning(
                "OrbitalRouter: run_tick falló (%s), usando fallback TOR manual", exc,
            )
            # Fallback: usar cálculo TOR manual (compat con comportamiento anterior)
            resonances = self._fallback_tor_routing(intent_var_name, cards_by_domain)
            self._cleanup_routing_cycles(cycle_names)
            return resonances

        # 5. Leer resonance_strength de cada ciclo RCC
        resonances = self._read_domain_resonances(cycle_names)

        # 6. Limpiar ciclos de routing (no persisten entre requests)
        self._cleanup_routing_cycles(cycle_names)

        # 7. Ordenar desc y tomar top-N
        resonances.sort(key=lambda x: x[1], reverse=True)
        return resonances[:TOP_N_DOMAINS]

    # ── Registro de ciclos RCC ─────────────────────────────────────────

    def _register_routing_cycles(
        self,
        intent_var_name: str,
        cards_by_domain: dict[str, list[str]],
    ) -> dict[str, str]:
        """Registra un ciclo RCC por dominio en el motor ORBITAL.

        Cada ciclo contiene: [user_intent_var] + [card_vars del dominio].
        El RCC detectará resonancia entre el intent y las cards del dominio.
        El COD colapsará las fases a un estado determinista.
        El Espectro generará el modo primario (dominio ganador).

        Args:
            intent_var_name: Nombre de la variable OVC del user_intent.
            cards_by_domain: Dict domain → lista de nombres de variables OVC.

        Returns:
            Dict domain → cycle_name (para lookup y cleanup posterior).
        """
        cycle_names: dict[str, str] = {}
        safe_session = self._sanitize_session_id(self._session_id)

        for domain, card_vars in cards_by_domain.items():
            cycle_name = f"routing_{domain}_{safe_session}"
            all_vars = [intent_var_name, *card_vars]
            try:
                self._ctx.rcc.register_cycle_from_names(
                    cycle_name, all_vars, threshold=ROUTING_CYCLE_THRESHOLD,
                )
                cycle_names[domain] = cycle_name
                logger.debug(
                    "OrbitalRouter: ciclo RCC registrado '%s' con %d variables",
                    cycle_name, len(all_vars),
                )
            except Exception as exc:
                logger.warning(
                    "OrbitalRouter: no se pudo registrar ciclo '%s': %s",
                    cycle_name, exc,
                )

        return cycle_names

    def _read_domain_resonances(
        self,
        cycle_names: dict[str, str],
    ) -> list[tuple[str, float]]:
        """Lee la resonance_strength de cada ciclo RCC de dominio.

        Después de ``run_tick()``, cada ciclo tiene su ``resonance_level``
        actualizado por el RCC (detect_all). El COD puede haber ajustado
        las fases, pero el resonance_level refleja el estado post-detección.

        Args:
            cycle_names: Dict domain → cycle_name.

        Returns:
            Lista de tuplas (domain, resonance_strength) con valores en [0, 1].
        """
        resonances: list[tuple[str, float]] = []

        for domain, cycle_name in cycle_names.items():
            resonance = self._read_cycle_resonance(cycle_name)
            resonances.append((domain, resonance))

        return resonances

    def _read_cycle_resonance(self, cycle_name: str) -> float:
        """Lee el resonance_level de un ciclo RCC por nombre.

        Busca el ciclo en el RCC por su nombre (no por UUID) y retorna
        su ``resonance_level``, que fue seteado durante ``detect_all()``.

        Args:
            cycle_name: Nombre del ciclo a buscar.

        Returns:
            Resonance strength en [0.0, 1.0]. 0.0 si no se encuentra.
        """
        rcc = self._ctx.rcc
        # Iterar sobre los ciclos registrados en el RCC
        for cycle in rcc._cycles.values():
            if cycle.name == cycle_name:
                # resonance_level fue seteado por detect_all() durante run_tick
                return min(max(cycle.resonance_level, 0.0), 1.0)
        return 0.0

    def _cleanup_routing_cycles(self, cycle_names: dict[str, str]) -> None:
        """Elimina los ciclos de routing del RCC después de cada route().

        Los ciclos de routing son efímeros — no persisten entre requests.
        Esto evita acumulación de ciclos fantasma (bug Sprint 1 #3).

        Args:
            cycle_names: Dict domain → cycle_name a eliminar.
        """
        rcc = self._ctx.rcc
        for cycle_name in cycle_names.values():
            rcc.remove_cycles_by_name(cycle_name)

        # Limpiar cache TOR para que no queden entradas stale
        tor = self._ctx.tor
        if hasattr(tor, "clear_cache"):
            tor.clear_cache()

    # ── Fallback: cálculo TOR manual (compat) ──────────────────────────

    def _fallback_tor_routing(
        self,
        intent_var_name: str,
        cards_by_domain: dict[str, list[str]],
    ) -> list[tuple[str, float]]:
        """Fallback: cálculo TOR manual si run_tick falla.

        Este es el comportamiento anterior a Phase 1 — calcula TOR
        directamente sin pasar por RCC/COD/Espectro. Se usa solo
        como safety net si el motor ORBITAL completo falla.

        Args:
            intent_var_name: Nombre de la variable OVC del user_intent.
            cards_by_domain: Dict domain → card_vars.

        Returns:
            Lista de tuplas (domain, resonance) ordenada desc, top-N.
        """
        resonances: list[tuple[str, float]] = [
            (domain, self.compute_domain_resonance(domain, card_vars))
            for domain, card_vars in cards_by_domain.items()
        ]
        resonances.sort(key=lambda x: x[1], reverse=True)
        return resonances[:TOP_N_DOMAINS]

    # ── Helpers de namespacing ─────────────────────────────────────────

    def get_intent_var_name(self) -> str:
        """Retorna el nombre namespaced de la variable OVC de user_intent."""
        safe_id = self._sanitize_session_id(self._session_id)
        return f"hat_{safe_id}__user_intent_current"

    @staticmethod
    def _sanitize_session_id(session_id: str) -> str:
        """Sanitiza un session_id (no alfanuméricos → '_')."""
        return "".join(c if c.isalnum() else "_" for c in str(session_id))

    # ── Helpers de variables OVC ───────────────────────────────────────

    def _clear_intent_variable(self, intent_var_name: str) -> None:
        """Elimina la variable user_intent previa de esta sesión."""
        existing = self._ctx.ovc.get_variable(intent_var_name)
        if existing is not None:
            self._ctx.ovc.delete_variable(intent_var_name)

    def _create_intent_variable(self, intent_var_name: str, message: str) -> None:
        """Crea la variable OVC user_intent para esta sesión."""
        with contextlib.suppress(ValueError):
            self._ctx.ovc.create_variable(
                name=intent_var_name,
                theta=INTENT_THETA,
                amplitude=INTENT_AMPLITUDE,
                velocity=INTENT_VELOCITY,
                orbit_group=ROUTING_ORBIT_GROUP,
                metadata={"type": INTENT_VAR_TYPE, "text": message},
            )

    # ── Helpers de Agent Cards ─────────────────────────────────────────

    def collect_cards_by_domain(self) -> dict[str, list[str]]:
        """Agrupa las variables OVC de tipo agent_card por dominio.

        Returns:
            Dict ``domain → lista de nombres de variables OVC``.
        """
        result: dict[str, list[str]] = {}
        for name, var in self._ctx.ovc.get_all_variables().items():
            metadata = var.metadata or {}
            if metadata.get("type") != "agent_card":
                continue
            domain = metadata.get("domain", "unknown")
            result.setdefault(domain, []).append(name)
        return result

    # ── Cálculo de resonancia (fallback, usado si run_tick falla) ──────

    def compute_domain_resonance(
        self, domain: str, card_vars: list[str],
    ) -> float:
        """Calcula resonancia manualmente via TOR (método fallback).

        Este método se mantiene para compatibilidad y como fallback
        cuando ``run_tick()`` falla. En operación normal, la resonancia
        se calcula via el ciclo ORBITAL completo (RCC detect_all).
        """
        if not card_vars:
            return 0.0
        intent_var_name = self.get_intent_var_name()
        user_intent = self._ctx.ovc.get_variable(intent_var_name)
        if user_intent is None:
            return 0.0
        total, max_possible = self._accumulate_resonance(
            card_vars, user_intent, intent_var_name,
        )
        if max_possible <= 0:
            return 0.0
        return min(total / max_possible, 1.0)

    def _accumulate_resonance(
        self,
        card_vars: list[str],
        user_intent: object,
        intent_var_name: str,
    ) -> tuple[float, float]:
        """Acumula TOR entre user_intent y cada card (fallback)."""
        tor = self._ctx.tor
        total = 0.0
        max_possible = 0.0
        for card_var_name in card_vars:
            card_var = self._ctx.ovc.get_variable(card_var_name)
            if card_var is None:
                continue
            max_possible += card_var.amplitude * user_intent.amplitude
            try:
                result = tor.calculate(intent_var_name, card_var_name)
                total += abs(result.tor_value)
            except Exception as exc:
                logger.warning(
                    "OrbitalRouter: TOR falló para card '%s': %s",
                    card_var_name, exc,
                )
        return total, max_possible

    # ── Representación ─────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"<OrbitalRouter session={self._session_id!r} "
            f"vars={self._ctx.ovc.variable_count}>"
        )
