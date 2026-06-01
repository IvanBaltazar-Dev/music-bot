"""Repositorio de persistencia.

Encapsula el acceso a Google Sheets de forma **opcional**. Si Google Sheets
no está habilitado, o faltan credenciales, o la librería `gspread` no está
instalada, el repositorio cae automáticamente a un almacenamiento en memoria.

De esta forma el backend SIEMPRE levanta, incluso sin configurar Sheets, y el
webhook nunca se rompe por un fallo de persistencia.

Funciones públicas:
    get_active_events()                  -> list[dict]
    save_event(event_data)               -> bool
    save_quotation_request(data)         -> bool
    get_recent_quotation_requests(limit) -> list[dict]
    get_active_admins()                  -> list[str]
    save_metric_event(metric_data)       -> bool
    get_metrics_summary()                -> dict
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

from app.config import settings

# ---------------------------------------------------------------------------
# Estado interno
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_use_sheets = False
_spreadsheet = None

# Almacenes en memoria (fallback). Se pierden al reiniciar el proceso.
_mem_events: list[dict] = []
_mem_quotations: list[dict] = []
_mem_metrics: list[dict] = []

# Nombres de hojas
SHEET_EVENTS = "Eventos"
SHEET_REQUESTS = "Solicitudes"
SHEET_ADMINS = "Admins"
SHEET_METRICS = "Metricas"

# Encabezados esperados por hoja
_HEADERS = {
    SHEET_EVENTS: [
        "id", "fecha", "hora", "ciudad", "lugar",
        "descripcion", "estado", "creado_por", "fecha_registro",
    ],
    SHEET_REQUESTS: [
        "id", "fecha_registro", "whatsapp", "nombre", "lugar",
        "fecha_evento", "tipo_evento", "duracion", "contacto", "estado",
    ],
    SHEET_ADMINS: ["nombre", "telefono", "activo"],
    SHEET_METRICS: ["fecha_hora", "tipo", "whatsapp", "detalle", "origen"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Inicialización de Google Sheets (perezosa y tolerante a fallos)
# ---------------------------------------------------------------------------
def _init_sheets() -> None:
    global _use_sheets, _spreadsheet

    if not settings.GOOGLE_SHEETS_ENABLED:
        print("[sheets] deshabilitado (GOOGLE_SHEETS_ENABLED=false). Usando memoria.")
        return

    creds_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if not settings.GOOGLE_SHEETS_ID or not creds_path or not os.path.exists(creds_path):
        print("[sheets] faltan GOOGLE_SHEETS_ID o credenciales válidas. Usando memoria.")
        return

    try:
        import gspread  # type: ignore
        from google.oauth2.service_account import Credentials  # type: ignore

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(creds)
        _spreadsheet = client.open_by_key(settings.GOOGLE_SHEETS_ID)
        _use_sheets = True
        print("[sheets] conexión establecida correctamente.")
    except ModuleNotFoundError:
        print("[sheets] 'gspread' no está instalado. Usando memoria. "
              "Instala con: pip install gspread google-auth")
    except Exception as exc:  # noqa: BLE001 - cualquier fallo debe degradar a memoria
        print(f"[sheets] no se pudo inicializar ({exc.__class__.__name__}). Usando memoria.")


def _get_ws(name: str):
    """Devuelve la hoja, creándola con encabezados si no existe. None si falla."""
    if not _use_sheets or _spreadsheet is None:
        return None
    try:
        try:
            ws = _spreadsheet.worksheet(name)
        except Exception:
            ws = _spreadsheet.add_worksheet(title=name, rows=100, cols=20)
            ws.append_row(_HEADERS.get(name, []))
        return ws
    except Exception as exc:  # noqa: BLE001
        print(f"[sheets] error accediendo a la hoja '{name}': {exc.__class__.__name__}")
        return None


_init_sheets()


def is_enabled() -> bool:
    """Indica si la persistencia en Google Sheets está activa."""
    return _use_sheets


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------
def _format_sheet_date(value) -> str:
    """Convierte fechas de Sheets a texto legible sin romper valores ya formateados."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()

    raw = str(value).strip()
    if not raw:
        return ""

    try:
        serial = float(raw)
    except ValueError:
        return raw

    if serial <= 0:
        return raw

    # Google Sheets usa el mismo origen serial que Excel para fechas modernas.
    base = datetime(1899, 12, 30, tzinfo=timezone.utc)
    return (base + timedelta(days=serial)).date().isoformat()


def _normalize_event_record(row: dict) -> dict:
    record = dict(row)
    record.setdefault("id", record.get("id_evento", ""))
    record.setdefault("fecha", _format_sheet_date(record.get("fecha_evento", record.get("fecha", ""))))
    record.setdefault("hora", record.get("hora_inicio", record.get("hora", "")))
    record.setdefault("descripcion", record.get("descripcion_publica", record.get("descripcion", "")))
    return record


def _is_public_event(row: dict) -> bool:
    estado = str(row.get("estado", "")).strip().upper()
    return estado in {"ACTIVO", "CONFIRMADO"}


def get_active_events() -> list[dict]:
    if _use_sheets:
        ws = _get_ws(SHEET_EVENTS)
        if ws is not None:
            try:
                rows = ws.get_all_records()
                return [_normalize_event_record(r) for r in rows if _is_public_event(r)]
            except Exception as exc:  # noqa: BLE001
                print(f"[sheets] error leyendo eventos: {exc.__class__.__name__}. Usando memoria.")
    with _lock:
        return [_normalize_event_record(e) for e in _mem_events if _is_public_event(e)]


def save_event(event_data: dict) -> bool:
    record = {
        "id": event_data.get("id") or _new_id(),
        "fecha": event_data.get("fecha", ""),
        "hora": event_data.get("hora", ""),
        "ciudad": event_data.get("ciudad", ""),
        "lugar": event_data.get("lugar", ""),
        "descripcion": event_data.get("descripcion", ""),
        "estado": event_data.get("estado", "ACTIVO"),
        "creado_por": event_data.get("creado_por", ""),
        "fecha_registro": event_data.get("fecha_registro") or _now_iso(),
    }

    if _use_sheets:
        ws = _get_ws(SHEET_EVENTS)
        if ws is not None:
            try:
                ws.append_row([record[h] for h in _HEADERS[SHEET_EVENTS]])
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"[sheets] error guardando evento: {exc.__class__.__name__}")
                return False

    with _lock:
        _mem_events.append(record)
    return True


# ---------------------------------------------------------------------------
# Solicitudes de cotización
# ---------------------------------------------------------------------------
def save_quotation_request(data: dict) -> bool:
    record = {
        "id": data.get("id") or _new_id(),
        "fecha_registro": data.get("fecha_registro") or _now_iso(),
        "whatsapp": data.get("whatsapp", ""),
        "nombre": data.get("nombre", ""),
        "lugar": data.get("lugar", ""),
        "fecha_evento": data.get("fecha_evento", ""),
        "tipo_evento": data.get("tipo_evento", ""),
        "duracion": data.get("duracion", ""),
        "contacto": data.get("contacto", ""),
        "estado": data.get("estado", "NUEVA"),
    }

    if _use_sheets:
        ws = _get_ws(SHEET_REQUESTS)
        if ws is not None:
            try:
                ws.append_row([record[h] for h in _HEADERS[SHEET_REQUESTS]])
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"[sheets] error guardando solicitud: {exc.__class__.__name__}")
                return False

    with _lock:
        _mem_quotations.append(record)
    return True


def get_recent_quotation_requests(limit: int = 5) -> list[dict]:
    if _use_sheets:
        ws = _get_ws(SHEET_REQUESTS)
        if ws is not None:
            try:
                rows = ws.get_all_records()
                return list(reversed(rows))[:limit]
            except Exception as exc:  # noqa: BLE001
                print(f"[sheets] error leyendo solicitudes: {exc.__class__.__name__}")
                return []
    with _lock:
        return list(reversed(_mem_quotations))[:limit]


# ---------------------------------------------------------------------------
# Administradores
# ---------------------------------------------------------------------------
def get_active_admins() -> list[str]:
    """Devuelve la lista de teléfonos (solo dígitos) de admins activos en Sheets."""
    if _use_sheets:
        ws = _get_ws(SHEET_ADMINS)
        if ws is not None:
            try:
                rows = ws.get_all_records()
                numbers = []
                for r in rows:
                    if str(r.get("activo", "")).strip().upper() == "SI":
                        digits = "".join(ch for ch in str(r.get("telefono", "")) if ch.isdigit())
                        if digits:
                            numbers.append(digits)
                return numbers
            except Exception as exc:  # noqa: BLE001
                print(f"[sheets] error leyendo admins: {exc.__class__.__name__}")
                return []
    return []


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
def save_metric_event(metric_data: dict) -> bool:
    record = {
        "fecha_hora": metric_data.get("fecha_hora") or _now_iso(),
        "tipo": metric_data.get("tipo", ""),
        "whatsapp": metric_data.get("whatsapp", ""),
        "detalle": metric_data.get("detalle", ""),
        "origen": metric_data.get("origen", "bot"),
    }

    # Siempre guardamos en memoria para poder calcular resúmenes rápidos.
    with _lock:
        _mem_metrics.append(record)

    if _use_sheets:
        ws = _get_ws(SHEET_METRICS)
        if ws is not None:
            try:
                ws.append_row([record[h] for h in _HEADERS[SHEET_METRICS]])
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"[sheets] error guardando métrica: {exc.__class__.__name__}")
                return False
    return True


def _all_metrics() -> list[dict]:
    """Métricas para el resumen. Prefiere Sheets si está disponible."""
    if _use_sheets:
        ws = _get_ws(SHEET_METRICS)
        if ws is not None:
            try:
                return ws.get_all_records()
            except Exception:  # noqa: BLE001
                pass
    with _lock:
        return list(_mem_metrics)


def get_metrics_summary() -> dict:
    metrics = _all_metrics()
    now = datetime.now(timezone.utc)
    today = now.date()
    week_ago = now - timedelta(days=7)

    def _parse(dt_str: str):
        try:
            d = datetime.fromisoformat(str(dt_str))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d
        except Exception:  # noqa: BLE001
            return None

    today_rows, week_rows = [], []
    for m in metrics:
        d = _parse(m.get("fecha_hora", ""))
        if d is None:
            continue
        if d.date() == today:
            today_rows.append(m)
        if d >= week_ago:
            week_rows.append(m)

    def _count(rows, tipo):
        return sum(1 for r in rows if r.get("tipo") == tipo)

    def _unique_users(rows):
        return len({r.get("whatsapp") for r in rows if r.get("whatsapp")})

    return {
        "conversaciones_hoy": _count(today_rows, "intent_greeting"),
        "usuarios_unicos_hoy": _unique_users(today_rows),
        "consultas_eventos_hoy": _count(today_rows, "intent_events"),
        "consultas_precio_hoy": _count(today_rows, "intent_price"),
        "leads_completos_hoy": _count(today_rows, "quotation_completed"),
        "no_reconocidos_hoy": _count(today_rows, "unknown_message"),
        "usuarios_unicos_semana": _unique_users(week_rows),
        "leads_semana": _count(week_rows, "quotation_completed"),
        "eventos_consultados_semana": _count(week_rows, "intent_events"),
        "eventos_registrados": _count(metrics, "event_created"),
    }
