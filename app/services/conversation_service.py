"""Orquestador de la conversación (controlador principal del bot).

Mantiene el webhook delgado: recibe número + texto/botón ya extraídos, decide qué
hacer apoyándose en los servicios y envía la respuesta por WhatsApp. Coordina:

* Flujo "Quiero ir a verlos" (eventos + interés de localidad).
* Flujo "Quiero contratarlos" (delegado a `session_service`).
* Flujo "Conoce la agrupación" (contenidos desde Sheets).
* Relevo administrador ⇄ cliente ("Tomar control" / "Hacer seguimiento").
* Registro de mensajes, métricas y errores.

Frases de localidad: SIEMPRE provienen de `locality_service` (hoja Localidades),
nunca quemadas aquí.
"""

from __future__ import annotations

from app.config import settings
from app.models.session import (
    SEE_STATES,
    STATE_SEE_CITY,
    STATE_SEE_INTEREST,
    STATE_IDLE,
    STATE_ADMIN_EVENT_COLLECT,
    STATE_ADMIN_EVENT_EDIT,
    STATE_ADMIN_EVENT_EDIT_CONFIRM,
    ADMIN_EVENT_STATES,
)
from app.repositories import (
    conversation_repository as conv_repo,
    hiring_request_repository as hiring_repo,
    interest_repository,
    message_repository as msg_repo,
)
from app.services import (
    admin_service,
    error_service,
    event_service,
    group_info_service,
    hiring_service,
    intent_service,
    locality_service,
    metrics_service,
    session_service,
)
from app.services.whatsapp_service import (
    send_button_message,
    send_list_message,
    send_text_message,
)

# Nombres genéricos/placeholder que NO deben mostrarse como nombre real.
_PLACEHOLDER_NAMES = {
    "", "music bot", "la agrupacion", "la agrupación",
    "nombre de la agrupacion", "nombre de la agrupación",
}
_FALLBACK_GROUP_NAME = "Carlos Fer y Agrup. Cariño Lindo"


def group_name() -> str:
    """Nombre de la agrupación desde config; usa el oficial si es un placeholder."""
    name = (settings.GROUP_NAME or "").strip()
    if name.lower() in _PLACEHOLDER_NAMES:
        return _FALLBACK_GROUP_NAME
    return name


def _main_menu_buttons() -> list[dict]:
    return [
        {"id": intent_service.FLOW_SEE_EVENTS, "title": "Quiero ir a verlos"},
        {"id": intent_service.FLOW_HIRE, "title": "Quiero contratarlos"},
        {"id": intent_service.FLOW_KNOW_GROUP, "title": "Conoce agrupación"},
    ]


# ---------------------------------------------------------------------------
# Envío con registro de mensajes salientes
# ---------------------------------------------------------------------------
async def _send_text(to: str, text: str, *, flujo: str = "", intencion: str = ""):
    if not text:
        return
    await send_text_message(to, text)
    _log_msg(to, msg_repo.SALIENTE, text, flujo=flujo, intencion=intencion)


async def _send_buttons(to: str, text: str, buttons: list[dict], *, flujo: str = ""):
    await send_button_message(to, text, buttons)
    _log_msg(to, msg_repo.SALIENTE, text, flujo=flujo)


async def _send_menu(to: str, text: str, options: list[dict], *, button_text="Ver opciones", flujo=""):
    if len(options) > 3:
        await send_list_message(to, text, options, button_text=button_text)
    else:
        await send_button_message(to, text, options)
    _log_msg(to, msg_repo.SALIENTE, text, flujo=flujo)


def _log_msg(numero: str, direccion: str, texto: str, *, flujo="", intencion="",
             tipo="text", payload_boton="", codigo="", raw=""):
    try:
        msg_repo.save({
            "numero_usuario": numero,
            "direccion": direccion,
            "tipo_mensaje": tipo,
            "texto": (texto or "")[:1000],
            "payload_boton": payload_boton,
            "flujo_detectado": flujo,
            "intencion_detectada": intencion,
            "codigo_solicitud": codigo,
            "raw_json": (raw or "")[:1000],
        })
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Flujo de bienvenida
# ---------------------------------------------------------------------------
async def _send_greeting(to: str, profile_name: str = ""):
    metrics_service.log(to, metrics_service.GREETING, flujo="bienvenida")
    nombre = (profile_name or "").strip()
    if nombre:
        texto = (
            f"¡Hola, {nombre}! 🙌🎶\n"
            "Qué alegría tenerte por aquí.\n\n"
            f"Te damos la bienvenida al WhatsApp oficial de {group_name()}.\n\n"
            "Cuéntame, ¿qué te gustaría hacer hoy?"
        )
    else:
        texto = (
            "¡Hola! 🙌🎶\n"
            "Qué alegría tenerte por aquí.\n\n"
            f"Soy el asistente oficial de {group_name()}.\n\n"
            "Cuéntame, ¿qué te gustaría hacer hoy?"
        )
    await _send_buttons(to, texto, _main_menu_buttons(), flujo="bienvenida")


# ---------------------------------------------------------------------------
# Flujo "Quiero ir a verlos"
# ---------------------------------------------------------------------------
async def _start_see_events(to: str):
    metrics_service.log(to, metrics_service.QUIERO_IR_A_VERLOS, flujo="ver_eventos", paso="inicio")
    session_service.start_see(to)
    await _send_buttons(
        to,
        "¡Qué alegría leerte! 🙌🎶\n"
        "Queremos disfrutar contigo en nuestra próxima presentación.\n\n"
        "Cuéntanos, ¿desde dónde nos escribes?",
        [
            {"id": intent_service.BTN_CITY_HUANCAYO, "title": "Huancayo"},
            {"id": intent_service.BTN_CITY_LIMA, "title": "Lima"},
            {"id": intent_service.BTN_CITY_OTHER, "title": "Otra ciudad"},
        ],
        flujo="ver_eventos",
    )


async def _process_see_city(to: str, city_text: str):
    loc = locality_service.buscar_localidad(city_text)
    city_name = locality_service.nombre_de(loc) or city_text.strip().title()
    frase = locality_service.obtener_frase_eventos(loc)

    if frase:
        intro = f"{frase}\n\nDame un ratito, voy a despertar al planificador de eventos y reviso la agenda. 😄"
    else:
        intro = (
            f"¡Qué alegría que nos escribas desde {city_name}! 🙌🎶\n\n"
            "Dame un ratito, voy a despertar al planificador de eventos y reviso la agenda. 😄"
        )
    await _send_text(to, intro, flujo="ver_eventos")

    events = event_service.get_upcoming_confirmed(city_name)
    metrics_service.log(
        to, metrics_service.PROXIMAS_PRESENTACIONES,
        flujo="ver_eventos", ciudad=city_name, mensaje=city_text,
    )

    if len(events) > 1:
        # Varias presentaciones en la localidad: el cliente elige una.
        session = session_service.get_session(to)
        session.data["city_events"] = events[:10]
        session_service.set_state(to, STATE_IDLE)

        options = []
        for i, e in enumerate(events[:10]):
            fecha = str(e.get("fecha") or e.get("fecha_evento") or "").strip()
            lugar = str(e.get("lugar", "")).strip()
            options.append({
                "id": intent_service.client_event_pick_id(i),
                "title": (fecha or f"Presentación {i+1}")[:24],
                "description": (lugar or city_name)[:72],
            })
        await _send_menu(
            to,
            f"¡Tenemos varias fechas por {city_name}! 🎶🙌\n\nElige la que te interese:",
            options,
            button_text="Ver fechas",
            flujo="ver_eventos",
        )
    elif len(events) == 1:
        await _show_event_to_client(to, events[0])
    else:
        session = session_service.get_session(to)
        session.data["interest_city"] = city_name
        session_service.set_state(to, STATE_SEE_INTEREST)
        await _send_buttons(
            to,
            f"Por ahora no tenemos una fecha confirmada en {city_name} 🙌\n\n"
            "Pero nos encantaría saber si te gustaría que visitemos tu localidad.\n\n"
            "¿Quieres dejarnos tu interés para tenerlo en cuenta?",
            [
                {"id": intent_service.BTN_INTEREST_YES, "title": "Sí, me gustaría"},
                {"id": intent_service.BTN_OTHER_CITY, "title": "Otra ciudad"},
                {"id": intent_service.BTN_NOT_NOW, "title": "Por ahora no"},
            ],
            flujo="ver_eventos",
        )


async def _save_interest(to: str, profile_name: str = ""):
    session = session_service.get_session(to)
    city = session.data.get("interest_city", "")
    interest_repository.save(to, city, nombre=profile_name)
    metrics_service.log(to, metrics_service.INTERES_LOCALIDAD, flujo="ver_eventos", ciudad=city)
    session_service.set_state(to, STATE_IDLE)
    await _send_text(
        to,
        f"¡Listo! Tomamos nota de tu interés por {city or 'tu localidad'} 🙌🎶\n\n"
        "Apenas tengamos algo por ahí, te avisamos por aquí. ¡Gracias por el cariño!",
        flujo="ver_eventos",
    )


async def _handle_see_input(to: str, text: str, profile_name: str = ""):
    session = session_service.get_session(to)
    if session.state == STATE_SEE_CITY:
        await _process_see_city(to, text)
        return
    if session.state == STATE_SEE_INTEREST:
        norm = intent_service.normalize(text)
        if any(w in norm for w in ("si", "claro", "gustaria", "dale", "ok", "bueno")):
            await _save_interest(to, profile_name)
        elif any(w in norm for w in ("otra", "consultar", "otro")):
            session_service.set_state(to, STATE_SEE_CITY)
            await _send_text(to, "¡De una! ¿Desde qué ciudad nos escribes? 🙌", flujo="ver_eventos")
        elif any(w in norm for w in ("no", "luego", "despues", "ahora no")):
            session_service.set_state(to, STATE_IDLE)
            await _send_text(to, "¡Sin problema! Aquí estaremos cuando quieras 🙌🎶", flujo="ver_eventos")
        else:
            # Probablemente escribió otra ciudad directamente
            await _process_see_city(to, text)
        return


# ---------------------------------------------------------------------------
# Acciones sobre un evento (botones dinámicos)
# ---------------------------------------------------------------------------
async def _show_event_to_client(to: str, e: dict):
    """Guarda el evento elegido y muestra su bloque + acciones."""
    session = session_service.get_session(to)
    session.data["last_event"] = e
    session_service.set_state(to, STATE_IDLE)

    buttons = []
    if event_service.has_maps(e):
        buttons.append({"id": intent_service.BTN_HELP_ARRIVE, "title": "Ayúdame a llegar"})
    # El botón de entradas siempre aparece: da precio o conecta con un asesor.
    buttons.append({"id": intent_service.BTN_TICKETS, "title": "Quiero entradas"})
    buttons.append({"id": intent_service.BTN_SHARE, "title": "Pasar la voz"})

    await _send_buttons(to, event_service.format_event_block(e), buttons[:3], flujo="ver_eventos")


async def _pick_city_event(to: str, index_str: str):
    """El cliente eligió un evento de la lista de su ciudad."""
    eventos = session_service.get_session(to).data.get("city_events") or []
    try:
        idx = int(index_str)
    except (TypeError, ValueError):
        idx = -1
    if 0 <= idx < len(eventos):
        await _show_event_to_client(to, eventos[idx])
    else:
        await _send_text(
            to,
            "Esa opción ya no está disponible 🙈 Cuéntame otra vez desde qué "
            "ciudad nos escribes y reviso la agenda 🙌",
            flujo="ver_eventos",
        )


async def _event_action(to: str, action: str):
    e = session_service.get_session(to).data.get("last_event")
    if not e:
        await _send_text(to, "Cuéntame de nuevo desde qué ciudad nos escribes y reviso la agenda 🙌")
        return

    if action == "maps":
        url = str(e.get("google_maps_url", "")).strip()
        metrics_service.log(to, metrics_service.CONSULTA_UBICACION, flujo="ver_eventos",
                            id_evento=str(e.get("id") or e.get("id_evento") or ""))
        if url:
            await _send_text(to, f"¡Te llevo de la mano! 🗺️\n\n{url}", flujo="ver_eventos")
        else:
            await _send_text(to, "Apenas tengamos el mapa listo te lo paso por aquí 🙌", flujo="ver_eventos")
    elif action == "tickets":
        metrics_service.log(to, metrics_service.CONSULTA_ENTRADAS, flujo="ver_eventos",
                            id_evento=str(e.get("id") or e.get("id_evento") or ""))
        precio = event_service.precio_entrada(e)
        link = event_service.link_evento(e)
        if precio:
            partes = ["🎟️ ¡Vamos con las entradas! 🎶\n", f"💵 {precio}"]
            if link:
                partes.append(f"\n👉 {link}")
            await _send_text(to, "\n".join(partes), flujo="ver_eventos")
        else:
            # Sin precio cargado: avisamos a un asesor para que lo contacte.
            await _send_text(
                to,
                "🎟️ ¡Claro! Para darte el detalle exacto de las entradas, "
                "un asesor te va a escribir por aquí en un ratito 🙌",
                flujo="ver_eventos",
            )
            try:
                await admin_service.notify_ticket_interest(to, e)
            except Exception as exc:  # noqa: BLE001
                print(f"[conversation] no se pudo avisar interés de entradas: {exc.__class__.__name__}")
    elif action == "share":
        link = event_service.link_evento(e)
        base = (
            "¡Pasa la voz y vente con tu gente! 🎶🙌\n\n"
            f"📅 {e.get('fecha') or e.get('fecha_evento', '')}\n"
            f"📍 {e.get('lugar', '')} — {e.get('ciudad', '')}"
        )
        if link:
            base += f"\n\nComparte este link con tus amigos:\n{link}"
        else:
            base += "\n\n¡Cuéntales a todos! Apenas tengamos el link de la publicación te lo paso por aquí."
        await _send_text(to, base, flujo="ver_eventos")


# ---------------------------------------------------------------------------
# Flujo "Conoce la agrupación"
# ---------------------------------------------------------------------------
async def _start_know_group(to: str):
    metrics_service.log(to, metrics_service.CONOCE_AGRUPACION, flujo="conoce", paso="inicio")
    opciones = [{"id": intent_service.BTN_WHO, "title": "¿Quiénes son?"}]
    if group_info_service.has_videos():
        opciones.append({"id": intent_service.BTN_VIDEOS, "title": "Ver videos"})
    if group_info_service.has_music():
        opciones.append({"id": intent_service.BTN_MUSIC, "title": "Escuchar música"})
    if group_info_service.has_redes():
        opciones.append({"id": intent_service.BTN_SOCIAL, "title": "Redes sociales"})
    opciones.append({"id": intent_service.FLOW_HIRE, "title": "Quiero contratarlos"})

    intro = (
        "¡Claro que sí! 🙌🎶\n\n"
        "Somos una agrupación nacida con harto cariño por la música y por la "
        "gente que disfruta celebrar bonito.\n\n"
        "Te cuento un poquito o, si prefieres, te paso directo lo que quieras ver:"
    )
    await _send_menu(to, intro, opciones, button_text="Conocer más", flujo="conoce")


async def _know_group_action(to: str, button_id: str):
    if button_id == intent_service.BTN_WHO:
        await _send_text(to, group_info_service.quienes_son_text(), flujo="conoce")
    elif button_id == intent_service.BTN_VIDEOS:
        metrics_service.log(to, metrics_service.VER_VIDEOS, flujo="conoce")
        if group_info_service.has_videos():
            await _send_text(to, group_info_service.videos_text(), flujo="conoce")
        else:
            await _send_text(to, "Muy pronto subiremos videos por aquí 🙌🎶", flujo="conoce")
    elif button_id == intent_service.BTN_MUSIC:
        metrics_service.log(to, metrics_service.ESCUCHAR_MUSICA, flujo="conoce")
        if group_info_service.has_music():
            await _send_text(to, group_info_service.music_text(), flujo="conoce")
        else:
            await _send_text(to, "Pronto compartiremos nuestra música por aquí 🎶", flujo="conoce")
    elif button_id == intent_service.BTN_SOCIAL:
        metrics_service.log(to, metrics_service.REDES_SOCIALES, flujo="conoce")
        if group_info_service.has_redes():
            await _send_text(to, group_info_service.redes_text(), flujo="conoce")
        else:
            await _send_text(to, "Estamos preparando nuestras redes, ¡muy pronto! 🙌", flujo="conoce")


# ---------------------------------------------------------------------------
# Finalización de flujos guiados (efectos secundarios)
# ---------------------------------------------------------------------------
async def _finalize_flow(to: str, resp: dict):
    kind = resp.get("kind")
    data = resp.get("data", {})

    if kind == "hire":
        existing = hiring_repo.get_active_by_client(to)
        if existing:
            code = existing.get("codigo_solicitud", "")
            updates = {
                "ultimo_mensaje_cliente": data.get("ultimo_mensaje_cliente", ""),
                "observaciones": data.get("observaciones", existing.get("observaciones", "")),
            }
            hiring_repo.update(code, updates)
            refreshed = hiring_repo.get_by_code(code) or existing
            await _send_text(
                to,
                "Ya tenemos una solicitud abierta con tus datos 🙌\n\n"
                "Acabo de agregar tu último mensaje para que el manager lo revise.",
                flujo="contratar",
            )
            await admin_service.notify_request_update(
                refreshed,
                data.get("ultimo_mensaje_cliente", ""),
            )
            session_service.clear_session(to)
            return

        code, sol = hiring_service.crear_solicitud(to, data)
        nombre = data.get("nombre_o_dni", "")
        await _send_text(to, hiring_service.texto_cierre_cliente(nombre), flujo="contratar")
        metrics_service.log(
            to, metrics_service.QUIERO_CONTRATAR, flujo="contratar",
            paso="completado", ciudad=data.get("localidad", ""), codigo_solicitud=code,
        )
        try:
            await admin_service.notify_new_request(sol)
        except Exception as exc:  # noqa: BLE001
            print(f"[conversation] no se pudo notificar la solicitud: {exc.__class__.__name__}")
        conv_repo.set_state(to, conv_repo.ESPERANDO_RESPUESTA)

    elif kind == "admin_event":
        ok, error_msg = event_service.validate_event(data)
        if not ok:
            await _send_text(to, f"❌ {error_msg}", flujo="admin")
        else:
            event_id = event_service.create_event(data)
            await _send_text(to, _admin_event_confirmation(data), flujo="admin")
            metrics_service.log(to, "EVENTO_REGISTRADO", flujo="admin", id_evento=event_id)

    session_service.clear_session(to)


async def _finalize_admin_flow(to: str, resp: dict):
    """Procesa la respuesta del flujo de registro de evento del admin.

    Puede ser: un paso intermedio (texto pidiendo datos), una cancelación,
    o un evento completado y listo para validar y guardar.
    """
    if resp.get("completed") and resp.get("kind") == "admin_event":
        data = resp.get("data", {})
        ok, error_msg = event_service.validate_event(data)
        if not ok:
            # No perdemos lo recogido: volvemos a pedir el dato correcto.
            await _send_text(
                to,
                f"❌ {error_msg}\n\nCorrige ese dato y te lo confirmo de nuevo. "
                "(o escribe *#salir* para cancelar)",
                flujo="admin",
            )
            session_service.set_state(to, STATE_ADMIN_EVENT_COLLECT)
            return
        event_id = event_service.create_event(data)
        await _send_text(to, _admin_event_confirmation(data), flujo="admin")
        metrics_service.log(to, "EVENTO_REGISTRADO", flujo="admin", id_evento=event_id)
        session_service.clear_session(to)
        return

    if resp.get("text"):
        await _send_text(to, resp["text"], flujo="admin")


async def _handle_event_edit_value(to: str, text: str):
    """Recibe el nuevo valor de un campo, lo valida y pide confirmación."""
    sess = session_service.get_session(to)
    event_id = sess.data.get("edit_event_id", "")
    field = sess.data.get("edit_field", "")
    if not event_id or not field:
        session_service.clear_session(to)
        await admin_service.send_menu(to)
        return

    ok, error, valor_norm = event_service.validate_field(field, text)
    if not ok:
        # Valor inválido: se mantiene el estado para reintentar.
        await _send_text(
            to,
            f"❌ {error}\n\nManda el valor de nuevo o escribe *#salir* para cancelar.",
            flujo="admin",
        )
        return

    # Guardamos el valor pendiente y pedimos confirmación antes de aplicar.
    sess.data["edit_pending_value"] = valor_norm
    session_service.set_state(to, STATE_ADMIN_EVENT_EDIT_CONFIRM)
    await admin_service.confirm_event_field(to, event_id, field, valor_norm)


async def _apply_pending_event_edit(to: str):
    """Aplica el cambio confirmado del campo de evento."""
    sess = session_service.get_session(to)
    event_id = sess.data.get("edit_event_id", "")
    field = sess.data.get("edit_field", "")
    valor = sess.data.get("edit_pending_value", "")
    if not event_id or not field:
        session_service.clear_session(to)
        await admin_service.send_menu(to)
        return
    await admin_service.apply_event_field(to, event_id, field, valor)
    session_service.clear_session(to)
    await admin_service.view_event(to, event_id)


async def _handle_event_edit_confirm_text(to: str, text: str):
    """El admin respondió por texto (no botón) en la confirmación de edición."""
    norm = intent_service.normalize(text)
    if norm in {"si", "sí", "ok", "dale", "confirmar", "guardar", "ya"}:
        await _apply_pending_event_edit(to)
    elif norm in {"no", "cancelar", "cancela", "mejor no"}:
        session_service.clear_session(to)
        await _send_text(to, "Listo, no guardé el cambio. 👍", flujo="admin")
    else:
        await _send_text(
            to,
            "¿Guardo el cambio? Responde *sí* o *no* (o usa los botones).",
            flujo="admin",
        )


def _admin_event_confirmation(d: dict) -> str:
    return (
        "✅ Evento registrado en la agenda.\n\n"
        f"📅 {d.get('fecha_evento', '-')}\n"
        f"📍 {d.get('lugar', '-')} — {d.get('ciudad', '-')}\n"
        f"🕘 {d.get('hora_inicio', '-')}"
    )


# ---------------------------------------------------------------------------
# Comandos de administrador (texto)
# ---------------------------------------------------------------------------
# Acción terminal pedida por texto -> (verbo de confirmación)
_TEXT_ACTION = {
    intent_service.ADMIN_CLOSE_REQUEST: "close",
    intent_service.ADMIN_MARK_QUOTED: "quote",
    intent_service.ADMIN_DISCARD_REQUEST: "discard",
}


async def _handle_admin_command(to: str, command: str, text: str):
    if command == intent_service.ADMIN_MENU:
        await admin_service.send_menu(to)
    elif command == intent_service.ADMIN_REGISTER_EVENT:
        # Si el admin ya mandó datos junto al comando, los aprovechamos;
        # si no, mostramos la plantilla y entramos en modo recolección.
        parsed = session_service.parse_admin_event(text)
        if parsed.get("ciudad") and parsed.get("fecha_evento"):
            resp = session_service.start_admin_event(to, parsed)
        else:
            resp = session_service.begin_admin_event(to)
        await _send_text(to, resp["text"], flujo="admin")
    elif command == intent_service.ADMIN_VIEW_REQUESTS:
        await admin_service.send_requests_list(to)
    elif command == intent_service.ADMIN_VIEW_EVENTS:
        await admin_service.send_events_list(to)
    elif command == intent_service.ADMIN_VIEW_METRICS:
        await _send_text(to, metrics_service.format_summary(), flujo="admin")
    elif command in _TEXT_ACTION:
        # Cerrar / cotizar / descartar la solicitud que se atiende ahora.
        action = _TEXT_ACTION[command]
        client = admin_service.controlling_client_of(to)
        if client:
            sol = hiring_repo.get_active_by_client(client) or hiring_repo.get_by_client(client)
            code = (sol or {}).get("codigo_solicitud", "")
            if code:
                await admin_service.confirm_action(to, action, code)
                return
        await _send_text(
            to,
            "No estás atendiendo ninguna solicitud ahora.\n"
            "Elige una desde *ver solicitudes* 👇",
            flujo="admin",
        )
        await admin_service.send_requests_list(to)
    elif command == intent_service.ADMIN_RELEASE:
        await admin_service.release_control(to)
    elif command == intent_service.ADMIN_HELP:
        await _send_text(to, admin_service.help_text(), flujo="admin")


# Acción de botón confirmada -> (estado, métrica)
_CONFIRM_METRIC = {
    "close": metrics_service.ADMIN_CERRAR_SOLICITUD,
    "quote": metrics_service.ADMIN_COTIZAR_SOLICITUD,
    "discard": metrics_service.ADMIN_DESCARTAR_SOLICITUD,
}


async def _handle_admin_button(to: str, action: str, code: str):
    if action == "take_control":
        metrics_service.log(to, metrics_service.ADMIN_TOMAR_CONTROL, flujo="admin", codigo_solicitud=code)
        await admin_service.take_control(to, code)
    elif action == "switch_control":
        metrics_service.log(to, metrics_service.ADMIN_TOMAR_CONTROL, flujo="admin", paso="switch", codigo_solicitud=code)
        await admin_service.switch_control(to, code)
    elif action == "keep_control":
        await admin_service.keep_control(to, code)
    elif action == "follow":
        metrics_service.log(to, metrics_service.ADMIN_SEGUIMIENTO, flujo="admin", codigo_solicitud=code)
        await admin_service.follow_request(to, code)
    elif action == "view":
        await admin_service.view_request(to, code)
    elif action == "reply_later":
        await admin_service.reply_later(to, code)
    # --- Acciones de menú principal ---
    elif action == "menu_view_requests":
        await admin_service.send_requests_list(to)
    elif action == "menu_view_events":
        await admin_service.send_events_list(to)
    elif action == "menu_register_event":
        resp = session_service.begin_admin_event(to)
        await _send_text(to, resp["text"], flujo="admin")
    elif action == "menu_metrics":
        await _send_text(to, metrics_service.format_summary(), flujo="admin")
    elif action == "menu_help":
        await _send_text(to, admin_service.help_text(), flujo="admin")
    # --- Acciones sobre una solicitud (piden confirmación) ---
    elif action in ("close", "quote", "discard"):
        await admin_service.confirm_action(to, action, code)
    elif action == "pending":
        await admin_service.set_pending_by_code(to, code)
    # --- Confirmaciones ---
    elif action in ("confirm_close", "confirm_quote", "confirm_discard"):
        verb = action.replace("confirm_", "")
        result = await admin_service.apply_state_by_code(to, verb, code)
        if result:
            metrics_service.log(
                to, _CONFIRM_METRIC.get(verb, ""),
                flujo="admin", codigo_solicitud=result.get("codigo_solicitud", ""),
            )
    # --- Acciones de eventos (CRUD) ---
    elif action == "event_view":
        await admin_service.view_event(to, code)
    elif action == "event_edit":
        await admin_service.send_event_field_menu(to, code)
    elif action == "event_field":
        # code = "<campo>~<id_evento>" (separador '~' porque los campos llevan '_')
        field, _, event_id = code.partition("~")
        session_service.set_state(to, STATE_ADMIN_EVENT_EDIT)
        sess = session_service.get_session(to)
        sess.data = {"edit_event_id": event_id, "edit_field": field}
        await _send_text(
            to,
            f"Escribe el nuevo valor para {admin_service.event_field_label(field)} "
            f"del evento {event_id}.\n\n(o *#salir* para cancelar)",
            flujo="admin",
        )
    elif action == "event_cancel":
        await admin_service.confirm_cancel_event(to, code)
    elif action == "event_cancel_ok":
        await admin_service.cancel_event(to, code)
    elif action == "event_edit_ok":
        await _apply_pending_event_edit(to)
    elif action == "cancel":
        # Si había una edición a medias, la descartamos.
        session_service.clear_session(to)
        await _send_text(to, "Acción cancelada. No se hizo ningún cambio.", flujo="admin")


# ---------------------------------------------------------------------------
# Dispatcher de botones de cliente
# ---------------------------------------------------------------------------
async def _dispatch_client_button(to: str, button_id: str, profile_name: str) -> bool:
    """Devuelve True si el botón fue manejado."""
    mapped = intent_service.button_to_intent(button_id)
    if mapped == intent_service.INTENT_SEE_EVENTS:
        await _start_see_events(to)
        return True
    if mapped == intent_service.INTENT_HIRE:
        await _start_hire(to)
        return True
    if mapped == intent_service.INTENT_KNOW_GROUP:
        await _start_know_group(to)
        return True

    if button_id in (intent_service.BTN_CITY_HUANCAYO, intent_service.BTN_CITY_LIMA):
        session_service.set_state(to, STATE_SEE_CITY)
        await _process_see_city(to, "Huancayo" if button_id == intent_service.BTN_CITY_HUANCAYO else "Lima")
        return True
    if button_id == intent_service.BTN_CITY_OTHER:
        session_service.set_state(to, STATE_SEE_CITY)
        await _send_text(to, "¡De una! Cuéntame, ¿desde qué ciudad nos escribes? 🙌", flujo="ver_eventos")
        return True

    if button_id.startswith(intent_service.PREFIX_CLIENT_EVENT_PICK):
        await _pick_city_event(to, button_id[len(intent_service.PREFIX_CLIENT_EVENT_PICK):])
        return True

    if button_id == intent_service.BTN_HELP_ARRIVE:
        await _event_action(to, "maps")
        return True
    if button_id == intent_service.BTN_TICKETS:
        await _event_action(to, "tickets")
        return True
    if button_id == intent_service.BTN_SHARE:
        await _event_action(to, "share")
        return True

    if button_id == intent_service.BTN_INTEREST_YES:
        await _save_interest(to, profile_name)
        return True
    if button_id == intent_service.BTN_OTHER_CITY:
        session_service.set_state(to, STATE_SEE_CITY)
        await _send_text(to, "¡De una! ¿Desde qué ciudad nos escribes? 🙌", flujo="ver_eventos")
        return True
    if button_id == intent_service.BTN_NOT_NOW:
        session_service.set_state(to, STATE_IDLE)
        await _send_text(to, "¡Sin problema! Aquí estaremos cuando quieras 🙌🎶")
        return True

    if button_id in (intent_service.BTN_WHO, intent_service.BTN_VIDEOS,
                     intent_service.BTN_MUSIC, intent_service.BTN_SOCIAL):
        await _know_group_action(to, button_id)
        return True

    return False


async def _start_hire(to: str):
    existing = hiring_repo.get_active_by_client(to)
    if existing:
        await _handle_existing_hire_request(
            to,
            "El cliente volvió a pedir contratación, pero ya tenía una solicitud abierta.",
        )
        return
    metrics_service.log(to, metrics_service.QUIERO_CONTRATAR, flujo="contratar", paso="inicio")
    resp = session_service.start_hire(to)
    await _send_text(to, resp["text"], flujo="contratar")


async def _handle_existing_hire_request(to: str, text: str) -> bool:
    sol = hiring_repo.get_active_by_client(to)
    if not sol:
        return False

    code = sol.get("codigo_solicitud", "")
    if code:
        hiring_repo.update(code, {"ultimo_mensaje_cliente": text})
        sol = hiring_repo.get_by_code(code) or sol

    await _send_text(
        to,
        "Ya tenemos tu solicitud en cola 🙌\n\n"
        "No voy a crear otra para no mezclar datos. Le aviso al manager que volviste "
        "a escribir por este mismo caso.",
        flujo="contratar",
    )
    try:
        await admin_service.notify_request_update(sol, text)
    except Exception as exc:  # noqa: BLE001
        print(f"[conversation] no se pudo notificar actualización: {exc.__class__.__name__}")
    return True


# ---------------------------------------------------------------------------
# Despacho de intención pública (texto libre)
# ---------------------------------------------------------------------------
async def _dispatch_intent(to: str, intent: str, profile_name: str, text: str = ""):
    if intent == intent_service.INTENT_GREETING:
        await _send_greeting(to, profile_name)
    elif intent == intent_service.INTENT_SEE_EVENTS:
        print(f"[events] intent_detected={intent} text={text!r}")
        metrics_service.log(
            to, metrics_service.PROXIMAS_PRESENTACIONES,
            flujo="ver_eventos", paso="consulta_directa", mensaje=text,
        )
        await _send_text(
            to,
            event_service.build_events_response(),
            flujo="ver_eventos",
            intencion=intent,
        )
    elif intent == intent_service.INTENT_HIRE:
        await _start_hire(to)
    elif intent == intent_service.INTENT_KNOW_GROUP:
        await _start_know_group(to)
    elif intent == intent_service.INTENT_CONTACT:
        await _handle_contact(to, profile_name, text)
    elif intent == intent_service.INTENT_OFF_TOPIC:
        # Fuera de tema: NO se responde la consulta; se redirige amablemente.
        metrics_service.log(to, "FUERA_DE_TEMA", mensaje=text)
        await _send_buttons(
            to,
            "Por aquí te ayudo con todo lo de la agrupación 🎶 "
            "(ver presentaciones, contratarnos o conocernos).\n\n"
            "¿Qué te gustaría hacer?",
            _main_menu_buttons(),
        )
    else:  # UNKNOWN -> nunca inventamos respuesta; ofrecemos el menú.
        metrics_service.log(to, metrics_service.UNKNOWN, mensaje=text)
        await _send_buttons(
            to,
            "Gracias por tu mensaje 🙌 Para ayudarte mejor, cuéntame qué te "
            "gustaría hacer hoy:",
            _main_menu_buttons(),
        )


async def _handle_contact(to: str, profile_name: str, text: str):
    """El cliente quiere comunicarse / que lo contacten. Atendemos por aquí y
    avisamos a un asesor (sin exponer números)."""
    metrics_service.log(to, "CONTACTO", flujo="contacto", mensaje=text)
    await _send_buttons(
        to,
        "¡Claro! Por aquí mismo te atendemos 🙌 En breve un asesor puede "
        "escribirte por este chat.\n\nMientras tanto, ¿te ayudo con algo de esto?",
        _main_menu_buttons(),
        flujo="contacto",
    )
    try:
        await admin_service.notify_contact_request(to, text, profile_name)
    except Exception as exc:  # noqa: BLE001
        print(f"[conversation] no se pudo avisar contacto: {exc.__class__.__name__}")


# ---------------------------------------------------------------------------
# Punto de entrada único
# ---------------------------------------------------------------------------
async def handle_incoming_message(
    from_number: str,
    text: str = "",
    button_id: str = "",
    profile_name: str = "",
    raw_json: str = "",
):
    try:
        await _route(from_number, text, button_id, profile_name, raw_json)
    except Exception as exc:  # noqa: BLE001 - el webhook nunca debe caerse
        print(f"[conversation] error: {exc.__class__.__name__}: {exc}")
        try:
            await error_service.log_error(
                "conversation_service", exc,
                numero_usuario=from_number, mensaje_usuario=text or button_id,
            )
        except Exception:  # noqa: BLE001
            pass


async def _route(from_number: str, text: str, button_id: str, profile_name: str, raw_json: str):
    # 0) Registrar mensaje entrante + asegurar registro de Conversación
    _log_msg(
        from_number, msg_repo.ENTRANTE, text or "",
        tipo="interactive" if button_id else "text",
        payload_boton=button_id, raw=raw_json,
    )
    try:
        conv_repo.upsert(from_number, {})  # crea/actualiza la fila de Conversaciones
    except Exception:  # noqa: BLE001
        pass

    is_admin = admin_service.is_admin(from_number)

    # 1) Administrador: nunca debe caer al flujo de cliente.
    if is_admin:
        print(f"[admin] inbound number={from_number} button={bool(button_id)}")
        if button_id:
            parsed = intent_service.parse_admin_button(button_id)
            if parsed:
                await _handle_admin_button(from_number, parsed[0], parsed[1])
            else:
                await admin_service.send_menu(from_number)
            return

        if text:
            is_hash = intent_service.is_hash_command(text)
            cliente = admin_service.controlling_client_of(from_number)

            # En conversación con un cliente: el texto normal SIEMPRE se le
            # reenvía. Para dar un comando, el admin antepone '#'.
            if cliente and not is_hash:
                await admin_service.relay_admin_to_client(from_number, cliente, text)
                return

            command_text = intent_service.strip_hash(text) if is_hash else text

            # Flujo de evento en curso (registro o edición).
            admin_session = session_service.get_session(from_number)
            if admin_session.state in ADMIN_EVENT_STATES:
                if is_hash:
                    # '#' cancela el flujo y libera para ejecutar el comando.
                    session_service.clear_session(from_number)
                elif admin_session.state == STATE_ADMIN_EVENT_EDIT:
                    await _handle_event_edit_value(from_number, text)
                    return
                elif admin_session.state == STATE_ADMIN_EVENT_EDIT_CONFIRM:
                    await _handle_event_edit_confirm_text(from_number, text)
                    return
                else:
                    resp = session_service.handle_flow(admin_session, text)
                    await _finalize_admin_flow(from_number, resp)
                    return

            command = intent_service.detect_admin_command(command_text)
            if command:
                await _handle_admin_command(from_number, command, command_text)
                return

            # '#' sin comando reconocido: salir del control si lo hay, y menú.
            if is_hash:
                if cliente:
                    await admin_service.release_control(from_number)
                else:
                    await admin_service.send_menu(from_number)
                return

            # Texto suelto sin contexto: mostrar el menú.
            await admin_service.send_menu(from_number)
            return

        await admin_service.send_menu(from_number)
        return

    # 2) Cliente bajo control de un administrador: no responde el bot
    control = admin_service.control_context_for_client(from_number)
    if control:
        admin_asignado = control.get("admin", "")
        code = control.get("code", "")
        if admin_asignado and text:
            try:
                conv_repo.set_state(from_number, conv_repo.ADMIN_CONTROL, admin_numero=admin_asignado)
            except Exception as exc:  # noqa: BLE001
                print(f"[conversation] no se pudo reparar estado ADMIN_CONTROL: {exc.__class__.__name__}")
            await admin_service.relay_client_to_admin(from_number, admin_asignado, text, code=code)
        return

    # 3) Cancelar / reiniciar en cualquier momento
    if text and not button_id and intent_service.detect_intent(text) == intent_service.INTENT_CANCEL:
        session_service.clear_session(from_number)
        conv_repo.set_state(from_number, conv_repo.BOT_ACTIVO)
        await _send_text(from_number, "Listo, volvemos a empezar 😊 ¿Qué te gustaría hacer?")
        await _send_greeting(from_number, profile_name)
        return

    # 4) Botones de cliente (flujos y acciones)
    if button_id:
        handled = await _dispatch_client_button(from_number, button_id, profile_name)
        if handled:
            await _notify_followers_if_any(from_number, text or button_id)
            return

    session = session_service.get_session(from_number)

    # 5) Flujo "Quiero ir a verlos" (entrada de ciudad por texto)
    if session.state in SEE_STATES:
        await _handle_see_input(from_number, text, profile_name)
        await _notify_followers_if_any(from_number, text)
        return

    # 6) Flujo guiado activo (contratar / registrar evento)
    if session.in_flow():
        resp = session_service.handle_flow(session, text)
        if resp.get("completed"):
            await _finalize_flow(from_number, resp)
        elif resp.get("text"):
            await _send_text(from_number, resp["text"])
        await _notify_followers_if_any(from_number, text)
        return

    # 7) Solicitud abierta: no crear otra, avisar a admins.
    if text and not button_id:
        handled_existing = await _handle_existing_hire_request(from_number, text)
        if handled_existing:
            return

    # 8) Intención pública
    await _dispatch_intent(from_number, intent_service.detect_intent(text), profile_name, text)
    await _notify_followers_if_any(from_number, text)


async def _notify_followers_if_any(client_number: str, texto: str):
    """Si hay administradores en seguimiento, reenvíales el nuevo mensaje."""
    if not texto:
        return
    try:
        await admin_service.notify_followers_new_message(client_number, texto)
    except Exception as exc:  # noqa: BLE001
        print(f"[conversation] error notificando seguidores: {exc.__class__.__name__}")
