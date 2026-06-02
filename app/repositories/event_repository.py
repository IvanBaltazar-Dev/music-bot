"""Repositorio de Eventos (hoja `Eventos`).

Lee y escribe eventos con el esquema ampliado del proyecto. La lógica de filtrado
por estado/fecha vive en el servicio; aquí solo se accede a los datos.
"""

from __future__ import annotations

import uuid

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_EVENTS


def _new_id() -> str:
    return "EVT-" + uuid.uuid4().hex[:8].upper()


def get_all() -> list[dict]:
    return sheets_client.read_records(SHEET_EVENTS)


def get_by_id(event_id: str) -> dict | None:
    return sheets_client.find_record(SHEET_EVENTS, "id_evento", event_id)


def update(event_id: str, updates: dict) -> bool:
    """Actualiza campos de un evento. Refresca fecha_actualizacion."""
    updates = dict(updates)
    updates["fecha_actualizacion"] = sheets_client.now_iso()
    return sheets_client.update_record(SHEET_EVENTS, "id_evento", event_id, updates)


def save(event: dict) -> str:
    """Guarda un evento y devuelve su id_evento."""
    event_id = event.get("id_evento") or _new_id()
    now = sheets_client.now_iso()
    record = dict(event)
    record["id_evento"] = event_id
    record.setdefault("estado", "CONFIRMADO")
    record.setdefault("fecha_creacion", now)
    record["fecha_actualizacion"] = now
    sheets_client.append_record(SHEET_EVENTS, record)
    return event_id
