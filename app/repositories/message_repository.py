"""Repositorio de Mensajes (hoja `Mensajes`).

Trazabilidad de cada mensaje entrante/saliente para auditoría y seguimiento.
"""

from __future__ import annotations

import uuid

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_MESSAGES

# Direcciones
ENTRANTE = "ENTRANTE"
SALIENTE = "SALIENTE"
ADMIN_INTERNO = "ADMIN_INTERNO"
ADMIN_A_CLIENTE = "ADMIN_A_CLIENTE"
CLIENTE_A_ADMIN = "CLIENTE_A_ADMIN"


def save(message: dict) -> bool:
    record = dict(message)
    record.setdefault("id_mensaje", "MSG-" + uuid.uuid4().hex[:8].upper())
    record["fecha_hora"] = record.get("fecha_hora") or sheets_client.now_iso()
    return sheets_client.append_record(SHEET_MESSAGES, record)
