from fastapi import APIRouter, Request, Query, HTTPException
from app.config import settings
from app.services.whatsapp_service import send_text_message
from app.services.intent_service import get_bot_response

router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])


@router.get("")
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge")
):
    if hub_mode == "subscribe" and hub_verify_token == settings.verify_token:
        return int(hub_challenge)

    raise HTTPException(status_code=403, detail="Token inválido")


@router.post("")
async def receive_message(request: Request):
    body = await request.json()

    print("Webhook recibido:")
    print(body)

    try:
        entry = body.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ignored", "reason": "no_messages"}

        message = messages[0]
        from_number = message.get("from")
        message_type = message.get("type")

        if message_type == "text":
            text = message.get("text", {}).get("body", "").strip()

            response_text = get_bot_response(text)

            await send_text_message(
                to=from_number,
                message=response_text
            )

        return {"status": "received"}

    except Exception as e:
        print("Error procesando webhook:", e)
        return {"status": "error", "detail": str(e)}