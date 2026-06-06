"""Repositorio de Solicitudes de Contratación (hoja `SolicitudesContratacion`).

Genera el código interno (SOL-0001) y persiste las solicitudes. El código NUNCA
se muestra al cliente; es de uso interno para administradores.
"""

from __future__ import annotations

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_HIRING

# Estados válidos de una solicitud
ESTADO_ABIERTA = "ABIERTA"
ESTADO_EN_SEGUIMIENTO = "EN_SEGUIMIENTO"
ESTADO_TOMADA = "TOMADA_POR_ADMIN"
ESTADO_EN_CONVERSACION = "EN_CONVERSACION"
ESTADO_COTIZADA = "COTIZADA"
ESTADO_CERRADA = "CERRADA"
ESTADO_DESCARTADA = "DESCARTADA"

ACTIVE_STATES = {
    ESTADO_ABIERTA,
    ESTADO_EN_SEGUIMIENTO,
    ESTADO_TOMADA,
    ESTADO_EN_CONVERSACION,
}


def next_code() -> str:
    """Siguiente código correlativo SOL-0001, SOL-0002, ..."""
    existing = sheets_client.read_records(SHEET_HIRING)
    max_n = 0
    for r in existing:
        code = str(r.get("codigo_solicitud", ""))
        digits = code.rsplit("-", 1)[-1]
        if digits.isdigit():
            max_n = max(max_n, int(digits))
    return f"SOL-{max_n + 1:04d}"


def save(data: dict) -> str:
    """Crea una solicitud nueva y devuelve su código interno."""
    code = data.get("codigo_solicitud") or next_code()
    now = sheets_client.now_iso()
    record = dict(data)
    record["codigo_solicitud"] = code
    record.setdefault("fecha_registro", now)
    record.setdefault("estado", ESTADO_ABIERTA)
    record.setdefault("admin_asignado", "")
    record.setdefault("modo_atencion", "BOT")
    record.setdefault("origen", "whatsapp")
    record["fecha_ultima_interaccion"] = now
    sheets_client.append_record(SHEET_HIRING, record)
    return code


def get_by_code(code: str) -> dict | None:
    return sheets_client.find_record(SHEET_HIRING, "codigo_solicitud", code)


def get_by_client(numero_cliente: str) -> dict | None:
    """Solicitud más reciente de un cliente (por número)."""
    target = "".join(ch for ch in str(numero_cliente) if ch.isdigit())
    matches = []
    for r in sheets_client.read_records(SHEET_HIRING):
        digits = "".join(ch for ch in str(r.get("numero_cliente", "")) if ch.isdigit())
        if digits and digits == target:
            matches.append(r)
    return matches[-1] if matches else None


def get_by_client_fragment(fragmento: str) -> dict | None:
    """Solicitud mas reciente cuyo numero contiene el fragmento indicado."""
    target = "".join(ch for ch in str(fragmento) if ch.isdigit())
    if not target:
        return None
    matches = []
    for r in sheets_client.read_records(SHEET_HIRING):
        digits = "".join(ch for ch in str(r.get("numero_cliente", "")) if ch.isdigit())
        if digits and (target in digits or digits.endswith(target)):
            matches.append(r)
    return matches[-1] if matches else None


def get_active_by_client(numero_cliente: str) -> dict | None:
    """Solicitud abierta más reciente de un cliente, si existe."""
    target = "".join(ch for ch in str(numero_cliente) if ch.isdigit())
    matches = []
    for r in sheets_client.read_records(SHEET_HIRING):
        digits = "".join(ch for ch in str(r.get("numero_cliente", "")) if ch.isdigit())
        estado = str(r.get("estado", "")).strip().upper()
        if digits and digits == target and estado in ACTIVE_STATES:
            matches.append(r)
    return matches[-1] if matches else None


def get_controlled_by_admin(admin_number: str) -> dict | None:
    """Solicitud en conversacion que esta atendiendo un administrador."""
    target = "".join(ch for ch in str(admin_number) if ch.isdigit())
    matches = []
    for r in sheets_client.read_records(SHEET_HIRING):
        admin = "".join(ch for ch in str(r.get("admin_asignado", "")) if ch.isdigit())
        estado = str(r.get("estado", "")).strip().upper()
        same_admin = admin == target or (admin and target and admin[-9:] == target[-9:])
        if same_admin and estado == ESTADO_EN_CONVERSACION:
            matches.append(r)
    return matches[-1] if matches else None


def release_control_by_admin(admin_number: str, trace_message: str = "") -> list[dict]:
    """Libera todas las solicitudes en conversacion asignadas al admin."""
    target = "".join(ch for ch in str(admin_number) if ch.isdigit())
    if not target:
        return []

    released: list[dict] = []
    for r in sheets_client.read_records(SHEET_HIRING):
        admin = "".join(ch for ch in str(r.get("admin_asignado", "")) if ch.isdigit())
        estado = str(r.get("estado", "")).strip().upper()
        same_admin = admin == target or (admin and target and admin[-9:] == target[-9:])
        if not same_admin or estado != ESTADO_EN_CONVERSACION:
            continue

        code = str(r.get("codigo_solicitud", "")).strip()
        if not code:
            continue

        observaciones = str(r.get("observaciones", "") or "").strip()
        if trace_message:
            observaciones = f"{observaciones}\n{trace_message}".strip()
        ok = update(code, {
            "estado": ESTADO_ABIERTA,
            "modo_atencion": "BOT",
            "admin_asignado": "",
            "observaciones": observaciones,
        })
        if ok:
            released.append(r)

    return released


def update(code: str, updates: dict) -> bool:
    updates = dict(updates)
    updates["fecha_ultima_interaccion"] = sheets_client.now_iso()
    return sheets_client.update_record(SHEET_HIRING, "codigo_solicitud", code, updates)


def get_recent(limit: int = 5) -> list[dict]:
    return list(reversed(sheets_client.read_records(SHEET_HIRING)))[:limit]
