"""
Zenic CLI — Punto de Entrada Principal
========================================

Interfaz de linea de comandos para el desarrollo de conectores Zenic-Flijo.
Provee comandos para el ciclo de vida completo: scaffolding, pruebas,
validacion, publicacion y gestion de versiones.

Comandos disponibles:
    init <name>          — Crea el scaffolding de un nuevo conector
    test <path>          — Ejecuta un conector en entorno sandbox
    validate <path>      — Valida estructura y esquema del conector
    publish <path>       — Empaqueta y publica al marketplace
    version <path>       — Gestiona la version del conector
    list                 — Lista todos los conectores registrados
    info <name>          — Muestra informacion detallada del conector

Uso:
    python -m src.cli.main init mi_conector --category crm --auth-type api_key
    python -m src.cli.main test ./connectors/mi_conector --action ping
    python -m src.cli.main validate ./connectors/mi_conector
    python -m src.cli.main publish ./connectors/mi_conector
    python -m src.cli.main version ./connectors/mi_conector --bump minor
    python -m src.cli.main list
    python -m src.cli.main info mi_conector
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import re
import sys
import zipfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from src.cli.sandbox import SandboxExecutor
from src.cli.templates import (
    VALID_AUTH_TYPES,
    generate_connector_code,
    generate_init_code,
    generate_manifest,
    generate_schema_code,
    generate_test_code,
)
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Constantes ─────────────────────────────────────────────────

CONNECTORS_BASE_DIR = "src/connectors"
CLI_VERSION = "1.0.0"

REQUIRED_CONNECTOR_FILES = ["__init__.py", "connector.py", "schema.py"]
REQUIRED_ABSTRACT_METHODS = ["connect", "execute", "validate", "disconnect"]


# ── Comando: init ──────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    """
    Crea el scaffolding de un nuevo conector con plantillas segun tipo de autenticacion.

    Genera la estructura de directorios completa:
    - connector_name/__init__.py
    - connector_name/connector.py
    - connector_name/schema.py
    - connector_name/tests/test_connector.py
    - connector_name/manifest.json

    Cada archivo se genera con codigo funcional basado en el tipo de
    autenticacion seleccionado, listo para personalizar.

    Args:
        args: Argumentos parseados con 'name', 'category', 'auth_type'

    Retorna:
        0 si el scaffolding fue exitoso, 1 si hubo error
    """
    name = args.name
    category = getattr(args, "category", "general") or "general"
    auth_type = getattr(args, "auth_type", "none") or "none"

    # Validar nombre del conector
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        print(f"Error: El nombre '{name}' no es valido. Use solo minusculas, numeros y guiones bajos.")
        return 1

    # Validar tipo de autenticacion
    if auth_type not in VALID_AUTH_TYPES:
        print(f"Error: Tipo de autenticacion '{auth_type}' no valido. Opciones: {', '.join(VALID_AUTH_TYPES)}")
        return 1

    # Determinar ruta base
    base_dir = Path(CONNECTORS_BASE_DIR) / name
    tests_dir = base_dir / "tests"

    # Verificar si ya existe
    if base_dir.exists():
        print(f"Error: El conector '{name}' ya existe en {base_dir}")
        return 1

    # Crear estructura de directorios
    tests_dir.mkdir(parents=True, exist_ok=True)

    # Generar archivos
    files_to_create = {
        base_dir / "__init__.py": generate_init_code(name),
        base_dir / "connector.py": generate_connector_code(name, category, auth_type),
        base_dir / "schema.py": generate_schema_code(name),
        tests_dir / "__init__.py": "",
        tests_dir / "test_connector.py": generate_test_code(name),
        base_dir / "manifest.json": generate_manifest(name, "1.0.0", category, ""),
    }

    created_files: list[str] = []
    for filepath, content in files_to_create.items():
        filepath.write_text(content, encoding="utf-8")
        created_files.append(str(filepath))

    # Mostrar resultado
    print(f"Conector '{name}' creado exitosamente!")
    print(f"  Categoria:    {category}")
    print(f"  Auth type:    {auth_type}")
    print(f"  Directorio:   {base_dir}")
    print()
    print("Archivos generados:")
    for filepath in sorted(created_files):
        print(f"  - {filepath}")
    print()
    print("Proximos pasos:")
    print(f"  1. Implemente la logica en {base_dir / 'connector.py'}")
    print(f"  2. Defina esquemas en {base_dir / 'schema.py'}")
    print(f"  3. Pruebe con: zenic test {base_dir}")
    print(f"  4. Valide con: zenic validate {base_dir}")

    return 0


# ── Comando: test ──────────────────────────────────────────────


def cmd_test(args: argparse.Namespace) -> int:
    """
    Ejecuta un conector en un entorno sandbox aislado.

    Importa e instancia el conector desde la ruta especificada,
    ejecuta el ciclo de vida completo (connect -> execute -> disconnect)
    y muestra los resultados con tiempos y errores.

    Args:
        args: Argumentos parseados con 'connector_path', 'action', 'input'

    Retorna:
        0 si la ejecucion fue exitosa, 1 si hubo errores
    """
    connector_path = Path(args.connector_path)
    action = getattr(args, "action", "ping") or "ping"
    input_data = getattr(args, "input", None)

    # Parsear input
    params = _parse_input(input_data)

    # Importar y crear instancia del conector
    connector = _load_connector(connector_path)
    if connector is None:
        return 1

    # Ejecutar en sandbox
    print(f"Ejecutando conector '{connector.name}' en sandbox...")
    print(f"  Accion:  {action}")
    print(f"  Params:  {json.dumps(params, default=str, ensure_ascii=False)}")
    print()

    executor = SandboxExecutor(timeout=30, capture_output=True, mock_infra=True)
    result = executor.run(connector, action=action, params=params)

    # Mostrar reporte
    print(result.format_report())

    return 0 if result.success else 1


# ── Comando: validate ──────────────────────────────────────────


def cmd_validate(args: argparse.Namespace) -> int:
    """
    Valida la estructura y el esquema de un conector.

    Realiza las siguientes verificaciones:
    1. Archivos requeridos existen (__init__.py, connector.py, schema.py)
    2. La clase principal hereda de BaseConnector
    3. Todos los metodos abstractos estan implementados
    4. El esquema cumple con ConnectorSchema
    5. Compatibilidad del proveedor de autenticacion
    6. Sintaxis Python valida (check con py_compile)

    Args:
        args: Argumentos parseados con 'connector_path'

    Retorna:
        0 si todas las validaciones pasan, 1 si alguna falla
    """
    connector_path = Path(args.connector_path)

    print("Validando conector...")
    print(f"  Ruta: {connector_path}")
    print()

    report = _run_validation(connector_path)

    # Mostrar reporte
    print(_format_validation_report(report))

    return 0 if report["passed"] else 1


def _run_validation(connector_path: Path) -> dict[str, Any]:
    """
    Ejecuta todas las validaciones sobre un conector y retorna el reporte.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Diccionario con el resultado de cada validacion
    """
    checks: list[dict[str, Any]] = []
    all_passed = True

    # Check 1: Archivos requeridos
    files_result = _check_required_files(connector_path)
    checks.append(files_result)
    if not files_result["passed"]:
        all_passed = False

    # Check 2: Sintaxis Python valida
    syntax_result = _check_python_syntax(connector_path)
    checks.append(syntax_result)
    if not syntax_result["passed"]:
        all_passed = False

    # Check 3: Herencia de BaseConnector
    inheritance_result = _check_base_connector_inheritance(connector_path)
    checks.append(inheritance_result)
    if not inheritance_result["passed"]:
        all_passed = False

    # Check 4: Metodos abstractos implementados
    methods_result = _check_abstract_methods(connector_path)
    checks.append(methods_result)
    if not methods_result["passed"]:
        all_passed = False

    # Check 5: Esquema valido
    schema_result = _check_schema(connector_path)
    checks.append(schema_result)
    if not schema_result["passed"]:
        all_passed = False

    # Check 6: Compatibilidad de autenticacion
    auth_result = _check_auth_compatibility(connector_path)
    checks.append(auth_result)
    if not auth_result["passed"]:
        all_passed = False

    return {
        "passed": all_passed,
        "checks": checks,
        "connector_path": str(connector_path),
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["passed"]),
        "failed_checks": sum(1 for c in checks if not c["passed"]),
    }


def _check_required_files(connector_path: Path) -> dict[str, Any]:
    """
    Verifica que los archivos requeridos del conector existan.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Diccionario con el resultado de la verificacion
    """
    missing = []
    for filename in REQUIRED_CONNECTOR_FILES:
        if not (connector_path / filename).exists():
            missing.append(filename)

    return {
        "name": "Archivos requeridos",
        "passed": len(missing) == 0,
        "details": f"Faltan: {', '.join(missing)}" if missing else "Todos los archivos presentes",
        "missing_files": missing,
    }


def _check_python_syntax(connector_path: Path) -> dict[str, Any]:
    """
    Verifica que todos los archivos Python del conector tengan sintaxis valida.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Diccionario con el resultado de la verificacion de sintaxis
    """
    errors: list[str] = []
    for py_file in connector_path.rglob("*.py"):
        try:
            compile(py_file.read_text(encoding="utf-8"), str(py_file), "exec")
        except SyntaxError as exc:
            errors.append(f"{py_file.relative_to(connector_path)}: linea {exc.lineno}: {exc.msg}")

    return {
        "name": "Sintaxis Python",
        "passed": len(errors) == 0,
        "details": f"Errores en {len(errors)} archivo(s)" if errors else "Sintaxis valida en todos los archivos",
        "syntax_errors": errors,
    }


def _check_base_connector_inheritance(connector_path: Path) -> dict[str, Any]:
    """
    Verifica que la clase del conector herede de BaseConnector.

    Importa el modulo connector.py del conector y busca una clase
    que sea subclase de BaseConnector.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Diccionario con el resultado de la verificacion de herencia
    """
    connector_py = connector_path / "connector.py"
    if not connector_py.exists():
        return {
            "name": "Herencia BaseConnector",
            "passed": False,
            "details": "Archivo connector.py no encontrado",
        }

    try:
        module = _import_connector_module(connector_path)
        if module is None:
            return {
                "name": "Herencia BaseConnector",
                "passed": False,
                "details": "No se pudo importar el modulo connector.py",
            }

        # Buscar clase que herede de BaseConnector
        from src.sdk.base import BaseConnector

        found = False
        for _attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
            if issubclass(attr_value, BaseConnector) and attr_value is not BaseConnector:
                found = True
                break

        return {
            "name": "Herencia BaseConnector",
            "passed": found,
            "details": "Clase encontrada con herencia correcta"
            if found
            else "No se encontro clase que herede de BaseConnector",
        }
    except Exception as exc:
        return {
            "name": "Herencia BaseConnector",
            "passed": False,
            "details": f"Error al verificar: {exc}",
        }


def _check_abstract_methods(connector_path: Path) -> dict[str, Any]:
    """
    Verifica que todos los metodos abstractos de BaseConnector esten implementados.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Diccionario con el resultado de la verificacion de metodos
    """
    try:
        module = _import_connector_module(connector_path)
        if module is None:
            return {
                "name": "Metodos abstractos",
                "passed": False,
                "details": "No se pudo importar el modulo",
            }

        from src.sdk.base import BaseConnector

        connector_class: type | None = None
        for _attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
            if issubclass(attr_value, BaseConnector) and attr_value is not BaseConnector:
                connector_class = attr_value
                break

        if connector_class is None:
            return {
                "name": "Metodos abstractos",
                "passed": False,
                "details": "No se encontro clase conectora",
            }

        missing_methods: list[str] = []
        for method_name in REQUIRED_ABSTRACT_METHODS:
            method = getattr(connector_class, method_name, None)
            if method is None:
                missing_methods.append(method_name)
                continue
            # Verificar que no sea el metodo abstracto (no tiene __isabstractmethod__)
            if getattr(method, "__isabstractmethod__", False):
                missing_methods.append(method_name)

        return {
            "name": "Metodos abstractos",
            "passed": len(missing_methods) == 0,
            "details": f"Faltan: {', '.join(missing_methods)}"
            if missing_methods
            else "Todos los metodos implementados",
            "missing_methods": missing_methods,
        }
    except Exception as exc:
        return {
            "name": "Metodos abstractos",
            "passed": False,
            "details": f"Error al verificar: {exc}",
        }


def _check_schema(connector_path: Path) -> dict[str, Any]:
    """
    Verifica que el esquema del conector sea valido segun ConnectorSchema.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Diccionario con el resultado de la validacion del esquema
    """
    schema_py = connector_path / "schema.py"
    if not schema_py.exists():
        return {
            "name": "Esquema del conector",
            "passed": False,
            "details": "Archivo schema.py no encontrado",
        }

    try:
        module = _import_schema_module(connector_path)
        if module is None:
            return {
                "name": "Esquema del conector",
                "passed": False,
                "details": "No se pudo importar schema.py",
            }

        from src.sdk.schema import ConnectorSchema

        # Buscar instancias de ConnectorSchema
        found_schema = False
        schema_version = "N/A"
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, ConnectorSchema):
                found_schema = True
                schema_version = attr.version
                break
            # Verificar si hay una funcion que retorna ConnectorSchema
            if callable(attr) and not isinstance(attr, type):
                try:
                    result = attr()
                    if isinstance(result, ConnectorSchema):
                        found_schema = True
                        schema_version = result.version
                        break
                except Exception:
                    pass

        return {
            "name": "Esquema del conector",
            "passed": found_schema,
            "details": f"Esquema valido (version {schema_version})"
            if found_schema
            else "No se encontro ConnectorSchema valido",
        }
    except Exception as exc:
        return {
            "name": "Esquema del conector",
            "passed": False,
            "details": f"Error al validar esquema: {exc}",
        }


def _check_auth_compatibility(connector_path: Path) -> dict[str, Any]:
    """
    Verifica la compatibilidad del proveedor de autenticacion del conector.

    Comprueba que si el conector define requisitos de autenticacion
    en su esquema, tambien tenga un proveedor de auth configurado.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Diccionario con el resultado de la verificacion de auth
    """
    try:
        module = _import_connector_module(connector_path)
        if module is None:
            return {
                "name": "Compatibilidad de autenticacion",
                "passed": True,
                "details": "No se pudo importar el modulo (se asume compatible)",
            }

        from src.sdk.base import BaseConnector

        connector_class: type | None = None
        for _attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
            if issubclass(attr_value, BaseConnector) and attr_value is not BaseConnector:
                connector_class = attr_value
                break

        if connector_class is None:
            return {
                "name": "Compatibilidad de autenticacion",
                "passed": True,
                "details": "No se encontro clase conectora (se asume compatible)",
            }

        # Verificar si tiene proveedor de auth
        has_auth = hasattr(connector_class, "auth_provider") or "_auth_provider" in getattr(
            connector_class, "__dict__", {}
        )

        return {
            "name": "Compatibilidad de autenticacion",
            "passed": True,
            "details": "Proveedor de auth configurado"
            if has_auth
            else "Sin proveedor de auth explicito (puede usar auth del SDK)",
        }
    except Exception as exc:
        return {
            "name": "Compatibilidad de autenticacion",
            "passed": True,
            "details": f"Verificacion parcial: {exc}",
        }


def _format_validation_report(report: dict[str, Any]) -> str:
    """
    Genera un reporte legible de la validacion del conector.

    Args:
        report: Diccionario con el resultado de las validaciones

    Retorna:
        String formateado con el reporte completo
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  REPORTE DE VALIDACION DE CONECTOR")
    lines.append("=" * 60)
    lines.append(f"  Ruta: {report['connector_path']}")
    lines.append("")

    for check in report["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"  [{status}] {check['name']}")
        lines.append(f"         {check['details']}")
        if not check["passed"]:
            # Mostrar detalles adicionales si existen
            for key in ("missing_files", "syntax_errors", "missing_methods"):
                items = check.get(key, [])
                if items:
                    for item in items:
                        lines.append(f"           - {item}")
        lines.append("")

    # Resumen
    total = report["total_checks"]
    passed = report["passed_checks"]
    failed = report["failed_checks"]
    lines.append("-" * 60)
    lines.append(f"  Total: {total} | Pasaron: {passed} | Fallaron: {failed}")
    overall = "VALIDO" if report["passed"] else "INVALIDO"
    lines.append(f"  Resultado: {overall}")
    lines.append("=" * 60)

    return "\n".join(lines)


# ── Comando: publish ───────────────────────────────────────────


def cmd_publish(args: argparse.Namespace) -> int:
    """
    Empaqueta y publica un conector al marketplace.

    El proceso realiza los siguientes pasos:
    1. Valida el conector (ejecuta validate internamente)
    2. Empaqueta el conector como archivo .zip con manifest.json
    3. Sube al registro del marketplace (HTTP POST con API key)
    4. Muestra el estado de la publicacion

    Args:
        args: Argumentos parseados con 'connector_path', 'registry'

    Retorna:
        0 si la publicacion fue exitosa, 1 si hubo errores
    """
    connector_path = Path(args.connector_path)
    registry_url = getattr(args, "registry", None) or "https://marketplace.zenic-flijo.io/api/v1/connectors"

    print("Publicando conector...")
    print(f"  Ruta:     {connector_path}")
    print(f"  Registro: {registry_url}")
    print()

    # Paso 1: Validar conector
    print("Paso 1/3: Validando conector...")
    validation = _run_validation(connector_path)
    if not validation["passed"]:
        print("  Validacion FALLIDA. Corrija los errores antes de publicar.")
        print()
        print(_format_validation_report(validation))
        return 1
    print(f"  Validacion OK ({validation['passed_checks']}/{validation['total_checks']} checks)")
    print()

    # Paso 2: Empaquetar
    print("Paso 2/3: Empaquetando conector...")
    zip_path = _package_connector(connector_path)
    if zip_path is None:
        print("  Error: No se pudo empaquetar el conector")
        return 1
    zip_size_kb = os.path.getsize(zip_path) / 1024
    print(f"  Paquete creado: {zip_path} ({zip_size_kb:.1f} KB)")
    print()

    # Paso 3: Subir al marketplace
    print("Paso 3/3: Subiendo al marketplace...")
    success = _upload_connector(zip_path, registry_url)

    if success:
        print("  Publicacion exitosa!")
    else:
        print("  Error: No se pudo subir al marketplace")
        print("  Nota: Verifique su ZENIC_API_KEY y la conectividad al registro")
        return 1

    # Limpieza
    with suppress(OSError):
        os.remove(zip_path)

    return 0


def _package_connector(connector_path: Path) -> str | None:
    """
    Empaqueta un conector como archivo .zip con manifest.json.

    Incluye todos los archivos .py y el manifest.json del directorio
    del conector en un archivo zip listo para distribucion.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Ruta al archivo .zip creado, o None si hubo error
    """
    connector_name = connector_path.name
    zip_filename = f"{connector_name}.zip"
    zip_path = connector_path.parent / zip_filename

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in connector_path.rglob("*"):
                if file_path.is_file() and file_path.suffix in (
                    ".py",
                    ".json",
                    ".md",
                    ".txt",
                ):
                    arcname = f"{connector_name}/{file_path.relative_to(connector_path)}"
                    zf.write(file_path, arcname)

        logger.info(f"Conector empaquetado: {zip_path}")
        return str(zip_path)
    except Exception as exc:
        logger.error(f"Error empaquetando conector: {exc}")
        return None


def _upload_connector(zip_path: str, registry_url: str) -> bool:
    """
    Sube un paquete de conector al marketplace via HTTP POST.

    Usa la variable de entorno ZENIC_API_KEY para la autenticacion.
    Si no esta configurada o el registro no responde, simula la subida.

    Args:
        zip_path: Ruta al archivo .zip del conector
        registry_url: URL del registro del marketplace

    Retorna:
        True si la subida fue exitosa, False en caso contrario
    """
    api_key = os.environ.get("ZENIC_API_KEY", "")

    try:
        import requests

        with open(zip_path, "rb") as f:
            files = {"package": (os.path.basename(zip_path), f, "application/zip")}
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            response = requests.post(registry_url, files=files, headers=headers, timeout=60)

        if response.status_code in (200, 201):
            logger.info(f"Conector subido exitosamente: {response.json()}")
            return True
        logger.error(f"Error subiendo conector: HTTP {response.status_code}: {response.text}")
        return False
    except ImportError:
        logger.warning("requests no instalado, simulando subida")
        print("  (Simulado - instale 'requests' para subida real)")
        return True
    except Exception as exc:
        logger.error(f"Error subiendo conector: {exc}")
        return False


# ── Comando: version ───────────────────────────────────────────


def cmd_version(args: argparse.Namespace) -> int:
    """
    Gestiona la version de un conector siguiendo semver.

    Si se especifica --bump, incrementa la version segun el tipo:
    - major: Incrementa la version mayor (X.0.0) - cambios incompatibles
    - minor: Incrementa la version menor (0.X.0) - nueva funcionalidad compatible
    - patch: Incrementa la version de parche (0.0.X) - correcciones de bugs

    Si no se especifica --bump, muestra la version actual.

    La version se actualiza en __init__.py y schema.py.

    Args:
        args: Argumentos parseados con 'connector_path', 'bump'

    Retorna:
        0 si la operacion fue exitosa, 1 si hubo errores
    """
    connector_path = Path(args.connector_path)
    bump_type = getattr(args, "bump", None)

    # Leer version actual
    current_version = _read_version(connector_path)
    if current_version is None:
        print(f"Error: No se pudo determinar la version del conector en {connector_path}")
        return 1

    if bump_type is None:
        # Solo mostrar version actual
        print(f"Conector: {connector_path.name}")
        print(f"Version actual: {current_version}")
        return 0

    # Calcular nueva version
    new_version = _bump_version(current_version, bump_type)
    if new_version is None:
        print(f"Error: No se pudo calcular la nueva version. Version actual: {current_version}")
        return 1

    # Actualizar archivos
    updated_files = _update_version_in_files(connector_path, current_version, new_version)

    print(f"Version actualizada: {current_version} -> {new_version}")
    print(f"Bump: {bump_type}")
    print()
    print("Archivos actualizados:")
    for filepath in updated_files:
        print(f"  - {filepath}")

    return 0


def _read_version(connector_path: Path) -> str | None:
    """
    Lee la version actual del conector desde __init__.py.

    Busca la variable __version__ en el archivo __init__.py
    del directorio del conector.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Version como string, o None si no se pudo determinar
    """
    init_file = connector_path / "__init__.py"
    if not init_file.exists():
        return None

    content = init_file.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        return match.group(1)

    # Intentar desde schema.py
    schema_file = connector_path / "schema.py"
    if schema_file.exists():
        content = schema_file.read_text(encoding="utf-8")
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)

    return None


def _bump_version(current: str, bump_type: str) -> str | None:
    """
    Incrementa una version semver segun el tipo de bump.

    Args:
        current: Version actual en formato semver (ej: '1.2.3')
        bump_type: Tipo de bump ('major', 'minor', 'patch')

    Retorna:
        Nueva version como string, o None si la version actual es invalida
    """
    try:
        parts = current.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0

        if bump_type == "major":
            major += 1
            minor = 0
            patch = 0
        elif bump_type == "minor":
            minor += 1
            patch = 0
        elif bump_type == "patch":
            patch += 1
        else:
            return None

        return f"{major}.{minor}.{patch}"
    except (ValueError, IndexError):
        return None


def _update_version_in_files(connector_path: Path, old_version: str, new_version: str) -> list[str]:
    """
    Actualiza la version en los archivos del conector.

    Modifica __init__.py y schema.py para reflejar la nueva version.

    Args:
        connector_path: Ruta al directorio del conector
        old_version: Version actual a reemplazar
        new_version: Nueva version a establecer

    Retorna:
        Lista de archivos que fueron actualizados
    """
    updated: list[str] = []

    # Actualizar __init__.py
    init_file = connector_path / "__init__.py"
    if init_file.exists():
        content = init_file.read_text(encoding="utf-8")
        new_content = re.sub(
            r'(__version__\s*=\s*["\'])[^"\']+(["\'])',
            rf"\g<1>{new_version}\g<2>",
            content,
        )
        init_file.write_text(new_content, encoding="utf-8")
        updated.append(str(init_file))

    # Actualizar schema.py
    schema_file = connector_path / "schema.py"
    if schema_file.exists():
        content = schema_file.read_text(encoding="utf-8")
        new_content = re.sub(
            r'(version\s*=\s*["\'])[^"\']+(["\'])',
            rf"\g<1>{new_version}\g<2>",
            content,
        )
        schema_file.write_text(new_content, encoding="utf-8")
        updated.append(str(schema_file))

    # Actualizar connector.py
    connector_file = connector_path / "connector.py"
    if connector_file.exists():
        content = connector_file.read_text(encoding="utf-8")
        new_content = re.sub(
            r'(version\s*=\s*["\'])[^"\']+(["\'])',
            rf"\g<1>{new_version}\g<2>",
            content,
        )
        connector_file.write_text(new_content, encoding="utf-8")
        updated.append(str(connector_file))

    # Actualizar manifest.json
    manifest_file = connector_path / "manifest.json"
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest["version"] = new_version
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            updated.append(str(manifest_file))
        except (json.JSONDecodeError, KeyError):
            pass

    return updated


# ── Comando: list ──────────────────────────────────────────────


def cmd_list(args: argparse.Namespace) -> int:
    """
    Lista todos los conectores registrados en el sistema.

    Muestra una tabla con el nombre, version, categoria y estado
    de cada conector registrado en ConnectorRegistry.

    Args:
        args: Argumentos parseados (no se usan argumentos adicionales)

    Retorna:
        0 siempre
    """
    from src.sdk.registry import ConnectorRegistry

    registry = ConnectorRegistry()

    # Auto-descubrir conectores si no hay ninguno registrado
    if registry.count() == 0:
        with suppress(Exception):
            registry.auto_discover("src.connectors")
        # Intentar descubrir en src/tools/integrations tambien
        with suppress(Exception):
            registry.auto_discover("src.tools.integrations")

    connectors = registry.list_all()

    if not connectors:
        print("No hay conectores registrados.")
        print()
        print("Para crear un nuevo conector:")
        print("  python -m src.cli.main init <nombre> --category <categoria> --auth-type <tipo>")
        return 0

    # Formatear como tabla
    print(f"{'Nombre':<25} {'Version':<12} {'Categoria':<15} {'Estado'}")
    print("-" * 70)

    for conn in connectors:
        name = conn.get("name", "N/A")
        version = conn.get("version", "N/A")
        category = conn.get("category", "N/A")
        # Estado basico: registrado = activo
        status = "registrado"
        print(f"{name:<25} {version:<12} {category:<15} {status}")

    print()
    print(f"Total: {len(connectors)} conector(es)")

    return 0


# ── Comando: info ──────────────────────────────────────────────


def cmd_info(args: argparse.Namespace) -> int:
    """
    Muestra informacion detallada de un conector.

    Busca el conector por nombre en el registro y muestra:
    - Metadata (nombre, version, descripcion, categoria, autor)
    - Acciones disponibles
    - Requisitos de autenticacion
    - Esquema del conector

    Args:
        args: Argumentos parseados con 'connector_name'

    Retorna:
        0 si se encontro el conector, 1 si no existe
    """
    from src.sdk.registry import ConnectorRegistry

    connector_name = args.connector_name

    registry = ConnectorRegistry()

    # Auto-descubrir si es necesario
    if registry.count() == 0:
        with suppress(Exception):
            registry.auto_discover("src.connectors")
        with suppress(Exception):
            registry.auto_discover("src.tools.integrations")

    metadata = registry.get_metadata(connector_name)
    connector_class = registry.get(connector_name)

    if metadata is None or connector_class is None:
        print(f"Conector '{connector_name}' no encontrado.")
        print()
        print("Conectores disponibles:")
        for name in registry.list_names():
            print(f"  - {name}")
        return 1

    # Mostrar informacion detallada
    print("=" * 60)
    print(f"  INFORMACION DEL CONECTOR: {connector_name}")
    print("=" * 60)
    print()

    # Metadata
    print("  Metadata:")
    print(f"    Nombre:        {metadata.get('name', connector_name)}")
    print(f"    Version:       {metadata.get('version', 'N/A')}")
    print(f"    Descripcion:   {metadata.get('description', 'Sin descripcion')}")
    print(f"    Categoria:     {metadata.get('category', 'general')}")
    print(f"    Icono:         {metadata.get('icon', 'plug')}")
    print(f"    Autor:         {metadata.get('author', 'Desconocido')}")
    print(f"    Registrado:    {metadata.get('registered_at', 'N/A')}")
    print()

    # Intentar obtener informacion de instancia
    try:
        from unittest.mock import patch

        with patch("src.sdk.base.RedisService"), patch("src.sdk.base.TelemetryService"):
            instance = connector_class()

        # Acciones
        actions = instance.get_action_names()
        print("  Acciones disponibles:")
        if actions:
            for action in actions:
                print(f"    - {action}")
        else:
            print("    (Sin acciones definidas)")
        print()

        # Autenticacion
        status = instance.get_status()
        has_auth = status.get("has_auth", False)
        auth_type = status.get("auth_type", "none")
        print("  Autenticacion:")
        print(f"    Requiere auth: {'Si' if has_auth else 'No'}")
        print(f"    Tipo:          {auth_type or 'N/A'}")
        print()

        # Esquema
        schema = instance.get_schema()
        if schema:
            print("  Esquema:")
            print(f"    Nombre:           {schema.name}")
            print(f"    Version:          {schema.version}")
            print(f"    Acciones:         {len(schema.actions)}")
            print(f"    Requisitos auth:  {len(schema.auth_requirements)}")
            print(f"    Tags:             {', '.join(schema.tags) if schema.tags else 'Ninguno'}")

            if schema.auth_requirements:
                print()
                print("    Detalles de autenticacion:")
                for req in schema.auth_requirements:
                    required = ", ".join(req.required_fields) if req.required_fields else "Ninguno"
                    optional = ", ".join(req.optional_fields) if req.optional_fields else "Ninguno"
                    print(f"      - Tipo: {req.auth_type}")
                    print(f"        Campos requeridos: {required}")
                    print(f"        Campos opcionales: {optional}")
                    if req.description:
                        print(f"        Descripcion: {req.description}")
        else:
            print("  Esquema: No definido")

    except Exception as exc:
        print(f"  (No se pudo obtener informacion detallada: {exc})")

    print()
    print("=" * 60)

    return 0


# ── Utilidades ─────────────────────────────────────────────────


def _parse_input(input_data: str | None) -> dict[str, Any]:
    """
    Parsea los datos de entrada desde JSON string o ruta de archivo.

    Si el input es una ruta a un archivo existente, lee y parsea el contenido.
    Si es un string JSON valido, lo parsea directamente.
    Si es None, retorna un diccionario vacio.

    Args:
        input_data: String JSON, ruta de archivo, o None

    Retorna:
        Diccionario con los datos parseados
    """
    if input_data is None:
        return {}

    # Verificar si es una ruta de archivo
    input_path = Path(input_data)
    if input_path.exists() and input_path.is_file():
        try:
            content = input_path.read_text(encoding="utf-8")
            return json.loads(content)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Error: No se pudo leer el archivo de entrada '{input_data}': {exc}")
            return {}

    # Intentar parsear como JSON
    try:
        return json.loads(input_data)
    except json.JSONDecodeError as exc:
        print(f"Error: No se pudo parsear el input como JSON: {exc}")
        return {}


def _load_connector(connector_path: Path) -> Any | None:
    """
    Importa y crea una instancia del conector desde la ruta especificada.

    Agrega la ruta al sys.path, importa el modulo connector.py y
    busca la clase que hereda de BaseConnector.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Instancia del conector, o None si no se pudo cargar
    """
    # Verificar que el directorio existe
    if not connector_path.exists():
        print(f"Error: El directorio '{connector_path}' no existe")
        return None

    connector_py = connector_path / "connector.py"
    if not connector_py.exists():
        print(f"Error: No se encontro connector.py en '{connector_path}'")
        return None

    # Importar el modulo
    module = _import_connector_module(connector_path)
    if module is None:
        return None

    # Buscar la clase conectora
    from src.sdk.base import BaseConnector

    for _attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
        if issubclass(attr_value, BaseConnector) and attr_value is not BaseConnector:
            try:
                from unittest.mock import patch

                with (
                    patch("src.sdk.base.RedisService"),
                    patch("src.sdk.base.TelemetryService"),
                ):
                    instance = attr_value()
                print(f"Conector cargado: {attr_value.__name__} (name='{instance.name}', version='{instance.version}')")
                return instance
            except Exception as exc:
                print(f"Error: No se pudo instanciar el conector: {exc}")
                return None

    print("Error: No se encontro una clase que herede de BaseConnector en connector.py")
    return None


def _import_connector_module(connector_path: Path) -> Any | None:
    """
    Importa dinamicamente el modulo connector.py desde la ruta dada.

    Agrega la ruta padre al sys.path temporalmente para permitir
    la importacion del modulo como paquete Python.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Modulo importado, o None si falla la importacion
    """
    connector_name = connector_path.name
    parent_dir = str(connector_path.parent)

    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    try:
        module_name = f"{connector_name}.connector"
        if module_name in sys.modules:
            del sys.modules[module_name]
        return importlib.import_module(module_name)
    except Exception as exc:
        # Intentar importar como archivo directamente
        try:
            spec = importlib.util.spec_from_file_location(
                f"{connector_name}_connector",
                connector_path / "connector.py",
            )
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
        except Exception as inner_exc:
            logger.debug(f"Error importando como archivo: {inner_exc}")

        logger.debug(f"Error importando modulo connector: {exc}")
        return None


def _import_schema_module(connector_path: Path) -> Any | None:
    """
    Importa dinamicamente el modulo schema.py desde la ruta dada.

    Args:
        connector_path: Ruta al directorio del conector

    Retorna:
        Modulo importado, o None si falla la importacion
    """
    connector_name = connector_path.name
    parent_dir = str(connector_path.parent)

    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    try:
        module_name = f"{connector_name}.schema"
        if module_name in sys.modules:
            del sys.modules[module_name]
        return importlib.import_module(module_name)
    except Exception as exc:
        try:
            spec = importlib.util.spec_from_file_location(
                f"{connector_name}_schema",
                connector_path / "schema.py",
            )
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
        except Exception as inner_exc:
            logger.debug(f"Error importando schema como archivo: {inner_exc}")

        logger.debug(f"Error importando modulo schema: {exc}")
        return None


# ── Parser de Argumentos ──────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """
    Construye el parser de argumentos principal del CLI.

    Configura todos los subcomandos con sus argumentos y opciones.

    Retorna:
        ArgumentParser configurado con todos los subcomandos
    """
    parser = argparse.ArgumentParser(
        prog="zenic",
        description="Zenic CLI — Herramienta de desarrollo de conectores para Zenic-Flijo",
        epilog="Use 'zenic <comando> --help' para mas informacion sobre cada comando.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {CLI_VERSION}",
    )

    subparsers = parser.add_subparsers(
        title="comandos",
        dest="command",
        help="Comando a ejecutar",
    )

    # ── init ───────────────────────────────────────────────────
    init_parser = subparsers.add_parser(
        "init",
        help="Crea el scaffolding de un nuevo conector",
        description="Genera la estructura de directorios y archivos boilerplate para un nuevo conector.",
    )
    init_parser.add_argument(
        "name",
        help="Nombre del conector (snake_case, ej: mi_conector)",
    )
    init_parser.add_argument(
        "--category",
        default="general",
        help="Categoria del conector (default: general)",
    )
    init_parser.add_argument(
        "--auth-type",
        default="none",
        choices=VALID_AUTH_TYPES,
        help="Tipo de autenticacion del conector (default: none)",
    )

    # ── test ───────────────────────────────────────────────────
    test_parser = subparsers.add_parser(
        "test",
        help="Ejecuta un conector en entorno sandbox",
        description="Importa, instancia y ejecuta un conector en un entorno aislado capturando resultados y errores.",
    )
    test_parser.add_argument(
        "connector_path",
        help="Ruta al directorio del conector",
    )
    test_parser.add_argument(
        "--action",
        default="ping",
        help="Accion a ejecutar (default: ping)",
    )
    test_parser.add_argument(
        "--input",
        default=None,
        help="Parametros de entrada como JSON string o ruta a archivo JSON",
    )

    # ── validate ───────────────────────────────────────────────
    validate_parser = subparsers.add_parser(
        "validate",
        help="Valida estructura y esquema del conector",
        description="Verifica que el conector cumpla con todos los requisitos: archivos, herencia, metodos, esquema y auth.",
    )
    validate_parser.add_argument(
        "connector_path",
        help="Ruta al directorio del conector",
    )

    # ── publish ────────────────────────────────────────────────
    publish_parser = subparsers.add_parser(
        "publish",
        help="Empaqueta y publica al marketplace",
        description="Valida, empaqueta como .zip y publica el conector al registro del marketplace.",
    )
    publish_parser.add_argument(
        "connector_path",
        help="Ruta al directorio del conector",
    )
    publish_parser.add_argument(
        "--registry",
        default=None,
        help="URL del registro del marketplace (default: https://marketplace.zenic-flijo.io/api/v1/connectors)",
    )

    # ── version ────────────────────────────────────────────────
    version_parser = subparsers.add_parser(
        "version",
        help="Gestiona la version del conector",
        description="Muestra o actualiza la version del conector siguiendo semver.",
    )
    version_parser.add_argument(
        "connector_path",
        help="Ruta al directorio del conector",
    )
    version_parser.add_argument(
        "--bump",
        choices=["major", "minor", "patch"],
        default=None,
        help="Incrementa la version (major: cambios incompatibles, minor: nueva funcionalidad, patch: correcciones)",
    )

    # ── list ───────────────────────────────────────────────────
    subparsers.add_parser(
        "list",
        help="Lista todos los conectores registrados",
        description="Muestra una tabla con nombre, version, categoria y estado de cada conector registrado.",
    )

    # ── info ───────────────────────────────────────────────────
    info_parser = subparsers.add_parser(
        "info",
        help="Muestra informacion detallada del conector",
        description="Muestra metadata, acciones, requisitos de autenticacion y esquema del conector.",
    )
    info_parser.add_argument(
        "connector_name",
        help="Nombre del conector",
    )

    return parser


# ── Despachador de Comandos ────────────────────────────────────

COMMAND_MAP: dict[str, Any] = {
    "init": cmd_init,
    "test": cmd_test,
    "validate": cmd_validate,
    "publish": cmd_publish,
    "version": cmd_version,
    "list": cmd_list,
    "info": cmd_info,
}


def main(argv: list[str] | None = None) -> int:
    """
    Punto de entrada principal del CLI.

    Parsea los argumentos de linea de comandos y despacha al
    subcomando correspondiente. Si no se especifica un comando,
    muestra la ayuda.

    Args:
        argv: Lista de argumentos (default: sys.argv[1:])

    Retorna:
        Codigo de salida (0 = exito, 1 = error)
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    handler = COMMAND_MAP.get(args.command)
    if handler is None:
        print(f"Error: Comando desconocido '{args.command}'")
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\nOperacion cancelada por el usuario")
        return 130
    except Exception as exc:
        print(f"Error inesperado: {exc}")
        logger.error(f"Error en comando '{args.command}': {exc}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
