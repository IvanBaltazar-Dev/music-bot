"""Repositorio de Contenidos de la agrupación (hoja `ContenidosAgrupacion`).

Videos, canciones, redes y descripciones. No se inventan URLs: si una hoja no
tiene contenidos de cierto tipo, el flujo simplemente no ofrece ese botón.
"""

from __future__ import annotations

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_CONTENT

# Tipos de contenido conocidos
VIDEO = "VIDEO"
CANCION = "CANCION"
FACEBOOK = "FACEBOOK"
TIKTOK = "TIKTOK"
YOUTUBE = "YOUTUBE"
INSTAGRAM = "INSTAGRAM"
DESCRIPCION_CORTA = "DESCRIPCION_CORTA"
DESCRIPCION_LARGA = "DESCRIPCION_LARGA"

REDES = {FACEBOOK, TIKTOK, YOUTUBE, INSTAGRAM}


def get_active() -> list[dict]:
    """Contenidos activos (activo = SI), ordenados por `orden` ascendente."""
    rows = [
        r for r in sheets_client.read_records(SHEET_CONTENT)
        if str(r.get("activo", "")).strip().upper() in ("SI", "SÍ", "TRUE", "1")
    ]

    def _orden(r):
        try:
            return int(str(r.get("orden", "999")).strip() or 999)
        except ValueError:
            return 999

    return sorted(rows, key=_orden)


def by_type(tipo: str) -> list[dict]:
    tipo = tipo.upper()
    return [r for r in get_active() if str(r.get("tipo", "")).strip().upper() == tipo]


def by_types(tipos: set[str]) -> list[dict]:
    tipos = {t.upper() for t in tipos}
    return [r for r in get_active() if str(r.get("tipo", "")).strip().upper() in tipos]


def get_redes() -> list[dict]:
    return by_types(REDES)


def get_description() -> str:
    """Descripción larga si existe, si no la corta; cadena vacía si no hay."""
    largas = by_type(DESCRIPCION_LARGA)
    if largas:
        return str(largas[0].get("descripcion", "") or largas[0].get("titulo", ""))
    cortas = by_type(DESCRIPCION_CORTA)
    if cortas:
        return str(cortas[0].get("descripcion", "") or cortas[0].get("titulo", ""))
    return ""
