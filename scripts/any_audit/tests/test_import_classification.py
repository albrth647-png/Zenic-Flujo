"""Tests para la reclasificación de import_any en any_audit.

Verifica que:
  - import de Any usado en el archivo → legitimate_import_any (justified)
  - import de Any NO usado en el archivo → unused_import_any (debt)
  - import de Any + dict[str, Any] → legitimate (uso en annotation)
  - import de Any + cast(Any, x) → legitimate (uso en cast)
  - import de Any + typing.Any → legitimate (uso cualificado)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from any_audit import scan_file  # type: ignore[import-not-found]


def _write_and_scan(source: str) -> list:
    """Escribe source a un archivo temporal dentro del proyecto y lo escanea."""
    # Usar un directorio temporal dentro del proyecto para que _module_for_file funcione
    tmp_dir = Path(__file__).resolve().parent / "_tmp_test_files"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", dir=tmp_dir, delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        path = Path(f.name)
    try:
        return scan_file(path)
    finally:
        path.unlink()


def _count_antipatterns(occurrences: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for occ in occurrences:
        counts[occ.antipattern] = counts.get(occ.antipattern, 0) + 1
    return counts


# ─── Tests: import + uso → legitimate ────────────────────────────────────────


def test_import_with_annotation_usage_is_legitimate() -> None:
    """from typing import Any + def f(x: Any) → legitimate_import_any."""
    src = (
        "from typing import Any\n"
        "\n"
        "def f(x: Any) -> None:\n"
        "    pass\n"
    )
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("legitimate_import_any") == 1
    assert counts.get("unused_import_any", 0) == 0
    assert counts.get("param_annotation") == 1


def test_import_with_dict_str_any_is_legitimate() -> None:
    """from typing import Any + def f() -> dict[str, Any] → legitimate."""
    src = (
        "from typing import Any\n"
        "\n"
        "def f() -> dict[str, Any]:\n"
        "    return {}\n"
    )
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("legitimate_import_any") == 1
    assert counts.get("unused_import_any", 0) == 0


def test_import_with_cast_usage_is_legitimate() -> None:
    """from typing import Any + x = cast(Any, val) → legitimate."""
    src = (
        "from typing import Any, cast\n"
        "\n"
        "x = cast(Any, 42)\n"
    )
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("legitimate_import_any") == 1
    assert counts.get("unused_import_any", 0) == 0


def test_import_with_typing_any_attribute_is_legitimate() -> None:
    """import typing + typing.Any usage → legitimate (no genera unused)."""
    src = (
        "import typing\n"
        "\n"
        "def f() -> typing.Any:\n"
        "    return None\n"
    )
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("unused_import_any", 0) == 0


# ─── Tests: import sin uso → unused_import_any ───────────────────────────────


def test_import_without_usage_is_unused() -> None:
    """from typing import Any sin usar → unused_import_any."""
    src = (
        "from typing import Any\n"
        "\n"
        "def f(x: int) -> None:\n"
        "    pass\n"
    )
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("unused_import_any") == 1
    assert counts.get("legitimate_import_any", 0) == 0


def test_import_any_alone_no_other_code_is_unused() -> None:
    """from typing import Any solo, sin nada más → unused."""
    src = "from typing import Any\n"
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("unused_import_any") == 1


# ─── Tests: justificación ────────────────────────────────────────────────────


def test_legitimate_import_is_justified() -> None:
    """legitimate_import_any debe tener is_justified=True."""
    src = (
        "from typing import Any\n"
        "\n"
        "def f(x: Any) -> None:\n"
        "    pass\n"
    )
    occurrences = _write_and_scan(src)
    legit = [o for o in occurrences if o.antipattern == "legitimate_import_any"]
    assert len(legit) == 1
    assert legit[0].is_justified is True
    assert legit[0].justification is not None


def test_unused_import_is_not_justified() -> None:
    """unused_import_any debe tener is_justified=False."""
    src = "from typing import Any\n"
    occurrences = _write_and_scan(src)
    unused = [o for o in occurrences if o.antipattern == "unused_import_any"]
    assert len(unused) == 1
    assert unused[0].is_justified is False


# ─── Tests: casos edge ───────────────────────────────────────────────────────


def test_multiple_imports_with_any_used() -> None:
    """from typing import Any, Optional, List + uso de Any → legitimate."""
    src = (
        "from typing import Any, List, Optional\n"
        "\n"
        "def f(x: Optional[Any] = None) -> List[int]:\n"
        "    return []\n"
    )
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("legitimate_import_any") == 1
    assert counts.get("unused_import_any", 0) == 0


def test_multiline_import_with_any_used() -> None:
    """from typing import (\n  Any,\n  List,\n) + uso → legitimate."""
    src = (
        "from typing import (\n"
        "    Any,\n"
        "    List,\n"
        ")\n"
        "\n"
        "def f(x: Any) -> List[int]:\n"
        "    return []\n"
    )
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("legitimate_import_any") == 1
    assert counts.get("unused_import_any", 0) == 0


def test_any_in_string_comment_does_not_count_as_usage() -> None:
    """Comentario mencionando Any no debe contar como uso."""
    src = (
        "from typing import Any\n"
        "\n"
        "# This uses Any internally but not really\n"
        "def f(x: int) -> None:\n"
        "    pass\n"
    )
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("unused_import_any") == 1


def test_any_in_docstring_does_not_count_as_usage() -> None:
    """Docstring mencionando Any no debe contar como uso."""
    src = (
        '"""Module that uses Any in docstring only."""\n'
        "from typing import Any\n"
        "\n"
        "def f(x: int) -> None:\n"
        '    """Does something with Any."""\n'
        "    pass\n"
    )
    occurrences = _write_and_scan(src)
    counts = _count_antipatterns(occurrences)
    assert counts.get("unused_import_any") == 1
