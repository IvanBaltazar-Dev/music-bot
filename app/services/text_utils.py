"""Utilidades de texto compartidas: normalización y coincidencia aproximada.

Centraliza la normalización (minúsculas, sin tildes, sin signos) y el fuzzy
matching. Usa `rapidfuzz` si está instalado; si no, cae a `difflib` de la
librería estándar. Nunca rompe por dependencias ausentes.
"""

from __future__ import annotations

import re
import unicodedata

try:  # rapidfuzz es opcional; difflib es el fallback estándar
    from rapidfuzz import fuzz as _rf_fuzz  # type: ignore

    _HAS_RAPIDFUZZ = True
except Exception:  # noqa: BLE001
    _HAS_RAPIDFUZZ = False

import difflib


def normalize(text: str) -> str:
    """minúsculas + sin tildes + sin signos + espacios reducidos."""
    text = (text or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def deburr(text: str) -> str:
    """minúsculas + sin tildes, PERO conserva signos (/, :, -) y dígitos.

    Útil para detectar fechas y horas (p. ej. '15/06/2026', '21:00', '9 pm')
    sin perder los separadores que `normalize` eliminaría.
    """
    text = (text or "").lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def ratio(a: str, b: str) -> float:
    """Similitud 0.0-1.0 entre dos cadenas (ya pueden venir normalizadas)."""
    a = a or ""
    b = b or ""
    if not a or not b:
        return 0.0
    if _HAS_RAPIDFUZZ:
        return _rf_fuzz.ratio(a, b) / 100.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def best_match(token: str, candidates: list[str], cutoff: float = 0.8) -> str | None:
    """Mejor candidato por encima del umbral, o None."""
    token = token or ""
    if not token or not candidates:
        return None
    best, best_score = None, 0.0
    for cand in candidates:
        score = ratio(token, cand)
        if score > best_score:
            best, best_score = cand, score
    return best if best_score >= cutoff else None
