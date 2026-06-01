"""Servicio de Localidades.

Personaliza las respuestas del bot según la ciudad/provincia del usuario. Las
frases NUNCA están quemadas en el código de los flujos: provienen de la hoja
`Localidades` (o del sembrado por defecto cuando Sheets no está disponible).

El usuario puede escribir la ciudad directamente, con errores de tipeo, o con
apodos ("ciudad incontrastable", "tierra de las flores"). La búsqueda usa:
* normalización (minúsculas, sin tildes, sin signos)
* coincidencia por nombre, nombre_normalizado y palabras_clave
* fuzzy matching (rapidfuzz si está disponible; si no, difflib)
"""

from __future__ import annotations

from app.repositories import locality_repository
from app.services import text_utils

# Frase genérica cuando no se reconoce la localidad (contratación).
GENERIC_CONTRATACION = (
    "¡Qué bonito destino! Por ahí se puede armar una celebración con bastante cariño 🙌🎶"
)


def normalizar_localidad(texto: str) -> str:
    """Normaliza un texto de localidad (minúsculas, sin tildes, sin signos)."""
    return text_utils.normalize(texto)


def _candidates_for(loc: dict) -> list[str]:
    """Cadenas normalizadas con las que puede coincidir una localidad."""
    cands = set()
    nombre = text_utils.normalize(loc.get("nombre_localidad", ""))
    if nombre:
        cands.add(nombre)
    norm = text_utils.normalize(loc.get("nombre_normalizado", ""))
    if norm:
        cands.add(norm)
    for kw in str(loc.get("palabras_clave", "")).split(","):
        kw_norm = text_utils.normalize(kw)
        if kw_norm:
            cands.add(kw_norm)
    return [c for c in cands if c]


def buscar_localidad(texto_usuario: str) -> dict | None:
    """Devuelve el registro de la localidad detectada en el texto, o None.

    Estrategia:
    1. Coincidencia por contención (la localidad/keyword aparece en el texto).
       Se prefiere la coincidencia más larga (más específica).
    2. Fuzzy matching token a token contra nombres/keywords.
    """
    norm_text = text_utils.normalize(texto_usuario)
    if not norm_text:
        return None

    localities = locality_repository.get_all_active()
    tokens = norm_text.split()

    best_contains = None
    best_contains_len = 0
    best_fuzzy = None
    best_fuzzy_score = 0.0

    for loc in localities:
        for cand in _candidates_for(loc):
            # 1) Contención directa (frase completa dentro del texto)
            #    Se exige límite de palabra para evitar falsos positivos ("lima"
            #    dentro de "climatizado", por ejemplo).
            if cand in norm_text and _is_word_boundary(norm_text, cand):
                if len(cand) > best_contains_len:
                    best_contains = loc
                    best_contains_len = len(cand)

            # 2) Fuzzy a nivel de token (corrige errores de tipeo)
            for tok in tokens:
                if len(tok) < 3:
                    continue
                score = text_utils.ratio(tok, cand)
                if score > best_fuzzy_score:
                    best_fuzzy_score = score
                    best_fuzzy = loc

    if best_contains is not None:
        return best_contains
    if best_fuzzy is not None and best_fuzzy_score >= 0.85:
        return best_fuzzy
    return None


def _is_word_boundary(text: str, fragment: str) -> bool:
    """True si `fragment` aparece en `text` como palabra(s) completas."""
    idx = text.find(fragment)
    while idx != -1:
        before = text[idx - 1] if idx > 0 else " "
        after_pos = idx + len(fragment)
        after = text[after_pos] if after_pos < len(text) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        idx = text.find(fragment, idx + 1)
    return False


def nombre_de(localidad: dict | None) -> str:
    if not localidad:
        return ""
    return str(localidad.get("nombre_localidad", "")).strip()


def obtener_frase_contratacion(localidad: dict | None) -> str:
    if localidad:
        frase = str(localidad.get("frase_contratacion", "")).strip()
        if frase:
            return frase
    return GENERIC_CONTRATACION


def obtener_frase_eventos(localidad: dict | None) -> str:
    if localidad:
        return str(localidad.get("frase_eventos", "")).strip()
    return ""


def obtener_frase_general(localidad: dict | None) -> str:
    if localidad:
        return str(localidad.get("frase_general", "")).strip()
    return ""
