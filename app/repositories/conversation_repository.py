"""Repositorio de Conversaciones (hoja `Conversaciones`).

Mantiene el estado de la conversación de cada cliente: flujo actual, paso,
estado (BOT_ACTIVO / ADMIN_CONTROL / ...), y si un administrador la controla.
"""

from __future__ import annotations

import json
import uuid

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_CONVERSATIONS

# Estados de conversación. Deben coincidir EXACTAMENTE con el CHECK constraint
# de conversation_threads.state en Supabase:
#   ('BOT_ACTIVO', 'ESPERANDO_RESPUESTA', 'ADMIN_CONTROL', 'CERRADA')
# Un valor fuera de esta lista rechaza toda la actualización (RuntimeError).
BOT_ACTIVO = "BOT_ACTIVO"
ESPERANDO_RESPUESTA = "ESPERANDO_RESPUESTA"
ADMIN_CONTROL = "ADMIN_CONTROL"
FINALIZADA = "CERRADA"


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
        "fecha_toma_control": updates.get("fecha_toma_control", ""),
        "fecha_suelta_control": updates.get("fecha_suelta_control", ""),
    }
    sheets_client.append_record(SHEET_CONVERSATIONS, record)

    # `profile_name` no es columna del esquema, así que el INSERT lo descarta.
    # Lo capturamos en el primer contacto con un update inmediato (la vía update
    # sí reenvía claves extra a Supabase -> clients.profile_name).
    profile_name = updates.get("profile_name", "")
    if profile_name:
        sheets_client.update_record(
            SHEET_CONVERSATIONS, "numero_usuario", numero_usuario,
            {"profile_name": profile_name, "fecha_ultima_interaccion": now},
        )


def set_state(numero_usuario: str, estado: str, admin_numero: str = "") -> None:
    updates = {"estado_conversacion": estado}
    if estado == ADMIN_CONTROL:
        updates["admin_en_control"] = "SI"
        updates["admin_numero"] = admin_numero
        updates["fecha_toma_control"] = sheets_client.now_iso()
    elif estado == BOT_ACTIVO:
        updates["admin_en_control"] = "NO"
        updates["admin_numero"] = ""
        updates["fecha_suelta_control"] = sheets_client.now_iso()
    upsert(numero_usuario, updates)


def release_control_for_admin(admin_numero: str) -> list[str]:
    """Libera todas las conversaciones tomadas por un admin.

    Devuelve los numeros de cliente liberados. Usa comparacion por digitos para
    cubrir filas duplicadas con +51, sin +51, espacios u otros formatos.
    """
    admin_digits = "".join(ch for ch in str(admin_numero) if ch.isdigit())
    if not admin_digits:
        return []

    released: list[str] = []
    now = sheets_client.now_iso()
    updates = {
        "estado_conversacion": BOT_ACTIVO,
        "admin_en_control": "NO",
        "admin_numero": "",
        "fecha_suelta_control": now,
    }

    for row in sheets_client.read_records(SHEET_CONVERSATIONS):
        estado = str(row.get("estado_conversacion", "")).strip().upper()
        row_admin = "".join(ch for ch in str(row.get("admin_numero", "")) if ch.isdigit())
        same_admin = row_admin == admin_digits or (
            row_admin and admin_digits and row_admin[-9:] == admin_digits[-9:]
        )
        if estado != ADMIN_CONTROL or not same_admin:
            continue

        client = "".join(ch for ch in str(row.get("numero_usuario", "")) if ch.isdigit())
        key = str(row.get("id_conversacion", "")).strip()
        ok = False
        if key:
            ok = sheets_client.update_record(SHEET_CONVERSATIONS, "id_conversacion", key, updates)
        if not ok:
            raw_number = str(row.get("numero_usuario", "")).strip()
            ok = sheets_client.update_record(SHEET_CONVERSATIONS, "numero_usuario", raw_number, updates)
        if ok and client:
            released.append(client)

    return released


def get_state(numero_usuario: str) -> str:
    conv = get(numero_usuario)
    return (conv or {}).get("estado_conversacion", BOT_ACTIVO) or BOT_ACTIVO


def get_temp_data(numero_usuario: str) -> dict:
    return temp_data_from_record(get(numero_usuario))


def temp_data_from_record(conv: dict | None) -> dict:
    """Lee los datos temporales del mismo snapshot de conversación."""
    raw = (conv or {}).get("datos_temporales_json", "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


def save_flow(numero_usuario: str, state: str, data: dict) -> None:
    """Persiste el avance de un flujo guiado para sobrevivir reinicios/workers."""
    upsert(numero_usuario, {
        "flujo_actual": "contratar" if state.startswith("hire_") else "",
        "paso_actual": state,
        "datos_temporales_json": json.dumps(data, ensure_ascii=False),
    })


def clear_flow(numero_usuario: str) -> None:
    """Limpia únicamente el estado temporal del bot, sin alterar el control admin."""
    upsert(numero_usuario, {
        "flujo_actual": "",
        "paso_actual": "",
        "datos_temporales_json": "",
    })
