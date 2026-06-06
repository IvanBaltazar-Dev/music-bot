"""Servicio de sesiones y flujos guiados (en memoria).

Mantiene una sesión simple por número de WhatsApp y opera las máquinas de estado:
* "Quiero contratarlos" (cliente) — recoge datos de forma amena, sin formulario.
* Registro de evento (administrador) — confirma antes de guardar.

No realiza efectos secundarios (guardar/notificar): solo avanza el estado y
devuelve el siguiente mensaje. La orquestación aplica los efectos al completar.
El flujo "Quiero ir a verlos" lo coordina `conversation_service` porque depende
de eventos y localidades.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.models.session import (
    Session,
    STATE_IDLE,
    STATE_SEE_CITY,
    STATE_HIRE_STEP1,
    STATE_HIRE_STEP2,
    STATE_HIRE_STEP3,
    STATE_HIRE_CONFIRM,
    STATE_ADMIN_EVENT_COLLECT,
    STATE_ADMIN_EVENT_CONFIRM,
    HIRE_STATES,
    ADMIN_EVENT_STATES,
    FLOW_STATES,
)
from app.repositories import conversation_repository as conv_repo
from app.services import gemini_service, locality_service, text_utils

# --- Almacén de sesiones en memoria ---
_sessions: dict[str, Session] = {}

_AFFIRMATIVE = {"si", "claro", "ok", "okay", "dale", "confirmar", "confirmo", "ya"}

# Tipos de evento conocidos (normalizado -> etiqueta para mostrar).
# Las frases multi-palabra se evalúan antes que las simples.
_EVENT_TYPES = {
    "evento privado": "evento privado",
    "fiesta patronal": "fiesta patronal",
    "fiesta pratonal": "fiesta patronal",
    "fiesta familiar": "fiesta familiar",
    "evento corporativo": "evento corporativo",
    "evento politico": "evento político",
    "mitin politico": "mitin político",
    "miting politico": "mitin político",
    "mitin": "mitin político",
    "miting": "mitin político",
    "tunantada": "Tunantada",
    "huaconada": "Huaconada",
    "yunza": "yunza",
    "cortamonte": "yunza / cortamonte",
    "safa casa": "safa casa",
    "safacasa": "safa casa",
    "herranza": "herranza",
    "santiago": "Santiago",
    "patron santiago": "Patrón Santiago",
    "patron san santiago": "Patrón Santiago",
    "san juan": "San Juan",
    "santa rosa": "Santa Rosa",
    "san pedro": "San Pedro",
    "san pablo": "San Pablo",
    "san sebastian": "San Sebastián",
    "san isidro": "San Isidro",
    "virgen de cocharcas": "Virgen de Cocharcas",
    "virgen del carmen": "Virgen del Carmen",
    "virgen de la candelaria": "Virgen de la Candelaria",
    "virgen de las mercedes": "Virgen de las Mercedes",
    "virgen de chapi": "Virgen de Chapi",
    "senor de muruhuay": "Señor de Muruhuay",
    "senor de los milagros": "Señor de los Milagros",
    "carnaval": "carnaval",
    "carnavales": "carnaval",
    "negreria": "negrería",
    "negritos": "negritos",
    "shacshas": "shacshas",
    "shaqshas": "shacshas",
    "huaylarsh": "huaylarsh",
    "huaylash": "huaylarsh",
    "danza de tijeras": "danza de tijeras",
    "tijeras": "danza de tijeras",
    "wititi": "wititi",
    "diablada": "diablada",
    "morenada": "morenada",
    "caporales": "caporales",
    "tinkus": "tinkus",
    "tinku": "tinkus",
    "aniversario de pueblo": "aniversario de pueblo",
    "aniversario del pueblo": "aniversario de pueblo",
    "aniversario distrital": "aniversario distrital",
    "aniversario comunal": "aniversario comunal",
    "quince anos": "quinceañero",
    "cumpleanos": "cumpleaños",
    "cumple": "cumpleaños",
    "boda": "boda",
    "matrimonio": "matrimonio",
    "aniversario": "aniversario",
    "bautizo": "bautizo",
    "quinceanero": "quinceañero",
    "promocion": "promoción",
    "corporativo": "evento corporativo",
    "graduacion": "graduación",
    "fiesta": "fiesta",
    "concierto": "concierto",
    "dia de la madre": "Día de la Madre",
    "dia de la mama": "Día de la Madre",
    "dia del padre": "Día del Padre",
    "dia del papa": "Día del Padre",
}

_COSTUMBRISTA_EVENT_PATTERNS: list[tuple[str, str]] = [
    (r"\bfiesta\s+(?:patronal|pratonal)\b", "fiesta patronal"),
    (r"\bfiesta\s+(?:costumbrista|tradicional)\b", "fiesta costumbrista"),
    (r"\bfiesta\s+(?:de|del|en)\s+[a-z0-9\s]{3,}\b", "fiesta costumbrista"),
    (r"\b(?:virgen|santa|san|senor|senora)\s+(?:de|del|la|las|los)\s+[a-z0-9\s]{3,}\b",
     "fiesta religiosa costumbrista"),
    (r"\b(?:san|santa)\s+[a-z0-9]{3,}(?:\s+[a-z0-9]{3,})?\b",
     "fiesta religiosa costumbrista"),
    (r"\bpatron\s+(?:santiago|san\s+[a-z0-9]+|de\s+[a-z0-9\s]{3,})\b",
     "fiesta patronal"),
    (r"\baniversario\s+(?:de|del|distrital|comunal|provincial|patrio|de\s+la\s+comunidad)\b",
     "aniversario de pueblo"),
    (r"\b(?:tunantada|huaconada|yunza|cortamonte|herranza|safa\s*casa|carnaval(?:es)?)\b",
     "fiesta costumbrista"),
    (r"\b(?:mitin|miting)\b", "mitin político"),
]

_STOPWORDS = {
    "para", "una", "un", "en", "de", "del", "la", "el", "lo", "los", "las",
    "y", "o", "seria", "sera", "es", "mi", "por", "ahi", "alla", "con", "que",
    "se", "presentacion", "evento", "fiesta", "ciudad", "localidad", "provincia",
    "distrito", "tipo", "fecha", "hora", "horas", "dia", "aprox", "aproximada",
    "a", "al", "las", "los", "desde", "pm", "am", "hoy", "manana", "pasado", "proximo",
    "este", "esta", "quincena", "fin", "fines", "finales", "madre", "mama",
    "padre", "papa", "patronal", "pratonal", "tunantada", "huaconada", "yunza",
    "cortamonte", "herranza", "virgen", "santa", "san", "senor", "senora",
    "santiago", "cocharcas", "carmen", "candelaria", "mercedes", "chapi",
    "muruhuay", "milagros", "mitin", "miting", "politico", "costumbrista",
    # verbos/relleno comunes (no son ciudades)
    "quiero", "quisiera", "queremos", "necesito", "busco", "deseo", "hacer",
    "organizar", "armar", "realizar", "tener", "llevar", "contratar", "gustaria",
    "me", "nos", "algo", "sobre",
    # meses
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "setiembre", "octubre", "noviembre", "diciembre",
    # días
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
}

# Patrones para detectar FECHA y HORA dentro de texto libre (usar sobre `deburr`).
_MONTHS = ("enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
           "septiembre|setiembre|octubre|noviembre|diciembre")
_DAYS = "lunes|martes|miercoles|jueves|viernes|sabado|domingo"

_NUMBER_WORDS = {
    "uno": "1", "una": "1", "dos": "2", "tres": "3", "cuatro": "4",
    "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9",
    "diez": "10", "once": "11", "doce": "12", "trece": "13", "catorce": "14",
    "quince": "15", "dieciseis": "16", "diecisiete": "17", "dieciocho": "18",
    "diecinueve": "19", "veinte": "20", "veintiuno": "21", "veintiuna": "21",
    "veintidos": "22", "veintitres": "23", "veinticuatro": "24",
    "veinticinco": "25", "veintiseis": "26", "veintisiete": "27",
    "veintiocho": "28", "veintinueve": "29", "treinta": "30",
    "treinta y uno": "31", "treinta y una": "31",
}

_DATE_PATTERNS = [
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
    r"\b\d{1,2}\s+de\s+(?:" + _MONTHS + r")(?:\s+de\s+\d{2,4})?\b",
    r"\b(?:primera|segunda)\s+quincena\s+de\s+(?:" + _MONTHS + r")\b",
    r"\bquincena\s+de\s+(?:" + _MONTHS + r")\b",
    r"\b(?:a\s+)?(?:fin|fines|finales)\s+de\s+(?:mes|" + _MONTHS + r")\b",
    r"\bfin\s+de\s+mes\b",
    r"\bdia\s+de\s+la\s+(?:madre|mama)\b",
    r"\bdia\s+del\s+(?:padre|papa)\b",
    r"\b(?:hoy|manana|pasado\s+manana)\b",
    r"\b(?:este|proximo|el)?\s*fin\s+de\s+semana\b",
    r"\b(?:este|proximo|el)\s+(?:" + _DAYS + r")\b",
    r"\b(?:" + _DAYS + r")\b",
]

_TIME_PATTERNS = [
    r"\b\d{1,2}:\d{2}\b",
    r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.?m\.?|p\.?m\.?)\b",
    r"\b\d{1,2}\s+de\s+la\s+(?:tarde|noche|manana)\b",
    r"\b\d{1,2}\s*(?:h|hrs|horas)\b",
    r"\ba\s+las?\s+\d{1,2}(?::\d{2})?\b",
    r"\bde\s+la\s+(?:tarde|noche|manana)\b",
]


def _replace_number_words(text: str) -> str:
    """Convierte números escritos a dígitos para reutilizar los patrones simples."""
    for word, value in sorted(_NUMBER_WORDS.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(rf"\b{re.escape(word)}\b", value, text, flags=re.IGNORECASE)
    return text


def _search_first(patterns: list[str], soft_text: str) -> str:
    for p in patterns:
        m = re.search(p, soft_text)
        if m:
            return m.group(0).strip()
    return ""


def _format_date_reference(value: str) -> str:
    norm = text_utils.normalize(value)
    if norm in ("dia de la madre", "dia de la mama"):
        return "Día de la Madre"
    if norm in ("dia del padre", "dia del papa"):
        return "Día del Padre"
    if norm.startswith("a fin de "):
        return norm.removeprefix("a ")
    if norm == "el fin de semana":
        return "fin de semana"
    return value.strip()


def _extract_date_reference(soft_text: str) -> str:
    return _format_date_reference(_search_first(_DATE_PATTERNS, soft_text))


def _remove_matches(patterns: list[str], soft_text: str) -> str:
    for p in patterns:
        soft_text = re.sub(p, " ", soft_text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", soft_text).strip()


def _resp(text, buttons=None, completed=False, kind=None, data=None, cancelled=False):
    return {
        "text": text,
        "buttons": buttons,
        "completed": completed,
        "kind": kind,
        "data": data or {},
        "cancelled": cancelled,
    }


# ---------------------------------------------------------------------------
# Manejo de sesiones
# ---------------------------------------------------------------------------
def get_session(number: str) -> Session:
    session = _sessions.get(number)
    if session is None:
        session = _restore_session(number)
        _sessions[number] = session
    return session


def refresh_session(number: str) -> Session:
    """Sincroniza el flujo al inicio de cada webhook.

    Cada worker mantiene su propia memoria. Por eso no basta con restaurar solo
    cuando la sesión no existe: un worker puede conservar un paso anterior
    mientras otro ya avanzó y persistió el siguiente.
    """
    current = _sessions.get(number)
    try:
        conv = conv_repo.get(number)
        if conv is None:
            return current or get_session(number)

        state = str(conv.get("paso_actual", "") or "")
        if state in FLOW_STATES:
            session = Session(
                whatsapp=number,
                state=state,
                data=conv_repo.get_temp_data(number),
            )
            _sessions[number] = session
            return session

        if current is not None and current.state in FLOW_STATES:
            current = Session(whatsapp=number)
            _sessions[number] = current
        return current or get_session(number)
    except Exception:  # noqa: BLE001
        return current or get_session(number)


def clear_session(number: str) -> None:
    _sessions.pop(number, None)
    try:
        conv_repo.clear_flow(number)
    except Exception:  # noqa: BLE001
        pass


def _restore_session(number: str) -> Session:
    """Recupera el flujo persistido cuando otro worker atiende el mensaje."""
    try:
        conv = conv_repo.get(number) or {}
        state = str(conv.get("paso_actual", "") or "")
        data = conv_repo.get_temp_data(number)
        if state in FLOW_STATES and isinstance(data, dict):
            return Session(whatsapp=number, state=state, data=data)
    except Exception:  # noqa: BLE001
        pass
    return Session(whatsapp=number)


def _persist(session: Session) -> None:
    try:
        if session.state in FLOW_STATES:
            conv_repo.save_flow(session.whatsapp, session.state, session.data)
        else:
            conv_repo.clear_flow(session.whatsapp)
    except Exception:  # noqa: BLE001
        pass


def _touch(session: Session, state: str) -> None:
    session.state = state
    session.updated_at = datetime.utcnow()
    _persist(session)


def set_state(number: str, state: str) -> Session:
    """Cambia el estado de la sesión (usado por flujos coordinados externamente)."""
    session = get_session(number)
    _touch(session, state)
    return session


def start_see(number: str) -> Session:
    """Inicia el flujo 'Quiero ir a verlos' (espera la ciudad de origen)."""
    session = get_session(number)
    session.data = {}
    _touch(session, STATE_SEE_CITY)
    return session


# ---------------------------------------------------------------------------
# Parsing de localidad + tipo de evento
# ---------------------------------------------------------------------------
def detect_event_type(text: str) -> str:
    """Devuelve la etiqueta del tipo de evento detectado, o ''."""
    norm = text_utils.normalize(text)
    if not norm:
        return ""
    # multi-palabra primero (más específico)
    multi = [k for k in _EVENT_TYPES if " " in k]
    single = [k for k in _EVENT_TYPES if " " not in k]
    for kw in sorted(multi, key=len, reverse=True):
        if kw in norm:
            return _EVENT_TYPES[kw]
    tokens = set(norm.split())
    generic_single = {"fiesta", "aniversario"}
    for kw in [k for k in single if k not in generic_single]:
        if kw in tokens:
            return _EVENT_TYPES[kw]
    for pattern, label in _COSTUMBRISTA_EVENT_PATTERNS:
        if re.search(pattern, norm):
            return label
    for kw in generic_single:
        if kw in tokens:
            return _EVENT_TYPES[kw]
    return ""


def _extract_unknown_city(text: str, tipo_label: str) -> str:
    """Intenta extraer un nombre de ciudad cuando no está en `Localidades`."""
    original_soft = _replace_number_words(text_utils.deburr(text))
    has_date_hint = bool(_search_first(_DATE_PATTERNS, original_soft))
    has_place_hint = bool(re.search(r"\b(?:en|para|de|del)\s+\w+", original_soft))
    if not (tipo_label or has_date_hint or has_place_hint):
        return ""

    soft = _remove_matches(_DATE_PATTERNS + _TIME_PATTERNS, original_soft)
    norm = text_utils.normalize(soft)
    tipo_norm = text_utils.normalize(tipo_label)
    for kw in tipo_norm.split():
        norm = norm.replace(kw, " ")
    palabras = [
        w for w in norm.split()
        if w not in _STOPWORDS and len(w) > 2 and not w.isdigit()
    ]
    if not palabras:
        return ""
    return " ".join(palabras).title()


def parse_location_type(text: str) -> dict:
    """Detecta localidad y tipo de evento en un texto libre."""
    loc = locality_service.buscar_localidad(text)
    tipo = detect_event_type(text)

    if loc is not None:
        city_name = locality_service.nombre_de(loc)
        city_given = True
    else:
        city_name = _extract_unknown_city(text, tipo)
        city_given = bool(city_name)

    return {
        "loc": loc,
        "city_given": city_given,
        "city_name": city_name,
        "tipo_given": bool(tipo),
        "tipo": tipo,
    }


# ---------------------------------------------------------------------------
# Flujo "Quiero contratarlos" (3 pasos agrupados)
# ---------------------------------------------------------------------------
_FIELD_LABELS = {
    "fecha_evento": "la fecha del evento",
    "localidad": "la ciudad o localidad",
    "tipo_evento": "el tipo de evento",
    "horario_evento": "la hora aproximada",
}


def _parse_hire_step1(text: str) -> dict:
    """Extrae fecha, localidad, tipo de evento y hora de un mensaje libre."""
    soft = _replace_number_words(text_utils.deburr(text))
    loc = locality_service.buscar_localidad(text)
    tipo = detect_event_type(text)
    hora = _search_first(_TIME_PATTERNS, soft)
    fecha = _extract_date_reference(soft)
    localidad = locality_service.nombre_de(loc) if loc is not None else _extract_unknown_city(text, tipo)
    return {"loc": loc, "localidad": localidad, "tipo": tipo, "fecha": fecha, "hora": hora}


def _missing_step1(d: dict) -> list[str]:
    return [k for k in ("fecha_evento", "localidad") if not d.get(k)]


def _missing_step2(d: dict) -> list[str]:
    return [k for k in ("tipo_evento", "horario_evento") if not d.get(k)]


def _looks_like_costumbrista_event(answer: str) -> bool:
    norm = text_utils.normalize(answer)
    return bool(re.search(
        r"\b(?:fiesta|festividad|costumbre|costumbrista|tradicional|patron|virgen|"
        r"santo|santa|san|senor|senora|aniversario|comunidad|pueblo)\b",
        norm,
    ))


def _ask_missing_step1(missing: list[str]):
    if "fecha_evento" in missing:
        if "localidad" in missing:
            return _resp(
                "No me quedó clara la fecha. ¿Me la indicas junto con la ciudad? "
                "Por ejemplo:\n"
                "• 15/10 en Huancayo\n"
                "• quincena de octubre en Jauja\n"
                "• Día de la Madre en Lima"
            )
        return _resp(
            "No entendí bien la fecha. ¿Me la escribes de nuevo? Puede ser: 15/10, "
            "quincena de octubre, fin de mes o Día del Padre."
        )

    return _resp(
        "Ya tengo la fecha. Me falta la ciudad o localidad: ¿dónde sería el evento?"
    )


def _ask_missing_step2(session: Session, missing: list[str], answer: str):
    if "tipo_evento" in missing:
        attempts = int(session.data.get("tipo_evento_intentos", 0)) + 1
        session.data["tipo_evento_intentos"] = attempts

        if attempts >= 2 and _looks_like_costumbrista_event(answer):
            session.data["tipo_evento"] = "fiesta costumbrista"
            missing = _missing_step2(session.data)
            if not missing:
                return _ask_hire_step3(session)
            return _resp(
                "Lo registro como fiesta costumbrista. Solo me falta la hora aproximada."
            )

        if attempts >= 2:
            return _resp(
                "No logré entender qué tipo de evento es. ¿Me lo escribes más "
                "directo? Por ejemplo: fiesta patronal, Tunantada, yunza, mitin "
                "político, aniversario de pueblo o evento privado."
            )

        if "horario_evento" in missing:
            return _resp(
                "Tengo la fecha y el lugar. ¿Qué tipo de evento será y a qué hora "
                "aproximada? Por ejemplo: Tunantada, Huaconada, yunza, fiesta "
                "patronal, mitin político, aniversario de pueblo, Virgen de "
                "Cocharcas o Patrón Santiago."
            )

        return _resp(
            "Ya tengo la hora, pero no entendí bien el tipo de evento. ¿Me lo "
            "escribes como fiesta patronal, Tunantada, yunza, mitin político, "
            "aniversario de pueblo o evento privado?"
        )

    return _resp(
        "Ya tengo el tipo de evento. Ahora me falta la hora aproximada: "
        "¿a qué hora sería?"
    )


def _store_hire_details(session: Session, answer: str, *, include_place_date: bool = True) -> None:
    parsed = _parse_hire_step1(answer)
    if include_place_date and parsed["localidad"]:
        session.data["localidad"] = parsed["localidad"]
        session.data["frase_contratacion"] = \
            locality_service.obtener_frase_contratacion(parsed["loc"])
    if parsed["tipo"]:
        session.data["tipo_evento"] = parsed["tipo"]
        session.data.pop("tipo_evento_intentos", None)
    if include_place_date and parsed["fecha"]:
        session.data["fecha_evento"] = parsed["fecha"]
    if parsed["hora"]:
        session.data["horario_evento"] = parsed["hora"]


def _ai_fill_missing(session: Session, answer: str) -> None:
    """Cuando el regex no entendió, la IA interpreta y completa lo que falte.
    Marca los campos rellenados por IA como 'por confirmar'."""
    faltan = set(_missing_step1(session.data)) | set(_missing_step2(session.data))
    if not faltan:
        return
    ai = gemini_service.interpret_event_fields(answer)
    if not ai:
        return
    pendientes = session.data.setdefault("por_confirmar", [])
    mapping = {"fecha_evento": "fecha", "horario_evento": "hora", "tipo_evento": "tipo"}
    for field, ai_key in mapping.items():
        if field in faltan and ai.get(ai_key):
            session.data[field] = ai[ai_key]
            if field not in pendientes:
                pendientes.append(field)


def _accept_after_retries(session: Session, answer: str, missing: list[str]) -> None:
    """Anti-bucle: tras varios intentos, acepta y sigue para no trabar al cliente,
    y marca el/los campo(s) para que el admin lo confirme luego.

    Para fecha/hora guardamos lo que dijo el cliente (suele ser una referencia
    válida que el regex no captó, ej 'fin de semana'). Para lugar/tipo usamos un
    marcador y conservamos el texto del cliente en observaciones."""
    ans = (answer or "").strip()
    pendientes = session.data.setdefault("por_confirmar", [])
    for field in missing:
        if field in ("fecha_evento", "horario_evento"):
            session.data[field] = ans or "(por confirmar)"
        else:
            session.data[field] = "(por confirmar)"
        if field not in pendientes:
            pendientes.append(field)
    # Si pusimos marcadores, guardamos lo que dijo el cliente como pista.
    if ans and any(f in ("localidad", "tipo_evento") for f in missing):
        obs = str(session.data.get("observaciones", "") or "").strip()
        pista = f"Cliente dijo: \"{ans}\"."
        session.data["observaciones"] = (obs + " " + pista).strip() if obs else pista


def _ask_hire_step2(session: Session):
    frase = session.data.get("frase_contratacion") or locality_service.GENERIC_CONTRATACION
    _touch(session, STATE_HIRE_STEP2)
    return _resp(
        f"{frase}\n\n"
        "Ahora cuéntame:\n"
        "• Tipo de evento (cumpleaños, boda, aniversario…)\n"
        "• Hora aproximada"
    )


def _ask_hire_step3(session: Session):
    _touch(session, STATE_HIRE_STEP3)
    return _resp(
        "¿A nombre de quién dejamos la solicitud? Puedes pasarme tu nombre "
        "completo o tu DNI.\n\n"
        "Si por ahora solo quieres cotizar o prefieres no dejar nombre, dímelo y "
        "lo pasamos al manager con tu WhatsApp. Te van a responder por este "
        "mismo chat; si prefieres una llamada, indícanos a qué hora te acomoda."
    )


def start_hire(number: str):
    session = get_session(number)
    session.data = {"numero_cliente": number, "ultimo_mensaje_cliente": ""}
    _touch(session, STATE_HIRE_STEP1)
    return _resp(
        "Gracias por pensar en nosotros para tu evento 🎶\n\n"
        "Para empezar, indícame:\n"
        "• Fecha del evento\n"
        "• Ciudad o localidad"
    )


def _advance_hire(session: Session, answer: str):
    answer = (answer or "").strip()
    session.data["ultimo_mensaje_cliente"] = answer
    state = session.state

    if state == STATE_HIRE_STEP1:
        _store_hire_details(session, answer)
        missing = _missing_step1(session.data)
        if missing:
            _ai_fill_missing(session, answer)        # la IA intenta entender
            missing = _missing_step1(session.data)
        if missing:
            intentos = session.data.get("step1_intentos", 0) + 1
            session.data["step1_intentos"] = intentos
            if intentos >= 2:                        # anti-bucle: aceptar y seguir
                _accept_after_retries(session, answer, missing)
                missing = _missing_step1(session.data)
            else:
                response = _ask_missing_step1(missing)
                _persist(session)
                return response
        session.data.pop("step1_intentos", None)

        if _missing_step2(session.data):
            return _ask_hire_step2(session)
        return _ask_hire_step3(session)

    if state == STATE_HIRE_STEP2:
        _store_hire_details(session, answer, include_place_date=False)
        missing = _missing_step2(session.data)
        if missing:
            _ai_fill_missing(session, answer)
            missing = _missing_step2(session.data)
        if missing:
            intentos = session.data.get("step2_intentos", 0) + 1
            session.data["step2_intentos"] = intentos
            if intentos >= 2:
                _accept_after_retries(session, answer, missing)
                missing = _missing_step2(session.data)
            else:
                response = _ask_missing_step2(session, missing, answer)
                _persist(session)
                return response
        session.data.pop("step2_intentos", None)

        return _ask_hire_step3(session)

    if state == STATE_HIRE_STEP3:
        if _is_bare_ack(answer):
            _persist(session)
            return _resp(
                "Para no registrar un dato incorrecto, necesito el nombre completo "
                "o DNI. Si prefieres no dejarlo, escribe *sin nombre* y enviaremos "
                "la solicitud con tu WhatsApp."
            )
        nombre, contacto, observacion = _parse_name_contact(answer, session.whatsapp)
        session.data["nombre_o_dni"] = nombre
        session.data["numero_contacto"] = contacto
        if observacion:
            session.data["observaciones"] = observacion
        return _ask_hire_confirm(session)

    if state == STATE_HIRE_CONFIRM:
        norm = text_utils.normalize(answer)
        if _is_hire_confirmation(norm):
            _annotate_pending(session)
            data = dict(session.data)
            _touch(session, STATE_IDLE)
            return _resp("", completed=True, kind="hire", data=data)
        # El cliente corrige: actualizamos solo los campos que menciona.
        if not _apply_hire_correction(session, answer):
            _persist(session)
            return _resp(
                "No identifiqué qué dato deseas corregir. Puedes escribir, por "
                "ejemplo: *la fecha es 15/10*, *el lugar es Lima*, *la hora es "
                "8 pm* o *el nombre es Ivan Baltazar*."
            )
        return _ask_hire_confirm(session, corregido=True)

    clear_session(session.whatsapp)
    return _resp("Reinicié la conversación. Escribe “hola” cuando quieras.")


def _ask_hire_confirm(session: Session, corregido: bool = False):
    """Resumen final para que el cliente confirme antes de enviar la solicitud."""
    d = session.data
    _touch(session, STATE_HIRE_CONFIRM)
    cab = ("Actualizado. ¿Así está bien?" if corregido
           else "Antes de enviarla, revisa que esté todo bien:")
    lineas = [
        cab, "",
        f"📅 Fecha: {d.get('fecha_evento') or '—'}",
        f"📍 Lugar: {d.get('localidad') or '—'}",
        f"🎉 Evento: {d.get('tipo_evento') or '—'}",
        f"🕒 Hora: {d.get('horario_evento') or '—'}",
        f"👤 A nombre de: {d.get('nombre_o_dni') or '—'}",
        "",
        "Responde *sí* para enviarla, o dime qué corrijo (por ejemplo: \"la hora es 8 pm\").",
    ]
    return _resp("\n".join(lineas))


def _is_bare_ack(answer: str) -> bool:
    norm = text_utils.normalize(answer)
    return norm in _AFFIRMATIVE or norm in {"bueno", "perfecto", "listo", "vale"}


def _is_hire_confirmation(norm: str) -> bool:
    if norm in _AFFIRMATIVE:
        return True
    return bool(re.fullmatch(
        r"(?:si|claro|ok|okay|dale|confirmo|confirmar|ya)"
        r"(?:\s+(?:esta\s+bien|todo\s+bien|correcto|confirmado))?",
        norm,
    ))


def _set_corrected_field(session: Session, field: str, value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    session.data[field] = value
    pendientes = session.data.get("por_confirmar")
    if isinstance(pendientes, list) and field in pendientes:
        pendientes.remove(field)
    return True


def _apply_hire_correction(session: Session, answer: str) -> bool:
    """Aplica una rectificación sin tocar campos que el cliente no mencionó."""
    norm = text_utils.normalize(answer)
    parsed = _parse_hire_step1(answer)
    changed = False

    if re.search(r"\b(?:fecha|dia)\b", norm):
        changed |= _set_corrected_field(session, "fecha_evento", parsed["fecha"])
    if re.search(r"\b(?:lugar|ciudad|localidad|donde)\b", norm):
        changed |= _set_corrected_field(session, "localidad", parsed["localidad"])
        if changed and parsed["loc"] is not None:
            session.data["frase_contratacion"] = \
                locality_service.obtener_frase_contratacion(parsed["loc"])
    if re.search(r"\b(?:tipo\s+de\s+evento|evento|celebracion)\b", norm):
        changed |= _set_corrected_field(session, "tipo_evento", parsed["tipo"])
    if re.search(r"\b(?:hora|horario)\b", norm):
        changed |= _set_corrected_field(session, "horario_evento", parsed["hora"])
    if re.search(r"\b(?:nombre|dni|a\s+nombre\s+de)\b", norm):
        identity_answer = re.sub(
            r"(?i)^.*?\b(?:mi\s+nombre\s+es|el\s+nombre\s+es|nombre\s+es|"
            r"a\s+nombre\s+de|dni\s+es)\b\s*:?\s*",
            "",
            answer,
        ).strip() or answer
        nombre, contacto, observacion = _parse_name_contact(
            identity_answer, session.whatsapp
        )
        if nombre:
            session.data["nombre_o_dni"] = nombre
            session.data["numero_contacto"] = contacto
            session.data["observaciones"] = observacion
            changed = True

    return changed


def _annotate_pending(session: Session) -> None:
    """Agrega a observaciones una nota con los datos que quedaron por confirmar."""
    pendientes = session.data.get("por_confirmar") or []
    if not pendientes:
        return
    etiquetas = {"fecha_evento": "fecha", "horario_evento": "hora",
                 "localidad": "lugar", "tipo_evento": "tipo de evento"}
    nombres = ", ".join(etiquetas.get(f, f) for f in pendientes)
    nota = f"⚠️ Confirmar con el cliente: {nombres}."
    obs = str(session.data.get("observaciones", "") or "").strip()
    session.data["observaciones"] = (obs + " " + nota).strip() if obs else nota


_PREF_WORDS_RE = re.compile(
    r"(?i)\b(este|mismo|misma|whatsapp|wsp|otro|otra|numero|número|aqui|aquí|"
    r"aca|acá|prefiero|prefiere|dejar|dejo|contacten|contáctenme|contactenme|"
    r"llamada|llamar|llamen|llámen|llamenme|llámenme|llamame|llámame|"
    r"escriban|escríbanme|escribanme|responder|respuesta|que me|me|mi|es|"
    r"telefono|teléfono|celular|cel|contacto|hora|por favor)\b"
)
_CONNECTORS = {"a", "al", "y", "e", "o", "de", "del", "para", "con", "por",
               "el", "la", "lo", "los", "las", "un", "una", "en"}
_PRICE_WORDS = {
    "precio", "precios", "cotizacion", "cotizar", "costo", "costos",
    "tarifa", "tarifas", "presupuesto",
}
_IDENTITY_HINT_RE = re.compile(
    r"\b(?:soy|me\s+llamo|mi\s+nombre\s+es|nombre\s+es|a\s+nombre\s+de)\b",
    re.IGNORECASE,
)


def _has_identity_hint(answer: str, norm: str) -> bool:
    if _IDENTITY_HINT_RE.search(answer):
        return True
    return any(len(n) == 8 for n in re.findall(r"\d{7,}", norm))


def _is_non_name_answer(answer: str) -> bool:
    """Detecta respuestas que son intencion/objecion, no nombre ni DNI."""
    norm = text_utils.normalize(answer)
    if not norm or _has_identity_hint(answer, norm):
        return False

    has_price_word = any(word in norm.split() for word in _PRICE_WORDS)
    declines_name = bool(re.search(
        r"\b(?:no|prefiero\s+no)\s+(?:quiero|deseo|puedo|voy\s+a)?\s*"
        r"(?:dar|dejar|decir|brindar|pasar)\s+(?:mi\s+)?(?:nombre|dni|datos)\b",
        norm,
    )) or norm in {"sin nombre", "sin dni", "anonimo", "anonima"}
    no_reservation_yet = bool(re.search(
        r"\b(?:no\s+quiero|sin|todavia\s+no|aun\s+no|por\s+ahora\s+no)\s+"
        r"(?:reservar|reserva|contratar|cerrar)\b",
        norm,
    ))
    starts_as_price_request = bool(re.match(
        r"^(?:solo|solamente|primero|antes|quiero|quisiera|necesito|busco|deseo|"
        r"me\s+gustaria|quiero\s+saber|quisiera\s+saber)\b",
        norm,
    ))
    return declines_name or (has_price_word and (no_reservation_yet or starts_as_price_request))


def _non_name_observation(answer: str) -> str:
    norm = text_utils.normalize(answer)
    parts = ["No brindo nombre/DNI."]
    if any(word in norm.split() for word in _PRICE_WORDS):
        parts.append("Busca precios/cotizacion antes de reservar.")
    return " ".join(parts)


def _contact_observation(answer: str, contacto: str, own_whatsapp: str) -> str:
    norm = text_utils.normalize(answer)
    wants_call = any(w in norm for w in ("llamada", "llamar", "llamen", "llamame"))
    wants_write = any(w in norm for w in ("escribir", "escriban", "responder", "mensaje", "whatsapp", "wsp"))
    hora = _search_first(_TIME_PATTERNS, _replace_number_words(text_utils.deburr(answer)))

    parts = []
    if wants_call:
        parts.append(f"Prefiere llamada{f' {hora}' if hora else ''}.")
    elif wants_write:
        parts.append("Prefiere coordinación por WhatsApp.")

    if contacto != own_whatsapp:
        parts.append(f"Pidió usar otro número de contacto: {contacto}.")
    else:
        parts.append("Responder por este mismo chat.")

    return " ".join(parts)


def _parse_name_contact(answer: str, own_whatsapp: str) -> tuple[str, str, str]:
    """Devuelve (nombre_o_dni, numero_contacto, observaciones).

    Reglas: un número de 9 dígitos se trata como celular; uno de 8 como DNI
    (identidad, no contacto). Si el usuario pide 'otro número', se usa el último
    celular indicado; si dice 'este mismo', se usa su propio WhatsApp.
    """
    norm = text_utils.normalize(answer)
    numbers = re.findall(r"\d{7,}", answer)
    nine = [n for n in numbers if len(n) == 9]
    wants_same = any(w in norm for w in ("este", "mismo", "misma", "whatsapp", "wsp", "aqui", "aca"))
    wants_other = any(w in norm for w in ("otro", "otra"))

    if wants_same:
        contacto = own_whatsapp
    elif wants_other and (nine or numbers):
        contacto = nine[-1] if nine else numbers[-1]
    elif nine:
        contacto = nine[0]
    else:
        # Solo hay DNI (8 díg.) o ningún número claro: usar el WhatsApp propio.
        contacto = own_whatsapp

    observacion = _contact_observation(answer, contacto, own_whatsapp)
    if _is_non_name_answer(answer):
        observacion = f"{_non_name_observation(answer)} {observacion}".strip()
        return "", contacto, observacion

    # Nombre/DNI: quitar SOLO el número usado como contacto (preservando un DNI
    # distinto) y las frases de preferencia.
    nombre = answer
    if contacto and contacto != own_whatsapp:
        nombre = re.sub(re.escape(contacto), " ", nombre)
    for pattern in _TIME_PATTERNS:
        nombre = re.sub(pattern, " ", nombre, flags=re.IGNORECASE)
    nombre = _PREF_WORDS_RE.sub(" ", nombre)

    tokens = re.sub(r"\s+", " ", nombre).strip(" ,.-").split()
    while tokens and tokens[0].lower().strip(",.-") in _CONNECTORS:
        tokens.pop(0)
    while tokens and tokens[-1].lower().strip(",.-") in _CONNECTORS:
        tokens.pop()
    nombre = " ".join(tokens).strip(" ,.-")
    if not nombre:
        nombre = answer.strip()
    return nombre, contacto, observacion


# ---------------------------------------------------------------------------
# Flujo administrativo: registrar evento
# ---------------------------------------------------------------------------
# Solo campos que existen en el esquema actual de la hoja Eventos.
_ADMIN_FIELD_MAP = {
    "ciudad": "ciudad",
    "lugar": "lugar",
    "local": "lugar",
    "fecha": "fecha_evento",
    "hora": "hora_inicio",
    "horario": "hora_inicio",
    "hora inicio": "hora_inicio",
    "hora fin": "hora_fin",
    "mapa": "google_maps_url",
    "maps": "google_maps_url",
    "ubicacion": "google_maps_url",
    "ubicación": "google_maps_url",
}


_DATE_RE = re.compile(r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b")
_URL_RE = re.compile(r"https?://\S+")
_TIME_RE = re.compile(r"\b(\d{1,2}([:.]\d{2})?\s*(am|pm|a\.m\.|p\.m\.|hrs|h)?)\b", re.IGNORECASE)


def parse_admin_event(text: str) -> dict:
    """Extrae los campos del evento. Tolerante: primero busca líneas
    'Campo: valor' y luego intenta deducir fecha y enlace del texto libre."""
    data: dict = {}
    raw = text or ""

    for line in raw.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        key = text_utils.normalize(label).strip()
        value = value.strip()
        if not value:
            continue
        field = _ADMIN_FIELD_MAP.get(key)
        if field:
            data[field] = value

    # Deducciones del texto libre (solo si faltan).
    if not data.get("google_maps_url"):
        m = _URL_RE.search(raw)
        if m:
            data["google_maps_url"] = m.group(0).strip().rstrip(".,)")
    if not data.get("fecha_evento"):
        m = _DATE_RE.search(raw)
        if m:
            data["fecha_evento"] = m.group(1)

    return data


def missing_event_fields(d: dict) -> list[str]:
    """Campos mínimos que faltan para poder guardar (ciudad y fecha)."""
    faltan = []
    if not d.get("ciudad"):
        faltan.append("ciudad")
    if not d.get("fecha_evento"):
        faltan.append("fecha")
    return faltan


def admin_event_template() -> str:
    return (
        "📝 Registrar evento\n\n"
        "Completa esta plantilla (lo que no tengas, déjalo en blanco):\n\n"
        "Ciudad: \n"
        "Lugar: \n"
        "Fecha: 15/06/2026\n"
        "Hora: 9 pm\n"
        "Mapa: https://maps.google.com/...\n\n"
        "Mínimo se requiere *ciudad* y *fecha*. Escribe *#salir* para cancelar."
    )


def begin_admin_event(number: str):
    """Inicia el flujo de registro de evento mostrando la plantilla."""
    session = get_session(number)
    session.data = {"creado_por": number}
    _touch(session, STATE_ADMIN_EVENT_COLLECT)
    return _resp(admin_event_template())


def collect_admin_event(number: str, text: str):
    """Recibe los datos del evento, los acumula y pide confirmación o lo
    que falte. Nunca falla por formato libre."""
    session = get_session(number)
    parsed = parse_admin_event(text)
    # Acumula sobre lo ya recogido (permite completarlo en varios mensajes).
    for k, v in parsed.items():
        if v:
            session.data[k] = v

    faltan = missing_event_fields(session.data)
    if faltan:
        _touch(session, STATE_ADMIN_EVENT_COLLECT)
        falta_txt = " y ".join(faltan)
        return _resp(
            f"Me falta {falta_txt} para agendar el evento.\n\n"
            "Mándamelo así, por ejemplo:\n"
            f"{'Ciudad: Huancayo' if 'ciudad' in faltan else 'Fecha: 15/06/2026'}\n\n"
            "O escribe *#salir* para cancelar."
        )

    _touch(session, STATE_ADMIN_EVENT_CONFIRM)
    return _resp(admin_event_summary(session.data))


def start_admin_event(number: str, parsed: dict):
    """Compatibilidad: prepara la confirmación con datos ya parseados."""
    session = get_session(number)
    session.data = dict(parsed)
    session.data["creado_por"] = number
    _touch(session, STATE_ADMIN_EVENT_CONFIRM)
    return _resp(admin_event_summary(session.data))


def admin_event_summary(d: dict) -> str:
    return (
        "Revisa el evento antes de guardar:\n\n"
        f"📅 Fecha: {d.get('fecha_evento', '-')}\n"
        f"🕒 Hora: {d.get('hora_inicio', '-')}\n"
        f"📍 Lugar: {d.get('lugar', '-')} — {d.get('ciudad', '-')}\n"
        f"🗺️ Mapa: {d.get('google_maps_url', '-')}\n\n"
        "¿Confirmas? Responde *sí* para guardar o *no* para cancelar."
    )


_NEGATIVE = {"no", "cancelar", "cancela", "descartar", "nel", "negativo"}


def _advance_admin_event(session: Session, answer: str):
    norm = text_utils.normalize(answer)

    # En la fase de recolección, todo texto se interpreta como datos.
    if session.state == STATE_ADMIN_EVENT_COLLECT:
        return collect_admin_event(session.whatsapp, answer)

    # Fase de confirmación.
    if norm in _AFFIRMATIVE:
        data = dict(session.data)
        data.setdefault("estado", "CONFIRMADO")
        _touch(session, STATE_IDLE)
        return _resp("", completed=True, kind="admin_event", data=data)
    if norm in _NEGATIVE:
        clear_session(session.whatsapp)
        return _resp(
            "Registro de evento cancelado.\n"
            "Escribe *registrar evento* cuando quieras intentarlo de nuevo.",
            cancelled=True,
        )
    # Respuesta ambigua: vuelve a pedir confirmación clara.
    return _resp(
        "No entendí la respuesta. Responde *sí* para guardar el evento o *no* "
        "para cancelar."
    )


# ---------------------------------------------------------------------------
# Despachador de flujos guiados (hire + admin event)
# ---------------------------------------------------------------------------
def handle_flow(session: Session, answer: str):
    if session.state in HIRE_STATES:
        return _advance_hire(session, answer)
    if session.state in ADMIN_EVENT_STATES:
        return _advance_admin_event(session, answer)
    return _resp("")
