"""
Workflow Determinista — Data Keeper Modelos
Define las estructuras de datos para colecciones dinámicas.
"""

import re

# Tipos de datos soportados para los campos de una colección
SUPPORTED_TYPES = {"string", "number", "boolean", "text", "date"}


def validate_name(name: str) -> None:
    """
    Valida que un nombre (colección o campo) sea seguro para SQL.
    Solo permite: letras, números, guión bajo. Sin espacios, sin SQL injection.
    """
    if not name or not isinstance(name, str):
        raise ValueError("El nombre no puede estar vacío")
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise ValueError(f"Nombre inválido: '{name}'. Solo letras, números y guión bajo. No puede empezar con número.")


def validate_schema(schema: dict) -> None:
    """Valida que un schema de colección sea correcto."""
    if not schema or not isinstance(schema, dict):
        raise ValueError("El schema debe ser un diccionario no vacío")

    for field_name, field_type in schema.items():
        validate_name(field_name)
        if field_type not in SUPPORTED_TYPES:
            raise ValueError(
                f"Tipo '{field_type}' no soportado para campo '{field_name}'. "
                f"Tipos válidos: {', '.join(sorted(SUPPORTED_TYPES))}"
            )


def validate_record(record: dict, schema: dict) -> None:
    """Valida que un registro cumpla con el schema de la colección."""
    for field_name in record:
        if field_name in ("id", "created_at", "updated_at"):
            continue
        if field_name not in schema:
            raise ValueError(
                f"Campo '{field_name}' no está en el schema de la colección. Campos permitidos: {list(schema.keys())}"
            )
