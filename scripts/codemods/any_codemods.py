"""
Codemods LibCST para migración mecánica de antipatrones `Any`.

Cada codemod es una clase `CSTTransformer` que aplica una transformación
determinística y reversible. Se invocan desde `run_codemod.py`.

Antipatrones cubiertos (en orden de seguridad):
  1. `bare_dict`   — `dict,` → `dict[str, Any],` (mecánico, 893 casos)
  2. `bare_list`   — `list,` → `list[Any],`     (mecánico, 22 casos)
  3. `bare_tuple`  — `tuple,` → `tuple[Any, ...]` (mecánico, 12 casos)
  4. `attribute_init` — `x: Any = None` → `x: Any | None = None` (mantiene Any
     pero documenta la opcionalidad; require revisión manual después)

Antipatrones NO cubiertos (requieren intervención humana):
  - `param_annotation`: depende del dominio, no es mecánico.
  - `return_annotation`: depende del dominio, no es mecánico.
  - `var_annotation`: idem.

Referencias:
  - Skill: .opencode/skills/any-best-practices/SKILL.md
  - Auditar antes/después: python3 scripts/any_audit/any_audit.py run
"""
from __future__ import annotations

from pathlib import Path

import libcst as cst


# Clase base: cst.CSTTransformer (libcst puro, sin dependencia de codemod visitor)
CSTTransformer = cst.CSTTransformer


# ─── Codemod 1: parametrizar `dict` bare ──────────────────────────────────────


class ParametrizeBareDict(CSTTransformer):
    """Reemplaza `dict` sin parámetros por `dict[str, Any]`.

    Contexto: en Zenic-Flujo, el 99% de los `dict` bare son respuestas JSON o
    kwargs de configuración donde la clave es `str`. El valor sí puede ser
    heterogéneo, por eso dejamos `Any` (que es el antipatrón menor y se documenta
    aparte). El objetivo es eliminar el `bare_dict` no discutir el valor aún.

    Casos cubiertos:
      - `def f(x: dict) -> None`        → `def f(x: dict[str, Any]) -> None`
      - `def f() -> dict:`              → `def f() -> dict[str, Any]:`
      - `x: dict = {}`                  → `x: dict[str, Any] = {}`
      - `Dict` (viejo typing) también se parametriza si está bare.

    NO cubre:
      - `dict[str, int]` (ya parametrizado)
      - `dict[str, Any]` (ya parametrizado con Any)
    """

    DESCRIPTION: str = "Parametriza `dict` y `Dict` bare como `dict[str, Any]`."
    MIN_FROM_VERSION = "3.9"

    @staticmethod
    def _is_bare_dict_name(node: cst.BaseExpression) -> bool:
        if isinstance(node, cst.Name) and node.value in {"dict", "Dict"}:
            return True
        # typing.Dict como Attribute
        if isinstance(node, cst.Attribute) and node.attr.value == "Dict":
            return True
        return False

    def leave_Annotation(self, original_node: cst.Annotation, updated_node: cst.Annotation) -> cst.Annotation:
        # La annotation puede ser directamente Name("dict") o Subscript
        annotation = updated_node.annotation

        if self._is_bare_dict_name(annotation):
            # Convertir a Subscript: dict[str, Any]
            new_dict = cst.Name("dict") if isinstance(annotation, cst.Name) and annotation.value == "dict" else annotation
            new_annotation = cst.Subscript(
                value=new_dict,
                slice=[
                    cst.SubscriptElement(slice=cst.Index(value=cst.Name("str"))),
                    cst.SubscriptElement(slice=cst.Index(value=cst.Name("Any"))),
                ],
            )
            return updated_node.with_changes(annotation=new_annotation)

        return updated_node


# ─── Codemod 2: parametrizar `list` bare ──────────────────────────────────────


class ParametrizeBareList(CSTTransformer):
    """Reemplaza `list`/`List` bare por `list[Any]`.

    Casos cubiertos:
      - `def f(x: list) -> None`        → `def f(x: list[Any]) -> None`
      - `def f() -> list:`              → `def f() -> list[Any]:`
      - `x: list = []`                  → `x: list[Any] = []`
    """

    DESCRIPTION: str = "Parametriza `list` y `List` bare como `list[Any]`."

    @staticmethod
    def _is_bare_list_name(node: cst.BaseExpression) -> bool:
        if isinstance(node, cst.Name) and node.value in {"list", "List"}:
            return True
        if isinstance(node, cst.Attribute) and node.attr.value == "List":
            return True
        return False

    def leave_Annotation(self, original_node: cst.Annotation, updated_node: cst.Annotation) -> cst.Annotation:
        annotation = updated_node.annotation

        if self._is_bare_list_name(annotation):
            new_list = (
                cst.Name("list")
                if isinstance(annotation, cst.Name) and annotation.value == "list"
                else annotation
            )
            new_annotation = cst.Subscript(
                value=new_list,
                slice=[cst.SubscriptElement(slice=cst.Index(value=cst.Name("Any")))],
            )
            return updated_node.with_changes(annotation=new_annotation)

        return updated_node


# ─── Codemod 3: parametrizar `tuple` bare ─────────────────────────────────────


class ParametrizeBareTuple(CSTTransformer):
    """Reemplaza `tuple`/`Tuple` bare por `tuple[Any, ...]`.

    Casos cubiertos:
      - `def f(x: tuple) -> None`        → `def f(x: tuple[Any, ...]) -> None`
      - `def f() -> tuple:`              → `def f() -> tuple[Any, ...]:`
    """

    DESCRIPTION: str = "Parametriza `tuple` y `Tuple` bare como `tuple[Any, ...]`."

    @staticmethod
    def _is_bare_tuple_name(node: cst.BaseExpression) -> bool:
        if isinstance(node, cst.Name) and node.value in {"tuple", "Tuple"}:
            return True
        if isinstance(node, cst.Attribute) and node.attr.value == "Tuple":
            return True
        return False

    def leave_Annotation(self, original_node: cst.Annotation, updated_node: cst.Annotation) -> cst.Annotation:
        annotation = updated_node.annotation

        if self._is_bare_tuple_name(annotation):
            new_tuple = (
                cst.Name("tuple")
                if isinstance(annotation, cst.Name) and annotation.value == "tuple"
                else annotation
            )
            # tuple[Any, ...]  — el `...` se construye con cst.Index(value=cst.Ellipsis())
            new_annotation = cst.Subscript(
                value=new_tuple,
                slice=[
                    cst.SubscriptElement(slice=cst.Index(value=cst.Name("Any"))),
                    cst.SubscriptElement(slice=cst.Index(value=cst.Ellipsis())),
                ],
            )
            return updated_node.with_changes(annotation=new_annotation)

        return updated_node


# ─── Codemod 4: añadir `| None` a atributos `x: Any = None` ──────────────────


class DocumentOptionalAnyAttribute(CSTTransformer):
    """Transforma `x: T = None` → `x: T | None = None` cuando T es Any o una colección bare.

    NO elimina el `Any` (eso requiere decisión de dominio). Solo documenta que
    el atributo es opcional, alineándolo con la skill §2.5 que dice:
    `client: Any = None` → `client: HTTPClient | None = None`.

    El siguiente paso (manual) sería reemplazar `Any` por el tipo concreto.
    Este codemod es el preamble mecánico.

    Casos cubiertos:
      - `client: Any = None`            → `client: Any | None = None`
      - `self.x: Any = None`            → `self.x: Any | None = None`
      - `config: dict = None`           → `config: dict | None = None` (luego el combo lo deja como dict[str, Any] | None)
      - `items: list = None`            → `items: list | None = None`

    NO cubre:
      - `x: Any = "default"` (no es None, no es opcional)
      - `x: Any` sin asignación (ya es var_annotation)
      - `x: HTTPClient = None` (tipo concreto, no lo toca; dejamos al humano decidir si añadir | None)
    """

    DESCRIPTION: str = "Añade `| None` a atributos `x: T = None` donde T es Any o colección bare."

    # Tipos que este codemod documento como opcionales (Any + colecciones bare)
    TARGET_TYPES = {"Any", "dict", "Dict", "list", "List", "tuple", "Tuple", "set", "Set"}

    def leave_AnnAssign(self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign) -> cst.BaseSmallStatement:
        annotation = updated_node.annotation.annotation

        # Solo Name de tipos objetivo (no Subscript ya parametrizado)
        if not (isinstance(annotation, cst.Name) and annotation.value in self.TARGET_TYPES):
            return updated_node

        # Solo si el valor es None
        value = updated_node.value
        if value is None:
            return updated_node
        if not (isinstance(value, cst.BaseExpression) and _is_none_literal(value)):
            return updated_node

        # Si la anotación ya es `X | None` (BinOperation con BitOr y None a la derecha), no tocar
        if isinstance(annotation, cst.BinaryOperation):
            return updated_node

        # Construir `T | None`
        new_annotation_expr = cst.BinaryOperation(
            left=annotation,
            operator=cst.BitOr(),
            right=cst.Name("None"),
        )
        new_annotation = updated_node.annotation.with_changes(annotation=new_annotation_expr)
        return updated_node.with_changes(annotation=new_annotation)


def _is_none_literal(node: cst.BaseExpression) -> bool:
    """True si el nodo es el literal `None`."""
    return isinstance(node, cst.Name) and node.value == "None"


# ─── Codemod 5: Combo — aplica los 4 anteriores en secuencia ─────────────────


class AutoMigrateBareCollections(CSTTransformer):
    """Aplica ParametrizeBareDict + ParametrizeBareList + ParametrizeBareTuple
    + DocumentOptionalAnyAttribute en una sola pasada.

    Útil para un primer barrido mecánico seguro antes de intervención humana.

    Orden de aplicación dentro de cada nodo:
      1. leave_AnnAssign: aplica DocumentOptionalAnyAttribute (añade | None si value=None)
      2. leave_Annotation: aplica parametrización de dict/list/tuple bare

    Así, `config: dict = None` primero se convierte en `config: dict | None = None`
    y luego el `dict` dentro de la BinaryOperation se parametriza a `dict[str, Any]`,
    resultando en `config: dict[str, Any] | None = None`.
    """

    DESCRIPTION: str = "Combo: parametriza dict/list/tuple bare + documenta Any = None."

    def __init__(self) -> None:
        super().__init__()
        self._dict = ParametrizeBareDict()
        self._list = ParametrizeBareList()
        self._tuple = ParametrizeBareTuple()
        self._attr = DocumentOptionalAnyAttribute()

    def leave_AnnAssign(self, original_node: cst.AnnAssign, updated_node: cst.AnnAssign) -> cst.BaseSmallStatement:
        """Después de que leave_Annotation ya parametrizó la anotación,
        añadimos `| None` si el valor es None y la anotación es:
          - Name("Any")
          - Subscript de dict/list/tuple/set bare recién parametrizado
        """
        # Solo si el valor es None
        value = updated_node.value
        if value is None or not _is_none_literal(value):
            return updated_node

        annotation_expr = updated_node.annotation.annotation

        # Si ya es BinOperation (X | None), no tocar
        if isinstance(annotation_expr, cst.BinaryOperation):
            return updated_node

        # Caso 1: Name("Any") — aplicar _attr
        if isinstance(annotation_expr, cst.Name) and annotation_expr.value == "Any":
            return self._attr.leave_AnnAssign(original_node, updated_node)

        # Caso 2: Subscript de dict/list/tuple/set recién parametrizado
        # (leave_Annotation ya lo convirtió de `dict` a `dict[str, Any]`)
        if isinstance(annotation_expr, cst.Subscript):
            base_value = annotation_expr.value
            if isinstance(base_value, cst.Name) and base_value.value in {
                "dict", "Dict", "list", "List", "tuple", "Tuple", "set", "Set"
            }:
                # Envolver en `X | None`
                new_annotation_expr = cst.BinaryOperation(
                    left=annotation_expr,
                    operator=cst.BitOr(),
                    right=cst.Name("None"),
                )
                new_annotation = updated_node.annotation.with_changes(annotation=new_annotation_expr)
                return updated_node.with_changes(annotation=new_annotation)

        # Caso 3: Name de colección bare que leave_Annotation NO tocó
        # (raro, pero por si acaso)
        if isinstance(annotation_expr, cst.Name) and annotation_expr.value in {
            "dict", "Dict", "list", "List", "tuple", "Tuple", "set", "Set"
        }:
            return self._attr.leave_AnnAssign(original_node, updated_node)

        return updated_node

    def _parametrize_annotation(self, annotation: cst.BaseExpression) -> cst.BaseExpression:
        """Aplica parametrización recursivamente a un nodo de anotación.

        Maneja Name directo y Name dentro de BinaryOperation (X | None).
        """
        # Caso directo: Name("dict") / Name("list") / Name("tuple")
        if isinstance(annotation, cst.Name) and annotation.value in {"dict", "Dict"}:
            return self._parametrize_dict_name(annotation)
        if isinstance(annotation, cst.Name) and annotation.value in {"list", "List"}:
            return self._parametrize_list_name(annotation)
        if isinstance(annotation, cst.Name) and annotation.value in {"tuple", "Tuple"}:
            return self._parametrize_tuple_name(annotation)

        # Caso BinaryOperation (X | None): parametrizar el left si es bare
        if isinstance(annotation, cst.BinaryOperation):
            left = annotation.left
            new_left = left
            if isinstance(left, cst.Name):
                if left.value in {"dict", "Dict"}:
                    new_left = self._parametrize_dict_name(left)
                elif left.value in {"list", "List"}:
                    new_left = self._parametrize_list_name(left)
                elif left.value in {"tuple", "Tuple"}:
                    new_left = self._parametrize_tuple_name(left)
            if new_left is not left:
                return annotation.with_changes(left=new_left)
        return annotation

    def _parametrize_dict_name(self, name_node: cst.Name) -> cst.BaseExpression:
        """Construye dict[str, Any] preservando `Dict` legacy si venía así."""
        base = cst.Name("dict") if name_node.value == "dict" else name_node
        return cst.Subscript(
            value=base,
            slice=[
                cst.SubscriptElement(slice=cst.Index(value=cst.Name("str"))),
                cst.SubscriptElement(slice=cst.Index(value=cst.Name("Any"))),
            ],
        )

    def _parametrize_list_name(self, name_node: cst.Name) -> cst.BaseExpression:
        base = cst.Name("list") if name_node.value == "list" else name_node
        return cst.Subscript(
            value=base,
            slice=[cst.SubscriptElement(slice=cst.Index(value=cst.Name("Any")))],
        )

    def _parametrize_tuple_name(self, name_node: cst.Name) -> cst.BaseExpression:
        base = cst.Name("tuple") if name_node.value == "tuple" else name_node
        return cst.Subscript(
            value=base,
            slice=[
                cst.SubscriptElement(slice=cst.Index(value=cst.Name("Any"))),
                cst.SubscriptElement(slice=cst.Index(value=cst.Ellipsis())),
            ],
        )

    def leave_Annotation(self, original_node: cst.Annotation, updated_node: cst.Annotation) -> cst.Annotation:
        annotation = updated_node.annotation
        new_annotation = self._parametrize_annotation(annotation)
        if new_annotation is not annotation:
            return updated_node.with_changes(annotation=new_annotation)
        return updated_node


# ─── Helpers para invocación ──────────────────────────────────────────────────


def list_codemods() -> dict[str, type[CSTTransformer]]:
    """Retorna los codemods disponibles por nombre."""
    return {
        "parametrize-bare-dict": ParametrizeBareDict,
        "parametrize-bare-list": ParametrizeBareList,
        "parametrize-bare-tuple": ParametrizeBareTuple,
        "document-optional-any-attr": DocumentOptionalAnyAttribute,
        "auto-migrate-bare": AutoMigrateBareCollections,
    }


def transform_module(source: str, codemod_class: type[CSTTransformer]) -> str:
    """Aplica un codemod al código fuente y retorna el resultado."""
    module = cst.parse_module(source)
    transformer = codemod_class()
    new_module = module.visit(transformer)
    return new_module.code


def transform_file(path: Path, codemod_class: type[CSTTransformer], *, dry_run: bool = False) -> bool:
    """Aplica un codemod a un archivo. Retorna True si hubo cambios.

    Args:
        path: ruta al archivo .py
        codemod_class: clase del codemod a aplicar
        dry_run: si True, no escribe cambios; solo reporta

    Returns:
        True si el archivo fue modificado (o lo sería en dry_run).
    """
    source = path.read_text(encoding="utf-8")
    new_source = transform_module(source, codemod_class)
    if new_source == source:
        return False
    if not dry_run:
        path.write_text(new_source, encoding="utf-8")
    return True
