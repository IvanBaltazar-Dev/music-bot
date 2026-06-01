# 🎵 Music Bot — Carlos Fer y Agrup. Cariño Lindo

Chatbot oficial de WhatsApp para la agrupación **Carlos Fer y Agrup. Cariño Lindo**.
Construido con **FastAPI** + **WhatsApp Cloud API** (oficial de Meta), con
persistencia en **Google Sheets** (como base inicial) y *fallback* automático en
memoria para que el backend nunca se caiga.

Tono cercano, ameno y con gracia ligera para el cliente; por dentro, ordenado y
trazable para el administrador.

## ✨ Flujos principales

1. **Quiero ir a verlos** — pregunta la ciudad, personaliza con frases de la hoja
   `Localidades`, consulta `Eventos` (solo `CONFIRMADO` y con fecha futura) y
   muestra botones dinámicos (`Ayúdame a llegar`, `Quiero entradas`, `Pasar la voz`).
   Si no hay evento, ofrece registrar el **interés de localidad**.
2. **Quiero contratarlos** — en **2 pasos agrupados**: *Paso 1* (fecha, ciudad/
   localidad, tipo de evento y hora aproximada en un solo mensaje; si falta algo,
   pide solo lo que falta); *Paso 2* (nombre o DNI + confirmar si se usa el mismo
   WhatsApp u otro número). Genera una **solicitud interna `SOL-XXXX`** (el
   cliente nunca ve el código), la guarda en `SolicitudesContratacion` y
   **notifica a los administradores** con botones *Tomar control* / *Hacer
   seguimiento*. El bot **no cotiza ni evalúa**: solo recibe y deriva.
3. **Conoce la agrupación** — lee videos, canciones y redes desde la hoja
   `ContenidosAgrupacion`. No muestra botones de contenido que no existan.

### Administración por WhatsApp

- **Tomar control**: el bot deja de responder a ese cliente y los mensajes se
  relevan administrador ⇄ cliente.
- **Hacer seguimiento**: el admin recibe en tiempo real los mensajes nuevos del
  cliente, sin tomar control.
- **Ver solicitud**: detalle completo de la solicitud.
- **Registrar evento**: en un solo mensaje con campos `Campo: valor`, con
  confirmación antes de guardar.
- Comandos de texto: `ver solicitudes`, `métricas`, `inicializar hojas`,
  `soltar control`, `ayuda admin`.

### Personalización por localidad (sin frases quemadas)

Las frases por ciudad **viven en la hoja `Localidades`**, no en el código. La
búsqueda normaliza el texto (minúsculas, sin tildes, sin signos) y usa fuzzy
matching (`rapidfuzz` si está instalado, si no `difflib`). Reconoce nombres,
apodos (`ciudad incontrastable`, `tierra de las flores`) y errores de tipeo.

> Si Google Sheets no está habilitado, las 5 localidades de ejemplo (Huancayo,
> Tarma, Lima, Jauja, Concepción) se siembran en memoria para que el bot siga
> siendo demostrable. La hoja real siempre tiene prioridad.

## 🚀 Ejecutar

```powershell
# 1. Entorno virtual
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Dependencias
pip install -r requirements.txt

# 3. Variables (NO sobrescribir un .env ya configurado)
copy .env.example .env

# 4. Levantar el servidor
python -m uvicorn app.main:app --reload
```

- Estado: `GET /`
- Healthcheck: `GET /health`
- Webhook WhatsApp: `GET/POST /webhook`
- Exponer en desarrollo: `ngrok http 8000` (solo desarrollo; en producción NO se usa ngrok)

Al arrancar, el bot ejecuta `ensure_sheets()`: crea **solo las hojas faltantes**
con sus encabezados. **Nunca borra ni sobrescribe** datos existentes.

### 🔌 Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Estado básico del servicio. |
| `GET` | `/health` | Healthcheck (whatsapp/sheets/gemini) para monitoreo/uptime. |
| `GET` | `/webhook` | Verificación del `VERIFY_TOKEN` de Meta. |
| `POST` | `/webhook` | Recibe y procesa mensajes de WhatsApp. |

## ⚙️ Variables de entorno

> El `.env` existente **no se modifica**. Esta tabla documenta las variables que
> el bot ya usa. No se agregaron variables nuevas obligatorias.

| Variable | Obligatoria | Descripción |
|---|---|---|
| `VERIFY_TOKEN` | ✅ | Token de verificación del webhook (Meta). |
| `WHATSAPP_TOKEN` | ✅ | Token de acceso de la WhatsApp Cloud API. |
| `PHONE_NUMBER_ID` | ✅ | ID del número de WhatsApp. |
| `WHATSAPP_API_VERSION` | – | Versión de la Graph API (def. `v25.0`). |
| `ADMIN_PHONE_NUMBERS` | – | Números admin separados por comas (con código de país, sin `+`). |
| `GOOGLE_SHEETS_ENABLED` | – | `true`/`false`. Si `false`, usa memoria. |
| `GOOGLE_SHEETS_ID` | – | ID de la hoja de cálculo. |
| `GOOGLE_APPLICATION_CREDENTIALS` | – | Ruta al JSON de la cuenta de servicio. |
| `BOT_NAME` | – | Nombre del bot. |
| `GROUP_NAME` | – | Nombre de la agrupación (ver nota). |
| `AI_ENABLED` | – | `true`/`false`. Activar Gemini (def. `false`). |
| `GEMINI_API_KEY` | – | API key de Google AI Studio. |
| `AI_PROVIDER` | – | Proveedor de IA (def. `gemini`). |
| `AI_MODEL` | – | Modelo de Gemini (def. `gemini-2.5-flash`). |
| `GEMINI_ENABLED` | – | **(nueva, opcional)** Alias de `AI_ENABLED`. Con que una esté en `true` basta. |
| `GEMINI_MODEL` | – | **(nueva, opcional)** Si se define, tiene prioridad sobre `AI_MODEL`. |

> Las dos últimas variables son **opcionales y nuevas**; tienen default seguro en
> `config.py`, así que **no es necesario tocar el `.env`** para que el bot siga
> funcionando. Solo documéntalas/añádelas si quieres usar los alias de Gemini.

> **Nota sobre `GROUP_NAME`:** para que el saludo muestre el nombre oficial,
> conviene poner `GROUP_NAME=Carlos Fer y Agrup. Cariño Lindo` en tu `.env`.
> Si quedó con un valor genérico (`Nombre de la agrupación`, etc.), el bot usa
> automáticamente el nombre oficial como respaldo (ver
> `conversation_service.group_name()`). **No se requiere ninguna variable nueva.**

## 🗂 Arquitectura

```
app/
├── main.py                       # App FastAPI + inicialización de hojas
├── config.py                     # Settings (pydantic-settings) — sin cambios de variables
├── models/
│   └── session.py                # Sesión + estados de los flujos guiados
├── repositories/                 # Acceso a datos (Sheets + fallback en memoria)
│   ├── sheets_schema.py          # Nombres y encabezados de las 15 hojas
│   ├── sheets_client.py          # Única conexión + CRUD genérico + memoria
│   ├── locality_repository.py    # Localidades (con sembrado de ejemplo)
│   ├── event_repository.py       # Eventos
│   ├── hiring_request_repository.py  # Solicitudes de contratación (SOL-XXXX)
│   ├── conversation_repository.py    # Estado de conversación (BOT/ADMIN_CONTROL)
│   ├── content_repository.py     # Contenidos de la agrupación
│   ├── admin_repository.py       # Administradores
│   ├── follow_up_repository.py   # Seguimientos
│   ├── interest_repository.py    # Intereses de localidad
│   ├── message_repository.py     # Mensajes (trazabilidad)
│   ├── metrics_repository.py     # Métricas
│   └── error_repository.py       # Errores
├── routes/
│   └── whatsapp_webhook.py       # Webhook delgado (extrae nombre, texto, botón)
└── services/
    ├── conversation_service.py   # Orquestador (controlador principal)
    ├── intent_service.py         # Normalización + intenciones + IDs de botones
    ├── locality_service.py       # Búsqueda de localidad + frases
    ├── session_service.py        # Flujos guiados (contratar / registrar evento)
    ├── event_service.py          # Eventos confirmados + botones dinámicos
    ├── hiring_service.py         # Creación de solicitud + textos al cliente
    ├── group_info_service.py     # "Conoce la agrupación"
    ├── admin_service.py          # Tomar control / seguimiento / ver / relevo
    ├── metrics_service.py        # Registro de métricas + resumen
    ├── error_service.py          # Registro de errores + aviso a admins
    ├── gemini_service.py         # Gemini como RESPALDO (clasificar / redactar)
    ├── text_utils.py             # Normalización + fuzzy (rapidfuzz/difflib)
    ├── ai_service.py             # (legado) integración IA previa, sin uso
    └── whatsapp_service.py       # Cliente WhatsApp (texto, botones, listas)
```

> El archivo `repositories/google_sheets_repository.py` quedó del backend
> anterior y **ya no se usa**; se conserva por compatibilidad. La nueva capa de
> datos es `sheets_client.py` + repositorios específicos.

## 📊 Hojas de Google Sheets

El bot trabaja con estas hojas (se crean con encabezados si faltan, sin borrar
nada): `ConfiguracionBot`, `Eventos`, `SolicitudesContratacion`,
`InteresesLocalidad`, `Usuarios`, `Conversaciones`, `Mensajes`,
`Administradores`, `Seguimientos`, `Metricas`, `ContenidosAgrupacion`,
`Localidades`, `NotificacionesAdmin`, `Errores`, `Catalogos`.

Para activar Sheets:

1. Habilita **Google Sheets API** y **Drive API** en Google Cloud.
2. Crea una **cuenta de servicio**, descarga el JSON y **comparte** la hoja con
   su email. Ver [SETUP_GOOGLE_SHEETS.md](SETUP_GOOGLE_SHEETS.md).
3. En `.env`: `GOOGLE_SHEETS_ENABLED=true`, `GOOGLE_SHEETS_ID=…`,
   `GOOGLE_APPLICATION_CREDENTIALS=…`
4. `pip install gspread google-auth`
5. Reinicia. (Opcional: un admin puede enviar `inicializar hojas`.)

**Fallback:** sin Sheets, todo se guarda en memoria temporal y el backend nunca
se cae.

## 🤖 Gemini como respaldo inteligente

Gemini **no es el cerebro del bot**: es un *fallback*. El orden de resolución es
siempre:

1. Reglas + intents + fuzzy matching + estados de conversación + Google Sheets.
2. **Solo si lo anterior no alcanza**, se llama a Gemini para:
   - clasificar una intención ambigua, o
   - redactar una respuesta natural cuando el mensaje es `UNKNOWN`.

Garantías (criterios 5–7):

- Si `GEMINI_API_KEY` falta o `*_ENABLED=false`, **el bot funciona igual** con
  reglas. No se rompe.
- Gemini recibe **contexto controlado** (descripción + capacidades), nunca el
  historial crudo ni datos sensibles.
- Si Gemini falla, se responde con un *fallback* seguro (menú) y se registra el
  error. Cada uso de Gemini se contabiliza en `Metricas` (`GEMINI_USED`).

Activación (sin tocar el `.env` real; documentado en `.env.example`):

```env
GEMINI_API_KEY=AIza...
GEMINI_ENABLED=true          # o AI_ENABLED=true
GEMINI_MODEL=gemini-1.5-flash  # opcional; si no, usa AI_MODEL
```

Instala la librería: `pip install google-generativeai`.

## 🚀 Despliegue en Oracle Cloud Always Free (producción 24/7)

Pensado para una instancia **Always Free** (Ubuntu/Oracle Linux ARM o x86).

**1) Servidor y dependencias**

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
git clone <tu-repo> music-bot && cd music-bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Crea el .env en el servidor con tus tokens reales (no lo subas al repo)
```

**2) Ejecutar con gunicorn + workers uvicorn (NO usar `--reload`)**

```bash
gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --workers 2
```

> Con varios *workers*, cada proceso tiene su propia memoria de sesiones. Para
> 24/7 multiproceso conviene `--workers 1` (sesiones en memoria) o migrar las
> sesiones a Redis/Sheets. El estado admin/cliente ya se persiste en
> `Conversaciones`.

**3) Servicio systemd (arranque automático y reinicio)**

`/etc/systemd/system/musicbot.service`:

```ini
[Unit]
Description=Music Bot (FastAPI)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/music-bot
EnvironmentFile=/home/ubuntu/music-bot/.env
ExecStart=/home/ubuntu/music-bot/venv/bin/gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now musicbot
sudo systemctl status musicbot
journalctl -u musicbot -f   # logs en vivo
```

**4) HTTPS público (Meta exige URL HTTPS, sin ngrok)**

Usa un *reverse proxy* con certificado (Caddy es el más simple):

```
# /etc/caddy/Caddyfile
tu-dominio.com {
    reverse_proxy localhost:8000
}
```

El webhook quedará en `https://tu-dominio.com/webhook`. Abre el puerto 443 en la
**Security List/NSG** de Oracle Cloud y en el firewall del SO
(`sudo ufw allow 443`). Configura esa URL y el `VERIFY_TOKEN` en el panel de Meta.

**5) Healthcheck**: apunta tu monitor de uptime a `GET /health`.

## 🧩 Pendiente / próximos pasos

- Migrar la capa de datos de Sheets a PostgreSQL/MySQL (los repositorios ya
  aíslan el acceso, así que el cambio es localizado).
- Hojas `Usuarios`, `ConfiguracionBot` y `NotificacionesAdmin`: tienen esquema y
  se inicializan, pero su uso es básico; se pueden enriquecer.
- El relevo admin ⇄ cliente usa el estado persistido en `Conversaciones`; en un
  despliegue multiproceso conviene un backend compartido (Redis) para sesiones.
- Cargar contenidos reales (videos, canciones, redes) en `ContenidosAgrupacion`.
