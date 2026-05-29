#!/usr/bin/env python
"""Valida la configuración de IA (Gemini) sin tocar el bot.

Ejecución:
    python test_ai_setup.py

Verifica que Gemini esté correctamente configurado probando con
mensajes de prueba.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings
from app.services import ai_service


def step(msg):
    print(f"✓ {msg}")


def error(msg):
    print(f"✗ ERROR: {msg}")
    sys.exit(1)


def check_enabled():
    if not settings.AI_ENABLED:
        error("AI_ENABLED=false. Habilita en .env si quieres usar IA.")
    step("AI_ENABLED=true")


def check_api_key():
    if not settings.GEMINI_API_KEY:
        error("GEMINI_API_KEY no configurado. Obtenlo de https://aistudio.google.com/app/apikey")
    step(f"GEMINI_API_KEY configurado (primeros 10 chars: {settings.GEMINI_API_KEY[:10]}...)")


def check_model():
    if not settings.AI_MODEL:
        error("AI_MODEL no configurado.")
    step(f"AI_MODEL={settings.AI_MODEL}")


def check_initialization():
    if not ai_service.is_enabled():
        error(
            "IA no se inicializó correctamente.\n"
            "Posibles causas:\n"
            "- Falta instalar: pip install google-generativeai\n"
            "- API key inválida\n"
            "- Error de red"
        )
    step("IA inicializada correctamente")


def test_classify_intent():
    print("\n[Test 1/3] Clasificar intención...")
    result = ai_service.classify_intent("hola, ¿cuándo tocan en Lima?")
    if not result.get("success"):
        error(f"Fallo: {result.get('reason')}")
    intent = result.get("intent")
    confidence = result.get("confidence")
    step(f"Intent={intent}, Confidence={confidence:.2f}")


def test_extract_data():
    print("\n[Test 2/3] Extraer datos de cotización...")
    result = ai_service.extract_quotation_data(
        "Necesito una presentación para el 15 de junio en Lima, para un cumpleaños de 3 horas"
    )
    if not result.get("success"):
        error(f"Fallo: {result}")
    extracted = result.get("extracted", {})
    step(f"Datos extraídos: {extracted}")


def test_validate_flow():
    print("\n[Test 3/3] Validar respuesta en flujo...")
    result = ai_service.validate_and_enhance_quotation(
        "quotation_date",
        {},
        "mañana a las 8"
    )
    if result:
        step(f"Interpretación: {result}")
    else:
        step("(IA decidió no intervenir, lo cual es normal)")


def main():
    print("=" * 70)
    print("Validador de IA: Gemini para Music Bot")
    print("=" * 70)

    check_enabled()
    check_api_key()
    check_model()
    check_initialization()

    try:
        test_classify_intent()
        test_extract_data()
        test_validate_flow()
    except Exception as e:
        error(f"Error durante pruebas: {e}")

    print("\n" + "=" * 70)
    print("✅ ¡IA está lista para usar!")
    print("=" * 70)
    print("\nLa IA se usará automáticamente como fallback cuando:")
    print("- Las reglas no clasifiquen una intención")
    print("- El usuario escriba algo ambiguo en un flujo")
    print("- Necesites mejorar la extracción de datos\n")


if __name__ == "__main__":
    main()
