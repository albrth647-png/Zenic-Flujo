#!/usr/bin/env python3
r"""
Pre-commit hook: Any Ratchet (anti-deuda para ``typing.Any``)
================================================================

Bloquea commits que introduzcan **nuevos** usos de ``Any`` sin justificación
en archivos ``.py`` dentro de ``src/`` (excluyendo ``src/core/`` y
``src/tests/``).

Filosofía *ratchet*: la deuda técnica existente (registrada en
``.any-baseline.json``) se audita globalmente en CI; este hook local solo
impide que la deuda **crezca** commit a commit. No reimplementa la auditoría
global — es una primera línea de defensa rápida y local.

Detección
---------
- Parsea cada archivo staged con :mod:`ast` (no regex).
- Detecta ``Any`` en anotaciones de params, retornos, variables, atributos,
  ``cast(Any, ...)``, imports explícitos y colecciones sin parametrizar
  (``dict`` / ``list`` / ``tuple`` / ``set`` bare).
- Considera justificado un ``Any`` si en la misma línea o en la anterior
  aparece alguno de: ``# legítimo:``, ``# legitimo:``, ``# TODO: tipar``,
  ``# type: ignore``.
- Compara el contenido staged (``git show :<file>``) contra ``HEAD``
  (``git show HEAD:<file>``) y reporta **solo** las ocurrencias en líneas
  nuevas o modificadas (vía :mod:`difflib`).

Uso
----
Configurado en ``.pre-commit-config.yaml``:

.. code-block:: yaml

    - repo: local
      hooks:
        - id: any-ratchet
          name: Any Ratchet (bloquea Any nuevos sin justificación)
          entry: python3 scripts/hooks/pre_commit_any_ratchet.py
          language: system
          files: ^src/.*\.py$
          exclude: ^src/(core|tests)/.*
          pass_filenames: true

Standalone (sin pre-commit):

.. code-block:: bash

    python3 scripts/hooks/pre_commit_any_ratchet.py src/foo.py src/bar.py
    # o vía stdin:
    echo "src/foo.py" | python3 scripts/hooks/pre_commit_any_ratchet.py

Bypass
-------
- Env var ``ANY_RATCHET_ALLOW=1`` emite un warning y permite el commit.
- En CI, label ``any-bypass`` en el PR salta el ``--enforce`` del audit global.

Exit codes
-----------
- ``0`` — sin regresiones (o bypass activo).
- ``1`` — hay nuevos ``Any`` injustificados.
- ``2`` — error de uso / argumentos.

Referencias
------------
- Skill: ``.opencode/skills/any-best-practices/SKILL.md``
- Auditoría global: ``scripts/any_audit/any_audit.py``
- Plan: ``docs/plans/any-ratchet-setup.md``
"""
from __future__ import annotations

import argparse
import ast
import difflib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# ─── Configuración ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Marcadores que justifican un Any (alineados con any_audit.py).
JUSTIFICATION_MARKERS: tuple[str, ...] = (
    "# legítimo",
    "# legitimo",
    "# TODO: tipar",
    "# type: ignore",
)

# Partes de ruta excluidas del scope del ratchet (igual que any_audit.py).
EXCLUDE_DIR_PARTS: frozenset[str] = frozenset({"core", "tests"})


# ─── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnyOccurrence:
    """Una ocurrencia individual de ``Any`` en un archivo."""

    file: str
    line: int  # 1-based
    col: int  # 1-based
    antipattern: str
    context: str
    is_justified: bool


# ─── Sugerencias de reemplazo ─────────────────────────────────────────────────

SUGGESTIONS: dict[str, str] = {
    "param_annotation": "Usa `object`, un `Protocol`, o un `TypeVar` en vez de `Any`.",
    "return_annotation": "Retorna un tipo concreto o `TypeVar`; evita `Any` como retorno.",
    "attribute_init": "Usa `X | None = None` en vez de `Any` para atributos.",
    "bare_dict": "Parametriza: `dict[K, V]`.",
    "bare_list": "Parametriza: `list[T]`.",
    "bare_tuple": "Parametriza: `tuple[X, ...]`.",
    "bare_set": "Parametriza: `set[T]`.",
    "var_annotation": "Usa un tipo concreto o `object`; `Any` desactiva el type-checking.",
    "cast_call": "Revisa si `cast(Any, ...)` es realmente necesario.",
    "import_any": "El import es legítimo solo si `Any` se usa; revisa usos.",
    "other_any": "Revisa este uso de `Any`; prefiere tipos concretos o `object`.",
}


# ─── Detección AST ────────────────────────────────────────────────────────────


def _is_any_node(node: ast.AST) -> bool:
    """True si ``node`` es una referencia a ``Any`` (``Name`` o ``Attribute``)."""
    if isinstance(node, ast.Name) and node.id == "Any":
        return True
    if isinstance(node, ast.Attribute) and node.attr == "Any":
        return True
    return False


def _is_bare_collection(node: ast.AST) -> str | None:
    """Detecta ``dict`` / ``list`` / ``tuple`` / ``set`` sin parametrizar."""
    if isinstance(node, ast.Name) and node.id in {"dict", "list", "tuple", "set", "frozenset"}:
        return node.id
    return None


def _has_justification(lines: list[str], lineno: int) -> bool:
    """True si hay un marker de justificación en la línea ``lineno`` o la anterior.

    ``lineno`` es 1-based. Busca los markers definidos en
    :data:`JUSTIFICATION_MARKERS` como subcadenas (case-sensitive, ya que
    los markers incluyen mayúsculas/minúsculas intencionales).
    """
    # Misma línea
    if 1 <= lineno <= len(lines):
        same_line = lines[lineno - 1]
        for marker in JUSTIFICATION_MARKERS:
            if marker in same_line:
                return True
    # Línea anterior
    if lineno - 2 >= 0:
        prev_line = lines[lineno - 2]
        for marker in JUSTIFICATION_MARKERS:
            if marker in prev_line:
                return True
    return False


class AnyDetector(ast.NodeVisitor):
    """Visitor AST que colecciona ocurrencias de ``Any`` en un archivo.

    La detección está alineada con ``any_audit.AnyVisitor`` para mantener
    consistencia entre el hook local y la auditoría global, pero se
    reimplementa aquí para mantener el hook autocontenido (sin imports
    cruzados) y fácil de testear.
    """

    def __init__(self, file: str, lines: list[str]) -> None:
        self.file = file
        self.lines = lines
        self.occurrences: list[AnyOccurrence] = []

    def _add(self, node: ast.AST, antipattern: str) -> None:
        lineno = node.lineno
        context = self.lines[lineno - 1].strip() if 1 <= lineno <= len(self.lines) else ""
        if len(context) > 120:
            context = context[:117] + "..."
        self.occurrences.append(
            AnyOccurrence(
                file=self.file,
                line=lineno,
                col=node.col_offset + 1,
                antipattern=antipattern,
                context=context,
                is_justified=_has_justification(self.lines, lineno),
            )
        )

    def visit_arg(self, node: ast.arg) -> None:
        """Parámetro de función con anotación ``Any`` o colección bare."""
        if node.annotation is not None:
            if _is_any_node(node.annotation):
                self._add(node, "param_annotation")
            else:
                bare = _is_bare_collection(node.annotation)
                if bare:
                    self._add(node, f"bare_{bare}")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Retorno ``-> Any`` o ``-> dict`` / ``-> list`` sin parametrizar."""
        if node.returns is not None:
            if _is_any_node(node.returns):
                self._add(node, "return_annotation")
            else:
                bare = _is_bare_collection(node.returns)
                if bare:
                    self._add(node, f"bare_{bare}")
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """``x: Any = ...`` o ``x: dict = ...`` sin parametrizar."""
        if _is_any_node(node.annotation):
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                self._add(node, "attribute_init")
            else:
                self._add(node, "var_annotation")
        else:
            bare = _is_bare_collection(node.annotation)
            if bare:
                self._add(node, f"bare_{bare}")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Detecta ``cast(Any, ...)`` dentro de asignaciones."""
        for sub in ast.walk(node.value):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "cast"
                and sub.args
                and _is_any_node(sub.args[0])
            ):
                self._add(node, "cast_call")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """``from typing import Any`` — registro informativo."""
        for alias in node.names:
            if alias.name == "Any":
                self._add(node, "import_any")
        self.generic_visit(node)


def detect_any_in_source(file: str, source: str) -> list[AnyOccurrence]:
    """Parsea ``source`` y retorna todas las ocurrencias de ``Any``.

    Si el source tiene errores de sintaxis, retorna lista vacía (no bloquea
    el commit por sintaxis — eso es trabajo de ruff/mypy).
    """
    try:
        tree = ast.parse(source, filename=file)
    except SyntaxError:
        return []
    lines = source.splitlines()
    visitor = AnyDetector(file=file, lines=lines)
    visitor.visit(tree)
    return visitor.occurrences


# ─── Git helpers ──────────────────────────────────────────────────────────────


def _git(args: Sequence[str], cwd: Path) -> tuple[int, str, str]:
    """Ejecuta un subcomando git y retorna (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def get_staged_content(filepath: str, project_root: Path) -> str | None:
    """Retorna el contenido staged (index) de ``filepath``, o None si falla.

    Usa ``git show :<file>``. Si el archivo no está en el index, retorna None.
    """
    code, out, _ = _git(["show", f":{filepath}"], project_root)
    if code != 0:
        return None
    return out


def get_head_content(filepath: str, project_root: Path) -> str | None:
    """Retorna el contenido de ``filepath`` en HEAD, o None si no existe en HEAD.

    None indica que el archivo es nuevo (sin versión en HEAD), por lo que
    todas sus líneas se consideran "nuevas".
    """
    code, out, _ = _git(["show", f"HEAD:{filepath}"], project_root)
    if code != 0:
        return None
    return out


# ─── Diff de líneas nuevas ────────────────────────────────────────────────────


def compute_new_lines(head_lines: list[str], staged_lines: list[str]) -> set[int]:
    """Retorna el conjunto de líneas (1-based) en ``staged_lines`` que son
    nuevas o modificadas respecto a ``head_lines``.

    Usa :class:`difflib.SequenceMatcher` para alinear las secuencias. Los
    bloques marcados como ``insert`` o ``replace`` producen líneas nuevas
    en la versión staged.
    """
    if not head_lines:
        # Archivo nuevo: todas las líneas son nuevas.
        return {i + 1 for i in range(len(staged_lines))}

    matcher = difflib.SequenceMatcher(a=head_lines, b=staged_lines, autojunk=False)
    new_lines: set[int] = set()
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            for j in range(j1, j2):
                new_lines.add(j + 1)  # 1-based
    return new_lines


# ─── Filtro de scope ──────────────────────────────────────────────────────────


def is_in_scope(filepath: str) -> bool:
    """True si ``filepath`` es ``.py`` bajo ``src/`` excluyendo ``src/core`` y ``src/tests``.

    Acepta rutas con o sin prefijo ``./`` y con separadores normalizados.
    """
    normalized = filepath.replace("\\", "/").lstrip("./")
    if not normalized.startswith("src/"):
        return False
    if not normalized.endswith(".py"):
        return False
    parts = normalized.split("/")
    # parts[0] == "src"; revisar que ningún subdir esté en EXCLUDE_DIR_PARTS
    for part in parts[1:]:
        if part in EXCLUDE_DIR_PARTS:
            return False
    return True


# ─── Lógica principal de chequeo ──────────────────────────────────────────────


def check_file(filepath: str, project_root: Path) -> list[AnyOccurrence]:
    """Chequea un único archivo y retorna las ocurrencias de ``Any`` que son:
    - nuevas o modificadas (línea en ``compute_new_lines``), Y
    - no justificadas.

    Si no se puede leer el contenido staged, retorna lista vacía (no bloquea).
    """
    if not is_in_scope(filepath):
        return []

    staged = get_staged_content(filepath, project_root)
    if staged is None:
        # No está staged (¿eliminado? ¿sin index?) — leer de disco como fallback.
        disk_path = project_root / filepath
        try:
            staged = disk_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []

    head = get_head_content(filepath, project_root)
    head_lines = head.splitlines() if head is not None else []
    staged_lines = staged.splitlines()

    new_line_set = compute_new_lines(head_lines, staged_lines)
    if not new_line_set:
        return []

    occurrences = detect_any_in_source(filepath, staged)
    # Filtrar: solo líneas nuevas Y no justificadas.
    return [o for o in occurrences if o.line in new_line_set and not o.is_justified]


def check_files(filepaths: Iterable[str], project_root: Path) -> list[AnyOccurrence]:
    """Chequea múltiples archivos y retorna todas las violaciones."""
    violations: list[AnyOccurrence] = []
    for fp in filepaths:
        fp = fp.strip()
        if not fp:
            continue
        violations.extend(check_file(fp, project_root))
    return violations


# ─── Reporte ──────────────────────────────────────────────────────────────────


def format_violations(violations: list[AnyOccurrence]) -> str:
    """Formatea las violaciones como un mensaje legible para el usuario."""
    if not violations:
        return ""
    lines: list[str] = []
    lines.append("")
    lines.append("❌ Any Ratchet: se detectaron {} nuevo(s) `Any` sin justificación.".format(len(violations)))
    lines.append("   La deuda existente se audita en CI; este hook impide que crezca commit a commit.")
    lines.append("")
    # Agrupar por archivo
    by_file: dict[str, list[AnyOccurrence]] = {}
    for v in violations:
        by_file.setdefault(v.file, []).append(v)
    for file, occs in sorted(by_file.items()):
        lines.append(f"  📄 {file}")
        for o in sorted(occs, key=lambda x: x.line):
            suggestion = SUGGESTIONS.get(o.antipattern, SUGGESTIONS["other_any"])
            lines.append(f"     L{o.line}:{o.col}  [{o.antipattern}]  {o.context}")
            lines.append(f"       → {suggestion}")
            lines.append(f"       (o justifica con: `# legítimo: <razón>` / `# TODO: tipar` / `# type: ignore`)")
    lines.append("")
    lines.append("Bypass temporal: ANY_RATCHET_ALLOW=1 git commit ...")
    lines.append("Doc: docs/plans/any-ratchet-setup.md")
    lines.append("")
    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────


def _read_stdin_files() -> list[str]:
    """Lee filenames de stdin (una ruta por línea), útil para uso standalone."""
    if sys.stdin.isatty():
        return []
    return [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    """Entry point del pre-commit hook.

    Args:
        argv: Argumentos CLI (default: ``sys.argv[1:]``).

    Returns:
        0 si no hay regresiones (o bypass activo), 1 si las hay, 2 si error
        de uso.
    """
    parser = argparse.ArgumentParser(
        prog="any-ratchet",
        description=(
            "Bloquea commits que introduzcan nuevos `Any` sin justificación "
            "en src/ (excluye src/core/ y src/tests/)."
        ),
    )
    parser.add_argument(
        "files",
        nargs="*",
        help=(
            "Archivos a chequear (pasados por pre-commit con pass_filenames: true). "
            "Si se omite, se leen rutas de stdin."
        ),
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Directorio raíz del repo git (default: cwd).",
    )
    args = parser.parse_args(argv)

    # Bypass por env var
    if os.environ.get("ANY_RATCHET_ALLOW") == "1":
        print(
            "⚠️  ANY_RATCHET_ALLOW=1 — Any Ratchet en bypass. "
            "Recuerda justificar o tipar los Any nuevos en un próximo commit.",
            file=sys.stderr,
        )
        return 0

    # Recolectar archivos: argv primero, luego stdin si argv vacío.
    filepaths: list[str] = list(args.files)
    if not filepaths:
        filepaths = _read_stdin_files()

    if not filepaths:
        # Nada que chequear (pre-commit puede invocar sin archivos en algunos
        # escenarios con pass_filenames: true si el filtro no matchea).
        return 0

    project_root = args.project_root.resolve()
    violations = check_files(filepaths, project_root)

    if not violations:
        # Mensaje silencioso de éxito solo si hubo archivos en scope.
        in_scope = [fp for fp in filepaths if is_in_scope(fp.strip())]
        if in_scope:
            print(f"✅ Any Ratchet: sin nuevos `Any` injustificados en {len(in_scope)} archivo(s).")
        return 0

    print(format_violations(violations), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
