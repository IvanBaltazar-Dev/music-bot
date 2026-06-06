# Levantar Local Con Supabase Y Gemini

Esta guia deja Google Sheets fuera del flujo local. El bot usa Supabase para
persistencia, Gemini como fallback inteligente y WhatsApp Cloud API para envios
reales.

## 1. Crear Supabase

1. Crea un proyecto en Supabase.
2. Abre SQL Editor.
3. Ejecuta la migracion:

```text
supabase/migrations/202606020001_initial_crm_schema.sql
```

## 2. Configurar `.env`

No subas este archivo al repo. Para local, deja estas variables:

```env
STORAGE_BACKEND=supabase
SUPABASE_URL=https://TU-PROYECTO.supabase.co
SUPABASE_SERVICE_ROLE_KEY=TU_SERVICE_ROLE_KEY

GOOGLE_SHEETS_ENABLED=false
GOOGLE_SHEETS_ID=
GOOGLE_APPLICATION_CREDENTIALS=

AI_ENABLED=true
GEMINI_ENABLED=true
GEMINI_API_KEY=TU_GEMINI_API_KEY
AI_MODEL=gemini-2.5-flash
GEMINI_MODEL=gemini-2.5-flash

GROUP_NAME=Carlos Fer y Agrup. Cariño Lindo
ADMIN_PHONE_NUMBERS=519XXXXXXXX

VERIFY_TOKEN=music_bot_verify_token
WHATSAPP_TOKEN=TU_WHATSAPP_TOKEN
PHONE_NUMBER_ID=TU_PHONE_NUMBER_ID
WHATSAPP_API_VERSION=v25.0
```

Importante: usa `SUPABASE_SERVICE_ROLE_KEY` solo en backend. No debe ir en un
frontend ni en codigo publico.

## 3. Sembrar Un Admin Opcional

`ADMIN_PHONE_NUMBERS` ya autoriza admins desde `.env`. Si tambien quieres verlo
en el CRM, inserta un admin:

```sql
insert into public.admins (name, phone, role, active)
values ('Ivan Baltazar', '519XXXXXXXX', 'manager', true)
on conflict (phone) do update
set name = excluded.name,
    role = excluded.role,
    active = true;
```

## 4. Levantar API

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

Verifica:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Esperado:

```json
{
  "status": "healthy",
  "storage": "supabase",
  "supabase": true,
  "google_sheets": false,
  "gemini": true
}
```

## 5. Probar Webhook Local Sin WhatsApp

Esto prueba que el bot procesa mensajes y persiste en Supabase. Si no tienes
token de WhatsApp valido, el envio fallara en logs, pero el webhook no cae.

```powershell
$body = @{
  entry = @(@{
    changes = @(@{
      value = @{
        contacts = @(@{
          profile = @{ name = "Ivan Baltazar" }
        })
        messages = @(@{
          from = "51934011041"
          type = "text"
          text = @{ body = "Hola" }
        })
      }
    })
  })
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/webhook" `
  -ContentType "application/json" `
  -Body $body
```

## 6. Probar WhatsApp Real

Expone local:

```powershell
ngrok http 8000
```

En Meta:

```text
Callback URL: https://TU-NGROK.ngrok-free.app/webhook
Verify token: music_bot_verify_token
```

Luego escribe al numero de prueba.

## 7. Flujo Minimo A Validar

Cliente:

```text
Hola
Quiero contratarlos
Quincena de junio en Zapallanga
Cumpleaños 8 pm
No quiero reservar todavía quiero saber los precios
```

Revisar en Supabase:

- `clients`: debe existir el telefono.
- `conversation_threads`: debe existir el hilo WhatsApp.
- `messages`: debe tener el historial.
- `hiring_requests`: debe tener `name_or_dni = null`, telefono y nota.

Admin:

```text
ver solicitudes
Tomar control
#salir
```

## 8. Google Sheets

Para este modo no se usa Sheets. No borres el codigo viejo todavia; queda como
backend alterno hasta que todos los flujos pasen con Supabase. El selector real
es:

```env
STORAGE_BACKEND=supabase
```
