"""Fluent BPMN process builder — programmatic BPMN process creation.

Extracted from src/bpmn/__init__.py.
"""

from __future__ import annotations

import uuid

from src.bpmn.models import BPMNElement, BPMNElementType, BPMNProcess, BPMNSequenceFlow


class BPMNBuilder:
    """Fluent builder for creating BPMN processes programmatically."""

    def __init__(self, name: str = "", process_id: str = "") -> None:
        self._process = BPMNProcess(
            process_id=process_id or f"process_{uuid.uuid4().hex[:8]}",
            name=name,
        )
        self._x_offset = 50.0
        self._y_offset = 50.0
        self._step_width = 150.0
        self._step_gap = 200.0

    def start_event(self, element_id: str, name: str = "") -> BPMNBuilder:
        element = BPMNElement(element_id=element_id, name=name or "Start",
                              element_type=BPMNElementType.START_EVENT,
                              x=self._x_offset, y=self._y_offset, width=36.0, height=36.0)
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def end_event(self, element_id: str, name: str = "") -> BPMNBuilder:
        element = BPMNElement(element_id=element_id, name=name or "End",
                              element_type=BPMNElementType.END_EVENT,
                              x=self._x_offset, y=self._y_offset, width=36.0, height=36.0)
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def user_task(self, element_id: str, name: str = "") -> BPMNBuilder:
        element = BPMNElement(element_id=element_id, name=name,
                              element_type=BPMNElementType.USER_TASK,
                              x=self._x_offset, y=self._y_offset, width=self._step_width, height=80.0)
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def service_task(self, element_id: str, name: str = "") -> BPMNBuilder:
        element = BPMNElement(element_id=element_id, name=name,
                              element_type=BPMNElementType.SERVICE_TASK,
                              x=self._x_offset, y=self._y_offset, width=self._step_width, height=80.0)
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def script_task(self, element_id: str, name: str = "") -> BPMNBuilder:
        element = BPMNElement(element_id=element_id, name=name,
                              element_type=BPMNElementType.SCRIPT_TASK,
                              x=self._x_offset, y=self._y_offset, width=self._step_width, height=80.0)
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def exclusive_gateway(self, element_id: str, name: str = "") -> BPMNBuilder:
        element = BPMNElement(element_id=element_id, name=name,
                              element_type=BPMNElementType.EXCLUSIVE_GATEWAY,
                              x=self._x_offset, y=self._y_offset, width=50.0, height=50.0)
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def parallel_gateway(self, element_id: str, name: str = "") -> BPMNBuilder:
        element = BPMNElement(element_id=element_id, name=name,
                              element_type=BPMNElementType.PARALLEL_GATEWAY,
                              x=self._x_offset, y=self._y_offset, width=50.0, height=50.0)
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def connect(self, source_id: str, target_id: str, name: str = "", condition: str = "") -> BPMNBuilder:
        flow = BPMNSequenceFlow(flow_id=f"flow_{source_id}_to_{target_id}", name=name,
                                source_ref=source_id, target_ref=target_id, condition_expression=condition)
        self._process.add_flow(flow)
        return self

    def build(self) -> BPMNProcess:
        """Build and return the BPMN process."""
        return self._process
