"""
Connector SDK — Definicion de Esquemas con Pydantic
=====================================================

Sistema de definicion de esquemas para conectores que permite:

- Definir entradas, salidas, acciones y requisitos de autenticacion
- Validar datos de entrada/salida contra esquemas Pydantic
- Generar especificaciones OpenAPI automaticamente
- Versionar esquemas para compatibilidad hacia atras

Uso tipico:
    from src.sdk.schema import ConnectorSchema, ActionDefinition

    class SendEmailInput(BaseModel):
        to: str
        subject: str
        body: str

    class SendEmailOutput(BaseModel):
        message_id: str
        status: str

    schema = ConnectorSchema(
        name="gmail",
        version="1.0.0",
        actions=[
            ActionDefinition(
                name="send_email",
                description="Envia un correo electronico",
                input_schema=SendEmailInput,
                output_schema=SendEmailOutput,
            )
        ]
    )
"""

from __future__ import annotations

import copy
import json
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from src.sdk.exceptions import SchemaError, ValidationError
from src.core.logging import setup_logging

logger = setup_logging(__name__)


# ── Modelos Base ──────────────────────────────────────────────


class AuthRequirement(BaseModel):
    """
    Requisito de autenticacion para un conector.

    Define que tipo de autenticacion requiere un conector
    y cuales son los campos obligatorios.

    Attributes:
        auth_type: Tipo de autenticacion requerida (api_key, basic, oauth2, oauth1, mtls, custom)
        required_fields: Lista de campos obligatorios para la autenticacion
        optional_fields: Lista de campos opcionales
        description: Descripcion del metodo de autenticacion
    """

    auth_type: str = Field(description="Tipo de autenticacion requerida")
    required_fields: list[str] = Field(default_factory=list, description="Campos obligatorios para la autenticacion")
    optional_fields: list[str] = Field(default_factory=list, description="Campos opcionales de la autenticacion")
    description: str = Field(default="", description="Descripcion del metodo de autenticacion")


class ActionDefinition(BaseModel):
    """
    Definicion de una accion del conector.

    Cada accion representa una operacion que el conector puede realizar,
    con sus esquemas de entrada y salida definidos por modelos Pydantic.

    Attributes:
        name: Nombre unico de la accion (kebab-case recomendado)
        description: Descripcion legible de la accion
        input_schema: Modelo Pydantic para validar entradas
        output_schema: Modelo Pydantic para validar salidas
        category: Categoria de la accion (read, write, delete, etc.)
        deprecated: Si la accion esta deprecada
        deprecation_message: Mensaje si la accion esta deprecada
        rate_limit: Limite de frecuencia especifico de la accion (max_calls/period_seconds)
        timeout: Timeout en segundos para la accion
        tags: Etiquetas para clasificar la accion
    """

    name: str = Field(description="Nombre unico de la accion")
    description: str = Field(default="", description="Descripcion legible de la accion")
    input_schema: type[BaseModel] | None = Field(default=None, description="Modelo Pydantic para entradas")
    output_schema: type[BaseModel] | None = Field(default=None, description="Modelo Pydantic para salidas")
    category: str = Field(default="general", description="Categoria de la accion")
    deprecated: bool = Field(default=False, description="Si la accion esta deprecada")
    deprecation_message: str = Field(default="", description="Mensaje de deprecacion")
    rate_limit: dict[str, int] | None = Field(default=None, description="Limite de frecuencia de la accion")
    timeout: int = Field(default=30, description="Timeout en segundos para la accion")
    tags: list[str] = Field(default_factory=list, description="Etiquetas de clasificacion")

    model_config: ClassVar[dict[str, Any]] = {"arbitrary_types_allowed": True}

    def get_input_schema_json(self) -> dict[str, Any]:
        """
        Obtiene el esquema JSON de entrada de la accion.

        Retorna:
            Diccionario con el JSON Schema del modelo de entrada,
            o diccionario vacio si no esta definido
        """
        if self.input_schema is None:
            return {}
        return self.input_schema.model_json_schema()

    def get_output_schema_json(self) -> dict[str, Any]:
        """
        Obtiene el esquema JSON de salida de la accion.

        Retorna:
            Diccionario con el JSON Schema del modelo de salida,
            o diccionario vacio si no esta definido
        """
        if self.output_schema is None:
            return {}
        return self.output_schema.model_json_schema()


class ConnectorSchema(BaseModel):
    """
    Esquema completo de un conector.

    Define la interfaz completa de un conector: sus entradas, salidas,
    acciones disponibles y requisitos de autenticacion.

    Attributes:
        name: Nombre unico del conector
        version: Version del esquema (semver)
        description: Descripcion del conector
        category: Categoria del conector (messaging, crm, storage, etc.)
        icon: Nombre del icono o URL para el conector
        author: Autor del conector
        actions: Lista de acciones disponibles
        auth_requirements: Requisitos de autenticacion
        inputs: Modelo Pydantic para la configuracion global del conector
        outputs: Modelo Pydantic para la salida global del conector
        tags: Etiquetas de clasificacion
        homepage: URL del sitio web del conector
        docs_url: URL de la documentacion del conector
    """

    name: str = Field(description="Nombre unico del conector")
    version: str = Field(default="1.0.0", description="Version del esquema (semver)")
    description: str = Field(default="", description="Descripcion del conector")
    category: str = Field(default="general", description="Categoria del conector")
    icon: str = Field(default="plug", description="Nombre del icono o URL")
    author: str = Field(default="", description="Autor del conector")
    actions: list[ActionDefinition] = Field(default_factory=list, description="Acciones disponibles")
    auth_requirements: list[AuthRequirement] = Field(default_factory=list, description="Requisitos de autenticacion")
    inputs: type[BaseModel] | None = Field(default=None, description="Modelo de configuracion global")
    outputs: type[BaseModel] | None = Field(default=None, description="Modelo de salida global")
    tags: list[str] = Field(default_factory=list, description="Etiquetas de clasificacion")
    homepage: str = Field(default="", description="URL del sitio web")
    docs_url: str = Field(default="", description="URL de la documentacion")

    model_config: ClassVar[dict[str, Any]] = {"arbitrary_types_allowed": True}

    def get_action(self, name: str) -> ActionDefinition | None:
        """
        Obtiene una accion por su nombre.

        Args:
            name: Nombre de la accion a buscar

        Retorna:
            La definicion de la accion, o None si no existe
        """
        for action in self.actions:
            if action.name == name:
                return action
        return None

    def get_actions_by_category(self, category: str) -> list[ActionDefinition]:
        """
        Obtiene todas las acciones de una categoria.

        Args:
            category: Categoria a filtrar

        Retorna:
            Lista de acciones que pertenecen a la categoria
        """
        return [a for a in self.actions if a.category == category]

    def get_action_names(self) -> list[str]:
        """
        Obtiene los nombres de todas las acciones disponibles.

        Retorna:
            Lista de nombres de acciones
        """
        return [a.name for a in self.actions]

    def add_action(self, action: ActionDefinition) -> None:
        """
        Agrega una nueva accion al esquema del conector.

        Verifica que no exista una accion con el mismo nombre.

        Args:
            action: Definicion de la accion a agregar

        Raises:
            SchemaError: Si ya existe una accion con el mismo nombre
        """
        if self.get_action(action.name):
            raise SchemaError(
                message=f"Accion duplicada: {action.name}",
                connector_name=self.name,
                conflict_field=f"actions.{action.name}",
            )
        self.actions.append(action)

    def remove_action(self, name: str) -> bool:
        """
        Elimina una accion del esquema por su nombre.

        Args:
            name: Nombre de la accion a eliminar

        Retorna:
            True si la accion fue eliminada, False si no existia
        """
        for i, action in enumerate(self.actions):
            if action.name == name:
                self.actions.pop(i)
                return True
        return False


# ── Validador de Esquemas ────────────────────────────────────


class SchemaValidator:
    """
    Validador de datos contra esquemas de conectores.

    Valida datos de entrada y salida contra los esquemas Pydantic
    definidos en las acciones del conector. Provee mensajes de error
    detallados para facilitar el diagnostico.

    Attributes:
        schema: Esquema del conector contra el cual validar
        strict: Si True, rechaza campos no definidos en el esquema
    """

    def __init__(self, schema: ConnectorSchema, strict: bool = False) -> None:
        self._schema = schema
        self._strict = strict

    def validate_input(self, action_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Valida datos de entrada contra el esquema de una accion.

        Args:
            action_name: Nombre de la accion
            data: Datos de entrada a validar

        Retorna:
            Datos validados y posiblemente transformados por Pydantic

        Raises:
            ActionNotFoundError: Si la accion no existe en el esquema
            ValidationError: Si los datos no cumplen el esquema
        """
        action = self._schema.get_action(action_name)
        if action is None:
            from src.sdk.exceptions import ActionNotFoundError

            raise ActionNotFoundError(
                message=f"Accion '{action_name}' no encontrada en conector '{self._schema.name}'",
                connector_name=self._schema.name,
                action=action_name,
                available_actions=self._schema.get_action_names(),
            )

        if action.input_schema is None:
            return data

        try:
            validated = action.input_schema.model_validate(data)
            return validated.model_dump()
        except Exception as e:
            raise ValidationError.from_pydantic(
                validation_exception=e,
                connector_name=self._schema.name,
                action=action_name,
            ) from e

    def validate_output(self, action_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Valida datos de salida contra el esquema de una accion.

        Args:
            action_name: Nombre de la accion
            data: Datos de salida a validar

        Retorna:
            Datos validados y posiblemente transformados por Pydantic

        Raises:
            ActionNotFoundError: Si la accion no existe en el esquema
            ValidationError: Si los datos no cumplen el esquema
        """
        action = self._schema.get_action(action_name)
        if action is None:
            from src.sdk.exceptions import ActionNotFoundError

            raise ActionNotFoundError(
                message=f"Accion '{action_name}' no encontrada en conector '{self._schema.name}'",
                connector_name=self._schema.name,
                action=action_name,
                available_actions=self._schema.get_action_names(),
            )

        if action.output_schema is None:
            return data

        try:
            validated = action.output_schema.model_validate(data)
            return validated.model_dump()
        except Exception as e:
            raise ValidationError.from_pydantic(
                validation_exception=e,
                connector_name=self._schema.name,
                action=action_name,
            ) from e

    def validate_auth(self, auth_data: dict[str, Any]) -> bool:
        """
        Valida que los datos de autenticacion cumplan los requisitos del conector.

        Verifica que todos los campos requeridos por los metodos de
        autenticacion del conector esten presentes en los datos.

        Args:
            auth_data: Datos de autenticacion a validar

        Retorna:
            True si los datos de autenticacion son validos

        Raises:
            ValidationError: Si faltan campos requeridos
        """
        missing_fields: list[str] = []
        for req in self._schema.auth_requirements:
            for field_name in req.required_fields:
                if field_name not in auth_data or not auth_data[field_name]:
                    missing_fields.append(f"{req.auth_type}.{field_name}")

        if missing_fields:
            raise ValidationError(
                message=f"Campos de autenticacion faltantes: {', '.join(missing_fields)}",
                connector_name=self._schema.name,
                validation_errors=[
                    {"field": f, "message": "Campo requerido faltante", "type": "missing"} for f in missing_fields
                ],
            )
        return True

    def get_validation_report(self, action_name: str, data: dict[str, Any], direction: str = "input") -> dict[str, Any]:
        """
        Genera un reporte de validacion sin lanzar excepciones.

        Args:
            action_name: Nombre de la accion
            data: Datos a validar
            direction: Direccion de validacion ('input' o 'output')

        Retorna:
            Diccionario con: valid (bool), errors (list), warnings (list)
        """
        report: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

        action = self._schema.get_action(action_name)
        if action is None:
            report["valid"] = False
            report["errors"].append({"message": f"Accion '{action_name}' no encontrada"})
            return report

        schema_model = action.input_schema if direction == "input" else action.output_schema
        if schema_model is None:
            report["warnings"].append({"message": f"No hay esquema de {direction} definido para '{action_name}'"})
            return report

        try:
            schema_model.model_validate(data)
        except Exception as e:
            report["valid"] = False
            if hasattr(e, "errors"):
                for err in e.errors():
                    report["errors"].append(
                        {
                            "field": ".".join(str(loc) for loc in err.get("loc", [])),
                            "message": err.get("msg", ""),
                            "type": err.get("type", ""),
                        }
                    )
            else:
                report["errors"].append({"message": str(e)})

        return report


# ── Generador de OpenAPI ─────────────────────────────────────


class OpenAPIGenerator:
    """
    Genera especificaciones OpenAPI desde esquemas de conectores.

    Transforma la definicion de un conector (acciones, esquemas,
    autenticacion) en una especificacion OpenAPI 3.1 completa
    que puede ser usada para documentacion, generacion de SDKs
    o integracion con herramientas API.

    Attributes:
        schema: Esquema del conector a documentar
    """

    OPENAPI_VERSION = "3.1.0"

    def __init__(self, schema: ConnectorSchema) -> None:
        self._schema = schema

    def generate(self, base_url: str = "https://api.example.com") -> dict[str, Any]:
        """
        Genera la especificacion OpenAPI completa del conector.

        Args:
            base_url: URL base para los endpoints de la API

        Retorna:
            Diccionario con la especificacion OpenAPI 3.1 completa
        """
        spec: dict[str, Any] = {
            "openapi": self.OPENAPI_VERSION,
            "info": {
                "title": f"{self._schema.name} Connector",
                "version": self._schema.version,
                "description": self._schema.description,
                "contact": {"name": self._schema.author} if self._schema.author else {},
                "x-category": self._schema.category,
                "x-icon": self._schema.icon,
                "x-tags": self._schema.tags,
            },
            "servers": [{"url": base_url, "description": "API del conector"}],
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": self._generate_security_schemes(),
            },
            "tags": self._generate_tags(),
        }

        # Generar schemas de componentes desde las acciones
        for action in self._schema.actions:
            self._add_action_schemas(spec["components"]["schemas"], action)
            self._add_action_path(spec["paths"], action)

        # Agregar schemas globales si existen
        if self._schema.inputs:
            spec["components"]["schemas"][f"{self._schema.name}_inputs"] = self._schema.inputs.model_json_schema()
        if self._schema.outputs:
            spec["components"]["schemas"][f"{self._schema.name}_outputs"] = self._schema.outputs.model_json_schema()

        return spec

    def _generate_security_schemes(self) -> dict[str, Any]:
        """
        Genera los esquemas de seguridad OpenAPI desde los requisitos de auth.

        Retorna:
            Diccionario con los security schemes de OpenAPI
        """
        schemes: dict[str, Any] = {}
        for req in self._schema.auth_requirements:
            if req.auth_type == "api_key":
                schemes["api_key"] = {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": req.description,
                }
            elif req.auth_type == "basic":
                schemes["basic_auth"] = {
                    "type": "http",
                    "scheme": "basic",
                    "description": req.description,
                }
            elif req.auth_type == "oauth2":
                schemes["oauth2"] = {
                    "type": "oauth2",
                    "flows": {
                        "authorizationCode": {
                            "authorizationUrl": "https://example.com/oauth/authorize",
                            "tokenUrl": "https://example.com/oauth/token",
                            "scopes": {s: s for s in (req.required_fields + req.optional_fields) or ["default"]},
                        }
                    },
                    "description": req.description,
                }
            elif req.auth_type == "mtls":
                schemes["mtls"] = {
                    "type": "mutualTLS",
                    "description": req.description,
                }
            elif req.auth_type == "custom":
                schemes["custom"] = {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Custom-Auth",
                    "description": req.description,
                }
        return schemes

    def _generate_tags(self) -> list[dict[str, Any]]:
        """
        Genera los tags de OpenAPI desde las categorias de acciones.

        Retorna:
            Lista de tags unicos para la especificacion
        """
        categories: set[str] = set()
        for action in self._schema.actions:
            categories.add(action.category)

        return [{"name": cat, "description": f"Acciones de categoria {cat}"} for cat in sorted(categories)]

    def _add_action_schemas(self, schemas: dict[str, Any], action: ActionDefinition) -> None:
        """
        Agrega los esquemas Pydantic de una accion al componente schemas.

        Args:
            schemas: Diccionario de schemas existente (se modifica in-place)
            action: Accion cuyos esquemas se agregan
        """
        prefix = f"{self._schema.name}_{action.name}"
        if action.input_schema:
            schemas[f"{prefix}_input"] = action.get_input_schema_json()
        if action.output_schema:
            schemas[f"{prefix}_output"] = action.get_output_schema_json()

    def _add_action_path(self, paths: dict[str, Any], action: ActionDefinition) -> None:
        """
        Agrega el path de una accion a la especificacion OpenAPI.

        Args:
            paths: Diccionario de paths existente (se modifica in-place)
            action: Accion a agregar como path
        """
        prefix = f"{self._schema.name}_{action.name}"
        path = f"/actions/{action.name}"
        is_read = action.category in ("read", "general")

        operation: dict[str, Any] = {
            "operationId": action.name,
            "summary": action.description or action.name,
            "tags": [action.category],
            "deprecated": action.deprecated,
        }

        if action.deprecated and action.deprecation_message:
            operation["x-deprecation-message"] = action.deprecation_message

        # Request body para acciones de escritura
        if not is_read and action.input_schema:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{prefix}_input"},
                    }
                },
            }

        # Parameters para acciones de lectura
        if is_read and action.input_schema:
            input_json = action.get_input_schema_json()
            properties = input_json.get("properties", {})
            required = input_json.get("required", [])
            operation["parameters"] = [
                {
                    "name": prop_name,
                    "in": "query",
                    "required": prop_name in required,
                    "schema": prop_schema,
                    "description": prop_schema.get("description", ""),
                }
                for prop_name, prop_schema in properties.items()
            ]

        # Response schema
        response_schema = {"$ref": f"#/components/schemas/{prefix}_output"} if action.output_schema else {}
        operation["responses"] = {
            "200": {
                "description": "Respuesta exitosa",
                "content": {"application/json": {"schema": response_schema}} if response_schema else {},
            },
            "400": {"description": "Error de validacion"},
            "401": {"description": "Error de autenticacion"},
            "429": {"description": "Limite de frecuencia excedido"},
            "500": {"description": "Error interno del conector"},
        }

        method = "get" if is_read else "post"
        paths[path] = {method: operation}

    def to_json(self, base_url: str = "https://api.example.com", indent: int = 2) -> str:
        """
        Genera la especificacion OpenAPI como JSON formateado.

        Args:
            base_url: URL base para los endpoints
            indent: Indentacion del JSON

        Retorna:
            String JSON con la especificacion OpenAPI
        """
        return json.dumps(self.generate(base_url), indent=indent, default=str, ensure_ascii=False)


# ── Versionamiento de Esquemas ────────────────────────────────


class SchemaVersion:
    """
    Gestor de versiones de esquemas de conectores.

    Mantiene un historial de versiones de un esquema y permite
    verificar compatibilidad entre versiones, migrar datos
    entre versiones, y determinar la version mas reciente.

    Attributes:
        schema_name: Nombre del conector
        versions: Diccionario de version -> ConnectorSchema
    """

    def __init__(self, schema_name: str) -> None:
        self._schema_name = schema_name
        self._versions: dict[str, ConnectorSchema] = {}
        self._migration_paths: dict[tuple[str, str], Any] = {}

    @property
    def schema_name(self) -> str:
        """Retorna el nombre del conector."""
        return self._schema_name

    def add_version(self, schema: ConnectorSchema) -> None:
        """
        Agrega una nueva version del esquema.

        Verifica que la version no exista ya y que el nombre
        del esquema coincida con el del gestor.

        Args:
            schema: Esquema del conector para la nueva version

        Raises:
            SchemaError: Si la version ya existe o el nombre no coincide
        """
        if schema.name != self._schema_name:
            raise SchemaError(
                message=f"Nombre de esquema inconsistente: esperado '{self._schema_name}', obtenido '{schema.name}'",
                connector_name=self._schema_name,
                conflict_field="name",
            )
        if schema.version in self._versions:
            raise SchemaError(
                message=f"Version '{schema.version}' ya existe para '{self._schema_name}'",
                connector_name=self._schema_name,
                schema_version=schema.version,
            )
        self._versions[schema.version] = schema
        logger.info(f"SchemaVersion: version {schema.version} agregada para {self._schema_name}")

    def get_version(self, version: str) -> ConnectorSchema | None:
        """
        Obtiene una version especifica del esquema.

        Args:
            version: Version a obtener (semver)

        Retorna:
            Esquema de la version, o None si no existe
        """
        return self._versions.get(version)

    def get_latest(self) -> ConnectorSchema | None:
        """
        Obtiene la version mas reciente del esquema.

        Retorna:
            Esquema de la ultima version, o None si no hay versiones
        """
        if not self._versions:
            return None
        sorted_versions = sorted(self._versions.keys(), key=self._parse_version)
        return self._versions[sorted_versions[-1]]

    def list_versions(self) -> list[str]:
        """
        Lista todas las versiones disponibles ordenadas.

        Retorna:
            Lista de versiones en orden ascendente
        """
        return sorted(self._versions.keys(), key=self._parse_version)

    def is_compatible(self, from_version: str, to_version: str) -> bool:
        """
        Verifica si dos versiones son compatibles.

        Dos versiones son compatibles si el major version coincide
        (seguindo semver: versiones con el mismo major son compatibles
        hacia atras).

        Args:
            from_version: Version de origen
            to_version: Version de destino

        Retorna:
            True si las versiones son compatibles
        """
        from_major = self._parse_version(from_version)[0]
        to_major = self._parse_version(to_version)[0]
        return from_major == to_major

    def register_migration(
        self,
        from_version: str,
        to_version: str,
        migration_func: Any,
    ) -> None:
        """
        Registra una funcion de migracion entre dos versiones.

        Args:
            from_version: Version de origen
            to_version: Version de destino
            migration_func: Funcion que transforma datos de from_version a to_version
        """
        self._migration_paths[(from_version, to_version)] = migration_func
        logger.debug(f"SchemaVersion: migracion registrada {from_version} -> {to_version}")

    def migrate(self, data: dict[str, Any], from_version: str, to_version: str) -> dict[str, Any]:
        """
        Migra datos de una version a otra usando la funcion registrada.

        Args:
            data: Datos en el formato de la version de origen
            from_version: Version actual de los datos
            to_version: Version destino

        Retorna:
            Datos transformados al formato de la version destino

        Raises:
            SchemaError: Si no existe migracion registrada entre las versiones
        """
        migration_func = self._migration_paths.get((from_version, to_version))
        if migration_func is None:
            raise SchemaError(
                message=f"No existe migracion de {from_version} a {to_version}",
                connector_name=self._schema_name,
                schema_version=from_version,
            )
        result = migration_func(copy.deepcopy(data))
        logger.info(f"SchemaVersion: datos migrados de {from_version} a {to_version}")
        return result

    @staticmethod
    def _parse_version(version: str) -> tuple[int, int, int]:
        """
        Parsea una version semver a tupla (major, minor, patch).

        Args:
            version: Version en formato semver (ej: '1.2.3')

        Retorna:
            Tupla con los tres componentes de la version
        """
        try:
            parts = version.split(".")
            return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
        except (ValueError, IndexError):
            return (0, 0, 0)

    def to_dict(self) -> dict[str, Any]:
        """
        Serializa el gestor de versiones a diccionario.

        Retorna:
            Diccionario con la informacion de todas las versiones
        """
        return {
            "schema_name": self._schema_name,
            "versions": self.list_versions(),
            "latest": self.get_latest().version if self.get_latest() else None,
            "migration_paths": [f"{f} -> {t}" for f, t in self._migration_paths],
        }
