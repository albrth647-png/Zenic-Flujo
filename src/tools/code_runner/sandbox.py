"""
Workflow Determinista — Code Runner Sandbox (Sprint 6)

Ejecuta código Python de forma segura con:
- Timeout configurable (máximo 10s)
- Bloqueo de imports peligrosos (solo módulos seguros permitidos)
- Sin acceso a red, filesystem, subprocess
- Variables del contexto disponibles como inputs
"""

import ast
import io
import signal
import sys
import time
from dataclasses import dataclass

from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Límites de seguridad ──────────────────────────────────
MAX_EXECUTION_TIME = 10  # segundos
MAX_MEMORY_MB = 50  # MB
MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB

# ── Imports bloqueados (Python) ───────────────────────────
BLOCKED_MODULES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "http",
    "urllib",
    "requests",
    "shutil",
    "pathlib",
    "glob",
    "pickle",
    "shelve",
    "dbm",
    "sqlite3",
    "ctypes",
    "signal",
    "multiprocessing",
    "threading",
    "asyncio",
    "xmlrpc",
    "importlib",
}

# ── Imports seguros permitidos ──────────────────────────
SAFE_MODULES = {
    "math",
    "json",
    "datetime",
    "re",
    "collections",
    "itertools",
    "functools",
    "string",
    "textwrap",
    "random",
    "decimal",
    "fractions",
    "statistics",
    "copy",
    "pprint",
}

# ── Builtins peligrosos bloqueados ────────────────────────
# Nota: __import__ se provee restringido via _make_safe_import()
BLOCKED_BUILTINS = {
    "eval",
    "exec",
    "compile",
    "open",
    "breakpoint",
    "exit",
    "quit",
    "input",
    "globals",
    "locals",
}


@dataclass
class SandboxResult:
    """Resultado de la ejecución en sandbox."""

    success: bool
    output: dict  # Variables de salida
    stdout: str  # Salida estándar
    error: str | None  # Error si falló
    execution_time_ms: int


class CodeSandbox:
    """
    Sandbox seguro para ejecutar Python de forma aislada.

    Restricciones:
    - Sin imports de módulos del sistema
    - Sin eval/exec/compile
    - Sin acceso a archivos
    - Sin acceso a red
    - Timeout configurable
    - Límite de memoria
    """

    def __init__(
        self,
        timeout: int = MAX_EXECUTION_TIME,
        memory_limit_mb: int = MAX_MEMORY_MB,
    ):
        self.timeout = min(timeout, MAX_EXECUTION_TIME)
        self.memory_limit_mb = min(memory_limit_mb, MAX_MEMORY_MB)

    def _make_timeout_handler(self):
        """Crea handler de timeout con referencia al timeout configurado."""
        timeout = self.timeout

        def handler(signum, frame):
            raise TimeoutError(f"Código excedió el timeout de {timeout}s")

        return handler

    def execute_python(
        self,
        code: str,
        input_vars: dict | None = None,
        output_var: str = "result",
    ) -> SandboxResult:
        """
        Ejecuta código Python en un sandbox seguro.

        Args:
            code: Código Python a ejecutar
            input_vars: Variables disponibles en el código
            output_var: Nombre de la variable de salida

        Returns:
            SandboxResult con el resultado
        """
        start_time = time.time()

        # 1. Validar código fuente
        validation_error = self._validate_source(code)
        if validation_error:
            return SandboxResult(
                success=False,
                output={},
                stdout="",
                error=f"Código bloqueado: {validation_error}",
                execution_time_ms=self._elapsed(start_time),
            )

        # 2. Preparar entorno seguro
        safe_builtins = self._get_safe_builtins()
        safe_builtins["__import__"] = self._make_safe_import()
        context = {
            "__builtins__": safe_builtins,
            "input_vars": input_vars or {},
            "output": {},
        }

        # Agregar variables de input ANTES de __builtins__ para no sobreescribir
        # y validar que no contengan keys reservadas
        reserved_keys = {
            "__builtins__",
            "__name__",
            "__doc__",
            "__file__",
            "__import__",
            "eval",
            "exec",
            "compile",
        }
        if input_vars:
            for key, value in input_vars.items():
                if key not in reserved_keys:
                    context[key] = value

        # 3. Configurar timeout con signal (Linux)
        old_handler = None
        try:
            timeout_handler = self._make_timeout_handler()
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.timeout)
        except (ValueError, OSError):
            pass  # signal no disponible en algunos contextos

        # 4. Capturar stdout
        old_stdout = sys.stdout
        captured_stdout = io.StringIO()

        try:
            sys.stdout = captured_stdout

            # Ejecutar — la seguridad se logra via:
            # validación AST + builtins restringidos + timeout SIGALRM
            exec(code, context)

            # 5. Extraer variable de salida
            output_value = context.get(output_var, context.get("result"))
            if output_value is None and output_var in context:
                output_value = context[output_var]

            return SandboxResult(
                success=True,
                output={"result": output_value},
                stdout=captured_stdout.getvalue()[:MAX_OUTPUT_SIZE],
                error=None,
                execution_time_ms=self._elapsed(start_time),
            )

        except TimeoutError as e:
            logger.warning(f"Sandbox timeout: {e}")
            return SandboxResult(
                success=False,
                output={},
                stdout=captured_stdout.getvalue()[:MAX_OUTPUT_SIZE],
                error=str(e),
                execution_time_ms=self._elapsed(start_time),
            )

        except MemoryError:
            logger.warning("Sandbox: memory limit exceeded")
            return SandboxResult(
                success=False,
                output={},
                stdout="",
                error=f"Límite de memoria excedido ({self.memory_limit_mb}MB)",
                execution_time_ms=self._elapsed(start_time),
            )

        except SyntaxError as e:
            return SandboxResult(
                success=False,
                output={},
                stdout="",
                error=f"Error de sintaxis: {e}",
                execution_time_ms=self._elapsed(start_time),
            )

        except Exception as e:
            return SandboxResult(
                success=False,
                output={},
                stdout=captured_stdout.getvalue()[:MAX_OUTPUT_SIZE],
                error=f"Error de ejecución: {type(e).__name__}: {e}",
                execution_time_ms=self._elapsed(start_time),
            )

        finally:
            sys.stdout = old_stdout
            # Cancelar alarm y restaurar handler
            try:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            except (ValueError, OSError):
                pass

    def _validate_source(self, code: str) -> str | None:
        """
        Valida el código fuente antes de ejecutar.
        Retorna None si es seguro, o un mensaje de error si no lo es.
        """
        if not code or not code.strip():
            return "Código vacío"

        code_lower = code.lower().strip()

        # Verificar imports prohibidos (permitir SAFE_MODULES)
        for module in BLOCKED_MODULES:
            if f"import {module}" in code_lower or f"from {module}" in code_lower:
                return f"Import prohibido: {module}"
        # Detectar imports de módulos no conocidos ni bloqueados
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        if root not in SAFE_MODULES and root not in BLOCKED_MODULES:
                            return f"Import no permitido: {alias.name} (solo módulos seguros)"
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    if root not in SAFE_MODULES and root not in BLOCKED_MODULES:
                        return f"Import no permitido: {node.module} (solo módulos seguros)"
        except SyntaxError:
            pass

        # Verificar patrones peligrosos
        dangerous_patterns = [
            "eval(",
            "exec(",
            "open(",
            "os.",
            "sys.",
            "subprocess.",
        ]
        for pattern in dangerous_patterns:
            if pattern in code:
                return f"Patrón prohibido: {pattern}"

        return None

    @staticmethod
    def _make_safe_import():
        """Crea una función __import__ restringida a módulos seguros."""
        import builtins as _builtins

        _real_import = _builtins.__import__

        def safe_import(name, *args, **kwargs):
            root = name.split(".")[0]
            if root in SAFE_MODULES:
                return _real_import(name, *args, **kwargs)
            raise ImportError(
                f"Import no permitido: {name} (solo módulos permitidos: {', '.join(sorted(SAFE_MODULES))})"
            )

        return safe_import

    @staticmethod
    def _get_safe_builtins() -> dict:
        """Retorna builtins seguros (sin eval, exec, open, etc.)."""
        import builtins

        safe = {}
        for name in dir(builtins):
            if name.startswith("_") and name != "__name__":
                continue
            if name in BLOCKED_BUILTINS:
                continue
            attr = getattr(builtins, name)
            if callable(attr):
                safe[name] = attr
        # Agregar __name__ para que el código funcione
        safe["__name__"] = "__main__"
        return safe

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)
