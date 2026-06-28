#!/usr/bin/env python3
"""M2.6 — Actualizador masivo de imports HAT para migración a 5 niveles.

Reemplaza imports viejos de HAT por nuevos paths en src/hat/level1-level5/.

Uso:
    python scripts/migrate_imports_m2.py
"""
import re
import sys
from pathlib import Path

# Mapeo de imports viejos → nuevos
REPLACEMENTS = [
    # === NIVEL 1: orbital_n0 + ledger + anti_dup + observability + api ===
    (r'\bfrom src\.hat\.orbital_n0\.tick_router import', 'from src.hat.level1_orchestrator.tick_router import'),
    (r'\bfrom src\.hat\.orbital_n0\.states import', 'from src.hat.level1_orchestrator.fsm.states import'),
    (r'\bfrom src\.hat\.orbital_n0\.fsm_disambiguator import', 'from src.hat.level1_orchestrator.fsm.disambiguator import'),
    (r'\bfrom src\.hat\.orbital_n0\.intent_hasher import', 'from src.hat.level1_orchestrator.intent.hasher import'),
    (r'\bfrom src\.hat\.orbital_n0 import', 'from src.hat.level1_orchestrator import'),

    (r'\bfrom src\.hat\.ledger\.repository import', 'from src.hat.level1_orchestrator.ledger.repository import'),
    (r'\bfrom src\.hat\.ledger\.ovc_bridge import', 'from src.hat.level1_orchestrator.ledger.ovc_bridge import'),
    (r'\bfrom src\.hat\.ledger import', 'from src.hat.level1_orchestrator.ledger import'),

    (r'\bfrom src\.hat\.anti_duplication\.cascade import', 'from src.hat.level1_orchestrator.anti_duplication.cascade import'),
    (r'\bfrom src\.hat\.anti_duplication\.exact_match import', 'from src.hat.level1_orchestrator.anti_duplication.exact_match import'),
    (r'\bfrom src\.hat\.anti_duplication\.idempotency import', 'from src.hat.level1_orchestrator.anti_duplication.idempotency import'),
    (r'\bfrom src\.hat\.anti_duplication\.ttl_freshness import', 'from src.hat.level1_orchestrator.anti_duplication.ttl_freshness import'),
    (r'\bfrom src\.hat\.anti_duplication\.circuit_breaker import', 'from src.hat.level4_workers.circuit_breaker import'),
    # semantic_dedup fue eliminado — borrar la línea entera
    (r'^from src\.hat\.anti_duplication\.semantic_dedup import.*\n', ''),
    (r'\bfrom src\.hat\.anti_duplication import', 'from src.hat.level1_orchestrator.anti_duplication import'),

    (r'\bfrom src\.hat\.observability\.dispatch_tracer import', 'from src.hat.level1_orchestrator.observability.dispatch_tracer import'),
    (r'\bfrom src\.hat\.observability import', 'from src.hat.level1_orchestrator.observability import'),

    (r'\bfrom src\.hat\.api\.routes import', 'from src.hat.level1_orchestrator.api.routes import'),
    (r'\bfrom src\.hat\.api import', 'from src.hat.level1_orchestrator.api import'),

    # === NIVEL 2: supervisors ===
    (r'\bfrom src\.hat\.supervisors\.base import', 'from src.hat.level2_supervisors.base import'),
    # Los supervisores research/build/operate fueron eliminados — estos imports
    # se manejan caso por caso (tests que los usan se eliminan en M4)
    # No tocamos los imports de research/build/operate porque esos tests se eliminan después

    # === NIVEL 3: agents → level3_specialists ===
    (r'\bfrom src\.hat\.agents\.cards import', 'from src.hat.level3_specialists.base.cards import'),
    (r'\bfrom src\.hat\.agents\.card_publisher import', 'from src.hat.level3_specialists.base.card_publisher import'),
    # Imports de specialists/workers stubs eliminados — borrar la línea
    (r'^from src\.hat\.agents\.specialists\.[a-z_]+ import.*\n', ''),
    (r'^from src\.hat\.agents\.workers\.[a-z_]+ import.*\n', ''),
    (r'\bfrom src\.hat\.agents import', 'from src.hat.level3_specialists import'),

    # === Limpieza de imports a hat.tools (directorio eliminado) ===
    (r'\bfrom src\.hat\.tools import.*\n', ''),
    (r'\bfrom src\.hat\.tools\..*import.*\n', ''),
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

    # Escanear todos los archivos .py EXCEPTO los que están dentro de src/hat/level*
    # (esos ya están migrados por los sub-agentes)
    py_files = []
    for p in src_dir.rglob('*.py'):
        path_str = str(p)
        # Skip archivos dentro de hat/level* (ya migrados)
        if 'src/hat/level1_orchestrator' in path_str or 'src/hat/level2_supervisors' in path_str:
            continue
        if 'src/hat/level3_specialists' in path_str or 'src/hat/level4_workers' in path_str:
            continue
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
    print(f"M2.6 — HAT Import migration completo")
    print(f"{'='*60}")
    print(f"Archivos escaneados: {len(py_files)}")
    print(f"Archivos modificados: {total_files}")
    print(f"Total de reemplazos: {total_changes}")
    print(f"{'='*60}\n")

    for path_str, changes in files_modified[:20]:
        print(f"✅ {path_str}")
        for ch in changes[:3]:
            print(f"   {ch}")
        if len(changes) > 3:
            print(f"   ... +{len(changes) - 3} más")
        print()

    if len(files_modified) > 20:
        print(f"... y {len(files_modified) - 20} archivos más modificados")

    return 0


if __name__ == '__main__':
    sys.exit(main())
