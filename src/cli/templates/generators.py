"""
Zenic CLI — Generadores de Codigo para Conectores
==================================================

Genera codigo boilerplate para crear nuevos conectores, soportando
todos los tipos de autenticacion disponibles en el SDK.
"""

from __future__ import annotations

import json
from typing import Any

from src.cli.templates.helpers import (
    AUTH_CONNECT_BODIES,
    AUTH_IMPORTS,
    AUTH_SETUP_CODES,
    AUTH_VALIDATE_BODIES,
    to_class_name,
)
from src.core.logging import setup_logging

logger = setup_logging(__name__)


def generate_connector_code(name: str, category: str, auth_type: str) -> str:
    """
    Genera el codigo Python completo para un conector con el tipo de autenticacion dado.

    Crea una clase que hereda de BaseConnector e implementa los metodos
    abstractos connect(), execute(), validate() y disconnect(). El codigo
    generado incluye manejo de autenticacion segun el tipo seleccionado
    y un despachador de acciones basico.

    Args:
        name: Nombre del conector en formato snake_case (ej: 'mi_conector')
        category: Categoria del conector (ej: 'messaging', 'crm', 'storage')
        auth_type: Tipo de autenticacion ('api_key', 'basic', 'oauth2', 'oauth1', 'mtls', 'custom', 'none')

    Retorna:
        Codigo fuente Python completo como string, listo para escribir a archivo
    """
    class_name = to_class_name(name)
    auth_import = AUTH_IMPORTS.get(auth_type, "")
    auth_setup = AUTH_SETUP_CODES.get(auth_type, "")
    connect_body = AUTH_CONNECT_BODIES.get(auth_type, "        self._connected = True\n        return True")
    validate_body = AUTH_VALIDATE_BODIES.get(auth_type, "        return True")

    return f'''\
"""
Conector {class_name} — {category.capitalize()}
===============================================

Conector generado automaticamente por zenic-cli.
Tipo de autenticacion: {auth_type}
Categoria: {category}

Para personalizar:
1. Implemente la logica de conexion en connect()
2. Agregue acciones en execute()
3. Defina esquemas de entrada/salida en schema.py
4. Configure las credenciales necesarias
"""

from __future__ import annotations

from typing import Any
{auth_import}
from src.sdk.base import BaseConnector


class {class_name}(BaseConnector):
    """Conector para {name.replace("_", " ").title()} ({category})."""

    name = "{name}"
    version = "1.0.0"
    description = "Conector {name.replace("_", " ")} - generado por zenic-cli"
    category = "{category}"
    icon = "plug"
    author = ""

{auth_setup}
    def connect(self) -> bool:
        """Establece la conexion con el servicio externo."""
{connect_body}

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion

        Retorna:
            Resultado de la accion ejecutada

        Raises:
            ValueError: Si la accion no esta soportada
        """
        action_map = {{
            "ping": self._action_ping,
        }}

        handler = action_map.get(action)
        if handler is None:
            available = ", ".join(sorted(action_map.keys()))
            msg = f"Accion '{{action}}' no soportada. Disponibles: {{available}}"
            raise ValueError(msg)

        return handler(params)

    def validate(self) -> bool:
        """Valida la configuracion del conector."""
{validate_body}

    def disconnect(self) -> bool:
        """Cierra la conexion con el servicio externo."""
        self._connected = False
        self._log_operation("disconnect", "Desconexion exitosa")
        return True

    # -- Acciones de ejemplo ------------------------------------

    @staticmethod
    def _action_ping(params: dict[str, Any]) -> dict[str, Any]:
        """Accion de verificacion de salud del conector.

        Args:
            params: Parametros (no utilizados en esta accion)

        Retorna:
            Diccionario con estado del conector
        """
        return {{"status": "ok", "message": "pong"}}
'''


def generate_schema_code(name: str) -> str:
    """
    Genera el codigo Python para la definicion del esquema del conector.

    Crea un archivo schema.py con definiciones de modelos Pydantic para
    las entradas y salidas de las acciones del conector.

    Args:
        name: Nombre del conector en formato snake_case

    Retorna:
        Codigo fuente Python con los modelos Pydantic y ConnectorSchema
    """
    class_name = to_class_name(name)

    return f'''\
"""
Esquema del Conector {class_name}
===================================

Define los modelos de entrada/salida y el esquema completo
del conector usando Pydantic y ConnectorSchema.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema


# -- Modelos de Entrada/Salida ---------------------------------


class PingInput(BaseModel):
    """Modelo de entrada para la accion ping."""

    message: str = Field(default="hello", description="Mensaje de verificacion")


class PingOutput(BaseModel):
    """Modelo de salida para la accion ping."""

    status: str = Field(description="Estado de la respuesta")
    message: str = Field(description="Mensaje de respuesta")


# -- Esquema del Conector --------------------------------------


def build_schema() -> ConnectorSchema:
    """Construye y retorna el esquema completo del conector.

    Retorna:
        Instancia de ConnectorSchema con todas las definiciones
    """
    return ConnectorSchema(
        name="{name}",
        version="1.0.0",
        description="Conector {name.replace("_", " ")}",
        category="general",
        icon="plug",
        author="",
        actions=[
            ActionDefinition(
                name="ping",
                description="Verifica la disponibilidad del conector",
                input_schema=PingInput,
                output_schema=PingOutput,
                category="read",
                timeout=10,
            ),
        ],
        auth_requirements=_build_auth_requirements(),
        tags=["auto-generated"],
    )


def _build_auth_requirements() -> list[AuthRequirement]:
    """Construye los requisitos de autenticacion del conector.

    Modifique esta funcion para agregar los requisitos de auth
    que su conector necesite.

    Retorna:
        Lista de AuthRequirement con los metodos de auth soportados
    """
    return []


# -- Esquema singleton -----------------------------------------

SCHEMA = build_schema()
'''


def generate_test_code(name: str) -> str:
    """
    Genera el codigo Python para las pruebas unitarias del conector.

    Crea un archivo de tests con pruebas basicas para verificar:
    - Instanciacion del conector
    - Conexion y desconexion
    - Ejecucion de acciones (ping)
    - Validacion del conector
    - Propiedades basicas (name, version, category)

    Args:
        name: Nombre del conector en formato snake_case

    Retorna:
        Codigo fuente Python con las pruebas unitarias
    """
    class_name = to_class_name(name)
    module_path = f"src.connectors.{name}.connector"

    return f'''\
"""
Pruebas Unitarias del Conector {class_name}
==============================================

Pruebas automaticas generadas por zenic-cli para verificar
el funcionamiento basico del conector.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Agregar la raiz del proyecto al path para importar el conector
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.sdk.base import BaseConnector
from src.sdk.registry import ConnectorRegistry


# -- Fixtures ---------------------------------------------------


@pytest.fixture
def connector_class():
    """Obtiene la clase del conector desde el registro."""
    # Intentar importar dinamicamente
    try:
        import importlib
        module = importlib.import_module("{module_path}")
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseConnector)
                and attr is not BaseConnector
                and getattr(attr, "name", "") == "{name}"
            ):
                return attr
    except ImportError:
        pass

    # Fallback: buscar en el registro
    cls = ConnectorRegistry.get("{name}")
    if cls is not None:
        return cls

    pytest.skip("Conector '{name}' no encontrado")
    return None


@pytest.fixture
def connector(connector_class):
    """Crea una instancia del conector para las pruebas."""
    # Mockear dependencias de infraestructura
    with patch("src.sdk.base.RedisService"), \\
         patch("src.sdk.base.TelemetryService"):
        instance = connector_class()
    return instance


# -- Pruebas de Instanciacion ----------------------------------


class TestConnectorInstantiation:
    """Pruebas de creacion del conector."""

    def test_connector_is_base_connector_subclass(self, connector_class):
        """Verifica que el conector hereda de BaseConnector."""
        assert issubclass(connector_class, BaseConnector)

    def test_connector_has_name(self, connector):
        """Verifica que el conector tiene un nombre definido."""
        assert connector.name == "{name}"

    def test_connector_has_version(self, connector):
        """Verifica que el conector tiene una version definida."""
        assert connector.version
        assert isinstance(connector.version, str)

    def test_connector_has_category(self, connector):
        """Verifica que el conector tiene una categoria definida."""
        assert connector.category


# -- Pruebas de Conexion ---------------------------------------


class TestConnectorConnection:
    """Pruebas del ciclo de conexion del conector."""

    def test_connect_returns_bool(self, connector):
        """Verifica que connect() retorna un booleano."""
        with patch("src.sdk.base.RedisService"), \\
             patch("src.sdk.base.TelemetryService"):
            result = connector.connect()
        assert isinstance(result, bool)

    def test_disconnect_returns_bool(self, connector):
        """Verifica que disconnect() retorna un booleano."""
        result = connector.disconnect()
        assert isinstance(result, bool)

    def test_validate_returns_bool(self, connector):
        """Verifica que validate() retorna un booleano."""
        result = connector.validate()
        assert isinstance(result, bool)


# -- Pruebas de Ejecucion --------------------------------------


class TestConnectorExecution:
    """Pruebas de ejecucion de acciones del conector."""

    def test_execute_ping_action(self, connector):
        """Verifica que la accion ping funciona correctamente."""
        with patch("src.sdk.base.RedisService"), \\
             patch("src.sdk.base.TelemetryService"):
            connector.connect()
        result = connector.execute("ping", {{}})
        assert isinstance(result, dict)
        assert result.get("status") == "ok"

    def test_execute_unknown_action_raises(self, connector):
        """Verifica que una accion desconocida lanza error."""
        with pytest.raises((ValueError, Exception)):
            connector.execute("accion_inexistente", {{}})
'''


def generate_manifest(name: str, version: str, category: str, author: str) -> str:
    """
    Genera el contenido JSON del archivo manifest.json para publicacion.

    El manifest contiene la metadata completa del conector necesaria
    para el marketplace: nombre, version, categoria, autor, acciones,
    requisitos de autenticacion y metadatos adicionales.

    Args:
        name: Nombre del conector
        version: Version del conector en formato semver
        category: Categoria del conector
        author: Autor o equipo responsable del conector

    Retorna:
        String JSON formateado con el manifest del conector
    """
    manifest: dict[str, Any] = {
        "name": name,
        "version": version,
        "category": category,
        "author": author,
        "description": f"Conector {name.replace('_', ' ')}",
        "icon": "plug",
        "sdk_version": "1.0.0",
        "min_platform_version": "1.0.0",
        "actions": [
            {
                "name": "ping",
                "description": "Verifica la disponibilidad del conector",
                "category": "read",
            },
        ],
        "auth_requirements": [],
        "tags": ["auto-generated"],
        "files": [
            "__init__.py",
            "connector.py",
            "schema.py",
            "tests/test_connector.py",
            "manifest.json",
        ],
    }
    return json.dumps(manifest, indent=2, ensure_ascii=False)


def generate_init_code(name: str) -> str:
    """
    Genera el codigo para el archivo __init__.py del conector.

    Incluye la version del conector y las importaciones publicas
    para facilitar el uso del conector como paquete Python.

    Args:
        name: Nombre del conector en formato snake_case

    Retorna:
        Codigo fuente Python para __init__.py
    """
    class_name = to_class_name(name)

    return f'''\
"""
Conector {class_name}
======================

Paquete del conector {name.replace("_", " ")}.
"""

from __future__ import annotations

__version__ = "1.0.0"
__connector_name__ = "{name}"

from src.connectors.{name}.connector import {class_name}  # noqa: E402

__all__ = ["{class_name}", "__version__", "__connector_name__"]
'''
