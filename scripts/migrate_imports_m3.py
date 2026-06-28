#!/usr/bin/env python3
"""M3.4 — Actualizador masivo de imports src.tools → src.hat.level5_tools.

Reemplaza imports viejos de src.tools por nuevos paths en src/hat/level5_tools/.

Uso:
    python scripts/migrate_imports_m3.py
"""
import re
import sys
from pathlib import Path

# Mapeo de imports viejos → nuevos
REPLACEMENTS = [
    # === BUSINESS ===
    (r'\bfrom src\.tools\.crm\.service import', 'from src.hat.level5_tools.business.crm.service import'),
    (r'\bfrom src\.tools\.crm\.repository import', 'from src.hat.level5_tools.business.crm.repository import'),
    (r'\bfrom src\.tools\.crm\.models import', 'from src.hat.level5_tools.business.crm.models import'),
    (r'\bfrom src\.tools\.crm import', 'from src.hat.level5_tools.business.crm import'),

    (r'\bfrom src\.tools\.invoice\.service import', 'from src.hat.level5_tools.business.invoice.service import'),
    (r'\bfrom src\.tools\.invoice\.repository import', 'from src.hat.level5_tools.business.invoice.repository import'),
    (r'\bfrom src\.tools\.invoice\.models import', 'from src.hat.level5_tools.business.invoice.models import'),
    (r'\bfrom src\.tools\.invoice import', 'from src.hat.level5_tools.business.invoice import'),

    (r'\bfrom src\.tools\.inventory\.service import', 'from src.hat.level5_tools.business.inventory.service import'),
    (r'\bfrom src\.tools\.inventory\.repository import', 'from src.hat.level5_tools.business.inventory.repository import'),
    (r'\bfrom src\.tools\.inventory\.models import', 'from src.hat.level5_tools.business.inventory.models import'),
    (r'\bfrom src\.tools\.inventory import', 'from src.hat.level5_tools.business.inventory import'),

    # === COMMUNICATIONS ===
    (r'\bfrom src\.tools\.notification\.service import', 'from src.hat.level5_tools.communications.notification.service import'),
    (r'\bfrom src\.tools\.notification\.models import', 'from src.hat.level5_tools.communications.notification.models import'),
    (r'\bfrom src\.tools\.notification import', 'from src.hat.level5_tools.communications.notification import'),

    # === INTEGRATIONS → split by category ===
    # payments
    (r'\bfrom src\.tools\.integrations\.stripe_service import', 'from src.hat.level5_tools.payments.stripe_service import'),
    (r'\bfrom src\.tools\.integrations\.mercadopago_service import', 'from src.hat.level5_tools.payments.mercadopago_service import'),

    # communications
    (r'\bfrom src\.tools\.integrations\.gmail_service import', 'from src.hat.level5_tools.communications.gmail_service import'),
    (r'\bfrom src\.tools\.integrations\.slack_service import', 'from src.hat.level5_tools.communications.slack_service import'),
    (r'\bfrom src\.tools\.integrations\.telegram_service import', 'from src.hat.level5_tools.communications.telegram_service import'),

    # data
    (r'\bfrom src\.tools\.integrations\.sheets_service import', 'from src.hat.level5_tools.data.sheets_service import'),
    (r'\bfrom src\.tools\.integrations\.drive_service import', 'from src.hat.level5_tools.data.drive_service import'),
    (r'\bfrom src\.tools\.integrations\.postgresql_service import', 'from src.hat.level5_tools.data.postgresql_service import'),

    # automation
    (r'\bfrom src\.tools\.integrations\.openai_service import', 'from src.hat.level5_tools.automation.openai_service import'),
    (r'\bfrom src\.tools\.integrations\.ollama_service import', 'from src.hat.level5_tools.automation.ollama_service import'),

    # whatsapp_service was ELIMINATED (orphan duplicate of notification)
    # Just remove the import line entirely
    (r'^from src\.tools\.integrations\.whatsapp_service import.*\n', ''),
    (r'^from src\.tools\.integrations import WhatsAppService.*\n', ''),

    # === DATA ===
    (r'\bfrom src\.tools\.data_keeper\.service import', 'from src.hat.level5_tools.data.data_keeper.service import'),
    (r'\bfrom src\.tools\.data_keeper\.repository import', 'from src.hat.level5_tools.data.data_keeper.repository import'),
    (r'\bfrom src\.tools\.data_keeper\.models import', 'from src.hat.level5_tools.data.data_keeper.models import'),
    (r'\bfrom src\.tools\.data_keeper import', 'from src.hat.level5_tools.data.data_keeper import'),

    (r'\bfrom src\.tools\.api_connector\.service import', 'from src.hat.level5_tools.data.api_connector.service import'),
    (r'\bfrom src\.tools\.api_connector\.http_client import', 'from src.hat.level5_tools.data.api_connector.http_client import'),
    (r'\bfrom src\.tools\.api_connector\.pagination import', 'from src.hat.level5_tools.data.api_connector.pagination import'),
    (r'\bfrom src\.tools\.api_connector\.rate_limiter import', 'from src.hat.level5_tools.data.api_connector.rate_limiter import'),
    (r'\bfrom src\.tools\.api_connector\.response_cache import', 'from src.hat.level5_tools.data.api_connector.response_cache import'),
    (r'\bfrom src\.tools\.api_connector\.xml_processor import', 'from src.hat.level5_tools.data.api_connector.xml_processor import'),
    (r'\bfrom src\.tools\.api_connector\.webhooks import', 'from src.hat.level5_tools.data.api_connector.webhooks import'),
    (r'\bfrom src\.tools\.api_connector import', 'from src.hat.level5_tools.data.api_connector import'),

    # === AUTOMATION ===
    (r'\bfrom src\.tools\.code_runner\.service import', 'from src.hat.level5_tools.automation.code_runner.service import'),
    (r'\bfrom src\.tools\.code_runner\.sandbox import', 'from src.hat.level5_tools.automation.code_runner.sandbox import'),
    (r'\bfrom src\.tools\.code_runner import', 'from src.hat.level5_tools.automation.code_runner import'),

    (r'\bfrom src\.tools\.logic_gate\.service import', 'from src.hat.level5_tools.automation.logic_gate.service import'),
    (r'\bfrom src\.tools\.logic_gate import', 'from src.hat.level5_tools.automation.logic_gate import'),

    (r'\bfrom src\.tools\.autopilot\.service import', 'from src.hat.level5_tools.automation.autopilot.service import'),
    (r'\bfrom src\.tools\.autopilot import', 'from src.hat.level5_tools.automation.autopilot import'),

    # === GENERIC FALLBACK ===
    (r'\bfrom src\.tools\.integrations import', 'from src.hat.level5_tools import'),
    (r'\bfrom src\.tools import', 'from src.hat.level5_tools import'),
    (r'\bimport src\.tools\b', 'import src.hat.level5_tools'),
]


def update_file(path: Path) -> tuple[int, list[str]]:
    """Actualiza un archivo. Retorna (número de reemplazos, lista de cambios)."""
    try:
        content = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, PermissionError):
        return 0, []

    original = content
    changes = []

    for old_pattern, new_pattern in REPLACEMENTS:
        new_content, count = re.subn(old_pattern, new_pattern, content, flags=re.MULTILINE)
        if count > 0:
            action = "ELIMINADO" if new_pattern == "" else "REEMPLAZADO"
            changes.append(f"  {action}: {old_pattern[:60]} ({count}x)")
            content = new_content

    if content != original:
        path.write_text(content, encoding='utf-8')
        return len(changes), changes

    return 0, []


def main():
    src_dir = Path('/home/z/my-project/Zenic-Flujo/src')

    # Escanear todos los .py EXCEPTO los dentro de src/hat/level5_tools/ (ya migrados)
    py_files = []
    for p in src_dir.rglob('*.py'):
        path_str = str(p)
        if 'src/hat/level5_tools' in path_str:
            continue
        py_files.append(p)

    total_files = 0
    total_changes = 0
    files_modified = []

    for path in py_files:
        count, changes = update_file(path)
        if count > 0:
            total_files += 1
            total_changes += count
            files_modified.append((str(path.relative_to(src_dir.parent)), changes))

    print(f"\n{'='*60}")
    print(f"M3.4 — Tools Import migration completo")
    print(f"{'='*60}")
    print(f"Archivos escaneados: {len(py_files)}")
    print(f"Archivos modificados: {total_files}")
    print(f"Total de reemplazos: {total_changes}")
    print(f"{'='*60}\n")

    for path_str, changes in files_modified[:15]:
        print(f"✅ {path_str}")
        for ch in changes[:2]:
            print(f"   {ch}")
        if len(changes) > 2:
            print(f"   ... +{len(changes) - 2} más")
        print()

    if len(files_modified) > 15:
        print(f"... y {len(files_modified) - 15} archivos más modificados")

    return 0


if __name__ == '__main__':
    sys.exit(main())
