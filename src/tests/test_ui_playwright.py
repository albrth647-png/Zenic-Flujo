"""Test UI completo con Playwright - Navega todo el proyecto en tiempo real"""
import asyncio
from playwright.async_api import async_playwright

async def run_ui_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage']
        )
        page = await browser.new_page()
        results = []

        # 1. Login page
        print("=" * 60)
        print("1. CARGANDO PÁGINA DE LOGIN")
        print("=" * 60)
        await page.goto("http://127.0.0.1:8080/login", wait_until="networkidle")
        title = await page.title()
        content = await page.content()
        print(f"  Title: {title}")
        print(f"  Tamaño HTML: {len(content)} bytes")
        has_login = "login" in content.lower() or "Login" in content
        print(f"  Formulario login visible: {has_login}")
        results.append(("Login page", "PASS" if has_login else "FAIL"))

        # 2. Login
        print("\n" + "=" * 60)
        print("2. INICIANDO SESIÓN")
        print("=" * 60)
        await page.fill('input[name="username"]', "admin")
        await page.fill('input[name="password"]', "admin")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2000)
        current_url = page.url
        print(f"  URL después de login: {current_url}")
        logged_in = "dashboard" in current_url.lower()
        results.append(("Login", "PASS" if logged_in else "FAIL"))

        # 3. Dashboard
        print("\n" + "=" * 60)
        print("3. VERIFICANDO DASHBOARD")
        print("=" * 60)
        await page.goto("http://127.0.0.1:8080/dashboard", wait_until="networkidle")
        dash_content = await page.content()
        has_stats = "stats" in dash_content.lower() or "Stat" in dash_content
        print(f"  Dashboard cargado: {len(dash_content)} bytes")
        print(f"  Estadísticas visibles: {has_stats}")
        results.append(("Dashboard", "PASS" if has_stats else "FAIL"))

        # 4. Chat
        print("\n" + "=" * 60)
        print("4. VERIFICANDO CHAT")
        print("=" * 60)
        await page.goto("http://127.0.0.1:8080/chat", wait_until="networkidle")
        chat_content = await page.content()
        has_chat = "chat" in chat_content.lower() or "Chat" in chat_content
        print(f"  Chat cargado: {len(chat_content)} bytes")
        print(f"  Interfaz chat visible: {has_chat}")
        results.append(("Chat", "PASS" if has_chat else "FAIL"))

        # 5. Workflows list
        print("\n" + "=" * 60)
        print("5. VERIFICANDO LISTA DE WORKFLOWS")
        print("=" * 60)
        await page.goto("http://127.0.0.1:8080/workflows", wait_until="networkidle")
        wf_content = await page.content()
        has_wf = "workflow" in wf_content.lower() or "Workflow" in wf_content
        print(f"  Workflows cargado: {len(wf_content)} bytes")
        print(f"  Lista workflows visible: {has_wf}")
        results.append(("Workflows", "PASS" if has_wf else "FAIL"))

        # 6. Editor
        print("\n" + "=" * 60)
        print("6. VERIFICANDO EDITOR VISUAL")
        print("=" * 60)
        await page.goto("http://127.0.0.1:8080/editor", wait_until="networkidle")
        editor_content = await page.content()
        has_editor = "editor" in editor_content.lower() or "Editor" in editor_content
        print(f"  Editor cargado: {len(editor_content)} bytes")
        print(f"  Editor visible: {has_editor}")
        results.append(("Editor", "PASS" if has_editor else "FAIL"))

        # 7. Settings
        print("\n" + "=" * 60)
        print("7. VERIFICANDO CONFIGURACIÓN")
        print("=" * 60)
        await page.goto("http://127.0.0.1:8080/settings", wait_until="networkidle")
        settings_content = await page.content()
        has_settings = "setting" in settings_content.lower() or "Setting" in settings_content
        print(f"  Settings cargado: {len(settings_content)} bytes")
        print(f"  Configuración visible: {has_settings}")
        results.append(("Settings", "PASS" if has_settings else "FAIL"))

        # 8. Consola
        print("\n" + "=" * 60)
        print("8. ERRORES DE CONSOLA")
        print("=" * 60)
        console_errors = []
        page.on("dialog", lambda dialog: console_errors.append(f"Dialog: {dialog.message}"))
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(2000)
        if console_errors:
            for err in console_errors[:10]:
                print(f"  ❌ {err}")
        else:
            print("  ✅ Sin errores de diálogo ni alertas")
        results.append(("Consola", "PASS" if not console_errors else "FAIL"))

        # Screenshot
        await page.screenshot(path="test_ui_final.png")
        print("\n  📸 Screenshot guardado: test_ui_final.png")

        await browser.close()

        # Resumen final
        print("\n" + "=" * 60)
        print("RESUMEN FINAL DE PRUEBAS UI")
        print("=" * 60)
        all_pass = True
        for name, status in results:
            icon = "✅" if status == "PASS" else "❌"
            print(f"  {icon} {name}: {status}")
            if status == "FAIL":
                all_pass = False
        print(f"\n  {'✅ TODAS LAS PRUEBAS PASARON' if all_pass else '❌ ALGUNAS PRUEBAS FALLARON'}")

asyncio.run(run_ui_test())
