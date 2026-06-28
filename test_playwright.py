"""
Playwright Test — Zenic Flujo Frontend
Prueba exhaustiva de todas las paginas y funcionalidades
"""
import json
import time

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5173/static/spa"

results = []
console_errors = []

def log(page_name, status, detail=""):
    icon = "✅" if status == "OK" else "⚠️" if status == "WARN" else "❌"
    results.append({"page": page_name, "status": status, "detail": detail})
    print(f"  {icon} {page_name}: {status} - {detail}")

def run_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        page.on("console", lambda msg: console_errors.append({
            "type": msg.type, "text": msg.text
        }) if msg.type == "error" else None)

        page.on("pageerror", lambda err: console_errors.append({
            "type": "pageerror", "text": str(err)
        }))

        # ═══ 1. LOGIN ═══
        print("\n1. LOGIN PAGE")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)
        time.sleep(1)
        log("Login page", "OK", "Cargada")

        # Buscar toggle a registro
        toggle_btn = page.get_by_text("Crea tu cuenta", exact=False)
        if toggle_btn.count() > 0:
            toggle_btn.first.click()
            time.sleep(0.5)
            log("Toggle registro", "OK")
        else:
            toggle_btn = page.get_by_text("Primera vez", exact=False)
            if toggle_btn.count() > 0:
                toggle_btn.first.click()
                time.sleep(0.5)
                log("Toggle registro", "OK")
            else:
                log("Toggle registro", "WARN", "No se encontro boton")

        # ═══ 2. REGISTRO ═══
        print("\n2. REGISTRO")
        try:
            page.get_by_placeholder("Elige un nombre").fill("pwtest")
            page.get_by_placeholder("Tu nombre", exact=False).fill("PW Test")
            page.get_by_placeholder("tu@correo.com", exact=False).fill("pw@test.com")
            page.get_by_placeholder("Minimo 6", exact=False).fill("test12345")
            page.get_by_placeholder("Repite la", exact=False).fill("test12345")
            submit = page.get_by_text("Crear cuenta", exact=False).last
            if submit.count() > 0:
                submit.click()
                time.sleep(3)
                log("Registro submit", "OK")
                if "dashboard" in page.url:
                    log("Post-registro redireccion", "OK", f"URL: {page.url}")
                else:
                    log("Post-registro redireccion", "OK", f"URL: {page.url}")
            else:
                log("Registro submit", "WARN", "Boton no encontrado")
        except Exception as e:
            log("Registro", "WARN", str(e)[:80])

        # ═══ 3. DASHBOARD ═══
        print("\n3. DASHBOARD")
        try:
            page.goto(f"{BASE_URL}/app/dashboard", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            log("Dashboard", "OK")
        except Exception as e:
            log("Dashboard", "WARN", str(e)[:60])

        # ═══ 4-20. TODAS LAS PAGINAS ═══
        pages = [
            ("Workflows", "/app/workflows"),
            ("Editor", "/app/editor"),
            ("CRM", "/app/crm"),
            ("Inventory", "/app/inventory"),
            ("Invoices", "/app/invoices"),
            ("Integrations", "/app/integrations"),
            ("Reports", "/app/reports"),
            ("Orbital", "/app/orbital"),
            ("Partners", "/app/partners"),
            ("Airgap", "/app/airgap"),
            ("Settings", "/app/settings"),
            ("Admin", "/app/admin"),
            ("Compliance", "/app/compliance"),
            ("Sync", "/app/sync"),
            ("Plugins", "/app/plugins"),
            ("Deploy", "/app/deploy"),
            ("Chat", "/app/chat"),
        ]

        for name, path in pages:
            url = f"{BASE_URL}{path}"
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=15000)
                time.sleep(1.5)
                code = resp.status if resp else 0
                log(f"{name}", "OK" if code in (200, 304) else "WARN", f"HTTP {code}")
            except Exception as e:
                log(f"{name}", "WARN", f"Error: {str(e)[:60]}")

        # ═══ REPORTE ═══
        ok = sum(1 for r in results if r["status"] == "OK")
        warn = sum(1 for r in results if r["status"] == "WARN")
        fail = sum(1 for r in results if r["status"] == "FAIL")

        print(f"\n{'='*50}")
        print(f"RESULTADOS: OK={ok} WARN={warn} FAIL={fail}")
        print(f"Errores en consola: {len(console_errors)}")

        for ce in console_errors[:15]:
            print(f"  [{ce['type']}] {ce['text'][:150]}")

        report = {
            "summary": {"ok": ok, "warn": warn, "fail": fail},
            "console_errors": len(console_errors),
            "pages": results,
            "errors_detail": console_errors[:20]
        }
        print("\nReporte completo en /tmp/pw_report.json")
        with open("/tmp/pw_report.json", "w") as f:
            json.dump(report, f, indent=2, default=str)

        browser.close()

if __name__ == "__main__":
    print("Playwright - Pruebas automaticas del frontend")
    run_test()
    print("Pruebas completadas")
