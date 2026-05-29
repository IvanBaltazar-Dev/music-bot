# 🔄 Flujo de funcionamiento del Music Bot

Documento que explica cómo fluye un mensaje desde WhatsApp hasta la respuesta, incluidas las decisiones, servicios involucrados y capas.

---

## 1. Flujo general de un mensaje

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ENTRADA: WhatsApp                             │
│  Un usuario o admin envía un mensaje o presiona un botón             │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ↓
        ┌─────────────────────────────────┐
        │   webhook.py (DELGADO)          │
        │  - Verifica firma                │
        │  - Extrae: número, texto/botón  │
        │  - Delega a conversation_service│
        └────────────┬────────────────────┘
                     │
                     ↓
        ┌─────────────────────────────────────────────┐
        │   conversation_service.py (ORQUESTADOR)     │
        │  - Punto de entrada: handle_incoming_message│
        │  - Coordina servicios                        │
        │  - Aplica lógica de negocio                 │
        └────────────┬────────────────────────────────┘
                     │
     ┌───────────────┴───────────────┐
     │                               │
     ↓                               ↓
┌──────────────────────┐  ┌──────────────────────────────┐
│ USUARIO NORMAL      │  │ USUARIO ADMIN                 │
│ (cliente)           │  │ (número en ADMIN_PHONE_NUMBERS)
└──────────────────────┘  └──────────────────────────────┘
     │                               │
     ├─→ ¿Cancelar? ────────────────┤─→ ¿Cancelar?
     │                               │
     ├─→ ¿En flujo activo?          │   ├─→ ¿Comando admin?
     │   (cotización)               │   │   (registrar evento, solicitudes, etc.)
     │                               │   │
     ├─→ ¿Botón de menú?            │   ├─→ Ejecutar comando
     │                               │   │
     └─→ ¿Intención pública?        │   └─→ Mostrar resultado
         (greeting, events, price)  │
                                     │
                                     └─→ Mostrar resultado
```

---

## 2. Árbol de decisiones: Detección de intención

```
Mensaje del usuario llega a conversation_service
         │
         ↓
    ¿Está en un flujo activo?
    (quotation_*, admin_event_*)
    │
    ├─ SÍ → handle_flow()
    │       (máquina de estados para cotizaciones/eventos)
    │       └─ Respuesta: siguiente pregunta del flujo
    │
    └─ NO →  ¿Presionó un botón?
             │
             ├─ SÍ (button_id) → Mapear botón a intención
             │                  └─ "menu_price" → INTENT_PRICE
             │
             └─ NO (texto) →  ¿Es comando admin?
                              │
                              ├─ SÍ → admin_service
                              │       ├─ registrar evento → start_admin_event()
                              │       ├─ solicitudes → format_recent_requests()
                              │       ├─ métricas → format_summary()
                              │       └─ ayuda → help_text()
                              │
                              └─ NO → detect_intent(text)
                                      │
                                      ├─ Reglas + normalización
                                      │  (hola, eventos, precio, contacto)
                                      │
                                      ├─ Fuzzy matching (difflib)
                                      │  (hla→hola, presio→precio)
                                      │
                                      ├─ IA Gemini (si habilitada)
                                      │  (fallback para ambigüedad)
                                      │
                                      └─ Si todo falla → INTENT_UNKNOWN
                                         └─ Mostrar menú con botones
```

---

## 3. Pipeline de detección de intención (intent_service.py)

### 3.1 Normalización

```
Entrada: "¡Holaaaa! 😊"
         │
         ↓ normalize()
         ├─ lowercase    → "¡holaaaa! 😊"
         ├─ strip tildes → "¡holaaaa! 😊" (no hay)
         ├─ quitar signos → "holaaaa"
         ├─ trim espacios → "holaaaa"
         │
         ↓
Salida: "holaaaa"
```

### 3.2 Búsqueda en palabras clave

```
Normalizado: "holaaaa"
         │
         ├─ ¿Exacta en keywords de GREETING?
         │  ["hola", "ola", "buenas", "hey", "hi"]
         │  → NO
         │
         ├─ ¿Contiene token de GREETING?
         │  → NO (después de split no coincide)
         │
         └─ ¿Fuzzy match con cutoff=0.75?
            ├─ difflib.get_close_matches("holaaaa", keywords, cutoff=0.75)
            │  → "hola" (similitud ~0.86)
            │
            ↓
            INTENT_GREETING ✓
```

### 3.3 Si reglas fallan: IA

```
INTENT_UNKNOWN (reglas + fuzzy no encontraron nada)
         │
         ├─ ¿AI_ENABLED = true?
         │  Y ¿GEMINI_API_KEY configurado?
         │
         ├─ SÍ → ai_service.classify_intent(text)
         │       │
         │       ├─ Llamada a Gemini
         │       ├─ Parse JSON
         │       ├─ intent + confidence
         │       │
         │       ├─ ¿confidence >= 0.6?
         │       │  ├─ SÍ → usar intent de IA
         │       │  └─ NO → INTENT_UNKNOWN
         │
         └─ NO → INTENT_UNKNOWN
```

---

## 4. Flujo de cotización (cliente)

Cuando el usuario elige "Consultar precio" o dice "precio":

```
START: INTENT_PRICE
         │
         ↓
session_service.start_quotation()
         │
         ├─ Crear sesión
         ├─ State = quotation_location
         ├─ Inicializar data = {whatsapp: "519..."}
         │
         ↓
Pregunta 1: "¿Para qué ciudad?"
─────────────────────────────────────
Usuario responde: "Lima Norte"
         │
         ↓
_advance_quotation(session, "Lima Norte")
         │
         ├─ ¿IA habilitada?
         │  └─ validate_and_enhance_quotation() [opcional]
         │
         ├─ Guardar: data["lugar"] = "Lima Norte"
         ├─ State = quotation_date
         │
         ↓
Pregunta 2: "¿Qué fecha?"
─────────────────────────────────────
Usuario responde: "15 de junio"
         │
         ↓
_advance_quotation(session, "15 de junio")
         │
         ├─ data["fecha_evento"] = "15 de junio"
         ├─ State = quotation_event_type
         │
         ↓
Pregunta 3: "¿Tipo de evento?" [BOTONES]
─────────────────────────────────────────
Opciones: Cumpleaños | Boda | Corporativo
Usuario presiona: "Cumpleaños"
         │
         ↓
_advance_quotation(session, "Cumpleaños")
         │
         ├─ data["tipo_evento"] = "Cumpleaños"
         ├─ State = quotation_duration
         │
         ↓
Pregunta 4: "¿Cuántas horas?"
─────────────────────────────
Usuario responde: "2 horas"
         │
         ↓
_advance_quotation(session, "2 horas")
         │
         ├─ data["duracion"] = "2 horas"
         ├─ State = quotation_name
         │
         ↓
Pregunta 5: "¿Cuál es tu nombre?"
──────────────────────────────────
Usuario responde: "Ivan"
         │
         ↓
_advance_quotation(session, "Ivan")
         │
         ├─ data["nombre"] = "Ivan"
         ├─ State = quotation_contact
         │
         ↓
Pregunta 6: "¿Contacto?"
────────────────────────
Usuario responde: "sí, este WhatsApp"
         │
         ↓
_advance_quotation(session, "sí, este WhatsApp")
         │
         ├─ data["contacto"] = "519111111111" (número extraído)
         ├─ State = quotation_completed = true
         │
         ↓
_finalize_flow(to, resp)
         │
         ├─ repo.save_quotation_request(data)  [persistencia]
         ├─ metrics_service.record("quotation_completed")
         ├─ admin_service.notify_lead(data)  [notifica admins]
         ├─ session_service.clear_session(to)  [cierra sesión]
         │
         ↓
Respuesta al usuario: Resumen + "Gracias por pensar en nosotros"
─────────────────────────────────────────────────────────────────

Data guardada:
{
  "whatsapp": "519111111111",
  "nombre": "Ivan",
  "lugar": "Lima Norte",
  "fecha_evento": "15 de junio",
  "tipo_evento": "Cumpleaños",
  "duracion": "2 horas",
  "contacto": "519111111111",
  "estado": "NUEVA"
}

Admins notificados: 📩 "¡Nuevo lead completo! Ivan - Lima Norte - 15 de junio"
```

---

## 5. Flujo administrativo (registrar evento)

Cuando un admin dice "registrar evento":

```
START: admin detecta "registrar evento"
         │
         ├─ ¿Es admin? (número en ADMIN_PHONE_NUMBERS)
         │  ├─ SÍ → continuar
         │  └─ NO → "Este comando es solo para admins"
         │
         ↓
session_service.start_admin_event()
         │
         ├─ State = admin_event_date
         │
         ↓
Pregunta 1: "¿Cuál es la FECHA?"
──────────────────────────────────
Admin responde: "15 de junio"
         │
         ↓
State = admin_event_time
         │
         ↓
Pregunta 2: "¿A qué HORA?"
────────────────────────────
Admin responde: "8:00 PM"
         │
         ↓
State = admin_event_city
         │
         ↓
Pregunta 3: "¿En qué CIUDAD?"
──────────────────────────────
Admin responde: "Lima"
         │
         ↓
State = admin_event_place
         │
         ↓
Pregunta 4: "¿En qué LUGAR?"
──────────────────────────────
Admin responde: "Plaza Norte"
         │
         ↓
State = admin_event_description
         │
         ↓
Pregunta 5: "¿DESCRIPCIÓN?"
────────────────────────────
Admin responde: "Presentación especial"
         │
         ↓
State = admin_event_confirm
         │
         ↓
"Revisa: Fecha / Hora / Lugar / Ciudad / Descripción
 Escribe: confirmar o cancelar"
         │
         ├─ Admin: "confirmar"
         │  │
         │  ↓
         │  _finalize_flow(to, resp)
         │  │
         │  ├─ event_service.create_event(data)
         │  ├─ metrics_service.record("event_created")
         │  ├─ session_service.clear_session(to)
         │  │
         │  ↓
         │  Respuesta: "✅ Evento registrado"
         │
         └─ Admin: "cancelar"
            │
            ↓
            Respuesta: "Listo, descarté el evento"

Data guardada en Sheets (hoja "Eventos"):
{
  "id": "a1b2c3d4",
  "fecha": "15 de junio",
  "hora": "8:00 PM",
  "ciudad": "Lima",
  "lugar": "Plaza Norte",
  "descripcion": "Presentación especial",
  "estado": "ACTIVO",
  "creado_por": "519000000001",
  "fecha_registro": "2026-05-29T..."
}

Ahora cuando clientes consulten "eventos" verán este evento registrado.
```

---

## 6. Flujo de métricas (admin)

```
Admin: "metricas"
         │
         ├─ ¿Es admin?
         │  └─ SÍ → continuar
         │
         ├─ metrics_service.record("admin_metric_requested")
         │
         ├─ metrics_service.get_metrics_summary()
         │  │
         │  ├─ Lee todas las métricas (Sheets o memoria)
         │  ├─ Filtra por hoy
         │  ├─ Filtra por últimos 7 días
         │  ├─ Calcula agregados
         │
         ↓
Respuesta:
📊 Resumen de Music Bot

Hoy:
👋 Conversaciones iniciadas: 2
🎤 Consultas de eventos: 2
💰 Consultas de precio: 3
📩 Solicitudes completas: 1

Últimos 7 días:
👥 Usuarios únicos: 3
📈 Leads generados: 2
🎵 Eventos consultados: 5

🎶 Eventos registrados (total): 1
```

---

## 7. Estructura de datos que fluye

### 7.1 Session (en memoria, por número de WhatsApp)

```python
Session {
    whatsapp: "519111111111"
    state: "quotation_date"  # o idle si no está en flujo
    data: {
        "whatsapp": "519111111111",
        "lugar": "Lima Norte",
        "fecha_evento": "15 de junio",
        # ... otros campos según el flujo
    }
    created_at: datetime
    updated_at: datetime
}
```

### 7.2 Mensaje extraído del webhook

```python
# De extract_message(body)
from_number: "519111111111"
text: "hola" | ""
button_id: "menu_price" | ""
```

### 7.3 Respuesta de conversation_service

```python
resp = {
    "text": "¿Para qué ciudad?",
    "buttons": [
        {"id": "...", "title": "..."}
    ],
    "completed": False,  # True si flujo terminó
    "kind": "quotation",  # o "admin_event" si completó
    "data": {...},  # datos finales si completó
    "cancelled": False
}
```

### 7.4 Métrica registrada

```python
{
    "fecha_hora": "2026-05-29T17:30:45Z",
    "tipo": "quotation_completed",  # message_received, intent_greeting, etc.
    "whatsapp": "519111111111",
    "detalle": "cumpleaños, 2 horas",
    "origen": "bot"
}
```

---

## 8. Capa de persistencia (opcional)

```
┌─────────────────────────────────────────────────┐
│ google_sheets_repository.py                      │
│ (Encapsula Sheets + fallback en memoria)        │
└─────────────────────┬───────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ↓                           ↓
   [Google Sheets]            [Memoria RAM]
   (persistencia real)        (fallback temporal)
   
   Hojas:                      Dicts:
   - Eventos                   - _mem_events
   - Solicitudes               - _mem_quotations
   - Admins                    - _mem_metrics
   - Metricas                  - (se pierden al reiniciar)

┌─────────────────────────────────────────────────┐
│ Si GOOGLE_SHEETS_ENABLED=false o falla:         │
│ → Todo va a memoria                             │
│ → Bot sigue funcionando                         │
│ → Datos se pierden al reiniciar                 │
└─────────────────────────────────────────────────┘
```

---

## 9. Flujos especiales

### 9.1 Cancelar en cualquier momento

```
¿Usuario escribe "cancelar"?
         │
         ├─ SÍ → intent_service.detect_intent() → INTENT_CANCEL
         │       │
         │       ├─ session_service.clear_session(to)
         │       ├─ Respuesta: "Listo, reinicié la conversación"
         │       │
         │       └─ Siguiente mensaje empieza en state = IDLE
         │
         └─ NO → continuar flujo normal
```

### 9.2 Botón de menú fuera de flujo

```
¿button_id = "menu_price"?
         │
         ├─ SÍ → intent_service.button_to_intent("menu_price")
         │       → INTENT_PRICE
         │       → _dispatch_intent(to, INTENT_PRICE)
         │       → start_quotation()
         │
         └─ NO → procesar como texto normal
```

### 9.3 Respuesta corta/ambigua en flujo

```
state = "quotation_date"
usuario responde: "mañana a las 8"
         │
         ├─ ¿AI_ENABLED?
         │  └─ SÍ → ai_service.validate_and_enhance_quotation()
         │          → extrae {"date": "mañana", "time": "8:00"}
         │          → data["fecha_evento"] = "mañana a las 8"
         │
         └─ NO → guardar texto tal cual
```

---

## 10. Puntos de decisión críticos

| Punto | Pregunta | SÍ | NO |
|-------|----------|----|----|
| 1 | ¿Cancelar? | Limpiar sesión, reiniciar | Continuar |
| 2 | ¿En flujo? | handle_flow() | Procesad como intención |
| 3 | ¿Botón? | Mapear a intención | Procesar texto |
| 4 | ¿Comando admin? | Ejecutar (si es admin) | Detectar intención |
| 5 | ¿Reglas coinciden? | Usar intención | Fuzzy match |
| 6 | ¿Fuzzy coincide? | Usar intención | IA (si habilitada) |
| 7 | ¿IA decide? | Usar intent de IA | INTENT_UNKNOWN |
| 8 | ¿INTENT_UNKNOWN? | Mostrar menú | Responder directa |

---

## 11. Ejemplo completo: Usuario nuevo

```
Usuario: "519111111111"
Mensaje: "hola, ¿cuánto cuesta?"

┌─ webhook.py
│  ├─ Verifica firma Meta ✓
│  ├─ Extrae: from="519111111111", text="hola, ¿cuánto cuesta?"
│  └─ Delega a conversation_service.handle_incoming_message()
│
├─ conversation_service.py
│  ├─ metrics_service.record("message_received", whatsapp="519111111111")
│  │
│  ├─ session = session_service.get_session("519111111111")
│  │  └─ Nueva sesión con state=IDLE
│  │
│  ├─ ¿Cancelar? → NO
│  │
│  ├─ ¿En flujo? → NO (state=IDLE)
│  │
│  ├─ ¿Botón? → NO
│  │
│  ├─ ¿Comando admin? → NO
│  │
│  ├─ detect_intent("hola, ¿cuánto cuesta?")
│  │  │
│  │  ├─ normalize() → "hola cuanto cuesta"
│  │  │
│  │  ├─ Reglas
│  │  │  ├─ "hola" en GREETING keywords? → SÍ (exacto)
│  │  │  └─ Devuelve INTENT_GREETING
│  │  │
│  │  └─ (IA no se consulta porque las reglas ganaron)
│  │
│  ├─ _dispatch_intent(to, INTENT_GREETING)
│  │  │
│  │  ├─ metrics_service.record("intent_greeting")
│  │  │
│  │  ├─ send_button_message(to, GREETING_TEXT, MENU_BUTTONS)
│  │  │  └─ Envía: "¡Hola! Qué alegría..." + botones
│  │  │     [Ver eventos] [Consultar precio] [Contactar]
│
└─ Respuesta llegó a WhatsApp ✓
   Usuario puede presionar un botón o escribir más

Usuario presiona: "Consultar precio"
│
├─ Webhook verifica y extrae: button_id="menu_price"
│
├─ conversation_service.handle_incoming_message(from, text="", button_id="menu_price")
│  │
│  ├─ Session ya existe: state=IDLE
│  │
│  ├─ button_to_intent("menu_price") → INTENT_PRICE
│  │
│  ├─ _dispatch_intent(to, INTENT_PRICE)
│  │  │
│  │  ├─ metrics_service.record("intent_price")
│  │  ├─ metrics_service.record("quotation_started")
│  │  │
│  │  ├─ resp = start_quotation("519111111111")
│  │  │  │
│  │  │  ├─ session.data = {"whatsapp": "519111111111"}
│  │  │  ├─ session.state = "quotation_location"
│  │  │  │
│  │  │  └─ Devuelve:
│  │  │     {
│  │  │       "text": "¿Para qué ciudad?",
│  │  │       "buttons": null,
│  │  │       "completed": false,
│  │  │       ...
│  │  │     }
│  │  │
│  │  └─ send_text_message(to, resp["text"])
│
└─ Respuesta: "¿Para qué ciudad?" ✓
   Sesión ahora en estado quotation_location
   
   [Flujo continúa como se mostró en sección 4]
```

---

## 12. Tabla de servicios

| Servicio | Responsabilidad | Entrada | Salida |
|----------|-----------------|---------|--------|
| `whatsapp_webhook` | Validar firma, extraer datos | HTTP POST | Número, texto/botón |
| `conversation_service` | Orquestación principal | Número, texto | Respuesta (texto/botones) |
| `intent_service` | Clasificar intención | Texto | Intent string |
| `session_service` | Máquina de estados | Número, respuesta | Próximo estado + pregunta |
| `event_service` | Consultar/crear eventos | - | Evento o lista de eventos |
| `admin_service` | Autorización, comandos | Número, comando | Respuesta o denegación |
| `metrics_service` | Registrar y calcular métricas | Tipo, detalles | Resumen |
| `whatsapp_service` | Enviar mensajes | Número, texto/botones | Response HTTP WhatsApp |
| `ai_service` | Fallback IA | Texto | Intent + confianza |
| `google_sheets_repo` | Persistencia | Datos | Guardado (Sheets o memoria) |

---

## 13. Resumen visual: Estado de la sesión

```
Usuario normal (cliente):
┌─────────────────────────────────┐
│ state = IDLE                    │  → Espera intención
├─────────────────────────────────┤
│ ¿Intención "precio"?            │
├─────────────────────────────────┤
│ state = quotation_location      │  → "¿Para qué ciudad?"
├─────────────────────────────────┤
│ Respuesta: "Lima"               │
├─────────────────────────────────┤
│ state = quotation_date          │  → "¿Qué fecha?"
├─────────────────────────────────┤
│ [... continúa 6 preguntas ...]  │
├─────────────────────────────────┤
│ state = quotation_completed     │  → Guarda, notifica, limpia
├─────────────────────────────────┤
│ state = IDLE                    │  → Sesión lista para nuevo flujo
└─────────────────────────────────┘

Usuario admin:
┌─────────────────────────────────┐
│ state = IDLE                    │
├─────────────────────────────────┤
│ Comando: "registrar evento"     │
├─────────────────────────────────┤
│ state = admin_event_date        │  → "¿Cuál es la fecha?"
├─────────────────────────────────┤
│ [... 5 preguntas más ...]       │
├─────────────────────────────────┤
│ state = admin_event_confirm     │  → "Revisa y confirma"
├─────────────────────────────────┤
│ Respuesta: "confirmar"          │
├─────────────────────────────────┤
│ state = IDLE (evento guardado)  │
└─────────────────────────────────┘
```

---

Este es el **flujo completo y detallado** de cómo funciona Music Bot desde que un usuario envía un mensaje hasta que recibe la respuesta. Cada servicio tiene una responsabilidad clara y el orquestador (conversation_service) mantiene la lógica de negocio centralizada.
