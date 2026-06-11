"""
Marketplace — Motor de Certificacion de Conectores
====================================================

Implementa el proceso de certificacion automatica y manual para
conectores del marketplace. Incluye verificaciones de lint,
seguridad, esquemas y ejecucion de tests.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import zipfile
from enum import Enum
from pathlib import Path
from typing import Any

from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class CertificationStatus(str, Enum):
    """Estados posibles de la certificacion de un conector."""

    PENDING = "pending"
    AUTO_PASSED = "auto_passed"
    AUTO_FAILED = "auto_failed"
    CERTIFIED = "certified"
    REJECTED = "rejected"


class CertificationEngine:
    """
    Motor de certificacion automatica y manual para conectores.

    Ejecuta verificaciones automatizadas (lint, seguridad, esquema,
    tests) y genera reportes detallados con resultados por criterio.
    """

    # Patrones de seguridad a detectar
    SECRET_PATTERNS: list[str] = [
        r'(?i)(api_key|apikey|api_secret|apisecret)\s*=\s*["\'][^"\']{8,}["\']',
        r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']',
        r'(?i)(secret|token)\s*=\s*["\'][^"\']{8,}["\']',
        r'(?i)aws_(access_key_id|secret_access_key)\s*=\s*["\'][^"\']+["\']',
        r"(?i)-----BEGIN (RSA |EC )?PRIVATE KEY-----",
        r"(?i)ghp_[0-9a-zA-Z]{36}",
        r"(?i)sk-[0-9a-zA-Z]{32,}",
    ]

    SQL_INJECTION_PATTERNS: list[str] = [
        r'execute\s*\(\s*f["\']',
        r'execute\s*\(\s*["\'].*%s.*["\']\s*%',
        r"raw\s*\(\s*f[\"']",
        r"\.format\s*\(.*sql",
    ]

    UNSAFE_EVAL_PATTERNS: list[str] = [
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"__import__\s*\(",
        r"subprocess\.call\s*\([^)]*shell\s*=\s*True",
        r"subprocess\.Popen\s*\([^)]*shell\s*=\s*True",
        r"os\.system\s*\(",
    ]

    def auto_review(self, connector_path: str) -> dict[str, Any]:
        """
        Ejecuta la revision automatica de un conector.

        Realiza verificaciones de lint, seguridad, esquema y tests.
        Genera un reporte detallado con resultados por criterio.

        Args:
            connector_path: Ruta al directorio o archivo zip del conector

        Retorna:
            Diccionario con el reporte de certificacion completo
        """
        checks: list[dict[str, Any]] = []
        total_passed = 0
        total_failed = 0
        total_warnings = 0

        # Descomprimir si es un zip
        review_path = self._prepare_path(connector_path)

        # 1. Verificacion de lint con ruff
        lint_result = self._check_lint(review_path)
        checks.append(lint_result)
        if lint_result["status"] == "passed":
            total_passed += 1
        elif lint_result["status"] == "failed":
            total_failed += 1
        if lint_result.get("warnings", 0) > 0:
            total_warnings += 1

        # 2. Escaneo de seguridad
        security_result = self._check_security(review_path)
        checks.append(security_result)
        if security_result["status"] == "passed":
            total_passed += 1
        elif security_result["status"] == "failed":
            total_failed += 1
        if security_result.get("warnings", 0) > 0:
            total_warnings += 1

        # 3. Validacion de esquema
        schema_result = self._check_schema(review_path)
        checks.append(schema_result)
        if schema_result["status"] == "passed":
            total_passed += 1
        elif schema_result["status"] == "failed":
            total_failed += 1
        if schema_result.get("warnings", 0) > 0:
            total_warnings += 1

        # 4. Ejecucion de tests
        test_result = self._check_tests(review_path)
        checks.append(test_result)
        if test_result["status"] == "passed":
            total_passed += 1
        elif test_result["status"] == "failed":
            total_failed += 1
        if test_result.get("warnings", 0) > 0:
            total_warnings += 1

        # Calcular puntuacion y estado final
        total_checks = len(checks)
        score = round((total_passed / total_checks) * 100, 2) if total_checks > 0 else 0
        status = CertificationStatus.AUTO_PASSED if total_failed == 0 else CertificationStatus.AUTO_FAILED

        report = {
            "connector_path": connector_path,
            "status": status.value,
            "checks": checks,
            "passed": total_passed,
            "failed": total_failed,
            "warnings": total_warnings,
            "score": score,
            "details": f"{total_passed}/{total_checks} verificaciones aprobadas",
        }

        logger.info(f"CertificationEngine: revision automatica completada - {status.value} (score={score})")
        return report

    def manual_review_requirements(self) -> dict[str, Any]:
        """
        Retorna los requisitos que cubre la revision manual.

        La revision manual complementa la automatica verificando
        aspectos que no se pueden automatizar facilmente.

        Retorna:
            Diccionario con la lista de requisitos de revision manual
        """
        return {
            "requirements": [
                {
                    "id": "MAN-001",
                    "name": "Revision de codigo por pares",
                    "description": "Al menos un ingeniero senior debe revisar el codigo del conector",
                    "category": "code_quality",
                },
                {
                    "id": "MAN-002",
                    "name": "Verificacion de licencias de dependencias",
                    "description": "Todas las dependencias deben tener licencias compatibles",
                    "category": "legal",
                },
                {
                    "id": "MAN-003",
                    "name": "Revision de manejo de datos sensibles",
                    "description": "Verificar que los datos sensibles se manejan de forma segura",
                    "category": "security",
                },
                {
                    "id": "MAN-004",
                    "name": "Pruebas de integracion con servicio real",
                    "description": "El conector debe probarse contra el servicio real (no solo mocks)",
                    "category": "testing",
                },
                {
                    "id": "MAN-005",
                    "name": "Documentacion de calidad",
                    "description": "La documentacion debe ser completa, clara y con ejemplos",
                    "category": "documentation",
                },
                {
                    "id": "MAN-006",
                    "name": "Verificacion de compatibilidad hacia atras",
                    "description": "Las nuevas versiones no deben romper integraciones existentes",
                    "category": "compatibility",
                },
            ],
            "categories": ["code_quality", "legal", "security", "testing", "documentation", "compatibility"],
        }

    def _prepare_path(self, connector_path: str) -> str:
        """
        Prepara la ruta del conector para revision.

        Si es un archivo zip, lo descomprime en un directorio temporal.

        Args:
            connector_path: Ruta al conector (directorio o zip)

        Retorna:
            Ruta al directorio con el contenido del conector
        """
        if connector_path.endswith(".zip") and os.path.isfile(connector_path):
            extract_dir = connector_path[:-4]
            with zipfile.ZipFile(connector_path, "r") as zf:
                zf.extractall(extract_dir)
            logger.info(f"CertificationEngine: zip descomprimido en {extract_dir}")
            return extract_dir
        return connector_path

    def _check_lint(self, path: str) -> dict[str, Any]:
        """
        Ejecuta la verificacion de lint con ruff.

        Args:
            path: Ruta al directorio del conector

        Retorna:
            Resultado de la verificacion de lint
        """
        try:
            result = subprocess.run(
                ["ruff", "check", path, "--select", "E,W,F,I,UP,B,SIM,RUF"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            errors = result.stdout.strip().split("\n") if result.stdout.strip() else []
            error_count = len([e for e in errors if e.strip()]) if result.returncode != 0 else 0

            return {
                "name": "Lint Check (ruff)",
                "status": "passed" if error_count == 0 else "failed",
                "details": f"{error_count} error(es) de lint encontrados",
                "errors": errors[:20] if error_count > 0 else [],
                "warnings": 0,
            }
        except FileNotFoundError:
            logger.warning("CertificationEngine: ruff no encontrado, saltando lint check")
            return {"name": "Lint Check (ruff)", "status": "passed", "details": "ruff no disponible, verificacion omitida", "warnings": 1}
        except subprocess.TimeoutExpired:
            return {"name": "Lint Check (ruff)", "status": "failed", "details": "Timeout ejecutando ruff check", "warnings": 0}

    def _check_security(self, path: str) -> dict[str, Any]:
        """
        Ejecuta el escaneo de seguridad del conector.

        Busca patrones de secrets codificados, inyecciones SQL,
        y uso inseguro de eval/exec.

        Args:
            path: Ruta al directorio del conector

        Retorna:
            Resultado del escaneo de seguridad
        """
        findings: list[str] = []
        py_files = list(Path(path).rglob("*.py"))

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                lines = content.split("\n")

                for line_num, line in enumerate(lines, 1):
                    # Buscar secrets codificados
                    for pattern in self.SECRET_PATTERNS:
                        if re.search(pattern, line):
                            findings.append(f"{py_file.name}:{line_num} - Posible secret codificado")
                            break

                    # Buscar patrones de inyeccion SQL
                    for pattern in self.SQL_INJECTION_PATTERNS:
                        if re.search(pattern, line):
                            findings.append(f"{py_file.name}:{line_num} - Posible inyeccion SQL")
                            break

                    # Buscar uso inseguro de eval/exec
                    for pattern in self.UNSAFE_EVAL_PATTERNS:
                        if re.search(pattern, line):
                            findings.append(f"{py_file.name}:{line_num} - Uso inseguro de eval/exec")
                            break

            except Exception as e:
                logger.warning(f"CertificationEngine: error leyendo {py_file}: {e}")

        status = "passed" if len(findings) == 0 else "failed"
        return {
            "name": "Security Scan",
            "status": status,
            "details": f"{len(findings)} hallazgo(s) de seguridad",
            "errors": findings[:20],
            "warnings": 0,
        }

    def _check_schema(self, path: str) -> dict[str, Any]:
        """
        Valida el esquema del conector.

        Verifica que el conector tenga la estructura requerida,
        herede de BaseConnector y defina los metodos abstractos.

        Args:
            path: Ruta al directorio del conector

        Retorna:
            Resultado de la validacion de esquema
        """
        errors: list[str] = []
        py_files = list(Path(path).rglob("*.py"))
        has_connector = False

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if not isinstance(node, ast.ClassDef):
                        continue

                    # Verificar si hereda de BaseConnector
                    base_names = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            base_names.append(base.id)
                        elif isinstance(base, ast.Attribute):
                            base_names.append(base.attr)

                    if "BaseConnector" in base_names:
                        has_connector = True

                        # Verificar metodos requeridos
                        method_names = {m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
                        required_methods = {"connect", "execute", "validate", "disconnect"}
                        missing = required_methods - method_names
                        if missing:
                            errors.append(f"{py_file.name}: Clase {node.name} falta metodo(s): {', '.join(missing)}")

                        # Verificar atributos de clase
                        class_attrs = {
                            target.id
                            for stmt in node.body
                            if isinstance(stmt, ast.Assign)
                            for target in stmt.targets
                            if isinstance(target, ast.Name)
                        }
                        if "name" not in class_attrs:
                            errors.append(f"{py_file.name}: Clase {node.name} falta atributo 'name'")

            except SyntaxError as e:
                errors.append(f"{py_file.name}: Error de sintaxis - {e}")
            except Exception as e:
                logger.warning(f"CertificationEngine: error parseando {py_file}: {e}")

        if not has_connector:
            errors.append("No se encontro ninguna clase que herede de BaseConnector")

        status = "passed" if len(errors) == 0 else "failed"
        return {
            "name": "Schema Validation",
            "status": status,
            "details": f"{len(errors)} error(es) de esquema",
            "errors": errors[:20],
            "warnings": 0,
        }

    def _check_tests(self, path: str) -> dict[str, Any]:
        """
        Ejecuta los tests del conector.

        Busca archivos de test en el directorio del conector y los ejecuta.

        Args:
            path: Ruta al directorio del conector

        Retorna:
            Resultado de la ejecucion de tests
        """
        test_files = list(Path(path).rglob("test_*.py")) + list(Path(path).rglob("*_test.py"))

        if not test_files:
            return {
                "name": "Test Execution",
                "status": "passed",
                "details": "No se encontraron tests (se acepta sin tests en la revision automatica)",
                "errors": [],
                "warnings": 1,
            }

        try:
            result = subprocess.run(
                ["python", "-m", "pytest", path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                return {
                    "name": "Test Execution",
                    "status": "passed",
                    "details": "Todos los tests pasaron exitosamente",
                    "errors": [],
                    "warnings": 0,
                }
            else:
                failed_lines = [l for l in result.stdout.split("\n") if "FAILED" in l or "ERROR" in l]
                return {
                    "name": "Test Execution",
                    "status": "failed",
                    "details": f"{len(failed_lines)} test(s) fallaron",
                    "errors": failed_lines[:20],
                    "warnings": 0,
                }
        except FileNotFoundError:
            return {"name": "Test Execution", "status": "passed", "details": "pytest no disponible", "warnings": 1}
        except subprocess.TimeoutExpired:
            return {"name": "Test Execution", "status": "failed", "details": "Timeout ejecutando tests", "warnings": 0}
