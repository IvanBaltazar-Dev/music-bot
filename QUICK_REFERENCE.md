# 🎯 Referencia rápida: Music Bot

**Un vistazo rápido a cómo funciona** sin perder en detalles.

---

## El viaje de un mensaje

```
👤 Usuario escribe "precio"
   ↓
📥 WhatsApp → Meta → Tu servidor (/webhook)
   ↓
🔐 webhook.py: verifica firma, extrae from="519...", text="precio"
   ↓
🎛️ conversation_service.handle_incoming_message()
   ↓
📋 Decides:
   • ¿Cancelar? NO
   • ¿En flujo activo? NO → inicio nuevo
   • ¿Comando admin? NO
   • ¿Intención? INTENT_PRICE ✓
   ↓
📝 session_service.start_quotation()
   • Crea sesión con state="quotation_location"
   • data = {whatsapp: "519..."}
   ↓
💬 Respuesta: "¿Para qué ciudad?"
   ↓
📤 whatsapp_service.send_text_message() → Meta → usuario
   ↓
👤 Usuario: "Lima"
   ↓
🔄 conversation_service (nuevamente)
   ↓
📝 session_service.handle_flow()
   • Avanza: data["lugar"]="Lima"
   • state="quotation_date"
   ↓
💬 "¿Qué fecha?"

[... repite 6 veces hasta completar ...]

   ↓
✅ Flujo completado
   ↓
💾 Guarda: google_sheets_repository.save_quotation_request()
   ↓
🔔 Notifica admin: admin_service.notify_lead()
   ↓
📊 Registra métrica: metrics_service.record()
   ↓
🧹 Limpia: session_service.clear_session()
   ↓
👤 Usuario recibe resumen
```

---

## Detección de intención

```
Usuario: "kiero kontratarlos"
         ↓
normalize() → "kiero kontratarlos"
         ↓
1️⃣  Reglas exactas? NO
2️⃣  Reglas fuzzy? 
    difflib("kontratarlos", keywords) → "contratar"
    ✓ INTENT_PRICE
    ↓
    (IA no se consulta, reglas ganaron)

Usuario: "me encantaría saber si..."
         ↓
normalize() → "me encantaría saber si"
         ↓
1️⃣  Reglas exactas? NO
2️⃣  Reglas fuzzy? NO
3️⃣  IA habilitada?
    ├─ SÍ → Gemini clasifica
    │       confidence=0.72 → INTENT_PRICE ✓
    └─ NO → INTENT_UNKNOWN → menú con botones
```

---

## Servicios y qué hacen

| Servicio | Qué hace | Entrada | Salida |
|----------|----------|---------|--------|
| **webhook** | Recibe y valida | HTTP POST | Número + texto |
| **conversation** | Orquesta todo | from, text | Respuesta |
| **session** | Guarda estado | Número | Session |
| **intent** | Detecta intención | Texto | Intent string |
| **event** | Eventos | - | Eventos o guardados |
| **admin** | Admin checks | Número, comando | Resultado |
| **metrics** | Métricas | Tipo de métrica | Guardado |
| **whatsapp** | Envía por API | Número, texto | Response |
| **ai** | Fallback IA | Texto | Intent + confianza |
| **repo** | Persiste | Datos | Guardado en Sheets/memoria |

---

## Estados principales

### Cliente (6 pasos de cotización)

```
IDLE
  ↓ [usuario dice "precio"]
quotation_location → "¿Ciudad?"
  ↓
quotation_date → "¿Fecha?"
  ↓
quotation_event_type → "¿Tipo?"
  ↓
quotation_duration → "¿Horas?"
  ↓
quotation_name → "¿Nombre?"
  ↓
quotation_contact → "¿Contacto?"
  ↓
IDLE [sesión limpia, listo para nuevo flujo]
```

### Admin (6 pasos para evento)

```
IDLE
  ↓ [admin: "registrar evento"]
admin_event_date → "¿Fecha?"
  ↓
admin_event_time → "¿Hora?"
  ↓
admin_event_city → "¿Ciudad?"
  ↓
admin_event_place → "¿Lugar?"
  ↓
admin_event_description → "¿Descripción?"
  ↓
admin_event_confirm → "¿Confirmar?"
  ↓
IDLE [evento guardado]
```

---

## Intenciones públicas

```
"hola", "ola", "hla", "buenas"
  → INTENT_GREETING (botones: Ver eventos | Precio | Contacto)

"eventos", "conciertos", "presentacion"
  → INTENT_EVENTS (lista de eventos activos o fallback)

"precio", "cotizacion", "contratar", "presio"
  → INTENT_PRICE (inicia flujo de 6 pasos)

"contacto", "telefono", "hablar con alguien"
  → INTENT_CONTACT (número de contacto + indicación)

Cualquier cosa ambigua
  → Reglas no coinciden
  → Fuzzy fallido
  → IA (si habilitada)
  → Sino: INTENT_UNKNOWN (menú con botones)
```

---

## Comandos admin

```
"registrar evento"  → Inicia flujo de 6 pasos para nuevo evento
"solicitudes"       → Muestra últimas 5 cotizaciones
"metricas"          → Resumen operativo (hoy + 7 días)
"ayuda admin"       → Lista de comandos disponibles

⚠️ Nota: solo funcionan si user es admin
   Definición: número en ADMIN_PHONE_NUMBERS del .env
              O en hoja "Admins" de Sheets
```

---

## Flujos especiales

### 1. Presionar botón

```
Usuario presiona: [Consultar precio]
         ↓
button_id = "menu_price"
         ↓
intent_service.button_to_intent() → INTENT_PRICE
         ↓
Inicia flujo de cotización normalmente
```

### 2. Escribir "cancelar" en cualquier momento

```
¿Estado?         ¿Flujo activo?    ¿Respuesta?
─────────────────────────────────────────────────
IDLE              NO               NO HACE NADA
quotation_*       SÍ               "Cancelé, reinicia"
admin_event_*     SÍ               "Cancelé, reinicia"
─────────────────────────────────────────────────
```

### 3. Respuesta muy corta o ambigua

```
[Si IA habilitada]

Estado: quotation_date
Usuario: "mañana a las 8"
         ↓
ai_service.validate_and_enhance_quotation()
         ↓
IA extrae: date="mañana", hour="8"
         ↓
Flujo continúa sin pedir confirmación extra
```

---

## Persistencia (2 opciones)

### Opción 1: Solo memoria (por defecto)

```
GOOGLE_SHEETS_ENABLED=false
         ↓
Todo se guarda en RAM
         ↓
Si reincias el bot: ❌ datos se pierden
```

### Opción 2: Google Sheets (opcional)

```
GOOGLE_SHEETS_ENABLED=true
GOOGLE_SHEETS_ID=...
GOOGLE_APPLICATION_CREDENTIALS=...
         ↓
google_sheets_repository guarda en Sheets
         ↓
Hojas automáticas:
- Eventos (agenda)
- Solicitudes (cotizaciones)
- Admins (lista de admins)
- Metricas (estadísticas)
         ↓
Si Sheets falla: ✓ degrada a memoria
Si no está instalado gspread: ✓ bot sigue funcionando
```

---

## IA (completamente opcional)

### Sin IA (por defecto)

```
detect_intent(text)
  1️⃣ Reglas exactas
  2️⃣ Fuzzy matching (difflib)
  3️⃣ INTENT_UNKNOWN → menú
```

### Con IA (opcional)

```
AI_ENABLED=true
GEMINI_API_KEY=...
         ↓
detect_intent(text)
  1️⃣ Reglas exactas
  2️⃣ Fuzzy matching
  3️⃣ IA Gemini (si confidence >= 0.6)
  4️⃣ INTENT_UNKNOWN → menú

✓ Si Gemini falla: degrada a menú
✓ Si API key no existe: funciona sin IA
✓ Si google-generativeai no instalado: usa reglas
```

---

## Métricas automáticas

El bot registra:
- `message_received` — cada mensaje
- `intent_greeting` — saludos
- `intent_events` — consultas de eventos
- `intent_price` — solicitudes de precio
- `quotation_started` — inicia flujo de cotización
- `quotation_completed` — cotización completada ✓
- `event_created` — evento registrado (admin)
- `admin_metric_requested` — admin pidió resumen
- `unknown_message` — mensaje no entendido

Resumen disponible con: admin escribe "metricas"

---

## Seguridad

✅ **Nunca se imprimen tokens** en logs
✅ **Errores de API no rompen el webhook** (siempre devuelve 200)
✅ **Usuarios no-admin no ven comandos internos**
✅ **IA nunca responde directo al usuario** (solo interno)
✅ **Persistencia es opcional** (siempre hay fallback en memoria)

---

## URLs clave

```
GET  /                → Health check (status: ok)
GET  /webhook         → Verificación Meta (challenge)
POST /webhook         → Mensajes entrantes

Nunca expone:
  - Tokens en URLs
  - Datos de usuarios en logs
  - Credenciales en .env publicado
```

---

## Flujo completo en 30 segundos

```
Usuario: "hola"
  ↓ [webhook valida y extrae]
conversation_service: ¿qué hago?
  ↓ [detecta intención]
intent_service: INTENT_GREETING
  ↓ [ejecuta intención]
Respuesta: "¡Hola! Qué alegría..." + [botones]
  ↓ [registra métrica]
Usuario ve botones en WhatsApp
  ↓
Usuario: presiona "Consultar precio"
  ↓ [webhook extrae button_id]
conversation_service: ¿qué hago?
  ↓ [inicia flujo]
session_service: state = quotation_location
  ↓
"¿Para qué ciudad?" [repetir 6 veces]
  ↓ [usuario responde última pregunta]
Flujo completado
  ↓ [guarda, notifica, limpia]
Usuario recibe resumen
```

---

## En caso de problemas

| Síntoma | Causa | Solución |
|---------|-------|----------|
| Bot no responde | Webhook no llega | Verifica ngrok, URL en Meta |
| Intención "unknown" | Texto no reconocido | Usa reglas más general o activa IA |
| Datos se pierden | Sheets no habilitado | `pip install gspread google-auth` + `.env` |
| Admin no recibe notificación | Número no autorizado | Agrega a `ADMIN_PHONE_NUMBERS` |
| API falla con 400 | Número no en lista de prueba | Agrega número a test users en Meta |
| IA no funciona | API key incorrecta | Obtén de google.generativeai.dev |

---

**Documentación completa:** Lee `ARCHITECTURE_FLOW.md` y `SERVICES_INTERACTION.md`

**Primeros pasos:** Lee `README.md`
