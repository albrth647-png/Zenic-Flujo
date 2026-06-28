#!/usr/bin/env python3
"""M1.9 — Actualizador masivo de imports para HAT v2 migration.

Reemplaza imports viejos por nuevos paths en src/core/.

Uso:
    python scripts/migrate_imports_m1.py
"""
import re
import sys
from pathlib import Path

# Mapeo de imports viejos → nuevos
# Order matters: more specific patterns first
REPLACEMENTS = [
    # === CONFIG ===
    (r'\bfrom src\.config import', 'from src.core.config import'),
    (r'\bfrom src\.config\.paths import', 'from src.core.config.paths import'),
    (r'\bfrom src\.config\.secrets import', 'from src.core.config.secrets import'),
    (r'\bfrom src\.config\.services import', 'from src.core.config.services import'),
    (r'\bfrom src\.config\.validation import', 'from src.core.config.validation import'),
    (r'\bimport src\.config\b', 'import src.core.config'),

    # === CONTAINER + AIRGAP ===
    (r'\bfrom src\.container import', 'from src.core.container import'),
    (r'\bfrom src\.airgap import', 'from src.core.airgap import'),
    (r'\bimport src\.container\b', 'import src.core.container'),
    (r'\bimport src\.airgap\b', 'import src.core.airgap'),

    # === UTILS ===
    (r'\bfrom src\.utils\.logger import', 'from src.core.logging import'),
    (r'\bfrom src\.utils\.logging_config import', 'from src.core.logging import'),
    (r'\bfrom src\.utils\.helpers import', 'from src.core.utils import'),
    (r'\bfrom src\.utils\.sql import', 'from src.core.db.sql_builder import'),
    (r'\bfrom src\.utils import', 'from src.core.utils import'),
    (r'\bimport src\.utils\b', 'import src.core.utils'),

    # === DATA LAYER ===
    (r'\bfrom src\.data\.database_manager import', 'from src.core.db.sqlite_manager import'),
    (r'\bfrom src\.data\.interfaces import', 'from src.core.db.interfaces import'),
    (r'\bfrom src\.data\.backup_engine import', 'from src.core.db.backup_engine import'),
    (r'\bfrom src\.data\.mongodb_service import', 'from src.core.db.mongodb_service import'),
    (r'\bfrom src\.data\.mongodb_repository import', 'from src.core.db.mongodb_repository import'),
    (r'\bfrom src\.data\.redis_service import', 'from src.core.db.redis_service import'),
    (r'\bfrom src\.data\.marketplace_db import', 'from src.core.db.marketplace_db import'),
    (r'\bfrom src\.data\.settings_repository import', 'from src.core.repositories.settings_repository import'),
    (r'\bfrom src\.data\.user_repository import', 'from src.core.repositories.user_repository import'),
    (r'\bfrom src\.data\.audit_repository import', 'from src.core.repositories.audit_repository import'),
    (r'\bfrom src\.data import', 'from src.core.db import'),
    (r'\bimport src\.data\b', 'import src.core.db'),

    # === SECURITY ===
    (r'\bfrom src\.security\.sso\.keycloak import', 'from src.core.security.sso.keycloak import'),
    (r'\bfrom src\.security\.sso\.oidc import', 'from src.core.security.sso.oidc import'),
    (r'\bfrom src\.security\.sso\.saml import', 'from src.core.security.sso.saml import'),
    (r'\bfrom src\.security\.sso\.session import', 'from src.core.security.sso.session import'),
    (r'\bfrom src\.security\.sso\.routes import', 'from src.core.security.sso.routes import'),
    (r'\bfrom src\.security\.sso\.constants import', 'from src.core.security.sso.constants import'),
    (r'\bfrom src\.security\.sso\.provider_manager import', 'from src.core.security.sso.provider_manager import'),
    (r'\bfrom src\.security\.sso import', 'from src.core.security.sso import'),
    (r'\bfrom src\.security\.sso\.service import', 'from src.core.security.sso.service import'),
    # CRITICAL: src.security.sso (the package) was previously src.security.sso.py (module).
    # The old code did `from src.security.sso import SSOService` which actually loaded sso.py.
    # Now it loads sso/service.py via the new __init__.py. Keep this import path.
    (r'\bfrom src\.security\.mfa import', 'from src.core.security.mfa import'),
    (r'\bfrom src\.security\.key_manager import', 'from src.core.security.key_manager import'),
    (r'\bfrom src\.security\.auth_shared import', 'from src.core.security.auth_shared import'),
    (r'\bfrom src\.security\.rbac import', 'from src.core.security.rbac import'),
    (r'\bfrom src\.security\.encryption import', 'from src.core.security.encryption import'),
    (r'\bfrom src\.security\.vault import', 'from src.core.security.vault import'),
    (r'\bfrom src\.security\.crypto import', 'from src.core.security.crypto import'),
    (r'\bfrom src\.security import', 'from src.core.security import'),
    (r'\bimport src\.security\b', 'import src.core.security'),

    # === OBSERVABILITY ===
    (r'\bfrom src\.observability\.logging_formatter import', 'from src.core.observability.logging import'),
    (r'\bfrom src\.observability\.telemetry import', 'from src.core.observability.telemetry import'),
    (r'\bfrom src\.observability\.telemetry_config import', 'from src.core.observability.telemetry_config import'),
    (r'\bfrom src\.observability\.tracing import', 'from src.core.observability.tracing import'),
    (r'\bfrom src\.observability\.alerts import', 'from src.core.observability.alerts import'),
    (r'\bfrom src\.observability\.metrics\.registry import', 'from src.core.observability.metrics.registry import'),
    (r'\bfrom src\.observability\.metrics\.auth_metrics import', 'from src.core.observability.metrics.auth_metrics import'),
    (r'\bfrom src\.observability\.metrics\.agent_metrics import', 'from src.core.observability.metrics.agent_metrics import'),
    (r'\bfrom src\.observability\.metrics\.bpmn_metrics import', 'from src.core.observability.metrics.bpmn_metrics import'),
    (r'\bfrom src\.observability\.metrics\.compliance_metrics import', 'from src.core.observability.metrics.compliance_metrics import'),
    (r'\bfrom src\.observability\.metrics\.connector_metrics import', 'from src.core.observability.metrics.connector_metrics import'),
    (r'\bfrom src\.observability\.metrics\.db_metrics import', 'from src.core.observability.metrics.db_metrics import'),
    (r'\bfrom src\.observability\.metrics\.marketplace_metrics import', 'from src.core.observability.metrics.marketplace_metrics import'),
    (r'\bfrom src\.observability\.metrics\.mobile_metrics import', 'from src.core.observability.metrics.mobile_metrics import'),
    (r'\bfrom src\.observability\.metrics\.nlu_metrics import', 'from src.core.observability.metrics.nlu_metrics import'),
    (r'\bfrom src\.observability\.metrics\.partner_metrics import', 'from src.core.observability.metrics.partner_metrics import'),
    (r'\bfrom src\.observability\.metrics\.step_metrics import', 'from src.core.observability.metrics.step_metrics import'),
    (r'\bfrom src\.observability\.metrics\.sync_metrics import', 'from src.core.observability.metrics.sync_metrics import'),
    (r'\bfrom src\.observability\.metrics\.system_metrics import', 'from src.core.observability.metrics.system_metrics import'),
    (r'\bfrom src\.observability\.metrics\.tenant_metrics import', 'from src.core.observability.metrics.tenant_metrics import'),
    (r'\bfrom src\.observability\.metrics\.workflow_metrics import', 'from src.core.observability.metrics.workflow_metrics import'),
    (r'\bfrom src\.observability\.metrics import', 'from src.core.observability.metrics import'),
    (r'\bfrom src\.observability import', 'from src.core.observability import'),
    (r'\bimport src\.observability\b', 'import src.core.observability'),

    # === I18N ===
    (r'\bfrom src\.i18n\.locales\.es import', 'from src.core.i18n.locales.es import'),
    (r'\bfrom src\.i18n\.locales\.en import', 'from src.core.i18n.locales.en import'),
    (r'\bfrom src\.i18n\.locales\.pt_br import', 'from src.core.i18n.locales.pt_br import'),
    (r'\bfrom src\.i18n import', 'from src.core.i18n import'),
    (r'\bimport src\.i18n\b', 'import src.core.i18n'),
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
        # Solo reemplazar si el archivo no está YA en src/core/ (evita doble migración)
        if 'src/core/' in str(path):
            # Archivos dentro de src/core/ ya están migrados, skip
            return 0, []
        new_content, count = re.subn(old_pattern, new_pattern, content)
        if count > 0:
            changes.append(f"  {old_pattern} → {new_pattern} ({count}x)")
            content = new_content

    if content != original:
        path.write_text(content, encoding='utf-8')
        return len(changes), changes

    return 0, []


def main():
    src_dir = Path('/home/z/my-project/Zenic-Flujo/src')

    # No tocar archivos dentro de src/core/ (ya migrados)
    py_files = [
        p for p in src_dir.rglob('*.py')
        if 'src/core/' not in str(p) and 'src/core\\' not in str(p)
    ]

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
    print(f"M1.9 — Import migration completo")
    print(f"{'='*60}")
    print(f"Archivos escaneados: {len(py_files)}")
    print(f"Archivos modificados: {total_files}")
    print(f"Total de reemplazos: {total_changes}")
    print(f"{'='*60}\n")

    # Mostrar primeros 30 archivos modificados
    for path_str, changes in files_modified[:30]:
        print(f"✅ {path_str}")
        for ch in changes[:3]:
            print(f"   {ch}")
        if len(changes) > 3:
            print(f"   ... +{len(changes) - 3} más")
        print()

    if len(files_modified) > 30:
        print(f"... y {len(files_modified) - 30} archivos más modificados")

    return 0


if __name__ == '__main__':
    sys.exit(main())
