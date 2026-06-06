"""Repositorio de Localidades.

Las frases personalizadas por ciudad/provincia viven en la hoja `Localidades`,
NUNCA quemadas en el código de los flujos. Este repositorio las lee desde Sheets
y, cuando Sheets no está disponible, usa un sembrado en memoria con los ejemplos
oficiales para que el bot siga siendo demostrable.
"""

from __future__ import annotations

from app.repositories import sheets_client
from app.repositories.sheets_schema import SHEET_LOCALITIES

# Sembrado por defecto (solo se usa en modo memoria, si la hoja no existe).
# La hoja `Localidades` siempre tiene prioridad cuando Sheets está habilitado.
_DEFAULT_LOCALITIES = [
    {
        "id_localidad": "LOC-001", "nombre_localidad": "Huancayo",
        "nombre_normalizado": "huancayo", "region": "Junín", "provincia": "Huancayo",
        "palabras_clave": "huanca, ciudad incontrastable, incontrastable, wanka",
        "frase_contratacion": "¡Huancayo, la Ciudad Incontrastable! Nos encanta celebrar en casa 🎶",
        "frase_eventos": "Qué bueno que nos escribas desde Huancayo, nuestra tierra.",
        "frase_general": "Huancayo, nuestra tierra, siempre presente.",
        "activo": "SI", "prioridad": "1", "fecha_actualizacion": "2026-06-01",
    },
    {
        "id_localidad": "LOC-002", "nombre_localidad": "Tarma",
        "nombre_normalizado": "tarma", "region": "Junín", "provincia": "Tarma",
        "palabras_clave": "tierra de las flores, flores, tarmeño, tarmeña",
        "frase_contratacion": "¡Tarma, la tierra de las flores! 🌸 Suena a una buena celebración.",
        "frase_eventos": "Qué bueno que nos escribas desde Tarma, la tierra de las flores.",
        "frase_general": "Tarma siempre tiene el encanto de la tierra de las flores.",
        "activo": "SI", "prioridad": "1", "fecha_actualizacion": "2026-06-01",
    },
    {
        "id_localidad": "LOC-003", "nombre_localidad": "Lima",
        "nombre_normalizado": "lima", "region": "Lima", "provincia": "Lima",
        "palabras_clave": "lima capital, capital, todos salen adelante",
        "frase_contratacion": "¡Lima! Siempre hay un buen motivo para celebrar.",
        "frase_eventos": "Qué bueno que nos escribas desde la capital.",
        "frase_general": "Lima, la capital, siempre con algo que celebrar.",
        "activo": "SI", "prioridad": "1", "fecha_actualizacion": "2026-06-01",
    },
    {
        "id_localidad": "LOC-004", "nombre_localidad": "Jauja",
        "nombre_normalizado": "jauja", "region": "Junín", "provincia": "Jauja",
        "palabras_clave": "jauja querida, primera capital, aire bonito",
        "frase_contratacion": "¡Jauja querida! Con su gente alegre, la celebración ya toma forma 🎶",
        "frase_eventos": "Qué alegría que nos escribas desde Jauja.",
        "frase_general": "Jauja querida, siempre con alegría.",
        "activo": "SI", "prioridad": "1", "fecha_actualizacion": "2026-06-01",
    },
    {
        "id_localidad": "LOC-005", "nombre_localidad": "Concepción",
        "nombre_normalizado": "concepcion", "region": "Junín", "provincia": "Concepción",
        "palabras_clave": "concepcion, heroica, valle del mantaro",
        "frase_contratacion": "¡Concepción, en el Valle del Mantaro! Buena tierra para celebrar 🎶",
        "frase_eventos": "Qué bueno que nos escribas desde Concepción.",
        "frase_general": "Concepción siempre presente.",
        "activo": "SI", "prioridad": "1", "fecha_actualizacion": "2026-06-01",
    },
]

sheets_client.seed_memory(SHEET_LOCALITIES, _DEFAULT_LOCALITIES)


def get_all_active() -> list[dict]:
    """Localidades con activo = SI, ordenadas por prioridad (asc)."""
    rows = [
        r for r in sheets_client.read_records(SHEET_LOCALITIES)
        if str(r.get("activo", "")).strip().upper() in ("SI", "SÍ", "TRUE", "1")
    ]

    def _prio(r):
        try:
            return int(str(r.get("prioridad", "99")).strip() or 99)
        except ValueError:
            return 99

    return sorted(rows, key=_prio)
