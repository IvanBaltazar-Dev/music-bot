"""Supabase/PostgreSQL storage adapter.

Mantiene la interfaz historica de `sheets_client` (nombres de columnas tipo
Google Sheets), pero persiste en las tablas CRM de Supabase.
"""

from __future__ import annotations

import json
from urllib.parse import quote

import httpx

from app.config import settings
from app.security import sanitize_text
from app.repositories import sheets_schema


def _only_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _bool_to_sheet(value) -> str:
    return "SI" if bool(value) else "NO"


def _sheet_bool(value) -> bool:
    return str(value or "").strip().lower() in {"si", "sí", "true", "1", "x", "yes", "activo"}


def _headers(extra: str = "") -> dict:
    prefer = extra or "return=representation"
    return {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def is_enabled() -> bool:
    return settings.supabase_enabled


def _base_url() -> str:
    return settings.SUPABASE_URL.rstrip("/") + "/rest/v1"


def _request(method: str, table: str, *, params: dict | None = None,
             json_body=None, prefer: str = "return=representation"):
    if not is_enabled():
        raise RuntimeError("Supabase no esta configurado")
    url = f"{_base_url()}/{table}"
    with httpx.Client(timeout=15.0) as client:
        response = client.request(
            method,
            url,
            headers=_headers(prefer),
            params=params or {},
            json=json_body,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase {response.status_code}: {sanitize_text(response.text, limit=500)}")
    if not response.content:
        return None
    return response.json()


def _select(table: str, *, params: dict | None = None, limit: int | None = None) -> list[dict]:
    q = {"select": "*"}
    q.update(params or {})
    if limit:
        q["limit"] = str(limit)
    data = _request("GET", table, params=q)
    return data if isinstance(data, list) else []


def _select_one(table: str, *, params: dict | None = None) -> dict | None:
    rows = _select(table, params=params, limit=1)
    return rows[0] if rows else None


def _insert(table: str, payload: dict) -> dict | None:
    rows = _request("POST", table, json_body=payload)
    return rows[0] if isinstance(rows, list) and rows else None


def _upsert(table: str, payload: dict, conflict: str) -> dict | None:
    rows = _request(
        "POST",
        table,
        params={"on_conflict": conflict},
        json_body=payload,
        prefer="resolution=merge-duplicates,return=representation",
    )
    return rows[0] if isinstance(rows, list) and rows else None


def _patch(table: str, filters: dict, payload: dict) -> bool:
    params = {k: f"eq.{v}" for k, v in filters.items()}
    rows = _request("PATCH", table, params=params, json_body=payload)
    return bool(rows)


def _ensure_client(phone: str, name: str = "") -> dict:
    digits = _only_digits(phone)
    payload = {"phone": digits, "last_seen_at": "now()"}
    if name:
        payload["display_name"] = name
    found = _select_one("clients", params={"phone": f"eq.{digits}"})
    if found:
        return found
    return _insert("clients", {"phone": digits, "display_name": name or None}) or {"phone": digits}


def _ensure_thread(phone: str, client_id: str | None = None) -> dict | None:
    digits = _only_digits(phone)
    if not client_id:
        client = _ensure_client(digits)
        client_id = client.get("id")
    if not client_id:
        return None
    found = _select_one("conversation_threads", params={"client_id": f"eq.{client_id}", "channel": "eq.whatsapp"})
    if found:
        return found
    return _insert("conversation_threads", {
        "client_id": client_id,
        "client_phone": digits,
        "channel": "whatsapp",
        "state": "BOT_ACTIVO",
    })


def _request_by_code(code: str) -> dict | None:
    code = str(code or "").strip()
    if not code:
        return None
    return _select_one("hiring_requests", params={"code": f"eq.{quote(code, safe='')}"})


def _admin_by_phone(phone: str) -> dict | None:
    digits = _only_digits(phone)
    if not digits:
        return None
    return _select_one("admins", params={"phone": f"eq.{digits}"})


def _json_or_text(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        return json.loads(str(value))
    except Exception:  # noqa: BLE001
        return {"raw": str(value)}


def _from_admin(r: dict) -> dict:
    return {
        "id_admin": r.get("legacy_id") or r.get("id", ""),
        "nombre": r.get("name", ""),
        "telefono": r.get("phone", ""),
        "rol": r.get("role", ""),
        "activo": _bool_to_sheet(r.get("active", False)),
    }


def _to_admin(r: dict) -> dict:
    return {
        "legacy_id": r.get("id_admin") or None,
        "name": r.get("nombre") or r.get("telefono") or "Admin",
        "phone": _only_digits(r.get("telefono", "")),
        "role": r.get("rol") or "manager",
        "active": _sheet_bool(r.get("activo", "SI")),
    }


def _from_conversation(r: dict) -> dict:
    return {
        "id_conversacion": r.get("legacy_id") or r.get("id", ""),
        "numero_usuario": r.get("client_phone", ""),
        "estado_conversacion": r.get("state", "BOT_ACTIVO"),
        "admin_numero": r.get("current_admin_phone", ""),
        "fecha_inicio": r.get("started_at", ""),
        "fecha_ultima_interaccion": r.get("last_interaction_at", ""),
        "fecha_toma_control": r.get("control_taken_at", ""),
        "fecha_suelta_control": r.get("control_released_at", ""),
    }


def _to_conversation(r: dict) -> dict:
    phone = _only_digits(r.get("numero_usuario", ""))
    client = _ensure_client(phone)
    admin_phone = _only_digits(r.get("admin_numero", ""))
    admin = _admin_by_phone(admin_phone) if admin_phone else None
    payload = {
        "legacy_id": r.get("id_conversacion") or None,
        "client_id": client.get("id"),
        "client_phone": phone,
        "channel": "whatsapp",
        "state": r.get("estado_conversacion") or "BOT_ACTIVO",
        "current_admin_id": (admin or {}).get("id"),
        "current_admin_phone": admin_phone or None,
    }
    if r.get("fecha_toma_control"):
        payload["control_taken_at"] = r.get("fecha_toma_control")
    if r.get("fecha_suelta_control"):
        payload["control_released_at"] = r.get("fecha_suelta_control")
    return payload


def _from_hiring(r: dict) -> dict:
    return {
        "codigo_solicitud": r.get("code", ""),
        "fecha_registro": r.get("created_at", ""),
        "estado": r.get("status", ""),
        "numero_cliente": r.get("client_phone", ""),
        "nombre_o_dni": r.get("name_or_dni", "") or "",
        "admin_asignado": r.get("assigned_admin_phone", "") or "",
        "modo_atencion": r.get("attention_mode", ""),
        "fecha_ultima_interaccion": r.get("last_interaction_at", ""),
        "observaciones": r.get("notes", "") or "",
        "origen": r.get("origin", ""),
        "tipo_evento": r.get("event_type", "") or "",
        "fecha_evento": r.get("event_date_text", "") or "",
        "horario_evento": r.get("event_time_text", "") or "",
        "localidad": r.get("locality", "") or "",
        "ultimo_mensaje_cliente": r.get("last_client_message", "") or "",
    }


def _to_hiring(r: dict) -> dict:
    phone = _only_digits(r.get("numero_cliente", ""))
    client = _ensure_client(phone, r.get("nombre_o_dni", ""))
    thread = _ensure_thread(phone, client.get("id"))
    admin_phone = _only_digits(r.get("admin_asignado", ""))
    admin = _admin_by_phone(admin_phone) if admin_phone else None
    payload = {
        "code": r.get("codigo_solicitud") or None,
        "client_id": client.get("id"),
        "thread_id": (thread or {}).get("id"),
        "client_phone": phone,
        "name_or_dni": r.get("nombre_o_dni") or None,
        "contact_phone": _only_digits(r.get("numero_contacto", "")) or phone or None,
        "assigned_admin_id": (admin or {}).get("id"),
        "assigned_admin_phone": admin_phone or None,
        "status": r.get("estado") or "ABIERTA",
        "attention_mode": r.get("modo_atencion") or "BOT",
        "origin": r.get("origen") or "whatsapp",
        "event_type": r.get("tipo_evento") or None,
        "event_date_text": r.get("fecha_evento") or None,
        "event_time_text": r.get("horario_evento") or None,
        "locality": r.get("localidad") or None,
        "last_client_message": r.get("ultimo_mensaje_cliente") or None,
        "notes": r.get("observaciones") or None,
    }
    return payload


def _from_message(r: dict) -> dict:
    return {
        "id_mensaje": r.get("legacy_id") or r.get("id", ""),
        "fecha_hora": r.get("created_at", ""),
        "numero_usuario": r.get("phone", ""),
        "direccion": r.get("direction", ""),
        "tipo_mensaje": r.get("message_type", "text"),
        "texto": r.get("text", "") or "",
        "payload_boton": r.get("button_payload", "") or "",
        "flujo_detectado": r.get("flow", "") or "",
        "intencion_detectada": r.get("intent", "") or "",
        "codigo_solicitud": (r.get("request") or {}).get("code", "") if isinstance(r.get("request"), dict) else "",
        "admin_numero": r.get("admin_phone", "") or "",
        "raw_json": json.dumps(r.get("raw_json", ""), ensure_ascii=False) if isinstance(r.get("raw_json"), dict) else (r.get("raw_json") or ""),
    }


def _to_message(r: dict) -> dict:
    phone = _only_digits(r.get("numero_usuario", ""))
    client = _ensure_client(phone)
    thread = _ensure_thread(phone, client.get("id"))
    req = _request_by_code(r.get("codigo_solicitud", ""))
    admin_phone = _only_digits(r.get("admin_numero", ""))
    admin = _admin_by_phone(admin_phone) if admin_phone else None
    direction = r.get("direccion") or "ENTRANTE"
    sender_type = "CLIENT" if direction in {"ENTRANTE", "CLIENTE_A_ADMIN"} else "BOT"
    if direction in {"ADMIN_A_CLIENTE", "ADMIN_INTERNO"}:
        sender_type = "ADMIN"
    return {
        "legacy_id": r.get("id_mensaje") or None,
        "thread_id": (thread or {}).get("id"),
        "client_id": client.get("id"),
        "request_id": (req or {}).get("id"),
        "admin_id": (admin or {}).get("id"),
        "phone": phone,
        "direction": direction,
        "sender_type": sender_type,
        "message_type": r.get("tipo_mensaje") or "text",
        "text": r.get("texto") or None,
        "button_payload": r.get("payload_boton") or None,
        "flow": r.get("flujo_detectado") or None,
        "intent": r.get("intencion_detectada") or None,
        "raw_json": _json_or_text(r.get("raw_json", "")) or None,
    }


def _from_event(r: dict) -> dict:
    return {
        "id_evento": r.get("legacy_id") or r.get("id", ""),
        "fecha_evento": r.get("event_date_text") or str(r.get("event_date") or ""),
        "hora_inicio": r.get("start_time", "") or "",
        "hora_fin": r.get("end_time", "") or "",
        "ciudad": r.get("city", "") or "",
        "lugar": r.get("place", "") or "",
        "google_maps_url": r.get("google_maps_url", "") or "",
        "estado": r.get("status", "") or "",
        "fecha_creacion": r.get("created_at", "") or "",
        "fecha_actualizacion": r.get("updated_at", "") or "",
        "precio_entrada": r.get("ticket_price", "") or "",
        "link_evento": r.get("event_link", "") or "",
    }


def _to_event(r: dict) -> dict:
    return {
        "legacy_id": r.get("id_evento") or None,
        "event_date_text": r.get("fecha_evento") or None,
        "start_time": r.get("hora_inicio") or None,
        "end_time": r.get("hora_fin") or None,
        "city": r.get("ciudad") or "",
        "place": r.get("lugar") or None,
        "google_maps_url": r.get("google_maps_url") or None,
        "status": r.get("estado") or "CONFIRMADO",
        "ticket_price": r.get("precio_entrada") or None,
        "event_link": r.get("link_evento") or None,
    }


def _from_locality(r: dict) -> dict:
    return {
        "id_localidad": r.get("legacy_id") or r.get("id", ""),
        "nombre_localidad": r.get("name", "") or "",
        "nombre_normalizado": r.get("normalized_name", "") or "",
        "region": r.get("region", "") or "",
        "provincia": r.get("province", "") or "",
        "palabras_clave": ", ".join(r.get("keywords") or []),
        "frase_contratacion": r.get("hiring_phrase", "") or "",
        "frase_eventos": r.get("events_phrase", "") or "",
        "frase_general": r.get("general_phrase", "") or "",
        "activo": _bool_to_sheet(r.get("active", False)),
        "prioridad": str(r.get("priority", "")),
        "fecha_actualizacion": r.get("updated_at", "") or "",
    }


def _to_locality(r: dict) -> dict:
    keywords = [p.strip() for p in str(r.get("palabras_clave", "")).split(",") if p.strip()]
    return {
        "legacy_id": r.get("id_localidad") or None,
        "name": r.get("nombre_localidad") or "",
        "normalized_name": r.get("nombre_normalizado") or "",
        "region": r.get("region") or None,
        "province": r.get("provincia") or None,
        "keywords": keywords,
        "hiring_phrase": r.get("frase_contratacion") or None,
        "events_phrase": r.get("frase_eventos") or None,
        "general_phrase": r.get("frase_general") or None,
        "active": _sheet_bool(r.get("activo", "SI")),
        "priority": int(str(r.get("prioridad") or "0")) if str(r.get("prioridad") or "0").isdigit() else 0,
    }


def _from_follow(r: dict) -> dict:
    return {
        "id_seguimiento": r.get("legacy_id") or r.get("id", ""),
        "codigo_solicitud": (r.get("request") or {}).get("code", "") if isinstance(r.get("request"), dict) else "",
        "admin_numero": r.get("admin_phone", "") or "",
        "numero_cliente": r.get("client_phone", "") or "",
        "fecha_inicio": r.get("started_at", "") or "",
        "estado": r.get("status", "") or "",
    }


def _to_follow(r: dict) -> dict:
    req = _request_by_code(r.get("codigo_solicitud", ""))
    admin_phone = _only_digits(r.get("admin_numero", ""))
    admin = _admin_by_phone(admin_phone) if admin_phone else None
    phone = _only_digits(r.get("numero_cliente", ""))
    client = _ensure_client(phone)
    return {
        "legacy_id": r.get("id_seguimiento") or None,
        "request_id": (req or {}).get("id"),
        "admin_id": (admin or {}).get("id"),
        "admin_phone": admin_phone or None,
        "client_id": client.get("id"),
        "client_phone": phone,
        "status": r.get("estado") or "ACTIVO",
    }


def _from_metric(r: dict) -> dict:
    return {
        "id_metrica": r.get("legacy_id") or r.get("id", ""),
        "fecha_hora": r.get("created_at", "") or "",
        "numero_usuario": r.get("phone", "") or "",
        "intencion_detectada": r.get("intent", "") or "",
        "flujo": r.get("flow", "") or "",
        "paso": r.get("step", "") or "",
        "ciudad_mencionada": r.get("city", "") or "",
        "opcion_elegida": r.get("chosen_option", "") or "",
        "mensaje_usuario": r.get("user_message", "") or "",
        "respuesta_bot": r.get("bot_response", "") or "",
        "codigo_solicitud": "",
        "id_evento": "",
    }


def _to_metric(r: dict) -> dict:
    phone = _only_digits(r.get("numero_usuario", ""))
    client = _ensure_client(phone) if phone else {}
    req = _request_by_code(r.get("codigo_solicitud", ""))
    return {
        "legacy_id": r.get("id_metrica") or None,
        "client_id": client.get("id"),
        "request_id": (req or {}).get("id"),
        "phone": phone or None,
        "intent": r.get("intencion_detectada") or None,
        "flow": r.get("flujo") or None,
        "step": r.get("paso") or None,
        "city": r.get("ciudad_mencionada") or None,
        "chosen_option": r.get("opcion_elegida") or None,
        "user_message": r.get("mensaje_usuario") or None,
        "bot_response": r.get("respuesta_bot") or None,
    }


def _from_interest(r: dict) -> dict:
    return {
        "id_interes": r.get("legacy_id") or r.get("id", ""),
        "fecha_hora": r.get("created_at", "") or "",
        "numero_usuario": r.get("phone", "") or "",
        "nombre": r.get("name", "") or "",
        "localidad": r.get("locality", "") or "",
        "mensaje": r.get("message", "") or "",
        "estado": r.get("status", "") or "",
    }


def _to_interest(r: dict) -> dict:
    phone = _only_digits(r.get("numero_usuario", ""))
    client = _ensure_client(phone, r.get("nombre", ""))
    return {
        "legacy_id": r.get("id_interes") or None,
        "client_id": client.get("id"),
        "phone": phone,
        "name": r.get("nombre") or None,
        "locality": r.get("localidad") or None,
        "message": r.get("mensaje") or None,
        "status": r.get("estado") or "NUEVO",
    }


def _from_content(r: dict) -> dict:
    return {
        "id_contenido": r.get("legacy_id") or r.get("id", ""),
        "categoria": r.get("category", "") or "",
        "titulo": r.get("title", "") or "",
        "descripcion": r.get("description", "") or "",
        "url": r.get("url", "") or "",
        "activo": _bool_to_sheet(r.get("active", False)),
        "prioridad": str(r.get("priority", "")),
        "fecha_actualizacion": r.get("updated_at", "") or "",
    }


def _to_content(r: dict) -> dict:
    return {
        "legacy_id": r.get("id_contenido") or None,
        "category": r.get("categoria") or r.get("tipo") or "",
        "title": r.get("titulo") or "",
        "description": r.get("descripcion") or None,
        "url": r.get("url") or None,
        "active": _sheet_bool(r.get("activo", "SI")),
        "priority": int(str(r.get("prioridad") or r.get("orden") or "0")) if str(r.get("prioridad") or r.get("orden") or "0").isdigit() else 0,
    }


def _from_error(r: dict) -> dict:
    return {
        "id_error": r.get("legacy_id") or r.get("id", ""),
        "fecha_hora": r.get("created_at", "") or "",
        "modulo": r.get("module", "") or "",
        "numero_usuario": r.get("phone", "") or "",
        "mensaje_usuario": r.get("user_message", "") or "",
        "error": r.get("error", "") or "",
        "stacktrace": r.get("stacktrace", "") or "",
        "raw_json": json.dumps(r.get("raw_json", ""), ensure_ascii=False) if isinstance(r.get("raw_json"), dict) else (r.get("raw_json") or ""),
        "estado": r.get("status", "") or "",
    }


def _to_error(r: dict) -> dict:
    return {
        "legacy_id": r.get("id_error") or None,
        "module": r.get("modulo") or None,
        "phone": _only_digits(r.get("numero_usuario", "")) or None,
        "user_message": r.get("mensaje_usuario") or None,
        "error": r.get("error") or "",
        "stacktrace": r.get("stacktrace") or None,
        "raw_json": _json_or_text(r.get("raw_json", "")) or None,
        "status": r.get("estado") or "NUEVO",
    }


_MAP = {
    sheets_schema.SHEET_ADMINS: ("admins", _from_admin, _to_admin, {"id_admin": "legacy_id", "telefono": "phone"}),
    sheets_schema.SHEET_CONVERSATIONS: ("conversation_threads", _from_conversation, _to_conversation, {"id_conversacion": "legacy_id", "numero_usuario": "client_phone"}),
    sheets_schema.SHEET_HIRING: ("hiring_requests", _from_hiring, _to_hiring, {"codigo_solicitud": "code", "numero_cliente": "client_phone"}),
    sheets_schema.SHEET_MESSAGES: ("messages", _from_message, _to_message, {"id_mensaje": "legacy_id", "numero_usuario": "phone"}),
    sheets_schema.SHEET_EVENTS: ("events", _from_event, _to_event, {"id_evento": "legacy_id"}),
    sheets_schema.SHEET_LOCALITIES: ("localities", _from_locality, _to_locality, {"id_localidad": "legacy_id", "nombre_normalizado": "normalized_name"}),
    sheets_schema.SHEET_FOLLOWUPS: ("follow_ups", _from_follow, _to_follow, {"id_seguimiento": "legacy_id", "numero_cliente": "client_phone"}),
    sheets_schema.SHEET_METRICS: ("metrics", _from_metric, _to_metric, {"id_metrica": "legacy_id", "numero_usuario": "phone"}),
    sheets_schema.SHEET_INTEREST: ("interests", _from_interest, _to_interest, {"id_interes": "legacy_id", "numero_usuario": "phone"}),
    sheets_schema.SHEET_CONTENT: ("group_contents", _from_content, _to_content, {"id_contenido": "legacy_id"}),
    sheets_schema.SHEET_ERRORS: ("internal_errors", _from_error, _to_error, {"id_error": "legacy_id", "numero_usuario": "phone"}),
}


def ensure_schema() -> dict:
    if not is_enabled():
        return {"modo": "supabase_no_configurado"}
    _select("clients", limit=1)
    return {"modo": "supabase", "tablas": sorted({v[0] for v in _MAP.values()})}


def read_records(sheet_name: str) -> list[dict]:
    if sheet_name not in _MAP:
        return []
    table, from_db, _, _ = _MAP[sheet_name]
    params = {"order": "created_at.asc"} if table not in {"localities", "events"} else {"order": "created_at.asc"}
    if table == "messages":
        params["select"] = "*,request:hiring_requests(code)"
    elif table == "follow_ups":
        params["select"] = "*,request:hiring_requests(code)"
    rows = _select(table, params=params)
    return [from_db(r) for r in rows]


def append_record(sheet_name: str, record: dict) -> bool:
    if sheet_name not in _MAP:
        return False
    table, _, to_db, _ = _MAP[sheet_name]
    payload = {k: v for k, v in to_db(record).items() if v is not None}
    _insert(table, payload)
    return True


def find_record(sheet_name: str, key_col: str, key_val: str) -> dict | None:
    if sheet_name not in _MAP:
        return None
    table, from_db, _, key_map = _MAP[sheet_name]
    db_col = key_map.get(key_col)
    if not db_col:
        for row in read_records(sheet_name):
            if str(row.get(key_col, "")).strip() == str(key_val).strip():
                return row
        return None
    value = _only_digits(key_val) if db_col.endswith("phone") or db_col in {"client_phone", "phone"} else str(key_val).strip()
    row = _select_one(table, params={db_col: f"eq.{quote(value, safe='')}"})
    return from_db(row) if row else None


def update_record(sheet_name: str, key_col: str, key_val: str, updates: dict) -> bool:
    if sheet_name not in _MAP:
        return False
    table, _, to_db, key_map = _MAP[sheet_name]
    db_col = key_map.get(key_col)
    if not db_col:
        current = find_record(sheet_name, key_col, key_val)
        if not current:
            return False
        key_col = next(iter(key_map))
        key_val = current.get(key_col, "")
        db_col = key_map[key_col]

    merged = dict(find_record(sheet_name, key_col, key_val) or {})
    merged.update(updates)
    payload = {k: v for k, v in to_db(merged).items() if v is not None}
    value = _only_digits(key_val) if db_col.endswith("phone") or db_col in {"client_phone", "phone"} else str(key_val).strip()
    return _patch(table, {db_col: quote(value, safe="")}, payload)
