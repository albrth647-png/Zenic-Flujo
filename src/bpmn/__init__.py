"""BPMN Support — Business Process Model and Notation integration.

Provides import, export, execution, and visualization of BPMN 2.0
process definitions within the Zenic-Flijo workflow engine.

Features:
- BPMN 2.0 XML parsing and generation
- Conversion between BPMN and Zenic-Flijo workflow definitions
- Support for all major BPMN elements (tasks, gateways, events, subprocesses)
- Visual process model generation
- BPMN process execution via the workflow engine
- Process simulation and validation
"""

from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("bpmn")

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
    # Position for visualization
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
        # Update incoming/outgoing on elements
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
        task_types = {
            BPMNElementType.USER_TASK,
            BPMNElementType.SERVICE_TASK,
            BPMNElementType.SCRIPT_TASK,
            BPMNElementType.MANUAL_TASK,
        }
        return [e for e in self.elements.values() if e.element_type in task_types]

    def get_gateways(self) -> list[BPMNElement]:
        """Get all gateway elements."""
        gateway_types = {
            BPMNElementType.EXCLUSIVE_GATEWAY,
            BPMNElementType.PARALLEL_GATEWAY,
            BPMNElementType.INCLUSIVE_GATEWAY,
            BPMNElementType.EVENT_BASED_GATEWAY,
        }
        return [e for e in self.elements.values() if e.element_type in gateway_types]

    def validate(self) -> list[str]:
        """Validate the BPMN process definition.

        Returns:
            List of validation error messages. Empty list means valid.
        """
        errors: list[str] = []

        # Must have at least one start event
        if not self.get_start_events():
            errors.append("Process must have at least one Start Event")

        # Must have at least one end event
        if not self.get_end_events():
            errors.append("Process must have at least one End Event")

        # All elements should be reachable (connected via flows)
        if self.elements:
            connected = set()
            for flow in self.flows.values():
                connected.add(flow.source_ref)
                connected.add(flow.target_ref)
            for elem_id in self.elements:
                if elem_id not in connected and len(self.elements) > 1:
                    errors.append(f"Element '{elem_id}' is not connected to any flow")

        # Gateways should have at least 2 outgoing or 2 incoming
        for gw in self.get_gateways():
            if len(gw.outgoing) < 2 and len(gw.incoming) < 2:
                errors.append(
                    f"Gateway '{gw.element_id}' should have at least 2 incoming or 2 outgoing flows"
                )

        # Check for cycles (simple DFS)
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

        for elem_id in self.elements:
            if elem_id not in visited:
                if dfs(elem_id):
                    return True
        return False


class BPMNParser:
    """Parse BPMN 2.0 XML into BPMNProcess objects.

    Supports the standard BPMN 2.0 XML format with namespaces.
    Handles tasks, gateways, events, sequence flows, and subprocesses.

    Usage:
        parser = BPMNParser()
        process = parser.parse(bpmn_xml_string)
        errors = process.validate()
    """

    def parse(self, xml_string: str) -> BPMNProcess:
        """Parse a BPMN 2.0 XML string into a BPMNProcess.

        Args:
            xml_string: Valid BPMN 2.0 XML content.

        Returns:
            A BPMNProcess with all elements and flows parsed.

        Raises:
            ValueError: If the XML is invalid or not BPMN 2.0.
        """
        # Handle namespace prefixes
        xml_clean = self._clean_xml(xml_string)
        root = ET.fromstring(xml_clean)

        # Find the process element
        process_elem = root.find(f".//{{{BPMN_NS}}}process")
        if process_elem is None:
            # Try without namespace
            process_elem = root.find(".//process")
        if process_elem is None:
            msg = "No BPMN process element found in XML"
            raise ValueError(msg)

        process = BPMNProcess(
            process_id=process_elem.get("id", ""),
            name=process_elem.get("name", ""),
            is_executable=process_elem.get("isExecutable", "false").lower() == "true",
        )

        # Parse elements
        for child in process_elem:
            tag = self._strip_ns(child.tag)
            element_type = self._tag_to_element_type(tag)
            if element_type is not None:
                element = self._parse_element(child, element_type)
                process.add_element(element)

        # Parse sequence flows
        for child in process_elem:
            tag = self._strip_ns(child.tag)
            if tag == "sequenceFlow":
                flow = self._parse_flow(child)
                process.add_flow(flow)

        return process

    def parse_file(self, file_path: str) -> BPMNProcess:
        """Parse a BPMN 2.0 XML file."""
        with open(file_path, encoding="utf-8") as f:
            return self.parse(f.read())

    def _clean_xml(self, xml_string: str) -> str:
        """Clean XML string by normalizing namespace prefixes."""
        # Replace common namespace prefixes
        xml_string = re.sub(r'xmlns:bpmn2?="[^"]*"', "", xml_string)
        return xml_string

    def _strip_ns(self, tag: str) -> str:
        """Strip namespace from an XML tag."""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def _tag_to_element_type(self, tag: str) -> BPMNElementType | None:
        """Map an XML tag to a BPMNElementType."""
        mapping = {
            "startEvent": BPMNElementType.START_EVENT,
            "endEvent": BPMNElementType.END_EVENT,
            "intermediateCatchEvent": BPMNElementType.INTERMEDIATE_CATCH_EVENT,
            "intermediateThrowEvent": BPMNElementType.INTERMEDIATE_THROW_EVENT,
            "userTask": BPMNElementType.USER_TASK,
            "serviceTask": BPMNElementType.SERVICE_TASK,
            "scriptTask": BPMNElementType.SCRIPT_TASK,
            "manualTask": BPMNElementType.MANUAL_TASK,
            "exclusiveGateway": BPMNElementType.EXCLUSIVE_GATEWAY,
            "parallelGateway": BPMNElementType.PARALLEL_GATEWAY,
            "inclusiveGateway": BPMNElementType.INCLUSIVE_GATEWAY,
            "eventBasedGateway": BPMNElementType.EVENT_BASED_GATEWAY,
            "subProcess": BPMNElementType.SUB_PROCESS,
            "callActivity": BPMNElementType.CALL_ACTIVITY,
        }
        return mapping.get(tag)

    def _parse_element(self, elem: ET.Element, element_type: BPMNElementType) -> BPMNElement:
        """Parse an XML element into a BPMNElement."""
        incoming = [inc.text for inc in elem.findall(f"{{{BPMN_NS}}}incoming") if inc.text]
        outgoing = [out.text for out in elem.findall(f"{{{BPMN_NS}}}outgoing") if out.text]

        # Also try without namespace
        if not incoming:
            incoming = [inc.text for inc in elem.findall("incoming") if inc.text]
        if not outgoing:
            outgoing = [out.text for out in elem.findall("outgoing") if out.text]

        # Parse documentation
        doc = ""
        doc_elem = elem.find(f"{{{BPMN_NS}}}documentation")
        if doc_elem is None:
            doc_elem = elem.find("documentation")
        if doc_elem is not None and doc_elem.text:
            doc = doc_elem.text

        return BPMNElement(
            element_id=elem.get("id", ""),
            name=elem.get("name", ""),
            element_type=element_type,
            documentation=doc,
            incoming=incoming,
            outgoing=outgoing,
        )

    def _parse_flow(self, elem: ET.Element) -> BPMNSequenceFlow:
        """Parse a sequence flow XML element."""
        condition = ""
        cond_elem = elem.find(f"{{{BPMN_NS}}}conditionExpression")
        if cond_elem is None:
            cond_elem = elem.find("conditionExpression")
        if cond_elem is not None and cond_elem.text:
            condition = cond_elem.text

        return BPMNSequenceFlow(
            flow_id=elem.get("id", ""),
            name=elem.get("name", ""),
            source_ref=elem.get("sourceRef", ""),
            target_ref=elem.get("targetRef", ""),
            condition_expression=condition,
            is_default=elem.get("isDefault", "false").lower() == "true",
        )


class BPMNExporter:
    """Export BPMNProcess objects to BPMN 2.0 XML format.

    Generates standards-compliant BPMN 2.0 XML with visual layout
    information (BPMNDI) for rendering in BPMN viewers.

    Usage:
        exporter = BPMNExporter()
        xml_string = exporter.export(process)
    """

    def export(self, process: BPMNProcess, pretty: bool = True) -> str:
        """Export a BPMNProcess to BPMN 2.0 XML.

        Args:
            process: The BPMNProcess to export.
            pretty: Whether to pretty-print the XML.

        Returns:
            BPMN 2.0 XML string.
        """
        root = ET.Element("bpmn:definitions")
        root.set("xmlns:bpmn", BPMN_NS)
        root.set("xmlns:bpmndi", BPMNDI_NS)
        root.set("xmlns:dc", DC_NS)
        root.set("xmlns:di", DI_NS)
        root.set("id", f"Definitions_{process.process_id}")
        root.set("targetNamespace", BPMN_NS)

        # Process element
        process_elem = ET.SubElement(root, "bpmn:process")
        process_elem.set("id", process.process_id)
        process_elem.set("name", process.name)
        process_elem.set("isExecutable", str(process.is_executable).lower())

        # Add documentation
        if process.documentation:
            doc_elem = ET.SubElement(process_elem, "bpmn:documentation")
            doc_elem.text = process.documentation

        # Add elements
        for element in process.elements.values():
            self._export_element(process_elem, element)

        # Add sequence flows
        for flow in process.flows.values():
            self._export_flow(process_elem, flow)

        # Add visual layout (BPMNDI)
        diagram = ET.SubElement(root, "bpmndi:BPMNDiagram")
        diagram.set("id", f"BPMNDiagram_{process.process_id}")
        plane = ET.SubElement(diagram, "bpmndi:BPMNPlane")
        plane.set("id", f"BPMNPlane_{process.process_id}")
        plane.set("bpmnElement", process.process_id)

        for element in process.elements.values():
            self._export_shape(plane, element)
        for flow in process.flows.values():
            self._export_edge(plane, flow, process)

        # Serialize to string
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")  # Python 3.9+
        xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=True)
        return xml_bytes

    def export_to_file(self, process: BPMNProcess, file_path: str) -> None:
        """Export a process to a BPMN XML file."""
        xml_string = self.export(process)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(xml_string)

    def _export_element(self, parent: ET.Element, element: BPMNElement) -> ET.Element:
        """Export a single BPMN element."""
        tag = f"bpmn:{element.element_type.value}"
        elem = ET.SubElement(parent, tag)
        elem.set("id", element.element_id)
        if element.name:
            elem.set("name", element.name)

        # Add documentation
        if element.documentation:
            doc = ET.SubElement(elem, "bpmn:documentation")
            doc.text = element.documentation

        # Add incoming/outgoing references
        for inc_id in element.incoming:
            inc = ET.SubElement(elem, "bpmn:incoming")
            inc.text = inc_id
        for out_id in element.outgoing:
            out = ET.SubElement(elem, "bpmn:outgoing")
            out.text = out_id

        return elem

    def _export_flow(self, parent: ET.Element, flow: BPMNSequenceFlow) -> ET.Element:
        """Export a sequence flow."""
        elem = ET.SubElement(parent, "bpmn:sequenceFlow")
        elem.set("id", flow.flow_id)
        if flow.name:
            elem.set("name", flow.name)
        elem.set("sourceRef", flow.source_ref)
        elem.set("targetRef", flow.target_ref)

        if flow.condition_expression:
            cond = ET.SubElement(elem, "bpmn:conditionExpression")
            cond.set("xsi:type", "bpmn:tFormalExpression")
            cond.text = flow.condition_expression

        return elem

    def _export_shape(self, plane: ET.Element, element: BPMNElement) -> ET.Element:
        """Export a BPMN shape for visual layout."""
        shape = ET.SubElement(plane, "bpmndi:BPMNShape")
        shape.set("id", f"Shape_{element.element_id}")
        shape.set("bpmnElement", element.element_id)

        bounds = ET.SubElement(shape, "dc:Bounds")
        bounds.set("x", str(element.x))
        bounds.set("y", str(element.y))
        bounds.set("width", str(element.width))
        bounds.set("height", str(element.height))

        return shape

    def _export_edge(
        self,
        plane: ET.Element,
        flow: BPMNSequenceFlow,
        process: BPMNProcess,
    ) -> ET.Element:
        """Export a BPMN edge for visual layout."""
        edge = ET.SubElement(plane, "bpmndi:BPMNEdge")
        edge.set("id", f"Edge_{flow.flow_id}")
        edge.set("bpmnElement", flow.flow_id)

        # Add waypoints based on source/target positions
        source = process.elements.get(flow.source_ref)
        target = process.elements.get(flow.target_ref)

        if source and target:
            # Source waypoint (right center)
            wp1 = ET.SubElement(edge, "di:waypoint")
            wp1.set("x", str(source.x + source.width))
            wp1.set("y", str(source.y + source.height / 2))

            # Target waypoint (left center)
            wp2 = ET.SubElement(edge, "di:waypoint")
            wp2.set("x", str(target.x))
            wp2.set("y", str(target.y + target.height / 2))

        return edge


class BPMNToWorkflowConverter:
    """Convert BPMN process definitions to Zenic-Flijo workflow definitions.

    Maps BPMN elements to Zenic-Flijo workflow steps:
    - Tasks → workflow steps (with appropriate tool type)
    - Gateways → branch/condition steps
    - Events → trigger/webhook steps
    - Subprocesses → subworkflow calls

    Usage:
        converter = BPMNToWorkflowConverter()
        workflow_def = converter.convert(bpmn_process)
    """

    # Mapping from BPMN task types to Zenic-Flijo tool types
    TASK_TYPE_MAP = {
        BPMNElementType.USER_TASK: "input",
        BPMNElementType.SERVICE_TASK: "api_call",
        BPMNElementType.SCRIPT_TASK: "code_runner",
        BPMNElementType.MANUAL_TASK: "notification",
    }

    def convert(self, process: BPMNProcess) -> dict[str, Any]:
        """Convert a BPMNProcess to a Zenic-Flijo workflow definition.

        Args:
            process: The BPMN process to convert.

        Returns:
            A workflow definition dict compatible with the WorkflowEngine.
        """
        steps = []
        step_id_map: dict[str, str] = {}

        # Convert each BPMN element to a workflow step
        for element in process.elements.values():
            step = self._element_to_step(element, process)
            if step:
                step_id_map[element.element_id] = step["id"]
                steps.append(step)

        # Map sequence flows to next_step references
        for flow in process.flows.values():
            source_step_id = step_id_map.get(flow.source_ref)
            target_step_id = step_id_map.get(flow.target_ref)
            if source_step_id and target_step_id:
                self._update_next_steps(steps, source_step_id, target_step_id, flow)

        # Find entry point (first start event)
        start_events = process.get_start_events()
        entry_step_id = step_id_map.get(start_events[0].element_id) if start_events else None

        return {
            "name": process.name or process.process_id,
            "description": process.documentation or f"BPMN Process: {process.name}",
            "steps": steps,
            "entry_step_id": entry_step_id,
            "metadata": {
                "source": "bpmn",
                "bpmn_process_id": process.process_id,
                "version": process.version,
            },
        }

    def _element_to_step(self, element: BPMNElement, process: BPMNProcess) -> dict[str, Any] | None:
        """Convert a single BPMN element to a workflow step."""
        step_type = self._map_element_type(element.element_type)
        if step_type is None:
            return None

        step: dict[str, Any] = {
            "id": f"step_{element.element_id}",
            "name": element.name or element.element_id,
            "type": step_type,
            "next_step": None,
            "config": {},
        }

        # Add type-specific configuration
        if element.element_type in self.TASK_TYPE_MAP:
            step["config"]["tool_type"] = self.TASK_TYPE_MAP[element.element_type]
            step["config"]["bpmn_task_type"] = element.element_type.value

        elif element.element_type == BPMNElementType.EXCLUSIVE_GATEWAY:
            step["type"] = "condition"
            step["config"]["gateway_type"] = "exclusive"

        elif element.element_type == BPMNElementType.PARALLEL_GATEWAY:
            step["type"] = "fork"
            step["config"]["gateway_type"] = "parallel"

        elif element.element_type == BPMNElementType.START_EVENT:
            step["type"] = "trigger"
            step["config"]["trigger_type"] = "manual"

        elif element.element_type == BPMNElementType.END_EVENT:
            step["next_step"] = None
            step["config"]["is_terminal"] = True

        elif element.element_type == BPMNElementType.SUB_PROCESS:
            step["type"] = "subworkflow"
            step["config"]["subprocess_id"] = element.properties.get("calledElement", "")

        # Preserve BPMN extensions
        if element.extensions:
            step["config"]["bpmn_extensions"] = element.extensions

        return step

    def _map_element_type(self, element_type: BPMNElementType) -> str | None:
        """Map BPMN element type to workflow step type."""
        mapping = {
            BPMNElementType.START_EVENT: "trigger",
            BPMNElementType.END_EVENT: "output",
            BPMNElementType.USER_TASK: "input",
            BPMNElementType.SERVICE_TASK: "api_call",
            BPMNElementType.SCRIPT_TASK: "code_runner",
            BPMNElementType.MANUAL_TASK: "notification",
            BPMNElementType.EXCLUSIVE_GATEWAY: "condition",
            BPMNElementType.PARALLEL_GATEWAY: "fork",
            BPMNElementType.INCLUSIVE_GATEWAY: "condition",
            BPMNElementType.SUB_PROCESS: "subworkflow",
            BPMNElementType.CALL_ACTIVITY: "subworkflow",
            BPMNElementType.INTERMEDIATE_CATCH_EVENT: "webhook",
            BPMNElementType.INTERMEDIATE_THROW_EVENT: "notification",
        }
        return mapping.get(element_type)

    def _update_next_steps(
        self,
        steps: list[dict[str, Any]],
        source_step_id: str,
        target_step_id: str,
        flow: BPMNSequenceFlow,
    ) -> None:
        """Update next_step references based on sequence flows."""
        for step in steps:
            if step["id"] == source_step_id:
                if step["type"] in ("condition", "fork"):
                    # Branch step: add branch
                    if "branches" not in step:
                        step["branches"] = []
                    step["branches"].append({
                        "next_step": target_step_id,
                        "condition": flow.condition_expression or "",
                        "label": flow.name or f"Branch {len(step['branches']) + 1}",
                    })
                else:
                    # Linear step: set next_step
                    if step.get("next_step") is None or step["type"] == "output":
                        step["next_step"] = target_step_id
                break


class BPMNBuilder:
    """Fluent builder for creating BPMN processes programmatically.

    Provides a clean API for building BPMN processes step by step
    without dealing with XML directly.

    Usage:
        process = (
            BPMNBuilder("Order Process")
            .start_event("start", "Order Received")
            .service_task("validate", "Validate Order")
            .exclusive_gateway("check", "Valid?")
            .user_task("review", "Manual Review")
            .service_task("process", "Process Order")
            .end_event("end", "Order Complete")
            .connect("start", "validate")
            .connect("validate", "check")
            .connect("check", "review", condition="invalid")
            .connect("check", "process", condition="valid")
            .connect("review", "process")
            .connect("process", "end")
            .build()
        )
    """

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
        """Add a start event."""
        element = BPMNElement(
            element_id=element_id,
            name=name or "Start",
            element_type=BPMNElementType.START_EVENT,
            x=self._x_offset,
            y=self._y_offset,
            width=36.0,
            height=36.0,
        )
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def end_event(self, element_id: str, name: str = "") -> BPMNBuilder:
        """Add an end event."""
        element = BPMNElement(
            element_id=element_id,
            name=name or "End",
            element_type=BPMNElementType.END_EVENT,
            x=self._x_offset,
            y=self._y_offset,
            width=36.0,
            height=36.0,
        )
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def user_task(self, element_id: str, name: str = "") -> BPMNBuilder:
        """Add a user task."""
        element = BPMNElement(
            element_id=element_id,
            name=name,
            element_type=BPMNElementType.USER_TASK,
            x=self._x_offset,
            y=self._y_offset,
            width=self._step_width,
            height=80.0,
        )
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def service_task(self, element_id: str, name: str = "") -> BPMNBuilder:
        """Add a service task."""
        element = BPMNElement(
            element_id=element_id,
            name=name,
            element_type=BPMNElementType.SERVICE_TASK,
            x=self._x_offset,
            y=self._y_offset,
            width=self._step_width,
            height=80.0,
        )
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def script_task(self, element_id: str, name: str = "") -> BPMNBuilder:
        """Add a script task."""
        element = BPMNElement(
            element_id=element_id,
            name=name,
            element_type=BPMNElementType.SCRIPT_TASK,
            x=self._x_offset,
            y=self._y_offset,
            width=self._step_width,
            height=80.0,
        )
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def exclusive_gateway(self, element_id: str, name: str = "") -> BPMNBuilder:
        """Add an exclusive gateway (XOR)."""
        element = BPMNElement(
            element_id=element_id,
            name=name,
            element_type=BPMNElementType.EXCLUSIVE_GATEWAY,
            x=self._x_offset,
            y=self._y_offset,
            width=50.0,
            height=50.0,
        )
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def parallel_gateway(self, element_id: str, name: str = "") -> BPMNBuilder:
        """Add a parallel gateway (AND)."""
        element = BPMNElement(
            element_id=element_id,
            name=name,
            element_type=BPMNElementType.PARALLEL_GATEWAY,
            x=self._x_offset,
            y=self._y_offset,
            width=50.0,
            height=50.0,
        )
        self._process.add_element(element)
        self._x_offset += self._step_gap
        return self

    def connect(
        self,
        source_id: str,
        target_id: str,
        name: str = "",
        condition: str = "",
    ) -> BPMNBuilder:
        """Connect two elements with a sequence flow."""
        flow = BPMNSequenceFlow(
            flow_id=f"flow_{source_id}_to_{target_id}",
            name=name,
            source_ref=source_id,
            target_ref=target_id,
            condition_expression=condition,
        )
        self._process.add_flow(flow)
        return self

    def build(self) -> BPMNProcess:
        """Build and return the BPMN process."""
        return self._process
