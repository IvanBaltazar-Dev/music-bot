"""Servicio de eventos de la agrupación.

Consulta los eventos activos, formatea la respuesta para el cliente y crea
eventos nuevos a partir del flujo administrativo. Se apoya en el repositorio,
que ya maneja el fallback en memoria cuando Google Sheets no está disponible.
"""

from app.repositories import google_sheets_repository as repo


def get_active_events() -> list[dict]:
    return repo.get_active_events()


def format_events_response() -> str:
    """Devuelve el mensaje de eventos: lista confirmada o fallback elegante."""
    events = get_active_events()

    if not events:
        return (
            "🎤 Estamos actualizando nuestra agenda de presentaciones.\n\n"
            "Muy pronto podrás ver aquí las próximas fechas confirmadas.\n"
            "Gracias por tu interés en acompañarnos 🎶"
        )

    bloques = []
    for e in events:
        fecha = e.get("fecha", "Por confirmar")
        hora = e.get("hora", "")
        lugar = e.get("lugar", "")
        ciudad = e.get("ciudad", "")
        desc = e.get("descripcion", "")

        lugar_linea = ", ".join([p for p in [lugar, ciudad] if p])
        bloque = f"📅 {fecha}" + (f" - {hora}" if hora else "")
        if lugar_linea:
            bloque += f"\n📍 {lugar_linea}"
        if desc:
            bloque += f"\n🎶 {desc}"
        bloques.append(bloque)

    return (
        "🎤 Próximos eventos confirmados:\n\n"
        + "\n\n".join(bloques)
        + "\n\nGracias por querer acompañarnos 🙌"
    )


def create_event(event_data: dict) -> bool:
    """Guarda un evento nuevo (usado por el flujo administrativo)."""
    return repo.save_event(event_data)
