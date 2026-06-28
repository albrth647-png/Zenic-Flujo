"""
Sprint 6 (Fase 6) — IoC Container ligero.
=========================================

Resuelve BUG-ARCH-01 (singletonitis) introduciendo un patrón de registro
y resolución de dependencias que convive con los singletons existentes.

Estrategia gradual (sin breaking changes):
1. Los singletons actuales siguen funcionando como están.
2. Los servicios NUEVOS pueden registrarse en el container y resolverse
   vía type hints o por nombre.
3. Los tests pueden overridear dependencias sin tocar _instance.

Uso:
    from src.container import container

    # Registrar
    container.register("db", DatabaseManager)
    container.register_factory("event_bus", lambda: EventBus())

    # Resolver
    db = container.resolve("db")
    event_bus = container.resolve("event_bus")

    # Override para tests
    container.override("db", mock_db)
    db = container.resolve("db")  # retorna mock_db

    # Reset overrides
    container.reset_overrides()

El container es sí mismo un singleton (única instancia global), pero
actúa como punto único de configuración en lugar de tener 15+ singletons
dispersos por el código.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class ContainerError(Exception):
    """Error del IoC container."""


class Container:
    """
    IoC container thread-safe con soporte para:
    - Registro por clase (singleton lazy)
    - Registro por factory (función que retorna la instancia)
    - Registro por instancia (ya construida)
    - Overrides para tests
    - Scopes (pendiente para v2.1)
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._factories: dict[str, Callable[[], Any]] = {}
        self._instances: dict[str, Any] = {}
        self._overrides: dict[str, Any] = {}
        self._singletons: set[str] = set()

    # ── Registro ──────────────────────────────────────────────

    def register(
        self,
        name: str,
        factory: Callable[[], Any] | type,
        singleton: bool = True,
    ) -> None:
        """
        Registra una dependencia.

        Args:
            name: Nombre único de la dependencia.
            factory: Función factory o clase a instanciar.
            singleton: Si True, la instancia se cachea tras la primera resolución.
        """
        with self._lock:
            if isinstance(factory, type):
                # Si es una clase, crear factory que instancia
                cls = factory
                self._factories[name] = cls
            else:
                self._factories[name] = factory

            if singleton:
                self._singletons.add(name)

            # Invalidar instancia cacheada si se re-registra
            self._instances.pop(name, None)

    def register_factory(self, name: str, factory: Callable[[], Any]) -> None:
        """Alias para register con factory function."""
        self.register(name, factory, singleton=True)

    def register_instance(self, name: str, instance: object) -> None:
        """Registra una instancia ya construida (singleton inmediato)."""
        with self._lock:
            self._instances[name] = instance
            self._singletons.add(name)
            # No necesita factory porque la instancia ya está construida

    # ── Resolución ────────────────────────────────────────────

    def resolve(self, name: str) -> object:
        """
        Resuelve una dependencia por nombre.
        Lanza ContainerError si no está registrada.
        """
        with self._lock:
            # 1. Override tiene prioridad (para tests)
            if name in self._overrides:
                return self._overrides[name]

            # 2. Instancia cacheada (singleton)
            if name in self._instances:
                return self._instances[name]

            # 3. Factory
            if name not in self._factories:
                raise ContainerError(
                    f"Dependencia no registrada: {name!r}. "
                    f"Disponibles: {list(self._factories.keys())}"
                )

            factory = self._factories[name]
            instance = factory()

            # Cachear si es singleton
            if name in self._singletons:
                self._instances[name] = instance

            return instance

    def has(self, name: str) -> bool:
        """True si la dependencia está registrada."""
        with self._lock:
            return name in self._factories or name in self._instances

    def list_registered(self) -> list[str]:
        """Lista todas las dependencias registradas."""
        with self._lock:
            names = set(self._factories.keys()) | set(self._instances.keys())
            return sorted(names)

    # ── Overrides para tests ──────────────────────────────────

    def override(self, name: str, instance: object) -> None:
        """
        Reemplaza una dependencia con un mock/stub para tests.
        El override tiene prioridad sobre la instancia cacheada.
        """
        with self._lock:
            self._overrides[name] = instance

    def reset_overrides(self) -> None:
        """Elimina todos los overrides (restaura comportamiento normal)."""
        with self._lock:
            self._overrides.clear()

    # ── Limpieza ──────────────────────────────────────────────

    def clear(self) -> None:
        """Elimina todos los registros (útil para reset entre tests)."""
        with self._lock:
            self._factories.clear()
            self._instances.clear()
            self._overrides.clear()
            self._singletons.clear()

    def clear_instances(self) -> None:
        """Solo limpia instancias cacheadas (mantiene factories). Útil para
        forzar re-construcción de singletons."""
        with self._lock:
            self._instances.clear()

    # ── Introspección ─────────────────────────────────────────

    def get_info(self) -> dict[str, Any]:
        """Retorna info del container para debugging."""
        with self._lock:
            return {
                "registered": self.list_registered(),
                "singletons": sorted(self._singletons),
                "cached_instances": sorted(self._instances.keys()),
                "overrides": sorted(self._overrides.keys()),
            }


# ─── Instancia global (singleton del container) ─────────────────────────

container = Container()
"""Container global único. Importar y usar directamente."""


def setup_default_container() -> None:
    """
    Registra las dependencias por defecto del proyecto en el container global.
    Es idempotente: si ya están registradas, no hace nada.

    Esta función debe llamarse al inicio de main.py (junto con el resto de
    inicialización del sistema). Los servicios siguen siendo singletons
    internamente, pero ahora son accesibles vía container.resolve().
    """
    if container.has("db"):
        return  # Ya inicializado

    # ── Data layer ────────────────────────────────────────────
    from src.core.db import DatabaseManager

    container.register("db", lambda: DatabaseManager())

    from src.core.db import RedisService

    container.register("redis", lambda: RedisService())

    # ── Events ────────────────────────────────────────────────
    from src.events.bus import EventBus

    container.register("event_bus", lambda: EventBus())

    # ── Workflow ──────────────────────────────────────────────
    from src.workflow.engine import WorkflowEngine

    container.register("workflow_engine", lambda: WorkflowEngine())

    from src.workflow.repository import WorkflowRepository

    container.register("workflow_repository", lambda: WorkflowRepository())

    # ── Versioning (Sprint 9) ─────────────────────────────────
    from src.workflow.versioning import (
        EnvironmentService,
        PromotionService,
        WorkflowVersionRepository,
    )

    container.register("version_repository", lambda: WorkflowVersionRepository())
    container.register("environment_service", lambda: EnvironmentService())
    container.register("promotion_service", lambda: PromotionService())

    # ── Observability (Sprint 11) ─────────────────────────────
    from src.core.observability.alerts import AlertService

    container.register("alert_service", lambda: AlertService())

    # ── Security ──────────────────────────────────────────────
    from src.core.security.rbac import RBACManager

    container.register("rbac_manager", lambda: RBACManager())
