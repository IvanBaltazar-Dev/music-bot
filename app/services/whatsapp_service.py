"""Cliente de la WhatsApp Cloud API.

Envía mensajes de texto y mensajes con botones interactivos. Toda llamada de red
está protegida: un fallo de la API NUNCA debe romper el webhook. No se imprimen
tokens en consola bajo ninguna circunstancia.
"""

import contextvars

import httpx

from app.config import settings
from app.security import mask_identifier, sanitize_text

# Número (phone_number_id) que RECIBIÓ el mensaje en curso. El webhook lo fija
# por cada request para que el bot responda DESDE ese mismo número y no desde uno
# fijo del .env. ContextVar = aislado por request (seguro en async).
_phone_number_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "wa_phone_number_id", default=""
)


def set_active_phone_number_id(phone_number_id: str) -> None:
    """Fija el número emisor para la request actual (lo llama el webhook)."""
    if phone_number_id:
        _phone_number_id_ctx.set(str(phone_number_id))


def _active_phone_number_id() -> str:
    """Número emisor: el que recibió el mensaje; si no, el del .env."""
    return _phone_number_id_ctx.get() or settings.PHONE_NUMBER_ID


def _base_url() -> str:
    return (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
        f"{_active_phone_number_id()}/messages"
    )


def _normalize_recipient(to: str) -> str:
    """Asegura que el destinatario tenga código de país.

    Los números nacionales (Perú: 9 dígitos) no son entregables por WhatsApp sin
    el código de país. Si falta, se antepone DEFAULT_COUNTRY_CODE. Los números
    que ya lo traen (>= 10 dígitos o que ya empiezan con el código) no se tocan.
    """
    digits = "".join(ch for ch in str(to or "") if ch.isdigit())
    cc = (settings.DEFAULT_COUNTRY_CODE or "").strip()
    if cc and digits and not digits.startswith(cc) and len(digits) <= 9:
        return cc + digits
    return digits


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


async def _post(payload: dict):
    """POST seguro hacia la API de WhatsApp. Devuelve dict o None si falla."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(_base_url(), headers=_headers(), json=payload)
        if response.status_code >= 400:
            recipient = mask_identifier(payload.get("to", ""))
            detail = sanitize_text(response.text, limit=400)
            print(
                f"[whatsapp] send_failed status={response.status_code} "
                f"to={recipient} type={payload.get('type', '')} detail={detail}"
            )
            return None
        result = response.json()
        message_id = ""
        if isinstance(result, dict):
            messages = result.get("messages") or []
            if messages and isinstance(messages[0], dict):
                message_id = mask_identifier(messages[0].get("id", ""), visible=8)
        print(
            f"[whatsapp] send_ok to={mask_identifier(payload.get('to', ''))} "
            f"type={payload.get('type', '')} message={message_id or '-'}"
        )
        return result
    except Exception as exc:  # noqa: BLE001 - el webhook no debe caerse por la red
        print(f"[whatsapp] fallo de red: {exc.__class__.__name__}")
        return None


async def send_whatsapp_message(to: str, message: str):
    """Compatibilidad con la implementación original (envío de texto)."""
    return await send_text_message(to, message)


async def send_text_message(to: str, message: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_recipient(to),
        "type": "text",
        "text": {"body": message},
    }
    return await _post(payload)


async def send_template_message(
    to: str,
    template_name: str,
    parameters: list[str],
    language: str = "es_PE",
):
    """Envía una plantilla aprobada por Meta con variables de cuerpo."""
    if not template_name:
        return None
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_recipient(to),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language or "es_PE"},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(value or "-")[:1000]}
                    for value in parameters
                ],
            }],
        },
    }
    return await _post(payload)


async def send_button_message(to: str, body: str, buttons: list[dict]):
    """Envía un mensaje con botones rápidos.

    buttons: lista de dicts {"id": "...", "title": "..."} (máx. 3, títulos <= 20 chars).
    Si algo falla, hace fallback a un mensaje de texto para no perder la respuesta.
    """
    reply_buttons = [
        {
            "type": "reply",
            "reply": {"id": b["id"], "title": b["title"][:20]},
        }
        for b in buttons[:3]
    ]

    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_recipient(to),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": reply_buttons},
        },
    }

    result = await _post(payload)
    if result is None:
        # Fallback: enviar el cuerpo como texto plano para no dejar al usuario sin respuesta.
        return await send_text_message(to, body)
    return result


async def send_list_message(
    to: str,
    body: str,
    options: list[dict],
    button_text: str = "Ver opciones",
    header: str | None = None,
):
    """Envía un menú tipo lista (hasta 10 opciones).

    options: lista de dicts {"id": "...", "title": "...", "description": "..."}.
    Útil cuando hay más de 3 opciones (los botones rápidos solo permiten 3).
    Si falla, hace fallback a botones (3) o a texto.
    """
    rows = []
    for o in options[:10]:
        row = {"id": o["id"], "title": o["title"][:24]}
        desc = o.get("description")
        if desc:
            row["description"] = desc[:72]
        rows.append(row)

    interactive: dict = {
        "type": "list",
        "body": {"text": body},
        "action": {
            "button": button_text[:20],
            "sections": [{"title": "Opciones", "rows": rows}],
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header[:60]}

    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_recipient(to),
        "type": "interactive",
        "interactive": interactive,
    }

    result = await _post(payload)
    if result is None:
        # Fallback a botones (máx. 3) y, si también falla, a texto.
        return await send_button_message(to, body, options[:3])
    return result
