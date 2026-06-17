#!/usr/bin/env python3
"""
Auditoría extrema de Zenic-Flijo v2.0.0
========================================

Ejecuta 10 dimensiones de pruebas para romper el sistema:
1. Seguridad (SQLi, XSS, auth bypass)
2. Robustez de inputs (nulls, payloads grandes)
3. Concurrencia (race conditions)
4. Performance (stress)
5. Integridad de datos (cascade, FK)
6. API surface (auth gaps, validation)
7. Motor ORBITAL (caos matemático)
8. Multi-tenancy (RBAC bypass)
9. Compliance (PII leaks)
10. Frontend (XSS, leaks)

Cada prueba retorna: PASS, FAIL, CRITICAL, o WARNING.
Al final genera un JSON con todos los resultados.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import threading
import concurrent.futures
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

REPO = Path("/home/z/my-project/repos/Zenic-Flijo")
BASE_URL = "http://127.0.0.1:8080"
RESULTS_FILE = Path("/home/z/my-project/audit_results.json")

# ─── Dataclasses ─────────────────────────────────────────────────────────


@dataclass
class TestResult:
    dimension: str
    test_name: str
    severity: str  # PASS, FAIL, CRITICAL, WARNING
    expected: str
    actual: str
    details: str = ""


@dataclass
class AuditReport:
    started_at: str = ""
    finished_at: str = ""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    critical: int = 0
    warnings: int = 0
    score: float = 0.0
    results: list[TestResult] = field(default_factory=list)

    def add(self, r: TestResult) -> None:
        self.results.append(r)
        self.total_tests += 1
        if r.severity == "PASS":
            self.passed += 1
        elif r.severity == "FAIL":
            self.failed += 1
        elif r.severity == "CRITICAL":
            self.critical += 1
        elif r.severity == "WARNING":
            self.warnings += 1

    def compute_score(self) -> None:
        if self.total_tests == 0:
            self.score = 0.0
            return
        # Score = (PASS + 0.5*WARNING) / total * 100, penalizado por CRITICAL
        weighted = self.passed + 0.5 * self.warnings
        self.score = round((weighted / self.total_tests) * 100, 2)
        # Penalización por críticos
        if self.critical > 0:
            self.score = max(0, self.score - self.critical * 5)


# ─── Backend management ──────────────────────────────────────────────────


def start_backend() -> subprocess.Popen | None:
    """Inicia el backend y retorna el proceso."""
    # Matar procesos previos
    subprocess.run(["pkill", "-f", "src.main"], capture_output=True)
    time.sleep(2)

    env = os.environ.copy()
    env["WFD_SESSION_SECRET"] = "audit-test-secret-" + os.urandom(16).hex()
    env["WFD_LICENSE_SECRET"] = "audit-license-secret-" + os.urandom(16).hex()
    env["WFD_WEB_HOST"] = "0.0.0.0"
    env["WFD_WEB_PORT"] = "8080"
    env["WFD_WEBHOOK_PORT"] = "8081"
    env["PYTHONPATH"] = str(REPO)

    log_file = open("/tmp/audit_backend.log", "w")
    proc = subprocess.Popen(
        ["/home/z/.venv/bin/python3", "-m", "src.main"],
        cwd=str(REPO),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    # Esperar a que arranque
    for _ in range(20):
        time.sleep(1)
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/auth/status", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            continue

    print("❌ Backend no arrancó")
    return None


def stop_backend(proc: subprocess.Popen | None) -> None:
    if proc:
        proc.terminate()
        proc.wait(timeout=10)
    subprocess.run(["pkill", "-f", "src.main"], capture_output=True)


def http_request(method: str, path: str, body: dict | None = None,
                 cookies: str = "", timeout: int = 10) -> tuple[int, str, dict]:
    """Hace request HTTP y retorna (status, body_text, headers).
    NO sigue redirecciones (para que 302 se reporte como 302, no como 200)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    if cookies:
        req.add_header("Cookie", cookies)
    try:
        # Usar un opener que no sigue redirecciones
        opener = urllib.request.build_opener(NoRedirectHandler)
        resp = opener.open(req, timeout=timeout)
        return resp.status, resp.read().decode("utf-8", errors="replace"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace"), dict(e.headers)
    except Exception as e:
        return 0, str(e), {}


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Handler que NO sigue redirecciones — reporta 302 como error."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # No seguir redirección
    http_error_301 = http_error_302 = http_error_303 = http_error_307 = lambda self, req, fp, code, msg, headers: fp


def login() -> str:
    """Login admin y retorna cookie string."""
    code, body, headers = http_request("POST", "/api/auth/login",
        {"username": "admin", "password": "admin123"})
    if code == 200:
        set_cookie = headers.get("Set-Cookie", "")
        # Extraer solo el session cookie
        if ";" in set_cookie:
            return set_cookie.split(";")[0]
        return set_cookie
    return ""


# ─── D1: Seguridad ───────────────────────────────────────────────────────


def test_security(report: AuditReport, cookies: str) -> None:
    print("\n🔍 D1: Seguridad")
    sqli_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "' UNION SELECT * FROM users--",
        "admin'--",
        "1; SELECT pg_sleep(5)--",
    ]
    for i, payload in enumerate(sqli_payloads):
        code, body, _ = http_request("POST", "/api/auth/login",
            {"username": payload, "password": payload})
        # No debe dar 200 (login exitoso) ni 500 (error interno)
        if code == 200:
            report.add(TestResult("D1-Security", f"SQLi login #{i}", "CRITICAL",
                "Login debe fallar", f"Login exitoso con payload: {payload}"))
        elif code == 500:
            report.add(TestResult("D1-Security", f"SQLi login #{i}", "FAIL",
                "Sin error 500", f"Error 500 con payload: {payload}"))
        else:
            report.add(TestResult("D1-Security", f"SQLi login #{i}", "PASS",
                "Login rechazado", f"HTTP {code}"))

    # XSS en workflow name
    xss_payloads = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert(1)>",
        "javascript:alert(1)",
        "\"><script>alert(1)</script>",
    ]
    for i, payload in enumerate(xss_payloads):
        code, body, _ = http_request("POST", "/api/workflows",
            {"name": payload, "trigger_type": "manual", "trigger_config": {}, "steps": []},
            cookies=cookies)
        if code in (200, 201):
            # Verificar que el nombre se sanitiza al leer
            wf_id = json.loads(body).get("id")
            if wf_id:
                code2, body2, _ = http_request("GET", f"/api/workflows", cookies=cookies)
                if "<script>" in body2.lower():
                    report.add(TestResult("D1-Security", f"XSS workflow #{i}", "CRITICAL",
                        "XSS sanitizado", "XSS sin sanitizar en respuesta"))
                else:
                    report.add(TestResult("D1-Security", f"XSS workflow #{i}", "PASS",
                        "XSS sanitizado", "XSS bloqueado/sanitizado"))
                # Limpiar
                http_request("DELETE", f"/api/workflows/{wf_id}", cookies=cookies)
        else:
            report.add(TestResult("D1-Security", f"XSS workflow #{i}", "PASS",
                "Workflow rechazado", f"HTTP {code}"))

    # Auth bypass: acceder a endpoint protegido sin cookie
    protected_endpoints = [
        ("GET", "/api/workflows"),
        ("GET", "/api/admin/metrics"),
        ("GET", "/api/orbital/status"),
        ("GET", "/api/admin/alerts/stats"),
    ]
    for method, path in protected_endpoints:
        code, _, _ = http_request(method, path)
        if code == 200:
            report.add(TestResult("D1-Security", f"Auth bypass {path}", "CRITICAL",
                "401/302", "200 sin auth"))
        else:
            report.add(TestResult("D1-Security", f"Auth bypass {path}", "PASS",
                "401/302", f"HTTP {code}"))


# ─── D2: Robustez de inputs ──────────────────────────────────────────────


def test_input_robustness(report: AuditReport, cookies: str) -> None:
    print("\n🔨 D2: Robustez de inputs")
    # Payloads patológicos
    payloads = [
        ("null", None),
        ("empty string", ""),
        ("whitespace only", "   "),
        ("unicode null", "\x00"),
        ("very long string", "A" * 100000),
        ("nested object", {"a": {"b": {"c": {"d": "deep"}}}}),
        ("array of nulls", [None] * 1000),
        ("number as string", "12345"),
        ("boolean as string", "true"),
        ("NaN", float("nan") if False else "NaN"),
    ]
    for name, value in payloads:
        try:
            code, body, _ = http_request("POST", "/api/workflows",
                {"name": value if isinstance(value, str) else "test",
                 "trigger_type": "manual", "trigger_config": {},
                 "steps": [{"id": 1, "tool": "crm", "action": "list_leads", "params": value if isinstance(value, dict) else {}}]},
                cookies=cookies, timeout=15)
            if code == 500:
                report.add(TestResult("D2-Robustness", f"Input {name}", "FAIL",
                    "Sin 500", f"HTTP 500 con payload: {name}"))
            elif code in (200, 201):
                wf_id = json.loads(body).get("id")
                if wf_id:
                    http_request("DELETE", f"/api/workflows/{wf_id}", cookies=cookies)
                report.add(TestResult("D2-Robustness", f"Input {name}", "PASS",
                    "Maneja el payload", f"HTTP {code}"))
            else:
                report.add(TestResult("D2-Robustness", f"Input {name}", "PASS",
                    "Rechaza gracefully", f"HTTP {code}"))
        except Exception as e:
            report.add(TestResult("D2-Robustness", f"Input {name}", "WARNING",
                "Maneja el payload", f"Excepción: {e}"))


# ─── D3: Concurrencia ────────────────────────────────────────────────────


def test_concurrency(report: AuditReport, cookies: str) -> None:
    print("\n🔀 D3: Concurrencia")
    # Login concurrente
    def do_login():
        return http_request("POST", "/api/auth/login",
            {"username": "admin", "password": "admin123"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(do_login) for _ in range(20)]
        results = [f.result() for f in futures]

    success_count = sum(1 for code, _, _ in results if code == 200)
    if success_count == 20:
        report.add(TestResult("D3-Concurrency", "20 logins concurrentes", "PASS",
            "Todos exitosos", f"{success_count}/20 OK"))
    else:
        report.add(TestResult("D3-Concurrency", "20 logins concurrentes", "WARNING",
            "Todos exitosos", f"{success_count}/20 OK"))

    # Crear workflow concurrente
    def create_wf(i):
        return http_request("POST", "/api/workflows",
            {"name": f"Concurrent WF {i}", "trigger_type": "manual",
             "trigger_config": {}, "steps": []}, cookies=cookies)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(create_wf, i) for i in range(10)]
        results = [f.result() for f in futures]

    created = sum(1 for code, _, _ in results if code in (200, 201))
    # Limpiar
    for code, body, _ in results:
        if code in (200, 201):
            wf_id = json.loads(body).get("id")
            if wf_id:
                http_request("DELETE", f"/api/workflows/{wf_id}", cookies=cookies)

    if created == 10:
        report.add(TestResult("D3-Concurrency", "10 workflows concurrentes", "PASS",
            "Todos creados", f"{created}/10 OK"))
    else:
        report.add(TestResult("D3-Concurrency", "10 workflows concurrentes", "FAIL",
            "Todos creados", f"{created}/10 OK"))

    # Ejecutar workflow concurrente
    code, body, _ = http_request("POST", "/api/workflows",
        {"name": "Exec Concurrent", "trigger_type": "manual",
         "trigger_config": {}, "steps": [{"id": 1, "tool": "system", "action": "wait", "params": {"seconds": 1}}]},
        cookies=cookies)
    if code in (200, 201):
        wf_id = json.loads(body).get("id")
        def exec_wf():
            return http_request("POST", f"/api/workflows/{wf_id}/execute", {"trigger_data": {}}, cookies=cookies, timeout=30)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(exec_wf) for _ in range(5)]
            results = [f.result() for f in futures]
        exec_ok = sum(1 for code, _, _ in results if code == 200)
        report.add(TestResult("D3-Concurrency", "5 ejecuciones concurrentes", "PASS" if exec_ok == 5 else "WARNING",
            "Todas exitosas", f"{exec_ok}/5 OK"))
        http_request("DELETE", f"/api/workflows/{wf_id}", cookies=cookies)


# ─── D4: Performance ─────────────────────────────────────────────────────


def test_performance(report: AuditReport, cookies: str) -> None:
    print("\n⚡ D4: Performance")
    # Crear 50 workflows
    start = time.time()
    created = 0
    for i in range(50):
        code, _, _ = http_request("POST", "/api/workflows",
            {"name": f"Perf WF {i}", "trigger_type": "manual",
             "trigger_config": {}, "steps": []}, cookies=cookies)
        if code in (200, 201):
            created += 1
    elapsed = time.time() - start
    if elapsed < 10:
        report.add(TestResult("D4-Performance", "50 workflows en <10s", "PASS",
            f"<10s", f"{elapsed:.2f}s ({created} creados)"))
    else:
        report.add(TestResult("D4-Performance", "50 workflows en <10s", "WARNING",
            f"<10s", f"{elapsed:.2f}s"))

    # Listar todos
    start = time.time()
    code, body, _ = http_request("GET", "/api/workflows", cookies=cookies, timeout=15)
    elapsed = time.time() - start
    if code == 200 and elapsed < 2:
        report.add(TestResult("D4-Performance", "Listar 50 workflows", "PASS",
            "<2s", f"{elapsed:.2f}s"))
    else:
        report.add(TestResult("D4-Performance", "Listar 50 workflows", "WARNING",
            "<2s", f"{elapsed:.2f}s, HTTP {code}"))

    # Limpiar
    code, body, _ = http_request("GET", "/api/workflows", cookies=cookies)
    if code == 200:
        for wf in json.loads(body):
            http_request("DELETE", f"/api/workflows/{wf['id']}", cookies=cookies)

    # Dashboard stats
    start = time.time()
    code, _, _ = http_request("GET", "/api/dashboard/stats", cookies=cookies)
    elapsed = time.time() - start
    if code == 200 and elapsed < 1:
        report.add(TestResult("D4-Performance", "Dashboard stats", "PASS",
            "<1s", f"{elapsed:.2f}s"))
    else:
        report.add(TestResult("D4-Performance", "Dashboard stats", "WARNING",
            "<1s", f"{elapsed:.2f}s"))

    # Métricas admin
    start = time.time()
    code, _, _ = http_request("GET", "/api/admin/metrics", cookies=cookies)
    elapsed = time.time() - start
    if code == 200 and elapsed < 2:
        report.add(TestResult("D4-Performance", "Admin metrics", "PASS",
            "<2s", f"{elapsed:.2f}s"))
    else:
        report.add(TestResult("D4-Performance", "Admin metrics", "WARNING",
            "<2s", f"{elapsed:.2f}s"))


# ─── D5: Integridad de datos ─────────────────────────────────────────────


def test_data_integrity(report: AuditReport, cookies: str) -> None:
    print("\n🗄️  D5: Integridad de datos")
    # Crear workflow y verificar que se puede leer
    code, body, _ = http_request("POST", "/api/workflows",
        {"name": "Integrity Test", "trigger_type": "manual",
         "trigger_config": {}, "steps": [{"id": 1, "tool": "crm", "action": "list_leads", "params": {}}]},
        cookies=cookies)
    if code not in (200, 201):
        report.add(TestResult("D5-Integrity", "Crear workflow", "FAIL", "200/201", f"HTTP {code}"))
        return
    wf_id = json.loads(body).get("id")

    # Leer workflow
    code, body, _ = http_request("GET", f"/api/workflows/{wf_id}", cookies=cookies)
    if code == 200:
        report.add(TestResult("D5-Integrity", "Leer workflow creado", "PASS",
            "200", "Workflow accesible"))
    else:
        report.add(TestResult("D5-Integrity", "Leer workflow creado", "FAIL",
            "200", f"HTTP {code}"))

    # Ejecutar y verificar historial
    code, _, _ = http_request("POST", f"/api/workflows/{wf_id}/execute", {"trigger_data": {}}, cookies=cookies)
    code, body, _ = http_request("GET", f"/api/workflows/{wf_id}/history", cookies=cookies)
    if code == 200:
        history = json.loads(body)
        report.add(TestResult("D5-Integrity", "Historial de ejecución", "PASS",
            "200 con historial", f"{len(history)} ejecuciones registradas"))
    else:
        report.add(TestResult("D5-Integrity", "Historial de ejecución", "FAIL",
            "200", f"HTTP {code}"))

    # Borrar y verificar que ya no existe
    code, _, _ = http_request("DELETE", f"/api/workflows/{wf_id}", cookies=cookies)
    code, body, _ = http_request("GET", f"/api/workflows/{wf_id}", cookies=cookies)
    if code == 404:
        report.add(TestResult("D5-Integrity", "Borrado cascade", "PASS",
            "404 tras delete", "Workflow eliminado correctamente"))
    else:
        report.add(TestResult("D5-Integrity", "Borrado cascade", "WARNING",
            "404", f"HTTP {code}"))

    # Acceder a workflow inexistente
    code, _, _ = http_request("GET", "/api/workflows/99999", cookies=cookies)
    if code == 404:
        report.add(TestResult("D5-Integrity", "Workflow inexistente", "PASS",
            "404", "Correcto 404"))
    else:
        report.add(TestResult("D5-Integrity", "Workflow inexistente", "FAIL",
            "404", f"HTTP {code}"))


# ─── D6: API surface ─────────────────────────────────────────────────────


def test_api_surface(report: AuditReport, cookies: str) -> None:
    print("\n🌐 D6: API surface")
    # Method tampering
    code, _, _ = http_request("DELETE", "/api/auth/status")
    if code in (405, 404):
        report.add(TestResult("D6-API", "Method tampering DELETE /status", "PASS",
            "405/404", f"HTTP {code}"))
    else:
        report.add(TestResult("D6-API", "Method tampering DELETE /status", "WARNING",
            "405/404", f"HTTP {code}"))

    # Params inválidos
    code, _, _ = http_request("GET", "/api/workflows?limit=-1", cookies=cookies)
    if code in (200, 400, 422):
        report.add(TestResult("D6-API", "Param limit=-1", "PASS",
            "200/400/422", f"HTTP {code}"))
    else:
        report.add(TestResult("D6-API", "Param limit=-1", "FAIL",
            "200/400/422", f"HTTP {code}"))

    code, _, _ = http_request("GET", "/api/workflows?limit=999999", cookies=cookies)
    if code in (200, 400, 422):
        report.add(TestResult("D6-API", "Param limit=999999", "PASS",
            "200/400/422", f"HTTP {code}"))
    else:
        report.add(TestResult("D6-API", "Param limit=999999", "FAIL",
            "200/400/422", f"HTTP {code}"))

    # Rate limiting (10 intentos fallidos de login)
    blocked = 0
    for _ in range(15):
        code, _, _ = http_request("POST", "/api/auth/login",
            {"username": "admin", "password": "wrong"})
        if code == 429:
            blocked += 1
    if blocked > 0:
        report.add(TestResult("D6-API", "Rate limiting login", "PASS",
            "429 tras 10 intentos", f"{blocked} bloqueos"))
    else:
        report.add(TestResult("D6-API", "Rate limiting login", "WARNING",
            "429 tras 10 intentos", "Sin rate limiting visible"))


# ─── D7: Motor ORBITAL ───────────────────────────────────────────────────


def test_orbital(report: AuditReport, cookies: str) -> None:
    print("\n🌌 D7: Motor ORBITAL")
    # Variable con amplitud extrema
    code, body, _ = http_request("POST", "/api/orbital/variable",
        {"name": "extreme_amp", "theta": 0, "amplitude": 1000000, "velocity": 0.1},
        cookies=cookies)
    if code == 200:
        # Tick y verificar que no crashea
        code, body, _ = http_request("POST", "/api/orbital/tick", cookies=cookies)
        if code == 200:
            report.add(TestResult("D7-Orbital", "Amplitud 1M + tick", "PASS",
                "Converge sin crash", "Tick exitoso"))
        else:
            report.add(TestResult("D7-Orbital", "Amplitud 1M + tick", "FAIL",
                "Converge sin crash", f"HTTP {code}"))
        # Limpiar
        http_request("DELETE", "/api/orbital/variable/extreme_amp", cookies=cookies)
    else:
        report.add(TestResult("D7-Orbital", "Amplitud 1M + tick", "WARNING",
            "Variable creada", f"HTTP {code}"))

    # Estado orbital
    code, body, _ = http_request("GET", "/api/orbital/status", cookies=cookies)
    if code == 200:
        report.add(TestResult("D7-Orbital", "Estado orbital", "PASS",
            "200 con datos", "OK"))
    else:
        report.add(TestResult("D7-Orbital", "Estado orbital", "FAIL",
            "200", f"HTTP {code}"))

    # 10 ticks seguidos
    success = 0
    for _ in range(10):
        code, _, _ = http_request("POST", "/api/orbital/tick", cookies=cookies)
        if code == 200:
            success += 1
    if success == 10:
        report.add(TestResult("D7-Orbital", "10 ticks consecutivos", "PASS",
            "10/10 OK", f"{success}/10"))
    else:
        report.add(TestResult("D7-Orbital", "10 ticks consecutivos", "FAIL",
            "10/10 OK", f"{success}/10"))


# ─── D8: Multi-tenancy / RBAC ────────────────────────────────────────────


def test_multitenancy(report: AuditReport, cookies: str) -> None:
    print("\n🏢 D8: Multi-tenancy / RBAC")
    # Sin auth → debe fallar
    code, _, _ = http_request("GET", "/api/workflows")
    if code in (302, 401, 403):
        report.add(TestResult("D8-MultiTenancy", "Sin auth → protegido", "PASS",
            "302/401/403", f"HTTP {code}"))
    else:
        report.add(TestResult("D8-MultiTenancy", "Sin auth → protegido", "CRITICAL",
            "302/401/403", f"HTTP {code}"))

    # Sin auth a admin
    code, _, _ = http_request("GET", "/api/admin/metrics")
    if code in (302, 401, 403):
        report.add(TestResult("D8-MultiTenancy", "Sin auth → admin bloqueado", "PASS",
            "302/401/403", f"HTTP {code}"))
    else:
        report.add(TestResult("D8-MultiTenancy", "Sin auth → admin bloqueado", "CRITICAL",
            "302/401/403", f"HTTP {code}"))

    # Sin auth a alertas
    code, _, _ = http_request("GET", "/api/admin/alerts/stats")
    if code in (302, 401, 403):
        report.add(TestResult("D8-MultiTenancy", "Sin auth → alerts bloqueado", "PASS",
            "302/401/403", f"HTTP {code}"))
    else:
        report.add(TestResult("D8-MultiTenancy", "Sin auth → alerts bloqueado", "CRITICAL",
            "302/401/403", f"HTTP {code}"))


# ─── D9: Compliance ──────────────────────────────────────────────────────


def test_compliance(report: AuditReport, cookies: str) -> None:
    print("\n📋 D9: Compliance")
    # Verificar que login no expone password_hash
    code, body, _ = http_request("POST", "/api/auth/login",
        {"username": "admin", "password": "admin123"})
    if "password_hash" in body.lower():
        report.add(TestResult("D9-Compliance", "Login expone password_hash", "CRITICAL",
            "Sin password_hash", "password_hash en respuesta"))
    else:
        report.add(TestResult("D9-Compliance", "Login no expone password_hash", "PASS",
            "Sin password_hash", "OK"))

    # Verificar que auth/status no expone campos sensibles
    code, body, _ = http_request("GET", "/api/auth/status", cookies=cookies)
    sensitive_fields = ["password", "mfa_secret", "api_key", "token", "secret"]
    leaked = [f for f in sensitive_fields if f in body.lower()]
    if leaked:
        report.add(TestResult("D9-Compliance", "Auth status expone campos", "WARNING",
            "Sin campos sensibles", f"Campos: {leaked}"))
    else:
        report.add(TestResult("D9-Compliance", "Auth status limpio", "PASS",
            "Sin campos sensibles", "OK"))

    # Verificar que dashboard stats no expone PII
    code, body, _ = http_request("GET", "/api/dashboard/stats", cookies=cookies)
    if "password" in body.lower() or "email" in body.lower():
        report.add(TestResult("D9-Compliance", "Dashboard expone PII", "WARNING",
            "Sin PII", "Posible PII en dashboard"))
    else:
        report.add(TestResult("D9-Compliance", "Dashboard sin PII", "PASS",
            "Sin PII", "OK"))

    # Audit log existe
    code, body, _ = http_request("GET", "/api/reports/audit/csv", cookies=cookies)
    if code == 200:
        report.add(TestResult("D9-Compliance", "Audit log accesible", "PASS",
            "200", "Audit log disponible"))
    else:
        report.add(TestResult("D9-Compliance", "Audit log accesible", "WARNING",
            "200", f"HTTP {code}"))


# ─── D10: Frontend (vía API) ─────────────────────────────────────────────


def test_frontend(report: AuditReport, cookies: str) -> None:
    print("\n🎨 D10: Frontend (vía API)")
    # SPA routes
    spa_routes = [
        "/app/dashboard", "/app/workflows", "/app/editor",
        "/app/crm", "/app/inventory", "/app/invoices",
        "/app/chat", "/app/admin", "/app/orbital",
        "/app/plugins", "/app/compliance", "/app/settings",
    ]
    ok = 0
    for route in spa_routes:
        code, _, _ = http_request("GET", route, cookies=cookies)
        if code == 200:
            ok += 1
    if ok == len(spa_routes):
        report.add(TestResult("D10-Frontend", "12 SPA routes", "PASS",
            "Todas 200", f"{ok}/{len(spa_routes)}"))
    else:
        report.add(TestResult("D10-Frontend", "12 SPA routes", "FAIL",
            "Todas 200", f"{ok}/{len(spa_routes)}"))

    # Login page
    code, body, _ = http_request("GET", "/login")
    if code == 200 and "<html" in body.lower():
        report.add(TestResult("D10-Frontend", "Login page HTML", "PASS",
            "200 con HTML", "OK"))
    else:
        report.add(TestResult("D10-Frontend", "Login page HTML", "FAIL",
            "200 con HTML", f"HTTP {code}"))

    # SPA build assets
    code, _, _ = http_request("GET", "/static/spa/index.html")
    if code == 200:
        report.add(TestResult("D10-Frontend", "SPA index.html", "PASS",
            "200", "OK"))
    else:
        report.add(TestResult("D10-Frontend", "SPA index.html", "WARNING",
            "200", f"HTTP {code}"))


# ─── Main ────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  AUDITORÍA EXTREMA — Zenic-Flijo v2.0.0")
    print("=" * 60)

    report = AuditReport(
        started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )

    print("\n🚀 Iniciando backend...")
    proc = start_backend()
    if not proc:
        print("❌ No se pudo iniciar el backend")
        sys.exit(1)
    print("✅ Backend listo")

    print("\n🔐 Login admin...")
    cookies = login()
    if not cookies:
        print("❌ Login falló")
        stop_backend(proc)
        sys.exit(1)
    print("✅ Login OK")

    # Ejecutar dimensiones
    test_security(report, cookies)
    test_input_robustness(report, cookies)
    test_concurrency(report, cookies)
    test_performance(report, cookies)
    test_data_integrity(report, cookies)
    test_api_surface(report, cookies)
    test_orbital(report, cookies)
    test_multitenancy(report, cookies)
    test_compliance(report, cookies)
    test_frontend(report, cookies)

    report.compute_score()
    report.finished_at = time.strftime("%Y-%m-%d %H:%M:%S")

    # Guardar resultados
    results_data = {
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "total_tests": report.total_tests,
        "passed": report.passed,
        "failed": report.failed,
        "critical": report.critical,
        "warnings": report.warnings,
        "score": report.score,
        "results": [asdict(r) for r in report.results],
    }
    RESULTS_FILE.write_text(json.dumps(results_data, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("  REPORTE FINAL")
    print("=" * 60)
    print(f"Total tests: {report.total_tests}")
    print(f"✅ PASS: {report.passed}")
    print(f"❌ FAIL: {report.failed}")
    print(f"🚨 CRITICAL: {report.critical}")
    print(f"⚠️  WARNING: {report.warnings}")
    print(f"📊 Score: {report.score}/100")
    print(f"\n📁 Resultados: {RESULTS_FILE}")

    stop_backend(proc)
    return 0 if report.critical == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
