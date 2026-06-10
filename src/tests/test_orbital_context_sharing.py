"""
ORBITAL — Tests: OrbitalContext Compartido (Bug #1 MiroFish)
=============================================================

Verifica que OrbitalContext comparte correctamente las instancias de OVC,
TOR, RCC, COD y EspectroOrbital entre TODOS los componentes del sistema.

Bug #1 (MiroFish): OrbitalContext Singleton no comparte OVC con OrbitalEngine.
Si id(ctx.ovc) != id(ctx.engine._ovc), las variables orbitales estan aisladas
y la retroalimentacion circular NO funciona.

Ejecutar con: pytest src/tests/test_orbital_context_sharing.py -v
"""

import math
import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.orbital.context import OrbitalContext


# ══════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_orbital_context():
    """Reset singleton antes y despues de cada test."""
    OrbitalContext._reset()
    yield
    OrbitalContext._reset()


@pytest.fixture
def ctx():
    """OrbitalContext compartido con 3 variables orbitales."""
    context = OrbitalContext()
    context.ovc.create_variable("Demanda", theta=0.0, amplitude=10.0, velocity=0.15)
    context.ovc.create_variable("Precio", theta=0.3, amplitude=50.0, velocity=0.08)
    context.ovc.create_variable("Oferta", theta=0.5, amplitude=8.0, velocity=0.12)
    context.rcc.register_cycle_from_names("Economico", ["Demanda", "Precio", "Oferta"], threshold=0.5)
    return context


# ══════════════════════════════════════════════════════════════
# TESTS: Bug #1 — OrbitalContext comparte OVC correctamente
# ══════════════════════════════════════════════════════════════

class TestOrbitalContextOVCParsing:
    """Verifica que ctx.ovc y ctx.engine._ovc son la MISMA instancia."""

    def test_ovc_same_instance_as_engine_ovc(self, ctx):
        """CRITICO: id(ctx.ovc) DEBE ser igual a id(ctx.engine._ovc).
        
        Si falla, el Bug #1 de MiroFish NO esta corregido.
        """
        assert id(ctx.ovc) == id(ctx.engine._ovc), (
            f"Bug #1 activo: ctx.ovc (id={id(ctx.ovc)}) "
            f"!= ctx.engine._ovc (id={id(ctx.engine._ovc)}). "
            "Las variables orbitales NO se comparten."
        )

    def test_tor_same_instance(self, ctx):
        """TOR compartido: ctx.tor debe ser el mismo que el engine usa."""
        assert id(ctx.tor) == id(ctx.engine._tor), (
            "TOR no compartido entre context y engine"
        )

    def test_rcc_same_instance(self, ctx):
        """RCC compartido: ctx.rcc debe ser el mismo que el engine usa."""
        assert id(ctx.rcc) == id(ctx.engine._rcc), (
            "RCC no compartido entre context y engine"
        )

    def test_cod_same_instance(self, ctx):
        """COD compartido: ctx.cod debe ser el mismo que el engine usa."""
        assert id(ctx.cod) == id(ctx.engine._cod), (
            "COD no compartido entre context y engine"
        )

    def test_espectro_same_instance(self, ctx):
        """Espectro compartido: ctx.espectro debe ser el mismo que el engine usa."""
        assert id(ctx.espectro) == id(ctx.engine._espectro), (
            "EspectroOrbital no compartido entre context y engine"
        )


# ══════════════════════════════════════════════════════════════
# TESTS: Variables creadas en ctx son visibles en engine
# ══════════════════════════════════════════════════════════════

class TestVariableVisibility:
    """Verifica que las variables son visibles entre componentes."""

    def test_variable_created_in_ctx_visible_in_engine(self, ctx):
        """Variable creada via ctx.ovc debe ser visible via engine.get_variable()."""
        var = ctx.engine.get_variable("Demanda")
        assert var is not None, "Variable 'Demanda' no encontrada en engine"
        assert var.amplitude == 10.0

    def test_variable_created_in_engine_visible_in_ctx(self, ctx):
        """Variable creada via engine.create_variable() debe ser visible en ctx.ovc."""
        ctx.engine.create_variable("Innovacion", theta=1.2, amplitude=4.0, velocity=0.06)
        var = ctx.ovc.get_variable("Innovacion")
        assert var is not None, "Variable 'Innovacion' no encontrada en ctx.ovc"
        assert var.amplitude == 4.0

    def test_phase_modification_in_ctx_reflected_in_engine(self, ctx):
        """Cambiar fase en ctx.ovc debe reflejarse al consultar via engine."""
        demanda = ctx.ovc.get_variable("Demanda")
        demanda.theta = 1.5  # Cambiar fase

        # Verificar que engine ve el cambio
        engine_var = ctx.engine.get_variable("Demanda")
        assert engine_var.theta == 1.5, (
            "Cambio de fase en ctx.ovc no se refleja en engine"
        )

    def test_phase_modification_in_engine_reflected_in_ctx(self, ctx):
        """Cambiar fase en engine debe reflejarse en ctx.ovc."""
        engine_var = ctx.engine.get_variable("Precio")
        engine_var.theta = 2.0

        ctx_var = ctx.ovc.get_variable("Precio")
        assert ctx_var.theta == 2.0, (
            "Cambio de fase en engine no se refleja en ctx.ovc"
        )


# ══════════════════════════════════════════════════════════════
# TESTS: Ciclo completo OVC → TOR → RCC → COD → Espectro → Retro
# ══════════════════════════════════════════════════════════════

class TestOrbitalCycleCompleteness:
    """Verifica que el ciclo orbital completo funciona con OVC compartido."""

    def test_run_tick_uses_shared_ovc(self, ctx):
        """run_tick debe ejecutar usando el OVC compartido."""
        result = ctx.run_tick()
        assert result.tick == 1
        # Verificar que TOR, RCC, COD y Espectro se ejecutaron
        assert len(result.tor_results) > 0, "TOR no calculó tensiones"
        assert len(result.rcc_results) > 0, "RCC no detectó resonancia"
        assert len(result.cod_results) > 0, "COD no ejecutó colapso"
        assert result.espectro is not None, "Espectro no generado"

    def test_tick_advances_phases_in_shared_ovc(self, ctx):
        """Un tick debe avanzar las fases en el OVC compartido."""
        pre_phases = ctx.ovc.get_phase_snapshot()
        ctx.run_tick()
        post_phases = ctx.ovc.get_phase_snapshot()

        # Al menos una fase debe haber cambiado
        changed = [k for k in pre_phases
                   if not math.isclose(pre_phases[k], post_phases[k], abs_tol=1e-6)]
        assert len(changed) > 0, "Ninguna fase cambió después de un tick"

    def test_multiple_ticks_increment_engine_tick(self, ctx):
        """Multiples ticks deben incrementar el tick del engine y OVC."""
        ctx.run_tick()
        ctx.run_tick()
        ctx.run_tick()
        assert ctx.engine.tick == 3
        # El OVC compartido tambien debe haber avanzado
        assert ctx.ovc.tick == 3

    def test_retrofeedback_modifies_ovc_phases(self, ctx):
        """La retroalimentación del espectro debe modificar las fases del OVC."""
        # Ejecutar varios ticks para que la retroalimentación tenga efecto
        pre_phases = ctx.ovc.get_phase_snapshot()
        for _ in range(5):
            ctx.run_tick()
        post_phases = ctx.ovc.get_phase_snapshot()

        # Verificar que las fases cambiaron
        changed = [k for k in pre_phases
                   if not math.isclose(pre_phases[k], post_phases[k], abs_tol=1e-6)]
        assert len(changed) > 0, "Retroalimentación no modificó las fases del OVC"


# ══════════════════════════════════════════════════════════════
# TESTS: Singleton behavior
# ══════════════════════════════════════════════════════════════

class TestOrbitalContextSingleton:
    """Verifica que OrbitalContext es un singleton correcto."""

    def test_same_instance(self):
        """Dos instancias deben ser el mismo objeto."""
        ctx1 = OrbitalContext()
        ctx2 = OrbitalContext()
        assert ctx1 is ctx2, "OrbitalContext no es singleton"

    def test_same_ovc_after_reset(self):
        """Después de reset, nueva instancia debe tener OVC nuevo."""
        ctx1 = OrbitalContext()
        ctx1.ovc.create_variable("Test", theta=0.0)

        OrbitalContext._reset()
        ctx2 = OrbitalContext()
        # La nueva instancia debe tener OVC vacío
        assert ctx2.ovc.variable_count == 0

    def test_reset_clears_all_pillars(self):
        """Reset debe limpiar todos los pilares."""
        ctx = OrbitalContext()
        ctx.ovc.create_variable("Test", theta=0.0)
        ctx.rcc.register_cycle_from_names("Cycle", ["Test"])

        OrbitalContext._reset()
        ctx2 = OrbitalContext()
        assert ctx2.ovc.variable_count == 0
        assert len(ctx2.rcc._cycles) == 0
        assert ctx2.engine.tick == 0


# ══════════════════════════════════════════════════════════════
# TESTS: Snapshot y estado
# ══════════════════════════════════════════════════════════════

class TestOrbitalContextState:
    """Verifica que el estado del OrbitalContext es consistente."""

    def test_snapshot_includes_all_pillars(self, ctx):
        """El snapshot debe incluir datos de todos los pilares."""
        snapshot = ctx.get_snapshot()
        assert "ovc_variables" in snapshot
        assert "engine_tick" in snapshot
        assert snapshot["ovc_variables"] == 3

    def test_status_summary_includes_variables(self, ctx):
        """El status summary debe incluir las variables."""
        summary = ctx.status_summary()
        assert "Demanda" in summary
        assert "Precio" in summary
        assert "Oferta" in summary

    def test_repr_shows_state(self, ctx):
        """repr debe mostrar estado actual."""
        r = repr(ctx)
        assert "vars=3" in r
        assert "tick=0" in r


# ══════════════════════════════════════════════════════════════
# TESTS: Thread safety del singleton
# ══════════════════════════════════════════════════════════════

class TestOrbitalContextThreadSafety:
    """Verifica que el singleton es seguro en multihilo."""

    def test_concurrent_creation(self):
        """Múltiples hilos creando OrbitalContext deben obtener la misma instancia."""
        import threading

        instances = []
        lock = threading.Lock()

        def create_instance():
            ctx = OrbitalContext()
            with lock:
                instances.append(id(ctx))

        threads = [threading.Thread(target=create_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Todos deben tener la misma id
        assert len(set(instances)) == 1, (
            f"Singleton thread-unsafe: {len(set(instances))} instancias diferentes"
        )
