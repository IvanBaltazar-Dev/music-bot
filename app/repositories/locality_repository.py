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
        "frase_contratacion": "¡Nuestra tierra huanca! La Ciudad Incontrastable siempre sabe celebrar bonito 🙌🎶",
        "frase_eventos": "¡Huancayo es casa! 🙌🎶 Qué bonito saber que nos escribes desde ahí.",
        "frase_general": "Nuestra tierra huanca siempre se hace presente 🙌🎶",
        "activo": "SI", "prioridad": "1", "fecha_actualizacion": "2026-06-01",
    },
    {
        "id_localidad": "LOC-002", "nombre_localidad": "Tarma",
        "nombre_normalizado": "tarma", "region": "Junín", "provincia": "Tarma",
        "palabras_clave": "tierra de las flores, flores, tarmeño, tarmeña",
        "frase_contratacion": "¡Tarma, la tierra de las flores! 🌸 Ya suena a celebración bonita.",
        "frase_eventos": "¡Tarma presente! 🌸 Qué bonito saber que nos escribes desde la tierra de las flores.",
        "frase_general": "Tarma siempre tiene ese encanto especial de la tierra de las flores 🌸",
        "activo": "SI", "prioridad": "1", "fecha_actualizacion": "2026-06-01",
    },
    {
        "id_localidad": "LOC-003", "nombre_localidad": "Lima",
        "nombre_normalizado": "lima", "region": "Lima", "provincia": "Lima",
        "palabras_clave": "lima capital, capital, todos salen adelante",
        "frase_contratacion": "¡Lima capital! Donde todos salen adelante y siempre hay motivo para celebrar 🙌",
        "frase_eventos": "¡Lima presente! 🙌🎶 Qué bueno saber que nos escribes desde la capital.",
        "frase_general": "Lima capital siempre tiene algo bonito por celebrar 🙌",
        "activo": "SI", "prioridad": "1", "fecha_actualizacion": "2026-06-01",
    },
    {
        "id_localidad": "LOC-004", "nombre_localidad": "Jauja",
        "nombre_normalizado": "jauja", "region": "Junín", "provincia": "Jauja",
        "palabras_clave": "jauja querida, primera capital, aire bonito",
        "frase_contratacion": "¡Jauja querida! Con ese aire bonito y su gente alegre, el evento ya va tomando forma 🎶",
        "frase_eventos": "¡Jauja querida! 🙌🎶 Qué alegría saber que nos escribes desde ahí.",
        "frase_general": "Jauja querida siempre se siente con alegría 🙌🎶",
        "activo": "SI", "prioridad": "1", "fecha_actualizacion": "2026-06-01",
    },
    {
        "id_localidad": "LOC-005", "nombre_localidad": "Concepción",
        "nombre_normalizado": "concepcion", "region": "Junín", "provincia": "Concepción",
        "palabras_clave": "concepcion, heroica, valle del mantaro",
        "frase_contratacion": "¡Concepción! Tierra bonita del Valle del Mantaro, ya va tomando forma esa celebración 🙌🎶",
        "frase_eventos": "¡Concepción presente! 🙌 Qué bonito saber que nos escribes desde ahí.",
        "frase_general": "Concepción siempre se hace presente con cariño 🙌",
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
