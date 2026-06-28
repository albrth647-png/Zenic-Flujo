"""BPMN 2.0 XML exporter — exports BPMNProcess to BPMN 2.0 XML.

Extracted from src/bpmn/__init__.py.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from src.bpmn.models import BPMN_NS, BPMNDI_NS, DC_NS, DI_NS, BPMNProcess


class BPMNExporter:
    """Export BPMNProcess objects to BPMN 2.0 XML format."""

    def export(self, process: BPMNProcess) -> str:
        """Export a BPMNProcess to BPMN 2.0 XML."""
        root = ET.Element("bpmn:definitions")
        root.set("xmlns:bpmn", BPMN_NS)
        root.set("xmlns:bpmndi", BPMNDI_NS)
        root.set("xmlns:dc", DC_NS)
        root.set("xmlns:di", DI_NS)
        root.set("id", f"Definitions_{process.process_id}")
        root.set("targetNamespace", BPMN_NS)

        process_elem = ET.SubElement(root, "bpmn:process")
        process_elem.set("id", process.process_id)
        process_elem.set("name", process.name)
        process_elem.set("isExecutable", str(process.is_executable).lower())

        if process.documentation:
            doc_elem = ET.SubElement(process_elem, "bpmn:documentation")
            doc_elem.text = process.documentation

        for element in process.elements.values():
            self._export_element(process_elem, element)
        for flow in process.flows.values():
            self._export_flow(process_elem, flow)

        diagram = ET.SubElement(root, "bpmndi:BPMNDiagram")
        diagram.set("id", f"BPMNDiagram_{process.process_id}")
        plane = ET.SubElement(diagram, "bpmndi:BPMNPlane")
        plane.set("id", f"BPMNPlane_{process.process_id}")
        plane.set("bpmnElement", process.process_id)
        for element in process.elements.values():
            self._export_shape(plane, element)
        for flow in process.flows.values():
            self._export_edge(plane, flow, process)

        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def export_to_file(self, process: BPMNProcess, file_path: str) -> None:
        """Export a process to a BPMN XML file."""
        xml_string = self.export(process)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(xml_string)

    @staticmethod
    def _export_element(parent: ET.Element, element) -> ET.Element:
        tag = f"bpmn:{element.element_type.value}"
        elem = ET.SubElement(parent, tag)
        elem.set("id", element.element_id)
        if element.name:
            elem.set("name", element.name)
        if element.documentation:
            doc = ET.SubElement(elem, "bpmn:documentation")
            doc.text = element.documentation
        for inc_id in element.incoming:
            inc = ET.SubElement(elem, "bpmn:incoming")
            inc.text = inc_id
        for out_id in element.outgoing:
            out = ET.SubElement(elem, "bpmn:outgoing")
            out.text = out_id
        return elem

    @staticmethod
    def _export_flow(parent: ET.Element, flow) -> ET.Element:
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

    @staticmethod
    def _export_shape(plane: ET.Element, element) -> ET.Element:
        shape = ET.SubElement(plane, "bpmndi:BPMNShape")
        shape.set("id", f"Shape_{element.element_id}")
        shape.set("bpmnElement", element.element_id)
        bounds = ET.SubElement(shape, "dc:Bounds")
        bounds.set("x", str(element.x))
        bounds.set("y", str(element.y))
        bounds.set("width", str(element.width))
        bounds.set("height", str(element.height))
        return shape

    @staticmethod
    def _export_edge(plane: ET.Element, flow, process: BPMNProcess) -> ET.Element:
        edge = ET.SubElement(plane, "bpmndi:BPMNEdge")
        edge.set("id", f"Edge_{flow.flow_id}")
        edge.set("bpmnElement", flow.flow_id)
        source = process.elements.get(flow.source_ref)
        target = process.elements.get(flow.target_ref)
        if source and target:
            wp1 = ET.SubElement(edge, "di:waypoint")
            wp1.set("x", str(source.x + source.width))
            wp1.set("y", str(source.y + source.height / 2))
            wp2 = ET.SubElement(edge, "di:waypoint")
            wp2.set("x", str(target.x))
            wp2.set("y", str(target.y + target.height / 2))
        return edge
