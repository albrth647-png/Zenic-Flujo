"""validate_input and validate_output decorators for Pydantic schema validation.

Extracted from src/sdk/decorators.py.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from src.sdk.decorators._helpers import _get_connector_name
from src.sdk.exceptions import ValidationError

F = TypeVar("F", bound=Callable[..., Any])


def validate_input(schema: type[BaseModel]) -> Callable[[F], F]:
    """Valida los parametros de entrada de una accion contra un modelo Pydantic."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        # legítimo: wrapper transparente (skill §1.2)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)
            if len(args) > 1 and isinstance(args[1], dict):
                params_data = args[1]
            elif "params" in kwargs and isinstance(kwargs["params"], dict):
                params_data = kwargs["params"]
            else:
                params_data = kwargs
            try:
                validated = schema.model_validate(params_data)
                if len(args) > 1 and isinstance(args[1], dict):
                    args = (args[0], validated.model_dump(), *args[2:])  # type: ignore[assignment]
                elif "params" in kwargs:
                    kwargs["params"] = validated.model_dump()
                else:
                    kwargs = validated.model_dump()
            except Exception as e:
                raise ValidationError.from_pydantic(validation_exception=e, connector_name=connector_name, action=action_name) from e
            return func(*args, **kwargs)

        wrapper._input_schema = schema  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def validate_output(schema: type[BaseModel]) -> Callable[[F], F]:
    """Valida el resultado de una accion contra un modelo Pydantic."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        # legítimo: wrapper transparente (skill §1.2)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)
            result = func(*args, **kwargs)
            if isinstance(result, dict):
                try:
                    schema.model_validate(result)
                except Exception as e:
                    raise ValidationError.from_pydantic(validation_exception=e, connector_name=connector_name, action=action_name) from e
            return result

        wrapper._output_schema = schema  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
