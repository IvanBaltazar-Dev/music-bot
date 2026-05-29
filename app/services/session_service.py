"""Servicio de sesiones y flujos guiados.

Mantiene una sesión simple en memoria por número de WhatsApp y opera las
máquinas de estado del flujo de cotización (cliente) y de registro de evento
(administrador). No realiza efectos secundarios (guardar/notificar): solo avanza
el estado y devuelve el siguiente mensaje. La orquestación los aplica al
completarse el flujo.
"""

import re

from app.services import ai_service
from app.models.session import (
    Session,
    STATE_IDLE,
    STATE_Q_LOCATION,
    STATE_Q_DATE,
    STATE_Q_EVENT_TYPE,
    STATE_Q_DURATION,
    STATE_Q_NAME,
    STATE_Q_CONTACT,
    STATE_ADMIN_EVENT_DATE,
    STATE_ADMIN_EVENT_TIME,
    STATE_ADMIN_EVENT_CITY,
    STATE_ADMIN_EVENT_PLACE,
    STATE_ADMIN_EVENT_DESCRIPTION,
    STATE_ADMIN_EVENT_CONFIRM,
    QUOTATION_STATES,
    ADMIN_EVENT_STATES,
)
from app.services.intent_service import (
    normalize,
    BTN_EVT_BIRTHDAY,
    BTN_EVT_WEDDING,
    BTN_EVT_CORPORATE,
)

# --- Almacén de sesiones en memoria ---
_sessions: dict[str, Session] = {}

_AFFIRMATIVE = {"si", "sí", "claro", "ok", "okay", "dale", "confirmar", "confirmo"}

# Botones para el paso "tipo de evento"
EVENT_TYPE_BUTTONS = [
    {"id": BTN_EVT_BIRTHDAY, "title": "Cumpleaños"},
    {"id": BTN_EVT_WEDDING, "title": "Boda"},
    {"id": BTN_EVT_CORPORATE, "title": "Corporativo"},
]


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
        session = Session(whatsapp=number)
        _sessions[number] = session
    return session


def clear_session(number: str) -> None:
    _sessions.pop(number, None)


def _touch(session: Session, state: str) -> None:
    from datetime import datetime
    session.state = state
    session.updated_at = datetime.utcnow()


# ---------------------------------------------------------------------------
# Flujo de cotización (cliente)
# ---------------------------------------------------------------------------
def start_quotation(number: str):
    session = get_session(number)
    session.data = {"whatsapp": number}
    _touch(session, STATE_Q_LOCATION)
    return _resp(
        "🎵 ¡Genial! Con gusto preparamos tu cotización.\n\n"
        "Cuéntame, ¿para qué ciudad o distrito sería el evento?"
    )


def _finish_quotation(session: Session):
    d = session.data
    resumen = (
        "¡Gracias! Ya tengo los datos principales de tu solicitud 🎵✨\n\n"
        "Nuestro equipo revisará la disponibilidad y te contactará para darte "
        "una cotización más precisa.\n\n"
        "Resumen:\n"
        f"📍 Lugar: {d.get('lugar', '-')}\n"
        f"📅 Fecha: {d.get('fecha_evento', '-')}\n"
        f"🎉 Tipo de evento: {d.get('tipo_evento', '-')}\n"
        f"⏱ Duración: {d.get('duracion', '-')}\n"
        f"👤 Nombre: {d.get('nombre', '-')}\n"
        f"📞 Contacto: {d.get('contacto', '-')}\n\n"
        "Gracias por pensar en nosotros para un momento tan especial 🙌"
    )
    data = dict(d)
    _touch(session, STATE_IDLE)
    return _resp(resumen, completed=True, kind="quotation", data=data)


def _advance_quotation(session: Session, answer: str):
    answer = (answer or "").strip()
    state = session.state

    # Opcionalmente, IA puede ayudar a interpretar respuestas cortas/ambiguas
    ai_enhanced = None
    if ai_service.is_enabled() and len(answer) < 50:
        ai_enhanced = ai_service.validate_and_enhance_quotation(state, session.data, answer)
        if ai_enhanced:
            answer = ai_enhanced.get(state, answer)

    if state == STATE_Q_LOCATION:
        session.data["lugar"] = answer
        _touch(session, STATE_Q_DATE)
        return _resp("Perfecto 🙌 ¿Qué fecha tienes en mente? 📅")

    if state == STATE_Q_DATE:
        session.data["fecha_evento"] = answer
        _touch(session, STATE_Q_EVENT_TYPE)
        return _resp(
            "¿Qué tipo de evento será? 🎉\n\n"
            "También puedes escribir:\n"
            "4. Fiesta patronal\n"
            "5. Discoteca / local\n"
            "6. Otro",
            buttons=EVENT_TYPE_BUTTONS,
        )

    if state == STATE_Q_EVENT_TYPE:
        session.data["tipo_evento"] = answer
        _touch(session, STATE_Q_DURATION)
        return _resp("¿Cuántas horas aproximadamente deseas la presentación? ⏱")

    if state == STATE_Q_DURATION:
        session.data["duracion"] = answer
        _touch(session, STATE_Q_NAME)
        return _resp("¿Cuál es tu nombre? 😊")

    if state == STATE_Q_NAME:
        session.data["nombre"] = answer
        _touch(session, STATE_Q_CONTACT)
        return _resp(
            "¿Deseas dejar un número de contacto o usamos este mismo WhatsApp? 📞"
        )

    if state == STATE_Q_CONTACT:
        norm = normalize(answer)
        if re.search(r"\d{6,}", answer):
            session.data["contacto"] = answer
        elif (not norm) or (norm in _AFFIRMATIVE) or any(
            w in norm for w in ("este", "mismo", "whatsapp", "wsp")
        ):
            session.data["contacto"] = session.whatsapp
        else:
            session.data["contacto"] = answer
        return _finish_quotation(session)

    # Estado inesperado: reiniciar de forma segura
    clear_session(session.whatsapp)
    return _resp(
        "Reinicié la conversación 😊 Escribe “hola” o “precio” cuando quieras."
    )


# ---------------------------------------------------------------------------
# Flujo administrativo: registrar evento
# ---------------------------------------------------------------------------
def start_admin_event(number: str):
    session = get_session(number)
    session.data = {"creado_por": number}
    _touch(session, STATE_ADMIN_EVENT_DATE)
    return _resp("🎫 Registremos un nuevo evento.\n\n¿Cuál es la *fecha* del evento?")


def _admin_confirm_summary(d: dict) -> str:
    return (
        "Revisa el evento antes de guardar 👇\n\n"
        f"📅 Fecha: {d.get('fecha', '-')}\n"
        f"🕒 Hora: {d.get('hora', '-')}\n"
        f"📍 Lugar: {d.get('lugar', '-')}\n"
        f"🏙 Ciudad: {d.get('ciudad', '-')}\n"
        f"🎶 Descripción: {d.get('descripcion', '-')}\n\n"
        "Escribe *confirmar* para guardar o *cancelar* para descartar."
    )


def _advance_admin_event(session: Session, answer: str):
    answer = (answer or "").strip()
    state = session.state

    if state == STATE_ADMIN_EVENT_DATE:
        session.data["fecha"] = answer
        _touch(session, STATE_ADMIN_EVENT_TIME)
        return _resp("¿A qué *hora*? 🕒")

    if state == STATE_ADMIN_EVENT_TIME:
        session.data["hora"] = answer
        _touch(session, STATE_ADMIN_EVENT_CITY)
        return _resp("¿En qué *ciudad*? 🏙")

    if state == STATE_ADMIN_EVENT_CITY:
        session.data["ciudad"] = answer
        _touch(session, STATE_ADMIN_EVENT_PLACE)
        return _resp("¿En qué *lugar* o local se realizará? 📍")

    if state == STATE_ADMIN_EVENT_PLACE:
        session.data["lugar"] = answer
        _touch(session, STATE_ADMIN_EVENT_DESCRIPTION)
        return _resp("Cuéntame una *descripción breve* del evento 🎶")

    if state == STATE_ADMIN_EVENT_DESCRIPTION:
        session.data["descripcion"] = answer
        _touch(session, STATE_ADMIN_EVENT_CONFIRM)
        return _resp(_admin_confirm_summary(session.data))

    if state == STATE_ADMIN_EVENT_CONFIRM:
        norm = normalize(answer)
        if norm in _AFFIRMATIVE:
            data = dict(session.data)
            _touch(session, STATE_IDLE)
            return _resp("", completed=True, kind="admin_event", data=data)
        # Cualquier otra cosa que no sea confirmar la tratamos como descarte
        clear_session(session.whatsapp)
        return _resp(
            "Listo, descarté el registro del evento 😊\n"
            "Escribe “registrar evento” cuando quieras intentarlo de nuevo.",
            cancelled=True,
        )

    clear_session(session.whatsapp)
    return _resp("Reinicié el flujo administrativo 😊")


# ---------------------------------------------------------------------------
# Despachador de flujos
# ---------------------------------------------------------------------------
def handle_flow(session: Session, answer: str):
    """Avanza el flujo activo de la sesión y devuelve la respuesta."""
    if session.state in QUOTATION_STATES:
        return _advance_quotation(session, answer)
    if session.state in ADMIN_EVENT_STATES:
        return _advance_admin_event(session, answer)
    # No debería ocurrir, pero por seguridad:
    return _resp("")
