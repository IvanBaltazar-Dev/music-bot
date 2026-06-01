"""Repositorio de Conversaciones (hoja `Conversaciones`).

Mantiene el estado de la conversación de cada cliente: flujo actual, paso,
estado (BOT_ACTIVO / ADMIN_CONTROL / ...), y si un administrador la controla.
"""

from __future__ import annotations

import json
import uuid

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_CONVERSATIONS

# Estados de conversación
BOT_ACTIVO = "BOT_ACTIVO"
ESPERANDO_RESPUESTA = "ESPERANDO_RESPUESTA"
ADMIN_CONTROL = "ADMIN_CONTROL"
FINALIZADA = "FINALIZADA"


def _new_id() -> str:
    return "CONV-" + uuid.uuid4().hex[:8].upper()


def get(numero_usuario: str) -> dict | None:
    return sheets_client.find_record(SHEET_CONVERSATIONS, "numero_usuario", numero_usuario)


def upsert(numero_usuario: str, updates: dict) -> None:
    """Crea o actualiza la conversación de un usuario."""
    now = sheets_client.now_iso()
    existing = get(numero_usuario)
    if existing:
        payload = dict(updates)
        payload["fecha_ultima_interaccion"] = now
        sheets_client.update_record(
            SHEET_CONVERSATIONS, "numero_usuario", numero_usuario, payload
        )
        return

    record = {
        "id_conversacion": _new_id(),
        "numero_usuario": numero_usuario,
        "flujo_actual": updates.get("flujo_actual", ""),
        "paso_actual": updates.get("paso_actual", ""),
        "estado_conversacion": updates.get("estado_conversacion", BOT_ACTIVO),
        "datos_temporales_json": updates.get("datos_temporales_json", ""),
        "admin_en_control": updates.get("admin_en_control", "NO"),
        "admin_numero": updates.get("admin_numero", ""),
        "fecha_inicio": now,
        "fecha_ultima_interaccion": now,
    }
    sheets_client.append_record(SHEET_CONVERSATIONS, record)


def set_state(numero_usuario: str, estado: str, admin_numero: str = "") -> None:
    updates = {"estado_conversacion": estado}
    if estado == ADMIN_CONTROL:
        updates["admin_en_control"] = "SI"
        updates["admin_numero"] = admin_numero
    elif estado == BOT_ACTIVO:
        updates["admin_en_control"] = "NO"
        updates["admin_numero"] = ""
    upsert(numero_usuario, updates)


def get_state(numero_usuario: str) -> str:
    conv = get(numero_usuario)
    return (conv or {}).get("estado_conversacion", BOT_ACTIVO) or BOT_ACTIVO


def get_temp_data(numero_usuario: str) -> dict:
    conv = get(numero_usuario)
    raw = (conv or {}).get("datos_temporales_json", "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}
