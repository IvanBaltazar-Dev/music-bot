"""Repositorio de Seguimientos (hoja `Seguimientos`).

Registra cuándo un administrador activa "Hacer seguimiento" sobre una solicitud.
"""

from __future__ import annotations

import uuid

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_FOLLOWUPS


def save(codigo_solicitud: str, admin_numero: str, numero_cliente: str) -> bool:
    record = {
        "id_seguimiento": "SEG-" + uuid.uuid4().hex[:8].upper(),
        "codigo_solicitud": codigo_solicitud,
        "admin_numero": admin_numero,
        "numero_cliente": numero_cliente,
        "fecha_inicio": sheets_client.now_iso(),
        "estado": "ACTIVO",
    }
    return sheets_client.append_record(SHEET_FOLLOWUPS, record)


def followers_for_client(numero_cliente: str) -> list[str]:
    """Admins con seguimiento ACTIVO sobre las solicitudes de un cliente."""
    target = "".join(ch for ch in str(numero_cliente) if ch.isdigit())
    admins = []
    for r in sheets_client.read_records(SHEET_FOLLOWUPS):
        if str(r.get("estado", "")).strip().upper() != "ACTIVO":
            continue
        digits = "".join(ch for ch in str(r.get("numero_cliente", "")) if ch.isdigit())
        if digits and digits == target:
            admin = "".join(ch for ch in str(r.get("admin_numero", "")) if ch.isdigit())
            if admin:
                admins.append(admin)
    return list(dict.fromkeys(admins))
