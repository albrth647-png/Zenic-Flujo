"""
Test de verificacion para bug O2 — OrbitalCompiler manipula atributos privados.

Antes del fix: ``OrbitalCompiler.compile`` accedia directamente a
``self._orbital_engine._ovc._variables`` (linea 268) y
``self._orbital_engine._rcc._cycles`` (lineas 270, 272) para eliminar variables
y ciclos de compilaciones anteriores. Esto rompe encapsulamiento y, segun el
catalogo, NO invalida el cache TOR asociado.

Despues del fix:
- ``OrbitalEngine`` expone ``delete_variable(name)``, ``delete_variables_by_prefix(prefix)``,
  ``delete_cycle(cycle_id)`` y ``get_cycle_ids()`` como metodos publicos.
- ``OrbitalCompiler.compile`` usa estos metodos en vez de manipular atributos privados.
- El comportamiento funcional del compiler es identico (no rompe el contrato).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from src.orbital.engine import OrbitalEngine
from src.orbital.orbital_compiler import OrbitalCompiler


class TestBugO2OrbitalEngineExposesPublicMethods:
    """OrbitalEngine debe exonerar public methods para delete/get variables y cycles."""

    def test_engine_has_delete_variable_method(self) -> None:
        """OrbitalEngine debe tener un metodo publico delete_variable(name)."""
        assert hasattr(OrbitalEngine, "delete_variable"), (
            "OrbitalEngine debe exponer delete_variable(name) como metodo publico. "
            "Sin esto, los callers acceden a _ovc._variables directamente (BUG-O2)."
        )
        assert callable(OrbitalEngine.delete_variable)

    def test_engine_has_delete_cycle_method(self) -> None:
        """OrbitalEngine debe tener un metodo publico delete_cycle(cycle_id)."""
        assert hasattr(OrbitalEngine, "delete_cycle"), (
            "OrbitalEngine debe exponer delete_cycle(cycle_id) como metodo publico. "
            "Sin esto, los callers acceden a _rcc._cycles directamente (BUG-O2)."
        )
        assert callable(OrbitalEngine.delete_cycle)

    def test_engine_has_get_cycle_ids_method(self) -> None:
        """OrbitalEngine debe tener un metodo publico get_cycle_ids() para iterar IDs."""
        assert hasattr(OrbitalEngine, "get_cycle_ids"), (
            "OrbitalEngine debe exponer get_cycle_ids() como metodo publico. "
            "Sin esto, los callers acceden a _rcc._cycles.keys() directamente (BUG-O2)."
        )
        assert callable(OrbitalEngine.get_cycle_ids)

    def test_engine_delete_variable_removes_from_ovc(self) -> None:
        """delete_variable debe eliminar la variable del OVC."""
        engine = OrbitalEngine()
        engine.create_variable("var_test_o2", theta=0.5, amplitude=1.0, velocity=0.1)
        assert engine.get_variable("var_test_o2") is not None
        result = engine.delete_variable("var_test_o2")
        assert result is True, "delete_variable debe retornar True si la variable existia"
        assert engine.get_variable("var_test_o2") is None

    def test_engine_delete_variable_returns_false_for_missing(self) -> None:
        """delete_variable debe retornar False si la variable no existe."""
        engine = OrbitalEngine()
        result = engine.delete_variable("var_inexistente_o2")
        assert result is False

    def test_engine_delete_cycle_removes_from_rcc(self) -> None:
        """delete_cycle debe eliminar el ciclo del RCC."""
        engine = OrbitalEngine()
        engine.create_variable("v1", theta=0.0, amplitude=1.0, velocity=0.1)
        engine.create_variable("v2", theta=0.5, amplitude=1.0, velocity=0.1)
        engine.create_cycle("ciclo_test_o2", ["v1", "v2"], threshold=0.5)
        ids_antes = engine.get_cycle_ids()
        # El ID interno del ciclo lo asigna CicloOrbital (UUID-like).
        # Pero el nombre registrado en RCC es "ciclo_test_o2" — el ID se obtiene
        # del propio CicloOrbital.
        ciclo = engine.rcc.get_cycles()
        assert any(c.name == "ciclo_test_o2" for c in ciclo.values())
        # Tomar el ID real del ciclo recien creado.
        ciclo_id = next(cid for cid, c in ciclo.items() if c.name == "ciclo_test_o2")
        engine.delete_cycle(ciclo_id)
        ids_despues = engine.get_cycle_ids()
        assert ciclo_id not in ids_despues, (
            f"delete_cycle no elimino el ciclo {ciclo_id!r}. "
            f"IDs antes: {ids_antes}, despues: {ids_despues}"
        )


class TestBugO2OrbitalCompilerDoesNotAccessPrivateAttributes:
    """OrbitalCompiler NO debe acceder a atributos que empiezan con _ en _ovc o _rcc."""

    def _extract_attribute_access(self, source: str) -> list[str]:
        """Extrae todos los accesos a atributos del source code.

        Retorna una lista de strings como '_orbital_engine._ovc._variables'.
        """
        tree = ast.parse(source)
        accesses: list[str] = []

        class _Visitor(ast.NodeVisitor):
            def visit_Attribute(self, node: ast.Attribute) -> None:
                # Reconstruir la cadena de acceso: a.b.c
                parts: list[str] = []
                cur: ast.AST = node
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                parts.reverse()
                accesses.append(".".join(parts))
                self.generic_visit(node)

        _Visitor().visit(tree)
        return accesses

    def test_orbital_compiler_source_does_not_access_ovc_variables_directly(self) -> None:
        """El codigo fuente de OrbitalCompiler no debe contener '_ovc._variables'."""
        source = inspect.getsource(OrbitalCompiler)
        assert "_ovc._variables" not in source, (
            "BUG-O2: OrbitalCompiler aun accede a '_ovc._variables' (atributo privado). "
            "Debe usar OrbitalEngine.delete_variable() o delete_variables_by_prefix()."
        )

    def test_orbital_compiler_source_does_not_access_rcc_cycles_directly(self) -> None:
        """El codigo fuente de OrbitalCompiler no debe contener '_rcc._cycles'."""
        source = inspect.getsource(OrbitalCompiler)
        assert "_rcc._cycles" not in source, (
            "BUG-O2: OrbitalCompiler aun accede a '_rcc._cycles' (atributo privado). "
            "Debe usar OrbitalEngine.delete_cycle() o get_cycle_ids()."
        )

    def test_orbital_compiler_ast_does_not_access_private_chain(self) -> None:
        """Verifica via AST que OrbitalCompiler no use cadenas con atributos '_xxx'.

        Recorre el AST del archivo orbital_compiler.py y rechaza cualquier acceso
        del tipo ``self._orbital_engine._ovc._variables`` o ``self._orbital_engine._rcc._cycles``.
        """
        source_path = Path(inspect.getfile(OrbitalCompiler))
        source = source_path.read_text(encoding="utf-8")
        accesses = self._extract_attribute_access(source)
        # Buscar cadenas que contengan '_orbital_engine._' o '_ovc._' o '_rcc._'
        offenders = [
            a for a in accesses
            if ("_orbital_engine._" in a) or ("_ovc._" in a) or ("_rcc._" in a)
        ]
        assert not offenders, (
            "BUG-O2: OrbitalCompiler accede a atributos privados del engine/OVC/RCC: "
            f"{offenders}. Debe usar los metodos publicos delete_variable / delete_cycle / "
            "get_cycle_ids expuestos en OrbitalEngine."
        )


class TestBugO2OrbitalCompilerStillWorks:
    """El fix O2 no debe romper el comportamiento funcional del OrbitalCompiler."""

    def test_compile_returns_valid_result_for_simple_phrase(self) -> None:
        """Una compilacion simple debe seguir retornando un resultado valido."""
        compiler = OrbitalCompiler()
        result = compiler.compile("Quiero registrar un nuevo cliente", {"lang": "es"})
        assert result.status == "ready"
        assert result.intent != ""
        assert result.confidence > 0
        assert result.workflow.get("steps"), (
            "OrbitalCompiler.compile debe retornar un workflow con steps. "
            "El fix O2 no debe romper este contrato."
        )

    def test_compile_consecutive_runs_do_not_accumulate_variables(self) -> None:
        """Compilaciones consecutivas no deben acumular variables fantasma.

        El proposito del bloque que accedia a _ovc._variables era limpiar
        las variables de compilaciones anteriores. Con el fix O2, esta
        limpieza debe seguir funcionando via delete_variable.
        """
        compiler = OrbitalCompiler()
        # Primera compilacion
        compiler.compile("registrar cliente nuevo", {"lang": "es"})
        vars_despues_1 = compiler._orbital_engine.get_all_variables()
        # Segunda compilacion
        compiler.compile("enviar factura al cliente", {"lang": "es"})
        vars_despues_2 = compiler._orbital_engine.get_all_variables()
        # La cantidad de variables no debe crecer indefinidamente — las variables
        # token_* y kw_* previas deben eliminarse al inicio de la segunda compilacion.
        # Permitimos que algunas variables kw_* se recreen (mismas keywords en ambos textos),
        # pero el total NO debe multiplicarse.
        assert len(vars_despues_2) <= len(vars_despues_1) * 2, (
            f"BUG-O2: las variables se estan acumulando entre compilaciones. "
            f"Despues de 1ra: {len(vars_despues_1)}, despues de 2da: {len(vars_despues_2)}. "
            f"El fix deberia limpiar las variables token_*/kw_* previas."
        )

    def test_compile_does_not_raise_on_empty_text(self) -> None:
        """Compilar texto vacio debe retornar status='error' sin levantar excepcion."""
        compiler = OrbitalCompiler()
        result = compiler.compile("", {"lang": "es"})
        assert result.status == "error"

    def test_compile_does_not_raise_on_text_without_keywords(self) -> None:
        """Compilar texto sin keywords conocidos debe retornar un resultado sin romper."""
        compiler = OrbitalCompiler()
        result = compiler.compile("asdfgh zxcvbn qwerty", {"lang": "es"})
        # Debe retornar algun resultado (probablemente 'general' o baja confianza)
        # sin levantar excepciones por acceso a atributos privados.
        assert hasattr(result, "status")
        assert hasattr(result, "intent")
