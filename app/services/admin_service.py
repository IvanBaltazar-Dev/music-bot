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
from app.services.whatsapp_service import (
    send_text_message,
    send_button_message,
    send_list_message,
)


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


async def _send_admin_list(numero: str, texto: str, options: list[dict],
                           button_text: str = "Ver opciones", codigo: str = ""):
    """Envía un menú tipo lista al admin y lo registra."""
    await send_list_message(numero, texto, options, button_text=button_text)
    try:
        msg_repo.save({
            "numero_usuario": numero,
            "direccion": msg_repo.ADMIN_INTERNO,
            "tipo_mensaje": "interactive",
            "texto": texto,
            "codigo_solicitud": codigo,
            "admin_numero": numero,
        })
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Menú principal de administrador
# ---------------------------------------------------------------------------
async def send_menu(numero: str) -> None:
    """Menú principal con las acciones más usadas (lista desplegable)."""
    options = [
        {"id": intent_service.MENU_VIEW_REQUESTS, "title": "Ver solicitudes",
         "description": "Lista de clientes y sus estados"},
        {"id": intent_service.MENU_REGISTER_EVENT, "title": "Registrar evento",
         "description": "Agendar una presentación"},
        {"id": intent_service.MENU_METRICS, "title": "Métricas",
         "description": "Resumen de la semana"},
        {"id": intent_service.MENU_HELP, "title": "Ayuda",
         "description": "Cómo usar el bot"},
    ]
    await _send_admin_list(
        numero,
        "🎛️ Menú de administrador\n\n¿Qué deseas hacer?",
        options,
        button_text="Abrir menú",
    )


# ---------------------------------------------------------------------------
# Notificación de nueva solicitud
# ---------------------------------------------------------------------------
def _request_summary(sol: dict) -> str:
    from app.services.formatting_service import format_timestamp_readable

    code = sol.get('codigo_solicitud', '-')
    cliente = sol.get('nombre_o_dni', '-')
    numero = sol.get('numero_cliente', '-')
    fecha_reg = sol.get('fecha_registro', '-')
    obs = sol.get('observaciones', '')

    fecha_fmt = format_timestamp_readable(fecha_reg) if fecha_reg else "-"

    return (
        f"📩 NUEVA SOLICITUD\n\n"
        f"{code} • {fecha_fmt}\n\n"
        f"👤 {cliente}\n"
        f"📞 {numero}\n"
        f"Notas: {obs if obs else '(sin notas)'}\n\n"
        "Escribe aquí tu respuesta para el cliente 👇"
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
        context_block = f"\n📋 {obs_label} (el {obs_time})"

    nombre_cliente = sol.get('nombre_o_dni', client) or client
    await _send_admin(
        admin_number,
        f"✅ Ahora atiendes a {nombre_cliente} ({code}){context_block}\n\n"
        f"📞 {client}\n"
        f"Notas: {sol.get('observaciones', '(sin notas)')}\n\n"
        "Escribe tu respuesta aquí 👇\n\n"
        "Para salir: escribe *dejar control* o *soltar*",
        codigo=code,
    )
    admin_label = _admin_label(admin)
    await send_text_message(
        client,
        f"✅ CONVERSACIÓN INICIADA CON {admin_label}\n\n"
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
# Etiquetas de estado (legibles para el admin)
# ---------------------------------------------------------------------------
_ESTADO_LABEL = {
    hiring_repo.ESTADO_ABIERTA: "🟢 Pendiente",
    hiring_repo.ESTADO_EN_SEGUIMIENTO: "👀 En seguimiento",
    hiring_repo.ESTADO_TOMADA: "✋ Tomada",
    hiring_repo.ESTADO_EN_CONVERSACION: "💬 En conversación",
    hiring_repo.ESTADO_COTIZADA: "💰 Cotizada",
    hiring_repo.ESTADO_CERRADA: "✅ Cerrada",
    hiring_repo.ESTADO_DESCARTADA: "🗑️ Descartada",
}


def _estado_label(estado: str) -> str:
    return _ESTADO_LABEL.get(str(estado or "").strip().upper(), estado or "-")


# ---------------------------------------------------------------------------
# Ver solicitud (detalle + acciones disponibles)
# ---------------------------------------------------------------------------
async def view_request(admin_number: str, code: str) -> None:
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return

    estado = str(sol.get("estado", "-")).strip().upper()
    admin_label = _admin_label(sol.get('admin_asignado', '')) if sol.get('admin_asignado') else 'Sin asignar'
    cliente = sol.get('nombre_o_dni', sol.get('numero_cliente', '-'))

    await _send_admin(
        admin_number,
        f"📄 {code}\n\n"
        f"👤 {cliente}\n"
        f"📞 {sol.get('numero_cliente', '-')}\n"
        f"Notas: {sol.get('observaciones', '(sin notas)')}\n\n"
        f"Estado: {_estado_label(estado)}\n"
        f"Responsable: {admin_label}",
        codigo=code,
    )

    # Las solicitudes finalizadas pueden reabrirse a pendiente, no más.
    finalizada = estado in {
        hiring_repo.ESTADO_CERRADA,
        hiring_repo.ESTADO_COTIZADA,
        hiring_repo.ESTADO_DESCARTADA,
    }
    if finalizada:
        options = [
            {"id": intent_service.pending_id(code), "title": "Reabrir (pendiente)",
             "description": "Vuelve a la cola de atención"},
        ]
    else:
        options = [
            {"id": intent_service.take_control_id(code), "title": "Ingresar a conversación",
             "description": "Responder al cliente tú mismo"},
            {"id": intent_service.quote_id(code), "title": "Marcar cotizada",
             "description": "Ya se envió cotización"},
            {"id": intent_service.close_id(code), "title": "Cerrar solicitud",
             "description": "Caso atendido y finalizado"},
            {"id": intent_service.discard_id(code), "title": "Descartar",
             "description": "Cliente no interesado / no procede"},
            {"id": intent_service.pending_id(code), "title": "Marcar pendiente",
             "description": "Dejar en cola para después"},
        ]
    await _send_admin_list(
        admin_number,
        f"¿Qué deseas hacer con {code}?",
        options,
        button_text="Elegir acción",
        codigo=code,
    )


# ---------------------------------------------------------------------------
# Lista de solicitudes (navegable)
# ---------------------------------------------------------------------------
async def send_requests_list(admin_number: str) -> None:
    """Envía una lista navegable de solicitudes recientes. Al elegir una,
    el admin ve el detalle y las acciones disponibles."""
    try:
        requests = hiring_repo.get_recent(limit=9)
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error leyendo solicitudes: {exc.__class__.__name__}")
        requests = []

    if not requests:
        await _send_admin(
            admin_number,
            "📭 Por ahora no hay solicitudes registradas.\n\n"
            "Cuando un cliente complete el flujo de contratación aparecerá aquí.",
        )
        return

    options = []
    for r in requests:
        code = r.get("codigo_solicitud", "-")
        estado = str(r.get("estado", "-")).strip().upper()
        cliente = r.get("nombre_o_dni") or r.get("numero_cliente", "-")
        options.append({
            "id": intent_service.view_id(code),
            "title": f"{code} · {cliente}"[:24],
            "description": _estado_label(estado),
        })

    await _send_admin_list(
        admin_number,
        "📋 Solicitudes recientes\n\nElige una para ver el detalle y las acciones.",
        options,
        button_text="Ver solicitudes",
    )


# ---------------------------------------------------------------------------
# Cambios de estado por código (desde el menú, con confirmación)
# ---------------------------------------------------------------------------
_ACTION_STATE = {
    "close": hiring_repo.ESTADO_CERRADA,
    "quote": hiring_repo.ESTADO_COTIZADA,
    "discard": hiring_repo.ESTADO_DESCARTADA,
}
_ACTION_VERB = {
    "close": "cerrar",
    "quote": "marcar como cotizada",
    "discard": "descartar",
}


async def confirm_action(admin_number: str, action: str, code: str) -> None:
    """Pide confirmación antes de un cambio de estado terminal."""
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return
    verbo = _ACTION_VERB.get(action, "cambiar")
    cliente = sol.get("nombre_o_dni") or sol.get("numero_cliente", "-")
    await _send_admin(
        admin_number,
        f"¿Seguro que quieres {verbo} la solicitud {code}?\n\n"
        f"👤 {cliente}",
        buttons=[
            {"id": intent_service.confirm_id(action, code), "title": "Sí, confirmar"},
            {"id": intent_service.BTN_CANCEL, "title": "Cancelar"},
        ],
        codigo=code,
    )


async def apply_state_by_code(admin_number: str, action: str, code: str) -> dict | None:
    """Aplica un cambio de estado terminal a una solicitud por su código."""
    final_state = _ACTION_STATE.get(action)
    if not final_state:
        return None
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return None

    admin = _only_digits(admin_number)
    trace = f"{_admin_label(admin)} marcó la solicitud como {final_state}"
    hiring_repo.update(code, {
        "estado": final_state,
        "modo_atencion": "CERRADO",
        "observaciones": _with_trace(sol, trace),
    })
    # Si el cliente estaba bajo control, devolverlo al bot.
    client = _only_digits(sol.get("numero_cliente", ""))
    if client:
        try:
            conv_repo.set_state(client, conv_repo.BOT_ACTIVO)
        except Exception:  # noqa: BLE001
            pass

    await _send_admin(
        admin_number,
        f"Listo ✅ La solicitud {code} quedó en estado {_estado_label(final_state)}.",
        codigo=code,
    )
    print(f"[admin] state_by_code code={code} state={final_state} admin={admin}")
    return {"codigo_solicitud": code, "estado": final_state, "numero_cliente": client}


async def set_pending_by_code(admin_number: str, code: str) -> dict | None:
    """Devuelve una solicitud a la cola (ABIERTA / pendiente)."""
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return None
    admin = _only_digits(admin_number)
    trace = f"{_admin_label(admin)} marcó la solicitud como pendiente"
    hiring_repo.update(code, {
        "estado": hiring_repo.ESTADO_ABIERTA,
        "modo_atencion": "BOT",
        "admin_asignado": "",
        "observaciones": _with_trace(sol, trace),
    })
    client = _only_digits(sol.get("numero_cliente", ""))
    if client:
        try:
            conv_repo.set_state(client, conv_repo.BOT_ACTIVO)
        except Exception:  # noqa: BLE001
            pass
    await _send_admin(
        admin_number,
        f"Listo 🟢 La solicitud {code} volvió a la cola como pendiente.",
        codigo=code,
    )
    return {"codigo_solicitud": code, "estado": hiring_repo.ESTADO_ABIERTA, "numero_cliente": client}


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
    admin_clean = _only_digits(admin_number)
    client_clean = _only_digits(client_number)

    # Intenta enviar el mensaje al cliente
    sent_ok = False
    try:
        await send_text_message(client_clean, texto)
        sent_ok = True
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error enviando mensaje a cliente {client_clean}: {exc.__class__.__name__}: {str(exc)[:100]}")
        await _send_admin(admin_clean, f"⚠️ Error al enviar a {client_clean}: {exc.__class__.__name__}")

    # Guarda el registro del intento (aunque haya fallado)
    try:
        msg_repo.save({
            "numero_usuario": client_clean,
            "direccion": msg_repo.ADMIN_A_CLIENTE,
            "tipo_mensaje": "text",
            "texto": texto,
            "admin_numero": admin_clean,
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error guardando mensaje admin→cliente: {exc.__class__.__name__}: {str(exc)[:100]}")


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
        "🎛️ Cómo usar el bot (admin)\n\n"
        "Escribe *menú* para ver todas las opciones con botones.\n\n"
        "Comandos rápidos:\n"
        "• *menú* — abre el menú principal\n"
        "• *ver solicitudes* — lista de clientes\n"
        "• *registrar evento* — agendar presentación\n"
        "• *métricas* — resumen de la semana\n\n"
        "⚠️ Cuando estés atendiendo a un cliente, todo lo que escribas le llega "
        "a él. Para dar un comando sin enviárselo, ponle *#* delante.\n"
        "Ejemplos: *#salir* (dejar la conversación), *#menú*, *#cerrar*."
    )


def not_authorized_text() -> str:
    return "Este comando está disponible solo para administradores autorizados."


# La lista navegable de solicitudes ahora la envía `send_requests_list`
# (mensaje interactivo). El formato de texto plano quedó obsoleto.
