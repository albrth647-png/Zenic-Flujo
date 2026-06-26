"""
ORBITAL — Database Schema & Operations
========================================

Esquema de base de datos para el motor ORBITAL.
Anade 4 tablas nuevas a la base de datos existente de Zenic-Flijo:

1. orbital_variables: Variables orbitales con fase, amplitud, velocidad
2. orbital_cycles: Ciclos cerrados con umbral de resonancia
3. orbital_spectrum: Estados del espectro por tick
4. orbital_executions: Historial de ejecuciones orbitales

Estas tablas conviven con las tablas lineales existentes,
permitiendo una migracion gradual (FASE 2).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.logging import setup_logging

logger = setup_logging(__name__)

# ── Esquema SQL ────────────────────────────────────────────

ORBITAL_SCHEMA = """
-- ============================================================
-- ORBITAL — Esquema de Base de Datos
-- Motor Determinista Circular: 4 tablas nuevas
-- ============================================================

-- Variables Orbitales (OVC)
-- UNIQUE compuesto (workflow_id, name): dos workflows pueden tener
-- variables con el mismo nombre (ej: "step_1_notification") sin pisarse.
-- Fix bug Sprint 1 #5: antes era UNIQUE(name) sola, lo que causaba
-- INSERT OR REPLACE y pérdida de variables entre workflows.
CREATE TABLE IF NOT EXISTS orbital_variables (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    workflow_id TEXT NOT NULL DEFAULT '__global__',
    theta REAL NOT NULL DEFAULT 0.0,
    amplitude REAL NOT NULL DEFAULT 1.0,
    velocity REAL NOT NULL DEFAULT 0.1,
    value REAL NOT NULL DEFAULT 1.0,
    orbit_group TEXT NOT NULL DEFAULT 'default',
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(workflow_id, name)
);

-- Ciclos Orbitales (RCC)
CREATE TABLE IF NOT EXISTS orbital_cycles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    variable_ids TEXT NOT NULL DEFAULT '[]',
    threshold REAL NOT NULL DEFAULT 0.5,
    status TEXT DEFAULT 'active',
    resonance_level REAL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Espectro Orbital por tick
CREATE TABLE IF NOT EXISTS orbital_spectrum (
    id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    phase_state TEXT NOT NULL DEFAULT '{}',
    tor_matrix TEXT NOT NULL DEFAULT '[]',
    resonance_active INTEGER DEFAULT 0,
    resonance_strength REAL DEFAULT 0.0,
    collapsed_state TEXT DEFAULT '{}',
    spectrum_modes TEXT DEFAULT '[]',
    primary_mode INTEGER DEFAULT 0,
    retrofeedback TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (cycle_id) REFERENCES orbital_cycles(id) ON DELETE CASCADE
);

-- Ejecuciones Orbitales (historial)
CREATE TABLE IF NOT EXISTS orbital_executions (
    id TEXT PRIMARY KEY,
    tick INTEGER NOT NULL,
    total_variables INTEGER NOT NULL DEFAULT 0,
    total_cycles INTEGER NOT NULL DEFAULT 0,
    total_tor_pairs INTEGER NOT NULL DEFAULT 0,
    resonant_cycles INTEGER NOT NULL DEFAULT 0,
    converged_cycles INTEGER NOT NULL DEFAULT 0,
    final_state TEXT DEFAULT '{}',
    duration_ms INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_orbital_variables_group ON orbital_variables(orbit_group);
CREATE INDEX IF NOT EXISTS idx_orbital_variables_name ON orbital_variables(name);
CREATE INDEX IF NOT EXISTS idx_orbital_variables_workflow ON orbital_variables(workflow_id, name);
CREATE INDEX IF NOT EXISTS idx_orbital_spectrum_cycle ON orbital_spectrum(cycle_id, tick);
CREATE INDEX IF NOT EXISTS idx_orbital_executions_tick ON orbital_executions(tick);
"""

# Migración para DBs existentes: añadir columna workflow_id si no existe.
# Se ejecuta tras initialize_schema() de forma idempotente.
_ORBITAL_MIGRATION_ADD_WORKFLOW_ID = [
    # SQLite no soporta "ADD COLUMN IF NOT EXISTS", se usa PRAGMA para check
    "ALTER TABLE orbital_variables ADD COLUMN workflow_id TEXT NOT NULL DEFAULT '__global__'",
]


class OrbitalDB:
    """
    Base de datos ORBITAL — Operaciones CRUD para las tablas orbitales.

    Convive con la base de datos lineal existente, anadiendo
    las tablas orbitales en la misma base SQLite.
    """

    def __init__(self, db_path: str | None = None):
        """
        Inicializa la conexion a la base de datos orbital.

        Args:
            db_path: Ruta al archivo SQLite. Si es None, usa la config global.
        """
        if db_path is None:
            from src.core.config import DB_PATH

            db_path = DB_PATH

        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_connection(self) -> sqlite3.Connection:
        """Obtiene o crea la conexion a la base de datos."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self.initialize_schema()
        return self._conn

    def initialize_schema(self) -> None:
        """Crea las tablas orbitales si no existen + aplica migraciones idempotentes."""
        conn = self._get_connection()
        conn.executescript(ORBITAL_SCHEMA)

        # Migración idempotente: añadir workflow_id si la DB pre-existe sin esa columna.
        # Fix bug Sprint 1 #5: UNIQUE(name) → UNIQUE(workflow_id, name).
        cols = [row[1] for row in conn.execute("PRAGMA table_info(orbital_variables)").fetchall()]
        if "workflow_id" not in cols:
            try:
                conn.execute(
                    "ALTER TABLE orbital_variables ADD COLUMN workflow_id TEXT NOT NULL DEFAULT '__global__'"
                )
                # El UNIQUE compuesto no se puede añadir con ALTER en SQLite; se crea vía
                # CREATE UNIQUE INDEX IF NOT EXISTS que es equivalente para validación.
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_orbital_variables_workflow_name "
                    "ON orbital_variables(workflow_id, name)"
                )
                logger.info("OrbitalDB: migración workflow_id aplicada")
            except sqlite3.OperationalError as e:
                # "duplicate column name" si ya existe — ignorar
                if "duplicate column" not in str(e):
                    raise

        conn.commit()
        logger.info("OrbitalDB: Esquema inicializado")

    # ── Variables Orbitales (OVC) ──────────────────────────

    def save_variable(self, var: dict[str, Any], workflow_id: str = "__global__") -> str:
        """
        Guarda una variable orbital en la base de datos.

        Usa UNIQUE(workflow_id, name) para que dos workflows puedan tener
        variables con el mismo nombre sin pisarse. Fix bug Sprint 1 #5.

        Args:
            var: Diccionario con los datos de la variable (de VariableOrbital.to_dict())
            workflow_id: ID del workflow dueño de la variable. Default '__global__'
                para variables globales no asociadas a un workflow específico.

        Returns:
            ID de la variable
        """
        conn = self._get_connection()
        var_id = var.get("id", str(uuid.uuid4()))

        conn.execute(
            """
            INSERT OR REPLACE INTO orbital_variables
            (id, name, workflow_id, theta, amplitude, velocity, value, orbit_group, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                var_id,
                var.get("name", ""),
                workflow_id,
                var.get("theta", 0.0),
                var.get("amplitude", 1.0),
                var.get("velocity", 0.1),
                var.get("value", 1.0),
                var.get("orbit_group", "default"),
                json.dumps(var.get("metadata", {})),
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
        return var_id

    def save_variables_batch(self, variables: list[dict[str, Any]]) -> list[str]:
        """Guarda multiples variables orbitales de una vez."""
        ids = []
        for var in variables:
            vid = self.save_variable(var)
            ids.append(vid)
        return ids

    def load_variable(self, name: str) -> dict[str, Any] | None:
        """Carga una variable orbital por nombre."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM orbital_variables WHERE name = ?", (name,)).fetchone()
        if row:
            return dict(row)
        return None

    def load_all_variables(self) -> list[dict[str, Any]]:
        """Carga todas las variables orbitales."""
        conn = self._get_connection()
        rows = conn.execute("SELECT * FROM orbital_variables ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def delete_variable(self, name: str) -> bool:
        """Elimina una variable orbital."""
        conn = self._get_connection()
        cursor = conn.execute("DELETE FROM orbital_variables WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0

    # ── Ciclos Orbitales (RCC) ─────────────────────────────

    def save_cycle(self, cycle: dict[str, Any]) -> str:
        """Guarda un ciclo orbital en la base de datos."""
        conn = self._get_connection()
        cycle_id = cycle.get("id", str(uuid.uuid4()))

        conn.execute(
            """
            INSERT OR REPLACE INTO orbital_cycles
            (id, name, variable_ids, threshold, status, resonance_level, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                cycle_id,
                cycle.get("name", ""),
                json.dumps(cycle.get("variable_ids", [])),
                cycle.get("threshold", 0.5),
                cycle.get("status", "active"),
                cycle.get("resonance_level", 0.0),
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
        return cycle_id

    def load_cycle(self, cycle_id: str) -> dict[str, Any] | None:
        """Carga un ciclo orbital por ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM orbital_cycles WHERE id = ?", (cycle_id,)).fetchone()
        if row:
            result = dict(row)
            result["variable_ids"] = json.loads(result.get("variable_ids", "[]"))
            return result
        return None

    def load_all_cycles(self) -> list[dict[str, Any]]:
        """Carga todos los ciclos orbitales."""
        conn = self._get_connection()
        rows = conn.execute("SELECT * FROM orbital_cycles ORDER BY name").fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["variable_ids"] = json.loads(d.get("variable_ids", "[]"))
            results.append(d)
        return results

    # ── Espectro Orbital ───────────────────────────────────

    def save_spectrum(self, cycle_id: str, tick: int, data: dict[str, Any]) -> str:
        """Guarda un estado del espectro orbital."""
        conn = self._get_connection()
        spec_id = str(uuid.uuid4())

        conn.execute(
            """
            INSERT INTO orbital_spectrum
            (id, cycle_id, tick, phase_state, tor_matrix, resonance_active,
             resonance_strength, collapsed_state, spectrum_modes, primary_mode,
             retrofeedback, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                spec_id,
                cycle_id,
                tick,
                json.dumps(data.get("phase_state", {})),
                json.dumps(data.get("tor_matrix", [])),
                1 if data.get("resonance_active", False) else 0,
                data.get("resonance_strength", 0.0),
                json.dumps(data.get("collapsed_state", {})),
                json.dumps(data.get("spectrum_modes", [])),
                data.get("primary_mode", 0),
                json.dumps(data.get("retrofeedback", {})),
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
        return spec_id

    def load_spectrum_history(self, cycle_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Carga el historial de espectro de un ciclo."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM orbital_spectrum WHERE cycle_id = ? ORDER BY tick DESC LIMIT ?", (cycle_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Ejecuciones Orbitales ──────────────────────────────

    def save_execution(self, result: dict[str, Any]) -> str:
        """Guarda el resultado de una ejecucion orbital."""
        conn = self._get_connection()
        exec_id = str(uuid.uuid4())

        conn.execute(
            """
            INSERT INTO orbital_executions
            (id, tick, total_variables, total_cycles, total_tor_pairs,
             resonant_cycles, converged_cycles, final_state, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                exec_id,
                result.get("tick", 0),
                result.get("total_variables", 0),
                result.get("total_cycles", 0),
                result.get("total_tor_pairs", 0),
                result.get("resonant_cycles", 0),
                result.get("converged_cycles", 0),
                json.dumps(result.get("final_state", {})),
                result.get("duration_ms", 0),
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
        return exec_id

    def load_execution_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Carga el historial de ejecuciones orbitales."""
        conn = self._get_connection()
        rows = conn.execute("SELECT * FROM orbital_executions ORDER BY tick DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── Estadisticas ───────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadisticas generales de las tablas orbitales."""
        conn = self._get_connection()
        try:
            var_count = conn.execute("SELECT COUNT(*) FROM orbital_variables").fetchone()[0]
            cycle_count = conn.execute("SELECT COUNT(*) FROM orbital_cycles").fetchone()[0]
            spectrum_count = conn.execute("SELECT COUNT(*) FROM orbital_spectrum").fetchone()[0]
            exec_count = conn.execute("SELECT COUNT(*) FROM orbital_executions").fetchone()[0]
        except sqlite3.OperationalError:
            # Tablas no existen aun
            var_count = cycle_count = spectrum_count = exec_count = 0

        return {
            "orbital_variables": var_count,
            "orbital_cycles": cycle_count,
            "orbital_spectrum": spectrum_count,
            "orbital_executions": exec_count,
        }

    # ── Limpieza ───────────────────────────────────────────

    def close(self) -> None:
        """Cierra la conexion a la base de datos."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass  # Conexión ya cerrada o inválida
            self._conn = None

    # Fix Sprint 4 bug #54: __del__ no es fiable en Python (no se garantiza
    # que se llame, especialmente en shutdown). Eliminado __del__ y añadido
    # soporte para context manager (__enter__/__exit__) como reemplazo.
    # Uso recomendado: `with OrbitalDB() as db: ...`
    def __enter__(self) -> "OrbitalDB":
        self._get_connection()  # Asegura que la conexión esté abierta
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False  # No suprimir excepciones
