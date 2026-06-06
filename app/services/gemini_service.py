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
import time

from app.config import settings
from app.security import sanitize_text

_client = None
_enabled = False
_cooldown_until = 0.0
_COOLDOWN_SECONDS = 300

# Categorías que Gemini puede devolver (coinciden con las intenciones del bot).
_VALID_INTENTS = {
    "GREETING", "QUIERO_IR_A_VERLOS", "QUIERO_CONTRATAR",
    "CONOCE_AGRUPACION", "CONTACTO", "FUERA_DE_TEMA", "DESPEDIDA", "UNKNOWN",
}


def _init_client():
    """Inicialización perezosa de Gemini (tolerante a fallos).

    Usa el SDK nuevo `google-genai` (import `from google import genai`).
    """
    global _client, _enabled

    if not settings.gemini_enabled:
        print("[gemini] deshabilitado (sin GEMINI_API_KEY o *_ENABLED=false).")
        return

    try:
        from google import genai  # type: ignore

        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
        _enabled = True
        print(f"[gemini] inicializado con {settings.gemini_model}.")
    except ModuleNotFoundError:
        print("[gemini] librería google-genai no instalada. Usando solo reglas.")
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] no se pudo inicializar ({exc.__class__.__name__}). Usando solo reglas.")


def _generate(prompt: str) -> str:
    """Llama al modelo y devuelve el texto. Lanza si falla (lo maneja el caller)."""
    global _cooldown_until
    try:
        response = _client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
    except Exception as exc:
        detail = sanitize_text(exc, limit=300)
        code = getattr(exc, "code", None)
        if code == 429 or "429" in detail or "RESOURCE_EXHAUSTED" in detail:
            _cooldown_until = time.monotonic() + _COOLDOWN_SECONDS
            print(
                f"[gemini] cuota/rate limit; pausa de {_COOLDOWN_SECONDS}s. "
                f"detail={detail}"
            )
        raise
    return (response.text or "").strip()


_init_client()


def is_enabled() -> bool:
    return _enabled and time.monotonic() >= _cooldown_until


def classify_intent(text: str) -> dict:
    """Clasifica una intención ambigua. Devuelve {success, intent, confidence}.

    `intent` es una de las categorías del bot (GREETING / QUIERO_IR_A_VERLOS /
    QUIERO_CONTRATAR / CONOCE_AGRUPACION / UNKNOWN). success=False si Gemini no
    está disponible o falla.
    """
    if not is_enabled() or not _client:
        return {"success": False}

    try:
        prompt = (
            "Eres un CLASIFICADOR de intenciones para el WhatsApp de una agrupación "
            "musical. Tu ÚNICA tarea es clasificar; NO respondas la pregunta del "
            "usuario ni des información. Devuelve EXACTAMENTE una categoría:\n"
            "- GREETING: solo un saludo, sin una consulta concreta.\n"
            "- QUIERO_IR_A_VERLOS: pregunta por eventos, fechas, lugares, entradas o "
            "presentaciones a las que quiere asistir.\n"
            "- QUIERO_CONTRATAR: quiere contratar/cotizar o llevar la agrupación a su "
            "evento (cumpleaños, boda, aniversario, etc.).\n"
            "- CONOCE_AGRUPACION: quiere conocer a la agrupación, videos, música, "
            "redes, integrantes o trayectoria.\n"
            "- CONTACTO: quiere comunicarse con una persona, pide un número/teléfono, "
            "que lo llamen, retomar una conversación previa o hablar con un asesor.\n"
            "- FUERA_DE_TEMA: cualquier cosa que NO sea sobre ESTA agrupación ni sus "
            "presentaciones/contratación (cultura general, otras agrupaciones, "
            "preguntas personales, chistes, etc.).\n"
            "- DESPEDIDA: el usuario solo confirma/agradece/cierra y NO pide nada "
            "más (ej: 'ok', 'gracias', 'ya', 'listo', 'perfecto', 'nada más', "
            "'después te escribo').\n"
            "- UNKNOWN: no encaja claramente en ninguna.\n\n"
            f"Mensaje: {text}\n\n"
            'Responde SOLO un JSON válido sin markdown: '
            '{"intent": "...", "confidence": 0.0-1.0}'
        )
        result = json.loads(_strip_json(_generate(prompt)))
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


def interpret_event_fields(text: str) -> dict:
    """Interpreta fecha/hora/tipo de un mensaje ambiguo que el regex no entendió.

    Normaliza expresiones como 'medio día'→'mediodía (12:00 pm)',
    'fin de semana'→'fin de semana', 'al atardecer'→'tarde'. Devuelve
    {fecha, hora, tipo} con lo que pueda inferir (vacío si no hay).
    NO inventa: si el texto no da pistas de un campo, lo deja vacío.
    """
    if not is_enabled() or not _client:
        return {}
    try:
        prompt = (
            "Extrae del mensaje de un cliente estos datos para una contratación "
            "musical y NORMALÍZALOS a un texto corto y claro en español. Si un "
            "dato no aparece, déjalo como cadena vacía. NO inventes.\n"
            "- fecha: fecha o referencia ('15/10', 'fin de semana', 'sábado', "
            "'fin de mes', 'Día de la Madre').\n"
            "- hora: hora aproximada ('mediodía (12 pm)', '8 pm', 'en la tarde', "
            "'al atardecer (~6 pm)').\n"
            "- tipo: tipo de evento ('cumpleaños', 'boda', 'fiesta patronal', etc.).\n"
            "- localidad: ciudad, distrito o localidad del evento.\n"
            "- confidence: confianza general de 0.0 a 1.0.\n\n"
            f"Mensaje: {text}\n\n"
            'Responde SOLO JSON sin markdown: {"fecha": "", "hora": "", '
            '"tipo": "", "localidad": "", "confidence": 0.0}'
        )
        result = json.loads(_strip_json(_generate(prompt)))
        return {
            "fecha": str(result.get("fecha", "") or "").strip(),
            "hora": str(result.get("hora", "") or "").strip(),
            "tipo": str(result.get("tipo", "") or "").strip(),
            "localidad": str(result.get("localidad", "") or "").strip(),
            "confidence": _confidence(result),
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] error en interpret_event_fields: {exc.__class__.__name__}")
        return {}


def interpret_identity(text: str) -> dict:
    """Extrae nombre/DNI y preferencia de contacto sin inventar identidad."""
    if not is_enabled() or not _client:
        return {}
    try:
        prompt = (
            "Analiza una respuesta al pedido: '¿A nombre de quién dejamos la "
            "solicitud?'. Extrae únicamente datos explícitos. No inventes.\n"
            "- name_or_dni: nombre completo o DNI; elimina frases como 'a nombre "
            "de', 'soy', 'me llamo' y 'mi nombre es'.\n"
            "- declined: true si no desea brindar nombre/DNI.\n"
            "- contact_phone: otro celular indicado, si existe.\n"
            "- prefers_call: true si pide llamada.\n"
            "- call_time: hora indicada para la llamada.\n"
            "- confidence: confianza de 0.0 a 1.0.\n\n"
            f"Mensaje: {text}\n\n"
            'Responde SOLO JSON sin markdown: {"name_or_dni": "", '
            '"declined": false, "contact_phone": "", "prefers_call": false, '
            '"call_time": "", "confidence": 0.0}'
        )
        result = json.loads(_strip_json(_generate(prompt)))
        return {
            "name_or_dni": str(result.get("name_or_dni", "") or "").strip(),
            "declined": bool(result.get("declined", False)),
            "contact_phone": str(result.get("contact_phone", "") or "").strip(),
            "prefers_call": bool(result.get("prefers_call", False)),
            "call_time": str(result.get("call_time", "") or "").strip(),
            "confidence": _confidence(result),
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] error en interpret_identity: {exc.__class__.__name__}")
        return {}


def interpret_hiring_action(text: str) -> dict:
    """Clasifica una respuesta ambigua durante la revisión final."""
    if not is_enabled() or not _client:
        return {}
    try:
        prompt = (
            "Clasifica el mensaje de un cliente que está revisando una solicitud "
            "de contratación musical. No respondas ni inventes datos.\n"
            "- CONFIRM: quiere enviar o confirmar la solicitud.\n"
            "- CORRECT: quiere cambiar algún dato.\n"
            "- CANCEL: quiere cancelar o borrar la solicitud.\n"
            "- UNKNOWN: no está claro.\n\n"
            f"Mensaje: {text}\n\n"
            'Responde SOLO JSON sin markdown: {"action": "CONFIRM|CORRECT|'
            'CANCEL|UNKNOWN", "confidence": 0.0}'
        )
        result = json.loads(_strip_json(_generate(prompt)))
        action = str(result.get("action", "UNKNOWN") or "UNKNOWN").upper()
        if action not in {"CONFIRM", "CORRECT", "CANCEL", "UNKNOWN"}:
            action = "UNKNOWN"
        return {"action": action, "confidence": _confidence(result)}
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] error en interpret_hiring_action: {exc.__class__.__name__}")
        return {}


# Acciones que la IA puede sugerir cuando un ADMIN escribe en lenguaje natural
# y las reglas no lo entienden. Solo clasifica (no redacta).
_VALID_ADMIN_ACTIONS = {
    "VER_SOLICITUDES", "VER_EVENTOS", "METRICAS", "REGISTRAR_EVENTO",
    "RESUMEN_CLIENTE", "AYUDA", "NADA",
}


def classify_admin_request(text: str) -> dict:
    """Asistente para administradores: clasifica un pedido en lenguaje natural
    en una acción del panel. Devuelve {success, action, confidence}."""
    if not is_enabled() or not _client:
        return {"success": False}
    try:
        prompt = (
            "Eres el asistente de un administrador en el panel de WhatsApp de una "
            "agrupación musical. Clasifica el pedido del admin en UNA acción. NO "
            "respondas el pedido, solo clasifícalo:\n"
            "- VER_SOLICITUDES: ver la lista de solicitudes/clientes/leads.\n"
            "- VER_EVENTOS: ver/gestionar la agenda de eventos.\n"
            "- METRICAS: ver métricas/estadísticas/reporte.\n"
            "- REGISTRAR_EVENTO: agendar/crear un evento nuevo.\n"
            "- RESUMEN_CLIENTE: quiere el resumen/contexto de la conversación con "
            "un cliente, saber de qué se habló o a quién atiende.\n"
            "- AYUDA: cómo usar el bot.\n"
            "- NADA: no encaja en ninguna.\n\n"
            f"Pedido: {text}\n\n"
            'Responde SOLO JSON sin markdown: {"action": "...", "confidence": 0.0-1.0}'
        )
        result = json.loads(_strip_json(_generate(prompt)))
        action = str(result.get("action", "NADA")).upper()
        if action not in _VALID_ADMIN_ACTIONS:
            action = "NADA"
        confidence = float(result.get("confidence", 0.5))
        return {"success": True, "action": action,
                "confidence": min(1.0, max(0.0, confidence))}
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] error en classify_admin_request: {exc.__class__.__name__}")
        return {"success": False}


def summarize_admin_context(client_name: str, request_data: dict, transcript: str) -> str | None:
    """Resume para un admin donde quedo una conversacion con un cliente."""
    if not is_enabled() or not _client or not transcript:
        return None
    try:
        prompt = (
            "Eres asistente interno de un manager de una agrupacion musical. "
            "Resume SOLO el contexto util para retomar una solicitud de contratacion. "
            "No inventes datos. Si falta algo, no lo menciones. Devuelve una sola "
            "frase en espanol, natural y concreta, maximo 35 palabras.\n\n"
            "Formato deseado:\n"
            "Contexto anterior: <que queria el cliente, condiciones, dudas, precio, "
            "rebaja, bailarines, horario o siguiente paso pendiente>.\n\n"
            f"Cliente: {client_name}\n"
            f"Solicitud: {request_data}\n\n"
            f"Historial:\n{transcript}\n\n"
            "Respuesta:"
        )
        text = _generate(prompt)
        if not text:
            return None
        text = text.replace("\n", " ").strip()
        if not text.lower().startswith("contexto anterior:"):
            text = "Contexto anterior: " + text
        return text[:500]
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] error en summarize_admin_context: {exc.__class__.__name__}")
        return None


# NOTA: la IA NO redacta respuestas libres a clientes. Solo clasifica.


def _strip_json(text: str) -> str:
    """Quita posibles cercos ```json ... ``` de la respuesta del modelo."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    return t.strip()


def _confidence(result: dict) -> float:
    try:
        value = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        value = 0.0
    return min(1.0, max(0.0, value))
