"""Orquestador de la conversación.

Es el "controlador" que mantiene el webhook delgado: recibe el número y el texto
(o botón) ya extraídos, decide qué hacer apoyándose en los demás servicios y
envía la respuesta por WhatsApp. Aplica los efectos secundarios (guardar en
Sheets, notificar admins, registrar métricas) cuando un flujo se completa.
"""

from app.repositories import google_sheets_repository as repo
from app.services import (
    admin_service,
    event_service,
    intent_service,
    metrics_service,
    session_service,
)
from app.services.whatsapp_service import send_text_message, send_button_message

# Botones del menú inicial
MENU_BUTTONS = [
    {"id": intent_service.BTN_MENU_EVENTS, "title": "Ver eventos"},
    {"id": intent_service.BTN_MENU_PRICE, "title": "Consultar precio"},
    {"id": intent_service.BTN_MENU_CONTACT, "title": "Contactar equipo"},
]

GREETING_TEXT = (
    "¡Hola! Qué alegría saludarte 🎵✨\n\n"
    "Soy Music Bot, el asistente de la agrupación.\n"
    "Puedo ayudarte con próximos eventos, contrataciones o contacto con el equipo.\n\n"
    "¿Qué te gustaría consultar?"
)

CONTACT_TEXT = (
    "📞 ¡Con gusto te conectamos con el equipo!\n\n"
    "Puedes dejarnos tus datos por aquí y un encargado se comunicará contigo muy pronto.\n"
    "Gracias por tu interés en acompañarnos 🎶"
)

CANCEL_TEXT = (
    "Listo, reinicié la conversación 😊\n"
    "Cuando quieras puedes escribir “hola” o “precio” para empezar otra vez."
)

UNKNOWN_TEXT = (
    "Gracias por tu mensaje 🙌 Para ayudarte mejor, cuéntame qué necesitas.\n\n"
    "Puedes escribir:\n"
    "- hola\n"
    "- eventos\n"
    "- precio\n"
    "- contacto"
)


async def _send(to: str, resp: dict):
    """Envía la respuesta de un flujo (texto o botones)."""
    text = resp.get("text") or ""
    buttons = resp.get("buttons")
    if not text:
        return
    if buttons:
        await send_button_message(to, text, buttons)
    else:
        await send_text_message(to, text)


def _admin_event_confirmation(d: dict) -> str:
    return (
        "✅ Evento registrado correctamente 🎵\n\n"
        f"📅 Fecha: {d.get('fecha', '-')}\n"
        f"🕒 Hora: {d.get('hora', '-')}\n"
        f"📍 Lugar: {d.get('lugar', '-')}\n"
        f"🏙 Ciudad: {d.get('ciudad', '-')}\n"
        f"🎶 Descripción: {d.get('descripcion', '-')}\n\n"
        "Ya podrá aparecer cuando los clientes consulten la agenda."
    )


async def _finalize_flow(to: str, resp: dict):
    """Aplica efectos secundarios cuando un flujo se completa."""
    kind = resp.get("kind")
    data = resp.get("data", {})

    if kind == "quotation":
        repo.save_quotation_request(data)
        metrics_service.record(metrics_service.QUOTATION_COMPLETED, whatsapp=to)
        await _send(to, resp)  # resumen para el cliente
        try:
            await admin_service.notify_lead(data)
        except Exception as exc:  # noqa: BLE001
            print(f"[conversation] no se pudo notificar el lead: {exc.__class__.__name__}")

    elif kind == "admin_event":
        event_service.create_event(data)
        metrics_service.record(metrics_service.EVENT_CREATED, whatsapp=to)
        await send_text_message(to, _admin_event_confirmation(data))

    session_service.clear_session(to)


async def _handle_admin_command(to: str, command: str):
    if command == intent_service.ADMIN_REGISTER_EVENT:
        resp = session_service.start_admin_event(to)
        await _send(to, resp)
    elif command == intent_service.ADMIN_VIEW_REQUESTS:
        await send_text_message(to, admin_service.format_recent_requests())
    elif command == intent_service.ADMIN_VIEW_METRICS:
        metrics_service.record(metrics_service.ADMIN_METRIC_REQUESTED, whatsapp=to)
        await send_text_message(to, metrics_service.format_summary())
    elif command == intent_service.ADMIN_HELP:
        await send_text_message(to, admin_service.help_text())


async def _dispatch_intent(to: str, intent: str):
    if intent == intent_service.INTENT_GREETING:
        metrics_service.record(metrics_service.INTENT_GREETING, whatsapp=to)
        await send_button_message(to, GREETING_TEXT, MENU_BUTTONS)

    elif intent == intent_service.INTENT_EVENTS:
        metrics_service.record(metrics_service.INTENT_EVENTS, whatsapp=to)
        await send_text_message(to, event_service.format_events_response())

    elif intent == intent_service.INTENT_PRICE:
        metrics_service.record(metrics_service.INTENT_PRICE, whatsapp=to)
        metrics_service.record(metrics_service.QUOTATION_STARTED, whatsapp=to)
        resp = session_service.start_quotation(to)
        await _send(to, resp)

    elif intent == intent_service.INTENT_CONTACT:
        metrics_service.record(metrics_service.INTENT_CONTACT, whatsapp=to)
        await send_text_message(to, CONTACT_TEXT)

    else:  # INTENT_UNKNOWN
        metrics_service.record(metrics_service.UNKNOWN_MESSAGE, whatsapp=to)
        await send_text_message(to, UNKNOWN_TEXT)


async def handle_incoming_message(from_number: str, text: str = "", button_id: str = ""):
    """Punto de entrada único del bot."""
    metrics_service.record(metrics_service.MESSAGE_RECEIVED, whatsapp=from_number)

    session = session_service.get_session(from_number)

    # 1) Cancelar / reiniciar funciona en cualquier momento
    if not button_id and intent_service.detect_intent(text) == intent_service.INTENT_CANCEL:
        session_service.clear_session(from_number)
        await send_text_message(from_number, CANCEL_TEXT)
        return

    # 2) Si hay un flujo guiado activo, el mensaje es la respuesta del paso actual
    if session.in_flow():
        resp = session_service.handle_flow(session, text)
        if resp.get("completed"):
            await _finalize_flow(from_number, resp)
        else:
            await _send(from_number, resp)
        return

    # 3) Botón de menú fuera de flujo -> intención directa
    if button_id:
        mapped = intent_service.button_to_intent(button_id)
        if mapped:
            await _dispatch_intent(from_number, mapped)
            return

    # 4) Comando de administrador
    command = intent_service.detect_admin_command(text)
    if command:
        if admin_service.is_admin(from_number):
            await _handle_admin_command(from_number, command)
        else:
            # Seguridad: no revelar nada interno a usuarios no autorizados
            await send_text_message(from_number, admin_service.not_authorized_text())
        return

    # 5) Intención pública
    await _dispatch_intent(from_number, intent_service.detect_intent(text))
