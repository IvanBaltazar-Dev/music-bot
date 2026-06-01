from dotenv import load_dotenv

load_dotenv()

from app.repositories.google_sheets_repository import get_active_events, is_enabled

print("Google Sheets activo:", is_enabled())

events = get_active_events()

print("Eventos encontrados:", len(events))

for event in events:
    print(event)
