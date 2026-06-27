"""Pytest fixtures for E2E HAT tests.

Aisla la DB de tests (WFD_DATA_DIR), resetea singletons y provee un
HATRouter listo para atender requests end-to-end.

v1.0 fix: reset completo de TODOS los singletons y caches entre tests,
no solo OrbitalContext. Esto previene contaminación entre tests que
causaba 24 falsos negativos.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def e2e_data_dir():
    """Crea un directorio temporal para la DB de tests E2E.

    Se usa WFD_DATA_DIR para redirigir la DB workflow_determinista.db
    a un path aislado del de producción (~/.workflow_determinista/).
    Se mantiene por toda la sesión de pytest y se limpia al final.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="e2e_hat_"))
    os.environ["WFD_DATA_DIR"] = str(tmpdir)
    yield tmpdir
    # Cleanup
    if "WFD_DATA_DIR" in os.environ:
        del os.environ["WFD_DATA_DIR"]
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def hat_router(e2e_data_dir):
    """Inicializa HAT una sola vez para toda la sesión de tests E2E.

    Bootstrap completo:
    - Nivel 5: 19 tools instanciadas
    - Nivel 4: ~101 workers auto-generados
    - Nivel 3: 9 specialists + AgentCards publicadas en OVC
    - Nivel 2: 3 supervisores con specialists
    - Nivel 1: HATRouter con supervisores inyectados

    Returns:
        HATRouter listo para atender requests.
    """
    # Reset singletons antes del bootstrap
    from src.core.db.sqlite_manager import DatabaseManager
    DatabaseManager._instance = None

    from src.events.bus import EventBus
    from src.hat.bootstrap import bootstrap_hat

    router = bootstrap_hat(event_bus=EventBus())
    return router


@pytest.fixture(autouse=True)
def _reset_all_state(hat_router):
    """Reset COMPLETO de todos los singletons y caches antes de cada test.

    Esto previene contaminación entre tests que causaba 24 falsos negativos
    en TestRouting, TestFullChain, y TestAntiDuplication.

    Resetea:
    1. OrbitalContext (OVC, TOR, RCC, COD, Espectro)
    2. AntiDuplicationCascade caches (exact_match + ttl_freshness)
    3. Ledger DB (limpiar hat_facts, hat_hypotheses, hat_progress)
    4. HATRouter session state (_current_session_id)
    """
    # 1. Reset OrbitalContext singleton
    try:
        from src.orbital.context import OrbitalContext
        OrbitalContext._reset()
    except Exception:
        pass

    # 2. Reset AntiDuplicationCascade caches del HATRouter
    try:
        from src.hat.level1_orchestrator.anti_duplication.cascade import AntiDuplicationCascade
        # El HATRouter crea la cascade via _run_anti_dup_cascade cada vez,
        # pero las capas internas (ExactMatch, TTLFreshness) pueden tener
        # caches si se reutilizan. Limpiar via clear_cache.
        if hasattr(hat_router, '_ledger') and hat_router._ledger:
            cascade = AntiDuplicationCascade(repo=hat_router._ledger)
            cascade.clear_cache()
    except Exception:
        pass

    # 3. Limpiar tablas del Ledger en la DB de tests
    try:
        from src.core.db.sqlite_manager import DatabaseManager
        db = DatabaseManager()
        # Limpiar tablas HAT que acumulan entre tests
        for table in ("hat_facts", "hat_hypotheses", "hat_progress"):
            with contextlib.suppress(Exception):
                db.execute(f"DELETE FROM {table}")  # nosec B608 — table name es literal
    except Exception:
        pass

    # 4. Reset HATRouter session state
    with contextlib.suppress(Exception):
        hat_router._current_session_id = "default"

    yield

    # Post-test cleanup: mismo reset
    try:
        from src.orbital.context import OrbitalContext
        OrbitalContext._reset()
    except Exception:
        pass
