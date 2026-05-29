"""Servicio de métricas operativas.

Registra eventos relevantes del bot y calcula un resumen. Usa Google Sheets si
está habilitado; de lo contrario usa el fallback en memoria del repositorio.
Nunca debe romper el flujo del webhook: cualquier fallo se ignora de forma segura.
"""

from app.repositories import google_sheets_repository as repo

# Tipos de métrica conocidos (documentación / referencia)
MESSAGE_RECEIVED = "message_received"
INTENT_GREETING = "intent_greeting"
INTENT_EVENTS = "intent_events"
INTENT_PRICE = "intent_price"
INTENT_CONTACT = "intent_contact"
QUOTATION_STARTED = "quotation_started"
QUOTATION_COMPLETED = "quotation_completed"
EVENT_CREATED = "event_created"
ADMIN_METRIC_REQUESTED = "admin_metric_requested"
UNKNOWN_MESSAGE = "unknown_message"


def record(metric_type: str, whatsapp: str = "", detalle: str = "", origen: str = "bot") -> None:
    """Registra una métrica de forma segura (no propaga errores)."""
    try:
        repo.save_metric_event({
            "tipo": metric_type,
            "whatsapp": whatsapp or "",
            "detalle": detalle or "",
            "origen": origen or "bot",
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] no se pudo registrar '{metric_type}': {exc.__class__.__name__}")


def get_metrics_summary() -> dict:
    try:
        return repo.get_metrics_summary()
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] no se pudo calcular el resumen: {exc.__class__.__name__}")
        return {}


def format_summary() -> str:
    """Texto cálido y claro con el resumen operativo para administradores."""
    s = get_metrics_summary()
    return (
        "📊 Resumen de Music Bot\n\n"
        "Hoy:\n"
        f"👋 Conversaciones iniciadas: {s.get('conversaciones_hoy', 0)}\n"
        f"🎤 Consultas de eventos: {s.get('consultas_eventos_hoy', 0)}\n"
        f"💰 Consultas de precio: {s.get('consultas_precio_hoy', 0)}\n"
        f"📩 Solicitudes completas: {s.get('leads_completos_hoy', 0)}\n\n"
        "Últimos 7 días:\n"
        f"👥 Usuarios únicos: {s.get('usuarios_unicos_semana', 0)}\n"
        f"📈 Leads generados: {s.get('leads_semana', 0)}\n"
        f"🎵 Eventos consultados: {s.get('eventos_consultados_semana', 0)}\n\n"
        f"🎶 Eventos registrados (total): {s.get('eventos_registrados', 0)}"
    )
