"""BPMN 2.0 XML parser — parses BPMN XML into BPMNProcess objects.

Extracted from src/bpmn/__init__.py.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from src.bpmn.models import BPMN_NS, BPMNElement, BPMNElementType, BPMNProcess, BPMNSequenceFlow
from src.core.logging import setup_logging

logger = setup_logging("bpmn")


class BPMNParser:
    """Parse BPMN 2.0 XML into BPMNProcess objects."""

    def parse(self, xml_string: str) -> BPMNProcess:
        """Parse a BPMN 2.0 XML string into a BPMNProcess."""
        xml_clean = self._clean_xml(xml_string)
        root = ET.fromstring(xml_clean)
        process_elem = root.find(f".//{{{BPMN_NS}}}process")
        if process_elem is None:
            process_elem = root.find(".//process")
        if process_elem is None:
            msg = "No BPMN process element found in XML"
            raise ValueError(msg)

        process = BPMNProcess(
            process_id=process_elem.get("id", ""),
            name=process_elem.get("name", ""),
            is_executable=process_elem.get("isExecutable", "false").lower() == "true",
        )
        for child in process_elem:
            tag = self._strip_ns(child.tag)
            element_type = self._tag_to_element_type(tag)
            if element_type is not None:
                element = self._parse_element(child, element_type)
                process.add_element(element)
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
        xml_string = re.sub(r'xmlns:bpmn2?="[^"]*"', "", xml_string)
        return xml_string

    @staticmethod
    def _strip_ns(tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    @staticmethod
    def _tag_to_element_type(tag: str) -> BPMNElementType | None:
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
        incoming = [inc.text for inc in elem.findall(f"{{{BPMN_NS}}}incoming") if inc.text]
        outgoing = [out.text for out in elem.findall(f"{{{BPMN_NS}}}outgoing") if out.text]
        if not incoming:
            incoming = [inc.text for inc in elem.findall("incoming") if inc.text]
        if not outgoing:
            outgoing = [out.text for out in elem.findall("outgoing") if out.text]
        doc = ""
        doc_elem = elem.find(f"{{{BPMN_NS}}}documentation")
        if doc_elem is None:
            doc_elem = elem.find("documentation")
        if doc_elem is not None and doc_elem.text:
            doc = doc_elem.text
        return BPMNElement(
            element_id=elem.get("id", ""), name=elem.get("name", ""),
            element_type=element_type, documentation=doc,
            incoming=incoming, outgoing=outgoing,
        )

    def _parse_flow(self, elem: ET.Element) -> BPMNSequenceFlow:
        condition = ""
        cond_elem = elem.find(f"{{{BPMN_NS}}}conditionExpression")
        if cond_elem is None:
            cond_elem = elem.find("conditionExpression")
        if cond_elem is not None and cond_elem.text:
            condition = cond_elem.text
        return BPMNSequenceFlow(
            flow_id=elem.get("id", ""), name=elem.get("name", ""),
            source_ref=elem.get("sourceRef", ""), target_ref=elem.get("targetRef", ""),
            condition_expression=condition,
            is_default=elem.get("isDefault", "false").lower() == "true",
        )
