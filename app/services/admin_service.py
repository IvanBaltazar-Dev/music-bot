"""Servicio de administración.

Reúne la lógica para administradores autorizados:
* Identificación (por .env y por la hoja `Administradores`).
* Notificación de nuevas solicitudes de contratación con botones de acción.
* "Tomar control" (relevo bot → administrador) y "Hacer seguimiento".
* Reenvío de mensajes cliente ⇄ administrador cuando hay control activo.

Todo mensaje saliente se registra en la hoja `Mensajes` para trazabilidad.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.security import mask_identifier
from app.repositories import (
    admin_repository,
    conversation_repository as conv_repo,
    event_repository,
    follow_up_repository,
    hiring_request_repository as hiring_repo,
    message_repository as msg_repo,
)
from app.services import event_service, intent_service
from app.services.whatsapp_service import (
    send_text_message,
    send_button_message,
    send_list_message,
    send_template_message,
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


def _client_label(sol: dict, fallback: str = "Cliente sin nombre") -> str:
    return str(sol.get("nombre_o_dni", "") or "").strip() or fallback


def _extract_last_admin_action(observaciones: str) -> tuple[str, str]:
    """Extrae la última acción de admin (qué pasó y cuándo) de observaciones.

    Devuelve (accion, fecha_legible_peru) o ("", "") si no hay historial.
    Ejemplo: "[2026-06-02T01:25:39+00:00] Julio (519...) solto control"
    Devuelve ("Julio (519...) solto control", "1 jun, 8:25 p. m.")
    """
    from app.services.formatting_service import format_datetime_peru

    if not observaciones:
        return "", ""

    # Última línea que sea una marca de actividad ([fecha] ...).
    trace_lines = [ln.strip() for ln in str(observaciones).splitlines()
                   if ln.strip().startswith("[")]
    if not trace_lines:
        return "", ""

    last_line = trace_lines[-1]
    try:
        end_bracket = last_line.find("]")
        if end_bracket < 1:
            return "", ""
        timestamp_str = last_line[1:end_bracket]
        rest = last_line[end_bracket + 1:].strip()
        if not rest:
            return "", ""
        return rest, format_datetime_peru(timestamp_str)
    except Exception:  # noqa: BLE001
        return "", ""


def _with_trace(sol: dict, message: str) -> str:
    current = str(sol.get("observaciones", "") or "").strip()
    stamp = datetime.now(timezone.utc).isoformat()
    trace = f"[{stamp}] {message}"
    if not current:
        return trace
    return current + "\n" + trace


def _parse_dt(value: str):
    try:
        dt = datetime.fromisoformat(str(value or ""))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _control_expired(conv: dict) -> bool:
    hours = max(int(getattr(settings, "ADMIN_CONTROL_TIMEOUT_HOURS", 48) or 48), 1)
    base = _parse_dt(conv.get("fecha_toma_control", "")) or _parse_dt(conv.get("fecha_ultima_interaccion", ""))
    if not base:
        return False
    return datetime.now(timezone.utc) - base > timedelta(hours=hours)


def _expire_control_for_client(client_number: str, admin_number: str, sol: dict | None = None) -> dict | None:
    client = _only_digits(client_number)
    admin = _only_digits(admin_number)
    sol = sol or hiring_repo.get_active_by_client(client) or hiring_repo.get_by_client(client)
    conv_repo.set_state(client, conv_repo.BOT_ACTIVO)
    if sol:
        code = sol.get("codigo_solicitud", "")
        trace = f"Control de {_admin_label(admin)} vencio por inactividad"
        if code:
            ok = hiring_repo.update(code, {
                "estado": hiring_repo.ESTADO_ABIERTA,
                "modo_atencion": "BOT",
                "admin_asignado": "",
                "observaciones": _with_trace(sol, trace),
            })
            if ok:
                sol = hiring_repo.get_by_code(code) or sol
            else:
                print(f"[admin] no se pudo expirar control: code={code}")
    print(f"[admin] control_expired client={mask_identifier(client)} admin={mask_identifier(admin)}")
    return sol


def _clean_notes(observaciones: str) -> str:
    """Devuelve solo las notas legibles (sin el historial técnico [fecha] ...)."""
    if not observaciones:
        return ""
    utiles = [
        ln.strip() for ln in str(observaciones).splitlines()
        if ln.strip() and not ln.strip().startswith("[")
    ]
    return " · ".join(utiles)


# Etiquetas de quién habla en el transcript
_DIR_LABEL = {
    msg_repo.ENTRANTE: "👤",
    msg_repo.CLIENTE_A_ADMIN: "👤",
    msg_repo.SALIENTE: "🤖",
    msg_repo.ADMIN_A_CLIENTE: "🧑‍💼",
}


def _format_transcript(client_number: str, nombre: str = "", limit: int = 5) -> str:
    """Arma un mini-historial de los últimos mensajes con el cliente."""
    try:
        mensajes = msg_repo.recent_for_client(client_number, limit=max(limit * 3, limit))
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] no se pudo leer el hilo: {exc.__class__.__name__}")
        mensajes = []

    if not mensajes:
        return ""

    quien_cliente = (nombre or "Cliente").split()[0]
    lineas = []
    seen = set()
    for m in mensajes:
        direccion = str(m.get("direccion", "")).strip().upper()
        if direccion in {msg_repo.ADMIN_A_CLIENTE, msg_repo.ADMIN_INTERNO, msg_repo.CLIENTE_A_ADMIN}:
            continue
        icono = _DIR_LABEL.get(direccion, "•")
        quien = quien_cliente if icono == "👤" else ("Bot" if icono == "🤖" else "Tú")
        texto = str(m.get("texto", "")).strip().replace("\n", " ")
        if not texto:
            continue
        dedupe_key = (direccion, " ".join(texto.lower().split()))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        if len(texto) > 90:
            texto = texto[:87] + "…"
        lineas.append(f"{icono} {quien}: {texto}")

    return "\n".join(lineas[-limit:])


def _conversation_context_line(sol: dict, transcript: str) -> str:
    client = _only_digits(sol.get("numero_cliente", ""))
    nombre = _client_label(sol, client)
    ultimo_cliente = str(sol.get("ultimo_mensaje_cliente", "") or "").strip()
    request_data = {
        "tipo_evento": sol.get("tipo_evento", ""),
        "fecha_evento": sol.get("fecha_evento", ""),
        "horario_evento": sol.get("horario_evento", ""),
        "localidad": sol.get("localidad", ""),
        "observaciones": _clean_notes(sol.get("observaciones", "")),
        "ultimo_mensaje_cliente": ultimo_cliente,
    }
    try:
        from app.services import gemini_service
        ai_summary = gemini_service.summarize_admin_context(nombre, request_data, transcript)
        if ai_summary:
            return ai_summary
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] no se pudo resumir con IA: {exc.__class__.__name__}")

    if ultimo_cliente:
        return f"Contexto anterior: ultimo mensaje del cliente: {ultimo_cliente}"
    if transcript:
        return "Contexto anterior: revisa los ultimos mensajes para retomar sin perder el hilo."
    return "Contexto anterior: no hay historial de mensajes guardado; retoma con los datos de la solicitud."


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
        result = await send_button_message(numero, texto, buttons)
    else:
        result = await send_text_message(numero, texto)
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
    return result is not None


async def _send_admin_list(numero: str, texto: str, options: list[dict],
                           button_text: str = "Ver opciones", codigo: str = ""):
    """Envía un menú tipo lista al admin y lo registra.

    Salvaguarda: WhatsApp solo admite 10 filas por lista. Si llegan más, se
    recortan (no debería pasar; los llamadores ya limitan) y se deja aviso.
    """
    if len(options) > 10:
        print(f"[admin] lista con {len(options)} filas recortada a 10 (límite de WhatsApp)")
        options = options[:10]
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
        {"id": intent_service.MENU_VIEW_EVENTS, "title": "Ver eventos",
         "description": "Agenda: ver, editar o cancelar"},
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
    from app.services.formatting_service import format_datetime_peru

    code = sol.get('codigo_solicitud', '-')
    cliente = _client_label(sol)
    numero = sol.get('numero_cliente', '-')
    fecha_reg = sol.get('fecha_registro', '')
    notas = _clean_notes(sol.get('observaciones', ''))
    ultimo_cliente = str(sol.get("ultimo_mensaje_cliente", "") or "").strip()

    fecha_fmt = format_datetime_peru(fecha_reg) if fecha_reg else "-"

    bloques = [
        "📩 NUEVA SOLICITUD",
        f"{code} • {fecha_fmt}",
        f"👤 {cliente}\n📞 {numero}",
    ]

    detalle = _event_details(sol)
    if detalle:
        bloques.append(detalle)

    if ultimo_cliente:
        bloques.append(f"Ultimo mensaje del cliente: {ultimo_cliente}")
    if notas:
        bloques.append(f"📝 Nota: {notas}")

    # Quién la atendió por última vez (si hay registro previo)
    accion, cuando = _extract_last_admin_action(sol.get("observaciones", ""))
    if accion and cuando:
        bloques.append(f"🕓 Última atención: {accion} ({cuando})")
    else:
        bloques.append("🕓 Última atención: aún sin atender")

    bloques.append("Escribe aquí tu respuesta para el cliente 👇")
    return "\n\n".join(bloques)


def _action_buttons(code: str) -> list[dict]:
    return [
        {"id": intent_service.take_control_id(code), "title": "Tomar control"},
        {"id": intent_service.view_id(code), "title": "Ver solicitud"},
        {"id": intent_service.reply_later_id(code), "title": "Responder luego"},
    ]


async def notify_new_request(sol: dict) -> dict:
    """Notifica a todos los administradores de una nueva solicitud abierta."""
    admins = admin_numbers()
    if not admins:
        print("[admin] no hay administradores configurados para notificar.")
        return {"configured": 0, "delivered": 0, "failed": 0}
    texto = _request_summary(sol)
    code = sol.get("codigo_solicitud", "")
    buttons = _action_buttons(code)
    delivered = 0
    failed = 0
    print(f"[admin] notification_start code={code or '-'} admins={len(admins)}")
    for numero in admins:
        ok = False
        try:
            if settings.ADMIN_NOTIFICATION_TEMPLATE_NAME:
                template_result = await send_template_message(
                    numero,
                    settings.ADMIN_NOTIFICATION_TEMPLATE_NAME,
                    [
                        code or "-",
                        _client_label(sol),
                        sol.get("fecha_evento", "-"),
                        sol.get("localidad", "-"),
                        sol.get("tipo_evento", "-"),
                    ],
                    language=settings.ADMIN_NOTIFICATION_TEMPLATE_LANGUAGE,
                )
                ok = template_result is not None
                if not ok:
                    ok = await _send_admin(
                        numero, texto, buttons=buttons, codigo=code
                    )
            else:
                ok = await _send_admin(
                    numero, texto, buttons=buttons, codigo=code
                )
        except Exception as exc:  # noqa: BLE001
            print(
                f"[admin] notification_exception code={code or '-'} "
                f"admin={mask_identifier(numero)} error={exc.__class__.__name__}"
            )
        if ok:
            delivered += 1
            print(
                f"[admin] notification_delivered code={code or '-'} "
                f"admin={mask_identifier(numero)}"
            )
        else:
            failed += 1
            print(
                f"[admin] notification_failed code={code or '-'} "
                f"admin={mask_identifier(numero)}"
            )
    return {
        "configured": len(admins),
        "delivered": delivered,
        "failed": failed,
    }


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
        f"Cliente: {_client_label(sol)}\n"
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
        print(
            f"[admin] take_control_blocked code={code} "
            f"assigned={mask_identifier(assigned_admin)} requester={mask_identifier(admin)}"
        )
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
    print(f"[admin] take_control code={code} admin={mask_identifier(admin)} client={mask_identifier(client)}")
    remember_last_code(admin_number, code)

    ok = hiring_repo.update(code, {
        "estado": hiring_repo.ESTADO_EN_CONVERSACION,
        "admin_asignado": admin,
        "modo_atencion": "ADMIN",
    })
    if not ok:
        await send_text_message(
            admin_number,
            f"⚠️ Error de conexión: no se pudo establecer control sobre {code}.\n\n"
            f"Verifica tu conexión a internet e intenta de nuevo.",
        )
        return None

    conv_repo.set_state(client, conv_repo.ADMIN_CONTROL, admin_numero=admin)

    nombre_cliente = sol.get('nombre_o_dni', client) or client
    await _send_admin(
        admin_number,
        _context_summary(sol, header=f"Atiendes a {nombre_cliente} ({code})")
        + "\n\nPuedes pedir el resumen de la conversacion con *#resumen* o *#ultimos mensajes*.\n\n"
        "*TODO LO QUE ENVIES DE AHORA EN ADELANTE SERA ENVIADO AL CLIENTE*\n"
        "Para salir sin enviar nada: *#salir*",
        codigo=code,
    )

    # Mensaje para el cliente: corto, alegre y sin revelar lo interno.
    await send_text_message(
        client,
        "Listo, ya estamos viendo tu solicitud. En un momento te escribe el "
        "manager por aquí mismo.",
    )
    return client


def _event_details(sol: dict) -> str:
    """Líneas con lo que pidió el cliente (solo los campos que existan)."""
    detalle = []
    if sol.get("tipo_evento"):
        detalle.append(f"🎉 Tipo: {sol['tipo_evento']}")
    if sol.get("fecha_evento"):
        detalle.append(f"📅 Fecha: {sol['fecha_evento']}")
    if sol.get("horario_evento"):
        detalle.append(f"🕒 Hora: {sol['horario_evento']}")
    if sol.get("localidad"):
        detalle.append(f"📍 Lugar: {sol['localidad']}")
    return "\n".join(detalle)


def _context_summary(sol: dict, header: str = "") -> str:
    """Resumen para que un admin entre con contexto. Separa claramente:
    - lo que pidió el cliente (evento + nota),
    - si ya lo atendió otro asistente (o nadie todavía),
    - la conversación reciente con el bot (si hay registro)."""
    client = _only_digits(sol.get("numero_cliente", ""))
    nombre_cliente = sol.get("nombre_o_dni", client) or client
    notas = _clean_notes(sol.get("observaciones", ""))
    ultimo_cliente = str(sol.get("ultimo_mensaje_cliente", "") or "").strip()
    accion, cuando = _extract_last_admin_action(sol.get("observaciones", ""))
    detalle = _event_details(sol)
    transcript = _format_transcript(client, nombre_cliente, limit=8)

    bloques = []
    if header:
        bloques.append(f"👤 {header}")
    bloques.append(f"📞 {client}")
    if detalle:
        bloques.append(detalle)
    bloques.append(_conversation_context_line(sol, transcript))
    if notas:
        bloques.append(f"📝 Nota: {notas}")

    # 1) Estado de atención por un asistente humano (distinto del bot).
    if accion and cuando:
        bloques.append(f"🕓 Última atención: {accion} ({cuando})")
    else:
        bloques.append("🕓 Todavía ningún asistente lo ha atendido (lo trae el bot).")

    # 2) Conversación con el bot. Solo se muestra si hay registro; si no, no
    #    afirmamos que el cliente nunca habló (sí completó su solicitud).
    if transcript:
        bloques.append("💬 Conversación reciente:\n" + transcript)

    return "\n\n".join(bloques)


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
            ok = hiring_repo.update(current_code, {
                "estado": hiring_repo.ESTADO_ABIERTA,
                "modo_atencion": "BOT",
                "admin_asignado": "",
                "observaciones": _with_trace(current_sol, trace),
            })
            if not ok:
                await _send_admin(
                    admin_number,
                    f"⚠️ Error de conexión: no se pudo liberar la solicitud anterior {current_code}.\n\n"
                    f"Escribe *#salir* para intentar liberar manualmente, luego intenta cambiar de solicitud.",
                    codigo=code,
                )
                return None

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
    ok = hiring_repo.update(code, {
        "estado": hiring_repo.ESTADO_ABIERTA,
        "modo_atencion": "BOT",
        "admin_asignado": "",
    })
    if not ok:
        await _send_admin(
            admin_number,
            f"⚠️ Error de conexión: no se pudo dejar {code} pendiente.\n\n"
            f"Intenta de nuevo. Si sigue fallando, escribe *#salir* para liberar la conversación.",
            codigo=code,
        )
        return
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
# Última solicitud que cada admin vio/atendió (para "dame el resumen de este
# cliente" cuando ya no está en control). Memoria simple en proceso.
_last_code_by_admin: dict = {}


def remember_last_code(admin_number: str, code: str) -> None:
    admin = _only_digits(admin_number)
    if admin and code:
        _last_code_by_admin[admin] = code


def get_last_code(admin_number: str) -> str:
    return _last_code_by_admin.get(_only_digits(admin_number), "")


def _resolve_request_reference(admin_number: str, text: str = "", code: str = "") -> dict | None:
    ref = (code or "").strip()
    if ref:
        sol = hiring_repo.get_by_code(ref)
        if sol:
            return sol

    code_match = re.search(r"\bSOL-\d+\b", (text or "").upper())
    if code_match:
        sol = hiring_repo.get_by_code(code_match.group(0))
        if sol:
            return sol

    for digits in reversed(re.findall(r"\d{6,}", text or "")):
        sol = hiring_repo.get_by_client_fragment(digits)
        if sol:
            return sol

    last_code = get_last_code(admin_number)
    return hiring_repo.get_by_code(last_code) if last_code else None


async def send_client_summary(admin_number: str, code: str = "", text: str = "") -> None:
    """Muestra el resumen/contexto de un cliente para que el admin entienda a
    quién atiende. Si no se indica código, usa el último que tocó este admin;
    si no hay, la solicitud más reciente."""
    sol = _resolve_request_reference(admin_number, text=text, code=code)
    if not sol:
        recientes = hiring_repo.get_recent(limit=1)
        sol = recientes[0] if recientes else None
    if not sol:
        await send_text_message(
            admin_number,
            "Todavía no hay solicitudes para resumir. Cuando un cliente escriba, "
            "aquí te muestro el contexto. Escribe *ver solicitudes* para la lista.",
        )
        return

    code = sol.get("codigo_solicitud", "")
    remember_last_code(admin_number, code)
    estado = str(sol.get("estado", "-")).strip().upper()
    cliente = _client_label(sol, sol.get("numero_cliente", "-"))
    resumen = _context_summary(sol, header=f"{cliente} ({code})")
    await _send_admin(
        admin_number,
        "🧾 Resumen del cliente\n\n" + resumen + f"\n\nEstado: {_estado_label(estado)}",
        codigo=code,
    )


async def view_request(admin_number: str, code: str) -> None:
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return

    remember_last_code(admin_number, code)
    estado = str(sol.get("estado", "-")).strip().upper()
    admin_label = _admin_label(sol.get('admin_asignado', '')) if sol.get('admin_asignado') else 'Sin asignar'

    resumen = _context_summary(sol, header=f"{_client_label(sol, sol.get('numero_cliente', '-'))} ({code})")
    estado_block = f"Estado: {_estado_label(estado)}\nResponsable: {admin_label}"

    await _send_admin(admin_number, resumen + "\n\n" + estado_block, codigo=code)

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
# WhatsApp limita las listas interactivas a 10 filas en total.
_MAX_LIST_ROWS = 10


async def send_requests_list(admin_number: str) -> None:
    """Envía una lista navegable de solicitudes. Prioriza las pendientes/activas,
    nunca supera el límite de WhatsApp y avisa si quedan más fuera de la lista."""
    try:
        # Traemos un universo acotado (las más recientes) y priorizamos aquí.
        todas = hiring_repo.get_recent(limit=200)
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error leyendo solicitudes: {exc.__class__.__name__}")
        todas = []

    if not todas:
        await _send_admin(
            admin_number,
            "📭 No hay solicitudes registradas.\n\n"
            "Cuando un cliente complete su solicitud, aparecerá aquí.",
        )
        return

    def _is_activa(r) -> bool:
        return str(r.get("estado", "")).strip().upper() in hiring_repo.ACTIVE_STATES

    activas = [r for r in todas if _is_activa(r)]
    finalizadas = [r for r in todas if not _is_activa(r)]
    # Primero lo accionable (pendientes/activas), luego las finalizadas recientes.
    ordenadas = activas + finalizadas
    mostrar = ordenadas[:_MAX_LIST_ROWS]
    restantes = len(ordenadas) - len(mostrar)

    options = []
    for r in mostrar:
        code = r.get("codigo_solicitud", "-")
        estado = str(r.get("estado", "-")).strip().upper()
        cliente = r.get("nombre_o_dni") or r.get("numero_cliente", "-")
        options.append({
            "id": intent_service.view_id(code),
            "title": f"{code} · {cliente}"[:24],
            "description": _estado_label(estado),
        })

    # Encabezado informativo: cuántas pendientes hay y si quedan fuera.
    cuerpo = [f"📋 Solicitudes ({len(activas)} pendientes de {len(todas)} en total)"]
    if restantes > 0:
        cuerpo.append(
            f"Mostrando {len(mostrar)} (las pendientes primero). "
            f"Quedan {restantes} fuera: ve resolviéndolas o ciérralas para "
            "destrabar la lista."
        )
        print(f"[admin] requests_list truncada: mostradas={len(mostrar)} restantes={restantes}")
    cuerpo.append("Elige una para ver el detalle y las acciones.")

    await _send_admin_list(
        admin_number,
        "\n\n".join(cuerpo),
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
        f"Confirma la acción: ¿{verbo} la solicitud {code}?\n\n"
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
    ok = hiring_repo.update(code, {
        "estado": final_state,
        "modo_atencion": "CERRADO",
        "observaciones": _with_trace(sol, trace),
    })
    if not ok:
        await _send_admin(
            admin_number,
            f"⚠️ Error de conexión: no se pudo guardar el cambio de {code}.\n\n"
            f"Sigue {_estado_label(final_state)} en el sistema. Intenta de nuevo en un momento. "
            f"Si sigue fallando, escribe *#salir* para intentar liberar la conversación.",
            codigo=code,
        )
        return None

    # Si el cliente estaba bajo control, devolverlo al bot.
    client = _only_digits(sol.get("numero_cliente", ""))
    if client:
        try:
            conv_repo.set_state(client, conv_repo.BOT_ACTIVO)
        except Exception:  # noqa: BLE001
            pass

    mensajes_ok = {
        hiring_repo.ESTADO_CERRADA: f"✅ Solicitud {code} cerrada.",
        hiring_repo.ESTADO_COTIZADA: f"✅ Solicitud {code} marcada como cotizada.",
        hiring_repo.ESTADO_DESCARTADA: f"✅ Solicitud {code} descartada.",
    }
    await _send_admin(
        admin_number,
        mensajes_ok.get(final_state, f"✅ {code} quedó en {_estado_label(final_state)}."),
        codigo=code,
    )
    print(f"[admin] state_by_code code={code} state={final_state} admin={mask_identifier(admin)}")
    return {"codigo_solicitud": code, "estado": final_state, "numero_cliente": client}


async def set_pending_by_code(admin_number: str, code: str) -> dict | None:
    """Devuelve una solicitud a la cola (ABIERTA / pendiente)."""
    sol = hiring_repo.get_by_code(code)
    if not sol:
        await send_text_message(admin_number, f"No encontré la solicitud {code}.")
        return None
    admin = _only_digits(admin_number)
    trace = f"{_admin_label(admin)} marcó la solicitud como pendiente"
    ok = hiring_repo.update(code, {
        "estado": hiring_repo.ESTADO_ABIERTA,
        "modo_atencion": "BOT",
        "admin_asignado": "",
        "observaciones": _with_trace(sol, trace),
    })
    if not ok:
        await _send_admin(
            admin_number,
            f"⚠️ Error de conexión: no se pudo marcar {code} como pendiente.\n\n"
            f"Intenta de nuevo en un momento. Si sigue fallando, escribe *#salir* para liberar la conversación.",
            codigo=code,
        )
        return None
    client = _only_digits(sol.get("numero_cliente", ""))
    if client:
        try:
            conv_repo.set_state(client, conv_repo.BOT_ACTIVO)
        except Exception:  # noqa: BLE001
            pass
    await _send_admin(
        admin_number,
        f"🟢 Solicitud {code} marcada como pendiente. Vuelve a la cola de atención.",
        codigo=code,
    )
    return {"codigo_solicitud": code, "estado": hiring_repo.ESTADO_ABIERTA, "numero_cliente": client}


# ---------------------------------------------------------------------------
# Administración de eventos (CRUD)
# ---------------------------------------------------------------------------
ESTADO_EVENTO_CANCELADO = "CANCELADO"
_EVENTO_ACTIVO = {"ACTIVO", "CONFIRMADO"}

# Campos editables: clave de la hoja -> etiqueta para el admin.
EVENT_EDIT_FIELDS = [
    ("fecha_evento", "📅 Fecha"),
    ("hora_inicio", "🕒 Hora"),
    ("lugar", "📍 Lugar"),
    ("ciudad", "🏙️ Ciudad"),
    ("google_maps_url", "🗺️ Mapa"),
    ("precio_entrada", "🎟️ Precio entrada"),
    ("link_evento", "🔗 Link del evento"),
]
_EVENT_FIELD_LABEL = dict(EVENT_EDIT_FIELDS)


def _event_is_active(e: dict) -> bool:
    return str(e.get("estado", "")).strip().upper() in _EVENTO_ACTIVO


def _event_row_title(e: dict) -> str:
    fecha = event_service.display_date(e.get("fecha_evento", ""))
    ciudad = str(e.get("ciudad", "")).strip()
    return f"{fecha} · {ciudad}".strip(" ·") or e.get("id_evento", "evento")


def _event_field_display(e: dict, field: str) -> str:
    """Valor actual legible de un campo (fecha como DD/MM/YYYY, no serial)."""
    if field == "fecha_evento":
        return event_service.display_date(e.get("fecha_evento", ""))
    return str(e.get(field, "") or "").strip()


def _event_detail_text(e: dict) -> str:
    estado = str(e.get("estado", "-")).strip().upper()
    estado_lbl = "✅ Activo" if _event_is_active(e) else f"🚫 {estado or 'Cancelado'}"
    lineas = [
        f"🗓️ Evento {e.get('id_evento', '-')} — {estado_lbl}",
        f"📅 Fecha: {event_service.display_date(e.get('fecha_evento')) or '-'}",
        f"🕒 Hora: {e.get('hora_inicio') or '-'}",
        f"📍 Lugar: {e.get('lugar') or '-'} — {e.get('ciudad') or '-'}",
        f"🗺️ Mapa: {e.get('google_maps_url') or '-'}",
        f"🎟️ Precio: {e.get('precio_entrada') or '(sin precio)'}",
        f"🔗 Link: {e.get('link_evento') or '-'}",
    ]
    return "\n".join(lineas)


async def confirm_event_field(admin_number: str, event_id: str, field: str, nuevo_valor: str) -> None:
    """Muestra el cambio propuesto y pide confirmación antes de guardar."""
    e = event_repository.get_by_id(event_id)
    if not e:
        await send_text_message(admin_number, f"No encontré el evento {event_id}.")
        return
    actual = _event_field_display(e, field)
    await _send_admin(
        admin_number,
        f"Vas a cambiar {event_field_label(field)} del evento {event_id}:\n\n"
        f"Antes: {actual or '(vacío)'}\n"
        f"Ahora: {nuevo_valor}\n\n"
        "¿Confirmas el cambio?",
        buttons=[
            {"id": intent_service.BTN_EVENT_EDIT_OK, "title": "Sí, guardar"},
            {"id": intent_service.BTN_CANCEL, "title": "Cancelar"},
        ],
        codigo=event_id,
    )


async def send_events_list(admin_number: str) -> None:
    """Lista navegable de eventos (activos primero). Tope de 10 filas."""
    try:
        eventos = event_repository.get_all()
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error leyendo eventos: {exc.__class__.__name__}")
        eventos = []

    if not eventos:
        await _send_admin(
            admin_number,
            "📭 No hay eventos registrados.\n\n"
            "Usa *registrar evento* (o el menú) para agendar el primero.",
        )
        return

    activos = [e for e in eventos if _event_is_active(e)]
    cancelados = [e for e in eventos if not _event_is_active(e)]
    ordenados = activos + cancelados
    mostrar = ordenados[:_MAX_LIST_ROWS]
    restantes = len(ordenados) - len(mostrar)

    options = []
    for e in mostrar:
        estado = str(e.get("estado", "-")).strip().upper()
        options.append({
            "id": intent_service.event_view_id(e.get("id_evento", "")),
            "title": _event_row_title(e)[:24],
            "description": ("✅ Activo" if _event_is_active(e) else f"🚫 {estado}"),
        })

    cuerpo = [f"🗓️ Eventos ({len(activos)} activos de {len(eventos)} en total)"]
    if restantes > 0:
        cuerpo.append(f"Mostrando {len(mostrar)}. Quedan {restantes} fuera de la lista.")
    cuerpo.append("Elige uno para ver el detalle y las acciones.")

    await _send_admin_list(
        admin_number, "\n\n".join(cuerpo), options, button_text="Ver eventos",
    )


async def view_event(admin_number: str, event_id: str) -> None:
    """Detalle del evento + acciones (editar / cancelar / reactivar)."""
    e = event_repository.get_by_id(event_id)
    if not e:
        await send_text_message(admin_number, f"No encontré el evento {event_id}.")
        return

    await _send_admin(admin_number, _event_detail_text(e), codigo=event_id)

    if _event_is_active(e):
        options = [
            {"id": intent_service.event_edit_id(event_id), "title": "✏️ Editar",
             "description": "Cambiar fecha, hora, lugar, precio, link…"},
            {"id": intent_service.event_cancel_id(event_id), "title": "🚫 Cancelar evento",
             "description": "Deja de mostrarse al cliente"},
        ]
    else:
        options = [
            {"id": intent_service.event_edit_id(event_id), "title": "✏️ Editar",
             "description": "Corregir datos del evento"},
        ]
    await _send_admin_list(
        admin_number, f"¿Qué deseas hacer con el evento {event_id}?",
        options, button_text="Elegir acción", codigo=event_id,
    )


async def send_event_field_menu(admin_number: str, event_id: str) -> None:
    """Muestra los campos editables de un evento."""
    e = event_repository.get_by_id(event_id)
    if not e:
        await send_text_message(admin_number, f"No encontré el evento {event_id}.")
        return
    options = [
        {"id": intent_service.event_field_id(field, event_id), "title": label[:24]}
        for field, label in EVENT_EDIT_FIELDS
    ]
    await _send_admin_list(
        admin_number,
        f"✏️ Editar evento {event_id}\n\n¿Qué campo quieres cambiar?",
        options, button_text="Elegir campo", codigo=event_id,
    )


def event_field_label(field: str) -> str:
    return _EVENT_FIELD_LABEL.get(field, field)


async def apply_event_field(admin_number: str, event_id: str, field: str, valor: str) -> bool:
    """Valida y guarda el nuevo valor de un campo. Devuelve True si guardó."""
    ok, error, valor_norm = event_service.validate_field(field, valor)
    if not ok:
        await send_text_message(admin_number, f"❌ {error}\n\nManda el valor de nuevo o escribe *#salir*.")
        return False
    if not event_repository.get_by_id(event_id):
        await send_text_message(admin_number, f"No encontré el evento {event_id}.")
        return True  # no reintentar
    event_repository.update(event_id, {field: valor_norm})
    e = event_repository.get_by_id(event_id) or {}
    await _send_admin(
        admin_number,
        f"✅ {event_field_label(field)} actualizado.\n\n" + _event_detail_text(e),
        codigo=event_id,
    )
    return True


async def confirm_cancel_event(admin_number: str, event_id: str) -> None:
    e = event_repository.get_by_id(event_id)
    if not e:
        await send_text_message(admin_number, f"No encontré el evento {event_id}.")
        return
    await _send_admin(
        admin_number,
        f"¿Cancelar el evento {event_id}?\n\n"
        f"{_event_row_title(e)}\n\n"
        "Dejará de mostrarse a los clientes (no se borra).",
        buttons=[
            {"id": intent_service.event_cancel_ok_id(event_id), "title": "Sí, cancelar"},
            {"id": intent_service.BTN_CANCEL, "title": "No"},
        ],
        codigo=event_id,
    )


async def cancel_event(admin_number: str, event_id: str) -> None:
    e = event_repository.get_by_id(event_id)
    if not e:
        await send_text_message(admin_number, f"No encontré el evento {event_id}.")
        return
    event_repository.update(event_id, {"estado": ESTADO_EVENTO_CANCELADO})
    await _send_admin(
        admin_number,
        f"🚫 Evento {event_id} cancelado. Ya no se muestra a los clientes.",
        codigo=event_id,
    )


async def notify_contact_request(client_number: str, texto: str, nombre: str = "") -> None:
    """Avisa a los admins que un cliente quiere comunicarse / que lo contacten."""
    admins = admin_numbers()
    if not admins:
        return
    cliente = nombre or client_number
    cuerpo = (
        "📞 Un cliente quiere comunicarse\n\n"
        f"👤 {cliente}\n📞 {_only_digits(client_number)}\n\n"
        "Mensaje:\n"
        f"\"{(texto or '').strip()[:300]}\"\n\n"
        "Escríbele por este chat para atenderlo."
    )
    for numero in admins:
        await _send_admin(numero, cuerpo)


async def notify_ticket_interest(client_number: str, event: dict, nombre: str = "") -> None:
    """Avisa a los admins que un cliente quiere info de entradas de un evento."""
    admins = admin_numbers()
    if not admins:
        return
    cliente = nombre or client_number
    cuerpo = (
        "🎟️ Un cliente quiere info de ENTRADAS\n\n"
        f"👤 {cliente}\n📞 {_only_digits(client_number)}\n\n"
        f"Evento: {_event_row_title(event)}\n"
        f"({event.get('id_evento', '-')})\n\n"
        "Aún no hay precio cargado para este evento. Contáctalo o carga el precio."
    )
    for numero in admins:
        await _send_admin(numero, cuerpo)


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
                    sol = hiring_repo.get_active_by_client(client) or hiring_repo.get_by_client(client) or {}
                    sol_estado = str(sol.get("estado", "")).strip().upper()
                    sol_admin = _only_digits(sol.get("admin_asignado", ""))
                    if sol_estado != hiring_repo.ESTADO_EN_CONVERSACION or not _same_number(sol_admin, admin):
                        try:
                            conv_repo.set_state(client, conv_repo.BOT_ACTIVO)
                        except Exception as exc:  # noqa: BLE001
                            print(f"[admin] no se pudo limpiar control stale: {exc.__class__.__name__}")
                        print(
                            "[admin] control stale ignorado "
                            f"admin={mask_identifier(admin)} client={mask_identifier(client)}"
                        )
                        continue
                    print(
                        "[admin] control activo por conversacion "
                        f"admin={mask_identifier(admin)} client={mask_identifier(client)}"
                    )
                    return client
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error buscando control activo: {exc.__class__.__name__}")

    try:
        sol = hiring_repo.get_controlled_by_admin(admin)
        if sol:
            client = _only_digits(sol.get("numero_cliente", ""))
            code = sol.get("codigo_solicitud", "")
            if client:
                print(
                    "[admin] control activo por solicitud "
                    f"admin={mask_identifier(admin)} client={mask_identifier(client)} code={code}"
                )
                return client
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error buscando solicitud en control: {exc.__class__.__name__}")

    print(f"[admin] sin control activo admin={mask_identifier(admin)}")
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
                sol_estado = str(sol.get("estado", "")).strip().upper()
                sol_admin = _only_digits(sol.get("admin_asignado", ""))
                if sol_estado != hiring_repo.ESTADO_EN_CONVERSACION or not _same_number(sol_admin, admin):
                    try:
                        conv_repo.set_state(client, conv_repo.BOT_ACTIVO)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[admin] no se pudo limpiar control stale cliente: {exc.__class__.__name__}")
                    print(
                        "[admin] control stale de cliente ignorado "
                        f"client={mask_identifier(client)} admin={mask_identifier(admin)}"
                    )
                    return None
                if _control_expired(conv):
                    _expire_control_for_client(client, admin, sol)
                    return None
                code = sol.get("codigo_solicitud", "")
                print(
                    "[admin] cliente bajo control por conversacion "
                    f"client={mask_identifier(client)} admin={mask_identifier(admin)} code={code}"
                )
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
            faux_conv = {
                "fecha_toma_control": sol.get("fecha_toma_control", ""),
                "fecha_ultima_interaccion": sol.get("fecha_ultima_interaccion", ""),
            }
            if _control_expired(faux_conv):
                _expire_control_for_client(client, admin, sol)
                return None
            code = sol.get("codigo_solicitud", "")
            print(
                "[admin] cliente bajo control por solicitud "
                f"client={mask_identifier(client)} admin={mask_identifier(admin)} code={code}"
            )
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
        print(f"[admin] error enviando mensaje a cliente {mask_identifier(client_clean)}: {exc.__class__.__name__}")
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
        print(f"[admin] error guardando mensaje admin→cliente: {exc.__class__.__name__}")


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
    nombre = _client_label(sol)
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
    ok = hiring_repo.update(code, {
        "estado": final_state,
        "modo_atencion": "CERRADO",
        "admin_asignado": admin,
        "observaciones": _with_trace(sol, trace),
    })
    if not ok:
        await _send_admin(
            admin_number,
            f"⚠️ Error de conexión: no se pudo cerrar {code}.\n\n"
            f"Intenta de nuevo en un momento. Si sigue fallando, escribe *#salir* para liberar la conversación.",
            codigo=code,
        )
        return None

    conv_repo.set_state(client, conv_repo.BOT_ACTIVO)

    await _send_admin(
        admin_number,
        f"Listo, la solicitud {code} quedo en estado {final_state}.\n\n"
        "La conversacion vuelve al bot y este caso ya no cuenta como solicitud activa.",
        codigo=code,
    )
    print(
        f"[admin] request_closed code={code} state={final_state} "
        f"admin={mask_identifier(admin)} client={mask_identifier(client)}"
    )
    return {"codigo_solicitud": code, "estado": final_state, "numero_cliente": client}


async def release_control(admin_number: str) -> bool:
    """El administrador devuelve la conversación al bot."""
    admin = _only_digits(admin_number)
    client = controlling_client_of(admin_number)
    trace = f"[{datetime.now(timezone.utc).isoformat()}] {_admin_label(admin)} solto control"

    released_clients = []
    released_sols = []
    try:
        released_clients = conv_repo.release_control_for_admin(admin)
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error liberando conversaciones: {exc.__class__.__name__}")
    try:
        released_sols = hiring_repo.release_control_by_admin(admin, trace)
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] error liberando solicitudes: {exc.__class__.__name__}")

    if client and client not in released_clients:
        try:
            conv_repo.set_state(client, conv_repo.BOT_ACTIVO)
            released_clients.append(client)
        except Exception as exc:  # noqa: BLE001
            print(f"[admin] error liberando conversacion actual: {exc.__class__.__name__}")

    sol = hiring_repo.get_by_client(client) if client else None
    if sol and str(sol.get("estado", "")).strip().upper() == hiring_repo.ESTADO_EN_CONVERSACION:
        code = sol.get("codigo_solicitud", "")
        try:
            ok = hiring_repo.update(code, {
                "estado": hiring_repo.ESTADO_ABIERTA,
                "modo_atencion": "BOT",
                "admin_asignado": "",
                "observaciones": _with_trace(sol, f"{_admin_label(admin)} solto control"),
            })
            if ok:
                released_sols.append(sol)
            else:
                print(f"[admin] no se pudo liberar solicitud en release_control: code={code}")
        except Exception as exc:  # noqa: BLE001
            print(f"[admin] error liberando solicitud actual: {exc.__class__.__name__}")

    still_client = controlling_client_of(admin_number)
    if still_client:
        await send_text_message(
            admin_number,
            "Intente salir, pero todavia veo una conversacion activa. "
            "No envies mensajes normales aun; usa #salir otra vez o revisa la hoja.",
        )
        return False

    if not client and not released_clients and not released_sols:
        await send_text_message(
            admin_number,
            "No estas atendiendo ninguna conversacion en este momento.",
        )
        return False

    await send_text_message(
        admin_number,
        "Saliste de la conversacion. El bot retoma la atencion automatica.",
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
        "• *ver eventos* — agenda: ver, editar o cancelar\n"
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
