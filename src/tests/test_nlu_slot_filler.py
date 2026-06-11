"""
DDE v3 — Tests del SlotFiller
"""

from src.nlu.entities.base import Entity, IntentMatch


class TestSlotFiller:
    """Tests para SlotFiller."""

    def make_email_entity(self, email: str = "test@test.com") -> Entity:
        return Entity(type="email", value=email, raw=email, span=(0, len(email)), score=1.0)

    def make_phone_entity(self, phone: str = "5551234") -> Entity:
        return Entity(type="phone", value=phone, raw=phone, span=(0, len(phone)), score=0.9)

    def test_fill_registro_cliente(self):
        from src.nlu.slot_filler import SlotFiller

        sf = SlotFiller()
        intents = (IntentMatch(intent="registro_cliente", score=0.9, evidence=["registr"]),)
        entities = (self.make_email_entity(), self.make_phone_entity())
        slots = sf.fill(intents, entities)

        assert len(slots) >= 2
        email_slot = next(s for s in slots if s.name == "email_destino")
        assert email_slot.filled is True
        assert email_slot.value == "test@test.com"
        phone_slot = next(s for s in slots if s.name == "telefono")
        assert phone_slot.filled is True

    def test_missing_email(self):
        from src.nlu.slot_filler import SlotFiller

        sf = SlotFiller()
        intents = (IntentMatch(intent="registro_cliente", score=0.9, evidence=["registr"]),)
        entities = ()
        slots = sf.fill(intents, entities)

        email_slot = next(s for s in slots if s.name == "email_destino")
        assert email_slot.filled is False
        assert email_slot.required is True

    def test_no_intents(self):
        from src.nlu.slot_filler import SlotFiller

        sf = SlotFiller()
        slots = sf.fill((), ())
        assert len(slots) == 0

    def test_missing_slots(self):
        from src.nlu.slot_filler import SlotFiller

        sf = SlotFiller()
        intents = (IntentMatch(intent="registro_cliente", score=0.9, evidence=["registr"]),)
        entities = ()
        slots = sf.fill(intents, entities)
        missing = sf.missing_slots(slots)
        assert "email_destino" in missing
        assert "nombre" in missing

    def test_determinista(self):
        from src.nlu.slot_filler import SlotFiller

        sf = SlotFiller()
        intents = (IntentMatch(intent="registro_cliente", score=0.9, evidence=["registr"]),)
        entities = (self.make_email_entity(),)
        r1 = sf.fill(intents, entities)
        r2 = sf.fill(intents, entities)
        assert [s.value for s in r1] == [s.value for s in r2]

    def test_fill_for_intent(self):
        from src.nlu.slot_filler import SlotFiller

        sf = SlotFiller()
        entities = (self.make_email_entity(),)
        slots = sf.fill_for_intent("registro_cliente", entities)
        assert len(slots) == 3
        assert any(s.name == "email_destino" and s.filled for s in slots)
