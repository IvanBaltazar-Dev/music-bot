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


def recent_for_client(numero_cliente: str, limit: int = 6) -> list[dict]:
    """Últimos mensajes del hilo de un cliente (orden cronológico).

    Excluye los mensajes internos entre administradores (ADMIN_INTERNO), que no
    forman parte de la conversación con el cliente.
    """
    target = "".join(ch for ch in str(numero_cliente) if ch.isdigit())
    hilo = []
    for r in sheets_client.read_records(SHEET_MESSAGES):
        digits = "".join(ch for ch in str(r.get("numero_usuario", "")) if ch.isdigit())
        if not digits or digits != target:
            continue
        if str(r.get("direccion", "")).strip().upper() == ADMIN_INTERNO:
            continue
        hilo.append(r)
    # Las filas ya vienen en orden de inserción; tomamos las últimas.
    return hilo[-limit:]
