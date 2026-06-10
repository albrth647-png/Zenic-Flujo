"""
ORBITAL — Pilar Puente: OrbitalAdapter
========================================

Adaptador que permite que las herramientas de negocio existentes
(CRM, Invoice, Inventory, Notification, etc.) funcionen con el
paradigma orbital.

En el sistema LINEAL:
    Tool.action(parametros) → resultado → FIN

En el sistema ORBITAL:
    Tool.action(parametros) → resultado orbital → OVC(theta) → TOR → retro → ...

Cada llamada a una herramienta:
1. Genera una variable orbital con el nombre de la tool y action
2. El resultado modifica la fase (exito=avanza, fallo=retrocede)
3. La tension entre herramientas determina dependencias orbitales
4. El resultado retroalimenta el sistema

El adaptador NO modifica las herramientas existentes.
Solo envuelve las llamadas con logica orbital.
"""

from __future__ import annotations

import math
from typing import Any

from src.orbital.models import TWO_PI
from src.orbital.context import OrbitalContext
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class OrbitalToolResult:
    """Resultado de una herramienta adaptada orbitalmente."""

    def __init__(self, status: str, data: dict | None = None,
                 orbital_theta: float = 0.0, orbital_amplitude: float = 1.0):
        self.status = status
        self.data = data or {}
        self.orbital_theta = orbital_theta
        self.orbital_amplitude = orbital_amplitude

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "data": self.data,
            "orbital_theta": self.orbital_theta,
            "orbital_amplitude": self.orbital_amplitude,
        }


class OrbitalAdapter:
    """
    Adaptador Orbital de Herramientas — Envuelve tools existentes con logica orbital.

    Registra cada herramienta como una variable orbital. Cuando se llama
    a una accion de la herramienta, el adaptador:

    1. Registra/actualiza la variable orbital de la tool
    2. Calcula tension con tools relacionadas
    3. Ejecuta la accion de la tool original
    4. Actualiza la variable orbital segun el resultado
    5. Retroalimenta el resultado al OVC

    Las herramientas existentes NO necesitan modificarse.
    El adaptador las envuelve transparentemente.
    """

    def __init__(self):
        # Usar OVC y TOR compartidos via OrbitalContext (no crear instancias aisladas)
        self._ctx = OrbitalContext()
        self._ovc = self._ctx.ovc
        self._tor = self._ctx.tor
        self._tools: dict[str, object] = {}
        self._tool_relations: dict[str, list[str]] = {
            # Relaciones orbitales entre herramientas:
            # Una herramienta "orbita alrededor" de las relacionadas
            "crm": ["notification", "invoice"],
            "invoice": ["crm", "notification"],
            "inventory": ["notification", "invoice"],
            "notification": ["crm", "invoice", "inventory"],
            "autopilot": ["crm", "notification"],
            "logic_gate": ["crm", "inventory"],
            "api_connector": [],
            "data_keeper": ["crm", "inventory"],
            "code_runner": [],
        }

    # ── Registro de herramientas ───────────────────────────

    def register_tool(self, tool_name: str, tool_instance: object) -> None:
        """
        Registra una herramienta de negocio en el adaptador orbital.

        Crea una variable orbital para la herramienta y la registra
        para ejecucion.

        Args:
            tool_name: Nombre de la herramienta (ej: "crm", "invoice")
            tool_instance: Instancia de la herramienta
        """
        self._tools[tool_name] = tool_instance
        self._ensure_tool_variable(tool_name)
        logger.info(f"OrbitalAdapter: Tool '{tool_name}' registrada orbitalmente")

    def register_tools_batch(self, tools: dict[str, object]) -> None:
        """Registra multiples herramientas de una vez."""
        for name, instance in tools.items():
            self.register_tool(name, instance)

    # ── Ejecucion orbital ──────────────────────────────────

    def execute_action(self, tool_name: str, action: str,
                       params: dict | None = None) -> OrbitalToolResult:
        """
        Ejecuta una accion de herramienta en modo orbital.

        Proceso:
        1. Actualizar variable orbital de la tool
        2. Calcular tension con tools relacionadas
        3. Ejecutar la accion original
        4. Actualizar orbital segun resultado
        5. Retroalimentar

        Args:
            tool_name: Nombre de la herramienta
            action: Accion a ejecutar
            params: Parametros de la accion

        Returns:
            OrbitalToolResult con el resultado enriquecido
        """
        params = params or {}

        # 1. Actualizar variable orbital
        self._ensure_tool_variable(tool_name)
        var = self._ovc.get_variable(tool_name)
        if var:
            var.advance(dt=1.0)  # Cada llamada avanza la fase

        # 2. Calcular tension con tools relacionadas
        relations = self._tool_relations.get(tool_name, [])
        tor_with_relations = {}
        for related in relations:
            if self._ovc.get_variable(related):
                try:
                    result = self._tor.calculate(tool_name, related)
                    tor_with_relations[related] = result.tor_value
                except KeyError:
                    pass

        # 3. Ejecutar la accion original
        tool = self._tools.get(tool_name)
        if tool is None:
            return OrbitalToolResult(
                status="failed",
                data={"error": f"Tool '{tool_name}' no registrada"},
                orbital_theta=var.theta if var else 0.0,
            )

        try:
            action_func = getattr(tool, action, None)
            if action_func is None:
                raise ValueError(f"Accion '{action}' no encontrada en '{tool_name}'")

            result_data = action_func(**params)

            # 4. Actualizar orbital: exito → avanzar
            if var:
                var.advance(dt=1.0)
                var.amplitude = min(var.amplitude * 1.05, 10.0)

            orbital_theta = var.theta if var else 0.0
            orbital_amplitude = var.amplitude if var else 1.0

            logger.info(
                f"OrbitalAdapter: {tool_name}.{action} → OK "
                f"θ={math.degrees(orbital_theta):.1f}° A={orbital_amplitude:.2f}"
            )

            return OrbitalToolResult(
                status="completed",
                data=result_data if isinstance(result_data, dict) else {"result": result_data},
                orbital_theta=orbital_theta,
                orbital_amplitude=orbital_amplitude,
            )

        except Exception as e:
            # 4b. Actualizar orbital: fallo → retroceder
            if var:
                var.retrofeed(-0.2, damping=0.5)

            orbital_theta = var.theta if var else 0.0

            logger.error(f"OrbitalAdapter: {tool_name}.{action} → FALLO: {e}")

            return OrbitalToolResult(
                status="failed",
                data={"error": str(e)},
                orbital_theta=orbital_theta,
            )

    # ── Consultas orbitales ────────────────────────────────

    def get_tool_phase(self, tool_name: str) -> float | None:
        """Retorna la fase orbital de una herramienta."""
        var = self._ovc.get_variable(tool_name)
        return var.theta if var else None

    def get_tool_alignment(self, tool_a: str, tool_b: str) -> float | None:
        """Retorna la alineacion orbital entre dos herramientas."""
        var_a = self._ovc.get_variable(tool_a)
        var_b = self._ovc.get_variable(tool_b)
        if var_a and var_b:
            return var_a.phase_alignment(var_b)
        return None

    def get_orbital_snapshot(self) -> dict[str, Any]:
        """Retorna snapshot del estado orbital de las herramientas."""
        return {
            "tools_registered": list(self._tools.keys()),
            "phases": self._ovc.get_phase_snapshot(),
            "values": self._ovc.get_value_snapshot(),
            "tor_matrix": [r.to_dict() for r in self._tor.calculate_matrix()],
        }

    def get_tool_recommendations(self, tool_name: str) -> list[str]:
        """
        Retorna herramientas recomendadas basadas en tension orbital.

        Las herramientas con mayor alineacion (TOR positivo) son las
        que mas "resuenan" con la herramienta dada, y por tanto
        son candidatas naturales para el siguiente paso.
        """
        recommendations = []
        relations = self._tool_relations.get(tool_name, [])

        for related in relations:
            if self._ovc.get_variable(related):
                alignment = self.get_tool_alignment(tool_name, related)
                if alignment is not None:
                    recommendations.append((related, alignment))

        # Ordenar por alineacion descendente
        recommendations.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in recommendations]

    # ── Helpers ────────────────────────────────────────────

    def _ensure_tool_variable(self, tool_name: str) -> None:
        """Crea una variable orbital para una herramienta si no existe."""
        if self._ovc.get_variable(tool_name) is None:
            import hashlib
            hash_val = int(hashlib.md5(tool_name.encode()).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ovc.create_variable(
                name=tool_name,
                theta=theta,
                amplitude=1.0,
                velocity=0.1,
                orbit_group="business_tools",
                metadata={"type": "tool", "name": tool_name},
            )

    # ── Representacion ─────────────────────────────────────

    def __repr__(self) -> str:
        return f"OrbitalAdapter(tools={len(self._tools)}, orbitals={self._ovc.variable_count})"

    def orbital_summary(self) -> str:
        """Retorna un resumen del estado orbital de las herramientas."""
        lines = ["OrbitalAdapter — Herramientas Orbitales"]
        lines.append(f"  Tools registradas: {len(self._tools)}")
        for name in self._tools:
            var = self._ovc.get_variable(name)
            if var:
                lines.append(f"    {name}: θ={var.phase_degrees:.1f}° A={var.amplitude:.2f} val={var.value:.3f}")
            else:
                lines.append(f"    {name}: sin variable orbital")
        return "\n".join(lines)
