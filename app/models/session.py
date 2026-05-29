"""Modelo de sesión por número de WhatsApp y constantes de estado."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict

# --- Estado base ---
STATE_IDLE = "idle"

# --- Flujo de cotización (cliente) ---
STATE_Q_LOCATION = "quotation_location"
STATE_Q_DATE = "quotation_date"
STATE_Q_EVENT_TYPE = "quotation_event_type"
STATE_Q_DURATION = "quotation_duration"
STATE_Q_NAME = "quotation_name"
STATE_Q_CONTACT = "quotation_contact"
STATE_Q_COMPLETED = "quotation_completed"

# --- Flujo administrativo (registrar evento) ---
STATE_ADMIN_EVENT_DATE = "admin_event_date"
STATE_ADMIN_EVENT_TIME = "admin_event_time"
STATE_ADMIN_EVENT_CITY = "admin_event_city"
STATE_ADMIN_EVENT_PLACE = "admin_event_place"
STATE_ADMIN_EVENT_DESCRIPTION = "admin_event_description"
STATE_ADMIN_EVENT_CONFIRM = "admin_event_confirm"

QUOTATION_STATES = {
    STATE_Q_LOCATION,
    STATE_Q_DATE,
    STATE_Q_EVENT_TYPE,
    STATE_Q_DURATION,
    STATE_Q_NAME,
    STATE_Q_CONTACT,
    STATE_Q_COMPLETED,
}

ADMIN_EVENT_STATES = {
    STATE_ADMIN_EVENT_DATE,
    STATE_ADMIN_EVENT_TIME,
    STATE_ADMIN_EVENT_CITY,
    STATE_ADMIN_EVENT_PLACE,
    STATE_ADMIN_EVENT_DESCRIPTION,
    STATE_ADMIN_EVENT_CONFIRM,
}


@dataclass
class Session:
    whatsapp: str
    state: str = STATE_IDLE
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def in_flow(self) -> bool:
        """True si la sesión está dentro de un flujo guiado activo."""
        return self.state in QUOTATION_STATES or self.state in ADMIN_EVENT_STATES
