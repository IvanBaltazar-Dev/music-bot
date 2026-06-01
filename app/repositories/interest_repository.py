"""Repositorio de Intereses por Localidad (hoja `InteresesLocalidad`).

Guarda cuando un usuario pide que la agrupación visite su localidad aunque no
haya un evento confirmado todavía.
"""

from __future__ import annotations

import uuid

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_INTEREST


def save(numero_usuario: str, localidad: str, nombre: str = "", mensaje: str = "") -> bool:
    record = {
        "id_interes": "INT-" + uuid.uuid4().hex[:8].upper(),
        "fecha_hora": sheets_client.now_iso(),
        "numero_usuario": numero_usuario,
        "nombre": nombre,
        "localidad": localidad,
        "mensaje": mensaje,
        "estado": "NUEVO",
    }
    return sheets_client.append_record(SHEET_INTEREST, record)
