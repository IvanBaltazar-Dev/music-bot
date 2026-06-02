"""Servicio de administración.

Reúne la lógica para administradores autorizados:
* Identificación (por .env y por la hoja `Administradores`).
* Notificación de nuevas solicitudes de contratación con botones de acción.
* "Tomar control" (relevo bot → administrador) y "Hacer seguimiento".
* Reenvío de mensajes cliente ⇄ administrador cuando hay control activo.

Todo mensaje saliente se registra en la hoja `Mensajes` para trazabilidad.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.repositories import (
    admin_repository,
    conversation_repository as conv_repo,
    follow_up_repository,
    hiring_request_repository as hiring_repo,
    message_repository as msg_repo,
)
from app.services import intent_service
from app.services.whatsapp_service import send_text_message, send_button_message


def _only_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _same_number(a: str, b: str) -> bool:
    a, b = _only_digits(a), _only_digits(b)
    if not a or not b:
        return False
    return a == b or a[-9:] == b[-9:]


def _admin_label(numero: str) -> str:
    digits = _only_digits(numero)
    if not digits:
        return "un administrador"
    try:
        name = admin_repository.get_name(digits)
    except Exception:  # noqa: BLE001
        name = ""
    return f"{name} ({digits})" if name else digits


def _extract_last_admin_action(observaciones: str) -> tuple[str, str]:
    """Extrae la última acción de admin (quién y cuándo) de observaciones.

    Devuelve (admin_label, fecha_hora_compacta) o ("", "") si no hay historial.
    Ejemplo: observaciones tiene "[2026-06-01T14:30:00+00:00] admin_123 solto control"
    Devuelve ("admin_123", "2026-06-01 14:30")
    """
    if not observaciones:
        return "", ""

    lines = str(observaciones).strip().split("\n")
    if not lines:
        return "", ""

    last_line = lines[-1].strip()
    if not last_line.startswith("["):
        return "", ""

    try:
        # Formato: [2026-06-01T14:30:00+00:00] {admin_label} {accion}
        end_bracket = last_line.find("]")
        if end_bracket < 1:
            return "", ""

        timestamp_str = last_line[1:end_bracket]
        rest = last_line[end_bracket + 1:].strip()

        if not rest:
            return "", ""

        # Parsea timestamp ISO a formato compacto
        from datetime import datetime as dt
        iso_dt = dt.fromisoformat(timestamp_str)
        compact_time = iso_dt.strftime("%Y-%m-%d %H:%M")

        return rest, compact_time
    except Exception:
        return "", ""


def _with_trace(sol: dict, message: str) -> str:
    current = str(sol.get("observaciones", "") or "").strip()
    stamp = datetime.now(timezone.utc).isoformat()
    trace = f"[{stamp}] {message}"
    if not current:
        return trace
    return current + "\n" + trace


def admin_numbers() -> list[str]:
    """Lista única de administradores (config .env + hoja Administradores)."""
    nums = list(settings.admin_numbers)
    try:
        nums += admin_repository.get_active_numbers()
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] no se pudieron leer admins de Sheets: {exc.__class__.__name__}")
    seen, unique = set(), []
    for n in nums:
        d = _only_digits(n)
        if d and d not in seen:
            seen.add(d)
            unique.append(d)
    return unique


def is_admin(whatsapp_number: str) -> bool:
    return any(_same_number(whatsapp_number, c) for c in admin_numbers())


# ---------------------------------------------------------------------------
# Mensajería interna con registro
# ---------------------------------------------------------------------------
async def _send_admin(numero: str, texto: str, buttons=None, codigo: str = ""):
    if buttons:
        await send_button_message(numero, texto, buttons)
    else:
        await send_text_message(numero, texto)
    try:
        msg_repo.save({
            "numero_usuario": numero,
            "direccion": msg_repo.ADMIN_INTERNO,
            "tipo_mensaje": "interactive" if buttons else "text",
            "texto": texto,
            "codigo_solicitud": codigo,
            "admin_numero": numero,
        })
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Notificación de nueva solicitud
# ---------------------------------------------------------------------------
def _request_summary(sol: dict) -> str:
    return (
        "📩 NUEVA SOLICITUD DE CONTRATACIÓN ABIERTA\n\n"
        f"Código interno: {sol.get('codigo_solicitud', '-')}\n"
        f"Fecha de registro: {sol.get('fecha_registro', '-')}\n\n"
        "Un cliente acaba de solicitar información para una presentación.\n\n"
        f"Cliente: {sol.get('nombre_o_dni', '-')}\n"
        f"WhatsApp del cliente: {sol.get('numero_cliente', '-')}\n"
        f"Número de contacto: {sol.get('numero_contacto', '-')}\n\n"
        f"Localidad: {sol.get('localidad', '-')}\n"
        f"Tipo de evento: {sol.get('tipo_evento', '-')}\n"
        f"Fecha solicitada: {sol.get('fecha_evento', '-')}\n"
        f"Horario aproximado: {sol.get('horario_evento', '-')}\n"
        f"Cantidad de personas: {sol.get('cantidad_personas', '-')}\n\n"
        f"Preferencia de contacto: {sol.get('observaciones', '-')}\n\n"
        "Último mensaje del cliente:\n"
        f"\"{sol.get('ultimo_mensaje_cliente', '-')}\"\n\n"
        "Estado: Pendiente de atención\n"
        "Administrador asignado: Sin asignar\n\n"
        "ℹ️ Si tocas *Tomar control*, lo que escribas en este chat se enviará "
        "directo al cliente. Si quieres revisar antes, toca *Ver solicitud*."
    )


def _action_buttons(code: str) -> list[dict]:
    return [
        {"id": intent_service.take_control_id(code), "title": "Tomar control"},
        {"id": intent_service.view_id(code), "title": "Ver solicitud"},
        {"id": intent_service.reply_later_id(code), "title": "Responder luego"},
    ]


async def notify_new_request(sol: dict) -> None:
    """Notifica a todos los administradores de una nueva solicitud abierta."""
    admins = admin_numbers()
    if not admins:
        print("[admin] no hay administradores configurados para notificar.")
        return
    texto = _request_summary(sol)
    code = sol.get("codigo_solicitud", "")
    buttons = _action_buttons(code)
    for numero in admins:
        await _send_admin(numero, texto, buttons=buttons, codigo=code)


async def notify_request_update(sol: dict, texto_cliente: str) -> None:
    """Avisa a admins que un cliente volvió a escribir sobre una solicitud abierta."""
    admins = admin_numbers()
    if not admins:
        print("[admin] no hay administradores configurados para notificar actualización.")
        return
    code = sol.get("codigo_solicitud", "")
    cuerpo = (
        "💬 El cliente volvió a escribir sobre una solicitud abierta\n\n"
        f"Solicitud: {code or '-'}\n"
        f"Cliente: {sol.get('nombre_o_dni', '-')}\n"
        f"WhatsApp: {sol.get('numero_cliente', '-')}\n"
        f"Estado: {sol.get('estado', '-')}\n\n"
        "Mensaje:\n"
        f"\"{texto_cliente}\""
    )
    buttons = [
        {"id": intent_service.take_control_id(code), "title": "Tomar control"},
        {"id": intent_service.view_id(code), "title": "Ver solicitud"},
        {"id": intent_service.reply_later_id(code), "title": "Responder luego"},
    ]
    for numero in admins:
        await _send_admin(numero, cuerpo, buttons=buttons if code else None, codigo=code)


# ---------------------------------------------------------------------------
# Tomar control
# ---------------------------------------------------------------------------
async def take_control(admin_number: str, code: str) -> str | None:
    """Un administrador toma el control de una solicitud. Devuelve el número
    del cliente si tuvo éxito, None en caso contrario."""
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return None

    client = _only_digits(sol.get("numero_cliente", ""))
    admin = _only_digits(admin_number)
    assigned_admin = _only_digits(sol.get("admin_asignado", ""))
    estado = str(sol.get("estado", "")).strip().upper()
    if estado in {
        hiring_repo.ESTADO_CERRADA,
        hiring_repo.ESTADO_COTIZADA,
        hiring_repo.ESTADO_DESCARTADA,
    }:
        await _send_admin(
            admin_number,
            f"La solicitud {code} ya esta en estado {estado}.\n\n"
            "No se puede tomar una solicitud finalizada.",
            buttons=[{"id": intent_service.view_id(code), "title": "Ver solicitud"}],
            codigo=code,
        )
        return None
    if estado == hiring_repo.ESTADO_EN_CONVERSACION and assigned_admin and not _same_number(assigned_admin, admin):
        await _send_admin(
            admin_number,
            f"La solicitud {code} ya la esta atendiendo {_admin_label(assigned_admin)}.\n\n"
            "Para evitar cruces, no puedo meterte en esa conversacion. Puedes "
            "ver la solicitud, pero solo el admin asignado puede responder o cerrarla.",
            buttons=[{"id": intent_service.view_id(code), "title": "Ver solicitud"}],
            codigo=code,
        )
        print(f"[admin] take_control_blocked code={code} assigned={assigned_admin} requester={admin}")
        return None
    if not client:
        await send_text_message(admin_number, f"La solicitud {code} no tiene número de cliente válido.")
        print(f"[admin] take_control_failed code={code} reason=missing_client")
        return None

    current_client = controlling_client_of(admin_number)
    if current_client and not _same_number(current_client, client):
        current_sol = hiring_repo.get_active_by_client(current_client) or hiring_repo.get_by_client(current_client) or {}
        current_code = current_sol.get("codigo_solicitud", "-")
        current_name = current_sol.get("nombre_o_dni", current_client) or current_client
        new_name = sol.get("nombre_o_dni", client) or client
        await _send_admin(
            admin_number,
            f"Ya estás atendiendo a {current_name} ({current_code}).\n\n"
            f"¿Quieres cambiar a {new_name} ({code})?",
            buttons=[
                {"id": intent_service.switch_control_id(code), "title": "Soltar y cambiar"},
                {"id": intent_service.keep_control_id(current_code), "title": "Seguir con actual"},
            ],
            codigo=code,
        )
        return None

    if current_client and _same_number(current_client, client):
        await _send_admin(
            admin_number,
            f"Ya estás atendiendo esta solicitud ({code}).\n\n"
            "Escribe tu mensaje y se enviará al cliente.",
            codigo=code,
        )
        return client

    return await _activate_control(admin_number, code, sol)


async def _activate_control(admin_number: str, code: str, sol: dict) -> str | None:
    client = _only_digits(sol.get("numero_cliente", ""))
    admin = _only_digits(admin_number)
    print(f"[admin] take_control code={code} admin={admin} client={client}")

    hiring_repo.update(code, {
        "estado": hiring_repo.ESTADO_EN_CONVERSACION,
        "admin_asignado": admin,
        "modo_atencion": "ADMIN",
    })
    conv_repo.set_state(client, conv_repo.ADMIN_CONTROL, admin_numero=admin)

    # Extrae contexto de última acción si existe
    obs_label, obs_time = _extract_last_admin_action(sol.get("observaciones", ""))
    context_block = ""
    if obs_label and obs_time:
        context_block = f"\n📋 Contexto previo:\n{obs_label} (el {obs_time})\n"

    await _send_admin(
        admin_number,
        f"✅ Tomaste el control de la solicitud {code}.{context_block}\n"
        "Desde ahora, los mensajes que escribas aquí se enviarán directamente "
        "al cliente.\n\n"
        f"Cliente: {sol.get('nombre_o_dni', '-')}\n"
        f"WhatsApp: {sol.get('numero_cliente', '-')}\n"
        f"Contacto registrado: {sol.get('numero_contacto', '-')}\n\n"
        f"Evento: {sol.get('tipo_evento', '-')}\n"
        f"Localidad: {sol.get('localidad', '-')}\n"
        f"Fecha: {sol.get('fecha_evento', '-')}\n"
        f"Horario: {sol.get('horario_evento', '-')}\n\n"
        f"Preferencia de contacto: {sol.get('observaciones', '-')}\n\n"
        "Puedes responderle cuando gustes.\n"
        "Para terminar: escribe \"cerrar solicitud\", \"marcar cotizada\" o "
        "\"descartar solicitud\".\n"
        "(\"soltar control\" devuelve la conversacion a cola, no la cierra.)",
        codigo=code,
    )
    await send_text_message(
        client,
        "Ya tenemos a alguien revisando tu solicitud 🙌\n\n"
        "Desde aquí continuará la atención por este mismo chat.",
    )
    return client


async def switch_control(admin_number: str, code: str) -> str | None:
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontre la solicitud {code}.")
        return None
    assigned_admin = _only_digits(sol.get("admin_asignado", ""))
    estado = str(sol.get("estado", "")).strip().upper()
    if estado == hiring_repo.ESTADO_EN_CONVERSACION and assigned_admin and not _same_number(assigned_admin, admin_number):
        await _send_admin(
            admin_number,
            f"No hice el cambio: la solicitud {code} ya la esta atendiendo {_admin_label(assigned_admin)}.",
            buttons=[{"id": intent_service.view_id(code), "title": "Ver solicitud"}],
            codigo=code,
        )
        return None

    current_client = controlling_client_of(admin_number)
    if current_client:
        admin = _only_digits(admin_number)
        conv_repo.set_state(current_client, conv_repo.BOT_ACTIVO)
        current_sol = hiring_repo.get_active_by_client(current_client) or hiring_repo.get_by_client(current_client)
        if current_sol:
            current_code = current_sol.get("codigo_solicitud", "")
            trace = f"{_admin_label(admin)} solto control para cambiar a otra solicitud"
            hiring_repo.update(current_code, {
                "estado": hiring_repo.ESTADO_ABIERTA,
                "modo_atencion": "BOT",
                "admin_asignado": "",
                "observaciones": _with_trace(current_sol, trace),
            })

    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return None
    return await _activate_control(admin_number, code, sol)


async def keep_control(admin_number: str, code: str = "") -> None:
    current_client = controlling_client_of(admin_number)
    current_sol = hiring_repo.get_active_by_client(current_client) if current_client else None
    current_code = (current_sol or {}).get("codigo_solicitud", code or "-")
    current_name = (current_sol or {}).get("nombre_o_dni", current_client or "") or current_client or "el cliente actual"
    await _send_admin(
        admin_number,
        f"Sigues atendiendo a {current_name} ({current_code}).\n\n"
        "Escribe tu mensaje y se enviará a esa conversación.",
        codigo=current_code,
    )


# ---------------------------------------------------------------------------
# Hacer seguimiento
# ---------------------------------------------------------------------------
async def follow_request(admin_number: str, code: str) -> None:
    """Compatibilidad con botones antiguos: deja la solicitud pendiente."""
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return

    await reply_later(admin_number, code)


async def reply_later(admin_number: str, code: str) -> None:
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return
    hiring_repo.update(code, {
        "estado": hiring_repo.ESTADO_ABIERTA,
        "modo_atencion": "BOT",
        "admin_asignado": "",
    })
    await _send_admin(
        admin_number,
        f"De acuerdo, dejamos la solicitud {code} pendiente.\n\n"
        "Si el cliente vuelve a escribir, no se creará otra solicitud; avisaremos "
        "a los administradores sobre este mismo caso.",
        buttons=[
            {"id": intent_service.take_control_id(code), "title": "Tomar control"},
            {"id": intent_service.view_id(code), "title": "Ver solicitud"},
        ],
        codigo=code,
    )


# ---------------------------------------------------------------------------
# Ver solicitud
# ---------------------------------------------------------------------------
async def view_request(admin_number: str, code: str) -> None:
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return
    await _send_admin(
        admin_number,
        f"📄 Detalle de solicitud {code}\n\n"
        f"Cliente: {sol.get('nombre_o_dni', '-')}\n"
        f"WhatsApp del cliente: {sol.get('numero_cliente', '-')}\n"
        f"Contacto registrado: {sol.get('numero_contacto', '-')}\n\n"
        f"Localidad: {sol.get('localidad', '-')}\n"
        f"Tipo de evento: {sol.get('tipo_evento', '-')}\n"
        f"Fecha: {sol.get('fecha_evento', '-')}\n"
        f"Horario: {sol.get('horario_evento', '-')}\n"
        f"Cantidad de personas: {sol.get('cantidad_personas', '-')}\n\n"
        f"Preferencia de contacto: {sol.get('observaciones', '-')}\n\n"
        f"Estado actual: {sol.get('estado', '-')}\n"
        f"Administrador asignado: {_admin_label(sol.get('admin_asignado', '')) if sol.get('admin_asignado') else 'Sin asignar'}\n\n"
        "Último mensaje:\n"
        f"\"{sol.get('ultimo_mensaje_cliente', '-')}\"",
        codigo=code,
    )


# ---------------------------------------------------------------------------
# Relevo de mensajes (cliente ⇄ administrador)
# ---------------------------------------------------------------------------
def controlling_client_of(admin_number: str) -> str | None:
    """Cliente que este administrador controla actualmente (o None)."""
    admin = _only_digits(admin_number)
    try:
        from app.repositories.sheets_client import read_records
        from app.repositories.sheets_schema import SHEET_CONVERSATIONS
        for r in read_records(SHEET_CONVERSATIONS):
            if str(r.get("estado_conversacion", "")).strip().upper() != conv_repo.ADMIN_CONTROL:
                continue
            if _only_digits(r.get("admin_numero", "")) == admin:
                client = _only_digits(r.get("numero_usuario", ""))
                if client:
                    print(f"[admin] control activo por conversacion admin={admin} client={client}")
                    return client
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error buscando control activo: {exc.__class__.__name__}")

    try:
        sol = hiring_repo.get_controlled_by_admin(admin)
        if sol:
            client = _only_digits(sol.get("numero_cliente", ""))
            code = sol.get("codigo_solicitud", "")
            if client:
                print(f"[admin] control activo por solicitud admin={admin} client={client} code={code}")
                return client
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error buscando solicitud en control: {exc.__class__.__name__}")

    print(f"[admin] sin control activo admin={admin}")
    return None


def control_context_for_client(client_number: str) -> dict | None:
    """Contexto de control activo para un cliente, si lo atiende un admin."""
    client = _only_digits(client_number)
    try:
        conv = conv_repo.get(client_number) or conv_repo.get(client) or {}
        if str(conv.get("estado_conversacion", "")).strip().upper() == conv_repo.ADMIN_CONTROL:
            admin = _only_digits(conv.get("admin_numero", ""))
            if admin:
                sol = hiring_repo.get_active_by_client(client) or hiring_repo.get_by_client(client) or {}
                code = sol.get("codigo_solicitud", "")
                print(f"[admin] cliente bajo control por conversacion client={client} admin={admin} code={code}")
                return {"client": client, "admin": admin, "code": code, "source": "conversation"}
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error leyendo control de cliente: {exc.__class__.__name__}")

    try:
        sol = hiring_repo.get_active_by_client(client)
        if not sol:
            return None
        estado = str(sol.get("estado", "")).strip().upper()
        admin = _only_digits(sol.get("admin_asignado", ""))
        if estado == hiring_repo.ESTADO_EN_CONVERSACION and admin:
            code = sol.get("codigo_solicitud", "")
            print(f"[admin] cliente bajo control por solicitud client={client} admin={admin} code={code}")
            return {"client": client, "admin": admin, "code": code, "source": "request"}
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error leyendo solicitud controlada: {exc.__class__.__name__}")

    return None


async def relay_admin_to_client(admin_number: str, client_number: str, texto: str) -> None:
    await send_text_message(client_number, texto)
    try:
        msg_repo.save({
            "numero_usuario": client_number,
            "direccion": msg_repo.ADMIN_A_CLIENTE,
            "tipo_mensaje": "text",
            "texto": texto,
            "admin_numero": _only_digits(admin_number),
        })
    except Exception:  # noqa: BLE001
        pass


async def relay_client_to_admin(client_number: str, admin_number: str, texto: str,
                                code: str = "") -> None:
    sol = hiring_repo.get_active_by_client(client_number) or hiring_repo.get_by_client(client_number) or {}
    code = code or sol.get("codigo_solicitud", "")
    nombre = sol.get("nombre_o_dni", "") or "Cliente"
    if code:
        try:
            hiring_repo.update(code, {"ultimo_mensaje_cliente": texto})
        except Exception as exc:  # noqa: BLE001
            print(f"[admin] no se pudo actualizar ultimo mensaje: {exc.__class__.__name__}")

    await send_text_message(
        admin_number,
        f"💬 {nombre} respondió"
        + (f" ({code})" if code else "")
        + f"\nWhatsApp: {_only_digits(client_number)}\n\n"
        f"{texto}",
    )
    try:
        msg_repo.save({
            "numero_usuario": client_number,
            "direccion": msg_repo.CLIENTE_A_ADMIN,
            "tipo_mensaje": "text",
            "texto": texto,
            "codigo_solicitud": code,
            "admin_numero": _only_digits(admin_number),
        })
    except Exception:  # noqa: BLE001
        pass


async def notify_followers_new_message(client_number: str, texto: str) -> None:
    """Reenvía a los administradores en seguimiento un nuevo mensaje del cliente."""
    followers = follow_up_repository.followers_for_client(client_number)
    if not followers:
        return
    sol = hiring_repo.get_by_client(client_number) or {}
    code = sol.get("codigo_solicitud", "")
    nombre = sol.get("nombre_o_dni", "-")
    cuerpo = (
        "💬 Nuevo mensaje del cliente\n\n"
        f"Solicitud: {code or '-'}\n"
        f"Cliente: {nombre}\n"
        f"WhatsApp: {client_number}\n\n"
        "Mensaje:\n"
        f"\"{texto}\""
    )
    buttons = [
        {"id": intent_service.take_control_id(code), "title": "Tomar control"},
        {"id": intent_service.reply_later_id(code), "title": "Responder luego"},
        {"id": intent_service.view_id(code), "title": "Ver solicitud"},
    ]
    for admin in followers:
        await _send_admin(admin, cuerpo, buttons=buttons if code else None, codigo=code)


async def close_current_request(admin_number: str, final_state: str, note: str = "") -> dict | None:
    """Finaliza la solicitud que el admin tiene bajo control."""
    admin = _only_digits(admin_number)
    client = controlling_client_of(admin)
    if not client:
        await send_text_message(
            admin_number,
            "No tienes ninguna conversacion bajo control para cerrar.",
        )
        return None

    sol = hiring_repo.get_active_by_client(client) or hiring_repo.get_by_client(client)
    if not sol:
        await send_text_message(admin_number, "No encontre la solicitud asociada a esta conversacion.")
        return None

    code = sol.get("codigo_solicitud", "")
    assigned_admin = _only_digits(sol.get("admin_asignado", ""))
    if assigned_admin and not _same_number(assigned_admin, admin):
        await _send_admin(
            admin_number,
            f"No puedes cerrar {code}: la esta atendiendo {_admin_label(assigned_admin)}.",
            buttons=[{"id": intent_service.view_id(code), "title": "Ver solicitud"}],
            codigo=code,
        )
        return None

    final_state = str(final_state or hiring_repo.ESTADO_CERRADA).strip().upper()
    if final_state not in {
        hiring_repo.ESTADO_CERRADA,
        hiring_repo.ESTADO_COTIZADA,
        hiring_repo.ESTADO_DESCARTADA,
    }:
        final_state = hiring_repo.ESTADO_CERRADA

    trace = f"{_admin_label(admin)} finalizo la solicitud como {final_state}"
    if note:
        trace += f". Nota: {note[:180]}"
    hiring_repo.update(code, {
        "estado": final_state,
        "modo_atencion": "CERRADO",
        "admin_asignado": admin,
        "observaciones": _with_trace(sol, trace),
    })
    conv_repo.set_state(client, conv_repo.BOT_ACTIVO)

    await _send_admin(
        admin_number,
        f"Listo, la solicitud {code} quedo en estado {final_state}.\n\n"
        "La conversacion vuelve al bot y este caso ya no cuenta como solicitud activa.",
        codigo=code,
    )
    print(f"[admin] request_closed code={code} state={final_state} admin={admin} client={client}")
    return {"codigo_solicitud": code, "estado": final_state, "numero_cliente": client}


async def release_control(admin_number: str) -> bool:
    """El administrador devuelve la conversación al bot."""
    admin = _only_digits(admin_number)
    client = controlling_client_of(admin_number)
    if not client:
        await send_text_message(admin_number, "No tienes ninguna conversación bajo control.")
        return False
    conv_repo.set_state(client, conv_repo.BOT_ACTIVO)
    sol = hiring_repo.get_by_client(client)
    if sol:
        code = sol.get("codigo_solicitud", "")
        trace = f"{_admin_label(admin)} solto control"
        hiring_repo.update(code, {
            "estado": hiring_repo.ESTADO_ABIERTA,
            "modo_atencion": "BOT",
            "admin_asignado": "",
            "observaciones": _with_trace(sol, trace),
        })
    await send_text_message(
        admin_number,
        "Listo, devolví la conversación al bot 🙌 El cliente volverá a recibir "
        "respuestas automáticas.",
    )
    return True


# ---------------------------------------------------------------------------
# Textos auxiliares
# ---------------------------------------------------------------------------
def help_text() -> str:
    return (
        "📋 Comandos disponibles:\n\n"
        "• Ver solicitudes\n"
        "• Cerrar solicitud\n"
        "• Marcar cotizada\n"
        "• Descartar solicitud\n"
        "• Soltar control\n"
        "• Métricas"
    )


def not_authorized_text() -> str:
    return "Este comando está disponible solo para administradores autorizados."


def format_recent_requests() -> str:
    try:
        requests = hiring_repo.get_recent(limit=5)
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error leyendo solicitudes: {exc.__class__.__name__}")
        requests = []

    if not requests:
        return (
            "📭 Por ahora no hay solicitudes registradas.\n\n"
            "Cuando un cliente complete el flujo de contratación aparecerá aquí."
        )

    bloques = []
    for r in requests:
        code = r.get('codigo_solicitud', '-')
        estado = r.get('estado', '-')
        admin_asignado = r.get('admin_asignado', '')

        # Muestra quién atiende cada solicitud
        admin_label = ""
        if admin_asignado and estado and estado.upper() == hiring_repo.ESTADO_EN_CONVERSACION:
            admin_label = f" [🔒 {_admin_label(admin_asignado)}]"
        elif estado and estado.upper() == hiring_repo.ESTADO_ABIERTA:
            admin_label = " [⏳ Disponible]"

        bloques.append(
            f"🔖 {code} ({estado}){admin_label}\n"
            f"👤 {r.get('nombre_o_dni', '-')} · 📞 {r.get('numero_contacto', '-')}\n"
            f"📍 {r.get('localidad', '-')} · 🎉 {r.get('tipo_evento', '-')}\n"
            f"📅 {r.get('fecha_evento', '-')} · 🕒 {r.get('horario_evento', '-')}"
        )
    return "📋 Últimas solicitudes:\n\n" + "\n\n".join(bloques)
