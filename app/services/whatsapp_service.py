"""Cliente de la WhatsApp Cloud API.

Envía mensajes de texto y mensajes con botones interactivos. Toda llamada de red
está protegida: un fallo de la API NUNCA debe romper el webhook. No se imprimen
tokens en consola bajo ninguna circunstancia.
"""

import httpx

from app.config import settings


def _base_url() -> str:
    return (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
        f"{settings.PHONE_NUMBER_ID}/messages"
    )


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
            # Importante: NO imprimir headers/tokens, solo el cuerpo de error de la API.
            print(f"[whatsapp] error {response.status_code}: {response.text}")
            return None
        return response.json()
    except Exception as exc:  # noqa: BLE001 - el webhook no debe caerse por la red
        print(f"[whatsapp] fallo de red: {exc.__class__.__name__}")
        return None


async def send_whatsapp_message(to: str, message: str):
    """Compatibilidad con la implementación original (envío de texto)."""
    return await send_text_message(to, message)


async def send_text_message(to: str, message: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
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
        "to": to,
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
