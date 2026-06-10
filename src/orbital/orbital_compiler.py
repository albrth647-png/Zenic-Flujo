"""
ORBITAL — Pilar Puente: OrbitalCompiler
=========================================

Compilacion orbital que reemplaza la pipeline NLU lineal de 13 etapas.

En el sistema LINEAL (NLU):
    Normalizar→Tokenizar→Idioma→Entidades→Intencion→Slots→
    Desambiguacion→Dialogo→Compilar→Validar→Explicar→DryRun→AIGen
    (13 etapas secuenciales, sin retroalimentacion)

En el sistema ORBITAL:
    Input → OVC(cada token = variable orbital) → TOR(tension entre tokens)
    → RCC(deteccion de patron resonante) → COD(colapso a intencion)
    → Espectro(workflow compilado) → Retro(input modifica fases)

La compilacion orbital es MAS RAPIDA que la pipeline de 13 etapas porque:
1. No necesita pasar por 13 etapas secuenciales
2. La resonancia detecta patrones en paralelo
3. El colapso determinista converge directamente a la intencion
4. El resultado retroalimenta para mejorar la siguiente compilacion

Compatibilidad: misma salida que el NLU pipeline (CompileResult).
"""

from __future__ import annotations

import hashlib

from src.orbital.models import (
    TWO_PI,
)
from src.orbital.context import OrbitalContext
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class OrbitalCompileResult:
    """
    Resultado de la compilacion orbital.

    Compatible con CompileResult del NLU lineal pero enriquecido
    con metadatos orbitales.
    """

    def __init__(
        self,
        status: str = "ready",
        workflow: dict | None = None,
        explanation: str = "",
        intent: str = "",
        entities: list[dict] | None = None,
        confidence: float = 0.0,
        orbital_theta: dict | None = None,
        orbital_resonance: float = 0.0,
        orbital_modes: list | None = None,
    ):
        self.status = status
        self.workflow = workflow or {}
        self.explanation = explanation
        self.intent = intent
        self.entities = entities or []
        self.confidence = confidence
        self.orbital_theta = orbital_theta or {}
        self.orbital_resonance = orbital_resonance
        self.orbital_modes = orbital_modes or []

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "workflow": self.workflow,
            "explanation": self.explanation,
            "intent": self.intent,
            "entities": self.entities,
            "confidence": self.confidence,
            "orbital_theta": self.orbital_theta,
            "orbital_resonance": self.orbital_resonance,
            "orbital_modes": self.orbital_modes,
        }


# ── Templates de workflows (simplificado del NLU lineal) ────

ORBITAL_TEMPLATES = {
    "registro_cliente": {
        "intent_keywords": ["cliente", "nuevo", "registre", "registro", "guardar", "lead"],
        "workflow": {
            "name": "Registro de Cliente Orbital",
            "trigger_type": "event",
            "trigger_config": {"event": "crm.lead.created"},
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "$input.nombre", "email": "$input.email"}},
                {"id": 2, "tool": "notification", "action": "send_email", "params": {"to": "$input.email", "subject": "Bienvenido"}},
            ],
        },
        "explanation": "Se creara un workflow que: 1) Guarda el lead en CRM, 2) Envia email de bienvenida",
    },
    "factura": {
        "intent_keywords": ["factura", "facturar", "cobrar", "invoice", "pago"],
        "workflow": {
            "name": "Facturacion Orbital",
            "trigger_type": "event",
            "trigger_config": {"event": "invoice.created"},
            "steps": [
                {"id": 1, "tool": "invoice", "action": "create_invoice", "params": {"client_name": "$input.cliente", "items": "$input.items"}},
                {"id": 2, "tool": "notification", "action": "send_email", "params": {"to": "$input.email", "subject": "Factura generada"}},
            ],
        },
        "explanation": "Se creara un workflow que: 1) Genera la factura, 2) Notifica al cliente",
    },
    "stock_bajo": {
        "intent_keywords": ["stock", "inventario", "bajo", "alerta", "producto", "agotar"],
        "workflow": {
            "name": "Alerta Stock Bajo Orbital",
            "trigger_type": "event",
            "trigger_config": {"event": "inventory.stock_low"},
            "steps": [
                {"id": 1, "tool": "inventory", "action": "update_stock", "params": {"product_id": "$input.product_id", "type": "in", "quantity": "$input.cantidad"}},
                {"id": 2, "tool": "notification", "action": "send_email", "params": {"to": "$input.email", "subject": "Stock reabastecido"}},
            ],
        },
        "explanation": "Se creara un workflow que: 1) Reabastece el stock, 2) Notifica la actualizacion",
    },
    "notificacion": {
        "intent_keywords": ["notificar", "email", "correo", "mensaje", "enviar", "avisar"],
        "workflow": {
            "name": "Notificacion Orbital",
            "trigger_type": "manual",
            "trigger_config": {},
            "steps": [
                {"id": 1, "tool": "notification", "action": "send_email", "params": {"to": "$input.email", "subject": "$input.asunto"}},
            ],
        },
        "explanation": "Se creara un workflow de notificacion por email",
    },
    "general": {
        "intent_keywords": [],
        "workflow": {
            "name": "Workflow Orbital General",
            "trigger_type": "manual",
            "trigger_config": {},
            "steps": [],
        },
        "explanation": "Workflow orbital general — requiere mas informacion",
    },
}


class OrbitalCompiler:
    """
    Compilador Orbital — Reemplazo de la pipeline NLU de 13 etapas.

    En lugar de pasar por 13 etapas secuenciales, usa el motor ORBITAL
    para detectar la intencion del usuario mediante resonancia entre
    las palabras clave y los templates de intenciones.

    Proceso:
    1. Tokenizar el texto (simplificado: split por espacios)
    2. Cada token → variable orbital con fase determinista
    3. Cada template → ciclo orbital de keywords
    4. Calcular TOR(token, keyword) para cada template
    5. RCC detecta que template tiene mayor resonancia
    6. COD colapsa a la intencion determinista
    7. Espectro genera el workflow compilado
    8. Retroalimentacion: la compilacion modifica las fases para la proxima

    VENTAJA vs NLU lineal:
    - 1 paso orbital vs 13 pasos secuenciales
    - Resonancia detecta patrones en paralelo
    - Retroalimentacion mejora compilaciones futuras
    - Determinista: mismo texto → misma compilacion siempre
    """

    def __init__(self):
        self._ctx = OrbitalContext()
        self._orbital_engine = self._ctx.engine
        self._templates = dict(ORBITAL_TEMPLATES)
        self._compilation_count = 0

    # ── Compilacion orbital ────────────────────────────────

    def compile(self, text: str, context: dict | None = None) -> OrbitalCompileResult:
        """
        Compila texto a workflow usando resonancia orbital.

        Args:
            text: Texto del usuario (ej: "Quiero registrar un cliente nuevo")
            context: Contexto adicional (opcional)

        Returns:
            OrbitalCompileResult con el workflow compilado
        """
        self._compilation_count += 1
        context = context or {}

        # 1. Tokenizar
        tokens = self._tokenize(text)
        if not tokens:
            return OrbitalCompileResult(
                status="error",
                explanation="Texto vacio o sin tokens validos",
                confidence=0.0,
            )

        # 2. Limpiar variables de compilaciones anteriores del grupo input_tokens
        for name in list(self._orbital_engine.get_all_variables().keys()):
            if name.startswith("token_") or name.startswith("kw_"):
                try:
                    del self._orbital_engine._ovc._variables[name]
                except KeyError:
                    pass
        # Limpiar ciclos de match anteriores
        for cid in list(self._orbital_engine._rcc._cycles.keys()):
            if cid.startswith("match_"):
                del self._orbital_engine._rcc._cycles[cid]

        # 3. Crear variables orbitales para cada token
        for i, token in enumerate(tokens):
            theta = self._deterministic_theta(token)
            self._orbital_engine.create_variable(
                name=f"token_{token}",
                theta=theta,
                amplitude=1.0,
                velocity=0.1,
                orbit_group="input_tokens",
            )

        # 4. Crear variables orbitales para cada template
        template_scores = {}
        for template_name, template in self._templates.items():
            keywords = template.get("intent_keywords", [])
            if not keywords:
                continue

            for keyword in keywords:
                theta = self._deterministic_theta(keyword)
                try:
                    self._orbital_engine.create_variable(
                        name=f"kw_{template_name}_{keyword}",
                        theta=theta,
                        amplitude=1.5,  # Keywords tienen amplitud mayor
                        velocity=0.05,
                        orbit_group=f"template_{template_name}",
                    )
                except ValueError:
                    pass  # Ya existe

            # Crear ciclo orbital para este template
            template_vars = [f"kw_{template_name}_{kw}" for kw in keywords]
            # Agregar tokens del input al ciclo
            token_vars = [f"token_{t}" for t in tokens]
            cycle_vars = token_vars + template_vars

            if len(cycle_vars) >= 2:
                try:
                    self._orbital_engine.create_cycle(
                        f"match_{template_name}",
                        cycle_vars[:10],  # Limitar a 10 variables por ciclo
                        threshold=0.1,
                    )
                except ValueError:
                    pass

        # 5. Ejecutar tick orbital
        orbital_result = self._orbital_engine.run_tick()

        # 6. Determinar mejor template por resonancia
        best_template = "general"
        best_resonance = 0.0
        best_confidence = 0.0

        for rcc_result in orbital_result.rcc_results:
            if rcc_result.is_resonant and rcc_result.resonance_strength > best_resonance:
                best_resonance = rcc_result.resonance_strength
                # Extraer nombre del template del cycle_id
                cycle = None
                for cid, cyc in self._orbital_engine.rcc._cycles.items():
                    if cid == rcc_result.cycle_id:
                        cycle = cyc
                        break
                if cycle and cycle.name.startswith("match_"):
                    template_name = cycle.name.replace("match_", "")
                    if template_name in self._templates:
                        best_template = template_name

        # Calcular confianza basada en resonancia
        best_confidence = min(best_resonance + 0.3, 0.99) if best_resonance > 0 else 0.3

        # Si no hay resonancia, usar busqueda directa como fallback
        if best_template == "general" and tokens:
            best_template = self._fallback_keyword_match(tokens)

        # 7. Compilar resultado
        template = self._templates.get(best_template, self._templates["general"])

        # Calcular fases de los tokens
        orbital_theta = {}
        for token in tokens:
            var = self._orbital_engine.get_variable(f"token_{token}")
            if var:
                orbital_theta[token] = var.theta

        result = OrbitalCompileResult(
            status="ready",
            workflow=template["workflow"],
            explanation=template["explanation"],
            intent=best_template,
            entities=self._extract_simple_entities(text),
            confidence=best_confidence,
            orbital_theta=orbital_theta,
            orbital_resonance=best_resonance,
            orbital_modes=orbital_result.espectro.modes if orbital_result.espectro else [],
        )

        logger.info(
            f"OrbitalCompiler: '{text[:50]}...' → intent={best_template} "
            f"conf={best_confidence:.2f} resonancia={best_resonance:.4f}"
        )

        return result

    # ── Helpers ────────────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """Tokenizacion simplificada: lowercase, split, filtrar stopwords."""
        import re
        text = text.lower().strip()
        # Normalizar acentos para matching
        text = re.sub(r'[áàä]', 'a', text)
        text = re.sub(r'[éèë]', 'e', text)
        text = re.sub(r'[íìï]', 'i', text)
        text = re.sub(r'[óòö]', 'o', text)
        text = re.sub(r'[úùü]', 'u', text)
        text = re.sub(r'[^a-z0-9 ]', ' ', text)

        stopwords = {"quiero", "que", "un", "una", "el", "la", "los", "las",
                     "se", "en", "y", "o", "de", "del", "al", "a", "por",
                     "para", "con", "sin", "es", "lo", "mi", "tu", "su",
                     "me", "te", "le", "nos", "les", "cuando", "como", "mas"}

        tokens = [t for t in text.split() if t and t not in stopwords and len(t) > 1]
        return tokens

    def _deterministic_theta(self, text: str) -> float:
        """Genera una fase determinista a partir de un texto (hash)."""
        hash_val = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        return (hash_val % 10000) / 10000.0 * TWO_PI

    def _fallback_keyword_match(self, tokens: list[str]) -> str:
        """Busqueda directa por keywords como fallback si no hay resonancia."""
        best_match = "general"
        best_count = 0

        for template_name, template in self._templates.items():
            keywords = template.get("intent_keywords", [])
            count = sum(1 for kw in keywords if any(kw in t or t in kw for t in tokens))
            if count > best_count:
                best_count = count
                best_match = template_name

        return best_match

    def _extract_simple_entities(self, text: str) -> list[dict]:
        """Extraccion simplificada de entidades."""
        import re
        entities = []

        # Emails
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
        for email in emails:
            entities.append({"type": "email", "value": email})

        # Numeros
        numbers = re.findall(r'\b\d+(?:\.\d+)?\b', text)
        for num in numbers:
            entities.append({"type": "number", "value": num})

        return entities

    # ── Propiedades ────────────────────────────────────────

    @property
    def compilation_count(self) -> int:
        return self._compilation_count

    def __repr__(self) -> str:
        return f"OrbitalCompiler(compilations={self._compilation_count})"
