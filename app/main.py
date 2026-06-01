from fastapi import FastAPI

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
def health():
    """Healthcheck para monitoreo/uptime (Oracle Cloud, balanceadores, etc.)."""
    from app.config import settings
    from app.repositories import sheets_client

    return {
        "status": "healthy",
        "whatsapp": bool(settings.WHATSAPP_TOKEN and settings.PHONE_NUMBER_ID),
        "google_sheets": sheets_client.is_enabled(),
        "gemini": settings.gemini_enabled,
    }
