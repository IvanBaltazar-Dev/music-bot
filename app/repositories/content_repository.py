"""Repositorio de Contenidos de la agrupación (hoja `ContenidosAgrupacion`).

Videos, canciones/música, redes y descripción. No se inventan URLs: si una hoja
no tiene contenidos de cierta categoría, el flujo simplemente no ofrece ese botón.

Se adapta a la hoja real, que usa la columna `categoria` con valores como
QUIENES_SON / VIDEO / MUSICA / RED_SOCIAL (y `prioridad` para el orden). Mantiene
compatibilidad con nombres antiguos (`tipo`, `orden`) por si acaso.
"""

from __future__ import annotations

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_CONTENT
from app.services import text_utils

# Comparación tolerante: sin tildes, minúsculas, '_' y espacios unificados.
_n = text_utils.normalize

# Tipos lógicos que usa el bot (los pide group_info_service).
VIDEO = "VIDEO"
CANCION = "CANCION"
FACEBOOK = "FACEBOOK"
TIKTOK = "TIKTOK"
YOUTUBE = "YOUTUBE"
INSTAGRAM = "INSTAGRAM"
DESCRIPCION_CORTA = "DESCRIPCION_CORTA"
DESCRIPCION_LARGA = "DESCRIPCION_LARGA"

REDES = {FACEBOOK, TIKTOK, YOUTUBE, INSTAGRAM}

# Valores que cuentan como "activo = sí" en la hoja.
_ACTIVO_TRUE = {"si", "true", "1", "x", "yes", "activo", "verdadero", "ok"}

# Categorías de la hoja (ya normalizadas) agrupadas por significado.
# Acepta tanto la estructura real (QUIENES_SON/MUSICA/RED_SOCIAL) como variantes.
_VIDEO_CATS = {"video", "videos"}
_MUSICA_CATS = {"musica", "cancion", "canciones", "music", "tema", "temas"}
_DESC_CATS = {
    "quienes son", "quien es", "descripcion", "descripcion larga",
    "descripcion corta", "sobre nosotros", "nosotros", "biografia", "bio",
}
_RED_CATS = {
    "red social", "redes sociales", "redes", "red", "social",
    "facebook", "tiktok", "youtube", "instagram",
}


def _categoria(r: dict) -> str:
    """Categoría normalizada (columna `categoria`, o `tipo` por compatibilidad)."""
    return _n(r.get("categoria") or r.get("tipo") or "")


def _orden_val(r: dict) -> int:
    raw = str(r.get("prioridad") or r.get("orden") or "999").strip() or "999"
    try:
        return int(raw)
    except ValueError:
        return 999


def get_active() -> list[dict]:
    """Contenidos activos (activo = SI), ordenados por prioridad ascendente."""
    rows = [
        r for r in sheets_client.read_records(SHEET_CONTENT)
        if _n(r.get("activo", "")) in _ACTIVO_TRUE
    ]
    return sorted(rows, key=_orden_val)


def _by_cats(cats: set[str]) -> list[dict]:
    return [r for r in get_active() if _categoria(r) in cats]


def by_type(tipo: str) -> list[dict]:
    """Filtra por tipo lógico (VIDEO/CANCION) o por categoría literal."""
    t = (tipo or "").upper()
    if t == VIDEO:
        return _by_cats(_VIDEO_CATS)
    if t == CANCION:
        return _by_cats(_MUSICA_CATS)
    # Otros: comparación directa por categoría normalizada.
    return [r for r in get_active() if _categoria(r) == _n(tipo)]


def by_types(tipos: set[str]) -> list[dict]:
    targets = {_n(t) for t in tipos}
    return [r for r in get_active() if _categoria(r) in targets]


def get_redes() -> list[dict]:
    return _by_cats(_RED_CATS)


def get_description() -> str:
    """Texto de '¿Quiénes son?': usa la descripción (o el título) de la fila
    de categoría QUIENES_SON / DESCRIPCION. Cadena vacía si no hay."""
    rows = _by_cats(_DESC_CATS)
    if rows:
        r = rows[0]
        return str(r.get("descripcion", "") or r.get("titulo", "")).strip()
    return ""
