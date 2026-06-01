"""Repositorio de Errores (hoja `Errores`)."""

from __future__ import annotations

import uuid

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_ERRORS


def save(error: dict) -> bool:
    record = dict(error)
    record.setdefault("id_error", "ERR-" + uuid.uuid4().hex[:8].upper())
    record["fecha_hora"] = record.get("fecha_hora") or sheets_client.now_iso()
    record.setdefault("estado", "NUEVO")
    return sheets_client.append_record(SHEET_ERRORS, record)
