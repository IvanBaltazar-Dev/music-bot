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
INTENT_CONTACT = "CONTACTO"          # quiere hablar/que lo contacten
INTENT_OFF_TOPIC = "FUERA_DE_TEMA"   # ajeno a la agrupación (no se responde)
INTENT_CLOSING = "DESPEDIDA"         # acuse/cierre: "ok", "gracias", "ya"...
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
ADMIN_MENU = "admin_menu"
ADMIN_VIEW_EVENTS = "view_events"
ADMIN_CLIENT_SUMMARY = "client_summary"   # resumen de la conversación con un cliente

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

# --- Acciones sobre una solicitud (cambios de estado desde el menú) ---
PREFIX_CLOSE = "BTN_CLOSE_"
PREFIX_QUOTE = "BTN_QUOTE_"
PREFIX_DISCARD = "BTN_DISCARD_"
PREFIX_PENDING = "BTN_PENDING_"
# Confirmación: BTN_CONFIRM_<accion>_<codigo>  (ej: BTN_CONFIRM_close_SOL-0002)
PREFIX_CONFIRM = "BTN_CONFIRM_"
BTN_CANCEL = "BTN_CANCEL_ACTION"

# --- Botones del menú principal de administrador ---
MENU_VIEW_REQUESTS = "MENU_VIEW_REQUESTS"
MENU_VIEW_EVENTS = "MENU_VIEW_EVENTS"
MENU_REGISTER_EVENT = "MENU_REGISTER_EVENT"
MENU_METRICS = "MENU_METRICS"
MENU_HELP = "MENU_HELP"

# --- Botones de administración de eventos (llevan el id del evento) ---
PREFIX_EVENT_VIEW = "BTN_EVENT_VIEW_"        # ver detalle + acciones
PREFIX_EVENT_EDIT = "BTN_EVENT_EDIT_"        # abrir menú de campos a editar
PREFIX_EVENT_FIELD = "BTN_EVTFIELD_"          # editar un campo: <campo>_<id>
PREFIX_EVENT_CANCEL = "BTN_EVENT_CANCEL_"     # pedir confirmación de cancelar
PREFIX_EVENT_CANCEL_OK = "BTN_EVENT_CANCELOK_"  # confirmar cancelación
BTN_EVENT_EDIT_OK = "BTN_EVENT_EDITOK"        # confirmar guardar la edición (valor en sesión)

# --- Botón del cliente: elegir un evento de la lista de su ciudad ---
PREFIX_CLIENT_EVENT_PICK = "BTN_EVENTPICK_"   # índice dentro de la lista


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
    INTENT_CONTACT: [
        "a que numero", "los puedo llamar", "puedo llamarlos", "numero de contacto",
        "quiero hablar con", "hablar con alguien", "hablar con un asesor",
        "comunicarme con", "como me comunico", "perdi comunicacion",
        "perdi la comunicacion", "como los contacto", "contactarlos",
        "que numero tienen", "su numero", "telefono",
    ],
    INTENT_CLOSING: [
        "ok", "oka", "okey", "okay", "ya", "listo", "gracias", "grax",
        "muchas gracias", "perfecto", "bueno", "vale", "chau", "chao",
        "adios", "bye", "entendido", "genial", "excelente", "bacan",
        "nada mas", "eso es todo", "esta bien", "todo bien", "de acuerdo",
        "ya esta", "hasta luego", "nos vemos", "despues te escribo",
        "luego te escribo", "ahorita no", "por ahora no",
    ],
    INTENT_CANCEL: [
        "cancelar", "salir", "reiniciar", "empezar de nuevo", "menu",
    ],
}

# Palabras de saludo/relleno: si lo único que hay es esto, es solo un saludo.
_GREETING_FILLERS = {
    "hola", "hl", "hola", "ola", "oa", "holi", "buenas", "buenos", "dias",
    "tardes", "noches", "hey", "hi", "saludos", "como", "estan", "estas",
    "esta", "que", "tal", "todo", "bien", "ustedes", "uds", "con",
}

_ADMIN_KEYWORDS = {
    ADMIN_MENU: ["menu", "inicio", "menu admin", "opciones"],
    ADMIN_REGISTER_EVENT: ["registrar evento", "nuevo evento", "crear evento", "agregar evento"],
    ADMIN_VIEW_EVENTS: ["ver eventos", "ver agenda", "listar eventos", "lista de eventos", "agenda"],
    ADMIN_VIEW_REQUESTS: ["ver solicitudes", "solicitudes", "leads", "cotizaciones"],
    ADMIN_CLIENT_SUMMARY: [
        "resumen de la conversacion", "resumen de la conversación",
        "resumen del cliente", "resumen de este cliente", "resumen del chat",
        "de que hablamos", "de que hablo", "que queria", "que quiere el cliente",
        "contexto del cliente", "con quien hablo", "quien es este cliente",
        "resumen conversacion",
    ],
    ADMIN_VIEW_METRICS: ["metricas", "reporte", "estadisticas", "estadistica", "kpis"],
    ADMIN_RELEASE: ["soltar control", "liberar control", "soltar", "dejar control", "dejar", "salir"],
    ADMIN_CLOSE_REQUEST: ["cerrar solicitud", "cerrar caso", "finalizar solicitud", "finalizar caso", "cerrar"],
    ADMIN_MARK_QUOTED: ["marcar cotizada", "cotizada", "ya se cotizo", "ya cotice", "cliente cotizado", "cotizar"],
    ADMIN_DISCARD_REQUEST: ["descartar solicitud", "descartar caso", "no procede", "cliente no interesado", "descartar"],
    ADMIN_HELP: ["ayuda admin", "comandos admin", "ayuda"],
}

# Orden de prioridad al resolver comandos admin (lo más específico primero)
_ADMIN_PRIORITY = [
    ADMIN_MENU, ADMIN_REGISTER_EVENT, ADMIN_VIEW_EVENTS, ADMIN_CLIENT_SUMMARY,
    ADMIN_VIEW_REQUESTS, ADMIN_VIEW_METRICS, ADMIN_CLOSE_REQUEST,
    ADMIN_MARK_QUOTED, ADMIN_DISCARD_REQUEST, ADMIN_RELEASE, ADMIN_HELP,
]

# Orden de prioridad al resolver intenciones públicas
_INTENT_PRIORITY = [
    INTENT_CANCEL,
    INTENT_HIRE,
    INTENT_SEE_EVENTS,
    INTENT_KNOW_GROUP,
    INTENT_CONTACT,
    INTENT_CLOSING,
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


def is_hash_command(text: str) -> bool:
    """True si el texto empieza con '#': el admin pide ejecutar un comando."""
    return bool(text) and text.lstrip().startswith("#")


def strip_hash(text: str) -> str:
    """Quita el prefijo '#' y espacios. '#cerrar' -> 'cerrar', '#' -> ''."""
    return (text or "").lstrip().lstrip("#").strip()


def detect_admin_command(text: str):
    """Devuelve el comando admin detectado o None."""
    norm = normalize(text)
    if not norm:
        return None
    for command in _ADMIN_PRIORITY:
        if _matches(norm, _ADMIN_KEYWORDS[command]):
            return command
    return None


def _is_pure_greeting(norm: str) -> bool:
    """True si el mensaje es SOLO un saludo (sin una consulta real adentro)."""
    tokens = [t for t in norm.split() if len(t) >= 3]
    meaningful = [t for t in tokens if t not in _GREETING_FILLERS]
    return len(meaningful) == 0


# Intenciones de match "blando": sus keywords son genéricas (saludos, o
# "agrupación/información"), así que conviene que la IA confirme/filtre.
_SOFT_INTENTS = {INTENT_GREETING, INTENT_KNOW_GROUP}

# La IA solo CLASIFICA (ayuda a procesar). Mapea sus categorías a las del bot.
_AI_INTENT_MAP = {
    "GREETING": INTENT_GREETING,
    "QUIERO_IR_A_VERLOS": INTENT_SEE_EVENTS,
    "QUIERO_CONTRATAR": INTENT_HIRE,
    "CONOCE_AGRUPACION": INTENT_KNOW_GROUP,
    "CONTACTO": INTENT_CONTACT,
    "FUERA_DE_TEMA": INTENT_OFF_TOPIC,
    "DESPEDIDA": INTENT_CLOSING,
}


def _classify_with_ai(text: str):
    """Pide a la IA que clasifique. Devuelve una intención del bot o None."""
    if not gemini_service.is_enabled():
        return None
    result = gemini_service.classify_intent(text)
    if not (result.get("success") and result.get("confidence", 0.0) >= 0.6):
        return None
    return _AI_INTENT_MAP.get(result.get("intent", ""))


def detect_intent(text: str) -> str:
    """Devuelve la intención pública. La IA ayuda a procesar (clasificar)
    saludos-con-consulta y mensajes ambiguos; nunca redacta respuestas."""
    norm = normalize(text)
    if not norm:
        return INTENT_UNKNOWN

    rule_intent = None
    for intent in _INTENT_PRIORITY:
        if _matches(norm, _KEYWORDS[intent]):
            rule_intent = intent
            break

    # Intenciones "duras" (keywords específicas) -> se confían directo.
    if rule_intent and rule_intent not in _SOFT_INTENTS:
        return rule_intent

    # Saludo a secas -> saludo (sin gastar IA).
    if rule_intent == INTENT_GREETING and _is_pure_greeting(norm):
        return INTENT_GREETING

    # Matches "blandos" (saludo+consulta, o CONOCE por palabras genéricas como
    # "agrupación") o nada reconocido: la IA ayuda a interpretar y a filtrar
    # lo que está fuera de tema.
    ai_intent = _classify_with_ai(text)
    if ai_intent:
        return ai_intent

    # Sin IA o sin certeza: se respeta la regla; si no había, desconocido.
    return rule_intent or INTENT_UNKNOWN


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


def close_id(code: str) -> str:
    return PREFIX_CLOSE + code


def quote_id(code: str) -> str:
    return PREFIX_QUOTE + code


def discard_id(code: str) -> str:
    return PREFIX_DISCARD + code


def pending_id(code: str) -> str:
    return PREFIX_PENDING + code


def confirm_id(action: str, code: str) -> str:
    """Botón de confirmación. action ∈ {close, quote, discard}."""
    return f"{PREFIX_CONFIRM}{action}_{code}"


# --- IDs de botones de eventos (admin) ---
def event_view_id(event_id: str) -> str:
    return PREFIX_EVENT_VIEW + event_id


def event_edit_id(event_id: str) -> str:
    return PREFIX_EVENT_EDIT + event_id


def event_field_id(field: str, event_id: str) -> str:
    # Separador '~': los nombres de campo llevan '_' y el id lleva '-'.
    return f"{PREFIX_EVENT_FIELD}{field}~{event_id}"


def event_cancel_id(event_id: str) -> str:
    return PREFIX_EVENT_CANCEL + event_id


def event_cancel_ok_id(event_id: str) -> str:
    return PREFIX_EVENT_CANCEL_OK + event_id


def client_event_pick_id(index: int) -> str:
    return f"{PREFIX_CLIENT_EVENT_PICK}{index}"


def parse_admin_button(button_id: str):
    """Devuelve (accion, codigo) para un botón admin, o None.

    accion ∈ {take_control, follow, view, reply_later, switch_control,
              keep_control, close, quote, discard, pending,
              confirm_close, confirm_quote, confirm_discard, cancel, menu}
    """
    if not button_id:
        return None

    # Botones del menú principal (sin código asociado)
    menu_actions = {
        MENU_VIEW_REQUESTS: ("menu_view_requests", ""),
        MENU_VIEW_EVENTS: ("menu_view_events", ""),
        MENU_REGISTER_EVENT: ("menu_register_event", ""),
        MENU_METRICS: ("menu_metrics", ""),
        MENU_HELP: ("menu_help", ""),
        BTN_CANCEL: ("cancel", ""),
        BTN_EVENT_EDIT_OK: ("event_edit_ok", ""),
    }
    if button_id in menu_actions:
        return menu_actions[button_id]

    # Confirmación: BTN_CONFIRM_<accion>_<codigo>
    if button_id.startswith(PREFIX_CONFIRM):
        rest = button_id[len(PREFIX_CONFIRM):]
        action, _, code = rest.partition("_")
        return f"confirm_{action}", code

    # Editar un campo de evento: BTN_EVTFIELD_<campo>_<id> -> ("event_field", "campo_id")
    if button_id.startswith(PREFIX_EVENT_FIELD):
        return "event_field", button_id[len(PREFIX_EVENT_FIELD):]

    for action, prefix in (
        ("switch_control", PREFIX_SWITCH_CONTROL),
        ("keep_control", PREFIX_KEEP_CONTROL),
        ("take_control", PREFIX_TAKE_CONTROL),
        ("follow", PREFIX_FOLLOW),
        ("view", PREFIX_VIEW),
        ("reply_later", PREFIX_REPLY_LATER),
        ("close", PREFIX_CLOSE),
        ("quote", PREFIX_QUOTE),
        ("discard", PREFIX_DISCARD),
        ("pending", PREFIX_PENDING),
        # Eventos (admin)
        ("event_view", PREFIX_EVENT_VIEW),
        ("event_edit", PREFIX_EVENT_EDIT),
        ("event_cancel_ok", PREFIX_EVENT_CANCEL_OK),
        ("event_cancel", PREFIX_EVENT_CANCEL),
        # Cliente: elegir evento
        ("client_event_pick", PREFIX_CLIENT_EVENT_PICK),
    ):
        if button_id.startswith(prefix):
            return action, button_id[len(prefix):]
    return None
