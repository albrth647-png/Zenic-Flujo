#!/usr/bin/env python3
"""
Análisis de memoria del Orbital Engine con memray.

Ejecuta 1000 ticks del OrbitalEngine bajo memray y genera:
  - Flame graph de memoria (HTML)
  - Estadísticas de top allocators
  - Reporte de stats

Uso:
    python3 scripts/orbital_memray_analysis.py
    # Genera: memray-orbital.html, memray-orbital-stats.txt

Requiere: pip install memray

Referencias:
  - Investigación: "memray sobre run de 10k ticks para detectar leaks"
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "scripts" / "any_audit" / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Script que memray ejecutará
TARGET_SCRIPT = PROJECT_ROOT / "scripts" / "orbital_memray_target.py"


def create_target_script() -> None:
    """Crea el script target que memray ejecutará."""
    TARGET_SCRIPT.write_text("""
import logging
logging.disable(logging.WARNING)

from src.orbital.engine import OrbitalEngine
from src.orbital.models import TWO_PI

# Crear engine con 50 variables
eng = OrbitalEngine()
for i in range(50):
    eng.create_variable(
        f"var_{i}",
        theta=(i / 50) * TWO_PI,
        amplitude=1.0,
        velocity=0.05,
    )
eng.create_cycle("mem_test", [f"var_{i}" for i in range(5)], threshold=0.4)

# Ejecutar 1000 ticks
for _ in range(1000):
    eng.run_tick(dt=1.0, retrofeed_damping=0.3)

print(f"Completado: {eng.tick} ticks, {eng.variable_count} variables")
print(f"Historial: {len(eng._execution_history)} OrbitalResult objetos")
""", encoding="utf-8")


def main() -> int:
    print("=== Análisis de memoria del Orbital Engine con memray ===")
    print()

    # 1. Crear script target
    create_target_script()
    print(f"✅ Script target creado: {TARGET_SCRIPT}")

    # 2. Ejecutar memray
    output_bin = OUTPUT_DIR / "memray-orbital.bin"
    print(f"🛠️  Ejecutando memray (1000 ticks, 50 variables)...")

    result = subprocess.run(
        [
            sys.executable, "-m", "memray", "run",
            "--force",  # sobrescribir si existe
            "-o", str(output_bin),
            str(TARGET_SCRIPT),
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        print(f"❌ memray run falló:")
        print(result.stderr)
        return 1

    print(f"✅ memray run completado: {output_bin}")

    # 3. Generar flame graph HTML
    flame_html = OUTPUT_DIR / "memray-orbital.html"
    print(f"📊 Generando flame graph...")

    result = subprocess.run(
        [
            sys.executable, "-m", "memray", "flamegraph",
            str(output_bin),
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode == 0:
        # memray flamegraph escribe a stdout, redirigir a archivo
        flame_html.write_text(result.stdout, encoding="utf-8")
        print(f"✅ Flame graph: {flame_html}")
    else:
        print(f"⚠️  flamegraph falló: {result.stderr[:200]}")

    # 4. Generar stats
    stats_file = OUTPUT_DIR / "memray-orbital-stats.txt"
    print(f"📈 Generando stats...")

    result = subprocess.run(
        [
            sys.executable, "-m", "memray", "stats",
            str(output_bin),
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode == 0:
        stats_file.write_text(result.stdout, encoding="utf-8")
        print(f"✅ Stats: {stats_file}")
        # Mostrar top 10 allocators
        print()
        print("=== Top 10 allocators ===")
        lines = result.stdout.split("\n")
        for line in lines[:30]:
            if line.strip():
                print(f"  {line}")
    else:
        print(f"⚠️  stats falló: {result.stderr[:200]}")

    # 5. Cleanup
    TARGET_SCRIPT.unlink(missing_ok=True)
    output_bin.unlink(missing_ok=True)

    print()
    print("=== Hallazgos ===")
    print("Si el flame graph muestra que _execution_history acumula memoria,")
    print("considerar usar deque(maxlen=1000) para acotar el historial.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
