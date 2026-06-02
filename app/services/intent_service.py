"""Detección de intenciones, normalización y corrección de errores.

Pipeline de intenciones:
1. Reglas + normalización
2. Coincidencia aproximada (rapidfuzz/difflib)
3. IA (si está habilitada, como fallback)
4. INTENT_UNKNOWN

La IA es completamente opcional: si falla o no está habilitada, el bot sigue
funcionando con reglas y menú con botones.
"""

from __future__ import annotations

from app.services import gemini_service, text_utils

# `normalize` se mantiene exportado aquí por compatibilidad con otros módulos.
normalize = text_utils.normalize

# --- Intenciones públicas (alineadas con las métricas) ---
INTENT_GREETING = "GREETING"
INTENT_SEE_EVENTS = "QUIERO_IR_A_VERLOS"
INTENT_HIRE = "QUIERO_CONTRATAR"
INTENT_KNOW_GROUP = "CONOCE_AGRUPACION"
INTENT_CANCEL = "CANCEL"
INTENT_UNKNOWN = "UNKNOWN"

# --- Comandos de administrador ---
ADMIN_REGISTER_EVENT = "register_event"
ADMIN_VIEW_REQUESTS = "view_requests"
ADMIN_VIEW_METRICS = "view_metrics"
ADMIN_RELEASE = "release_control"
ADMIN_CLOSE_REQUEST = "close_request"
ADMIN_MARK_QUOTED = "mark_quoted"
ADMIN_DISCARD_REQUEST = "discard_request"
ADMIN_HELP = "admin_help"

# --- IDs de botones: flujos principales ---
FLOW_SEE_EVENTS = "FLOW_SEE_EVENTS"
FLOW_HIRE = "FLOW_HIRE"
FLOW_KNOW_GROUP = "FLOW_KNOW_GROUP"

# --- IDs de botones: "Quiero ir a verlos" (ciudad de origen) ---
BTN_CITY_HUANCAYO = "BTN_CITY_HUANCAYO"
BTN_CITY_LIMA = "BTN_CITY_LIMA"
BTN_CITY_OTHER = "BTN_CITY_OTHER"

# --- IDs de botones: acciones sobre un evento ---
BTN_HELP_ARRIVE = "BTN_HELP_ARRIVE"
BTN_TICKETS = "BTN_TICKETS"
BTN_SHARE = "BTN_SHARE"

# --- IDs de botones: sin evento (interés de localidad) ---
BTN_INTEREST_YES = "BTN_INTEREST_YES"
BTN_OTHER_CITY = "BTN_OTHER_CITY"
BTN_NOT_NOW = "BTN_NOT_NOW"

# --- IDs de botones: "Conoce la agrupación" ---
BTN_WHO = "BTN_WHO"
BTN_VIDEOS = "BTN_VIDEOS"
BTN_MUSIC = "BTN_MUSIC"
BTN_SOCIAL = "BTN_SOCIAL"

# --- Prefijos de botones de administrador (llevan el código de solicitud) ---
PREFIX_TAKE_CONTROL = "BTN_TAKE_CONTROL_"
PREFIX_FOLLOW = "BTN_FOLLOW_"
PREFIX_VIEW = "BTN_VIEW_"
PREFIX_REPLY_LATER = "BTN_REPLY_LATER_"
PREFIX_SWITCH_CONTROL = "BTN_SWITCH_CONTROL_"
PREFIX_KEEP_CONTROL = "BTN_KEEP_CONTROL_"


# Palabras clave por intención (se normalizan al comparar)
_KEYWORDS = {
    INTENT_GREETING: [
        "hola", "hla", "hol", "ola", "buenas", "buenos dias", "buenas tardes",
        "buenas noches", "hey", "hi", "saludos",
    ],
    INTENT_SEE_EVENTS: [
        "quiero ir", "quiero ir a verlos", "ir a verlos", "donde se presentan",
        "cuando tocan", "proxima presentacion", "donde van a estar", "evento",
        "eventos", "concierto", "conciertos", "show", "fecha", "fechas",
        "ubicacion", "entradas", "agenda", "presentacion", "presentaciones",
    ],
    INTENT_HIRE: [
        "quiero contratarlos", "contratar", "contratacion", "precio", "precios",
        "cuanto cobran", "costo", "cotizacion", "para mi evento", "quiero que vengan",
        "presentacion privada", "cumpleanos", "boda", "aniversario", "fiesta patronal",
        "fiesta", "matrimonio", "contrato",
    ],
    INTENT_KNOW_GROUP: [
        "quienes son", "conoce", "conocer", "informacion", "videos", "video",
        "musica", "canciones", "redes", "tiktok", "facebook", "youtube",
        "instagram", "integrantes", "trayectoria", "agrupacion",
    ],
    INTENT_CANCEL: [
        "cancelar", "salir", "reiniciar", "empezar de nuevo", "menu",
    ],
}

_ADMIN_KEYWORDS = {
    ADMIN_REGISTER_EVENT: ["registrar evento", "nuevo evento", "crear evento", "agregar evento"],
    ADMIN_VIEW_REQUESTS: ["ver solicitudes", "solicitudes", "leads", "cotizaciones"],
    ADMIN_VIEW_METRICS: ["metricas", "reporte", "estadisticas", "resumen"],
    ADMIN_RELEASE: ["soltar control", "liberar control", "soltar"],
    ADMIN_CLOSE_REQUEST: ["cerrar solicitud", "cerrar caso", "finalizar solicitud", "finalizar caso"],
    ADMIN_MARK_QUOTED: ["marcar cotizada", "cotizada", "ya se cotizo", "ya cotice", "cliente cotizado"],
    ADMIN_DISCARD_REQUEST: ["descartar solicitud", "descartar caso", "no procede", "cliente no interesado"],
    ADMIN_HELP: ["ayuda admin", "comandos admin", "admin"],
}

# Orden de prioridad al resolver intenciones públicas
_INTENT_PRIORITY = [
    INTENT_CANCEL,
    INTENT_HIRE,
    INTENT_SEE_EVENTS,
    INTENT_KNOW_GROUP,
    INTENT_GREETING,
]

_BUTTON_INTENT = {
    FLOW_SEE_EVENTS: INTENT_SEE_EVENTS,
    FLOW_HIRE: INTENT_HIRE,
    FLOW_KNOW_GROUP: INTENT_KNOW_GROUP,
}


def _matches(norm_text: str, keywords: list[str], cutoff: float = 0.82) -> bool:
    if not norm_text:
        return False

    tokens = norm_text.split()
    token_set = set(tokens)
    single = [k for k in keywords if " " not in k]
    multi = [k for k in keywords if " " in k]

    for phrase in multi:
        if phrase in norm_text:
            return True

    if token_set & set(single):
        return True

    for tok in tokens:
        if len(tok) < 3:
            continue
        if text_utils.best_match(tok, single, cutoff=cutoff):
            return True

    return False


def detect_admin_command(text: str):
    """Devuelve el comando admin detectado o None."""
    norm = normalize(text)
    if not norm:
        return None
    for command in (
        ADMIN_REGISTER_EVENT, ADMIN_VIEW_REQUESTS, ADMIN_VIEW_METRICS,
        ADMIN_INIT_SHEETS, ADMIN_CLOSE_REQUEST, ADMIN_MARK_QUOTED,
        ADMIN_DISCARD_REQUEST, ADMIN_RELEASE, ADMIN_HELP,
    ):
        if _matches(norm, _ADMIN_KEYWORDS[command]):
            return command
    return None


def detect_intent(text: str) -> str:
    """Devuelve la intención pública. INTENT_UNKNOWN si no se reconoce."""
    norm = normalize(text)
    if not norm:
        return INTENT_UNKNOWN

    for intent in _INTENT_PRIORITY:
        if _matches(norm, _KEYWORDS[intent]):
            return intent

    # Gemini como respaldo inteligente (solo si las reglas no resolvieron)
    if gemini_service.is_enabled():
        result = gemini_service.classify_intent(text)
        if result.get("success") and result.get("confidence", 0.0) >= 0.6:
            cand = result.get("intent", "")
            if cand in (INTENT_GREETING, INTENT_SEE_EVENTS, INTENT_HIRE, INTENT_KNOW_GROUP):
                return cand

    return INTENT_UNKNOWN


def button_to_intent(button_id: str):
    """Mapea el id de un botón de flujo principal a una intención pública."""
    return _BUTTON_INTENT.get(button_id)


# ---------------------------------------------------------------------------
# Botones de administrador (llevan el código de solicitud en el id)
# ---------------------------------------------------------------------------
def take_control_id(code: str) -> str:
    return PREFIX_TAKE_CONTROL + code


def follow_id(code: str) -> str:
    return PREFIX_FOLLOW + code


def view_id(code: str) -> str:
    return PREFIX_VIEW + code


def reply_later_id(code: str) -> str:
    return PREFIX_REPLY_LATER + code


def switch_control_id(code: str) -> str:
    return PREFIX_SWITCH_CONTROL + code


def keep_control_id(code: str) -> str:
    return PREFIX_KEEP_CONTROL + code


def parse_admin_button(button_id: str):
    """Devuelve (accion, codigo) para un botón admin, o None.

    accion ∈ {"take_control", "follow", "view", "reply_later", "switch_control", "keep_control"}
    """
    if not button_id:
        return None
    for action, prefix in (
        ("switch_control", PREFIX_SWITCH_CONTROL),
        ("keep_control", PREFIX_KEEP_CONTROL),
        ("take_control", PREFIX_TAKE_CONTROL),
        ("follow", PREFIX_FOLLOW),
        ("view", PREFIX_VIEW),
        ("reply_later", PREFIX_REPLY_LATER),
    ):
        if button_id.startswith(prefix):
            return action, button_id[len(prefix):]
    return None
