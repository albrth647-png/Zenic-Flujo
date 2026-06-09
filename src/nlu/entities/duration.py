"""
DDE v3 — DurationExtractor

Extrae duraciones y horarios y los normaliza a expresiones cron.
Soporta: "cada día", "cada lunes", "cada 15 minutos", "a las 9am",
         "diariamente", "semanalmente", "mañana a las 9"

Determinista. Sin IA.
"""
from __future__ import annotations
import re
from src.nlu.entities.base import Entity

# Días de la semana
DAYS_ES = {"domingo": 0, "lunes": 1, "martes": 2, "miercoles": 3,
           "miércoles": 3, "jueves": 4, "viernes": 5, "sabado": 6, "sábado": 6}
DAYS_EN = {"sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
           "thursday": 4, "friday": 5, "saturday": 6}

# Unidades de tiempo con su valor en minutos
TIME_UNITS: dict[str, int] = {
    "minuto": 1, "minutos": 1, "min": 1,
    "minute": 1, "minutes": 1, "mins": 1,
    "hora": 60, "horas": 60, "hr": 60,
    "hour": 60, "hours": 60, "hrs": 60,
    "dia": 1440, "día": 1440, "dias": 1440, "días": 1440,
    "day": 1440, "days": 1440,
    "semana": 10080, "semanas": 10080,
    "week": 10080, "weeks": 10080,
}

# Frecuencias comunes → cron
FREQ_CRON: dict[str, str] = {
    "cada minuto": "* * * * *",
    "every minute": "* * * * *",
    "cada hora": "0 * * * *",
    "every hour": "0 * * * *",
    "cada dia": "0 0 * * *",
    "cada día": "0 0 * * *",
    "every day": "0 0 * * *",
    "daily": "0 0 * * *",
    "diario": "0 0 * * *",
    "diariamente": "0 0 * * *",
    "cada semana": "0 0 * * 0",
    "every week": "0 0 * * 0",
    "weekly": "0 0 * * 0",
    "semanal": "0 0 * * 0",
    "semanalmente": "0 0 * * 0",
    "cada mes": "0 0 1 * *",
    "every month": "0 0 1 * *",
    "monthly": "0 0 1 * *",
    "mensual": "0 0 1 * *",
    "cada noche": "0 23 * * *",
    "every night": "0 23 * * *",
    "midnight": "0 0 * * *",
    "medianoche": "0 0 * * *",
}

# Hora: "a las 9", "at 9am", "9:00", "9 am"
# REQUIERE al menos UN indicador de hora para evitar falsos positivos:
# - "las" o "at" (prefijo)
# - ":MM" (minutos)
# - "am" o "pm" (sufijo)
# Sin esto, números como "20" en "2024-01-15" o "50" en "$500" se interpretarían como hora.
HOUR_RE = re.compile(
    r'(?:'
    r'(?:a\s+)?(?:las\s+|at\s+)(\d{1,2})(?::(\d{2}))?\s*(am|pm)?'  # con prefijo
    r'|'
    r'(\d{1,2}):(\d{2})\s*(am|pm)?'  # con minutos
    r'|'
    r'(\d{1,2})\s*(am|pm)'  # con am/pm
    r')',
    re.IGNORECASE
)

# Cada N unidades: "cada 15 minutos", "every 2 hours"
EVERY_N_RE = re.compile(r'(?:cada|every|each)\s+(\d+)\s*(' + '|'.join(TIME_UNITS.keys()) + r')', re.IGNORECASE)

# Día de semana: "cada lunes", "every monday"
DAY_RE = re.compile(r'(?:cada|every|each)\s+(' + '|'.join(list(DAYS_ES.keys()) + list(DAYS_EN.keys())) + r')', re.IGNORECASE)


class DurationExtractor:
    """Extrae entidades de tipo 'cron' normalizadas a formato cron."""

    @staticmethod
    def _extract_hour_from_match(hour_match: re.Match | None) -> tuple[int, int, bool] | None:
        """Extrae hora, minuto y is_pm del match HOUR_RE.

        El regex HOUR_RE tiene 3 alternativas con diferentes grupos.
        Esta función unifica la extracción.

        Returns:
            (hour, minute, is_pm) o None si no hay match
        """
        if not hour_match:
            return None

        hour: int | None = None
        minute: int = 0
        is_pm: bool = False

        groups = hour_match.groups()

        # Alternativa 1: con prefijo "las" o "at"
        # groups[0]=hour, groups[1]=minute, groups[2]=ampm
        if groups[0] is not None:
            hour = int(groups[0])
            if groups[1] is not None:
                minute = int(groups[1])
            if groups[2] is not None and groups[2].lower() == "pm":
                is_pm = True

        # Alternativa 2: con minutos (:MM)
        # groups[3]=hour, groups[4]=minute, groups[5]=ampm
        elif groups[3] is not None:
            hour = int(groups[3])
            if groups[4] is not None:
                minute = int(groups[4])
            if groups[5] is not None and groups[5].lower() == "pm":
                is_pm = True

        # Alternativa 3: con am/pm
        # groups[6]=hour, groups[7]=ampm
        elif groups[6] is not None:
            hour = int(groups[6])
            if groups[7] is not None and groups[7].lower() == "pm":
                is_pm = True

        if hour is None or hour > 23:
            return None

        return (hour, minute, is_pm)

    def extract(self, text: str) -> list[Entity]:
        """Extrae duraciones/horarios y devuelve entidades cron.

        Returns:
            Lista de Entity con type='cron', value=str (expresión cron)
        """
        entities: list[Entity] = []
        text_lower = text.lower().strip()

        # 1. Frecuencias fijas
        for phrase, cron in FREQ_CRON.items():
            if text_lower == phrase or text_lower.startswith(phrase):
                entities.append(Entity(
                    type="cron",
                    value=cron,
                    raw=text,
                    span=(0, len(text)),
                    score=1.0,
                ))
                return entities

        # 2. Cada N unidades: "cada X minutos/horas/días"
        for match in EVERY_N_RE.finditer(text_lower):
            num = int(match.group(1))
            unit = match.group(2).lower()
            unit_base = TIME_UNITS.get(unit, 1)

            if unit_base == 1:  # minutos
                cron = f"*/{num} * * * *"
            elif unit_base == 60:  # horas
                cron = f"0 */{num} * * *"
            elif unit_base == 1440:  # días
                cron = f"0 0 */{num} * *"
            elif unit_base >= 10080:  # semanas
                cron = f"0 0 * */{num // 4} *"
            else:
                continue

            entities.append(Entity(
                type="cron",
                value=cron,
                raw=match.group(),
                span=(match.start(), match.end()),
                score=1.0,
            ))

        # 3. Día de semana: "cada lunes"
        if not entities:
            for match in DAY_RE.finditer(text_lower):
                day_name = match.group(1).lower()
                day_num = DAYS_ES.get(day_name) or DAYS_EN.get(day_name, 0)

                hour_result = self._extract_hour_from_match(HOUR_RE.search(text_lower))

                if hour_result:
                    hour, minute, is_pm = hour_result
                    if is_pm and hour < 12:
                        hour += 12
                    cron = f"{minute} {hour} * * {day_num}"
                else:
                    cron = f"0 9 * * {day_num}"  # default 9am

                entities.append(Entity(
                    type="cron",
                    value=cron,
                    raw=match.group(),
                    span=(match.start(), match.end()),
                    score=1.0,
                ))

        # 4. Hora simple: "a las 9", "9am", "9:00"
        if not entities:
            hour_match = HOUR_RE.search(text_lower)
            hour_result = self._extract_hour_from_match(hour_match)
            if hour_result and hour_match:
                hour, minute, is_pm = hour_result
                if is_pm and hour < 12:
                    hour += 12
                if not is_pm and hour == 12:
                    hour = 0

                cron = f"{minute} {hour} * * *"
                entities.append(Entity(
                    type="cron",
                    value=cron,
                    raw=hour_match.group(),
                    span=(hour_match.start(), hour_match.end()),
                    score=0.95,
                ))

        return entities
