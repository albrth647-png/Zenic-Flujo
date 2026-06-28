"""Tests para DispatchTracer — propagación de dispatch_id vía OpenTelemetry.

Cubre:
- Inicialización: usa OTel si está instalado, sino NoOpTracer.
- span(): retorna context manager con atributos HAT estándar.
- Atributos: hat.dispatch_id, hat.domain, extras.
- NoOpSpan: __enter__/__exit__ no lanzan.
"""
from __future__ import annotations

import pytest

from src.hat.level1_orchestrator.observability.dispatch_tracer import (
    DispatchTracer,
    _NoOpSpan,
    _NoOpTracer,
)

# ── Tests de inicialización ────────────────────────────────────────────


class TestInit:
    """Inicialización del tracer."""

    def test_init_does_not_raise(self) -> None:
        """DispatchTracer() no lanza aunque OTel no esté instalado."""
        tracer = DispatchTracer()
        assert tracer is not None

    def test_get_tracer_returns_object(self) -> None:
        """_get_tracer retorna un objeto (OTel o NoOp)."""
        result = DispatchTracer._get_tracer()
        assert result is not None


# ── Tests de span() ────────────────────────────────────────────────────


class TestSpan:
    """span() retorna context manager."""

    def test_span_returns_context_manager(self) -> None:
        """span() retorna algo con __enter__/__exit__."""
        tracer = DispatchTracer()
        span = tracer.span("test_span", dispatch_id="disp_123")
        assert hasattr(span, "__enter__")
        assert hasattr(span, "__exit__")

    def test_span_can_be_entered_and_exited(self) -> None:
        """El context manager funciona sin lanzar."""
        tracer = DispatchTracer()
        with tracer.span("test_span", dispatch_id="disp_123"):
            pass  # no debe lanzar
        # Si llegamos aquí sin excepción, el test pasa
        assert True

    def test_span_with_domain(self) -> None:
        """span() acepta el parámetro domain."""
        tracer = DispatchTracer()
        with tracer.span("test", dispatch_id="d1", domain="operaciones"):
            pass
        assert True

    def test_span_with_extra_attrs(self) -> None:
        """span() acepta atributos adicionales vía **extra_attrs."""
        tracer = DispatchTracer()
        with tracer.span(
            "test",
            dispatch_id="d1",
            domain="operaciones",
            custom_attr="value",
            iteration=5,
        ):
            pass
        assert True

    def test_span_with_minimal_args(self) -> None:
        """span() funciona sin argumentos opcionales."""
        tracer = DispatchTracer()
        with tracer.span("minimal"):
            pass
        assert True

    def test_span_does_not_raise_on_exception(self) -> None:
        """El context manager propaga excepciones del bloque."""
        tracer = DispatchTracer()
        with pytest.raises(ValueError, match="test error"), \
             tracer.span("test", dispatch_id="d1"):
            raise ValueError("test error")


# ── Tests de NoOpTracer (fallback) ─────────────────────────────────────


class TestNoOpTracer:
    """Tracer no-op cuando OTel no está disponible."""

    def test_noop_tracer_returns_noop_span(self) -> None:
        """_NoOpTracer.start_as_current_span retorna _NoOpSpan."""
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test", attributes={"a": "b"})
        assert isinstance(span, _NoOpSpan)

    def test_noop_span_enter_returns_self(self) -> None:
        """_NoOpSpan.__enter__ retorna self."""
        span = _NoOpSpan()
        result = span.__enter__()
        assert result is span

    def test_noop_span_exit_returns_none(self) -> None:
        """_NoOpSpan.__exit__ retorna None (no suprime excepciones)."""
        span = _NoOpSpan()
        result = span.__exit__(None, None, None)
        assert result is None

    def test_noop_span_with_attributes(self) -> None:
        """_NoOpTracer acepta attributes=None sin lanzar."""
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test", attributes=None)
        assert isinstance(span, _NoOpSpan)

    def test_noop_span_with_empty_attributes(self) -> None:
        """_NoOpTracer acepta attributes={} sin lanzar."""
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test", attributes={})
        assert isinstance(span, _NoOpSpan)
