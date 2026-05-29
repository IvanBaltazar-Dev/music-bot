from fastapi import APIRouter, Request, Query, HTTPException

from app.config import settings
from app.services.conversation_service import handle_incoming_message

router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])


@router.get("")
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge")
):
    if hub_mode == "subscribe" and hub_verify_token == settings.VERIFY_TOKEN:
        return int(hub_challenge)

    raise HTTPException(status_code=403, detail="Token inválido")


def _extract_message(body: dict):
    """Devuelve (from_number, text, button_id) o (None, None, None) si no aplica."""
    entry = body.get("entry", [])[0]
    changes = entry.get("changes", [])[0]
    value = changes.get("value", {})
    messages = value.get("messages", [])

    if not messages:
        return None, None, None

    message = messages[0]
    from_number = message.get("from")
    message_type = message.get("type")

    if message_type == "text":
        text = message.get("text", {}).get("body", "").strip()
        return from_number, text, ""

    if message_type == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return from_number, reply.get("title", ""), reply.get("id", "")

    # Otros tipos (imagen, audio, etc.) no se procesan por ahora
    return from_number, "", ""


@router.post("")
async def receive_message(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid_body"}

    try:
        from_number, text, button_id = _extract_message(body)

        if not from_number or (not text and not button_id):
            return {"status": "ignored", "reason": "no_actionable_message"}

        await handle_incoming_message(from_number, text=text, button_id=button_id)
        return {"status": "received"}

    except Exception as e:
        # Nunca propagar errores: WhatsApp reintentaría el webhook.
        print("Error procesando webhook:", e)
        return {"status": "error", "detail": str(e)}
