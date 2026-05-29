import httpx
from app.config import settings


async def send_whatsapp_message(to: str, message: str):
    url = (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
        f"{settings.PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": message
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code >= 400:
        print("Error enviando mensaje a WhatsApp:")
        print(response.status_code)
        print(response.text)

    return response.json()


async def send_text_message(to: str, message: str):
    return await send_whatsapp_message(to, message)