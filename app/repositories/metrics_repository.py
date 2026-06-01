"""Repositorio de Métricas (hoja `Metricas`)."""

from __future__ import annotations

import uuid

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_METRICS


def save(metric: dict) -> bool:
    record = dict(metric)
    record.setdefault("id_metrica", "MET-" + uuid.uuid4().hex[:8].upper())
    record["fecha_hora"] = record.get("fecha_hora") or sheets_client.now_iso()
    return sheets_client.append_record(SHEET_METRICS, record)


def get_all() -> list[dict]:
    return sheets_client.read_records(SHEET_METRICS)
