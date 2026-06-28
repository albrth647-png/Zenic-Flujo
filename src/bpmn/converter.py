"""BPMN to Workflow converter — converts BPMN processes to Zenic-Flijo workflows.

Extracted from src/bpmn/__init__.py.
"""

from __future__ import annotations

from typing import Any

from src.bpmn.models import BPMNElementType, BPMNProcess


class BPMNToWorkflowConverter:
    """Convert BPMN process definitions to Zenic-Flijo workflow definitions."""

    TASK_TYPE_MAP: dict[BPMNElementType, str] | None = None

    def _get_task_type_map(self) -> dict[BPMNElementType, str]:
        if self.TASK_TYPE_MAP is None:
            self.TASK_TYPE_MAP = {
                BPMNElementType.USER_TASK: "input",
                BPMNElementType.SERVICE_TASK: "api_call",
                BPMNElementType.SCRIPT_TASK: "code_runner",
                BPMNElementType.MANUAL_TASK: "notification",
            }
        return self.TASK_TYPE_MAP

    def convert(self, process: BPMNProcess) -> dict[str, Any]:
        """Convert a BPMNProcess to a Zenic-Flijo workflow definition."""
        steps = []
        step_id_map: dict[str, str] = {}

        for element in process.elements.values():
            step = self._element_to_step(element, process)
            if step:
                step_id_map[element.element_id] = step["id"]
                steps.append(step)

        for flow in process.flows.values():
            source_step_id = step_id_map.get(flow.source_ref)
            target_step_id = step_id_map.get(flow.target_ref)
            if source_step_id and target_step_id:
                self._update_next_steps(steps, source_step_id, target_step_id, flow)

        start_events = process.get_start_events()
        entry_step_id = step_id_map.get(start_events[0].element_id) if start_events else None

        return {
            "name": process.name or process.process_id,
            "description": process.documentation or f"BPMN Process: {process.name}",
            "steps": steps,
            "entry_step_id": entry_step_id,
            "metadata": {"source": "bpmn", "bpmn_process_id": process.process_id, "version": process.version},
        }

    def _element_to_step(self, element, process: BPMNProcess) -> dict[str, Any] | None:
        step_type = self._map_element_type(element.element_type)
        if step_type is None:
            return None

        step: dict[str, Any] = {
            "id": f"step_{element.element_id}", "name": element.name or element.element_id,
            "type": step_type, "next_step": None, "config": {},
        }

        if element.element_type in self._get_task_type_map():
            step["config"]["tool_type"] = self._get_task_type_map()[element.element_type]
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

        if element.extensions:
            step["config"]["bpmn_extensions"] = element.extensions
        return step

    @staticmethod
    def _map_element_type(element_type: BPMNElementType) -> str | None:
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

    @staticmethod
    def _update_next_steps(steps: list[dict[str, Any]], source_step_id: str, target_step_id: str, flow) -> None:
        for step in steps:
            if step["id"] == source_step_id:
                if step["type"] in ("condition", "fork"):
                    if "branches" not in step:
                        step["branches"] = []
                    step["branches"].append({
                        "next_step": target_step_id,
                        "condition": flow.condition_expression or "",
                        "label": flow.name or f"Branch {len(step['branches']) + 1}",
                    })
                else:
                    if step.get("next_step") is None or step["type"] == "output":
                        step["next_step"] = target_step_id
                break
