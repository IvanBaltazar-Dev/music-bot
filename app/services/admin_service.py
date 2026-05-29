"""Servicio de administración.

Identifica administradores autorizados (por .env y, opcionalmente, por Google
Sheets), notifica leads completos y arma las respuestas de los comandos admin.
"""

from app.config import settings
from app.repositories import google_sheets_repository as repo
from app.services import intent_service
from app.services.whatsapp_service import send_text_message


def _only_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _same_number(a: str, b: str) -> bool:
    a, b = _only_digits(a), _only_digits(b)
    if not a or not b:
        return False
    if a == b:
        return True
    # Tolerante a prefijos de país: comparar últimos 9 dígitos
    return a[-9:] == b[-9:]


def is_admin(whatsapp_number: str) -> bool:
    """True si el número está autorizado (en .env o en la hoja Admins)."""
    candidates = list(settings.admin_numbers)
    try:
        candidates += repo.get_active_admins()
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] no se pudieron leer admins de Sheets: {exc.__class__.__name__}")
    return any(_same_number(whatsapp_number, c) for c in candidates)


async def notify_lead(lead_data: dict) -> None:
    """Notifica a todos los administradores que llegó un lead completo."""
    admins = list(settings.admin_numbers)
    try:
        admins += repo.get_active_admins()
    except Exception:  # noqa: BLE001
        pass
    # Quitar duplicados conservando orden
    seen, unique = set(), []
    for a in admins:
        d = _only_digits(a)
        if d and d not in seen:
            seen.add(d)
            unique.append(d)

    if not unique:
        print("[admin] no hay administradores configurados para notificar el lead.")
        return

    mensaje = (
        "📩 ¡Nuevo lead completo! 🎵\n\n"
        f"👤 Nombre: {lead_data.get('nombre', '-')}\n"
        f"📍 Lugar: {lead_data.get('lugar', '-')}\n"
        f"📅 Fecha: {lead_data.get('fecha_evento', '-')}\n"
        f"🎉 Tipo: {lead_data.get('tipo_evento', '-')}\n"
        f"⏱ Duración: {lead_data.get('duracion', '-')}\n"
        f"📞 Contacto: {lead_data.get('contacto', '-')}\n"
        f"💬 WhatsApp: {lead_data.get('whatsapp', '-')}"
    )

    for number in unique:
        await send_text_message(number, mensaje)


def help_text() -> str:
    return (
        "Comandos de administrador 🎛️\n\n"
        "- registrar evento\n"
        "- solicitudes\n"
        "- métricas\n"
        "- ayuda admin"
    )


def not_authorized_text() -> str:
    return "Este comando está disponible solo para administradores autorizados."


def format_recent_requests() -> str:
    """Texto con las últimas solicitudes de cotización."""
    try:
        requests = repo.get_recent_quotation_requests(limit=5)
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error leyendo solicitudes: {exc.__class__.__name__}")
        requests = []

    if not requests:
        return (
            "📭 Por ahora no hay solicitudes registradas.\n\n"
            "Cuando un cliente complete una cotización aparecerá aquí."
        )

    bloques = []
    for r in requests:
        bloque = (
            f"👤 {r.get('nombre', '-')} ({r.get('estado', 'NUEVA')})\n"
            f"📍 {r.get('lugar', '-')} · 📅 {r.get('fecha_evento', '-')}\n"
            f"🎉 {r.get('tipo_evento', '-')} · ⏱ {r.get('duracion', '-')}\n"
            f"📞 {r.get('contacto', '-')}"
        )
        bloques.append(bloque)

    return "📋 Últimas solicitudes:\n\n" + "\n\n".join(bloques)
