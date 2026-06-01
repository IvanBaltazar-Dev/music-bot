from dotenv import load_dotenv

load_dotenv()

from app.repositories.google_sheets_repository import (
    is_enabled,
    save_metric_event,
    save_quotation_request,
    get_recent_quotation_requests,
)

print("Google Sheets activo:", is_enabled())

ok_metric = save_metric_event({
    "tipo": "test_sheets",
    "whatsapp": "51999999999",
    "detalle": "Prueba de conexión desde test_sheets.py",
    "origen": "test",
})

print("Métrica guardada:", ok_metric)

ok_request = save_quotation_request({
    "whatsapp": "51999999999",
    "nombre": "Cliente de prueba",
    "lugar": "Huancayo",
    "fecha_evento": "2026-06-15",
    "tipo_evento": "Cumpleaños",
    "duracion": "2 horas",
    "contacto": "Mismo WhatsApp",
    "estado": "NUEVA",
})

print("Solicitud guardada:", ok_request)

print("Últimas solicitudes:")
print(get_recent_quotation_requests(limit=3))