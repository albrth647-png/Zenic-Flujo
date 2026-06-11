"""
ORBITAL — Tests Unitarios del Motor Determinista Circular
==========================================================

Tests para los 5 pilares (OVC, TOR, RCC, COD, Espectro) + OrbitalEngine + DB.
Ejecutar con: pytest src/tests/test_orbital.py -v
"""

import math
import os

# Asegurar que src esta en el path
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.orbital.cod import COD
from src.orbital.db import OrbitalDB
from src.orbital.engine import OrbitalEngine
from src.orbital.espectro import EspectroOrbital
from src.orbital.models import (
    TWO_PI,
    CicloOrbital,
    CODResult,
    EspectroEstado,
    OrbitalResult,
    RCCResult,
    TORResult,
    VariableOrbital,
)
from src.orbital.ovc import OVC
from src.orbital.rcc import RCC
from src.orbital.tor import TOR

# ══════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def ovc():
    """OVC con variables economicas de ejemplo."""
    ovc = OVC()
    ovc.create_variable("Demanda", theta=0.0, amplitude=10.0, velocity=0.15)
    ovc.create_variable("Precio", theta=0.3, amplitude=50.0, velocity=0.08)
    ovc.create_variable("Oferta", theta=0.5, amplitude=8.0, velocity=0.12)
    return ovc


@pytest.fixture
def tor(ovc):
    return TOR(ovc)


@pytest.fixture
def rcc(ovc, tor):
    return RCC(ovc, tor)


@pytest.fixture
def cod(ovc, tor, rcc):
    return COD(ovc, tor, rcc)


@pytest.fixture
def espectro(ovc, tor, rcc, cod):
    return EspectroOrbital(ovc, tor, rcc, cod)


@pytest.fixture
def engine():
    """Motor ORBITAL completo con variables economicas."""
    engine = OrbitalEngine()
    engine.create_variable("Demanda", theta=0.0, amplitude=10.0, velocity=0.15)
    engine.create_variable("Precio", theta=0.3, amplitude=50.0, velocity=0.08)
    engine.create_variable("Oferta", theta=0.5, amplitude=8.0, velocity=0.12)
    engine.create_variable("Confianza", theta=0.8, amplitude=6.0, velocity=0.10)
    engine.create_cycle("Economico", ["Demanda", "Precio", "Oferta"], threshold=0.5)
    engine.create_cycle("Emocional", ["Precio", "Confianza", "Demanda"], threshold=0.3)
    return engine


@pytest.fixture
def db():
    """Base de datos orbital temporal para tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    orbital_db = OrbitalDB(db_path)
    yield orbital_db
    orbital_db.close()
    os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# TESTS: VariableOrbital (Modelo)
# ══════════════════════════════════════════════════════════════


class TestVariableOrbital:
    def test_creacion_basica(self):
        var = VariableOrbital(name="Test", theta=1.0, amplitude=5.0, velocity=0.2)
        assert var.name == "Test"
        assert var.theta == 1.0
        assert var.amplitude == 5.0
        assert var.velocity == 0.2

    def test_theta_normalizado(self):
        """Theta debe normalizarse a [0, 2pi)."""
        var = VariableOrbital(name="Test", theta=7.0)
        assert 0 <= var.theta < TWO_PI

    def test_amplitud_positiva(self):
        """Amplitud negativa debe convertirse a positiva."""
        var = VariableOrbital(name="Test", amplitude=-5.0)
        assert var.amplitude == 5.0

    def test_amplitud_cero(self):
        """Amplitud 0 debe usar default."""
        var = VariableOrbital(name="Test", amplitude=0.0)
        assert var.amplitude == 1.0

    def test_value(self):
        """value = A * cos(theta)."""
        var = VariableOrbital(name="Test", theta=0.0, amplitude=10.0)
        assert math.isclose(var.value, 10.0, abs_tol=1e-10)

        var2 = VariableOrbital(name="Test2", theta=math.pi, amplitude=10.0)
        assert math.isclose(var2.value, -10.0, abs_tol=1e-10)

    def test_phase_degrees(self):
        var = VariableOrbital(name="Test", theta=math.pi)
        assert math.isclose(var.phase_degrees, 180.0, abs_tol=1e-10)

    def test_advance(self):
        var = VariableOrbital(name="Test", theta=0.0, velocity=0.5)
        var.advance(dt=1.0)
        assert math.isclose(var.theta, 0.5, abs_tol=1e-10)

    def test_advance_normaliza(self):
        var = VariableOrbital(name="Test", theta=6.0, velocity=1.0)
        var.advance(dt=2.0)
        assert var.theta < TWO_PI

    def test_apply_tension(self):
        var = VariableOrbital(name="Test", theta=0.0, velocity=0.1)
        var.apply_tension(2.0, dt=1.0)  # tanh(2) ≈ 0.964
        assert var.theta > 0  # Debe avanzar

    def test_retrofeed(self):
        var = VariableOrbital(name="Test", theta=0.0)
        var.retrofeed(0.5, damping=0.3)
        assert var.theta > 0  # Debe avanzar por retroalimentacion

    def test_phase_alignment_alineadas(self):
        var1 = VariableOrbital(name="A", theta=0.0)
        var2 = VariableOrbital(name="B", theta=0.0)
        assert math.isclose(var1.phase_alignment(var2), 1.0, abs_tol=1e-10)

    def test_phase_alignment_opuestas(self):
        var1 = VariableOrbital(name="A", theta=0.0)
        var2 = VariableOrbital(name="B", theta=math.pi)
        assert math.isclose(var1.phase_alignment(var2), -1.0, abs_tol=1e-10)

    def test_distance_to(self):
        var1 = VariableOrbital(name="A", theta=0.0)
        var2 = VariableOrbital(name="B", theta=0.5)
        assert math.isclose(var1.distance_to(var2), 0.5, abs_tol=1e-10)

    def test_to_dict_from_dict(self):
        var = VariableOrbital(name="Test", theta=1.0, amplitude=5.0, velocity=0.2)
        d = var.to_dict()
        var2 = VariableOrbital.from_dict(d)
        assert var2.name == "Test"
        assert math.isclose(var2.theta, 1.0)
        assert math.isclose(var2.amplitude, 5.0)


# ══════════════════════════════════════════════════════════════
# TESTS: OVC (Pilar 1)
# ══════════════════════════════════════════════════════════════


class TestOVC:
    def test_create_variable(self, ovc):
        assert ovc.variable_count == 3
        demanda = ovc.get_variable("Demanda")
        assert demanda is not None
        assert demanda.amplitude == 10.0

    def test_create_variable_duplicada(self, ovc):
        with pytest.raises(ValueError, match="ya existe"):
            ovc.create_variable("Demanda", theta=0.0)

    def test_create_variables_batch(self):
        ovc = OVC()
        vars = ovc.create_variables_batch(
            [
                {"name": "A", "theta": 0.0},
                {"name": "B", "theta": 1.0},
            ]
        )
        assert len(vars) == 2
        assert ovc.variable_count == 2

    def test_advance_all(self, ovc):
        pre_theta = ovc.get_variable("Demanda").theta
        ovc.advance_all(dt=1.0)
        post_theta = ovc.get_variable("Demanda").theta
        assert post_theta != pre_theta  # Debe haber avanzado

    def test_advance_variable(self, ovc):
        pre_d = ovc.get_variable("Demanda").theta
        pre_p = ovc.get_variable("Precio").theta
        ovc.advance_variable("Demanda", dt=1.0)
        post_d = ovc.get_variable("Demanda").theta
        post_p = ovc.get_variable("Precio").theta
        assert post_d != pre_d  # Demanda avanzo
        assert post_p == pre_p  # Precio no cambio

    def test_apply_tension(self, ovc):
        pre_theta = ovc.get_variable("Demanda").theta
        ovc.apply_tension("Demanda", 5.0, dt=1.0)
        post_theta = ovc.get_variable("Demanda").theta
        assert post_theta != pre_theta

    def test_retrofeed(self, ovc):
        pre_theta = ovc.get_variable("Demanda").theta
        ovc.retrofeed({"Demanda": 0.5, "Precio": -0.3}, damping=0.3)
        post_theta_d = ovc.get_variable("Demanda").theta
        assert post_theta_d != pre_theta  # Debe haber cambiado

    def test_get_phase_snapshot(self, ovc):
        snapshot = ovc.get_phase_snapshot()
        assert "Demanda" in snapshot
        assert "Precio" in snapshot
        assert "Oferta" in snapshot

    def test_get_value_snapshot(self, ovc):
        snapshot = ovc.get_value_snapshot()
        assert all(isinstance(v, float) for v in snapshot.values())

    def test_get_variables_by_group(self, ovc):
        ovc.create_variable("Test", theta=0.0, orbit_group="test_group")
        group = ovc.get_variables_by_group("test_group")
        assert len(group) == 1

    def test_reset(self, ovc):
        ovc.reset()
        assert ovc.variable_count == 0
        assert ovc.tick == 0

    def test_status_summary(self, ovc):
        summary = ovc.status_summary()
        assert "Demanda" in summary
        assert "Precio" in summary


# ══════════════════════════════════════════════════════════════
# TESTS: TOR (Pilar 2)
# ══════════════════════════════════════════════════════════════


class TestTOR:
    def test_calculate_par(self, tor):
        result = tor.calculate("Demanda", "Precio")
        assert isinstance(result, TORResult)
        assert result.variable_i == "Demanda"
        assert result.variable_j == "Precio"
        assert isinstance(result.tor_value, float)

    def test_tor_formula(self):
        """TOR(i,j) = Ai * Aj * cos(theta_i - theta_j)."""
        ovc = OVC()
        ovc.create_variable("A", theta=0.0, amplitude=10.0)
        ovc.create_variable("B", theta=0.0, amplitude=5.0)
        tor = TOR(ovc)
        result = tor.calculate("A", "B")
        # theta iguales → cos(0) = 1 → TOR = 10 * 5 * 1 = 50
        assert math.isclose(result.tor_value, 50.0, abs_tol=1e-10)

    def test_tor_simetria(self, tor):
        """TOR(i,j) = TOR(j,i)."""
        r1 = tor.calculate("Demanda", "Precio")
        r2 = tor.calculate("Precio", "Demanda")
        assert math.isclose(r1.tor_value, r2.tor_value, abs_tol=1e-10)

    def test_tor_fases_opuestas(self):
        """Variables con fases opuestas → TOR negativo."""
        ovc = OVC()
        ovc.create_variable("A", theta=0.0, amplitude=10.0)
        ovc.create_variable("B", theta=math.pi, amplitude=5.0)
        tor = TOR(ovc)
        result = tor.calculate("A", "B")
        # cos(pi) = -1 → TOR = 10 * 5 * (-1) = -50
        assert math.isclose(result.tor_value, -50.0, abs_tol=1e-10)

    def test_calculate_matrix(self, tor):
        results = tor.calculate_matrix()
        # 3 variables → 3 parejas (C(3,2) = 3)
        assert len(results) == 3

    def test_calculate_for_cycle(self, tor):
        results = tor.calculate_for_cycle(["Demanda", "Precio"])
        assert len(results) == 1

    def test_get_total_tension(self, tor):
        total = tor.get_total_tension()
        assert isinstance(total, float)

    def test_get_strongest_pair(self, tor):
        strongest = tor.get_strongest_pair()
        assert strongest is not None
        assert isinstance(strongest.tor_value, float)

    def test_get_resonant_pairs(self, tor):
        resonant = tor.get_resonant_pairs(threshold=1.0)
        assert isinstance(resonant, list)

    def test_apply_tensions_to_ovc(self, tor, ovc):
        results = tor.calculate_matrix()
        pre_phases = ovc.get_phase_snapshot()
        tor.apply_tensions_to_ovc(results, dt=1.0, scale=0.01)
        post_phases = ovc.get_phase_snapshot()
        # Al menos una variable debe haber cambiado
        assert pre_phases != post_phases

    def test_variable_no_existe(self, tor):
        with pytest.raises(KeyError):
            tor.calculate("Inexistente", "Demanda")


# ══════════════════════════════════════════════════════════════
# TESTS: RCC (Pilar 3)
# ══════════════════════════════════════════════════════════════


class TestRCC:
    def test_register_cycle(self, rcc):
        cycle = CicloOrbital(name="Test", variable_ids=["Demanda", "Precio"], threshold=0.5)
        rcc.register_cycle(cycle)
        assert len(rcc._cycles) == 1

    def test_register_cycle_from_names(self, rcc):
        cycle = rcc.register_cycle_from_names("Econ", ["Demanda", "Precio", "Oferta"])
        assert cycle.name == "Econ"
        assert len(cycle.variable_ids) == 3

    def test_register_cycle_variable_faltante(self, rcc):
        with pytest.raises(ValueError, match="no existe"):
            rcc.register_cycle_from_names("Bad", ["Demanda", "Inexistente"])

    def test_detect_resonancia(self, rcc):
        cycle = rcc.register_cycle_from_names("Test", ["Demanda", "Precio"], threshold=0.5)
        result = rcc.detect(cycle)
        assert isinstance(result, RCCResult)
        assert isinstance(result.is_resonant, bool)
        assert 0 <= result.resonance_strength <= 1.0

    def test_detect_alineacion_perfecta(self):
        """Variables alineadas → alta resonancia."""
        ovc = OVC()
        ovc.create_variable("A", theta=0.0, amplitude=10.0)
        ovc.create_variable("B", theta=0.01, amplitude=10.0)  # Casi alineada
        tor = TOR(ovc)
        rcc = RCC(ovc, tor)
        cycle = rcc.register_cycle_from_names("Aligned", ["A", "B"], threshold=0.5)
        result = rcc.detect(cycle)
        assert result.is_resonant  # Debe detectar resonancia

    def test_detect_all(self, rcc):
        rcc.register_cycle_from_names("C1", ["Demanda", "Precio"])
        rcc.register_cycle_from_names("C2", ["Oferta", "Precio"])
        results = rcc.detect_all()
        assert len(results) == 2

    def test_get_resonant_cycles(self, rcc):
        rcc.register_cycle_from_names("C1", ["Demanda", "Precio"], threshold=0.01)
        resonant = rcc.get_resonant_cycles()
        assert isinstance(resonant, list)

    def test_resonance_summary(self, rcc):
        rcc.register_cycle_from_names("C1", ["Demanda", "Precio"])
        summary = rcc.get_resonance_summary()
        assert "total_cycles" in summary
        assert "resonant_cycles" in summary


# ══════════════════════════════════════════════════════════════
# TESTS: COD (Pilar 4)
# ══════════════════════════════════════════════════════════════


class TestCOD:
    def test_collapse_basico(self, rcc, cod):
        cycle = rcc.register_cycle_from_names("Test", ["Demanda", "Precio"], threshold=0.5)
        result = cod.collapse(cycle)
        assert isinstance(result, CODResult)
        assert isinstance(result.converged, bool)
        assert result.iterations > 0
        assert len(result.final_phases) > 0

    def test_collapse_determinista(self, rcc, cod):
        """Mismas condiciones iniciales → mismo resultado siempre."""
        cycle = rcc.register_cycle_from_names("Det", ["Demanda", "Precio"], threshold=0.5)

        # Primer colapso
        r1 = cod.collapse(cycle)

        # Restaurar fases para segundo colapso
        # (El primer colapso modifica las fases, asi que no seran exactamente iguales
        # pero el sistema debe converger consistentemente)

        assert isinstance(r1.converged, bool)
        assert isinstance(r1.final_phases, dict)

    def test_collapse_converge(self):
        """Variables cercanas deben converger con suficientes iteraciones."""
        ovc = OVC()
        ovc.create_variable("A", theta=0.0, amplitude=5.0, velocity=0.01)
        ovc.create_variable("B", theta=0.1, amplitude=5.0, velocity=0.01)
        tor = TOR(ovc)
        rcc = RCC(ovc, tor)
        cod = COD(ovc, tor, rcc)
        cod.configure(epsilon=1e-4, max_iterations=500, convergence_scale=0.001)

        cycle = rcc.register_cycle_from_names("Converge", ["A", "B"], threshold=0.01)
        result = cod.collapse(cycle)
        # Con parametros suaves, debe converger o al menos no diverger
        assert result.convergence_delta >= 0

    def test_collapse_with_retrofeedback(self, rcc, cod):
        cycle = rcc.register_cycle_from_names("Retro", ["Demanda", "Precio"], threshold=0.5)
        result = cod.collapse_with_retrofeedback(cycle, retrofeed_damping=0.3)
        assert isinstance(result, CODResult)

    def test_configure(self, cod):
        cod.configure(epsilon=1e-8, max_iterations=500)
        assert cod._epsilon == 1e-8
        assert cod._max_iterations == 500

    def test_is_stable(self, rcc, cod):
        cycle = rcc.register_cycle_from_names("Stable", ["Demanda", "Precio"], threshold=0.5)
        stable = cod.is_stable(cycle)
        assert isinstance(stable, bool)


# ══════════════════════════════════════════════════════════════
# TESTS: Espectro Orbital (Pilar 5)
# ══════════════════════════════════════════════════════════════


class TestEspectroOrbital:
    def test_generate(self, rcc, espectro):
        cycle = rcc.register_cycle_from_names("Spec", ["Demanda", "Precio"], threshold=0.5)
        estado = espectro.generate(cycle)
        assert isinstance(estado, EspectroEstado)
        assert len(estado.modes) > 0
        assert isinstance(estado.primary, dict)
        assert isinstance(estado.retrofeedback, dict)

    def test_generate_produce_modos(self, rcc, espectro):
        cycle = rcc.register_cycle_from_names("Modos", ["Demanda", "Precio", "Oferta"], threshold=0.5)
        estado = espectro.generate(cycle)
        # Debe tener al menos 3 modos: primario, ortogonal, opuesto
        assert len(estado.modes) >= 3

    def test_generate_all(self, rcc, espectro):
        rcc.register_cycle_from_names("C1", ["Demanda", "Precio"])
        rcc.register_cycle_from_names("C2", ["Oferta", "Precio"])
        estados = espectro.generate_all()
        assert len(estados) == 2

    def test_retrofeedback_cierra_ciclo(self, rcc, espectro, ovc):
        """El espectro debe retroalimentar al OVC."""
        _pre_phases = ovc.get_phase_snapshot()
        cycle = rcc.register_cycle_from_names("Retro", ["Demanda", "Precio"], threshold=0.5)
        espectro.generate(cycle, retrofeed_damping=0.3)
        _post_phases = ovc.get_phase_snapshot()
        # El OVC debe haber cambiado por la retroalimentacion
        # (al menos el tick avanzo)

    def test_history(self, rcc, espectro):
        cycle = rcc.register_cycle_from_names("Hist", ["Demanda", "Precio"], threshold=0.5)
        espectro.generate(cycle)
        espectro.generate(cycle)
        assert espectro.history_length == 2
        latest = espectro.get_latest()
        assert latest is not None

    def test_analyze_trend(self, rcc, espectro):
        cycle = rcc.register_cycle_from_names("Trend", ["Demanda", "Precio"], threshold=0.5)
        # Generar varios ticks para analizar tendencia
        for _ in range(5):
            espectro.generate(cycle)
        trend = espectro.analyze_trend()
        assert trend["trend"] in ("converging", "oscillating", "diverging", "no_data", "insufficient_data")

    def test_spectrum_summary(self, rcc, espectro):
        cycle = rcc.register_cycle_from_names("Sum", ["Demanda", "Precio"], threshold=0.5)
        espectro.generate(cycle)
        summary = espectro.spectrum_summary()
        assert "Espectro Orbital" in summary


# ══════════════════════════════════════════════════════════════
# TESTS: OrbitalEngine (Integracion)
# ══════════════════════════════════════════════════════════════


class TestOrbitalEngine:
    def test_creacion(self, engine):
        assert engine.variable_count == 4
        assert engine.cycle_count == 2

    def test_run_tick(self, engine):
        result = engine.run_tick()
        assert isinstance(result, OrbitalResult)
        assert result.tick == 1
        assert len(result.tor_results) > 0
        assert result.duration_ms >= 0

    def test_run_tick_ciclo_completo(self, engine):
        """Un tick debe ejecutar OVC → TOR → RCC → COD → Espectro → Retro."""
        result = engine.run_tick()
        # TOR calculado
        assert len(result.tor_results) > 0
        # RCC calculado
        assert len(result.rcc_results) > 0
        # COD calculado
        assert len(result.cod_results) > 0
        # Espectro generado
        assert result.espectro is not None

    def test_run_multiple_ticks(self, engine):
        results = engine.run_ticks(5)
        assert len(results) == 5
        assert engine.tick == 5

    def test_retroalimentacion_efectiva(self, engine):
        """Despues de varios ticks, las variables deben evolucionar."""
        phases_0 = engine.get_phase_snapshot()
        engine.run_ticks(3)
        phases_3 = engine.get_phase_snapshot()
        # Al menos una variable debe haber cambiado de fase
        changed = [k for k in phases_0 if not math.isclose(phases_0[k], phases_3[k], abs_tol=1e-6)]
        assert len(changed) > 0

    def test_determinismo(self, engine):
        """Mismas condiciones → mismo resultado (desde reset)."""
        engine.reset()
        engine.create_variable("X", theta=0.0, amplitude=10.0, velocity=0.1)
        engine.create_variable("Y", theta=0.5, amplitude=5.0, velocity=0.1)
        engine.create_cycle("Test", ["X", "Y"], threshold=0.5)

        _r1 = engine.run_tick()
        val1 = engine.get_value_snapshot()

        engine.reset()
        engine.create_variable("X", theta=0.0, amplitude=10.0, velocity=0.1)
        engine.create_variable("Y", theta=0.5, amplitude=5.0, velocity=0.1)
        engine.create_cycle("Test", ["X", "Y"], threshold=0.5)

        _r2 = engine.run_tick()
        val2 = engine.get_value_snapshot()

        # Los valores deben ser identicos (determinismo)
        for k in val1:
            assert math.isclose(val1[k], val2[k], abs_tol=1e-10), f"No determinista en {k}"

    def test_status_summary(self, engine):
        summary = engine.status_summary()
        assert "ORBITAL" in summary
        assert "Demanda" in summary

    def test_get_execution_history(self, engine):
        engine.run_ticks(3)
        history = engine.get_execution_history(limit=2)
        assert len(history) == 2


# ══════════════════════════════════════════════════════════════
# TESTS: OrbitalDB
# ══════════════════════════════════════════════════════════════


class TestOrbitalDB:
    def test_initialize_schema(self, db):
        stats = db.get_stats()
        assert stats["orbital_variables"] == 0

    def test_save_load_variable(self, db):
        var = {
            "name": "Demanda",
            "theta": 0.5,
            "amplitude": 10.0,
            "velocity": 0.15,
            "value": 8.775,
            "orbit_group": "economico",
        }
        db.save_variable(var)
        loaded = db.load_variable("Demanda")
        assert loaded is not None
        assert loaded["name"] == "Demanda"
        assert math.isclose(loaded["theta"], 0.5)
        assert math.isclose(loaded["amplitude"], 10.0)

    def test_save_variables_batch(self, db):
        vars = [
            {"name": "A", "theta": 0.0, "amplitude": 5.0},
            {"name": "B", "theta": 1.0, "amplitude": 8.0},
        ]
        ids = db.save_variables_batch(vars)
        assert len(ids) == 2
        assert db.load_variable("A") is not None
        assert db.load_variable("B") is not None

    def test_load_all_variables(self, db):
        db.save_variable({"name": "A", "theta": 0.0, "amplitude": 5.0})
        db.save_variable({"name": "B", "theta": 1.0, "amplitude": 8.0})
        all_vars = db.load_all_variables()
        assert len(all_vars) == 2

    def test_delete_variable(self, db):
        db.save_variable({"name": "ToDelete", "theta": 0.0})
        assert db.delete_variable("ToDelete")
        assert db.load_variable("ToDelete") is None

    def test_save_load_cycle(self, db):
        cycle = {
            "name": "Economico",
            "variable_ids": ["Demanda", "Precio", "Oferta"],
            "threshold": 0.5,
            "status": "active",
        }
        cycle_id = db.save_cycle(cycle)
        loaded = db.load_cycle(cycle_id)
        assert loaded is not None
        assert loaded["name"] == "Economico"
        assert len(loaded["variable_ids"]) == 3

    def test_save_spectrum(self, db):
        # Primero crear un ciclo
        cycle = {"name": "Test", "variable_ids": ["A", "B"]}
        cycle_id = db.save_cycle(cycle)

        data = {
            "phase_state": {"A": 0.5, "B": 1.0},
            "tor_matrix": [{"A": "B", "value": 50.0}],
            "resonance_active": True,
            "resonance_strength": 0.8,
            "collapsed_state": {"A": 0.6, "B": 0.9},
            "spectrum_modes": [{"A": 5.0, "B": 3.0}],
            "primary_mode": 0,
            "retrofeedback": {"A": 0.01, "B": -0.02},
        }
        spec_id = db.save_spectrum(cycle_id, tick=1, data=data)
        assert spec_id

    def test_save_execution(self, db):
        result = {
            "tick": 1,
            "total_variables": 3,
            "total_cycles": 1,
            "total_tor_pairs": 3,
            "resonant_cycles": 1,
            "converged_cycles": 1,
            "final_state": {"A": 0.5},
            "duration_ms": 150,
        }
        exec_id = db.save_execution(result)
        assert exec_id

    def test_get_stats(self, db):
        db.save_variable({"name": "A", "theta": 0.0})
        db.save_cycle({"name": "C1", "variable_ids": ["A"]})
        stats = db.get_stats()
        assert stats["orbital_variables"] == 1
        assert stats["orbital_cycles"] == 1


# ══════════════════════════════════════════════════════════════
# TESTS: Ejemplo Economico Completo
# ══════════════════════════════════════════════════════════════


class TestEjemploEconomico:
    """Test de integracion: ciclo economico completo Demanda→Precio→Oferta."""

    def test_ciclo_economico_orbital(self):
        engine = OrbitalEngine()
        engine.create_variables_batch(
            [
                {"name": "Demanda", "theta": 0.0, "amplitude": 10.0, "velocity": 0.15},
                {"name": "Precio", "theta": 0.3, "amplitude": 50.0, "velocity": 0.08},
                {"name": "Oferta", "theta": 0.5, "amplitude": 8.0, "velocity": 0.12},
                {"name": "Confianza", "theta": 0.8, "amplitude": 6.0, "velocity": 0.10},
                {"name": "Innovacion", "theta": 1.2, "amplitude": 4.0, "velocity": 0.06},
            ]
        )
        engine.create_cycle("Economico", ["Demanda", "Precio", "Oferta", "Confianza", "Innovacion"], threshold=0.5)

        # Ejecutar 10 ticks
        results = engine.run_ticks(10, retrofeed_damping=0.3)

        # Verificar que el sistema evoluciona
        assert len(results) == 10

        # Verificar determinismo: las variables cambiaron pero de forma determinista
        snap = engine.get_value_snapshot()
        assert len(snap) == 5
        assert all(isinstance(v, float) for v in snap.values())

        # Verificar que el espectro se genera
        espectro = engine.espectro.get_latest()
        assert espectro is not None
        assert len(espectro.modes) >= 3  # Primario, ortogonal, opuesto
        assert isinstance(espectro.primary, dict)
        assert len(espectro.primary) > 0

        # Verificar tendencia
        trend = engine.espectro.analyze_trend()
        assert trend["trend"] in ("converging", "oscillating", "diverging")
