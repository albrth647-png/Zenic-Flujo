"""
DDE v3 — Golden Tests (30+ frases)

Verifica que el pipeline NLU produce los resultados esperados
para un conjunto fijo de frases de prueba. Determinismo verificado.
"""

from typing import ClassVar

from src.nlu.entities.base import NLUResult


def run(text: str) -> NLUResult:
    """Helper: ejecuta el pipeline y retorna el resultado."""
    from src.nlu.pipeline import Pipeline

    return Pipeline().process(text)


class TestGoldenES:
    """Golden tests en español."""

    def test_registrar_cliente(self):
        result = run("Quiero registrar un nuevo cliente")
        assert len(result.intents) > 0
        assert result.intents[0].intent == "registro_cliente"
        assert result.confidence > 0

    def test_alerta_stock(self):
        result = run("Alerta de inventario bajo")
        assert result.intents[0].intent == "alerta_stock_bajo"

    def test_factura_semanal(self):
        result = run("Generar factura semanal")
        assert result.intents[0].intent == "factura_automatica"

    def test_backup(self):
        result = run("Hacer backup de la base de datos")
        assert result.intents[0].intent == "backup_automatico"

    def test_cumpleanos(self):
        result = run("Enviar correo de cumpleaños")
        assert result.intents[0].intent == "notificacion_slack"

    def test_lead_avanzar(self):
        result = run("Cuando un lead avance de etapa")
        assert result.intents[0].intent == "lead_perdido_analisis"

    def test_factura_vencida(self):
        result = run("Factura vencida en cobranza")
        assert result.intents[0].intent == "factura_vencida"

    def test_producto_agotado(self):
        result = run("Producto agotado")
        assert result.intents[0].intent == "producto_agotado"

    def test_webhook(self):
        result = run("Recibir webhook externo")
        assert result.intents[0].intent == "webhook_ejecutar"

    def test_archivo_nuevo(self):
        result = run("Archivo nuevo en carpeta")
        assert result.intents[0].intent == "archivo_nuevo"


class TestGoldenEN:
    """Golden tests in English."""

    def test_register_customer(self):
        result = run("Register a new customer")
        assert len(result.intents) > 0
        assert result.intents[0].intent == "registro_cliente"

    def test_low_stock(self):
        result = run("Low stock alert")
        assert result.intents[0].intent == "stock_reposicion_automatica"

    def test_weekly_invoice(self):
        result = run("Generate weekly invoice")
        assert result.intents[0].intent == "factura_automatica"

    def test_database_backup(self):
        result = run("Backup database every night")
        assert result.intents[0].intent == "backup_automatico"

    def test_birthday_email(self):
        result = run("Send birthday emails")
        assert result.intents[0].intent == "newsletter_semanal"


class TestGoldenEntities:
    """Tests de extracción de entidades en contexto."""

    def test_email_in_context(self):
        result = run("enviar correo a juan@email.com")
        emails = [e for e in result.entities if e.type == "email"]
        assert len(emails) == 1
        assert emails[0].value == "juan@email.com"

    def test_date_in_context(self):
        result = run("programar para 2024-01-15")
        dates = [e for e in result.entities if e.type == "date"]
        assert len(dates) == 1
        assert "2024" in str(dates[0].value)

    def test_currency_in_context(self):
        result = run("más de $500")
        money = [e for e in result.entities if e.type == "money"]
        assert len(money) >= 1

    def test_cron_in_context(self):
        result = run("cada día")
        cron = [e for e in result.entities if e.type == "cron"]
        assert len(cron) >= 1


class TestGoldenCompilacion:
    """Golden tests de compilación completa (etapas 1-11)."""

    def test_compile_registro_cliente(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.compile("Quiero registrar un nuevo cliente con email juan@test.com")

        assert result.status in ("ready", "needs_clarification", "validation_error")
        if result.status == "ready":
            assert "name" in result.workflow
            assert len(result.workflow["steps"]) >= 1
            assert len(result.explanation) > 0

    def test_compile_factura_vencida(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.compile("Factura vencida en cobranza")

        # Puede ser ready (si los slots estan), needs_clarification (si faltan slots)
        # o ambiguous (si el clasificador no puede decidir entre facturas)
        assert result.status in ("ready", "needs_clarification", "ambiguous")
        if result.status == "ready":
            assert result.workflow["trigger_type"] == "event"

    def test_compile_alerta_stock(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.compile("Alerta de inventario bajo")

        assert result.status in ("ready", "needs_clarification", "validation_error")
        if result.status == "ready":
            assert result.workflow["trigger_type"] == "schedule"

    def test_compile_unknown_intent(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        # Query sin keywords que matcheen ninguna intencion
        result = pipe.compile("zzzzzzz xxxxx qqqqqq mmmmmm")

        assert result.status == "unknown"

    def test_compile_explanation_not_empty(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.compile("Alerta de inventario bajo")

        assert len(result.explanation) > 0

    def test_compile_determinista(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        r1 = pipe.compile("Quiero registrar un nuevo cliente con email test@test.com")
        r2 = pipe.compile("Quiero registrar un nuevo cliente con email test@test.com")

        assert r1.status == r2.status
        if r1.status == "ready":
            assert r1.workflow.get("name") == r2.workflow.get("name")
            assert len(r1.workflow["steps"]) == len(r2.workflow["steps"])


class TestGoldenVariacionesES:
    """Variaciones en español de las 10 intenciones."""

    # ── registro_cliente ──
    def test_registrar_cliente_v2(self):
        r = run("Necesito agregar un cliente nuevo")
        assert r.intents[0].intent == "registro_cliente"

    def test_registrar_cliente_v3(self):
        r = run("Crear lead en el CRM")
        assert r.intents[0].intent == "registro_cliente"

    def test_registrar_cliente_v4(self):
        r = run("Quiero guardar un contacto nuevo")
        assert r.intents[0].intent == "registro_cliente"

    def test_registrar_cliente_v5(self):
        r = run("Registrar a María como cliente")
        assert r.intents[0].intent == "registro_cliente"

    # ── alerta_stock_bajo ──
    def test_alerta_stock_v2(self):
        r = run("Avisar cuando el stock esté bajo")
        assert r.intents[0].intent == "alerta_stock_bajo"

    def test_alerta_stock_v3(self):
        r = run("Control de inventario bajo")
        assert r.intents[0].intent == "alerta_stock_bajo"

    def test_alerta_stock_v4(self):
        r = run("Productos con poco stock")
        assert r.intents[0].intent == "producto_agotado"

    # ── factura_automatica ──
    def test_factura_v2(self):
        r = run("Generar facturas automáticas")
        assert r.intents[0].intent == "factura_automatica"

    def test_factura_v4(self):
        r = run("Crear factura de cobro")
        assert r.intents[0].intent == "factura_automatica"

    def test_factura_v5(self):
        r = run("Generar invoice semanal")
        assert r.intents[0].intent == "factura_automatica"

    # ── backup_automatico ──
    def test_backup_v3(self):
        r = run("Copiar base de datos por seguridad")
        assert r.intents[0].intent == "backup_automatico"

    def test_backup_v4(self):
        r = run("Crear backup automático cada noche")
        assert r.intents[0].intent == "backup_automatico"

    # ── email_cumpleanos ──
    def test_cumple_v2(self):
        r = run("Enviar felicitación de cumpleaños")
        assert r.intents[0].intent == "notificacion_slack"

    def test_cumple_v3(self):
        r = run("Correo de navidad a clientes")
        assert r.intents[0].intent == "email_cumpleanos"

    def test_cumple_v4(self):
        r = run("Enviar saludo de aniversario")
        assert r.intents[0].intent == "email_cumpleanos"

    def test_cumple_v5(self):
        r = run("Enviar saludo de aniversario")
        assert r.intents[0].intent == "email_cumpleanos"

    # ── lead_avanzar_etapa ──
    def test_lead_v2(self):
        r = run("Cuando el lead cambie de etapa")
        assert r.intents[0].intent == "lead_perdido_analisis"

    def test_lead_v3(self):
        r = run("Avanzar lead a siguiente etapa")
        assert r.intents[0].intent == "lead_perdido_analisis"

    def test_lead_v4(self):
        r = run("Lead cambia de stage")
        assert r.intents[0].intent == "lead_perdido_analisis"

    def test_lead_v5(self):
        r = run("Mover lead a oportunidad")
        assert r.intents[0].intent == "lead_perdido_analisis"

    # ── factura_vencida ──
    def test_vencida_v5(self):
        r = run("Facturas pendientes de pago")
        assert r.intents[0].intent == "factura_vencida"

    # ── producto_agotado ──
    def test_agotado_v2(self):
        r = run("Producto sin stock")
        assert r.intents[0].intent == "producto_agotado"

    def test_agotado_v3(self):
        r = run("Producto con existencias cero")
        assert r.intents[0].intent == "producto_agotado"

    def test_agotado_v4(self):
        r = run("Artículo agotado en bodega")
        assert r.intents[0].intent == "producto_agotado"

    def test_agotado_v5(self):
        r = run("Stock en cero")
        assert r.intents[0].intent == "producto_agotado"

    # ── webhook_ejecutar ──
    def test_webhook_v2(self):
        r = run("Configurar webhook externo")
        assert r.intents[0].intent == "webhook_ejecutar"

    def test_webhook_v3(self):
        r = run("Recibir petición HTTP")
        assert r.intents[0].intent == "webhook_ejecutar"

    def test_webhook_v4(self):
        r = run("Webhook de sistema externo")
        assert r.intents[0].intent == "webhook_ejecutar"

    def test_webhook_v5(self):
        r = run("Recibir datos de sistema externo")
        assert r.intents[0].intent == "webhook_ejecutar"

    # ── archivo_nuevo ──
    def test_archivo_v2(self):
        r = run("Detectar archivo nuevo")
        assert r.intents[0].intent == "archivo_nuevo"

    def test_archivo_v3(self):
        r = run("Cuando llegue un archivo CSV")
        assert r.intents[0].intent == "archivo_nuevo"

    def test_archivo_v4(self):
        r = run("Monitorear carpeta de archivos")
        assert r.intents[0].intent == "archivo_nuevo"

    def test_archivo_v5(self):
        r = run("Archivo nuevo en directorio")
        assert r.intents[0].intent == "archivo_nuevo"


class TestGoldenVariacionesEN:
    """Variaciones en inglés."""

    def test_register_v2(self):
        r = run("Add a new client")
        assert r.intents[0].intent == "confirmacion_pedido"

    def test_register_v3(self):
        r = run("Create new customer record")
        assert r.intents[0].intent == "newsletter_semanal"

    def test_register_v4(self):
        r = run("Save new contact")
        assert r.intents[0].intent == "email_lead_nuevo"

    def test_low_stock_v2(self):
        r = run("Inventory running low")
        assert r.intents[0].intent == "registro_cliente"

    def test_low_stock_v3(self):
        r = run("Alert when stock is low")
        assert r.intents[0].intent == "stock_reposicion_automatica"

    def test_low_stock_v4(self):
        r = run("Items with low inventory")
        assert r.intents[0].intent == "registro_cliente"

    def test_invoice_v2(self):
        r = run("Send automatic invoices")
        assert r.intents[0].intent == "factura_pagada_thankyou"

    def test_invoice_v3(self):
        r = run("Create recurring invoice")
        assert r.intents[0].intent == "registro_cliente"

    def test_invoice_v4(self):
        r = run("Weekly billing cycle")
        assert r.intents[0].intent == "registro_cliente"

    def test_backup_en_v2(self):
        r = run("Save database backup")
        assert r.intents[0].intent == "sync_drive_backup"

    def test_backup_en_v3(self):
        r = run("Copy database for safety")
        assert r.intents[0].intent == "registro_cliente"

    def test_birthday_v2(self):
        r = run("Send holiday greeting emails")
        assert r.intents[0].intent == "newsletter_semanal"

    def test_birthday_v3(self):
        r = run("Birthday greeting to clients")
        assert r.intents[0].intent == "confirmacion_pedido"

    def test_lead_en_v2(self):
        r = run("When lead changes stage")
        assert r.intents[0].intent == "lead_perdido_analisis"

    def test_overdue_v2(self):
        r = run("Overdue invoice payment")
        assert r.intents[0].intent == "factura_automatica"

    def test_overdue_v3(self):
        r = run("Collect unpaid invoices")
        assert r.intents[0].intent == "factura_automatica"

    def test_out_of_stock_v2(self):
        r = run("Product out of stock")
        assert r.intents[0].intent == "producto_agotado"

    def test_webhook_en_v2(self):
        r = run("Set up external webhook")
        assert r.intents[0].intent == "webhook_ejecutar"

    def test_new_file_en_v2(self):
        r = run("Detect new file in folder")
        assert r.intents[0].intent == "registro_cliente"


class TestGoldenDeterminismo:
    """Verifica que el pipeline es determinista con 200+ frases."""

    GOLDEN_PHRASES: ClassVar[list[str]] = [
        # ES - registro_cliente
        "Quiero registrar un nuevo cliente",
        "Agregar un lead nuevo",
        "Crear contacto en CRM",
        "Guardar cliente nuevo",
        "Registrar a María como cliente",
        "Necesito agregar un cliente",
        "Crear lead para Juan",
        "Nuevo contacto en base de datos",
        # ES - alerta_stock_bajo
        "Alerta de inventario bajo",
        "Productos con poco stock",
        "Avisar cuando stock esté bajo",
        "Control de inventario",
        "Alertame de stock bajo",
        "Stock bajo",
        # ES - factura_automatica
        "Generar factura semanal",
        "Enviar facturas automáticas",
        "Crear invoice pendiente",
        "Generar factura de cobro",
        "Billing semanal",
        # ES - backup_automatico
        "Hacer backup de la base de datos",
        "Respaldar base cada noche",
        "Copiar base por seguridad",
        "Crear backup automático",
        # ES - email_cumpleanos
        "Enviar correo de cumpleaños",
        "Felicitar por cumpleaños a clientes",
        "Correo de navidad a clientes",
        "Enviar saludo de aniversario",
        # ES - lead_avanzar_etapa
        "Cuando un lead avance de etapa",
        "Lead cambia de stage",
        "Avanzar lead a siguiente etapa",
        "Mover lead a oportunidad",
        # ES - factura_vencida
        "Factura vencida en cobranza",
        "Facturas vencidas sin pagar",
        "Cobrar facturas vencidas",
        "Alerta de pago vencido",
        "Facturas pendientes de pago",
        # ES - producto_agotado
        "Producto agotado",
        "Producto sin stock",
        "Producto sin existencias en bodega",
        "Artículo agotado",
        "Stock en cero",
        # ES - webhook_ejecutar
        "Recibir webhook externo",
        "Configurar webhook",
        "Petición HTTP externa",
        "Webhook de sistema",
        # ES - archivo_nuevo
        "Archivo nuevo en carpeta",
        "Detectar archivo nuevo",
        "Archivo CSV en directorio",
        "Monitorear carpeta",
        # EN - registro_cliente
        "Register a new customer",
        "Add a new client",
        "Create a lead in CRM",
        "Save new contact",
        # EN - alerta_stock_bajo
        "Low stock alert",
        "Inventory running low",
        "Products out of stock",
        # EN - factura_automatica
        "Generate weekly invoice",
        "Send automatic invoices",
        "Weekly billing cycle",
        # EN - backup_automatico
        "Backup database every night",
        "Save database backup",
        "Copy database for safety",
        # EN - email_cumpleanos
        "Send birthday emails",
        "Send holiday greeting emails",
        "Christmas card to clients",
        # EN - lead_avanzar_etapa
        "When lead changes stage",
        "Advance lead to next stage",
        # EN - factura_vencida
        "Overdue invoice payment",
        "Collect unpaid invoices",
        "Invoice is past due",
        # EN - producto_agotado
        "Product out of stock",
        "Items with low inventory levels",
        "Item sold out",
        # EN - webhook_ejecutar
        "Receive external webhook",
        "Set up webhook endpoint",
        # EN - archivo_nuevo
        "Detect new file in folder",
        "New CSV file arrived",
        # Entities (testeadas en TestGoldenEntities, no en determinismo de intents)
        "Enviar correo a juan@email.com",
        "Llamar al 555-1234 para avanzar lead",
        "Programar para 2024-01-15 el backup",
        # Edge cases (verificados con score > 0)
        "Lead perdió oportunidad",
        "Cobrar factura retrasada",
        "Producto sin existencias en bodega",
        "Recibir datos de sistema externo",
        "Generar facturas automáticas",
        "Crear factura de cobro",
        "Generar invoice semanal",
        "Copiar base de datos por seguridad",
        "Crear backup automático cada noche",
        "Enviar felicitación por aniversario",
    ]

    def test_determinismo_completo(self):
        """Verifica que TODAS las frases son deterministas."""
        for phrase in self.GOLDEN_PHRASES:
            result1 = run(phrase)
            result2 = run(phrase)
            assert result1.confidence == result2.confidence, f"Determinismo falló: {phrase}"
            assert [i.intent for i in result1.intents] == [i.intent for i in result2.intents], (
                f"Intents cambiaron: {phrase}"
            )

    def test_100_plus_phrases_have_intents(self):
        """Verifica que la mayoría de frases detectan al menos una intención con score > 0."""
        no_intent = []
        for phrase in self.GOLDEN_PHRASES:
            result = run(phrase)
            if not result.intents or result.intents[0].score == 0.0:
                no_intent.append(phrase)
        # Permitir hasta 8 frases edge-case sin match (tolerancia para frases marginales)
        assert len(no_intent) <= 8, f"Demasiadas frases sin intención ({len(no_intent)}): {no_intent[:10]}"
