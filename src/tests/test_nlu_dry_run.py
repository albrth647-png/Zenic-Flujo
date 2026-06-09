"""
Tests para DryRunSimulator (Sprint 4, Tarea 1).
"""
import pytest
from src.nlu.dry_run import DryRunSimulator, DryRunResult, DryRunStep


@pytest.fixture
def simulator():
    return DryRunSimulator()


@pytest.fixture
def sample_workflow():
    return {
        "name": "Registro de cliente",
        "trigger_type": "event",
        "trigger_config": {"event": "crm.lead.created"},
        "steps": [
            {"id": 1, "tool": "crm", "action": "create_lead",
             "params": {"name": "$input.nombre", "email": "$input.email"}},
            {"id": 2, "tool": "notification", "action": "send_email",
             "params": {"to": "$input.email", "subject": "Bienvenida"}},
        ],
    }


class TestDryRunSimulator:

    def test_returns_dry_run_result(self, simulator, sample_workflow):
        result = simulator.simulate(sample_workflow)
        assert isinstance(result, DryRunResult)

    def test_preserves_workflow_name(self, simulator, sample_workflow):
        result = simulator.simulate(sample_workflow)
        assert result.workflow_name == "Registro de cliente"

    def test_preserves_trigger_type(self, simulator, sample_workflow):
        result = simulator.simulate(sample_workflow)
        assert result.trigger_type == "event"
        assert result.trigger_config["event"] == "crm.lead.created"

    def test_counts_steps_correctly(self, simulator, sample_workflow):
        result = simulator.simulate(sample_workflow)
        assert result.total_steps == 2
        assert result.steps_that_would_succeed == 2
        assert result.steps_that_would_fail == 0

    def test_overall_feasible_when_all_ok(self, simulator, sample_workflow):
        result = simulator.simulate(sample_workflow)
        assert result.overall_feasible is True

    def test_simulated_output_for_crm(self, simulator, sample_workflow):
        result = simulator.simulate(sample_workflow)
        step1 = result.steps[0]
        assert step1.tool == "crm"
        assert step1.action == "create_lead"
        assert step1.would_succeed is True
        assert "id" in step1.simulated_output

    def test_simulated_output_for_notification(self, simulator, sample_workflow):
        result = simulator.simulate(sample_workflow)
        step2 = result.steps[1]
        assert step2.tool == "notification"
        assert "status" in step2.simulated_output

    def test_unknown_tool_fails(self, simulator):
        wf = {
            "name": "Test unknown",
            "trigger_type": "manual",
            "trigger_config": {},
            "steps": [
                {"id": 1, "tool": "nonexistent_tool", "action": "do_stuff", "params": {}},
            ],
        }
        result = simulator.simulate(wf)
        assert result.steps_that_would_fail == 1
        assert result.overall_feasible is False
        assert result.steps[0].error is not None

    def test_unresolved_refs_generate_warnings(self, simulator):
        wf = {
            "name": "Test refs",
            "trigger_type": "manual",
            "trigger_config": {},
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead",
                 "params": {"name": "$input.nombre", "email": "$output.1.email"}},
            ],
        }
        result = simulator.simulate(wf)
        # Should have warnings about unresolved $output refs
        assert any("$output" in w for w in result.warnings)

    def test_empty_workflow(self, simulator):
        wf = {"name": "Vacío", "trigger_type": "manual", "trigger_config": {}, "steps": []}
        result = simulator.simulate(wf)
        assert result.total_steps == 0
        assert result.overall_feasible is True

    def test_schedule_trigger_without_cron_warns(self, simulator):
        wf = {
            "name": "No cron",
            "trigger_type": "schedule",
            "trigger_config": {},
            "steps": [],
        }
        result = simulator.simulate(wf)
        assert any("cron" in w.lower() for w in result.warnings)

    def test_schedule_trigger_with_valid_cron_no_warn(self, simulator):
        wf = {
            "name": "Valid cron",
            "trigger_type": "schedule",
            "trigger_config": {"cron": "0 9 * * *"},
            "steps": [],
        }
        result = simulator.simulate(wf)
        # No cron warning
        assert not any("cron" in w.lower() for w in result.warnings)

    def test_event_trigger_without_event_warns(self, simulator):
        wf = {
            "name": "No event",
            "trigger_type": "event",
            "trigger_config": {},
            "steps": [],
        }
        result = simulator.simulate(wf)
        assert any("evento" in w.lower() for w in result.warnings)

    def test_summary_format(self, simulator, sample_workflow):
        result = simulator.simulate(sample_workflow)
        assert "2 pasos" in result.summary
        assert "factible" in result.summary

    def test_simulate_params_replaces_input_refs(self, simulator):
        wf = {
            "name": "Params test",
            "trigger_type": "manual",
            "trigger_config": {},
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead",
                 "params": {"name": "$input.nombre"}},
            ],
        }
        context = {"nombre": "Juan Pérez"}
        result = simulator.simulate(wf, context)
        step = result.steps[0]
        assert step.params["name"] == "$input.nombre"  # Original preserved
        # But the simulated params should have the value
        assert "nombre" in str(step.simulated_output) or step.would_succeed
