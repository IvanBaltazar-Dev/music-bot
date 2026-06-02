"""Servicio de métricas.

Registra cada interacción relevante en la hoja `Metricas` y calcula un resumen
para administradores. Nunca rompe el flujo del webhook: cualquier fallo se ignora.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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


def format_summary(dias: int = 7) -> str:
    """Resumen operativo con KPIs para administradores (últimos `dias` días)."""
    try:
        metrics = metrics_repository.get_all()
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] no se pudo leer el resumen: {exc.__class__.__name__}")
        metrics = []

    desde = date.today() - timedelta(days=dias - 1)

    def _in_range(row) -> bool:
        d = _parse(row.get("fecha_hora", ""))
        return d is not None and d.date() >= desde

    rows = [m for m in metrics if _in_range(m)]

    # Si no hay nada en el rango, muéstralo claramente (en vez de puros ceros
    # que parecen un error).
    if not rows:
        return (
            "📊 Music Bot — últimos 7 días\n\n"
            "Todavía no hay actividad registrada en este periodo.\n\n"
            "Cuando los clientes empiecen a escribir, aquí verás usuarios, "
            "conversiones y cierres."
        )

    def _count(intent):
        return sum(1 for r in rows if r.get("intencion_detectada") == intent)

    usuarios = len({r.get("numero_usuario") for r in rows if r.get("numero_usuario")})
    saludos = _count(GREETING)
    contratos = _count(QUIERO_CONTRATAR)
    no_reconocidos = _count(UNKNOWN)
    cerradas = _count(ADMIN_CERRAR_SOLICITUD)
    cotizadas = _count(ADMIN_COTIZAR_SOLICITUD)
    descartadas = _count(ADMIN_DESCARTAR_SOLICITUD)

    # Base de conversión: usar saludos si existen; si no, usuarios únicos.
    base = saludos if saludos > 0 else usuarios
    atendidas = cerradas + cotizadas
    tasa_conversion = f"{int(100 * contratos / base)}%" if base > 0 else "—"
    tasa_cierre = f"{int(100 * cerradas / atendidas)}%" if atendidas > 0 else "—"
    tasa_abandono = f"{int(100 * no_reconocidos / base)}%" if base > 0 else "—"

    lineas = [
        "📊 Music Bot — últimos 7 días\n",
        f"👥 Usuarios: {usuarios}",
        f"👋 Saludos: {saludos}",
        f"🎤 Ver eventos: {_count(QUIERO_IR_A_VERLOS)}",
        f"🤝 Contratar: {contratos}",
        f"🎶 Conocer: {_count(CONOCE_AGRUPACION)}",
        f"📩 Intereses: {_count(INTERES_LOCALIDAD)}",
        f"❓ No reconocidos: {no_reconocidos}",
        "",
        "📈 KPIs:",
        f"  • Conversión: {tasa_conversion} (contratos/contactos)",
        f"  • Cierre: {tasa_cierre} (cerradas/atendidas)",
        f"  • Abandono: {tasa_abandono} (no reconocidos/contactos)",
        "",
        "🎯 Gestión:",
        f"  • Cerradas: {cerradas}",
        f"  • Cotizadas: {cotizadas}",
        f"  • Descartadas: {descartadas}",
    ]

    return "\n".join(lineas)
