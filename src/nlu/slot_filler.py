"""
DDE v3 — SlotFiller (Etapa 6)

Mapea entidades extraídas a los slots requeridos por cada intención.
Determinista: mismo intent + mismas entidades → mismos slots.

Cada intención define sus slots (nombre, tipo, required, default).
El SlotFiller mapea entidades → slots por tipo y por palabra-ancla.
"""
from __future__ import annotations
from src.nlu.entities.base import Entity, IntentMatch, Slot


# ── Definición de slots por intención ───────────────────
# Cada intención tiene su lista de slots (nombre, tipo, required, default)
INTENT_SLOTS: dict[str, list[dict[str, object]]] = {
    "registro_cliente": [
        {"name": "nombre", "entity_type": "text", "required": True, "default": ""},
        {"name": "email_destino", "entity_type": "email", "required": True, "default": ""},
        {"name": "telefono", "entity_type": "phone", "required": False, "default": ""},
    ],
    "alerta_stock_bajo": [
        {"name": "email_admin", "entity_type": "email", "required": False, "default": "$settings.admin_email"},
        {"name": "umbral_stock", "entity_type": "qty", "required": False, "default": "10"},
    ],
    "factura_automatica": [
        {"name": "frecuencia", "entity_type": "cron", "required": True, "default": "0 9 * * 1"},
        {"name": "email_admin", "entity_type": "email", "required": False, "default": "$settings.admin_email"},
    ],
    "backup_automatico": [
        {"name": "frecuencia", "entity_type": "cron", "required": True, "default": "0 23 * * *"},
    ],
    "email_cumpleanos": [
        {"name": "frecuencia", "entity_type": "cron", "required": True, "default": "0 8 * * *"},
    ],
    "lead_avanzar_etapa": [
        {"name": "email_admin", "entity_type": "email", "required": False, "default": "$settings.admin_email"},
    ],
    "factura_vencida": [
        {"name": "email_cliente", "entity_type": "email", "required": True, "default": ""},
    ],
    "producto_agotado": [
        {"name": "email_admin", "entity_type": "email", "required": False, "default": "$settings.admin_email"},
    ],
    "webhook_ejecutar": [
        {"name": "url_webhook", "entity_type": "url", "required": True, "default": ""},
    ],
    "archivo_nuevo": [
        {"name": "carpeta", "entity_type": "text", "required": False, "default": "/uploads"},
    ],
}

# Mapeo entity_type → slot (para matching automático)
ENTITY_TO_SLOT_MAP: dict[str, str] = {
    "email": "email_destino",
    "phone": "telefono",
    "cron": "frecuencia",
    "url": "url_webhook",
    "qty": "umbral_stock",
    "money": "monto",
    "number": "monto",
    "condition": "condicion",
}


class SlotFiller:
    """Llena los slots de una intención usando entidades extraídas."""

    def fill(
        self,
        intents: tuple[IntentMatch, ...],
        entities: tuple[Entity, ...],
    ) -> tuple[Slot, ...]:
        """Llena slots para la mejor intención usando entidades disponibles.

        Args:
            intents: Intenciones detectadas (ordenadas por score)
            entities: Entidades extraídas del texto

        Returns:
            Tupla de slots llenos/vacíos según lo disponible
        """
        if not intents:
            return ()

        best_intent = intents[0].intent
        slot_defs = INTENT_SLOTS.get(best_intent, [])

        if not slot_defs:
            return ()

        return self._fill_slots(best_intent, slot_defs, entities)

    def fill_for_intent(
        self,
        intent_name: str,
        entities: tuple[Entity, ...],
    ) -> tuple[Slot, ...]:
        """Llena slots para una intención específica por nombre.

        Args:
            intent_name: Nombre de la intención
            entities: Entidades extraídas

        Returns:
            Tupla de slots
        """
        slot_defs = INTENT_SLOTS.get(intent_name, [])
        if not slot_defs:
            return ()
        return self._fill_slots(intent_name, slot_defs, entities)

    def _fill_slots(
        self,
        intent_name: str,
        slot_defs: list[dict[str, object]],
        entities: tuple[Entity, ...],
    ) -> tuple[Slot, ...]:
        """Lógica interna de llenado de slots."""
        result: list[Slot] = []

        for slot_def in slot_defs:
            name = slot_def.get("name", "")
            entity_type: str = slot_def.get("entity_type", "text")  # type: ignore
            required: bool = slot_def.get("required", False)  # type: ignore
            default_val: object = slot_def.get("default", "")

            # Buscar entidad que matchee con este slot
            matched_entity = self._find_entity(entities, name, entity_type)

            if matched_entity is not None:
                result.append(Slot(
                    name=name,
                    required=required,
                    filled=True,
                    value=matched_entity,
                    source="entity",
                ))
            elif default_val:
                result.append(Slot(
                    name=name,
                    required=required,
                    filled=True,
                    value=default_val,
                    source="default",
                ))
            else:
                result.append(Slot(
                    name=name,
                    required=required,
                    filled=False,
                    value=None,
                    source="entity",
                ))

        return tuple(result)

    def _find_entity(
        self,
        entities: tuple[Entity, ...],
        slot_name: str,
        entity_type: str,
    ) -> object:
        """Busca la mejor entidad para un slot dado."""
        if not entities:
            return None

        # 1. Buscar por tipo de entidad exacto
        if entity_type == "text":
            # Para slots de texto, no hay entidad que matchee directamente
            return None

        for ent in entities:
            if ent.type == entity_type:
                if isinstance(ent.value, dict):
                    return ent.value.get("value", ent.value)
                return ent.value

        # 2. Fallback: mapeo entity_type → slot_name
        expected_type = None
        for etype, sname in ENTITY_TO_SLOT_MAP.items():
            if sname == slot_name:
                expected_type = etype
                break

        if expected_type:
            for ent in entities:
                if ent.type == expected_type:
                    if isinstance(ent.value, dict):
                        return ent.value.get("value", ent.value)
                    return ent.value

        return None

    def missing_slots(self, slots: tuple[Slot, ...]) -> tuple[str, ...]:
        """Retorna los nombres de slots obligatorios que faltan."""
        return tuple(
            s.name for s in slots if s.required and not s.filled
        )
