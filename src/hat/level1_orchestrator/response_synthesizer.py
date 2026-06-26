"""
ResponseSynthesizer — Síntesis de respuestas del HATRouter
===========================================================

Extraído de tick_router.py. Responsabilidad única: construir textos
de respuesta legibles para el usuario a partir de los resultados
del supervisor/disambiguador.

Uso:
    synthesizer = ResponseSynthesizer()
    response = synthesizer.synthesize(
        dispatch_id="...", domain="operaciones",
        supervisor_result=..., resonance=0.85, duration_ms=120,
    )
"""

from typing import Any, TypedDict


class DispatchResult(TypedDict):
    """Respuesta final del HATRouter al usuario."""
    dispatch_id: str
    domain: str
    response: str
    orbital_resonance: float
    anti_dup_layer_hit: str
    duration_ms: int
    facts_updated: list[Any]
    status: str


class ResponseSynthesizer:
    """Sintetiza respuestas legibles para el usuario.

    Métodos públicos:
    - synthesize() — punto de entrada principal
    - build_clarify_response() — construye respuesta 'no sé qué quieres hacer'
    - build_anti_dup_response() — construye respuesta cuando anti-dup bloquea
    - anti_dup_response_text() — texto para cada acción anti-dup
    """

    @staticmethod
    def synthesize(
        dispatch_id: str,
        domain: str,
        supervisor_result: dict[str, Any],
        resonance: float,
        duration_ms: int,
        anti_dup_layer: str = "none",
    ) -> DispatchResult:
        """Sintetiza la respuesta final al usuario.

        Args:
            dispatch_id: ID del despacho.
            domain: Dominio ganador.
            supervisor_result: Resultado del supervisor.
            resonance: Resonancia ORBITAL final.
            duration_ms: Duración total en ms.
            anti_dup_layer: Capa anti-dup activada ('none' si ninguna).

        Returns:
            dict con: dispatch_id, domain, response, orbital_resonance,
            anti_dup_layer_hit, duration_ms, facts_updated.
        """
        status = supervisor_result.get("status", "unknown")
        result = supervisor_result.get("result", {})
        response_text = ResponseSynthesizer._extract_response_text(status, result, domain)

        return {
            "dispatch_id": dispatch_id,
            "domain": domain,
            "response": response_text,
            "orbital_resonance": round(resonance, 4),
            "anti_dup_layer_hit": anti_dup_layer,
            "duration_ms": duration_ms,
            "facts_updated": [],
            "status": status,
        }

    # ── Anti-dup response ────────────────────────────────────────────────

    @staticmethod
    def build_anti_dup_response(
        anti_dup_result: dict[str, Any],
        dispatch_id: str,
        domain: str,
        start: float,
    ) -> DispatchResult:
        """Construye respuesta cuando el cascade detecta duplicado.

        Args:
            anti_dup_result: Resultado del cascade.
            dispatch_id: ID del despacho.
            domain: Dominio ganador.
            start: Timestamp de inicio (monotonic).

        Returns:
            dict con respuesta anti-dup para el usuario.
        """
        import time
        action = anti_dup_result.get("action", "proceed")
        layer = anti_dup_result.get("layer_hit", "unknown")
        cached = anti_dup_result.get("cached_result")

        response_text = ResponseSynthesizer.anti_dup_response_text(action, layer, cached)

        return {
            "dispatch_id": dispatch_id,
            "domain": domain,
            "response": response_text,
            "orbital_resonance": 0.0,
            "anti_dup_layer_hit": layer,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "facts_updated": [],
            "status": "anti_dup_blocked",
        }

    @staticmethod
    def anti_dup_response_text(
        action: str, layer: str, cached: Any,
    ) -> str:
        """Genera texto de respuesta para cada acción anti-dup.

        Args:
            action: Acción del cascade.
            layer: Nombre de la capa que detectó.
            cached: Resultado cacheado si action='return_cache'.

        Returns:
            Texto legible para el usuario.
        """
        if action == "return_cache" and cached is not None:
            return f"Resultado cacheado (capa: {layer}): {cached}"
        if action == "subscribe":
            return (
                f"Tu solicitud está siendo procesada. "
                f"Te notificaremos cuando termine (capa: {layer})."
            )
        if action == "discard":
            return (
                f"Detectamos un doble-click. "
                f"Ignorando la solicitud duplicada (capa: {layer})."
            )
        if action == "confirm":
            return (
                f"Tu solicitud parece similar a una anterior. "
                f"¿Confirmas que quieres procesarla de nuevo? (capa: {layer})"
            )
        if action == "fallback":
            return (
                f"El dominio solicitado tiene problemas temporales. "
                f"Usando fallback (capa: {layer})."
            )
        return f"Solicitud bloqueada por anti-doble-llamada (capa: {layer})."

    # ── Clarify response ────────────────────────────────────────────────

    @staticmethod
    def build_clarify_response(message: str) -> dict[str, Any]:
        """Construye respuesta cuando FSM no resuelve (dominio = 'clarify').

        Args:
            message: Texto original del usuario.

        Returns:
            dict con status='clarify', result con mensaje pidiendo aclaración.
        """
        return {
            "status": "clarify",
            "result": {
                "clarify_message": (
                    f"No estoy seguro de qué quieres hacer con: {message!r}. "
                    "¿Puedes ser más específico?"
                ),
                "suggestions": [
                    "crear lead para Juan",
                    "enviar email a cliente@example.com",
                    "ejecutar código Python",
                    "listar productos del inventario",
                ],
            },
            "specialists_used": [],
            "duration_ms": 0,
        }

    # ── Extractores de texto internos ─────────────────────────────────────

    @staticmethod
    def _extract_response_text(
        status: str, result: Any, domain: str,
    ) -> str:
        """Extrae texto legible para el usuario desde el resultado del supervisor.

        Args:
            status: Estado del supervisor.
            result: Resultado crudo del supervisor.
            domain: Dominio ganador.

        Returns:
            Texto de respuesta para el usuario.
        """
        if status == "clarify":
            return ResponseSynthesizer._extract_clarify_text(result)
        if status == "failed":
            return ResponseSynthesizer._extract_failed_text(result)
        return ResponseSynthesizer._extract_completed_text(result, domain)

    @staticmethod
    def _extract_clarify_text(result: Any) -> str:
        """Extrae texto para status='clarify'."""
        if isinstance(result, dict):
            msg: str = result.get("clarify_message", "Necesito más información.")
            return msg
        return "Necesito más información."

    @staticmethod
    def _extract_failed_text(result: Any) -> str:
        """Extrae texto para status='failed'."""
        error = ""
        if isinstance(result, dict):
            error = result.get("error", "")
        return f"Error procesando solicitud: {error}"

    @staticmethod
    def _extract_completed_text(result: Any, domain: str) -> str:
        """Extrae texto para status='completed'."""
        if domain == "operaciones" and isinstance(result, dict):
            if "queries" in result:
                return f"Resultado: {', '.join(result['queries'][:3])}"
            if "id" in result:
                return f"Creado con ID: {result['id']}"
            if "number" in result:
                return f"Factura {result['number']} creada"
            return str(result)
        if domain in ("comunicaciones", "datos_auto") and isinstance(result, dict):
            if "status" in result:
                return f"Estado: {result['status']}"
            return str(result)
        return str(result)
