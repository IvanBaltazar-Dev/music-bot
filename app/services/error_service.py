"""Servicio de errores.

Registra errores en la hoja `Errores` y, ante fallos graves, notifica a los
administradores. Nunca propaga excepciones: es la última línea de defensa.
"""

from __future__ import annotations

import traceback

from app.repositories import error_repository
from app.services.whatsapp_service import send_text_message


async def log_error(modulo: str, exc: BaseException, numero_usuario: str = "",
                    mensaje_usuario: str = "", notify: bool = True) -> None:
    """Guarda el error y opcionalmente avisa a los administradores."""
    error_text = f"{exc.__class__.__name__}: {exc}"
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[:1500]

    try:
        error_repository.save({
            "modulo": modulo,
            "numero_usuario": numero_usuario,
            "mensaje_usuario": (mensaje_usuario or "")[:300],
            "error": error_text,
            "stacktrace": stack,
        })
    except Exception:  # noqa: BLE001
        pass

    if not notify:
        return

    # Import perezoso para evitar dependencias circulares.
    try:
        from app.services import admin_service
        admins = admin_service.admin_numbers()
    except Exception:  # noqa: BLE001
        admins = []

    aviso = (
        "⚠️ Error en Music Bot\n\n"
        f"Módulo: {modulo}\n"
        f"Usuario: {numero_usuario or '-'}\n"
        f"Mensaje: {mensaje_usuario or '-'}\n\n"
        "Revisar logs."
    )
    for admin in admins:
        try:
            await send_text_message(admin, aviso)
        except Exception:  # noqa: BLE001
            pass
