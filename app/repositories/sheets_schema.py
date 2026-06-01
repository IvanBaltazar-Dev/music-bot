"""Esquema central de las hojas de Google Sheets.

Define el nombre y los encabezados de cada hoja en un único lugar. El cliente de
Sheets (`sheets_client`) usa este esquema para:

* Leer registros con las columnas correctas.
* Crear hojas faltantes SOLO con sus encabezados (nunca borra ni sobrescribe).
* Mantener el almacén en memoria con la misma forma que las hojas reales.

IMPORTANTE: Si una hoja ya existe en el documento, jamás se modifica ni se borra.
Solo se crean encabezados cuando la hoja no existe o está completamente vacía.
"""

from __future__ import annotations

# --- Nombres de hojas (constantes) ---
SHEET_CONFIG = "ConfiguracionBot"
SHEET_EVENTS = "Eventos"
SHEET_HIRING = "SolicitudesContratacion"
SHEET_INTEREST = "InteresesLocalidad"
SHEET_USERS = "Usuarios"
SHEET_CONVERSATIONS = "Conversaciones"
SHEET_MESSAGES = "Mensajes"
SHEET_ADMINS = "Administradores"
SHEET_FOLLOWUPS = "Seguimientos"
SHEET_METRICS = "Metricas"
SHEET_CONTENT = "ContenidosAgrupacion"
SHEET_LOCALITIES = "Localidades"
SHEET_ADMIN_NOTIFS = "NotificacionesAdmin"
SHEET_ERRORS = "Errores"
SHEET_CATALOGS = "Catalogos"


# --- Encabezados por hoja ---
HEADERS: dict[str, list[str]] = {
    SHEET_CONFIG: [
        "clave", "valor", "descripcion", "fecha_actualizacion",
    ],
    SHEET_EVENTS: [
        "id_evento", "fecha_evento", "hora_inicio", "hora_fin", "ciudad",
        "provincia", "region", "lugar", "direccion", "google_maps_url",
        "estado", "entrada_precio", "entrada_descripcion", "entrada_link",
        "flyer_url", "post_url", "descripcion_publica", "notas_internas",
        "creado_por", "fecha_creacion", "fecha_actualizacion",
    ],
    SHEET_HIRING: [
        "codigo_solicitud", "fecha_registro", "estado", "numero_cliente",
        "nombre_o_dni", "numero_contacto", "localidad", "tipo_evento",
        "fecha_evento", "horario_evento", "cantidad_personas", "admin_asignado",
        "modo_atencion", "ultimo_mensaje_cliente", "fecha_ultima_interaccion",
        "observaciones", "origen",
    ],
    SHEET_INTEREST: [
        "id_interes", "fecha_hora", "numero_usuario", "nombre",
        "localidad", "mensaje", "estado",
    ],
    SHEET_USERS: [
        "numero_usuario", "nombre", "localidad", "primer_contacto",
        "ultimo_contacto", "total_mensajes",
    ],
    SHEET_CONVERSATIONS: [
        "id_conversacion", "numero_usuario", "flujo_actual", "paso_actual",
        "estado_conversacion", "datos_temporales_json", "admin_en_control",
        "admin_numero", "fecha_inicio", "fecha_ultima_interaccion",
    ],
    SHEET_MESSAGES: [
        "id_mensaje", "fecha_hora", "numero_usuario", "direccion",
        "tipo_mensaje", "texto", "payload_boton", "flujo_detectado",
        "intencion_detectada", "codigo_solicitud", "admin_numero", "raw_json",
    ],
    SHEET_ADMINS: [
        "id_admin", "nombre", "telefono", "rol", "activo",
    ],
    SHEET_FOLLOWUPS: [
        "id_seguimiento", "codigo_solicitud", "admin_numero",
        "numero_cliente", "fecha_inicio", "estado",
    ],
    SHEET_METRICS: [
        "id_metrica", "fecha_hora", "numero_usuario", "intencion_detectada",
        "flujo", "paso", "ciudad_mencionada", "opcion_elegida",
        "mensaje_usuario", "respuesta_bot", "codigo_solicitud", "id_evento",
    ],
    SHEET_CONTENT: [
        "id_contenido", "tipo", "titulo", "descripcion", "url",
        "orden", "activo", "fecha_actualizacion",
    ],
    SHEET_LOCALITIES: [
        "id_localidad", "nombre_localidad", "nombre_normalizado", "region",
        "provincia", "palabras_clave", "frase_contratacion", "frase_eventos",
        "frase_general", "activo", "prioridad", "fecha_actualizacion",
    ],
    SHEET_ADMIN_NOTIFS: [
        "id_notificacion", "fecha_hora", "codigo_solicitud", "admin_numero",
        "tipo", "estado",
    ],
    SHEET_ERRORS: [
        "id_error", "fecha_hora", "modulo", "numero_usuario", "mensaje_usuario",
        "error", "stacktrace", "raw_json", "estado",
    ],
    SHEET_CATALOGS: [
        "id_catalogo", "categoria", "clave", "valor", "descripcion",
        "orden", "activo",
    ],
}


def all_sheet_names() -> list[str]:
    return list(HEADERS.keys())


def headers_for(sheet_name: str) -> list[str]:
    return HEADERS.get(sheet_name, [])
