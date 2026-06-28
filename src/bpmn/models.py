"""BPMN 2.0 data models — constants, enums, and dataclasses.

Extracted from src/bpmn/__init__.py to keep the package modular.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# BPMN 2.0 Namespace
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"


class BPMNElementType(Enum):
    """BPMN 2.0 element types."""

    START_EVENT = "startEvent"
    END_EVENT = "endEvent"
    INTERMEDIATE_CATCH_EVENT = "intermediateCatchEvent"
    INTERMEDIATE_THROW_EVENT = "intermediateThrowEvent"
    USER_TASK = "userTask"
    SERVICE_TASK = "serviceTask"
    SCRIPT_TASK = "scriptTask"
    MANUAL_TASK = "manualTask"
    EXCLUSIVE_GATEWAY = "exclusiveGateway"
    PARALLEL_GATEWAY = "parallelGateway"
    INCLUSIVE_GATEWAY = "inclusiveGateway"
    EVENT_BASED_GATEWAY = "eventBasedGateway"
    SUB_PROCESS = "subProcess"
    CALL_ACTIVITY = "callActivity"
    SEQUENCE_FLOW = "sequenceFlow"
    MESSAGE_FLOW = "messageFlow"
    TIMER_EVENT = "timerEventDefinition"
    MESSAGE_EVENT = "messageEventDefinition"
    ERROR_EVENT = "errorEventDefinition"
    POOL = "pool"
    LANE = "lane"


class GatewayDirection(Enum):
    """Gateway direction (diverging or converging)."""

    DIVERGING = "diverging"
    CONVERGING = "converging"
    MIXED = "mixed"
    UNSPECIFIED = "unspecified"


@dataclass
class BPMNElement:
    """A single BPMN element in a process definition."""

    element_id: str = ""
    name: str = ""
    element_type: BPMNElementType = BPMNElementType.START_EVENT
    documentation: str = ""
    incoming: list[str] = field(default_factory=list)
    outgoing: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0
    width: float = 100.0
    height: float = 80.0

    def __post_init__(self) -> None:
        if not self.element_id:
            self.element_id = f"bpmn_{uuid.uuid4().hex[:8]}"


@dataclass
class BPMNSequenceFlow:
    """A sequence flow connecting two BPMN elements."""

    flow_id: str = ""
    name: str = ""
    source_ref: str = ""
    target_ref: str = ""
    condition_expression: str = ""
    is_default: bool = False

    def __post_init__(self) -> None:
        if not self.flow_id:
            self.flow_id = f"flow_{uuid.uuid4().hex[:8]}"


@dataclass
class BPMNProcess:
    """A complete BPMN 2.0 process definition."""

    process_id: str = ""
    name: str = ""
    is_executable: bool = True
    elements: dict[str, BPMNElement] = field(default_factory=dict)
    flows: dict[str, BPMNSequenceFlow] = field(default_factory=dict)
    pools: list[dict[str, Any]] = field(default_factory=list)
    lanes: list[dict[str, Any]] = field(default_factory=list)
    documentation: str = ""
    version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.process_id:
            self.process_id = f"process_{uuid.uuid4().hex[:8]}"

    def add_element(self, element: BPMNElement) -> None:
        """Add an element to the process."""
        self.elements[element.element_id] = element

    def add_flow(self, flow: BPMNSequenceFlow) -> None:
        """Add a sequence flow to the process."""
        self.flows[flow.flow_id] = flow
        if flow.source_ref in self.elements:
            self.elements[flow.source_ref].outgoing.append(flow.flow_id)
        if flow.target_ref in self.elements:
            self.elements[flow.target_ref].incoming.append(flow.flow_id)

    def get_start_events(self) -> list[BPMNElement]:
        """Get all start events."""
        return [e for e in self.elements.values() if e.element_type == BPMNElementType.START_EVENT]

    def get_end_events(self) -> list[BPMNElement]:
        """Get all end events."""
        return [e for e in self.elements.values() if e.element_type == BPMNElementType.END_EVENT]

    def get_tasks(self) -> list[BPMNElement]:
        """Get all task elements."""
        task_types = {BPMNElementType.USER_TASK, BPMNElementType.SERVICE_TASK,
                      BPMNElementType.SCRIPT_TASK, BPMNElementType.MANUAL_TASK}
        return [e for e in self.elements.values() if e.element_type in task_types]

    def get_gateways(self) -> list[BPMNElement]:
        """Get all gateway elements."""
        gateway_types = {BPMNElementType.EXCLUSIVE_GATEWAY, BPMNElementType.PARALLEL_GATEWAY,
                         BPMNElementType.INCLUSIVE_GATEWAY, BPMNElementType.EVENT_BASED_GATEWAY}
        return [e for e in self.elements.values() if e.element_type in gateway_types]

    def validate(self) -> list[str]:
        """Validate the BPMN process definition. Returns list of error messages."""
        errors: list[str] = []
        if not self.get_start_events():
            errors.append("Process must have at least one Start Event")
        if not self.get_end_events():
            errors.append("Process must have at least one End Event")
        if self.elements:
            connected = set()
            for flow in self.flows.values():
                connected.add(flow.source_ref)
                connected.add(flow.target_ref)
            for elem_id in self.elements:
                if elem_id not in connected and len(self.elements) > 1:
                    errors.append(f"Element '{elem_id}' is not connected to any flow")
        for gw in self.get_gateways():
            if len(gw.outgoing) < 2 and len(gw.incoming) < 2:
                errors.append(f"Gateway '{gw.element_id}' should have at least 2 incoming or 2 outgoing flows")
        if self._has_cycles():
            errors.append("Process contains unhandled cycles (consider using loop markers)")
        return errors

    def _has_cycles(self) -> bool:
        """Detect cycles in the process graph using DFS."""
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for flow in self.flows.values():
                if flow.source_ref == node_id:
                    neighbor = flow.target_ref
                    if neighbor not in visited:
                        if dfs(neighbor):
                            return True
                    elif neighbor in rec_stack:
                        return True
            rec_stack.discard(node_id)
            return False

        return any(elem_id not in visited and dfs(elem_id) for elem_id in self.elements)
