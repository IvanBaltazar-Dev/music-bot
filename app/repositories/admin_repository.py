"""Repositorio de Administradores (hoja `Administradores`)."""

from __future__ import annotations

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_ADMINS


def _only_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def get_active_numbers() -> list[str]:
    """Teléfonos (solo dígitos) de administradores con activo = SI."""
    numbers = []
    for r in sheets_client.read_records(SHEET_ADMINS):
        if str(r.get("activo", "")).strip().upper() in ("SI", "SÍ", "TRUE", "1"):
            digits = _only_digits(r.get("telefono", ""))
            if digits:
                numbers.append(digits)
    return numbers


def get_name(numero: str) -> str:
    target = _only_digits(numero)
    for r in sheets_client.read_records(SHEET_ADMINS):
        if _only_digits(r.get("telefono", "")) == target:
            return str(r.get("nombre", "")) or ""
    return ""
