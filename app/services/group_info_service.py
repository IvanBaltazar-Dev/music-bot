"""Servicio "Conoce la agrupación".

Arma las respuestas del flujo de presentación leyendo videos, canciones y redes
desde la hoja `ContenidosAgrupacion`. No se inventan enlaces: si no hay contenido
de cierto tipo, ese botón/sección no se ofrece.
"""

from __future__ import annotations

from app.repositories import content_repository as content

# Texto por defecto de "¿Quiénes son?" si no hay descripción en la hoja.
_DEFAULT_QUIENES_SON = (
    "Somos una agrupación que lleva música, alegría y sentimiento a cada "
    "presentación 🎶\n\n"
    "Nos gusta que cada evento se sienta cercano, animado y con ese toque especial "
    "que hace que la gente cante, baile y se quede con un bonito recuerdo.\n\n"
    "¿Quieres ver un video o prefieres escuchar un poquito de nuestra música?"
)

_RED_LABEL = {
    "FACEBOOK": "Facebook",
    "TIKTOK": "TikTok",
    "YOUTUBE": "YouTube",
    "INSTAGRAM": "Instagram",
}


def has_videos() -> bool:
    return bool(content.by_type(content.VIDEO))


def has_music() -> bool:
    return bool(content.by_type(content.CANCION))


def has_redes() -> bool:
    return bool(content.get_redes())


def quienes_son_text() -> str:
    desc = content.get_description()
    return desc or _DEFAULT_QUIENES_SON


def _format_links(rows: list[dict]) -> str:
    bloques = []
    for r in rows:
        titulo = str(r.get("titulo", "")).strip()
        url = str(r.get("url", "")).strip()
        if not url:
            continue
        bloques.append(f"• {titulo}\n{url}" if titulo else f"• {url}")
    return "\n\n".join(bloques)


def videos_text() -> str:
    cabecera = (
        "¡De una! Los videos hablan mejor que mil palabras 🎶😄\n\n"
        "Te dejo algunos para que veas el ambiente, la música y cómo se viven "
        "las presentaciones:\n\n"
    )
    return cabecera + _format_links(content.by_type(content.VIDEO))


def music_text() -> str:
    cabecera = (
        "¡Claro! Para conocer a una agrupación, primero hay que escucharla 🎶🙌\n\n"
        "Te dejo por aquí algunas canciones o presentaciones:\n\n"
    )
    return cabecera + _format_links(content.by_type(content.CANCION))


def redes_text() -> str:
    cabecera = (
        "¡Sí, claro! Por ahí también puedes ver novedades, videos y próximas "
        "presentaciones 🙌🎶\n\n"
        "Te dejo nuestras redes:\n\n"
    )
    bloques = []
    for r in content.get_redes():
        url = str(r.get("url", "")).strip()
        if not url:
            continue
        tipo = str(r.get("tipo", "")).strip().upper()
        label = _RED_LABEL.get(tipo, tipo.title())
        bloques.append(f"• {label}: {url}")
    return cabecera + "\n".join(bloques)
