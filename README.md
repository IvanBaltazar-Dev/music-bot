# 🎵 Music Bot

Chatbot operativo de WhatsApp para una agrupación musical. Construido con
**FastAPI** + **WhatsApp Cloud API** (oficial de Meta), con persistencia
opcional en **Google Sheets** y fallback automático en memoria.

Sin IA: la detección de intenciones usa normalización de texto + coincidencia
aproximada (`difflib`), reglas y palabras clave.

## ✨ Funcionalidades

- Detección de intenciones con corrección de errores comunes (`hla`, `ohla`, `presio`…).
- Respuestas cálidas y botones interactivos.
- Flujo guiado de cotización (lead) paso a paso.
- Flujo administrativo para registrar eventos desde WhatsApp.
- Consulta de próximos eventos.
- Notificación a administradores cuando llega un lead completo.
- Métricas operativas.
- Persistencia opcional en Google Sheets (con fallback en memoria).

## 🚀 Ejecutar

```bash
# 1. Crear/activar entorno virtual (Windows PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables (copiar y completar)
copy .env.example .env

# 4. Levantar el servidor
python -m uvicorn app.main:app --reload
```

- Health check: `GET /`
- Webhook WhatsApp: `GET/POST /webhook`

Para desarrollo, exponer con ngrok: `ngrok http 8000`.

### Configurar Google Sheets (opcional)

El bot funciona **sin Google Sheets** (usa memoria temporal). Para persistencia real:

1. Sigue los pasos en [SETUP_GOOGLE_SHEETS.md](SETUP_GOOGLE_SHEETS.md)
2. Ejecuta el validador:
   ```bash
   python test_google_sheets_setup.py
   ```
3. Reinicia el bot

## ⚙️ Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `VERIFY_TOKEN` | ✅ | Token de verificación del webhook (Meta). |
| `WHATSAPP_TOKEN` | ✅ | Token de acceso de la WhatsApp Cloud API. |
| `PHONE_NUMBER_ID` | ✅ | ID del número de WhatsApp. |
| `WHATSAPP_API_VERSION` | – | Versión de la Graph API (def. `v25.0`). |
| `ADMIN_PHONE_NUMBERS` | – | Números admin separados por comas. |
| `GOOGLE_SHEETS_ENABLED` | – | `true`/`false`. Si `false`, usa memoria. |
| `GOOGLE_SHEETS_ID` | – | ID de la hoja de cálculo. |
| `GOOGLE_APPLICATION_CREDENTIALS` | – | Ruta al JSON de la cuenta de servicio. |
| `BOT_NAME` | – | Nombre del bot. |
| `GROUP_NAME` | – | Nombre de la agrupación. |

## 🗂 Arquitectura

```
app/
├── main.py                  # App FastAPI
├── config.py                # Settings (pydantic-settings)
├── models/                  # Modelos (Session, Event)
├── repositories/
│   └── google_sheets_repository.py   # Persistencia + fallback en memoria
├── routes/
│   └── whatsapp_webhook.py  # Webhook delgado (extrae y delega)
└── services/
    ├── conversation_service.py   # Orquestador (controlador)
    ├── intent_service.py         # Normalización + intenciones + botones
    ├── session_service.py        # Sesiones y flujos guiados (máquina de estados)
    ├── event_service.py          # Eventos
    ├── admin_service.py          # Admins, notificaciones, comandos
    ├── metrics_service.py        # Métricas
    └── whatsapp_service.py       # Cliente WhatsApp Cloud API
```

## 📊 Google Sheets (opcional)

El bot funciona **sin** Google Sheets. Para activarlo:

1. Crear un proyecto en Google Cloud, habilitar **Google Sheets API** y **Drive API**.
2. Crear una **cuenta de servicio** y descargar el JSON de credenciales.
3. Crear una hoja de cálculo y **compartirla** con el email de la cuenta de servicio.
4. Configurar en `.env`:
   ```env
   GOOGLE_SHEETS_ENABLED=true
   GOOGLE_SHEETS_ID=<id_de_la_hoja>
   GOOGLE_APPLICATION_CREDENTIALS=ruta/al/credentials.json
   ```
5. `pip install gspread google-auth`

Las hojas (`Eventos`, `Solicitudes`, `Admins`, `Metricas`) se crean
automáticamente con sus encabezados si no existen.

**Fallback:** si Sheets está deshabilitado, faltan credenciales o `gspread`
no está instalado, todo se guarda en memoria temporal (se pierde al reiniciar)
y el backend nunca se cae.
