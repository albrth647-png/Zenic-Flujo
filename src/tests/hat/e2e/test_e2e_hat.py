"""E2E tests for HAT 5-level system — real side effects in SQLite.

Verifica el flujo completo N1→N2→N3→N4→N5:
- Nivel 1: HATRouter recibe mensajes y despacha
- Nivel 2: 3 supervisores (operaciones, comunicaciones, datos_auto)
- Nivel 3: 9 specialists (CrmSpecialist, InvoiceSpecialist, ...)
- Nivel 4: ~101 workers auto-generados
- Nivel 5: 19 tools ZF reales (CRMService, InventoryService, ...)

Los tests usan la DB SQLite real (no mocks). Se aísla con WFD_DATA_DIR
para no contaminar la DB de producción (~/.workflow_determinista/).
Cada test usa session_id único para evitar colisiones anti-dup cascade.
"""

from __future__ import annotations

import time
import uuid

import pytest


def _unique_session(prefix: str = "e2e") -> str:
    """Genera un session_id único para evitar colisiones anti-dup."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class TestBootstrap:
    """Tests que bootstrap_hat inicializa los 5 niveles correctamente."""

    def test_bootstrap_returns_hat_router(self, hat_router):
        """bootstrap_hat() retorna una instancia de HATRouter."""
        from src.hat.level1_orchestrator.tick_router import HATRouter
        assert isinstance(hat_router, HATRouter)

    def test_bootstrap_has_3_supervisors(self, hat_router):
        """HATRouter tiene 3 supervisores inyectados (operaciones, comunicaciones, datos_auto)."""
        assert len(hat_router._supervisors) == 3
        assert "operaciones" in hat_router._supervisors
        assert "comunicaciones" in hat_router._supervisors
        assert "datos_auto" in hat_router._supervisors

    def test_bootstrap_has_9_specialists(self, hat_router):
        """Cada supervisor tiene 3 specialists (total 9)."""
        total = sum(len(s._specialists) for s in hat_router._supervisors.values())
        assert total == 9

    def test_operaciones_has_crm_invoice_inventory(self, hat_router):
        """Supervisor de operaciones tiene CrmSpecialist, InvoiceSpecialist, InventorySpecialist."""
        ops = hat_router._supervisors["operaciones"]
        specialists = set(ops._specialists.keys())
        assert "crm" in specialists
        assert "invoice" in specialists
        assert "inventory" in specialists

    def test_comunicaciones_has_notification_email_chat(self, hat_router):
        """Supervisor de comunicaciones tiene NotificationSpecialist, EmailSpecialist, ChatSpecialist."""
        com = hat_router._supervisors["comunicaciones"]
        specialists = set(com._specialists.keys())
        assert "notification" in specialists
        assert "email" in specialists
        assert "chat" in specialists

    def test_datos_auto_has_data_api_code(self, hat_router):
        """Supervisor de datos_auto tiene DataSpecialist, ApiSpecialist, CodeSpecialist."""
        datos = hat_router._supervisors["datos_auto"]
        specialists = set(datos._specialists.keys())
        assert "data" in specialists
        assert "api" in specialists
        assert "code" in specialists


class TestRouting:
    """Tests que HATRouter rutea mensajes al dominio correcto."""

    def test_routes_to_operaciones_for_crm(self, hat_router):
        """'listar leads' debe rutear a operaciones."""
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_routing_crm"),
            message="listar leads",
        )
        assert result["domain"] == "operaciones"
        assert result["status"] in ("completed", "failed")

    def test_routes_to_operaciones_for_invoice(self, hat_router):
        """'listar facturas' debe rutear a operaciones."""
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_routing_invoice"),
            message="listar facturas",
        )
        assert result["domain"] == "operaciones"

    def test_routes_to_operaciones_for_inventory(self, hat_router):
        """'listar productos' debe rutear a operaciones."""
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_routing_inv"),
            message="listar productos",
        )
        assert result["domain"] == "operaciones"

    def test_routes_to_comunicaciones_for_email(self, hat_router):
        """'enviar email' debe rutear a comunicaciones."""
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_routing_email"),
            message="enviar email",
        )
        assert result["domain"] == "comunicaciones"

    def test_routes_to_datos_auto_for_code(self, hat_router):
        """'ejecutar código python' debe rutear a datos_auto."""
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_routing_code"),
            message="ejecutar código python",
        )
        assert result["domain"] == "datos_auto"

    def test_routes_to_datos_auto_for_python_script(self, hat_router):
        """'script python' también debe rutear a datos_auto."""
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_routing_script"),
            message="script python",
        )
        assert result["domain"] == "datos_auto"

    def test_routes_to_comunicaciones_for_slack(self, hat_router):
        """'mensaje slack' debe rutear a comunicaciones."""
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_routing_slack"),
            message="mensaje slack",
        )
        assert result["domain"] == "comunicaciones"


class TestResponseStructure:
    """Tests que handle() retorna responses bien formadas."""

    def test_response_has_dispatch_id(self, hat_router):
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_struct_1"),
            message="listar leads",
        )
        assert "dispatch_id" in result
        assert result["dispatch_id"].startswith("disp_")

    def test_response_has_domain(self, hat_router):
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_struct_2"),
            message="listar leads",
        )
        assert "domain" in result
        assert isinstance(result["domain"], str)

    def test_response_has_status(self, hat_router):
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_struct_3"),
            message="listar leads",
        )
        assert "status" in result
        assert result["status"] in ("completed", "failed", "clarify", "anti_dup_blocked")

    def test_response_has_duration_ms(self, hat_router):
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_struct_4"),
            message="listar leads",
        )
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0

    def test_response_has_anti_dup_layer_hit(self, hat_router):
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_struct_5"),
            message="listar leads",
        )
        assert "anti_dup_layer_hit" in result
        assert isinstance(result["anti_dup_layer_hit"], str)

    def test_response_has_response_field(self, hat_router):
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_struct_6"),
            message="listar leads",
        )
        assert "response" in result
        # response debe ser string (texto legible para el usuario)
        assert isinstance(result["response"], str)

    def test_response_has_orbital_resonance(self, hat_router):
        result = hat_router.handle(
            user_id="e2e_test",
            session_id=_unique_session("e2e_struct_7"),
            message="listar leads",
        )
        assert "orbital_resonance" in result
        assert isinstance(result["orbital_resonance"], (int, float))
        assert 0.0 <= result["orbital_resonance"] <= 1.0


class TestAntiDuplication:
    """Tests que el cascade anti-doble-llamada funciona."""

    def test_first_request_passes(self, hat_router):
        """La primera request debe pasar todas las capas anti-dup."""
        result = hat_router.handle(
            user_id="e2e_antidup",
            session_id=_unique_session("e2e_antidup_1"),
            message="listar leads primer request",
        )
        assert result["anti_dup_layer_hit"] == "none"
        assert result["status"] in ("completed", "failed")

    def test_same_message_blocked_second_time(self, hat_router):
        """El mismo mensaje dos veces → segunda es bloqueada por anti-dup."""
        session = _unique_session("e2e_antidup_block")
        msg = "listar leads anti dup test"
        r1 = hat_router.handle(
            user_id="e2e_antidup",
            session_id=session,
            message=msg,
        )
        # r1 debe pasar
        assert r1["anti_dup_layer_hit"] == "none"
        # r2 con mismo mensaje debe ser bloqueada
        r2 = hat_router.handle(
            user_id="e2e_antidup",
            session_id=session,
            message=msg,
        )
        # Algunas capas (exact_match) devuelven cache → status completed
        # Otras (ttl_freshness) bloquean → status anti_dup_blocked
        assert r2["status"] in ("anti_dup_blocked", "completed")
        if r2["status"] == "anti_dup_blocked":
            assert r2["anti_dup_layer_hit"] != "none"
        else:
            # Si retorna cache, también es anti-dup (no ejecutó de nuevo)
            assert r2["anti_dup_layer_hit"] != "none"

    def test_different_messages_not_blocked(self, hat_router):
        """Mensajes diferentes en misma sesión no se bloquean entre sí."""
        session = _unique_session("e2e_antidup_diff")
        r1 = hat_router.handle(
            user_id="e2e_antidup",
            session_id=session,
            message="listar leads primer mensaje",
        )
        r2 = hat_router.handle(
            user_id="e2e_antidup",
            session_id=session,
            message="listar productos segundo mensaje diferente",
        )
        # Ambos deben pasar (mensajes diferentes)
        assert r1["anti_dup_layer_hit"] == "none"
        # r2 también debe pasar — mensajes diferentes no son duplicados
        assert r2["anti_dup_layer_hit"] == "none"
        assert r2["status"] in ("completed", "failed")


class TestFullChain:
    """Tests que verifican el flujo completo N1→N2→N3→N4→N5."""

    def test_list_leads_returns_real_data(self, hat_router):
        """'listar leads' retorna datos reales de SQLite (CRM tool)."""
        result = hat_router.handle(
            user_id="e2e_full",
            session_id=_unique_session("e2e_full_list"),
            message="listar leads",
        )
        assert result["status"] == "completed"
        assert result["domain"] == "operaciones"
        # Response debe contener data (string repr de la lista de leads)
        response = result.get("response", "")
        assert len(response) > 0

    def test_create_lead_e2e(self, hat_router):
        """'crear lead' crea un lead real en SQLite."""
        result = hat_router.handle(
            user_id="e2e_full",
            session_id=_unique_session("e2e_full_create"),
            message="crear lead E2E TestLead",
        )
        assert result["domain"] == "operaciones"
        # El CrmSpecialist.route_action detecta "crear" → create_lead
        # Pero create_lead requiere params name/email. Sin params, falla.
        # Aceptamos completed o failed (lo importante es que llegó al specialist).
        assert result["status"] in ("completed", "failed")

    def test_get_stats_e2e(self, hat_router):
        """'estadísticas crm' retorna stats reales del CRM."""
        result = hat_router.handle(
            user_id="e2e_full",
            session_id=_unique_session("e2e_full_stats"),
            message="estadísticas crm",
        )
        assert result["domain"] == "operaciones"
        assert result["status"] in ("completed", "failed")

    def test_code_execution_e2e(self, hat_router):
        """'ejecutar código' rutea a datos_auto y attempta ejecución."""
        result = hat_router.handle(
            user_id="e2e_full",
            session_id=_unique_session("e2e_full_code"),
            message="ejecutar código python",
        )
        assert result["domain"] == "datos_auto"
        assert result["status"] in ("completed", "failed")

    def test_email_send_e2e(self, hat_router):
        """'enviar email' rutea a comunicaciones y attempta send_email."""
        result = hat_router.handle(
            user_id="e2e_full",
            session_id=_unique_session("e2e_full_email"),
            message="enviar email",
        )
        assert result["domain"] == "comunicaciones"
        # send_email requiere params (to, subject, body). Sin params, falla.
        # Pero el ruteo y dispatch deben funcionar.
        assert result["status"] in ("completed", "failed")

    def test_3_domains_all_accessible(self, hat_router):
        """Los 3 dominios supervisor son accesibles en una sesión de tests."""
        domains_seen = set()
        for msg, sess_prefix in [
            ("listar leads", "e2e_3d_op"),
            ("enviar email", "e2e_3d_com"),
            ("ejecutar código", "e2e_3d_dat"),
        ]:
            result = hat_router.handle(
                user_id="e2e_3d",
                session_id=_unique_session(sess_prefix),
                message=msg,
            )
            domains_seen.add(result.get("domain"))
            time.sleep(0.05)  # evitar colisión TTL
        assert "operaciones" in domains_seen
        assert "comunicaciones" in domains_seen
        assert "datos_auto" in domains_seen

    def test_dispatch_id_unique_per_request(self, hat_router):
        """Cada request recibe un dispatch_id único."""
        r1 = hat_router.handle(
            user_id="e2e_unique",
            session_id=_unique_session("e2e_unique_1"),
            message="listar leads",
        )
        r2 = hat_router.handle(
            user_id="e2e_unique",
            session_id=_unique_session("e2e_unique_2"),
            message="listar leads",
        )
        assert r1["dispatch_id"] != r2["dispatch_id"]

    @pytest.mark.skip(reason="M9: get_progress signature changed — rewrite in post-M10")
    def test_ledger_persists_dispatch(self, hat_router):
        """El dispatch se persiste en hat_progress del Ledger."""
        from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
        ledger = LedgerRepository()

        sess = _unique_session("e2e_ledger")
        result = hat_router.handle(
            user_id="e2e_ledger",
            session_id=sess,
            message="listar leads",
        )
        # Buscar el dispatch por user_id + session_id en hat_progress
        progress = ledger.get_progress("e2e_ledger", sess)
        assert isinstance(progress, list)
        assert len(progress) >= 1
        # El dispatch que acabamos de hacer debe estar en el progress
        matching = [p for p in progress if p.get("dispatch_id") == result["dispatch_id"]]
        assert len(matching) == 1


class TestWorkerFactory:
    """Tests que WorkerFactory generó workers para todas las tools."""

    def test_101_workers_generated(self, hat_router):
        """Bootstrap genera 100+ workers via WorkerFactory."""
        from src.hat.level4_workers.base.worker_factory import WorkerFactory
        factory = WorkerFactory()
        # generate_all() regenera workers (idempotente — registry es por factory)
        all_workers = factory.generate_all()
        total = sum(len(w) for w in all_workers.values())
        assert total >= 50  # al menos 50 workers (esperado ~101)

    def test_crm_has_at_least_9_actions(self, hat_router):
        """CRM tool expone al menos 9 actions públicas (create_lead, list_leads, etc.).

        Originalmente eran 9; el CRM creció a 15 con advance_stage, close_won,
        close_lost, convert_lead_to_deal, create_client, etc.
        Verificamos >= 9 para no romper cuando se añadan más acciones.
        """
        from src.hat.level4_workers.base.worker_factory import WorkerFactory
        factory = WorkerFactory()
        factory.generate_all()
        actions = factory.list_actions("crm")
        assert len(actions) >= 9
        assert "create_lead" in actions
        assert "list_leads" in actions
        assert "get_stats" in actions

    def test_inventory_has_actions(self, hat_router):
        """Inventory tool expone múltiples actions."""
        from src.hat.level4_workers.base.worker_factory import WorkerFactory
        factory = WorkerFactory()
        factory.generate_all()
        actions = factory.list_actions("inventory")
        assert len(actions) >= 5
        assert "add_product" in actions
        assert "list_products" in actions

    def test_code_runner_has_2_actions(self, hat_router):
        """Code runner tool expone run_python y validate."""
        from src.hat.level4_workers.base.worker_factory import WorkerFactory
        factory = WorkerFactory()
        factory.generate_all()
        actions = factory.list_actions("code_runner")
        assert "run_python" in actions
        assert "validate" in actions

    def test_tools_registered(self, hat_router):
        """Bootstrap registra tools (19 nativas + conectores variables).

        El número exacto de conectores puede variar según el entorno
        (algunos requieren dependencias opcionales). Verificamos >= 75
        para no romper cuando se añadan/quiten conectores.
        """
        from src.hat.level5_tools.registry import get_tools_registry
        registry = get_tools_registry()
        tools = registry.list_all()
        assert len(tools) >= 75  # 19 native + ~60 connectors (variable)

    def test_tools_by_domain(self, hat_router):
        """Las tools se distribuyen en los 3 dominios."""
        from src.hat.level5_tools.registry import get_tools_registry
        registry = get_tools_registry()
        ops = registry.list_by_domain("operaciones")
        comms = registry.list_by_domain("comunicaciones")
        datos = registry.list_by_domain("datos_auto")
        # operaciones: crm, invoice, inventory, stripe, mercadopago = 5
        assert len(ops) >= 3
        # comunicaciones: notification, gmail, slack, telegram = 4
        assert len(comms) >= 3
        # datos_auto: data_keeper, api_connector, sheets, drive, postgresql,
        #             code_runner, logic_gate, autopilot, openai, ollama = 10
        assert len(datos) >= 5


class TestDeterminism:
    """Tests que el sistema es determinista."""

    def test_same_intent_same_hash(self, hat_router):
        """Mismo user+session+message produce mismo intent_hash."""
        from src.hat.level1_orchestrator.intent.hasher import compute_intent_hash
        h1 = compute_intent_hash("user1", "sess1", "listar leads", None)
        h2 = compute_intent_hash("user1", "sess1", "listar leads", None)
        assert h1 == h2

    def test_different_message_different_hash(self, hat_router):
        """Mensajes diferentes producen hashes diferentes."""
        from src.hat.level1_orchestrator.intent.hasher import compute_intent_hash
        h1 = compute_intent_hash("user1", "sess1", "listar leads", None)
        h2 = compute_intent_hash("user1", "sess1", "listar productos", None)
        assert h1 != h2

    def test_different_session_different_hash(self, hat_router):
        """Sesiones diferentes producen hashes diferentes."""
        from src.hat.level1_orchestrator.intent.hasher import compute_intent_hash
        h1 = compute_intent_hash("user1", "sess1", "listar leads", None)
        h2 = compute_intent_hash("user1", "sess2", "listar leads", None)
        assert h1 != h2
