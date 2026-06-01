"""Cliente central de Google Sheets (única fuente de conexión).

Encapsula TODO el acceso de bajo nivel a Google Sheets y ofrece un almacén en
memoria como fallback automático. De esta forma:

* El backend SIEMPRE levanta, aunque Sheets no esté configurado.
* El webhook nunca se rompe por un fallo de persistencia.
* La lógica de negocio (servicios/repositorios) no depende de gspread.

Diseño tolerante a fallos: cualquier excepción de red/credenciales degrada a
memoria sin propagar el error. Nunca se imprimen tokens ni credenciales.

Reglas de inicialización (importantes):
* Si una hoja NO existe, se crea SOLO con sus encabezados.
* Si una hoja existe, jamás se borra ni se sobrescribe su contenido.
* `ensure_sheets()` solo agrega encabezados a hojas vacías o inexistentes.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from app.config import settings
from app.repositories import sheets_schema

# ---------------------------------------------------------------------------
# Estado interno
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_use_sheets = False
_spreadsheet = None
_ws_cache: dict = {}

# Almacén en memoria (fallback). Se pierde al reiniciar el proceso.
# { nombre_hoja: list[dict] }
_mem: dict[str, list[dict]] = {name: [] for name in sheets_schema.all_sheet_names()}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Inicialización perezosa y tolerante a fallos
# ---------------------------------------------------------------------------
def _init() -> None:
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
    except Exception as exc:  # noqa: BLE001 - cualquier fallo degrada a memoria
        print(f"[sheets] no se pudo inicializar ({exc.__class__.__name__}). Usando memoria.")


_init()


def is_enabled() -> bool:
    """True si la persistencia en Google Sheets está activa."""
    return _use_sheets


# ---------------------------------------------------------------------------
# Acceso a hojas
# ---------------------------------------------------------------------------
def _get_ws(name: str, create: bool = True):
    """Devuelve la hoja. La crea con encabezados si no existe (cuando create)."""
    if not _use_sheets or _spreadsheet is None:
        return None

    if name in _ws_cache:
        return _ws_cache[name]

    headers = sheets_schema.headers_for(name)
    try:
        try:
            ws = _spreadsheet.worksheet(name)
        except Exception:
            if not create:
                return None
            ws = _spreadsheet.add_worksheet(
                title=name, rows=200, cols=max(10, len(headers) + 2)
            )
            if headers:
                ws.append_row(headers)
        # Si la hoja existe pero está vacía, sembrar encabezados (sin borrar nada).
        try:
            if headers and not ws.row_values(1):
                ws.update("A1", [headers])
        except Exception:  # noqa: BLE001
            pass
        _ws_cache[name] = ws
        return ws
    except Exception as exc:  # noqa: BLE001
        print(f"[sheets] error accediendo a la hoja '{name}': {exc.__class__.__name__}")
        return None


def ensure_sheets() -> dict:
    """Crea (si faltan) todas las hojas con sus encabezados. No borra datos.

    Devuelve un resumen {creadas: [...], existentes: [...]} o un aviso si está
    en modo memoria.
    """
    if not _use_sheets or _spreadsheet is None:
        return {"modo": "memoria", "creadas": [], "existentes": []}

    creadas, existentes = [], []
    try:
        present = {ws.title for ws in _spreadsheet.worksheets()}
    except Exception:  # noqa: BLE001
        present = set()

    for name in sheets_schema.all_sheet_names():
        existed = name in present
        ws = _get_ws(name, create=True)
        if ws is None:
            continue
        (existentes if existed else creadas).append(name)
    return {"modo": "sheets", "creadas": creadas, "existentes": existentes}


# ---------------------------------------------------------------------------
# CRUD genérico (con fallback en memoria)
# ---------------------------------------------------------------------------
def read_records(sheet_name: str) -> list[dict]:
    """Devuelve todas las filas como lista de dicts (claves = encabezados)."""
    if _use_sheets:
        ws = _get_ws(sheet_name)
        if ws is not None:
            try:
                return ws.get_all_records()
            except Exception as exc:  # noqa: BLE001
                print(f"[sheets] error leyendo '{sheet_name}': {exc.__class__.__name__}")
                return []
    with _lock:
        return [dict(r) for r in _mem.get(sheet_name, [])]


def append_record(sheet_name: str, record: dict) -> bool:
    """Agrega una fila ordenada según los encabezados del esquema."""
    headers = sheets_schema.headers_for(sheet_name)
    row = {h: record.get(h, "") for h in headers}

    if _use_sheets:
        for attempt in (1, 2):
            ws = _get_ws(sheet_name)
            if ws is None:
                break
            try:
                ws.append_row([row[h] for h in headers],
                              value_input_option="USER_ENTERED")
                return True
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[sheets] error guardando en '{sheet_name}' "
                    f"(intento {attempt}/2): {exc.__class__.__name__}"
                )
                _ws_cache.pop(sheet_name, None)

    with _lock:
        _mem.setdefault(sheet_name, []).append(row)
    if _use_sheets:
        print(f"[sheets] usando memoria temporal para '{sheet_name}' tras fallo de escritura.")
    return True


def find_record(sheet_name: str, key_col: str, key_val: str) -> dict | None:
    """Primer registro cuyo key_col coincide (str, case-insensitive en bordes)."""
    target = str(key_val).strip()
    for r in read_records(sheet_name):
        if str(r.get(key_col, "")).strip() == target:
            return r
    return None


def update_record(sheet_name: str, key_col: str, key_val: str, updates: dict) -> bool:
    """Actualiza la primera fila que coincide con key_col == key_val.

    En memoria: muta el dict. En Sheets: localiza la fila y reescribe las celdas
    afectadas. Devuelve False si no encuentra coincidencia.
    """
    headers = sheets_schema.headers_for(sheet_name)
    target = str(key_val).strip()

    if _use_sheets:
        ws = _get_ws(sheet_name)
        if ws is not None:
            try:
                records = ws.get_all_records()
                for idx, r in enumerate(records):
                    if str(r.get(key_col, "")).strip() == target:
                        row_number = idx + 2  # +1 encabezado, +1 base-1
                        merged = dict(r)
                        merged.update(updates)
                        ordered = [merged.get(h, "") for h in headers]
                        ws.update(
                            f"A{row_number}",
                            [ordered],
                            value_input_option="USER_ENTERED",
                        )
                        return True
                return False
            except Exception as exc:  # noqa: BLE001
                print(f"[sheets] error actualizando '{sheet_name}': {exc.__class__.__name__}")
                return False

    with _lock:
        for r in _mem.get(sheet_name, []):
            if str(r.get(key_col, "")).strip() == target:
                r.update(updates)
                return True
    return False


# ---------------------------------------------------------------------------
# Sembrado de datos por defecto en memoria (solo fallback, NO toca Sheets)
# ---------------------------------------------------------------------------
def seed_memory(sheet_name: str, rows: list[dict]) -> None:
    """Carga datos por defecto en memoria si la hoja está vacía en memoria.

    Útil para que el bot funcione de forma demostrable sin Sheets configurado.
    Si Sheets está habilitado, este sembrado se ignora (la hoja manda).
    """
    if _use_sheets:
        return
    headers = sheets_schema.headers_for(sheet_name)
    with _lock:
        if _mem.get(sheet_name):
            return
        _mem[sheet_name] = [{h: r.get(h, "") for h in headers} for r in rows]
