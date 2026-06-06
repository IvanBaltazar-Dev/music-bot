import json

from fastapi import APIRouter, Request, Query, HTTPException

from app.config import settings
from app.security import constant_time_equals, verify_meta_signature
from app.services.conversation_service import handle_incoming_message
from app.services import whatsapp_service

router = APIRouter(prefix="/webhook", tags=["WhatsApp Webhook"])


@router.get("")
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge")
):
    if (
        settings.VERIFY_TOKEN
        and hub_mode == "subscribe"
        and constant_time_equals(hub_verify_token, settings.VERIFY_TOKEN)
    ):
        return hub_challenge or ""

    raise HTTPException(status_code=403, detail="forbidden")


def _extract_phone_number_id(body: dict) -> str:
    """phone_number_id del número que RECIBIÓ el mensaje (value.metadata)."""
    try:
        value = body["entry"][0]["changes"][0]["value"]
        return str(value.get("metadata", {}).get("phone_number_id", "") or "")
    except Exception:  # noqa: BLE001
        return ""


def _extract_message(body: dict):
    """Devuelve (from_number, text, button_id, profile_name) o Nones si no aplica."""
    entry = body.get("entry", [])[0]
    changes = entry.get("changes", [])[0]
    value = changes.get("value", {})
    messages = value.get("messages", [])

    if not messages:
        return None, None, None, ""

    # Nombre del perfil de WhatsApp (si viene en contacts)
    profile_name = ""
    contacts = value.get("contacts", [])
    if contacts:
        profile_name = contacts[0].get("profile", {}).get("name", "") or ""

    message = messages[0]
    from_number = message.get("from")
    message_type = message.get("type")

    if message_type == "text":
        text = message.get("text", {}).get("body", "").strip()
        return from_number, text, "", profile_name

    if message_type == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return from_number, reply.get("title", ""), reply.get("id", ""), profile_name

    # Otros tipos (imagen, audio, etc.) no se procesan por ahora
    return from_number, "", "", profile_name


@router.post("")
async def receive_message(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_meta_signature(raw_body, signature, settings.WHATSAPP_APP_SECRET):
        print("[whatsapp] webhook rechazado por firma invalida")
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        body = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return {"status": "ignored", "reason": "invalid_body"}

    try:
        # Responder SIEMPRE desde el número que recibió el mensaje.
        pnid = _extract_phone_number_id(body)
        if pnid:
            whatsapp_service.set_active_phone_number_id(pnid)
            if settings.PHONE_NUMBER_ID and pnid != settings.PHONE_NUMBER_ID:
                print("[whatsapp] mensaje recibido en un phone_number_id distinto al configurado")

        from_number, text, button_id, profile_name = _extract_message(body)

        if not from_number or (not text and not button_id):
            return {"status": "ignored", "reason": "no_actionable_message"}

        await handle_incoming_message(
            from_number,
            text=text,
            button_id=button_id,
            profile_name=profile_name,
        )
        return {"status": "received"}

    except Exception as exc:
        # Nunca propagar errores: WhatsApp reintentaría el webhook.
        print(f"[whatsapp] error procesando webhook: {exc.__class__.__name__}")
        return {"status": "error"}
