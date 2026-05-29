#!/usr/bin/env python
"""Valida la configuración de Google Sheets sin tocar el bot.

Ejecución:
    python test_google_sheets_setup.py

Busca `google-credentials.json` en la raíz del proyecto y verifica que
pueda conectar, crear hojas y leer/escribir datos de prueba.
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

CREDS_FILE = "google-credentials.json"
SHEETS_ID_HELP = (
    "Copía el ID desde la URL de tu Google Sheet:\n"
    "https://docs.google.com/spreadsheets/d/AQUI-ES-EL-ID/edit"
)


def step(msg):
    print(f"\n✓ {msg}")


def error(msg):
    print(f"\n✗ ERROR: {msg}")
    sys.exit(1)


def check_file():
    if not os.path.exists(CREDS_FILE):
        error(
            f"No encontré {CREDS_FILE}.\n"
            "Sigue los pasos en SETUP_GOOGLE_SHEETS.md para descargarlo."
        )
    step(f"Archivo {CREDS_FILE} encontrado")


def check_credentials():
    try:
        with open(CREDS_FILE) as f:
            creds = json.load(f)
    except Exception as e:
        error(f"No se pudo leer {CREDS_FILE}: {e}")

    email = creds.get("client_email")
    if not email:
        error(f"El JSON no tiene 'client_email'. ¿Está bien descargado?")
    step(f"Credenciales JSON válidas. Email: {email}")
    return email


def check_libraries():
    try:
        import gspread  # noqa: F401
        import google.oauth2.service_account  # noqa: F401
        step("Librerías gspread y google-auth instaladas")
    except ImportError as e:
        error(
            f"Faltan librerías: {e}\n"
            "Instala con: pip install gspread google-auth"
        )


def check_connection():
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        step("Conexión a Google establecida")
        return client
    except Exception as e:
        error(f"No se pudo conectar a Google: {e}")


def check_sheet():
    sheets_id = input(f"\n¿ID de tu Google Sheet? ")
    if not sheets_id:
        error("Necesito el ID de la hoja")

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        ss = client.open_by_key(sheets_id)
        step(f"Hoja '{ss.title}' accesible")
        return ss, sheets_id
    except Exception as e:
        error(
            f"No se pudo abrir la hoja:\n{e}\n\n"
            "Posibles problemas:\n"
            f"- El ID está mal (verifica: {SHEETS_ID_HELP})\n"
            f"- No compartiste la hoja con {CREDS_FILE}\n"
            f"- Aún no hiciste `pip install gspread google-auth`"
        )


def check_sheets_structure(ss):
    expected = ["Eventos", "Solicitudes", "Admins", "Metricas"]
    for name in expected:
        try:
            ws = ss.worksheet(name)
            step(f"Hoja '{name}' existe")
        except Exception:
            print(f"  (creando hoja '{name}'...)")
            try:
                ss.add_worksheet(title=name, rows=100, cols=10)
                step(f"Hoja '{name}' creada")
            except Exception as e:
                error(f"No se pudo crear '{name}': {e}")


def check_write(ss):
    try:
        ws = ss.worksheet("Metricas")
        ws.append_row(["2026-05-29T00:00:00Z", "test", "519000000", "setup_test", "test"])
        step("Prueba de escritura en 'Metricas' exitosa")
    except Exception as e:
        error(f"No se pudo escribir en la hoja: {e}")


def main():
    print("=" * 70)
    print("Validador de configuración: Google Sheets para Music Bot")
    print("=" * 70)

    check_file()
    email = check_credentials()
    check_libraries()
    check_connection()
    ss, sheets_id = check_sheet()
    check_sheets_structure(ss)
    check_write(ss)

    print("\n" + "=" * 70)
    print("✅ ¡Todo está bien!")
    print("=" * 70)
    print(f"\nAhora edita tu `.env` con estos valores:\n")
    print(f"GOOGLE_SHEETS_ENABLED=true")
    print(f"GOOGLE_SHEETS_ID={sheets_id}")
    print(f"GOOGLE_APPLICATION_CREDENTIALS={CREDS_FILE}")
    print(f"\nLuego reinicia el bot:\n")
    print(f"python -m uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
