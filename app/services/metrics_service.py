"""Servicio de métricas.

Registra cada interacción relevante en la hoja `Metricas` y calcula un resumen
para administradores. Nunca rompe el flujo del webhook: cualquier fallo se ignora.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.repositories import metrics_repository

# Intenciones (referencia / documentación)
GREETING = "GREETING"
QUIERO_IR_A_VERLOS = "QUIERO_IR_A_VERLOS"
QUIERO_CONTRATAR = "QUIERO_CONTRATAR"
CONOCE_AGRUPACION = "CONOCE_AGRUPACION"
VER_VIDEOS = "VER_VIDEOS"
ESCUCHAR_MUSICA = "ESCUCHAR_MUSICA"
REDES_SOCIALES = "REDES_SOCIALES"
PROXIMAS_PRESENTACIONES = "PROXIMAS_PRESENTACIONES"
CONSULTA_PRECIO = "CONSULTA_PRECIO"
CONSULTA_ENTRADAS = "CONSULTA_ENTRADAS"
CONSULTA_UBICACION = "CONSULTA_UBICACION"
INTERES_LOCALIDAD = "INTERES_LOCALIDAD"
ADMIN_TOMAR_CONTROL = "ADMIN_TOMAR_CONTROL"
ADMIN_SEGUIMIENTO = "ADMIN_SEGUIMIENTO"
ADMIN_CERRAR_SOLICITUD = "ADMIN_CERRAR_SOLICITUD"
ADMIN_COTIZAR_SOLICITUD = "ADMIN_COTIZAR_SOLICITUD"
ADMIN_DESCARTAR_SOLICITUD = "ADMIN_DESCARTAR_SOLICITUD"
GEMINI_USED = "GEMINI_USED"
ERROR = "ERROR"
UNKNOWN = "UNKNOWN"


def log(
    numero_usuario: str,
    intencion: str = "",
    flujo: str = "",
    paso: str = "",
    ciudad: str = "",
    opcion: str = "",
    mensaje: str = "",
    respuesta: str = "",
    codigo_solicitud: str = "",
    id_evento: str = "",
) -> None:
    """Registra una métrica de forma segura (no propaga errores)."""
    try:
        metrics_repository.save({
            "numero_usuario": numero_usuario or "",
            "intencion_detectada": intencion or "",
            "flujo": flujo or "",
            "paso": paso or "",
            "ciudad_mencionada": ciudad or "",
            "opcion_elegida": opcion or "",
            "mensaje_usuario": (mensaje or "")[:300],
            "respuesta_bot": (respuesta or "")[:300],
            "codigo_solicitud": codigo_solicitud or "",
            "id_evento": id_evento or "",
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] no se pudo registrar '{intencion}': {exc.__class__.__name__}")


def _parse(dt_str: str):
    try:
        d = datetime.fromisoformat(str(dt_str))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:  # noqa: BLE001
        return None


def format_summary() -> str:
    """Resumen operativo cálido para administradores."""
    try:
        metrics = metrics_repository.get_all()
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] no se pudo leer el resumen: {exc.__class__.__name__}")
        metrics = []

    today = date.today()
    today_rows = [m for m in metrics if (_parse(m.get("fecha_hora", "")) or datetime.min.replace(tzinfo=timezone.utc)).date() == today]

    def _count(rows, intent):
        return sum(1 for r in rows if r.get("intencion_detectada") == intent)

    usuarios_hoy = len({r.get("numero_usuario") for r in today_rows if r.get("numero_usuario")})

    return (
        "📊 Resumen de Music Bot (hoy)\n\n"
        f"👥 Usuarios únicos: {usuarios_hoy}\n"
        f"👋 Saludos: {_count(today_rows, GREETING)}\n"
        f"🎤 Quiero ir a verlos: {_count(today_rows, QUIERO_IR_A_VERLOS)}\n"
        f"🤝 Quiero contratarlos: {_count(today_rows, QUIERO_CONTRATAR)}\n"
        f"🎶 Conoce la agrupación: {_count(today_rows, CONOCE_AGRUPACION)}\n"
        f"📩 Intereses de localidad: {_count(today_rows, INTERES_LOCALIDAD)}\n"
        f"❓ No reconocidos: {_count(today_rows, UNKNOWN)}\n\n"
        f"Total de interacciones registradas: {len(metrics)}"
    )
