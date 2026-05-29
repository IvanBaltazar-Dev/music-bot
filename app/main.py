from fastapi import FastAPI
from app.routes.whatsapp_webhook import router as whatsapp_router

app = FastAPI(title="Music Bot WhatsApp API")

app.include_router(whatsapp_router)


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "message": "Music Bot API funcionando"
    }