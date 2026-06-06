from fastapi import FastAPI, Response, status

from app.routes.whatsapp_webhook import router as whatsapp_router

app = FastAPI(title="Music Bot WhatsApp API")

app.include_router(whatsapp_router)


@app.on_event("startup")
def _on_startup():
    """Crea las hojas faltantes con sus encabezados (sin borrar datos).

    Tolerante a fallos: si Sheets no está habilitado, no hace nada.
    """
    try:
        from app.repositories.sheets_client import ensure_sheets
        resumen = ensure_sheets()
        print(f"[startup] hojas: {resumen}")
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] no se pudieron inicializar hojas: {exc.__class__.__name__}")


@app.get("/")
def root():
    """Estado básico del servicio (para verificación rápida)."""
    return {
        "status": "ok",
        "service": "Music Bot WhatsApp API",
        "message": "Music Bot API funcionando",
    }


@app.get("/health")
def health(response: Response):
    """Healthcheck de producción sin exponer configuración sensible."""
    from app.config import settings

    ready = settings.production_health_ready
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "healthy" if ready else "unhealthy",
        "ready": ready,
    }
