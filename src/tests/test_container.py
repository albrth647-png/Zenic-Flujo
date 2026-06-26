"""
Tests del IoC Container (Fase 6 — BUG-ARCH-01).

Verifica que el container:
- Registra y resuelve dependencias por factory, clase e instancia.
- Cachea singletons correctamente.
- Soporta overrides para tests.
- Es thread-safe.
- setup_default_container registra las dependencias del proyecto.
"""
from __future__ import annotations

import threading

import pytest

from src.container import Container, ContainerError, container, setup_default_container


@pytest.fixture
def fresh_container() -> Container:
    """Container limpio para cada test."""
    c = Container()
    yield c
    c.clear()


class TestRegistration:
    """Tests de registro de dependencias."""

    def test_register_factory_and_resolve(self, fresh_container: Container):
        fresh_container.register("svc", lambda: {"value": 42})
        svc = fresh_container.resolve("svc")
        assert svc["value"] == 42

    def test_register_class_and_resolve(self, fresh_container: Container):
        class MyService:
            def __init__(self):
                self.name = "test"

        fresh_container.register("svc", MyService)
        svc = fresh_container.resolve("svc")
        assert isinstance(svc, MyService)
        assert svc.name == "test"

    def test_register_instance(self, fresh_container: Container):
        instance = {"pre": "built"}
        fresh_container.register_instance("svc", instance)
        assert fresh_container.resolve("svc") is instance

    def test_register_factory_alias(self, fresh_container: Container):
        fresh_container.register_factory("svc", lambda: [1, 2, 3])
        assert fresh_container.resolve("svc") == [1, 2, 3]

    def test_resolve_unregistered_raises(self, fresh_container: Container):
        with pytest.raises(ContainerError, match="no registrada"):
            fresh_container.resolve("nonexistent")

    def test_has_registered(self, fresh_container: Container):
        assert fresh_container.has("x") is False
        fresh_container.register("x", lambda: None)
        assert fresh_container.has("x") is True

    def test_list_registered(self, fresh_container: Container):
        fresh_container.register("a", lambda: 1)
        fresh_container.register("b", lambda: 2)
        registered = fresh_container.list_registered()
        assert "a" in registered
        assert "b" in registered


class TestSingletonCaching:
    """Tests de caching de singletons."""

    def test_singleton_returns_same_instance(self, fresh_container: Container):
        call_count = [0]

        def factory():
            call_count[0] += 1
            return {"id": call_count[0]}

        fresh_container.register("svc", factory, singleton=True)

        first = fresh_container.resolve("svc")
        second = fresh_container.resolve("svc")

        assert first is second
        assert call_count[0] == 1  # factory llamada solo una vez

    def test_non_singleton_creates_new_each_time(self, fresh_container: Container):
        call_count = [0]

        def factory():
            call_count[0] += 1
            return {"id": call_count[0]}

        fresh_container.register("svc", factory, singleton=False)

        first = fresh_container.resolve("svc")
        second = fresh_container.resolve("svc")

        assert first is not second
        assert call_count[0] == 2

    def test_re_register_clears_cache(self, fresh_container: Container):
        fresh_container.register("svc", lambda: {"v": 1})
        first = fresh_container.resolve("svc")

        fresh_container.register("svc", lambda: {"v": 2})
        second = fresh_container.resolve("svc")

        assert first is not second
        assert first["v"] == 1
        assert second["v"] == 2


class TestOverrides:
    """Tests de overrides para tests."""

    def test_override_returns_mock(self, fresh_container: Container):
        fresh_container.register("svc", lambda: {"real": True})
        mock = {"mock": True}
        fresh_container.override("svc", mock)
        assert fresh_container.resolve("svc") is mock

    def test_reset_overrides_restores_original(self, fresh_container: Container):
        fresh_container.register("svc", lambda: {"real": True})
        real = fresh_container.resolve("svc")

        fresh_container.override("svc", {"mock": True})
        assert fresh_container.resolve("svc") != real

        fresh_container.reset_overrides()
        assert fresh_container.resolve("svc") is real

    def test_override_takes_precedence_over_cached(self, fresh_container: Container):
        fresh_container.register("svc", lambda: {"v": 1})
        fresh_container.resolve("svc")  # cachea

        fresh_container.override("svc", {"v": 999})
        assert fresh_container.resolve("svc")["v"] == 999


class TestClear:
    """Tests de limpieza."""

    def test_clear_removes_all(self, fresh_container: Container):
        fresh_container.register("a", lambda: 1)
        fresh_container.register("b", lambda: 2)
        fresh_container.override("a", "mock")
        assert len(fresh_container.list_registered()) == 2

        fresh_container.clear()
        assert fresh_container.list_registered() == []

    def test_clear_instances_keeps_factories(self, fresh_container: Container):
        fresh_container.register("svc", lambda: {"v": 1})
        fresh_container.resolve("svc")  # cachea instancia

        fresh_container.clear_instances()

        # Factory sigue registrada, así que puede resolver de nuevo
        svc = fresh_container.resolve("svc")
        assert svc["v"] == 1


class TestThreadSafety:
    """Tests de thread-safety."""

    def test_concurrent_resolve_returns_same_singleton(self, fresh_container: Container):
        results: list = []
        barrier = threading.Barrier(10)

        def resolve():
            barrier.wait()
            svc = fresh_container.resolve("svc")
            results.append(svc)

        fresh_container.register("svc", lambda: {"id": id(threading.current_thread())})

        threads = [threading.Thread(target=resolve) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Todas las threads deben haber obtenido la misma instancia (singleton)
        assert len(results) == 10
        first = results[0]
        assert all(r is first for r in results)


class TestGlobalContainer:
    """Tests del container global."""

    def test_global_container_is_singleton(self):
        from src.container import container as c1
        from src.container import container as c2
        assert c1 is c2

    def test_global_container_starts_empty(self):
        # El container global puede tener registros de tests anteriores,
        # pero clear() lo vacía
        container.clear()
        assert container.list_registered() == []
        container.register("test", lambda: 42)
        assert container.resolve("test") == 42
        container.clear()


class TestSetupDefaultContainer:
    """Tests de setup_default_container."""

    def test_setup_registers_all_dependencies(self):
        container.clear()
        setup_default_container()

        registered = container.list_registered()
        # Debe tener al menos 10 dependencias registradas
        assert len(registered) >= 10

        # Verificar las clave
        expected = [
            "db",
            "redis",
            "event_bus",
            "workflow_engine",
            "workflow_repository",
            "version_repository",
            "environment_service",
            "promotion_service",
            "alert_service",
            "rbac_manager",
        ]
        for name in expected:
            assert name in registered, f"Missing: {name}"

        container.clear()

    def test_setup_is_idempotent(self):
        container.clear()
        setup_default_container()
        first_count = len(container.list_registered())

        # Llamar de nuevo no debe duplicar ni romper
        setup_default_container()
        second_count = len(container.list_registered())

        assert first_count == second_count

        container.clear()

    def test_setup_resolves_real_database_manager(self):
        container.clear()
        setup_default_container()

        from src.core.db import DatabaseManager

        db = container.resolve("db")
        assert isinstance(db, DatabaseManager)

        container.clear()


class TestGetInfo:
    """Tests de introspección."""

    def test_get_info_returns_dict(self, fresh_container: Container):
        fresh_container.register("a", lambda: 1)
        info = fresh_container.get_info()

        assert "registered" in info
        assert "singletons" in info
        assert "cached_instances" in info
        assert "overrides" in info
        assert "a" in info["registered"]

    def test_get_info_shows_overrides(self, fresh_container: Container):
        fresh_container.register("a", lambda: 1)
        fresh_container.override("a", "mock")
        info = fresh_container.get_info()
        assert "a" in info["overrides"]
