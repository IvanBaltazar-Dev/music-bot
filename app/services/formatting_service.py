"""Servicio de formateo para mensajes y datos."""

from datetime import datetime
from app.repositories import locality_repository

def format_timestamp_readable(iso_timestamp: str) -> str:
    """Convierte ISO timestamp a formato legible para admin.

    Ejemplo: 2026-06-02T00:38:12+00:00 → "2 de junio, 12:38 AM"
    """
    try:
        # Parsea el timestamp ISO
        dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))

        # Meses en español
        meses = [
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
        ]

        mes = meses[dt.month - 1]
        dia = dt.day
        hora = dt.hour
        minuto = dt.minute

        # Formato 12h con AM/PM
        period = "AM" if hora < 12 else "PM"
        hora_12 = hora if hora <= 12 else hora - 12
        if hora_12 == 0:
            hora_12 = 12

        return f"{dia} de {mes}, {hora_12}:{minuto:02d} {period}"
    except Exception:
        # Si falla, devuelve el original
        return iso_timestamp


def format_date_readable(date_str: str) -> str:
    """Convierte fecha a formato legible.

    Soporta: YYYY-MM-DD, DD/MM/YYYY, ISO con hora
    """
    if not date_str:
        return "-"

    try:
        # Intenta varios formatos
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"]:
            try:
                dt = datetime.strptime(date_str.split("T")[0], fmt)
                meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
                mes = meses[dt.month - 1]
                return f"{dt.day} de {mes} de {dt.year}"
            except ValueError:
                continue
        return date_str
    except Exception:
        return date_str


def validate_event_type(tipo_event: str) -> bool:
    """Valida si el tipo de evento es reconocido.

    Devuelve True si está en la lista de tipos válidos,
    False si fue inventado.
    """
    valid_types = {
        "concierto", "festival", "presentacion", "show", "recital",
        "evento", "fiesta", "boda", "cumpleaños", "aniversario",
        "gala", "convención", "asamblea", "reunión", "encuentro",
        "competencia", "torneo", "ceremonia", "inauguración"
    }

    tipo_norm = tipo_event.lower().strip()
    return any(t in tipo_norm for t in valid_types)


def format_solicitud_summary(sol: dict) -> str:
    """Formatea una solicitud para que sea clara y legible para el admin.

    Muestra solo los datos esenciales, sin técnicos.
    """
    lineas = []

    # Cliente
    cliente = sol.get('nombre_o_dni', '-')
    if cliente and cliente != "-":
        lineas.append(f"👤 {cliente}")

    # Localidad (limpia)
    localidad = sol.get('localidad', '')
    if localidad and localidad.lower() != "julcn":  # Evita entradas confusas
        lineas.append(f"📍 {localidad}")

    # Tipo de evento (valida)
    tipo = sol.get('tipo_evento', '')
    if tipo:
        if validate_event_type(tipo):
            lineas.append(f"🎉 {tipo}")
        else:
            lineas.append(f"⚠️ Evento: {tipo} (revisar)")

    # Fecha (formateada)
    fecha = sol.get('fecha_evento', '')
    if fecha:
        fecha_fmt = format_date_readable(fecha)
        lineas.append(f"📅 {fecha_fmt}")

    # Horario
    horario = sol.get('horario_evento', '')
    if horario:
        lineas.append(f"🕘 {horario}")

    return "\n".join(lineas) if lineas else "Sin detalles específicos"
