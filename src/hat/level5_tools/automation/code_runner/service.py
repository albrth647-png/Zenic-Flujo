"""
Workflow Determinista — Code Runner Service (Sprint 6)

Ejecuta código Python desde workflows de forma segura.
Permite al usuario escribir lógica custom en un paso del workflow.

Uso en workflow:
{
    "tool": "code_runner",
    "action": "run_python",
    "params": {
        "code": "result = sum([item['price'] * item['qty'] for item in $input.items])",
        "input_vars": {"items": "$input.carrito"},
        "output_var": "total"
    }
}

Seguridad:
- Sandbox aislado con timeout (10s) y límite de memoria (50MB)
- Bloqueo de imports peligrosos (os, sys, subprocess)
- Bloqueo de eval/exec/open
- Sin acceso a red ni filesystem
"""

from src.core.logging import setup_logging
from src.hat.level5_tools.automation.code_runner.sandbox import CodeSandbox, SandboxResult
from typing import Any

logger = setup_logging(__name__)


class CodeRunnerTool:
    """
    Ejecuta código Python de forma segura en workflows.

    Acciones disponibles:
    - run_python: Ejecuta código Python en sandbox seguro
    - validate: Valida código sin ejecutarlo
    """

    def __init__(self):
        self._sandbox = CodeSandbox()

    def run_python(
        self,
        code: str = "",
        input_vars: dict[str, Any] | None = None,
        output_var: str = "result",
        timeout: int = 10,
    ) -> dict[str, Any]:
        """
        Ejecuta código Python en el sandbox seguro.

        Args:
            code: Código Python a ejecutar
            input_vars: Variables de entrada disponibles en el código
            output_var: Nombre de la variable que contiene el resultado
            timeout: Timeout en segundos (máximo 10)

        Returns:
            dict con: success, output, stdout, error, execution_time_ms
        """
        if not code or not code.strip():
            return {
                "success": False,
                "output": {},
                "stdout": "",
                "error": "Código vacío",
                "execution_time_ms": 0,
            }

        sandbox = CodeSandbox(timeout=min(timeout, 10))

        result: SandboxResult = sandbox.execute_python(
            code=code,
            input_vars=input_vars or {},
            output_var=output_var,
        )

        logger.info(f"Code runner: {'OK' if result.success else 'FAIL'} ({result.execution_time_ms}ms)")

        return {
            "success": result.success,
            "output": result.output,
            "stdout": result.stdout,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
        }

    def validate(self, code: str = "") -> dict[str, Any]:
        """
        Valida código Python sin ejecutarlo.

        Args:
            code: Código Python a validar

        Returns:
            dict con: valid, errors, warnings
        """
        if not code or not code.strip():
            return {
                "valid": False,
                "errors": ["Código vacío"],
                "warnings": [],
            }

        sandbox = CodeSandbox()
        error = sandbox._validate_source(code)

        if error:
            return {
                "valid": False,
                "errors": [error],
                "warnings": [],
            }

        # Verificar sintaxis
        try:
            import ast

            ast.parse(code)
        except SyntaxError as e:
            return {
                "valid": False,
                "errors": [f"Error de sintaxis: {e}"],
                "warnings": [],
            }

        return {
            "valid": True,
            "errors": [],
            "warnings": [],
        }

    @staticmethod
    def get_tool_definition() -> dict[str, Any]:
        """Retorna la definición de la tool para el editor visual."""
        return {
            "tool": "code_runner",
            "name": "Code Runner",
            "description": "Ejecuta código Python de forma segura en un sandbox aislado",
            "actions": {
                "run_python": {
                    "name": "Ejecutar Python",
                    "description": "Ejecuta código Python en un sandbox seguro",
                    "params": [
                        {
                            "name": "code",
                            "type": "code",
                            "required": True,
                            "label": "Código Python",
                            "placeholder": "result = sum([1, 2, 3])",
                        },
                        {
                            "name": "input_vars",
                            "type": "dict",
                            "required": False,
                            "default": {},
                            "label": "Variables de entrada",
                            "placeholder": '{"datos": "$input.clientes"}',
                        },
                        {
                            "name": "output_var",
                            "type": "string",
                            "required": False,
                            "default": "result",
                            "label": "Variable de salida",
                        },
                        {
                            "name": "timeout",
                            "type": "number",
                            "required": False,
                            "default": 10,
                            "label": "Timeout (segundos, máx 10)",
                        },
                    ],
                },
                "validate": {
                    "name": "Validar código",
                    "description": "Valida código Python sin ejecutarlo",
                    "params": [
                        {
                            "name": "code",
                            "type": "code",
                            "required": True,
                            "label": "Código Python a validar",
                        },
                    ],
                },
            },
        }
