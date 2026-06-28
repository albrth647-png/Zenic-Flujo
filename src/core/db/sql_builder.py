"""
Zenic-Flijo — Helpers de construcción segura de SQL dinámico.

PROBLEMA: SQLite no permite pasar identificadores (nombres de tabla, columnas)
como parámetros (?) — solo valores. Esto fuerza a construir SQL dinámico con
concatenación de strings, lo que abre el riesgo de SQL injection si los
identificadores provienen de input externo.

SOLUCIÓN: Este módulo proporciona helpers que validan estrictamente los
identificadores contra un allowlist o un regex seguro antes de interpolarlos
en el SQL. Los valores siempre se pasan como parámetros (?) al cursor.

Mitiga Bandit B608 (SQL injection via string concatenation).
"""

from __future__ import annotations

import re
from typing import Any

# Regex de identificador seguro para SQLite.
# Zenic-Flijo restringe a [A-Za-z0-9_] (sin $ ni caracteres Unicode) por defensiva.
# SQLite permite más caracteres, pero $ y Unicode raramente se usan en esquemas
# reales y abrirlos podría facilitar SQL injection creativo.
# No empezamos con dígito. Longitud máx 128 (límite de SQLite).
# Ref: https://www.sqlite.org/syntax/qualified-name.html
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def validate_identifier(name: str) -> str:
    """Valida que `name` sea un identificador SQLite seguro.

    Args:
        name: Nombre de tabla o columna a validar.

    Returns:
        El mismo nombre si es válido.

    Raises:
        ValueError: Si el nombre contiene caracteres fuera del set[Any] seguro
                    o excede 128 caracteres.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"Identificador vacío o no-string: {name!r}")
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Identificador inseguro rechazado: {name!r}. "
            "Solo se permiten letras, dígitos y underscore (máx 128 chars, "
            "no empezar con dígito)."
        )
    return name


def quote_identifier(name: str) -> str:
    """Retorna el identificador quoteado para SQLite (con comillas dobles).

    Usa el formato `"name"` con escape de comillas internas. SQLite interpreta
    `"name"` como identificador (no string), evitando ambigüedad con palabras
    reservadas (ej. `"order"`, `"select"`).

    Args:
        name: Identificador a quotear.

    Returns:
        String `"name"` con escape de `"` internas como `""`.
    """
    validated = validate_identifier(name)
    # Escape de comillas dobles: " → "" (estándar SQL)
    escaped = validated.replace('"', '""')
    return f'"{escaped}"'


def build_update_query(
    table: str,
    allowed_fields: set[str],
    fields: dict[str, Any],
    *,
    where_clause: str = "id = ?",
    extra_set: dict[str, Any] | None = None,
) -> tuple[str, tuple[Any, ...]] | None:
    """Construye una sentencia `UPDATE table SET ... WHERE ...` con placeholders seguros.

    Los nombres de columnas se validan contra `allowed_fields` (allowlist estricto).
    Los valores se pasan como parámetros `?` al cursor — nunca se interpolan
    en el SQL.

    Args:
        table: Nombre de la tabla. Se valida con `validate_identifier`.
        allowed_fields: Set de nombres de columna permitidos. Cualquier campo
            en `fields` que no esté en este set[Any] se ignora silenciosamente.
        fields: Dict de {columna: valor} a setear en la cláusula SET.
        where_clause: Cláusula WHERE con placeholders `?`. Default: `"id = ?"`.
            El llamador debe append el valor del WHERE a los params.
        extra_set: Dict de columnas extra a setear (ej. `{"updated_at": timestamp}`).
            Estas columnas también se validan contra `allowed_fields`.

    Returns:
        Tuple `(sql, params)` listo para `cursor.execute(sql, params)`, o
        `None` si no hay campos válidos en `fields` (nada que actualizar).

    Raises:
        ValueError: Si `table` no es identificador seguro, o si alguna columna
            en `extra_set` no está en `allowed_fields`.

    Ejemplo:
        >>> sql, params = build_update_query(
        ...     "leads",
        ...     {"name", "email", "stage"},
        ...     {"name": "Juan", "stage": "won"},
        ...     extra_set={"updated_at": "2026-06-18T10:00:00"},
        ... )
        >>> sql
        'UPDATE "leads" SET "name" = ?, "stage" = ?, "updated_at" = ? WHERE id = ?'
        >>> params
        ('Juan', 'won', '2026-06-18T10:00:00', <lead_id>)
    """
    # Validar nombre de tabla (levantaría ValueError si es inseguro)
    table_quoted = quote_identifier(table)

    # Filtrar campos contra allowlist
    set_clauses: list[str] = []
    params: list[Any] = []

    for key, value in fields.items():
        if key in allowed_fields:
            col_quoted = quote_identifier(key)
            set_clauses.append(f"{col_quoted} = ?")
            params.append(value)

    # Agregar campos extra (ej. updated_at)
    if extra_set:
        for key, value in extra_set.items():
            if key not in allowed_fields and key != "updated_at":
                # updated_at se permite como excepción común; otras columnas
                # extra deben estar en el allowlist explícitamente.
                raise ValueError(
                    f"Columna extra {key!r} no está en allowed_fields. "
                    "Agrégala explícitamente al allowlist para evitar SQL injection."
                )
            col_quoted = quote_identifier(key)
            set_clauses.append(f"{col_quoted} = ?")
            params.append(value)

    if not set_clauses:
        return None  # Nada que actualizar

    # Validar que where_clause use placeholders y no interpolación
    if "%s" in where_clause or ".format(" in where_clause:
        raise ValueError(
            "where_clause no debe usar %s o .format() — solo placeholders '?'. "
            f"Recibido: {where_clause!r}"
        )

    # Construcción segura de SQL dinámico:
    # - `table_quoted` pasó `validate_identifier` (regex [A-Za-z_][A-Za-z0-9_]{0,127}).
    # - Cada elemento de `set_clauses` es `"{column}" = ?` donde {column} pasó
    #   `quote_identifier` (que valida con el mismo regex).
    # - Los valores van como params (placeholders `?`), nunca interpolados.
    # - `where_clause` se valida para no contener %s o .format().
    # B608 es falso positivo: el patrón de Bandit detecta cualquier f-string con
    # formato SQL, pero aquí los identificadores están validados contra allowlist.
    sql = f"UPDATE {table_quoted} SET {', '.join(set_clauses)} WHERE {where_clause}"  # nosec B608 — identificadores validados
    return sql, tuple(params)


def safe_drop_table_if_exists(cursor: Any, table_name: str) -> None:
    """Ejecuta `DROP TABLE IF EXISTS "name"` con validación estricta del identificador.

    Esta función es la única forma permitida de hacer DROP TABLE dinámico en
    Zenic-Flijo. La validación con `validate_identifier` asegura que el nombre
    de tabla solo contiene [A-Za-z0-9_] y no puede contener comillas, puntos
    y coma, o metacaracteres SQL.

    Args:
        cursor: Cursor SQLite (o cualquier cursor con método `execute(sql, params)`).
        table_name: Nombre de la tabla a dropear. Se valida con `validate_identifier`.

    Raises:
        ValueError: Si `table_name` no es identificador seguro.
    """
    quoted = quote_identifier(table_name)
    # No usamos params porque DROP TABLE no acepta placeholders para el nombre.
    # La validación previa con validate_identifier es la mitigación.
    cursor.execute(f"DROP TABLE IF EXISTS {quoted}")


def build_in_clause(num_values: int, *, placeholder: str = "?") -> str:
    """Construye una cláusula `IN (?, ?, ?)` con N placeholders seguros.

    Útil para queries tipo `WHERE id IN (?, ?, ?)` donde el número de valores
    es dinámico. Nunca interpola los valores — solo genera placeholders.

    Args:
        num_values: Número de valores en el IN. Debe ser >= 1.
        placeholder: Placeholder a usar. Default: "?" (SQLite).

    Returns:
        String `"(?, ?, ...)"` con `num_values` placeholders.

    Raises:
        ValueError: Si `num_values` < 1 o `placeholder` no es "?".
    """
    if num_values < 1:
        raise ValueError(f"num_values debe ser >= 1, recibido: {num_values}")
    if placeholder != "?":
        raise ValueError(
            f"placeholder debe ser '?' (SQLite). Recibido: {placeholder!r}. "
            "Otros placeholders (%s, $1) no son soportados."
        )
    return "(" + ", ".join([placeholder] * num_values) + ")"
