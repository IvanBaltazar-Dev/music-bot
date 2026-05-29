# 🔗 Interacción entre servicios

Diagrama de cómo los servicios se comunican y coordinan.

---

## 1. Estructura general de comunicación

```
┌────────────────────────────────────────────────────────────┐
│                      FastAPI / Webhook                      │
│  /webhook GET (Meta verification)                           │
│  /webhook POST (incoming messages)                          │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ↓
    ┌─────────────────────────────────┐
    │   routes/whatsapp_webhook.py    │
    │  - Valida firma                  │
    │  - Extrae datos                  │
    │  - Delega todo a conversación   │
    └────────────┬────────────────────┘
                 │
                 ↓
    ┌────────────────────────────────────────────────┐
    │    services/conversation_service.py (HUB)      │
    │  - Orquestador central                         │
    │  - Toma todas las decisiones                   │
    │  - Coordina otros servicios                    │
    └─────────┬──────────────────────────┬───────────┘
              │                          │
    ┌─────────┴──────────────────────────┴──────────┐
    │                                                │
    ├─→ session_service ←──────────────────────────┤
    │   (sesiones + flujos)                         │
    │                                                │
    ├─→ intent_service                              │
    │   (detectar intención)                        │
    │                                                │
    ├─→ event_service                               │
    │   (consultar/crear eventos)                   │
    │                                                │
    ├─→ admin_service                               │
    │   (verificar admin, ejecutar comandos)        │
    │                                                │
    ├─→ metrics_service                             │
    │   (registrar métricas)                        │
    │                                                │
    ├─→ whatsapp_service                            │
    │   (enviar mensajes)                           │
    │                                                │
    └─→ ai_service (opcional)                       │
        (fallback IA)                               │
        
    Todos pueden acceder a:
    └─→ google_sheets_repository                    │
        (persistencia)
```

---

## 2. Flujo de un mensaje paso a paso

```
1. WEBHOOK (whatsapp_webhook.py)
   ┌──────────────────────────────────┐
   │ POST /webhook                    │
   │ body = {entry, changes, value}   │
   │                                  │
   │ _extract_message() extrae:       │
   │ from_number, text, button_id     │
   └──────────┬───────────────────────┘
              │
              ├─→ await handle_incoming_message(
              │      from_number,
              │      text,
              │      button_id
              │   )
              │
              └─→ return 200 inmediatamente
                  (WhatsApp no espera respuesta)

2. CONVERSATION SERVICE (conversation_service.py)
   ┌──────────────────────────────────────────────┐
   │ handle_incoming_message()                    │
   │                                              │
   │ 1️⃣  metrics_service.record("message_received")
   │    └─→ google_sheets_repository.save_metric
   │                                              │
   │ 2️⃣  session = session_service.get_session() │
   │    └─→ Obtiene o crea nueva sesión
   │                                              │
   │ 3️⃣  ¿INTENT_CANCEL?                         │
   │    ├─ SÍ → session_service.clear_session()  │
   │    └─ NO → continuar                        │
   │                                              │
   │ 4️⃣  ¿En flujo activo?                       │
   │    ├─ SÍ → session_service.handle_flow()    │
   │    │       └─→ Máquina de estados           │
   │    │       └─→ Avanza al siguiente estado   │
   │    │                                        │
   │    └─ NO → continuar                        │
   │                                              │
   │ 5️⃣  ¿Botón de menú?                         │
   │    ├─ SÍ → intent_service.button_to_intent()│
   │    │       └─→ Mapea botón a intención     │
   │    │                                        │
   │    └─ NO → intent_service.detect_intent()  │
   │            (reglas → fuzzy → IA)           │
   │                                              │
   │ 6️⃣  ¿Comando admin?                         │
   │    ├─ SÍ → admin_service.is_admin()?       │
   │    │       ├─ SÍ → _handle_admin_command() │
   │    │       └─ NO → "No autorizado"         │
   │    │                                        │
   │    └─ NO → _dispatch_intent()              │
   │            (ejecutar intención)            │
   │                                              │
   │ 7️⃣  ¿Flujo completado?                      │
   │    ├─ SÍ → _finalize_flow()                │
   │    │       ├─→ repo.save_*()               │
   │    │       ├─→ admin_service.notify_lead()│
   │    │       └─→ metrics_service.record()   │
   │    │                                        │
   │    └─ NO → send_text/button_message()     │
   │                                              │
   └──────────────────────────────────────────────┘
```

---

## 3. Pipeline de intención (intent_service.py)

```
detect_intent(text)
         │
         ├─1️⃣ normalize(text)
         │   └─→ lowercase, sin tildes, sin signos
         │
         ├─2️⃣ ¿Reglas coinciden?
         │   ├─ SÍ → devuelve intent ✓
         │   └─ NO → continuar
         │
         ├─3️⃣ ¿Fuzzy match con difflib?
         │   ├─ SÍ → devuelve intent ✓
         │   └─ NO → continuar
         │
         ├─4️⃣ ¿AI habilitada?
         │   ├─ SÍ → ai_service.classify_intent(text)
         │   │       │
         │   │       ├─→ Llamada a Gemini
         │   │       ├─→ Parse JSON
         │   │       ├─→ ¿confidence >= 0.6?
         │   │       │   ├─ SÍ → devuelve intent ✓
         │   │       │   └─ NO → continuar
         │   │       │
         │   │       └─ Manejo de errores (no rompe)
         │   │
         │   └─ NO → continuar
         │
         └─5️⃣ INTENT_UNKNOWN
             (fallback final)
```

---

## 4. Máquina de estados: Flujo de cotización

```
session.start_quotation()
         │
         ├─ state = quotation_location
         │
         ├─→ Usuario: "Lima"
         │
         └─ handle_flow(session, "Lima")
            │
            └─ _advance_quotation()
               │
               ├─1️⃣ ai_service.validate_and_enhance_quotation() [opcional]
               │   └─→ Si texto corto, IA lo interpreta
               │
               ├─2️⃣ Guardar: data["lugar"] = "Lima"
               │
               ├─3️⃣ state = quotation_date
               │
               ├─4️⃣ return _resp("¿Qué fecha?")

[Repite para cada estado hasta quotation_completed]

Cuando completed=True:
         │
         ├─ _finalize_flow(to, resp)
         │
         ├─ repo.save_quotation_request(data)
         │  └─→ google_sheets_repository.py
         │      ├─ Si SHEETS habilitado → guarda en hoja "Solicitudes"
         │      └─ Si no → guarda en _mem_quotations
         │
         ├─ metrics_service.record("quotation_completed", ...)
         │  └─→ google_sheets_repository.py (hoja "Metricas")
         │
         ├─ admin_service.notify_lead(data)
         │  ├─ Obtiene números de admins
         │  └─ Envía notificación a cada uno
         │      └─→ whatsapp_service.send_text_message()
         │
         ├─ session_service.clear_session(to)
         │  └─ state = IDLE, data = {}
         │
         └─ send_text_message(to, resumen)
            └─→ Usuario recibe resumen y cierra flujo
```

---

## 5. Session Service: Gestión de estado

```
┌────────────────────────────────────────┐
│     session_service (en memoria)       │
├────────────────────────────────────────┤
│ _sessions = {                          │
│   "519111111111": Session({            │
│     whatsapp: "519111111111"           │
│     state: "quotation_date"            │
│     data: {...}                        │
│   }),                                  │
│   ...                                  │
│ }                                      │
└────────────────────────────────────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
     ↓             ↓             ↓
 get_session() start_quotation() handle_flow()
 (obtiene o     (inicia flujo)   (avanza estado)
  crea nueva)


conversation_service → session_service.get_session("519111111111")
                      └─→ Devuelve Session con estado actual
                      
conversation_service → session_service.handle_flow(session, "respuesta usuario")
                      └─→ Avanza estado + devuelve próxima pregunta
                      
conversation_service → session_service.clear_session("519111111111")
                      └─→ Limpia cuando flujo termina o cancela
```

---

## 6. Admin Service: Verificación y comandos

```
admin_service.is_admin(whatsapp)
         │
         ├─ Obtiene lista de admins:
         │  │
         │  ├─ settings.admin_numbers [del .env]
         │  │
         │  └─ repo.get_active_admins() [de Sheets si habilitado]
         │     └─→ google_sheets_repository.py (hoja "Admins")
         │
         ├─ Compara números (tolerante a prefijos de país)
         │
         └─→ True o False

admin_service.notify_lead(data)
         │
         ├─ Obtiene lista de admins (igual que arriba)
         │
         └─ Para cada admin:
            └─→ whatsapp_service.send_text_message(admin_number, mensaje)

admin_service.format_recent_requests()
         │
         └─ repo.get_recent_quotation_requests(limit=5)
            └─→ google_sheets_repository.py
                ├─ Si Sheets: obtiene de hoja "Solicitudes"
                └─ Si no: obtiene de _mem_quotations
```

---

## 7. Event Service: Gestión de eventos

```
event_service.get_active_events()
         │
         └─ repo.get_active_events()
            └─→ google_sheets_repository.py (hoja "Eventos")
                ├─ Si Sheets: filtra estado = "ACTIVO"
                └─ Si no: filtra de _mem_events

event_service.format_events_response()
         │
         ├─ events = get_active_events()
         │
         ├─ Si vacío:
         │  └─ Respuesta: "Actualizando agenda..."
         │
         └─ Si hay eventos:
            └─ Formatea cada uno con emojis y detalles

event_service.create_event(event_data)
         │
         └─ repo.save_event(event_data)
            └─→ google_sheets_repository.py (hoja "Eventos")
                ├─ Si Sheets: append_row()
                └─ Si no: guardaen _mem_events
```

---

## 8. Metrics Service: Registro y cálculo

```
metrics_service.record(tipo, whatsapp, detalle)
         │
         └─ repo.save_metric_event({
              "tipo": "intent_greeting",
              "whatsapp": "519...",
              "detalle": "...",
              "fecha_hora": "2026-05-29..."
            })
            │
            ├─ Siempre guarda en _mem_metrics (para resúmenes rápidos)
            │
            └─ Si Sheets: también guarda en hoja "Metricas"

metrics_service.get_metrics_summary()
         │
         └─ repo.get_metrics_summary()
            │
            ├─ Obtiene todas las métricas
            │
            ├─ Filtra por hoy y últimos 7 días
            │
            └─ Calcula agregados:
               ├─ conversaciones_hoy
               ├─ consultas_precio_hoy
               ├─ leads_completados
               ├─ usuarios_únicos_semana
               └─ eventos_registrados

metrics_service.format_summary()
         │
         └─ Devuelve texto formateado con emojis:
            "📊 Resumen de Music Bot\nHoy:\n👋 Conversaciones: X..."
```

---

## 9. WhatsApp Service: Envíos

```
send_text_message(to, message)
         │
         ├─ _base_url()
         │  └─ https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages
         │
         ├─ _headers()
         │  └─ Authorization: Bearer {WHATSAPP_TOKEN}
         │     (NO se imprime)
         │
         ├─ payload = {
         │    "messaging_product": "whatsapp",
         │    "to": to,
         │    "type": "text",
         │    "text": {"body": message}
         │  }
         │
         └─ _post(payload)
            │
            ├─ httpx.AsyncClient.post()
            │
            ├─ ¿Status >= 400?
            │  ├─ SÍ → imprime error (sin token) → devuelve None
            │  └─ NO → devuelve response.json()
            │
            └─ Si falla red → no rompe webhook, devuelve None

send_button_message(to, body, buttons)
         │
         ├─ Payload con tipo "interactive"
         │
         ├─ _post(payload)
         │
         └─ Si falla → fallback a send_text_message()
            (no dejar al usuario sin respuesta)
```

---

## 10. AI Service: Fallback inteligente

```
ai_service.is_enabled()
         │
         ├─ ¿AI_ENABLED=true?
         ├─ ¿GEMINI_API_KEY configurado?
         ├─ ¿google-generativeai instalado?
         └─→ True o False

ai_service.classify_intent(text)
         │
         ├─ ¿No habilitado?
         │  └─ return {"success": False}
         │
         └─ Si habilitado:
            │
            ├─ genai.GenerativeModel.generate_content(prompt)
            │  └─ Prompt: "Clasifica en: greeting|events|price|contact|unknown"
            │
            ├─ Parse JSON de respuesta
            │  └─ {"intent": "...", "confidence": 0.85}
            │
            ├─ Validar intent está en lista permitida
            │
            └─ return {"success": True, "intent": "...", "confidence": ...}
               (maneja errores, no rompe)

ai_service.validate_and_enhance_quotation(state, data, text)
         │
         ├─ ¿No habilitado?
         │  └─ return None (no interviene)
         │
         └─ Si habilitado:
            │
            ├─ genai.generate_content()
            │  └─ "Extrae el valor de [campo] del mensaje"
            │
            └─ Si encuentra valor:
               └─ return {state: valor_extraído}
                  (ej: {"quotation_date": "mañana"})
```

---

## 11. Google Sheets Repository: Persistencia

```
┌────────────────────────────────────────────┐
│    google_sheets_repository.py             │
│  (Interfaz única de persistencia)          │
└────────────┬───────────────────────────────┘
             │
    ┌────────┴───────────┐
    │                    │
    ↓                    ↓
[Sheets]              [Memoria]
 (si habilitado)    (siempre)

Funciones públicas:
├─ get_active_events()
│  ├─ Intenta Sheets → Si falla o no habilitado
│  └─ Cae a _mem_events
│
├─ save_event(event)
│  ├─ Guarda siempre en _mem_events
│  ├─ Si Sheets habilitado, también guarda en Sheets
│  └─ return True/False (nunca rompe)
│
├─ save_quotation_request(data)
│  ├─ Guarda en _mem_quotations
│  └─ Si Sheets: también guarda
│
├─ get_recent_quotation_requests(limit)
│  ├─ Intenta Sheets
│  └─ Si falla → _mem_quotations
│
├─ get_active_admins()
│  ├─ Intenta leer hoja "Admins" en Sheets
│  ├─ Si falla o no habilitado → [] (lista vacía)
│  └─ Nota: .env ADMIN_PHONE_NUMBERS se lee en admin_service
│
├─ save_metric_event(data)
│  ├─ Siempre guarda en _mem_metrics
│  ├─ Si Sheets: también guarda en hoja "Metricas"
│  └─ return True
│
└─ get_metrics_summary()
   ├─ Lee de Sheets si habilitado
   ├─ Si falla → usa _mem_metrics
   └─ Devuelve dict con agregados

Fallback automático:
├─ Si GOOGLE_SHEETS_ENABLED=false → usa memoria
├─ Si GOOGLE_APPLICATION_CREDENTIALS no existe → usa memoria
├─ Si gspread no está instalado → usa memoria
├─ Si API de Google falla → usa memoria
└─ Bot SIEMPRE funciona
```

---

## 12. Tabla de dependencias

| Servicio | Depende de | Propósito |
|----------|-----------|----------|
| conversation | Todos | Orquestación |
| intent | ai (opcional) | Detectar intención |
| session | - | Estado del usuario |
| event | repo | Consultar/guardar eventos |
| admin | repo | Verificar admin, notificar |
| metrics | repo | Registrar y calcular |
| whatsapp | - | Enviar mensajes |
| ai | - | Fallback inteligente |
| repo | - | Persistencia (Sheets/memoria) |

---

## 13. Resumen: Cómo se comunican

```
┌────────────────────────────────────────────────────────┐
│                    ENTRADA: WhatsApp                   │
└────────────────┬───────────────────────────────────────┘
                 │
                 ↓
          [webhook.py]
          (delgado)
                 │
                 ↓
    [conversation_service.py]
    (orquestador central)
             │ │ │ │ │ │ │
    ┌────────┼─┼─┼─┼─┼─┼──┐
    │        │ │ │ │ │ │  │
    ↓        ↓ ↓ ↓ ↓ ↓ ↓  ↓
 [session] [intent] [event] [admin] [metrics] [whatsapp] [ai]
    │         │        │       │        │        │         │
    └─────────┴────────┴───────┴───────┴────────┴─────────┘
                       │
                       ↓
            [google_sheets_repository]
            (abstracción de persistencia)
                       │
        ┌──────────────┴──────────────┐
        ↓                             ↓
    [Sheets]                      [Memoria]
    (si habilitado)              (siempre)
        │
        ↓
    [Google Cloud]
    (opcional)

FLUJO DE DATOS:
┌──────────────────────────────────────┐
│ Usuario                              │
│ (WhatsApp)                           │
└───────────┬──────────────────────────┘
            │ (1) Envía mensaje
            ↓
        webhook
            │ (2) Extrae: from, text, button_id
            ↓
    conversation_service
            │ (3) Decide qué hacer
            │
            ├─→ (4a) Consulta session_service
            │       └─→ (5a) Obtiene o crea sesión
            │
            ├─→ (4b) Consulta intent_service
            │       ├─→ (5b) Aplica reglas + fuzzy
            │       └─→ (5c) Si fallback, consulta ai_service
            │
            ├─→ (4c) Consulta admin_service
            │       └─→ (5d) Obtiene admins de .env o repo
            │
            ├─→ (4d) Consulta metrics_service
            │       └─→ (5e) Registra en repo
            │
            └─→ (6) Envía respuesta
                   ↓
               whatsapp_service
                   │ (7) API HTTP a Meta
                   ↓
              [WhatsApp API]
                   │ (8) Entrega a usuario
                   ↓
              Usuario (WhatsApp)

CICLO CERRADO.
```

Este documento muestra cómo cada servicio se especializa, cómo se comunican y cómo la persistencia es completamente opcional e intercambiable.
