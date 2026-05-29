"""Servicio de IA (Gemini) como fallback.

La IA es **completamente opcional** y actúa como último recurso:
1. Primero: reglas + normalización
2. Luego: coincidencia aproximada (difflib)
3. Finalmente: IA (si está habilitada)
4. Si IA falla: menú con botones

El bot **nunca depende** de IA. Si está deshabilitada, no instalada, o la API
falla, el sistema degrada gracefully a memoria/reglas.

Nunca se imprimen tokens. Nunca se envía IA al usuario directo.
"""

from __future__ import annotations

import json
from typing import Optional

from app.config import settings

_client = None
_enabled = False


def _init_client():
    """Inicialización perezosa de Gemini (sin romper si falla)."""
    global _client, _enabled

    if not settings.AI_ENABLED:
        print("[ai] deshabilitado (AI_ENABLED=false).")
        return

    if not settings.GEMINI_API_KEY:
        print("[ai] deshabilitado (GEMINI_API_KEY no configurado).")
        return

    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=settings.GEMINI_API_KEY)
        _client = genai.GenerativeModel(settings.AI_MODEL)
        _enabled = True
        print(f"[ai] inicializado con {settings.AI_MODEL}.")
    except ModuleNotFoundError:
        print(
            "[ai] librería google-generativeai no instalada. Usando solo reglas.\n"
            "    Para activar IA: pip install google-generativeai"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ai] no se pudo inicializar ({exc.__class__.__name__}). Usando solo reglas.")


_init_client()


def is_enabled() -> bool:
    """True si la IA está habilitada y disponible."""
    return _enabled


def classify_intent(text: str) -> dict:
    """Clasifica una intención ambigua usando IA.

    Devuelve:
        {
            "success": True/False,
            "intent": "greeting|events|price|contact|unknown",
            "confidence": 0.0-1.0,
            "reason": "explicación breve"
        }

    Si falla o no está habilitada, devuelve success=False.
    """
    if not _enabled or not _client:
        return {"success": False, "reason": "IA no habilitada"}

    try:
        prompt = (
            "Eres un clasificador de intenciones para un chatbot de una agrupación musical.\n"
            "Clasifica el siguiente mensaje en una de estas categorías:\n"
            "- greeting (saludo)\n"
            "- events (preguntas sobre próximos eventos/conciertos)\n"
            "- price (solicitud de precio, cotización o contratación)\n"
            "- contact (solicitud de contacto con el equipo)\n"
            "- unknown (no encaja en ninguna)\n\n"
            f"Mensaje: {text}\n\n"
            'Devuelve SOLO un JSON válido (sin markdown) con:\n'
            '{"intent": "...", "confidence": 0.0-1.0, "reason": "..."}'
        )

        response = _client.generate_content(prompt)
        result = json.loads(response.text)

        intent = result.get("intent", "unknown")
        if intent not in ("greeting", "events", "price", "contact", "unknown"):
            intent = "unknown"

        confidence = float(result.get("confidence", 0.5))
        reason = result.get("reason", "")

        return {
            "success": True,
            "intent": intent,
            "confidence": min(1.0, max(0.0, confidence)),
            "reason": reason,
        }

    except json.JSONDecodeError:
        return {"success": False, "reason": "respuesta IA no es JSON válido"}
    except Exception as exc:  # noqa: BLE001
        print(f"[ai] error en classify_intent: {exc.__class__.__name__}")
        return {"success": False, "reason": f"error de IA: {exc.__class__.__name__}"}


def extract_quotation_data(text: str) -> dict:
    """Extrae datos de una solicitud de cotización (ubicación, fecha, etc.).

    Devuelve:
        {
            "success": True/False,
            "extracted": {
                "location": "...",
                "date": "...",
                "event_type": "...",
                "duration": "...",
                ...
            },
            "confidence": 0.0-1.0
        }

    Si no hay datos relevantes, "extracted" está vacío.
    """
    if not _enabled or not _client:
        return {"success": False, "extracted": {}, "confidence": 0.0}

    try:
        prompt = (
            "Eres un extractor de datos para un chatbot de agrupaciones musicales.\n"
            "Extrae la siguiente información del mensaje, si está disponible:\n"
            "- location: ciudad o distrito del evento\n"
            "- date: fecha (en cualquier formato mencionado)\n"
            "- event_type: tipo de evento (cumpleaños, boda, corporativo, etc.)\n"
            "- duration: duración o cantidad de horas\n"
            "- name: nombre del solicitante\n"
            "- contact: teléfono u otro contacto\n\n"
            f"Mensaje: {text}\n\n"
            'Devuelve SOLO un JSON válido (sin markdown) con:\n'
            '{"extracted": {"location": "...", "date": "...", ...}, "confidence": 0.0-1.0}\n'
            'Los campos faltantes pueden ser null.'
        )

        response = _client.generate_content(prompt)
        result = json.loads(response.text)

        extracted = result.get("extracted", {})
        confidence = float(result.get("confidence", 0.5))

        return {
            "success": True,
            "extracted": extracted or {},
            "confidence": min(1.0, max(0.0, confidence)),
        }

    except json.JSONDecodeError:
        return {"success": False, "extracted": {}, "confidence": 0.0}
    except Exception as exc:  # noqa: BLE001
        print(f"[ai] error en extract_quotation_data: {exc.__class__.__name__}")
        return {"success": False, "extracted": {}, "confidence": 0.0}


def validate_and_enhance_quotation(state: str, current_data: dict, user_text: str) -> Optional[dict]:
    """Usa IA para interpretar una respuesta ambigua en un flujo de cotización.

    Útil cuando el usuario responde algo corto o poco claro.
    Devuelve un dict con campos pre-extraídos del estado actual, o None si no ayuda.

    Ejemplo:
        state = "quotation_date"
        user_text = "mañana a las 8"
        -> extrae y devuelve {"date": "mañana", "time": "8:00 PM"}
    """
    if not _enabled or not _client:
        return None

    state_labels = {
        "quotation_location": "ciudad/distrito",
        "quotation_date": "fecha",
        "quotation_event_type": "tipo de evento",
        "quotation_duration": "duración en horas",
        "quotation_name": "nombre",
        "quotation_contact": "contacto/teléfono",
    }

    label = state_labels.get(state, "")
    if not label:
        return None

    try:
        prompt = (
            f"Extrae el valor de '{label}' del siguiente mensaje.\n"
            f"Responde SOLO con el valor extraído, sin explicaciones ni formato adicional.\n"
            f"Si no hay información relevante, responde 'NO_ENCONTRADO'.\n\n"
            f"Mensaje: {user_text}"
        )

        response = _client.generate_content(prompt)
        value = response.text.strip()

        if value and value != "NO_ENCONTRADO":
            return {state: value}
        return None

    except Exception as exc:  # noqa: BLE001
        print(f"[ai] error en validate_and_enhance_quotation: {exc.__class__.__name__}")
        return None
