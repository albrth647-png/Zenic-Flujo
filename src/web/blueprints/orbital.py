"""
Blueprints — ORBITAL API (Espectro Orbital)

Rutas para el motor circular determinista ORBITAL:
- /api/orbital/status → Estado completo (variables, TOR, RCC, COD, cache)
- /api/orbital/tick    → Ejecutar un tick orbital
- /api/orbital/variable → CRUD de variables orbitales
- /api/orbital/cycle   → CRUD de ciclos orbitales
- /api/orbital/reset   → Reset del motor
"""

from flask import Blueprint, jsonify, request

from src.orbital.context import OrbitalContext
from src.web.helpers import login_required

bp = Blueprint("orbital", __name__)


def _get_engine():
    """Obtiene el motor ORBITAL compartido desde el contexto global."""
    ctx = OrbitalContext()
    return ctx.engine


# ── Status ────────────────────────────────────────────────────

@bp.route("/api/orbital/status", methods=["GET"])
@login_required
def api_orbital_status():
    """Retorna el estado completo del sistema ORBITAL."""
    engine = _get_engine()

    variables = {}
    for name, v in engine.get_all_variables().items():
        variables[name] = {
            "theta": v.theta,
            "amplitude": v.amplitude,
            "velocity": v.velocity,
            "value": getattr(v, "value", 0.0),
            "orbit_group": getattr(v, "orbit_group", "default"),
        }

    tor_results = []
    if hasattr(engine.tor, "_cache"):
        cache = engine.tor._cache
        tor_cache = {
            "hits": getattr(cache, "hits", 0),
            "misses": getattr(cache, "misses", 0),
            "cache_size": len(getattr(cache, "_cache", {})),
            "hit_rate": getattr(cache, "hit_rate", 0.0),
        }
        for entry in getattr(cache, "_cache", {}).values():
            if isinstance(entry, dict):
                tor_results.append({
                    "variable_i": entry.get("i", ""),
                    "variable_j": entry.get("j", ""),
                    "tor_value": entry.get("value", 0.0),
                    "alignment": entry.get("alignment", 0.0),
                })
    else:
        tor_cache = {"hits": 0, "misses": 0, "cache_size": 0, "hit_rate": 0.0}
        # Try TOR matrix
        if hasattr(engine.tor, "calculate_matrix"):
            try:
                matrix = engine.tor.calculate_matrix()
                for r in matrix[:20]:
                    if hasattr(r, "to_dict"):
                        tor_results.append(r.to_dict())
                    elif isinstance(r, dict):
                        tor_results.append(r)
            except Exception:
                pass

    # RCC results
    rcc_results = []
    if hasattr(engine.rcc, "_cycles"):
        for cycle_id, cycle in engine.rcc._cycles.items():
            try:
                result = engine.rcc.detect(cycle) if hasattr(engine.rcc, "detect") else None
                if result:
                    rcc_results.append({
                        "cycle_id": cycle_id,
                        "cycle_name": getattr(cycle, "name", cycle_id),
                        "is_resonant": getattr(result, "is_resonant", False),
                        "strength": getattr(result, "strength", 0.0),
                    })
                else:
                    rcc_results.append({
                        "cycle_id": cycle_id,
                        "cycle_name": getattr(cycle, "name", cycle_id),
                        "is_resonant": False,
                        "strength": 0.0,
                    })
            except Exception:
                pass

    # COD results
    cod_results = []
    if hasattr(engine.rcc, "_cycles"):
        for cycle_id, cycle in engine.rcc._cycles.items():
            try:
                result = engine.cod.collapse(cycle)
                cod_results.append({
                    "cycle_id": cycle_id,
                    "converged": getattr(result, "converged", False),
                    "iterations": getattr(result, "iterations", 0),
                    "convergence_delta": getattr(result, "convergence_delta", 0.0),
                })
            except Exception:
                pass

    # Execution history summary
    history = engine.get_execution_history(5)
    history_summary = []
    for h in history:
        if hasattr(h, "to_dict"):
            d = h.to_dict()
        elif isinstance(h, dict):
            d = h
        else:
            d = {"tick": getattr(h, "tick", 0), "duration_ms": getattr(h, "duration_ms", 0)}
        history_summary.append({
            "tick": d.get("tick", 0),
            "duration_ms": d.get("duration_ms", 0),
            "variables": len(d.get("variables", {})),
        })

    return jsonify({
        "variables": variables,
        "tor": tor_results[:30],
        "tor_cache": tor_cache,
        "rcc": rcc_results,
        "cod": cod_results,
        "tick": engine.tick,
        "variable_count": engine.variable_count,
        "cycle_count": engine.cycle_count,
        "history": history_summary,
    })


# ── Tick ──────────────────────────────────────────────────────

@bp.route("/api/orbital/tick", methods=["POST"])
@login_required
def api_orbital_tick():
    """Ejecuta un tick orbital completo."""
    engine = _get_engine()
    try:
        result = engine.run_tick()
        return jsonify({
            "status": "ok",
            "tick": result.tick,
            "duration_ms": result.duration_ms,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ── Variable ──────────────────────────────────────────────────

@bp.route("/api/orbital/variable", methods=["POST"])
@login_required
def api_orbital_create_variable():
    """Crea una variable orbital."""
    engine = _get_engine()
    data = request.get_json() or {}
    name = data.get("name", "")
    if not name:
        return jsonify({"error": "name es requerido"}), 400
    try:
        var = engine.create_variable(
            name=name,
            theta=float(data.get("theta", 0.0)),
            amplitude=float(data.get("amplitude", 10.0)),
            velocity=float(data.get("velocity", 0.1)),
            orbit_group=data.get("orbit_group", "default"),
        )
        return jsonify({"status": "created", "name": var.name, "theta": var.theta}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/orbital/variable/<name>", methods=["DELETE"])
@login_required
def api_orbital_delete_variable(name):
    """Elimina una variable orbital."""
    engine = _get_engine()
    if hasattr(engine.ovc, "delete_variable"):
        engine.ovc.delete_variable(name)
        return jsonify({"status": "deleted"})
    return jsonify({"error": "No soportado"}), 400


# ── Cycle ─────────────────────────────────────────────────────

@bp.route("/api/orbital/cycle", methods=["POST"])
@login_required
def api_orbital_create_cycle():
    """Crea un ciclo orbital cerrado."""
    engine = _get_engine()
    data = request.get_json() or {}
    name = data.get("name", "")
    variables = data.get("variables", [])
    threshold = float(data.get("threshold", 0.5))
    if not name or not variables:
        return jsonify({"error": "name y variables son requeridos"}), 400
    try:
        cycle = engine.create_cycle(name, variables, threshold)
        return jsonify({"status": "created", "cycle_id": cycle.id, "name": cycle.name}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Reset ─────────────────────────────────────────────────────

@bp.route("/api/orbital/reset", methods=["POST"])
@login_required
def api_orbital_reset():
    """Resetea el motor ORBITAL."""
    engine = _get_engine()
    engine.reset()
    return jsonify({"status": "reset", "tick": 0})
