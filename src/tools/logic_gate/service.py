"""
Workflow Determinista — LogicGate Service
Servicio de evaluación de reglas lógicas con persistencia en SQLite.
Permite guardar, listar, evaluar y eliminar reglas.
"""

import json

from src.data.database_manager import DatabaseManager
from src.events.bus import EventBus
from src.utils.logger import setup_logging
from src.workflow.condition_evaluator import ConditionEvaluator
from typing import Any

logger = setup_logging(__name__)


class LogicGateService:
    """
    Servicio de puertas lógicas para el workflow engine.

    Permite:
    - Evaluar expresiones condicionales en runtime (usando parser seguro)
    - Guardar reglas nombradas en la base de datos
    - Listar y recuperar reglas guardadas
    - Validar expresiones antes de usarlas
    """

    def __init__(self, event_bus: EventBus | None = None):
        self._evaluator = ConditionEvaluator()
        self._db = DatabaseManager()
        self._event_bus = event_bus or EventBus()

    def evaluate_rule(self, rule: str, context: dict[str, Any]) -> bool:
        """
        Evalúa una regla condicional contra un contexto dado.

        Args:
            rule: Expresión como "stock < 10 AND precio > 100"
            context: Dict con variables disponibles, ej: {"stock": 5, "precio": 150}

        Returns:
            bool: Resultado de la evaluación
        """
        return self._evaluator.evaluate(rule, context)

    def validate_expression(self, expression: str) -> dict[str, Any]:
        """
        Valida que una expresión sea sintácticamente correcta.

        Returns:
            dict: {"valid": True} o {"valid": False, "error": "mensaje"}
        """
        return self._evaluator.validate_expression(expression)

    def save_rule(self, name: str, expression: str, description: str = "") -> dict[str, Any]:
        """
        Guarda una regla nombrada en la base de datos.

        Args:
            name: Nombre único de la regla
            expression: Expresión condicional válida
            description: Descripción opcional

        Returns:
            dict: La regla guardada
        """
        # Validar antes de guardar
        validation = self.validate_expression(expression)
        if not validation.get("valid"):
            raise ValueError(f"Expresión inválida: {validation.get('error', 'unknown')}")

        self._db.execute(
            """INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)""",
            (
                f"logic_rule_{name}",
                json.dumps(
                    {
                        "name": name,
                        "expression": expression,
                        "description": description,
                    }
                ),
            ),
        )
        self._db.commit()
        logger.info(f"Regla lógica guardada: {name}")
        return {"name": name, "expression": expression, "description": description}

    def get_rule(self, name: str) -> dict[str, Any] | None:
        """Recupera una regla guardada por nombre."""
        row = self._db.fetchone(
            "SELECT value FROM settings WHERE key = ?",
            (f"logic_rule_{name}",),
        )
        if row:
            return json.loads(row["value"])
        return None

    def list_rules(self) -> list[dict]:
        """Lista todas las reglas guardadas."""
        rows = self._db.fetchall("SELECT value FROM settings WHERE key LIKE 'logic_rule_%'")
        return [json.loads(row["value"]) for row in rows]

    def delete_rule(self, name: str) -> bool:
        """Elimina una regla guardada."""
        self._db.execute(
            "DELETE FROM settings WHERE key = ?",
            (f"logic_rule_{name}",),
        )
        self._db.commit()
        logger.info(f"Regla lógica eliminada: {name}")
        return True

    def evaluate_saved_rule(self, name: str, context: dict[str, Any]) -> bool:
        """Evalúa una regla guardada por nombre contra un contexto."""
        rule = self.get_rule(name)
        if not rule:
            raise ValueError(f"Regla '{name}' no encontrada")
        return self.evaluate_rule(rule["expression"], context)
