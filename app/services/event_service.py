"""Servicio de Eventos.

Consulta eventos activos desde `google_sheets_repository` (hoja `Eventos`) y arma
las respuestas públicas del flujo "Quiero ir a verlos". No inventa precios ni
ubicaciones: si un dato no existe, simplemente no se muestra.
"""

from __future__ import annotations

from datetime import date, datetime
from datetime import timedelta

from app.repositories import event_repository
from app.repositories.google_sheets_repository import get_active_events, is_enabled
from app.services import text_utils


def _parse_date(value: str):
    """Intenta interpretar la fecha del evento en varios formatos comunes."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        serial = float(s)
        if serial > 0:
            return (datetime(1899, 12, 30) + timedelta(days=serial)).date()
    except ValueError:
        pass
    # Tomar solo la parte de fecha si viene con hora
    s_date = s.split("T")[0].split(" ")[0]
    formats = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d")
    for fmt in formats:
        try:
            return datetime.strptime(s_date, fmt).date()
        except ValueError:
            continue
    return None


def _event_date(e: dict) -> str:
    value = str(e.get("fecha") or e.get("fecha_evento") or "").strip()
    parsed = _parse_date(value)
    if parsed is not None:
        return parsed.isoformat()
    return value


def _event_time(e: dict) -> str:
    return str(e.get("hora") or e.get("hora_inicio") or "").strip()


def _event_description(e: dict) -> str:
    return str(e.get("descripcion") or e.get("descripcion_publica") or "").strip()


def get_upcoming_confirmed(ciudad: str | None = None) -> list[dict]:
    """Eventos ACTIVO desde Google Sheets, opcionalmente filtrados por ciudad."""
    print(f"[events] google_sheets_enabled={is_enabled()}")
    events = get_active_events()
    print(f"[events] active_events_found={len(events)}")

    today = date.today()
    ciudad_norm = text_utils.normalize(ciudad) if ciudad else ""

    result = []
    for e in events:
        d = _parse_date(_event_date(e))
        if d is not None and d < today:
            continue
        if ciudad_norm:
            ev_city = text_utils.normalize(e.get("ciudad", ""))
            if ciudad_norm not in ev_city and ev_city not in ciudad_norm:
                continue
        result.append(e)

    result.sort(key=lambda e: (_parse_date(_event_date(e)) or date.max))
    if ciudad_norm:
        print(f"[events] active_events_found_for_city={len(result)} city={ciudad}")
    return result


def build_events_response() -> str:
    events = get_upcoming_confirmed()

    if not events:
        return (
            "Por ahora no tengo eventos activos registrados, "
            "pero apenas tengamos una fecha confirmada la compartiremos por aquí 🎶"
        )

    lines = [
        "Estos son los próximos eventos confirmados de Carlos Fer y Agrup. Cariño Lindo 🎶🙌"
    ]

    for event in events[:5]:
        fecha = _event_date(event)
        hora = _event_time(event)
        ciudad = str(event.get("ciudad", "")).strip()
        lugar = str(event.get("lugar", "")).strip()
        descripcion = _event_description(event)

        encabezado = " - ".join(p for p in (fecha, hora) if p) or "Fecha por confirmar"
        ubicacion = ", ".join(p for p in (ciudad, lugar) if p)
        bloque = [f"• {encabezado}"]
        if ubicacion:
            bloque.append(f"  📍 {ubicacion}")
        if descripcion:
            bloque.append(f"  {descripcion}")
        lines.append("\n".join(bloque))

    return "\n\n".join(lines)


def format_event_block(e: dict) -> str:
    """Bloque de texto del evento, solo con datos realmente disponibles."""
    fecha = _event_date(e)
    hora = _event_time(e)
    lugar = str(e.get("lugar", "")).strip()
    ciudad = str(e.get("ciudad", "")).strip()

    lineas = ["¡Sí tenemos fecha! 🎶🙌", ""]
    if fecha:
        lineas.append(f"📅 {fecha}")
    lugar_ciudad = " — ".join([p for p in [lugar, ciudad] if p])
    if lugar_ciudad:
        lineas.append(f"📍 {lugar_ciudad}")
    if hora:
        lineas.append(f"🕘 Desde las {hora}")
    desc = _event_description(e)
    if desc:
        lineas.append(f"\n{desc}")
    lineas.append("\nVa a estar bonito para cantar, bailar y disfrutar juntos. 😄")
    lineas.append("\n¿Qué te gustaría hacer?")
    return "\n".join(lineas)


def precio_entrada(e: dict) -> str:
    """Precio de la entrada si se maneja (texto libre, ej 'S/20')."""
    return str(e.get("precio_entrada", "")).strip()


def link_evento(e: dict) -> str:
    """Link público del evento para compartir / pasar la voz."""
    return str(e.get("link_evento", "")).strip()


def has_price(e: dict) -> bool:
    return bool(precio_entrada(e))


def has_tickets(e: dict) -> bool:
    # Se mantiene por compatibilidad: hay info de entradas si hay precio.
    return has_price(e)


def has_maps(e: dict) -> bool:
    return bool(str(e.get("google_maps_url", "")).strip())


def validate_event(event_data: dict) -> tuple[bool, str]:
    """Valida evento antes de guardar. Devuelve (ok, error_msg)."""
    if not event_data.get("fecha_evento"):
        return False, "Falta fecha del evento. Usa DD/MM/YYYY"

    parsed = _parse_date(event_data["fecha_evento"])
    if parsed is None:
        return False, f"Fecha '{event_data['fecha_evento']}' inválida. Usa DD/MM/YYYY (ej: 15/06/2026)"

    if not event_data.get("ciudad"):
        return False, "Falta ciudad del evento"

    maps_url = str(event_data.get("google_maps_url", "")).strip()
    if maps_url and not (maps_url.startswith("http://") or maps_url.startswith("https://")):
        return False, "Link de mapa debe empezar con http:// o https://"

    return True, ""


def validate_field(field: str, value: str) -> tuple[bool, str, str]:
    """Valida el nuevo valor de un campo al editar un evento.

    Devuelve (ok, error_msg, valor_normalizado).
    """
    v = str(value or "").strip()
    if not v:
        return False, "El valor no puede estar vacío.", v
    if field == "fecha_evento" and _parse_date(v) is None:
        return False, f"Fecha '{v}' inválida. Usa DD/MM/YYYY (ej: 15/06/2026).", v
    if field in ("google_maps_url", "link_evento"):
        if not (v.startswith("http://") or v.startswith("https://")):
            return False, "El link debe empezar con http:// o https://.", v
    return True, "", v


def create_event(event_data: dict) -> str:
    """Guarda un evento nuevo (flujo administrativo). Devuelve id_evento."""
    return event_repository.save(event_data)
