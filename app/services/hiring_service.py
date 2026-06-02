"""Servicio de contratación.

Convierte los datos recogidos en el flujo "Quiero contratarlos" en una solicitud
interna (con código SOL-XXXX) y arma los textos para el cliente. El bot NO cotiza,
NO evalúa y NO decide: solo recoge datos y despierta al manager.

IMPORTANTE: el código de solicitud es interno; jamás se muestra al cliente.
"""

from __future__ import annotations

from app.repositories import hiring_request_repository as hiring_repo
from app.repositories import sheets_client


def crear_solicitud(numero_cliente: str, datos: dict) -> tuple[str, dict]:
    """Crea la solicitud de contratación. Devuelve (codigo, registro).

    Nota: los detalles del evento (tipo, fecha, hora, lugar) se adjuntan al
    registro en memoria para la notificación a los admins. La hoja solo guarda
    las columnas de su esquema; estas claves extra se ignoran al persistir.
    """
    now = sheets_client.now_iso()
    record = {
        "numero_cliente": numero_cliente,
        "nombre_o_dni": datos.get("nombre_o_dni", ""),
        "observaciones": datos.get("observaciones", ""),
        "estado": hiring_repo.ESTADO_ABIERTA,
        "modo_atencion": "BOT",
        "origen": "whatsapp",
        "fecha_registro": datos.get("fecha_registro") or now,
        "fecha_ultima_interaccion": now,
        # Detalles del evento (para la notificación; no se persisten en la hoja)
        "tipo_evento": datos.get("tipo_evento", ""),
        "fecha_evento": datos.get("fecha_evento", ""),
        "horario_evento": datos.get("horario_evento", ""),
        "localidad": datos.get("localidad", ""),
    }
    code = hiring_repo.save(record)
    record["codigo_solicitud"] = code
    return code, record


def texto_cierre_cliente(nombre: str) -> str:
    """Mensaje de cierre para el cliente (sin mostrar el código interno)."""
    saludo = f"¡Listo, {nombre}! 🙌🎶" if nombre else "¡Listo! 🙌🎶"
    return (
        f"{saludo}\n\n"
        "Ya dejé tu solicitud bien encargada. Ahora vamos a despertar a nuestro "
        "manager 😄🎶\n\n"
        "Te responderán por este mismo chat para coordinar los detalles. "
        "Estate atento por aquí."
    )
