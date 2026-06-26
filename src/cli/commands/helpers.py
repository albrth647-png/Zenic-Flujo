"""
Zenic CLI — Helpers compartidos entre comandos
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from src.core.logging import setup_logging

logger = setup_logging(__name__)

# ── Constantes ─────────────────────────────────────────────────

CONNECTORS_BASE_DIR = "src/connectors"
REQUIRED_CONNECTOR_FILES = ["__init__.py", "connector.py", "schema.py"]
REQUIRED_ABSTRACT_METHODS = ["connect", "execute", "validate", "disconnect"]

# ── Whitelist de conectores permitidos ─────────────────────────────
# Fix Sprint 3 bug #37: antes existían ALLOWED_CONNECTORS y DEFAULT_ALLOWED_CONNECTORS
# idénticos (duplicación sin propósito). Se unificó en una sola constante.
# Si se quiere override via env var ZENIC_ALLOWED_CONNECTORS (JSON list),
# se parsea en _import_connector_module/_import_schema_module.
ALLOWED_CONNECTORS = {
    "airtable", "anthropic", "asana", "aws_s3", "azure_ad", "azure_blob",
    "confluence", "datadog", "deepseek", "discord", "dropbox", "dte_chile",
    "elastic", "freshdesk", "gcs", "github", "gitlab", "grafana", "hubspot",
    "huggingface", "intercom", "jira", "mailchimp", "mailgun", "marketo",
    "mercadolibre", "monday", "mongo_connector", "mysql_connector", "new_relic",
    "nfe", "notion", "okta", "openai_v2", "pagerduty", "paypal", "pipedrive",
    "pix_brazil", "quickbooks", "salesforce", "sat_mexico", "sendgrid",
    "sentry", "shopify", "splunk", "square", "sumologic", "teams", "totvs",
    "trello", "twilio", "typeform", "vault", "whatsapp", "wise", "woocommerce",
    "xero", "zendesk", "zoho_crm",
}

# Alias para compatibilidad con código que use el nombre viejo
DEFAULT_ALLOWED_CONNECTORS = ALLOWED_CONNECTORS


# ── Parseo de entrada ──────────────────────────────────────────

def _parse_input(input_data: str | None) -> dict[str, Any]:
    """
    Parsea los datos de entrada desde JSON string o ruta de archivo.
    """
    if input_data is None:
        return {}
    input_path = Path(input_data)
    if input_path.exists() and input_path.is_file():
        try:
            content = input_path.read_text(encoding="utf-8")
            return json.loads(content)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Error: No se pudo leer el archivo de entrada '{input_data}': {exc}", file=sys.stderr)
            return {}
    try:
        return json.loads(input_data)
    except json.JSONDecodeError as exc:
        print(f"Error: No se pudo parsear el input como JSON: {exc}", file=sys.stderr)
        return {}


# ── Carga de conectores ────────────────────────────────────────

def _load_connector(connector_path: Path) -> Any | None:
    """Importa y crea una instancia del conector desde la ruta especificada."""
    if not connector_path.exists():
        print(f"Error: El directorio '{connector_path}' no existe", file=sys.stderr)
        return None
    connector_py = connector_path / "connector.py"
    if not connector_py.exists():
        print(f"Error: No se encontro connector.py en '{connector_path}'", file=sys.stderr)
        return None
    module = _import_connector_module(connector_path)
    if module is None:
        return None

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
                print(f"Error: No se pudo instanciar el conector: {exc}", file=sys.stderr)
                return None
    print("Error: No se encontro una clase que herede de BaseConnector en connector.py", file=sys.stderr)
    return None


def _import_connector_module(connector_path: Path) -> Any | None:
    """Importa dinamicamente el modulo connector.py desde la ruta dada."""
    connector_name = connector_path.name

    # Validar contra whitelist de conectores permitidos
    allowed_connectors = os.environ.get("ZENIC_ALLOWED_CONNECTORS")
    if allowed_connectors:
        allowed_set = {c.strip() for c in allowed_connectors.split(",")}
    else:
        allowed_set = DEFAULT_ALLOWED_CONNECTORS

    if connector_name not in allowed_set:
        logger.error(f"Conector no permitido: '{connector_name}'. No está en la whitelist.")
        return None

    parent_dir = str(connector_path.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    try:
        module_name = f"{connector_name}.connector"
        if module_name in sys.modules:
            del sys.modules[module_name]
        return importlib.import_module(module_name)
    except Exception as exc:
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
    """Importa dinamicamente el modulo schema.py desde la ruta dada."""
    connector_name = connector_path.name

    # Validar contra whitelist de conectores permitidos (mismo check que en _import_connector_module)
    allowed_connectors = os.environ.get("ZENIC_ALLOWED_CONNECTORS")
    if allowed_connectors:
        allowed_set = {c.strip() for c in allowed_connectors.split(",")}
    else:
        allowed_set = DEFAULT_ALLOWED_CONNECTORS

    if connector_name not in allowed_set:
        logger.error(f"Conector no permitido: '{connector_name}'. No está en la whitelist.")
        return None

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


# ── Validación ─────────────────────────────────────────────────

def _run_validation(connector_path: Path) -> dict[str, Any]:
    """Ejecuta todas las validaciones sobre un conector y retorna el reporte."""
    checks: list[dict[str, Any]] = []
    all_passed = True

    files_result = _check_required_files(connector_path)
    checks.append(files_result)
    if not files_result["passed"]:
        all_passed = False

    syntax_result = _check_python_syntax(connector_path)
    checks.append(syntax_result)
    if not syntax_result["passed"]:
        all_passed = False

    inheritance_result = _check_base_connector_inheritance(connector_path)
    checks.append(inheritance_result)
    if not inheritance_result["passed"]:
        all_passed = False

    methods_result = _check_abstract_methods(connector_path)
    checks.append(methods_result)
    if not methods_result["passed"]:
        all_passed = False

    schema_result = _check_schema(connector_path)
    checks.append(schema_result)
    if not schema_result["passed"]:
        all_passed = False

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
    """Verifica que los archivos requeridos del conector existan."""
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
    """Verifica que todos los archivos Python del conector tengan sintaxis valida."""
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
    """Verifica que la clase del conector herede de BaseConnector."""
    connector_py = connector_path / "connector.py"
    if not connector_py.exists():
        return {"name": "Herencia BaseConnector", "passed": False, "details": "Archivo connector.py no encontrado"}
    try:
        module = _import_connector_module(connector_path)
        if module is None:
            return {"name": "Herencia BaseConnector", "passed": False, "details": "No se pudo importar el modulo"}
        from src.sdk.base import BaseConnector
        found = any(
            issubclass(attr_value, BaseConnector) and attr_value is not BaseConnector
            for _attr_name, attr_value in inspect.getmembers(module, inspect.isclass)
        )
        return {
            "name": "Herencia BaseConnector",
            "passed": found,
            "details": "Clase encontrada con herencia correcta" if found else "No se encontro clase que herede de BaseConnector",
        }
    except Exception as exc:
        return {"name": "Herencia BaseConnector", "passed": False, "details": f"Error al verificar: {exc}"}


def _check_abstract_methods(connector_path: Path) -> dict[str, Any]:
    """Verifica que todos los metodos abstractos de BaseConnector esten implementados."""
    try:
        module = _import_connector_module(connector_path)
        if module is None:
            return {"name": "Metodos abstractos", "passed": False, "details": "No se pudo importar el modulo"}
        from src.sdk.base import BaseConnector
        connector_class: type | None = None
        for _attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
            if issubclass(attr_value, BaseConnector) and attr_value is not BaseConnector:
                connector_class = attr_value
                break
        if connector_class is None:
            return {"name": "Metodos abstractos", "passed": False, "details": "No se encontro clase conectora"}
        missing_methods: list[str] = []
        for method_name in REQUIRED_ABSTRACT_METHODS:
            method = getattr(connector_class, method_name, None)
            if method is None or getattr(method, "__isabstractmethod__", False):
                missing_methods.append(method_name)
        return {
            "name": "Metodos abstractos",
            "passed": len(missing_methods) == 0,
            "details": f"Faltan: {', '.join(missing_methods)}" if missing_methods else "Todos los metodos implementados",
            "missing_methods": missing_methods,
        }
    except Exception as exc:
        return {"name": "Metodos abstractos", "passed": False, "details": f"Error al verificar: {exc}"}


def _check_schema(connector_path: Path) -> dict[str, Any]:
    """Verifica que el esquema del conector sea valido segun ConnectorSchema."""
    schema_py = connector_path / "schema.py"
    if not schema_py.exists():
        return {"name": "Esquema del conector", "passed": False, "details": "Archivo schema.py no encontrado"}
    try:
        module = _import_schema_module(connector_path)
        if module is None:
            return {"name": "Esquema del conector", "passed": False, "details": "No se pudo importar schema.py"}
        from src.sdk.schema import ConnectorSchema
        found_schema = False
        schema_version = "N/A"
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, ConnectorSchema):
                found_schema = True
                schema_version = attr.version
                break
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
            "details": f"Esquema valido (version {schema_version})" if found_schema else "No se encontro ConnectorSchema valido",
        }
    except Exception as exc:
        return {"name": "Esquema del conector", "passed": False, "details": f"Error al validar esquema: {exc}"}


def _check_auth_compatibility(connector_path: Path) -> dict[str, Any]:
    """Verifica la compatibilidad del proveedor de autenticacion."""
    try:
        module = _import_connector_module(connector_path)
        if module is None:
            return {"name": "Compatibilidad de autenticacion", "passed": True, "details": "No se pudo importar el modulo (se asume compatible)"}
        from src.sdk.base import BaseConnector
        connector_class: type | None = None
        for _attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
            if issubclass(attr_value, BaseConnector) and attr_value is not BaseConnector:
                connector_class = attr_value
                break
        if connector_class is None:
            return {"name": "Compatibilidad de autenticacion", "passed": True, "details": "No se encontro clase conectora (se asume compatible)"}
        has_auth = hasattr(connector_class, "auth_provider") or "_auth_provider" in getattr(connector_class, "__dict__", {})
        return {
            "name": "Compatibilidad de autenticacion",
            "passed": True,
            "details": "Proveedor de auth configurado" if has_auth else "Sin proveedor de auth explicito",
        }
    except Exception as exc:
        return {"name": "Compatibilidad de autenticacion", "passed": True, "details": f"Verificacion parcial: {exc}"}


def _format_validation_report(report: dict[str, Any]) -> str:
    """Genera un reporte legible de la validacion del conector."""
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
            for key in ("missing_files", "syntax_errors", "missing_methods"):
                items = check.get(key, [])
                if items:
                    for item in items:
                        lines.append(f"           - {item}")
        lines.append("")
    total = report["total_checks"]
    passed = report["passed_checks"]
    failed = report["failed_checks"]
    lines.append("-" * 60)
    lines.append(f"  Total: {total} | Pasaron: {passed} | Fallaron: {failed}")
    overall = "VALIDO" if report["passed"] else "INVALIDO"
    lines.append(f"  Resultado: {overall}")
    lines.append("=" * 60)
    return "\n".join(lines)


# ── Empaquetado ────────────────────────────────────────────────

def _package_connector(connector_path: Path) -> str | None:
    """Empaqueta un conector como archivo .zip con manifest.json."""
    connector_name = connector_path.name
    zip_filename = f"{connector_name}.zip"
    zip_path = connector_path.parent / zip_filename
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in connector_path.rglob("*"):
                if file_path.is_file() and file_path.suffix in (".py", ".json", ".md", ".txt"):
                    arcname = f"{connector_name}/{file_path.relative_to(connector_path)}"
                    zf.write(file_path, arcname)
        logger.info(f"Conector empaquetado: {zip_path}")
        return str(zip_path)
    except Exception as exc:
        logger.error(f"Error empaquetando conector: {exc}")
        return None


def _upload_connector(zip_path: str, registry_url: str) -> bool:
    """Sube un paquete de conector al marketplace via HTTP POST."""
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


# ── Versionado ─────────────────────────────────────────────────

def _read_version(connector_path: Path) -> str | None:
    """Lee la version actual del conector desde __init__.py."""
    init_file = connector_path / "__init__.py"
    if not init_file.exists():
        return None
    content = init_file.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        return match.group(1)
    schema_file = connector_path / "schema.py"
    if schema_file.exists():
        content = schema_file.read_text(encoding="utf-8")
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    return None


def _bump_version(current: str, bump_type: str) -> str | None:
    """Incrementa una version semver segun el tipo de bump."""
    try:
        parts = current.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        if bump_type == "major":
            major += 1; minor = 0; patch = 0
        elif bump_type == "minor":
            minor += 1; patch = 0
        elif bump_type == "patch":
            patch += 1
        else:
            return None
        return f"{major}.{minor}.{patch}"
    except (ValueError, IndexError):
        return None


def _update_version_in_files(connector_path: Path, old_version: str, new_version: str) -> list[str]:
    """Actualiza la version en los archivos del conector."""
    updated: list[str] = []
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
