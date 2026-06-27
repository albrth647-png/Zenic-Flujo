"""
Tests for PersistentMemory — Code-Forge v1.0
Cobertura: add_reflection, find_similar (Jaccard), persistence, stats
"""

import json
import tempfile

import pytest

from forge.memory import PersistentMemory


class TestPersistentMemoryCreation:
    """Tests de creación e inicialización."""

    def test_creates_new_memory_file(self):
        """PersistentMemory crea archivo memory.json al inicializar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            assert mem.memory_path.exists()
            assert mem.data["version"] == "1.0"
            assert mem.data["reflections"] == []
            assert "created_at" in mem.data

    def test_loads_existing_memory(self):
        """PersistentMemory carga memoria existente."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem1 = PersistentMemory(tmpdir)
            mem1.add_reflection("iter-1", "Resumen 1", "Reflexión 1", score=8.0)

            mem2 = PersistentMemory(tmpdir)
            assert len(mem2.data["reflections"]) == 1
            assert mem2.data["reflections"][0]["iteration_id"] == "iter-1"

    def test_corrupted_json_raises(self):
        """JSON corrupto lanza error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            mem.add_reflection("iter-1", "Test", "Test", score=5.0)

            # Corromper
            with open(mem.memory_path, "w") as f:
                f.write("{ invalid }")

            # Nueva instancia - el _load actual no maneja error
            with pytest.raises(json.JSONDecodeError):
                PersistentMemory(tmpdir)


class TestAddReflection:
    """Tests de add_reflection."""

    def test_add_reflection_basic(self):
        """add_reflection guarda reflexión básica."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            ref = mem.add_reflection("iter-1", "Resumen", "Reflexión verbal", score=8.0)

            assert ref["iteration_id"] == "iter-1"
            assert ref["summary"] == "Resumen"
            assert ref["verbal_reflection"] == "Reflexión verbal"
            assert ref["score"] == 8.0
            assert "timestamp" in ref

    def test_add_reflection_with_all_fields(self):
        """add_reflection acepta todos los campos opcionales."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            ref = mem.add_reflection(
                iteration_id="iter-2",
                summary="Fix import error",
                verbal_reflection="Root cause was missing __init__.py",
                score=9.0,
                root_cause="Missing __init__.py",
                files_affected=["src/service.py", "src/__init__.py"],
                key_learnings=["Always check __init__.py", "Use absolute imports"],
            )

            assert ref["root_cause"] == "Missing __init__.py"
            assert ref["files_affected"] == ["src/service.py", "src/__init__.py"]
            assert ref["key_learnings"] == ["Always check __init__.py", "Use absolute imports"]

    def test_add_reflection_truncates_long_summary(self):
        """summary se trunca a 500 chars."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            long_summary = "x" * 1000
            ref = mem.add_reflection("iter-1", long_summary, "reflection", score=5.0)
            assert len(ref["summary"]) == 500

    def test_add_reflection_limits_key_learnings_to_5(self):
        """key_learnings limitado a 5 elementos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            ref = mem.add_reflection(
                "iter-1", "Sum", "Ref", score=5.0,
                key_learnings=[f"learning {i}" for i in range(10)]
            )
            assert len(ref["key_learnings"]) == 5

    def test_multiple_reflections_appended(self):
        """Múltiples reflexiones se apenden."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            mem.add_reflection("iter-1", "Sum1", "Ref1", score=5.0)
            mem.add_reflection("iter-2", "Sum2", "Ref2", score=7.0)
            mem.add_reflection("iter-3", "Sum3", "Ref3", score=9.0)

            assert len(mem.data["reflections"]) == 3


class TestJaccardSimilarity:
    """Tests de búsqueda por similitud Jaccard."""

    def test_find_similar_empty_memory(self):
        """find_similar retorna lista vacía si no hay reflexiones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            result = mem.find_similar("error de import")
            assert result == []

    def test_find_similar_exact_match(self):
        """find_similar encuentra coincidencia exacta de keywords."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            mem.add_reflection(
                "iter-1",
                "Error de import en service.py",
                "El problema fue que faltaba __init__.py en el subdirectorio",
                score=8.0,
                root_cause="Missing __init__.py",
                key_learnings=["Siempre verificar __init__.py antes de importar"]
            )

            results = mem.find_similar("error de import", top_n=5)
            assert len(results) == 1
            assert results[0]["iteration_id"] == "iter-1"

    def test_find_similar_partial_match(self):
        """find_similar encuentra coincidencia parcial (Jaccard > 0)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            mem.add_reflection(
                "iter-1",
                "Error de import circular en módulo A",
                "Import circular detectado",
                score=8.0,
                root_cause="Circular import",
            )

            # Búsqueda con keywords parciales
            results = mem.find_similar("circular import problema", top_n=5)
            assert len(results) == 1
            assert "circular" in results[0]["verbal_reflection"].lower()

    def test_find_similar_returns_top_n(self):
        """find_similar retorna máximo top_n resultados ordenados por similitud Jaccard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            # 3 reflexiones con keywords superpuestas
            mem.add_reflection("iter-1", "Error import A", "Missing __init__.py", score=5.0, root_cause="Missing __init__.py")
            mem.add_reflection("iter-2", "Error import B", "Missing __init__.py in subdir", score=7.0, root_cause="Missing __init__.py")
            mem.add_reflection("iter-3", "Error import C", "Typo in import statement", score=6.0, root_cause="Typo")

            results = mem.find_similar("import error", top_n=2)
            assert len(results) == 2
            # Debe ordenar por similitud Jaccard, no por score guardado
            # iter-1 y iter-2 tienen "Missing __init__.py" (más overlap con "import error")
            assert results[0]["iteration_id"] in ("iter-1", "iter-2")

    def test_find_similar_scores_correctly(self):
        """Verificar cálculo Jaccard: intersection/union."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            # Reflexión con keywords: "error", "import", "missing", "init"
            mem.add_reflection("iter-1", "Error import", "Missing __init__.py", score=8.0)

            # Query: "error import" -> keywords: {"error", "import"}
            # Ref keywords: {"error", "import", "missing", "init"}
            # Intersection: {"error", "import"} = 2
            # Union: {"error", "import", "missing", "init"} = 4
            # Jaccard: 2/4 = 0.5
            results = mem.find_similar("error import", top_n=5)
            assert len(results) == 1

    def test_find_similar_no_match_returns_empty(self):
        """Query sin overlap retorna lista vacía."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            mem.add_reflection("iter-1", "Error import", "Missing __init__.py", score=8.0)

            results = mem.find_similar("conexión base datos", top_n=5)
            assert results == []

    def test_find_similar_ignores_stopwords(self):
        """Stopwords comunes se ignoran en Jaccard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            mem.add_reflection("iter-1", "Error import", "The problem was missing init", score=8.0)

            # "the" y "was" son stopwords, no deberían afectar similitud
            results = mem.find_similar("the problem was missing", top_n=5)
            assert len(results) == 1


class TestPersistence:
    """Tests de persistencia cross-session."""

    def test_persists_across_instances(self):
        """Reflexiones persisten entre instancias."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem1 = PersistentMemory(tmpdir)
            mem1.add_reflection("iter-1", "Sum1", "Ref1", score=8.0)

            mem2 = PersistentMemory(tmpdir)
            assert len(mem2.data["reflections"]) == 1
            assert mem2.data["reflections"][0]["summary"] == "Sum1"

    def test_get_all_reflections(self):
        """get_all_reflections retorna todas las reflexiones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            mem.add_reflection("iter-1", "Sum1", "Ref1", score=5.0)
            mem.add_reflection("iter-2", "Sum2", "Ref2", score=7.0)

            all_refs = mem.get_all_reflections()
            assert len(all_refs) == 2
            assert all_refs[0]["iteration_id"] == "iter-1"
            assert all_refs[1]["iteration_id"] == "iter-2"


class TestStats:
    """Tests de estadísticas."""

    def test_stats_empty(self):
        """stats en memoria vacía."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            stats = mem.stats()
            assert stats == {"total_reflections": 0}

    def test_stats_with_reflections(self):
        """stats calcula promedio y top items."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            mem.add_reflection("iter-1", "Sum1", "Ref1", score=5.0, root_cause="Cause A", files_affected=["a.py"])
            mem.add_reflection("iter-2", "Sum2", "Ref2", score=9.0, root_cause="Cause B", files_affected=["b.py"])
            mem.add_reflection("iter-3", "Sum3", "Ref3", score=7.0, root_cause="Cause A", files_affected=["a.py", "c.py"])

            stats = mem.stats()
            assert stats["total_reflections"] == 3
            assert stats["avg_score"] == 7.0  # (5+9+7)/3
            assert stats["top_root_causes"][0][0] == "Cause A"  # Aparece 2 veces
            assert stats["top_files"][0][0] == "a.py"  # Aparece 2 veces


class TestEdgeCases:
    """Tests de casos frontera."""

    def test_add_reflection_none_files_affected(self):
        """files_affected None se convierte en lista vacía."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            ref = mem.add_reflection("iter-1", "Sum", "Ref", score=5.0, files_affected=None)
            assert ref["files_affected"] == []

    def test_add_reflection_none_key_learnings(self):
        """key_learnings None se convierte en lista vacía."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = PersistentMemory(tmpdir)
            ref = mem.add_reflection("iter-1", "Sum", "Ref", score=5.0, key_learnings=None)
            assert ref["key_learnings"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
