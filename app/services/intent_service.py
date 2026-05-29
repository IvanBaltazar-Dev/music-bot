"""Detección de intenciones, normalización y corrección de errores.

Pipeline de intenciones:
1. Reglas + normalización
2. Coincidencia aproximada (difflib)
3. IA (si está habilitada, como fallback)
4. INTENT_UNKNOWN

La IA es completamente opcional: si falla o no está habilitada, el bot sigue
con reglas y fallback a menú con botones.
"""

import difflib
import re
import unicodedata

from app.services import ai_service

# --- Intenciones públicas ---
INTENT_GREETING = "greeting"
INTENT_EVENTS = "events"
INTENT_PRICE = "price"
INTENT_CONTACT = "contact"
INTENT_CANCEL = "cancel"
INTENT_UNKNOWN = "unknown"

# --- Comandos de administrador ---
ADMIN_REGISTER_EVENT = "register_event"
ADMIN_VIEW_REQUESTS = "view_requests"
ADMIN_VIEW_METRICS = "view_metrics"
ADMIN_HELP = "admin_help"

# --- IDs de botones interactivos ---
BTN_MENU_EVENTS = "menu_events"
BTN_MENU_PRICE = "menu_price"
BTN_MENU_CONTACT = "menu_contact"
BTN_EVT_BIRTHDAY = "evt_birthday"
BTN_EVT_WEDDING = "evt_wedding"
BTN_EVT_CORPORATE = "evt_corporate"

# Palabras clave por intención (ya normalizadas: minúsculas, sin tildes)
_KEYWORDS = {
    INTENT_GREETING: [
        "hola", "ola", "hla", "ohla", "lhoa", "olaa", "holaa", "holaaa",
        "buenas", "buenos dias", "buenas tardes", "buenas noches", "hey", "hi",
    ],
    INTENT_EVENTS: [
        "eventos", "evento", "conciertos", "concierto", "presentaciones",
        "presentacion", "agenda", "fechas", "fecha", "tocan",
        "donde se presentan", "cuando hay concierto", "proxima fecha",
    ],
    INTENT_PRICE: [
        "precio", "precios", "costo", "cuanto cobran", "cotizacion",
        "cotisacion", "presio", "contratar", "quiero contratarlos",
        "quiero una presentacion", "disponibilidad", "cuanto esta",
    ],
    INTENT_CONTACT: [
        "contacto", "telefono", "llamar", "whatsapp", "asesor",
        "administrador", "hablar con alguien",
    ],
    INTENT_CANCEL: [
        "cancelar", "salir", "reiniciar", "empezar de nuevo",
    ],
}

_ADMIN_KEYWORDS = {
    ADMIN_REGISTER_EVENT: [
        "registrar evento", "nuevo evento", "crear evento", "agregar evento",
    ],
    ADMIN_VIEW_REQUESTS: [
        "solicitudes", "leads", "cotizaciones", "ver solicitudes",
    ],
    ADMIN_VIEW_METRICS: [
        "metricas", "reporte", "estadisticas", "resumen",
    ],
    ADMIN_HELP: [
        "admin", "ayuda admin", "comandos",
    ],
}

# Orden de prioridad al resolver intenciones públicas
_INTENT_PRIORITY = [
    INTENT_CANCEL,
    INTENT_PRICE,
    INTENT_EVENTS,
    INTENT_CONTACT,
    INTENT_GREETING,
]

_BUTTON_INTENT = {
    BTN_MENU_EVENTS: INTENT_EVENTS,
    BTN_MENU_PRICE: INTENT_PRICE,
    BTN_MENU_CONTACT: INTENT_CONTACT,
}


def normalize(text: str) -> str:
    """minúsculas + sin tildes + sin signos + espacios reducidos."""
    text = (text or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _matches(norm_text: str, keywords: list[str], cutoff: float = 0.75) -> bool:
    if not norm_text:
        return False

    tokens = norm_text.split()
    token_set = set(tokens)
    single = [k for k in keywords if " " not in k]
    multi = [k for k in keywords if " " in k]

    # Frases de varias palabras: por contención directa
    for phrase in multi:
        if phrase in norm_text:
            return True

    # Token exacto
    if token_set & set(single):
        return True

    # Coincidencia aproximada token a token (corrige errores de tipeo)
    for tok in tokens:
        if len(tok) < 3:
            continue
        if difflib.get_close_matches(tok, single, n=1, cutoff=cutoff):
            return True

    return False


def detect_admin_command(text: str):
    """Devuelve el comando admin detectado o None."""
    norm = normalize(text)
    if not norm:
        return None
    # 'registrar/crear/...' tiene prioridad sobre 'admin' suelto
    for command in (ADMIN_REGISTER_EVENT, ADMIN_VIEW_REQUESTS, ADMIN_VIEW_METRICS, ADMIN_HELP):
        if _matches(norm, _ADMIN_KEYWORDS[command]):
            return command
    return None


def detect_intent(text: str) -> str:
    """Devuelve la intención pública. INTENT_UNKNOWN si no se reconoce.

    Pipeline:
    1. Reglas + normalización
    2. Coincidencia aproximada
    3. IA (si está habilitada)
    4. INTENT_UNKNOWN (fallback)
    """
    norm = normalize(text)
    if not norm:
        return INTENT_UNKNOWN

    # 1. Reglas + normalización
    for intent in _INTENT_PRIORITY:
        if _matches(norm, _KEYWORDS[intent]):
            return intent

    # 2. IA como fallback (si está habilitada)
    if ai_service.is_enabled():
        result = ai_service.classify_intent(text)
        if result.get("success"):
            intent = result.get("intent", INTENT_UNKNOWN)
            confidence = result.get("confidence", 0.0)
            # Solo confiar en IA si tiene confianza media-alta
            if confidence >= 0.6:
                return intent

    # 3. Fallback final: INTENT_UNKNOWN
    return INTENT_UNKNOWN


def button_to_intent(button_id: str):
    """Mapea el id de un botón de menú a una intención pública."""
    return _BUTTON_INTENT.get(button_id)
