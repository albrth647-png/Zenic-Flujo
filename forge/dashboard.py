"""
Forge Dashboard — Genera HTML report con score por módulo
==========================================================
Genera un dashboard HTML navegable que muestra:
- Score por módulo (barras horizontales + tabla)
- Gates pasando/fallando por módulo
- Historial de scores (últimas N ejecuciones)
- Tendencias de calidad (delta vs ejecución anterior)
- Resumen global (score promedio, gates PASS totales)

Uso:
  from forge.dashboard import DashboardGenerator
  gen = DashboardGenerator(project_root)
  html = gen.generate()
  gen.save(html, "forge/dashboard.html")

CLI:
  python -m forge dashboard
  python -m forge dashboard --output reports/dashboard.html
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict


class ModuleScore(TypedDict):
    """Score de un módulo en el dashboard."""

    name: str
    path: str
    stack: str
    criticality: str
    file_count: int
    gates_pass: int
    gates_total: int
    avg_score: float
    status: str  # HOMOLOGADO | PARCIAL | NO_HOMOLOGADO
    gates: list[dict]  # [{name, passed, evidence, score}]


class DashboardSummary(TypedDict):
    """Resumen global del dashboard."""

    total_modules: int
    homologated: int
    partial: int
    not_homologated: int
    avg_score: float
    total_gates_pass: int
    total_gates: int
    generated_at: str


class DashboardGenerator:
    """Genera dashboard HTML con score por módulo y tendencias.

    Lee datos de:
    - `.forge/phase6/homologation_summary.json` (última homologación)
    - `.forge/dashboard_history.json` (historial de snapshots)
    """

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.history_path = self.project_root / ".forge" / "dashboard_history.json"
        self.homologation_path = self.project_root / ".forge" / "phase6" / "homologation_summary.json"

    def load_current_scores(self) -> list[ModuleScore]:
        """Carga los scores actuales de la última homologación."""
        if not self.homologation_path.exists():
            return []
        with open(self.homologation_path) as f:
            data = json.load(f)
        modules: list[ModuleScore] = []
        for m in data.get("modules", []):
            if m.get("skipped"):
                continue
            modules.append(ModuleScore(
                name=m["module"],
                path=m["path"],
                stack=m["stack"],
                criticality=m["criticality"],
                file_count=m["file_count"],
                gates_pass=m["gates_pass"],
                gates_total=m["gates_total"],
                avg_score=m["avg_score"],
                status=m["status"],
                gates=m.get("results", []),
            ))
        return modules

    def load_history(self) -> list[dict]:
        """Carga el historial de snapshots anteriores."""
        if not self.history_path.exists():
            return []
        with open(self.history_path) as f:
            return json.load(f).get("snapshots", [])

    def save_snapshot(self, modules: list[ModuleScore]) -> None:
        """Guarda un snapshot de los scores actuales en el historial."""
        history = self.load_history()
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "modules": [
                {
                    "name": m["name"],
                    "avg_score": m["avg_score"],
                    "gates_pass": m["gates_pass"],
                    "gates_total": m["gates_total"],
                    "status": m["status"],
                }
                for m in modules
            ],
            "global_avg": sum(m["avg_score"] for m in modules) / len(modules) if modules else 0,
        }
        history.append(snapshot)
        # Mantener solo los últimos 50 snapshots
        history = history[-50:]
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w") as f:
            json.dump({"snapshots": history}, f, indent=2, ensure_ascii=False)

    def compute_summary(self, modules: list[ModuleScore]) -> DashboardSummary:
        """Calcula el resumen global del dashboard."""
        if not modules:
            return DashboardSummary(
                total_modules=0,
                homologated=0,
                partial=0,
                not_homologated=0,
                avg_score=0.0,
                total_gates_pass=0,
                total_gates=0,
                generated_at=datetime.now().isoformat(),
            )
        homologated = sum(1 for m in modules if m["status"] == "HOMOLOGADO")
        partial = sum(1 for m in modules if m["status"] == "PARCIAL")
        not_homologated = sum(1 for m in modules if m["status"] == "NO_HOMOLOGADO")
        avg = sum(m["avg_score"] for m in modules) / len(modules)
        total_pass = sum(m["gates_pass"] for m in modules)
        total = sum(m["gates_total"] for m in modules)
        return DashboardSummary(
            total_modules=len(modules),
            homologated=homologated,
            partial=partial,
            not_homologated=not_homologated,
            avg_score=round(avg, 2),
            total_gates_pass=total_pass,
            total_gates=total,
            generated_at=datetime.now().isoformat(),
        )

    def generate(self) -> str:
        """Genera el HTML completo del dashboard."""
        modules = self.load_current_scores()
        summary = self.compute_summary(modules)
        history = self.load_history()

        # Guardar snapshot para historial
        self.save_snapshot(modules)

        return self._render_html(modules, summary, history)

    def _render_html(self, modules: list[ModuleScore], summary: DashboardSummary, history: list[dict]) -> str:
        """Renderiza el HTML del dashboard."""
        # Calcular delta vs snapshot anterior
        prev_avg = history[-2]["global_avg"] if len(history) >= 2 else summary["avg_score"]
        delta = summary["avg_score"] - prev_avg
        delta_emoji = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")

        # CSS inline (sin dependencias externas)
        css = """
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #0f172a; color: #e2e8f0; padding: 2rem; }
        h1 { color: #38bdf8; margin-bottom: 0.5rem; }
        h2 { color: #818cf8; margin: 1.5rem 0 0.75rem; }
        .subtitle { color: #94a3b8; margin-bottom: 2rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
        .card { background: #1e293b; border-radius: 0.75rem; padding: 1.25rem; border: 1px solid #334155; }
        .card .label { color: #94a3b8; font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; }
        .card .value { font-size: 2rem; font-weight: 700; margin-top: 0.5rem; }
        .card .delta { font-size: 0.875rem; margin-top: 0.25rem; }
        .positive { color: #4ade80; }
        .negative { color: #f87171; }
        .neutral { color: #94a3b8; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; }
        th, td { text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid #334155; }
        th { color: #818cf8; font-weight: 600; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 0.05em; }
        tr:hover { background: #1e293b; }
        .bar-container { width: 100px; height: 8px; background: #334155; border-radius: 4px; overflow: hidden; display: inline-block; vertical-align: middle; }
        .bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
        .status-badge { padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; font-weight: 600; }
        .status-HOMOLOGADO { background: #166534; color: #4ade80; }
        .status-PARCIAL { background: #854d0e; color: #fbbf24; }
        .status-NO_HOMOLOGADO { background: #991b1b; color: #f87171; }
        .gate-pass { color: #4ade80; }
        .gate-fail { color: #f87171; }
        .history-chart { display: flex; align-items: flex-end; gap: 4px; height: 120px; margin: 1rem 0; padding: 1rem; background: #1e293b; border-radius: 0.5rem; }
        .history-bar { flex: 1; min-width: 20px; background: linear-gradient(to top, #3b82f6, #818cf8); border-radius: 4px 4px 0 0; position: relative; }
        .history-bar:hover .history-tooltip { opacity: 1; }
        .history-tooltip { position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%); background: #0f172a; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; white-space: nowrap; opacity: 0; transition: opacity 0.2s; pointer-events: none; }
        .footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #334155; color: #64748b; font-size: 0.8rem; }
        """

        # Cards de resumen
        cards_html = f"""
        <div class="grid">
            <div class="card">
                <div class="label">Score Global</div>
                <div class="value">{summary['avg_score']}/10</div>
                <div class="delta {'positive' if delta > 0 else 'negative' if delta < 0 else 'neutral'}">
                    {delta_emoji} {delta:+.2f} vs anterior
                </div>
            </div>
            <div class="card">
                <div class="label">Módulos Homologados</div>
                <div class="value positive">{summary['homologated']}/{summary['total_modules']}</div>
                <div class="delta neutral">{summary['partial']} parcial, {summary['not_homologated']} no homologados</div>
            </div>
            <div class="card">
                <div class="label">Gates PASS</div>
                <div class="value">{summary['total_gates_pass']}/{summary['total_gates']}</div>
                <div class="delta neutral">{summary['total_gates_pass'] * 100 // max(summary['total_gates'], 1)}% de gates pasando</div>
            </div>
            <div class="card">
                <div class="label">Generado</div>
                <div class="value" style="font-size: 1rem;">{summary['generated_at'][:19]}</div>
                <div class="delta neutral">Code-Forge Fase 7</div>
            </div>
        </div>
        """

        # Tabla de módulos
        rows_html = ""
        for m in modules:
            score_color = "#4ade80" if m["avg_score"] >= 8 else ("#fbbf24" if m["avg_score"] >= 6 else "#f87171")
            bar_width = int(m["avg_score"] * 10)
            gates_detail = " ".join(
                f"<span class='{'gate-pass' if g['passed'] else 'gate-fail'}'>{'✅' if g['passed'] else '❌'} {g['name']}</span>"
                for g in m["gates"]
            )
            rows_html += f"""
            <tr>
                <td><strong>{m['name']}</strong></td>
                <td>{m['path']}</td>
                <td>{m['stack']}</td>
                <td>{m['file_count']}</td>
                <td>
                    <div class="bar-container"><div class="bar-fill" style="width: {bar_width}%; background: {score_color};"></div></div>
                    {m['avg_score']}/10
                </td>
                <td>{m['gates_pass']}/{m['gates_total']}</td>
                <td><span class="status-badge status-{m['status']}">{m['status']}</span></td>
                <td style="font-size: 0.75rem;">{gates_detail}</td>
            </tr>
            """

        table_html = f"""
        <h2>📊 Score por Módulo</h2>
        <table>
            <thead>
                <tr>
                    <th>Módulo</th>
                    <th>Path</th>
                    <th>Stack</th>
                    <th>Archivos</th>
                    <th>Score</th>
                    <th>Gates</th>
                    <th>Estado</th>
                    <th>Detalle Gates</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        """

        # Chart de historial
        history_html = ""
        if history:
            bars = ""
            for snap in history[-20:]:  # últimos 20 snapshots
                avg = snap.get("global_avg", 0)
                height = int(avg * 10)  # 0-100px
                ts = snap.get("timestamp", "")[:19]
                bars += f"""
                <div class="history-bar" style="height: {height}%;">
                    <div class="history-tooltip">{ts}<br>Score: {avg:.2f}</div>
                </div>
                """
            history_html = f"""
            <h2>📈 Historial de Scores</h2>
            <div class="history-chart">{bars}</div>
            <p style="color: #64748b; font-size: 0.8rem;">Últimos {min(len(history), 20)} snapshots. Hover sobre las barras para ver detalles.</p>
            """

        # HTML completo
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code-Forge Dashboard — Zenic-Flujo</title>
    <style>{css}</style>
</head>
<body>
    <h1>🔧 Code-Forge Dashboard</h1>
    <p class="subtitle">Zenic-Flujo — Calidad de código por módulo · Generado: {summary['generated_at'][:19]}</p>

    {cards_html}
    {table_html}
    {history_html}

    <div class="footer">
        <p>Generado por <code>forge dashboard</code> — Code-Forge Fase 7 (CI/CD)</p>
        <p>Datos: <code>.forge/phase6/homologation_summary.json</code> + <code>.forge/dashboard_history.json</code></p>
    </div>
</body>
</html>"""
        return html

    def save(self, html: str, output_path: str | Path) -> Path:
        """Guarda el HTML en el path especificado."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return out
