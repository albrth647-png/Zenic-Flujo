"""
Workflow Determinista — AutoPilot Service
Plantillas predefinidas de automatización para empezar rápido.
"""
from src.nlu.intent_classifier import IntentClassifier
from src.nlu.templates import TEMPLATES
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class AutoPilotService:
    def __init__(self):
        self._classifier = IntentClassifier()

    def suggest_templates(self, text: str) -> list[dict]:
        intent_matches = self._classifier.classify_text(text)
        results = []
        for im in intent_matches[:5]:
            template = next(
                (t for t in TEMPLATES if t["name"] == im.intent),
                None,
            )
            if template and im.score > 0.3:
                results.append({
                    "name": template["name"],
                    "confidence": im.score,
                    "trigger": template["trigger"],
                    "steps": template["steps"],
                    "description": template.get("description_es", ""),
                })
        return results

    def get_quick_templates(self) -> list[dict]:
        return [
            {"name": t["name"], "trigger_type": t["trigger"]["type"],
             "step_count": len(t["steps"])}
            for t in TEMPLATES
        ]

    def create_from_template(self, template_name: str,
                             params: dict | None = None) -> dict:
        template = next((t for t in TEMPLATES if t["name"] == template_name), None)
        if not template:
            raise ValueError(f"Template '{template_name}' no encontrado")
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition
        repo = WorkflowRepository()
        wf = WorkflowDefinition(
            name=template.get("label", template_name),
            description=template.get("description", ""),
            trigger_type=template["trigger"]["type"],
            trigger_config=template["trigger"]["config"],
            steps=template["steps"],
        )
        created = repo.create(wf)
        return created.to_dict()
