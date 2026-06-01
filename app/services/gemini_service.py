"""Servicio de Gemini (respaldo inteligente).

Gemini es un FALLBACK, no el cerebro del bot. El orden siempre es:
1. Reglas + intents + fuzzy matching + estados de conversación + Google Sheets.
2. Gemini solo si: la intención es UNKNOWN, el usuario pregunta algo general no
   cubierto por reglas, o se necesita redactar una respuesta natural con datos
   disponibles.

Garantías:
* El bot funciona perfectamente SIN Gemini (deshabilitado, sin key o si falla).
* Nunca se imprimen tokens. Se envía contexto controlado, no historial crudo.
* Si Gemini falla, se devuelve None y el llamador usa un fallback seguro.

Compatibilidad: respeta las variables existentes (AI_ENABLED/AI_MODEL) y soporta
las nuevas (GEMINI_ENABLED/GEMINI_MODEL). Ver `config.gemini_enabled`.
"""

from __future__ import annotations

import json

from app.config import settings

_client = None
_enabled = False

# Categorías que Gemini puede devolver (coinciden con las intenciones del bot).
_VALID_INTENTS = {
    "GREETING", "QUIERO_IR_A_VERLOS", "QUIERO_CONTRATAR",
    "CONOCE_AGRUPACION", "UNKNOWN",
}


def _init_client():
    """Inicialización perezosa de Gemini (tolerante a fallos)."""
    global _client, _enabled

    if not settings.gemini_enabled:
        print("[gemini] deshabilitado (sin GEMINI_API_KEY o *_ENABLED=false).")
        return

    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=settings.GEMINI_API_KEY)
        _client = genai.GenerativeModel(settings.gemini_model)
        _enabled = True
        print(f"[gemini] inicializado con {settings.gemini_model}.")
    except ModuleNotFoundError:
        print("[gemini] librería google-generativeai no instalada. Usando solo reglas.")
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] no se pudo inicializar ({exc.__class__.__name__}). Usando solo reglas.")


_init_client()


def is_enabled() -> bool:
    return _enabled


def classify_intent(text: str) -> dict:
    """Clasifica una intención ambigua. Devuelve {success, intent, confidence}.

    `intent` es una de las categorías del bot (GREETING / QUIERO_IR_A_VERLOS /
    QUIERO_CONTRATAR / CONOCE_AGRUPACION / UNKNOWN). success=False si Gemini no
    está disponible o falla.
    """
    if not _enabled or not _client:
        return {"success": False}

    try:
        prompt = (
            "Eres un clasificador de intenciones para el WhatsApp de una agrupación "
            "musical. Clasifica el mensaje del usuario en EXACTAMENTE una categoría:\n"
            "- GREETING: saludos o inicio de conversación.\n"
            "- QUIERO_IR_A_VERLOS: quiere asistir, pregunta por eventos, fechas, "
            "lugares, entradas o presentaciones.\n"
            "- QUIERO_CONTRATAR: quiere contratar, cotizar o llevar la agrupación a "
            "su evento (cumpleaños, boda, aniversario, etc.).\n"
            "- CONOCE_AGRUPACION: quiere conocer a la agrupación, videos, música, "
            "redes, integrantes o trayectoria.\n"
            "- UNKNOWN: no encaja claramente en ninguna.\n\n"
            f"Mensaje: {text}\n\n"
            'Responde SOLO un JSON válido sin markdown: '
            '{"intent": "...", "confidence": 0.0-1.0}'
        )
        response = _client.generate_content(prompt)
        result = json.loads(_strip_json(response.text))
        intent = str(result.get("intent", "UNKNOWN")).upper()
        if intent not in _VALID_INTENTS:
            intent = "UNKNOWN"
        confidence = float(result.get("confidence", 0.5))
        return {
            "success": True,
            "intent": intent,
            "confidence": min(1.0, max(0.0, confidence)),
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] error en classify_intent: {exc.__class__.__name__}")
        return {"success": False}


def generate_reply(user_text: str, contexto: str = "") -> str | None:
    """Redacta una respuesta natural y breve usando contexto controlado.

    Se usa solo cuando las reglas no cubren el mensaje. Devuelve el texto o None
    si Gemini no está disponible o falla (el llamador usa un fallback seguro).
    """
    if not _enabled or not _client:
        return None

    try:
        prompt = (
            "Eres el asistente oficial de WhatsApp de una agrupación musical. "
            "Hablas de forma cercana, profesional y natural; NADA excesivamente "
            "formal, sin bromas ni chistes.\n"
            "Reglas estrictas:\n"
            "- No inventes precios, fechas, lugares ni datos que no estén en el "
            "contexto.\n"
            "- El bot NO evalúa ni decide contrataciones; solo orienta y deriva al "
            "administrador.\n"
            "- No menciones el nombre de la agrupación en cada frase.\n"
            "- Responde en 1-3 frases cortas y, si aplica, sugiere amablemente una "
            "de estas acciones: ver presentaciones, contratar, o conocer a la "
            "agrupación.\n\n"
            f"Contexto disponible:\n{contexto or '(sin datos adicionales)'}\n\n"
            f"Mensaje del usuario: {user_text}\n\n"
            "Respuesta (texto plano, sin markdown):"
        )
        response = _client.generate_content(prompt)
        reply = (response.text or "").strip()
        return reply or None
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] error en generate_reply: {exc.__class__.__name__}")
        return None


def _strip_json(text: str) -> str:
    """Quita posibles cercos ```json ... ``` de la respuesta del modelo."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    return t.strip()
