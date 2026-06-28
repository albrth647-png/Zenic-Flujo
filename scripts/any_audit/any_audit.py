#!/usr/bin/env python3
"""
any_audit.py — Auditoría de uso de `Any` en el codebase Zenic-Flujo.

Genera un inventario completo de ocurrencias de `typing.Any` en `src/` (excluyendo
`src/core/` por configuración) y produce:

  - `any_audit.csv` — una fila por ocurrencia (módulo, archivo, línea, contexto, antipatrón).
  - `any_audit.json` — resumen estructurado por módulo y por antipatrón.
  - `any_audit.md` — reporte markdown legible para PRs y revisiones.

Uso:
    python3 scripts/any_audit/any_audit.py
    python3 scripts/any_audit/any_audit.py --path src/connectors --format json
    python3 scripts/any_audit/any_audit.py --baseline .any-baseline.json --enforce

Diseño:
  - Sin dependencias externas (solo stdlib + AST). Compatible con Python 3.12.
  - Detección por AST (no regex) para precisión sintáctica.
  - Antipatrones clasificados según la skill `.opencode/skills/any-best-practices/SKILL.md`.
  - Modo `--enforce` para CI: salida no-cero si el count supera el baseline.

Referencias:
  - Skill: .opencode/skills/any-best-practices/SKILL.md
  - Plan:  docs/plans/any-migration-rollout.md
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# ─── Configuración ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_PATH = PROJECT_ROOT / "src"
EXCLUDE_DIRS = {"core"}  # src/core queda fuera del scope por decisión explícita
EXCLUDE_FILE_PATTERNS = {"__pycache__", ".pyc", "test_"}  # tests en subdirs aparte

# Antipatrones clasificados según la skill
ANTIPATTERN_TYPES = {
    "param_annotation": "Any en parámetro de función (debería ser object/Protocol/TypeVar)",
    "return_annotation": "Any como tipo de retorno (debería ser tipo concreto o TypeVar)",
    "attribute_init": "Atributo de clase inicializado con Any (debería ser X | None)",
    "bare_dict": "dict sin parametrizar (debería ser dict[K, V])",
    "bare_list": "list sin parametrizar (debería ser list[T])",
    "bare_tuple": "tuple sin parametrizar (debería ser tuple[X, ...])",
    "bare_set": "set sin parametrizar (debería ser set[T])",
    "var_annotation": "Variable con anotación Any explícita",
    "cast_call": "typing.cast(Any, ...) — revisar si es necesario",
    "import_any": "Import explícito de Any (legítimo si se usa)",
    "legitimate_import_any": "Import de Any que SÍ se usa en el archivo (no es antipatrón)",
    "unused_import_any": "Import de Any que NO se usa en el archivo (deuda real, eliminar import)",
    "other_any": "Uso de Any no clasificado",
}

# Antipatrones que se excluyen del count de "deuda real" (no son antipatrón)
LEGITIMATE_PATTERNS = {"legitimate_import_any"}


@dataclass(frozen=True)
class AnyOccurrence:
    """Una ocurrencia individual de `Any` en el código."""

    module: str  # ej: "src/connectors"
    file: str  # ruta relativa al proyecto
    line: int
    col: int
    antipattern: str  # clave de ANTIPATTERN_TYPES
    context: str  # línea de código recortada
    is_justified: bool  # tiene # legítimo: o # TODO: tipar cerca
    justification: str | None  # el comentario si existe


# ─── Detección por AST ────────────────────────────────────────────────────────


def _is_any_node(node: ast.AST) -> bool:
    """True si el nodo es una referencia a `Any` (Name o Attribute)."""
    if isinstance(node, ast.Name) and node.id == "Any":
        return True
    if isinstance(node, ast.Attribute) and node.attr == "Any":
        # typing.Any o Any.Any (caso edge)
        return True
    return False


def _is_bare_collection(node: ast.AST) -> str | None:
    """Detecta `dict`, `list`, `tuple`, `set` sin parametrizar. Retorna el tipo o None."""
    if isinstance(node, ast.Name) and node.id in {"dict", "list", "tuple", "set", "frozenset"}:
        return node.id
    return None


def _get_justification(lines: list[str], lineno: int) -> tuple[bool, str | None]:
    """Busca comentario `# legítimo:` o `# TODO: tipar` en la misma línea o en
    comentarios consecutivos hacia atrás (bloque de comentarios anterior)."""
    markers = ("# legítimo", "# legitimo", "# TODO: tipar", "# type: ignore")
    # Misma línea
    if lineno - 1 < len(lines):
        same_line = lines[lineno - 1]
        for marker in markers:
            idx = same_line.find(marker)
            if idx >= 0:
                comment = same_line[idx:].strip()
                return True, comment
    # Buscar hacia atrás en comentarios consecutivos (bloque de comentarios)
    # Saltando decoradores (@abstractmethod, @property, etc.)
    # lineno es 1-indexed; lines es 0-indexed. lines[lineno-2] = línea anterior.
    check_idx = lineno - 2  # 0-indexed, línea anterior
    while check_idx >= 0:
        line = lines[check_idx]
        stripped = line.strip()
        # Si la línea está vacía, parar (no es comentario consecutivo)
        if not stripped:
            break
        # Si es comentario
        if stripped.startswith("#"):
            for marker in markers:
                idx = line.find(marker)
                if idx >= 0:
                    comment = line[idx:].strip()
                    return True, comment
            # Es comentario pero no tiene marker — seguir hacia atrás
            check_idx -= 1
            continue
        # Si es decorador (@abstractmethod, @property, etc.), saltarlo
        if stripped.startswith("@"):
            check_idx -= 1
            continue
        # No es comentario ni decorador — parar
        break
    return False, None


def _classify_node(node: ast.AST, lines: list[str], lineno: int) -> str:
    """Clasifica el antipatrón dado el contexto AST."""
    # Si el nodo padre es una anotación de atributo con = None
    # (lo manejamos en el visitor específicamente)
    bare = _is_bare_collection(node)
    if bare == "dict":
        return "bare_dict"
    if bare == "list":
        return "bare_list"
    if bare == "tuple":
        return "bare_tuple"
    if bare == "set":
        return "bare_set"
    return "other_any"


class AnyVisitor(ast.NodeVisitor):
    """Recorre el AST de un archivo y colecciona ocurrencias de Any."""

    def __init__(self, filepath: Path, module: str, lines: list[str]) -> None:
        self.filepath = filepath
        self.module = module
        self.lines = lines
        self.occurrences: list[AnyOccurrence] = []

    def _add(self, node: ast.AST, antipattern: str) -> None:
        rel_path = str(self.filepath.relative_to(PROJECT_ROOT))
        context = self.lines[node.lineno - 1].strip() if node.lineno <= len(self.lines) else ""
        # Truncar contexto largo
        if len(context) > 120:
            context = context[:117] + "..."
        is_just, justification = _get_justification(self.lines, node.lineno)
        self.occurrences.append(
            AnyOccurrence(
                module=self.module,
                file=rel_path,
                line=node.lineno,
                col=node.col_offset + 1,
                antipattern=antipattern,
                context=context,
                is_justified=is_just,
                justification=justification,
            )
        )

    def visit_arg(self, node: ast.arg) -> None:
        # Parámetro de función con anotación Any
        if node.annotation is not None and _is_any_node(node.annotation):
            self._add(node, "param_annotation")
        # Parámetro con dict/list sin parametrizar
        if node.annotation is not None:
            bare = _is_bare_collection(node.annotation)
            if bare:
                self._add(node, f"bare_{bare}")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Retorno -> Any
        if node.returns is not None and _is_any_node(node.returns):
            self._add(node, "return_annotation")
        # Retorno -> dict / -> list sin parametrizar
        if node.returns is not None:
            bare = _is_bare_collection(node.returns)
            if bare:
                self._add(node, f"bare_{bare}")
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # x: Any = ...  o  x: Any
        if _is_any_node(node.annotation):
            # Distinguir atributo de clase con = None
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                self._add(node, "attribute_init")
            else:
                self._add(node, "var_annotation")
        # x: dict = ...  sin parametrizar
        bare = _is_bare_collection(node.annotation)
        if bare:
            self._add(node, f"bare_{bare}")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # cast(Any, x) calls
        for call_node in ast.walk(node.value):
            if (
                isinstance(call_node, ast.Call)
                and isinstance(call_node.func, ast.Name)
                and call_node.func.id == "cast"
                and call_node.args
                and _is_any_node(call_node.args[0])
            ):
                self._add(node, "cast_call")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # from typing import Any (legítimo pero registrar)
        for alias in node.names:
            if alias.name == "Any":
                self._add(node, "import_any")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # Detectar usos sueltos de Any que no estén en annotation context.
        # Los annotations ya se detectan via visit_arg/visit_FunctionDef/visit_AnnAssign,
        # pero Any puede aparecer en cast(Any, x), TypeVar("T", bound=Any), etc.
        # que ya se cubren con visit_Assign (cast) o quedan como other_any.
        # NO detectamos aquí para evitar duplicados — los visitantes específicos ya cubren los casos.
        # Este método existe solo para documentar que se omite intencionalmente.
        self.generic_visit(node)


# ─── Escaneo de archivos ──────────────────────────────────────────────────────


def _module_for_file(filepath: Path) -> str:
    """Calcula el módulo de primer o segundo nivel: 'src/connectors' o 'src/api_v2/routers'."""
    try:
        rel = filepath.relative_to(PROJECT_ROOT / "src")
    except ValueError:
        return "src"
    parts = rel.parts
    if len(parts) <= 1:
        return "src"
    if len(parts) >= 3 and parts[0] in {"api_v2", "hat", "sdk", "cli", "nlu", "tests"}:
        return f"src/{parts[0]}/{parts[1]}"
    return f"src/{parts[0]}"


def _iter_python_files(root: Path) -> Iterable[Path]:
    """Itera archivos .py excluyendo __pycache__, tests y dirs EXCLUDE_DIRS."""
    for path in root.rglob("*.py"):
        # Excluir si está en un dir prohibido
        try:
            rel = path.relative_to(PROJECT_ROOT / "src")
        except ValueError:
            continue
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if "__pycache__" in path.parts:
            continue
        # Excluir tests (los auditamos aparte)
        if "tests" in rel.parts:
            continue
        yield path


def _file_uses_any_beyond_import(tree: ast.AST) -> bool:
    """True si el archivo usa `Any` en cualquier contexto que no sea el import.

    Esto es más exhaustivo que el visitor (que solo mira annotations) porque
    también detecta usos en cast(), TypeVar(bound=Any), typing.Any, etc.
    """
    for node in ast.walk(tree):
        # Name node "Any" (excluyendo alias.name en imports que es string, no Name)
        if isinstance(node, ast.Name) and node.id == "Any":
            return True
        # typing.Any (Attribute)
        if isinstance(node, ast.Attribute) and node.attr == "Any":
            # Asegurarse de que no sea `typing.Any` dentro de un import (raro pero posible)
            if not isinstance(node.ctx, ast.Load):
                continue
            return True
    return False


def scan_file(filepath: Path) -> list[AnyOccurrence]:
    """Escanea un solo archivo Python.

    Post-procesamiento: reclasifica `import_any` según si Any se usa en el archivo:
      - Si Any se usa en otros contextos (annotations, cast, etc.) → `legitimate_import_any`
        (no es antipatrón, se marca como justificado).
      - Si Any NO se usa en otros contextos → `unused_import_any` (deuda real, eliminar import).
    """
    try:
        source = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []
    lines = source.splitlines()
    module = _module_for_file(filepath)
    visitor = AnyVisitor(filepath, module, lines)
    visitor.visit(tree)

    occurrences = visitor.occurrences

    # Verificación exhaustiva: ¿Any se usa más allá del import?
    has_any_usages = _file_uses_any_beyond_import(tree)

    # Reclasificar import_any
    reclassified: list[AnyOccurrence] = []
    for occ in occurrences:
        if occ.antipattern == "import_any":
            if has_any_usages:
                # El import es legítimo: Any se usa en el archivo
                reclassified.append(
                    replace(
                        occ,
                        antipattern="legitimate_import_any",
                        is_justified=True,
                        justification="Any se usa en el archivo (import legítimo)",
                    )
                )
            else:
                # Import sin uso: deuda real
                reclassified.append(replace(occ, antipattern="unused_import_any"))
        else:
            reclassified.append(occ)

    return reclassified


def scan_project(root: Path | None = None) -> list[AnyOccurrence]:
    """Escanea todo el proyecto y devuelve la lista de ocurrencias."""
    root = root or DEFAULT_SCAN_PATH
    all_occurrences: list[AnyOccurrence] = []
    for filepath in _iter_python_files(root):
        all_occurrences.extend(scan_file(filepath))
    return all_occurrences


# ─── Reportes ─────────────────────────────────────────────────────────────────


def write_csv(occurrences: list[AnyOccurrence], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["module", "file", "line", "col", "antipattern", "is_justified", "justification", "context"]
        )
        for occ in sorted(occurrences, key=lambda o: (o.module, o.file, o.line)):
            writer.writerow(
                [
                    occ.module,
                    occ.file,
                    occ.line,
                    occ.col,
                    occ.antipattern,
                    str(occ.is_justified).lower(),
                    occ.justification or "",
                    occ.context,
                ]
            )


def build_summary(occurrences: list[AnyOccurrence]) -> dict:
    """Construye resumen estructurado para JSON.

    Métricas clave:
      - total_occurrences: todas las ocurrencias (incluye legitimate_import_any)
      - real_debt: ocurrencias que NO son legitimate_import_any NI justificadas
                   (deuda real a atacar: `Any` sin justificación que requiere decisión)
      - justified: ocurrencias con justificación explícita (# legítimo: / # TODO: tipar)
      - unjustified: ocurrencias sin justificación (= real_debt, alias)
      - legitimate_imports: imports de Any que se usan (no son antipatrón)
      - justified_any: Any justificados con comentario (decisión consciente, no deuda)
    """
    by_module: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_antipattern: dict[str, int] = Counter()
    by_file: dict[str, int] = Counter()
    justified = 0
    unjustified = 0
    real_debt = 0
    legitimate_count = 0
    justified_any = 0

    for occ in occurrences:
        by_module[occ.module]["total"] += 1
        if occ.is_justified:
            by_module[occ.module]["justified"] += 1
            justified += 1
        else:
            by_module[occ.module]["unjustified"] += 1
            unjustified += 1
        by_module[occ.module][occ.antipattern] += 1
        by_antipattern[occ.antipattern] += 1
        by_file[occ.file] += 1

        # Clasificar en 3 buckets:
        # 1. legitimate_import_any: import de Any que se USA (no es antipatrón)
        # 2. justified_any: Any con comentario # legítimo: (decisión consciente)
        # 3. real_debt: Any sin justificación (deuda real a atacar)
        if occ.antipattern in LEGITIMATE_PATTERNS:
            legitimate_count += 1
        elif occ.is_justified:
            justified_any += 1
        else:
            real_debt += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_occurrences": len(occurrences),
        "real_debt": real_debt,
        "legitimate_imports": legitimate_count,
        "justified_any": justified_any,
        "justified": justified,
        "unjustified": unjustified,
        "by_module": dict(sorted(by_module.items(), key=lambda x: -x[1]["total"])),
        "by_antipattern": dict(by_antipattern.most_common()),
        "top_files": dict(by_file.most_common(20)),
        "antipattern_descriptions": ANTIPATTERN_TYPES,
    }


def write_json(summary: dict, out_path: Path) -> None:
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)


def write_markdown(summary: dict, out_path: Path, baseline_count: int | None = None) -> None:
    """Genera reporte markdown legible."""
    lines: list[str] = []
    lines.append("# Any Audit Report — Zenic-Flujo\n")
    lines.append(f"**Generado:** {summary['generated_at']}\n")
    lines.append(f"**Scope:** `src/**` excluyendo `src/core/**` y `src/tests/**`\n")
    lines.append(
        f"**Total ocurrencias:** {summary['total_occurrences']} | "
        f"**Deuda real:** {summary['real_debt']} | "
        f"**Justificados:** {summary['justified_any']} | "
        f"**Imports legítimos:** {summary['legitimate_imports']}\n"
    )
    lines.append(
        f"**Justificadas:** {summary['justified']} | **Injustificadas:** {summary['unjustified']}\n"
    )
    if baseline_count is not None:
        delta = summary["total_occurrences"] - baseline_count
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
        lines.append(
            f"**Baseline:** {baseline_count} | **Actual:** {summary['total_occurrences']} | "
            f"**Delta:** {arrow} {abs(delta)}\n"
        )
    lines.append("")
    lines.append(
        "> **Nota**: `legitimate_import_any` = `from typing import Any` donde Any SÍ se usa. "
        "No es antipatrón, se excluye de la deuda real.\n"
    )
    lines.append("")

    # Tabla por módulo
    lines.append("## Por módulo\n")
    lines.append("| Módulo | Total | Deuda real | Justificadas | Injustificadas |")
    lines.append("|--------|------:|-----------:|------------:|---------------:|")
    for module, stats in summary["by_module"].items():
        real = stats["total"] - stats.get("legitimate_import_any", 0)
        lines.append(
            f"| `{module}` | {stats['total']} | {real} | "
            f"{stats.get('justified', 0)} | {stats.get('unjustified', 0)} |"
        )
    lines.append("")

    # Tabla por antipatrón
    lines.append("## Por antipatrón\n")
    lines.append("| Antipatrón | Ocurrencias | Es deuda real | Descripción |")
    lines.append("|------------|------------:|:-------------:|-------------|")
    for ap, count in summary["by_antipattern"].items():
        desc = ANTIPATTERN_TYPES.get(ap, "—")
        is_debt = "No" if ap in LEGITIMATE_PATTERNS else "Sí"
        lines.append(f"| `{ap}` | {count} | {is_debt} | {desc} |")
    lines.append("")

    # Top archivos
    lines.append("## Top 20 archivos con más `Any`\n")
    lines.append("| Archivo | Ocurrencias |")
    lines.append("|---------|------------:|")
    for fpath, count in summary["top_files"].items():
        lines.append(f"| `{fpath}` | {count} |")
    lines.append("")

    lines.append("## Comandos útiles\n")
    lines.append("```bash")
    lines.append("# Re-ejecutar auditoría")
    lines.append("python3 scripts/any_audit/any_audit.py")
    lines.append("")
    lines.append("# Filtrar por módulo")
    lines.append("python3 scripts/any_audit/any_audit.py --path src/connectors --format json")
    lines.append("")
    lines.append("# Modo enforce en CI (compara contra baseline)")
    lines.append("python3 scripts/any_audit/any_audit.py --baseline .any-baseline.json --enforce")
    lines.append("```")
    lines.append("")
    lines.append("## Referencias\n")
    lines.append("- Skill: `.opencode/skills/any-best-practices/SKILL.md`")
    lines.append("- Plan: `docs/plans/any-migration-rollout.md`")
    lines.append("- Investigación: `docs/research/any-best-practices.md`")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ─── CLI ──────────────────────────────────────────────────────────────────────


def load_baseline(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def cmd_run(args: argparse.Namespace) -> int:
    occurrences = scan_project(args.path)
    summary = build_summary(occurrences)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_count = None
    if args.baseline:
        try:
            baseline_data = load_baseline(args.baseline)
            baseline_count = baseline_data.get("total_occurrences")
        except (OSError, json.JSONDecodeError):
            print(f"⚠️  No se pudo leer baseline {args.baseline}", file=sys.stderr)

    # Escribir todos los formatos
    write_csv(occurrences, out_dir / "any_audit.csv")
    write_json(summary, out_dir / "any_audit.json")
    write_markdown(summary, out_dir / "any_audit.md", baseline_count=baseline_count)

    print(f"✅ Auditoría completa: {len(occurrences)} ocurrencias")
    print(f"   Justificadas: {summary['justified']}  Injustificadas: {summary['unjustified']}")
    print(f"   CSV:  {out_dir / 'any_audit.csv'}")
    print(f"   JSON: {out_dir / 'any_audit.json'}")
    print(f"   MD:   {out_dir / 'any_audit.md'}")

    if baseline_count is not None:
        delta = summary["total_occurrences"] - baseline_count
        if delta > 0:
            print(f"⚠️  Delta vs baseline: +{delta} (regresión)", file=sys.stderr)
            if args.enforce:
                return 1
        elif delta < 0:
            print(f"✅ Delta vs baseline: {delta} (mejora)")
        else:
            print("=  Delta vs baseline: 0 (sin cambios)")

    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    """Crea el archivo baseline con el count actual."""
    occurrences = scan_project(args.path)
    summary = build_summary(occurrences)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "total_occurrences": summary["total_occurrences"],
                "justified": summary["justified"],
                "unjustified": summary["unjustified"],
                "created_at": summary["generated_at"],
                "by_module": summary["by_module"],
                "by_antipattern": summary["by_antipattern"],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"✅ Baseline creado: {args.out}")
    print(f"   Total: {summary['total_occurrences']}")
    print(f"   Commit sugerido: git add {args.out} && git commit -m 'chore(any): baseline snapshot'")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Compara dos archivos de auditoría y muestra el diff."""
    try:
        before = json.loads(args.before.read_text(encoding="utf-8"))
        after = json.loads(args.after.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"❌ No se pudieron leer los archivos: {e}", file=sys.stderr)
        return 2

    b_total = before.get("total_occurrences", 0)
    a_total = after.get("total_occurrences", 0)
    delta = a_total - b_total

    print(f"Antes: {b_total}  Después: {a_total}  Delta: {delta:+d}")
    print()

    # Diff por módulo
    b_modules = before.get("by_module", {})
    a_modules = after.get("by_module", {})
    all_modules = sorted(set(b_modules) | set(a_modules))
    print("Por módulo:")
    for mod in all_modules:
        b = b_modules.get(mod, {}).get("total", 0)
        a = a_modules.get(mod, {}).get("total", 0)
        if b != a:
            print(f"  {mod}: {b} → {a} ({a - b:+d})")

    return 0 if delta <= 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="any_audit",
        description="Auditoría de uso de `Any` en Zenic-Flujo (ratchet anti-deuda).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run
    p_run = sub.add_parser("run", help="Ejecuta la auditoría y genera reportes.")
    p_run.add_argument("--path", type=Path, default=DEFAULT_SCAN_PATH, help="Directorio a escanear.")
    p_run.add_argument(
        "--out-dir", type=Path, default=PROJECT_ROOT / "scripts" / "any_audit" / "reports",
        help="Directorio de salida para los reportes.",
    )
    p_run.add_argument("--baseline", type=Path, help="Archivo baseline JSON para comparar.")
    p_run.add_argument(
        "--enforce",
        action="store_true",
        help="Salir con código no-cero si el count supera el baseline (uso en CI).",
    )
    p_run.add_argument(
        "--format", choices=["csv", "json", "md"], default="md",
        help="Formato a imprimir en stdout (los 3 se generan siempre).",
    )
    p_run.set_defaults(func=cmd_run)

    # baseline
    p_base = sub.add_parser("baseline", help="Crea un snapshot baseline.")
    p_base.add_argument("--path", type=Path, default=DEFAULT_SCAN_PATH)
    p_base.add_argument("--out", type=Path, default=PROJECT_ROOT / ".any-baseline.json")
    p_base.set_defaults(func=cmd_baseline)

    # diff
    p_diff = sub.add_parser("diff", help="Compara dos reportes JSON.")
    p_diff.add_argument("before", type=Path, help="Reporte JSON antes.")
    p_diff.add_argument("after", type=Path, help="Reporte JSON después.")
    p_diff.set_defaults(func=cmd_diff)

    # orbital
    p_orb = sub.add_parser(
        "orbital",
        help="Ejecuta auditoría como ciclo del motor Orbital (OVC→TOR→RCC→COD→Espectro).",
    )
    p_orb.add_argument("--path", type=Path, default=DEFAULT_SCAN_PATH, help="Directorio a escanear.")
    p_orb.add_argument(
        "--ticks", type=int, default=5,
        help="Número de ticks orbitales a ejecutar (default: 5).",
    )
    p_orb.add_argument(
        "--out", type=Path,
        default=PROJECT_ROOT / "scripts" / "any_audit" / "reports" / "any_audit_orbital.md",
        help="Archivo de salida para el reporte orbital markdown.",
    )
    p_orb.set_defaults(func=cmd_orbital)

    args = parser.parse_args()
    return args.func(args)


def cmd_orbital(args: argparse.Namespace) -> int:
    """Ejecuta auditoría orbital: integra any_audit con OrbitalEngine."""
    # Asegurar que PROJECT_ROOT está en sys.path para importar src.orbital
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.orbital.any_audit import OrbitalAnyAuditEngine

    print(f"🛰️  Ejecutando auditoría orbital ({args.ticks} ticks)...")
    engine = OrbitalAnyAuditEngine(
        scan_path=args.path,
        ticks=args.ticks,
    )
    result = engine.run_audit()

    print()
    print("═══════════════════════════════════════════════════════════════")
    print(f"  RESULTADO AUDITORÍA ORBITAL")
    print("═══════════════════════════════════════════════════════════════")
    print(f"  Tick orbital final:   {result.tick}")
    print(f"  Total ocurrencias:    {result.total_occurrences}")
    print(f"  Deuda real:           {result.real_debt}")
    print(f"  Justificados:         {result.justified}")
    print(f"  Imports legítimos:    {result.legitimate_imports}")
    print(f"  Hotspots resonantes:  {len(result.hotspots)}")
    print(f"  Top tensiones:        {len(result.top_tensions)}")
    print(f"  Retroalimentación:    {len(result.retrofeedback)} módulos")
    print("═══════════════════════════════════════════════════════════════")
    print()

    if result.hotspots:
        print("=== Hotspots de deuda (resonancia RCC) ===")
        for h in result.hotspots[:5]:
            mods = ", ".join(h["modules"])
            print(f"  {h['cycle']}: {mods} (resonancia={h['resonance']:.4f})")
        print()

    if result.refactor_strategy:
        print("=== Estrategia de refactor (top 5 del espectro) ===")
        for s in result.refactor_strategy[:5]:
            print(f"  {s['module']}: orbital={s['orbital_value']:.4f} deuda_real={s['real_debt']}")
        print()

    # Escribir reporte markdown
    engine.write_orbital_report(result, args.out)
    print(f"✅ Reporte orbital: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
