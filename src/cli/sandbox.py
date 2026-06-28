"""
Zenic CLI — Ejecutor Sandbox para Pruebas de Conectores
========================================================

Provee un entorno aislado para ejecutar conectores durante el desarrollo,
capturando toda la salida (stdout/stderr), midiendo tiempos de ejecucion,
y manejando timeouts configurables.

El SandboxExecutor permite probar el ciclo de vida completo de un conector:
1. Instanciacion del conector
2. Conexion (connect)
3. Ejecucion de accion (execute)
4. Desconexion (disconnect)

Y captura resultados, errores, logs y metricas de rendimiento.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.sdk.base import BaseConnector

import io
import time
from contextlib import redirect_stderr, redirect_stdout, suppress
from dataclasses import dataclass, field
from typing import Any

from src.core.logging import setup_logging

logger = setup_logging(__name__)


@dataclass
class SandboxResult:
    """
    Resultado estructurado de la ejecucion de un conector en el sandbox.

    Attributes:
        success: Si la ejecucion fue exitosa (sin excepciones no capturadas)
        output: Salida del conector (resultado de execute)
        errors: Lista de errores encontrados durante la ejecucion
        timing: Diccionario con tiempos de cada fase (connect, execute, disconnect)
        logs: Salida capturada de stdout y stderr durante la ejecucion
        connector_name: Nombre del conector ejecutado
        action: Nombre de la accion ejecutada
        params: Parametros proporcionados a la accion
    """

    success: bool = False
    output: Any | None = None
    errors: list[str] = field(default_factory=list)
    timing: dict[str, float] = field(default_factory=dict)
    logs: str = ""
    connector_name: str = ""
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def total_time_ms(self) -> float:
        """Retorna el tiempo total de ejecucion en milisegundos."""
        return sum(self.timing.values()) * 1000

    def to_dict(self) -> dict[str, Any]:
        """
        Serializa el resultado a diccionario para presentacion o API.

        Retorna:
            Diccionario con toda la informacion del resultado
        """
        return {
            "success": self.success,
            "output": self.output,
            "errors": self.errors,
            "timing": {k: round(v * 1000, 2) for k, v in self.timing.items()},
            "total_time_ms": round(self.total_time_ms, 2),
            "logs": self.logs,
            "connector_name": self.connector_name,
            "action": self.action,
        }

    def format_report(self) -> str:
        """
        Genera un reporte legible del resultado de la ejecucion.

        Retorna:
            String formateado con el reporte completo del resultado
        """
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append(f"  REPORTE DE EJECUCION SANDBOX — {self.connector_name}")
        lines.append("=" * 60)
        lines.append("")

        # Estado general
        status_icon = "OK" if self.success else "FALLO"
        lines.append(f"  Estado:    {status_icon}")
        lines.append(f"  Accion:    {self.action}")
        lines.append(f"  Tiempo:    {self.total_time_ms:.2f} ms")
        lines.append("")

        # Tiempos por fase
        if self.timing:
            lines.append("  Tiempos por fase:")
            for phase, duration in self.timing.items():
                lines.append(f"    {phase:.<30} {duration * 1000:>8.2f} ms")
            lines.append("")

        # Resultado
        if self.output is not None:
            lines.append("  Resultado:")
            import json

            try:
                output_str = json.dumps(self.output, indent=4, default=str, ensure_ascii=False)
            except (TypeError, ValueError):
                output_str = str(self.output)
            for line in output_str.split("\n"):
                lines.append(f"    {line}")
            lines.append("")

        # Errores
        if self.errors:
            lines.append("  Errores:")
            for error in self.errors:
                lines.append(f"    - {error}")
            lines.append("")

        # Logs capturados
        if self.logs.strip():
            lines.append("  Logs capturados:")
            for log_line in self.logs.strip().split("\n"):
                lines.append(f"    {log_line}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


class SandboxExecutor:
    """
    Ejecutor de conectores en entorno sandbox aislado.

    Permite ejecutar el ciclo de vida completo de un conector
    (connect -> execute -> disconnect) capturando toda la salida,
    midiendo tiempos y manejando timeouts.

    El sandbox redirige stdout y stderr para capturar logs, y
    maneja excepciones no capturadas gracefully.

    Args:
        timeout: Tiempo maximo de ejecucion en segundos (0 = sin limite)
        capture_output: Si se debe capturar stdout/stderr
        mock_infra: Si se deben mockear las dependencias de infraestructura (Redis, Telemetry)

    Ejemplo:
        executor = SandboxExecutor(timeout=30)
        result = executor.run(connector_instance, action="ping", params={})
        print(result.format_report())
    """

    def __init__(
        self,
        timeout: float = 0,
        capture_output: bool = True,
        mock_infra: bool = True,
    ) -> None:
        self._timeout = timeout
        self._capture_output = capture_output
        self._mock_infra = mock_infra

    def run(
        self,
        connector: BaseConnector,
        action: str = "ping",
        params: dict[str, Any] | None = None,
    ) -> SandboxResult:
        """
        Ejecuta el ciclo de vida completo del conector en el sandbox.

        Ejecuta la secuencia: connect() -> execute(action, params) -> disconnect()
        capturando errores, tiempos y salida en cada fase.

        Args:
            connector: Instancia del conector a ejecutar (debe heredar de BaseConnector)
            action: Nombre de la accion a ejecutar (default: 'ping')
            params: Parametros para la accion (default: diccionario vacio)

        Retorna:
            SandboxResult con el resultado completo de la ejecucion
        """
        params = params or {}
        result = SandboxResult(
            connector_name=getattr(connector, "name", "unknown"),
            action=action,
            params=params,
        )

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Configurar mocks de infraestructura si es necesario
        patches: list[Any] = []
        if self._mock_infra:
            self._setup_mocks(patches)

        try:
            # Iniciar redireccion de salida
            if self._capture_output:
                redirect_stdout(stdout_capture).__enter__()
                redirect_stderr(stderr_capture).__enter__()

            # Fase 1: Conexion
            connect_time = self._execute_phase(connector, "connect", result, timeout=self._timeout)
            result.timing["connect"] = connect_time

            if not result.success and result.errors:
                # La conexion fallo, intentar desconectar y retornar
                self._safe_disconnect(connector, result)
                return result

            # Fase 2: Ejecucion de la accion
            result.success = False  # Resetear para la fase de ejecucion
            result.errors = []

            start = time.monotonic()
            try:
                output = connector.execute(action, params)
                result.output = output
                result.success = True
            except Exception as exc:
                result.errors.append(f"Ejecucion: {type(exc).__name__}: {exc}")
                result.success = False
                logger.debug(f"SandboxExecutor: error en execute: {exc}")
            execute_time = time.monotonic() - start
            result.timing["execute"] = execute_time

            # Fase 3: Desconexion
            self._safe_disconnect(connector, result)

        finally:
            # Restaurar salida estandar
            if self._capture_output:
                try:
                    redirect_stderr(stderr_capture).__exit__(None, None, None)
                    redirect_stdout(stdout_capture).__exit__(None, None, None)
                except Exception:
                    pass

            # Limpiar mocks
            self._teardown_mocks(patches)

            # Capturar logs
            result.logs = stdout_capture.getvalue() + stderr_capture.getvalue()

        return result

    def run_lifecycle_only(
        self,
        connector: BaseConnector,
    ) -> SandboxResult:
        """
        Ejecuta solo el ciclo de vida (connect -> disconnect) sin ejecutar acciones.

        Util para verificar que un conector puede conectarse y desconectarse
        correctamente sin ejecutar ninguna accion.

        Args:
            connector: Instancia del conector a probar

        Retorna:
            SandboxResult con el resultado del ciclo de vida
        """
        result = SandboxResult(
            connector_name=getattr(connector, "name", "unknown"),
            action="<lifecycle_only>",
        )

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        patches: list[Any] = []
        if self._mock_infra:
            self._setup_mocks(patches)

        try:
            if self._capture_output:
                redirect_stdout(stdout_capture).__enter__()
                redirect_stderr(stderr_capture).__enter__()

            connect_time = self._execute_phase(connector, "connect", result, timeout=self._timeout)
            result.timing["connect"] = connect_time

            self._safe_disconnect(connector, result)

        finally:
            if self._capture_output:
                try:
                    redirect_stderr(stderr_capture).__exit__(None, None, None)
                    redirect_stdout(stdout_capture).__exit__(None, None, None)
                except Exception:
                    pass

            self._teardown_mocks(patches)
            result.logs = stdout_capture.getvalue() + stderr_capture.getvalue()

        return result

    def _execute_phase(
        self,
        connector: BaseConnector,
        phase: str,
        result: SandboxResult,
        timeout: float = 0,
    ) -> float:
        """
        Ejecuta una fase del ciclo de vida del conector con medicion de tiempo.

        Args:
            connector: Instancia del conector
            phase: Nombre de la fase ('connect' o 'disconnect')
            result: Objeto SandboxResult para registrar errores
            timeout: Tiempo maximo en segundos (0 = sin limite)

        Retorna:
            Tiempo de ejecucion de la fase en segundos
        """
        method = getattr(connector, phase, None)
        if method is None:
            result.errors.append(f"Fase '{phase}': metodo no encontrado")
            return 0.0

        start = time.monotonic()
        try:
            phase_result = self._run_with_timeout(method, timeout) if timeout > 0 else method()

            if phase == "connect":
                result.success = bool(phase_result)

        except TimeoutError:
            result.errors.append(f"Fase '{phase}': timeout ({timeout}s)")
            result.success = False
        except Exception as exc:
            result.errors.append(f"Fase '{phase}': {type(exc).__name__}: {exc}")
            result.success = False
            logger.debug(f"SandboxExecutor: error en fase {phase}: {exc}")

        return time.monotonic() - start

    def _safe_disconnect(self, connector: BaseConnector, result: SandboxResult) -> None:
        """
        Ejecuta disconnect() de forma segura, capturando cualquier error.

        Si la desconexion falla, registra el error pero no interrumpe
        el flujo de ejecucion.

        Args:
            connector: Instancia del conector
            result: Objeto SandboxResult para registrar errores y timing
        """
        start = time.monotonic()
        try:
            connector.disconnect()
        except Exception as exc:
            result.errors.append(f"Fase 'disconnect': {type(exc).__name__}: {exc}")
            logger.debug(f"SandboxExecutor: error en disconnect: {exc}")
        result.timing["disconnect"] = time.monotonic() - start

    @staticmethod
    # legítimo: retorna lo que func() retorna, dinámico por diseño
    def _run_with_timeout(func: Callable[..., Any], timeout: float) -> Any:
        """
        Ejecuta una funcion con un limite de tiempo.

        Utiliza threading para implementar el timeout ya que no todas
        las funciones son seguras para usar con signal.alarm.

        Args:
            func: Funcion a ejecutar
            timeout: Tiempo maximo en segundos

        Retorna:
            Resultado de la funcion

        Raises:
            TimeoutError: Si la funcion excede el tiempo limite
        """
        import threading

        result_container: list[Any] = [None]
        exception_container: list[Exception | None] = [None]

        def target() -> None:
            try:
                result_container[0] = func()
            except Exception as exc:
                exception_container[0] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            msg = f"Timeout: la ejecucion excedio {timeout} segundos"
            raise TimeoutError(msg)

        if exception_container[0] is not None:
            raise exception_container[0]

        return result_container[0]

    @staticmethod
    def _setup_mocks(patches: list[Any]) -> None:
        """
        Configura mocks de las dependencias de infraestructura del conector.

        Mockea RedisService y TelemetryService para que los conectores
        puedan ejecutarse sin depender de servicios externos.

        Args:
            patches: Lista donde se almacenan los mocks para limpieza posterior
        """
        try:
            from unittest.mock import patch

            redis_mock = patch("src.sdk.base.RedisService")
            telemetry_mock = patch("src.sdk.base.TelemetryService")

            redis_mock.start()
            telemetry_mock.start()

            patches.append(redis_mock)
            patches.append(telemetry_mock)

            logger.debug("SandboxExecutor: mocks de infraestructura configurados")
        except Exception as exc:
            logger.debug(f"SandboxExecutor: error configurando mocks: {exc}")

    @staticmethod
    def _teardown_mocks(patches: list[Any]) -> None:
        """
        Limpia los mocks de infraestructura configurados previamente.

            Detiene todos los patches activos para restaurar el comportamiento
            normal de las dependencias.

            Args:
                patches: Lista de mocks activos a detener
        """
        for p in patches:
            with suppress(Exception):
                p.stop()
        patches.clear()
        logger.debug("SandboxExecutor: mocks de infraestructura limpiados")
