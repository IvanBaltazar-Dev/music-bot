"""Modelo de sesión por número de WhatsApp y constantes de estado.

La sesión vive en memoria (rápida y suficiente para flujos cortos). El estado de
la conversación persistente (BOT_ACTIVO / ADMIN_CONTROL) vive en la hoja
`Conversaciones`; aquí solo se modela el avance dentro de un flujo guiado.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict

# --- Estado base ---
STATE_IDLE = "idle"

# --- Flujo "Quiero ir a verlos" ---
STATE_SEE_CITY = "see_city"
STATE_SEE_INTEREST = "see_interest"

# --- Flujo "Quiero contratarlos" (3 pasos agrupados) ---
# Paso 1: fecha + ciudad/localidad.
# Paso 2: tipo de evento + hora aproximada.
# Paso 3: nombre completo o DNI + preferencia de contacto.
STATE_HIRE_STEP1 = "hire_step1"
STATE_HIRE_STEP2 = "hire_step2"
STATE_HIRE_STEP3 = "hire_step3"

# --- Flujo administrativo: registrar evento (confirmación) ---
STATE_ADMIN_EVENT_CONFIRM = "admin_event_confirm"

SEE_STATES = {
    STATE_SEE_CITY,
    STATE_SEE_INTEREST,
}

HIRE_STATES = {
    STATE_HIRE_STEP1,
    STATE_HIRE_STEP2,
    STATE_HIRE_STEP3,
}

ADMIN_EVENT_STATES = {
    STATE_ADMIN_EVENT_CONFIRM,
}

FLOW_STATES = SEE_STATES | HIRE_STATES | ADMIN_EVENT_STATES


@dataclass
class Session:
    whatsapp: str
    state: str = STATE_IDLE
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def in_flow(self) -> bool:
        """True si la sesión está dentro de un flujo guiado activo."""
        return self.state in FLOW_STATES
