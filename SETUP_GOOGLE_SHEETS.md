# 📋 Configurar Google Sheets

Pasos para activar persistencia en Google Sheets. Sin esto, el bot funciona con memoria temporal.

## Paso 1: Crear proyecto en Google Cloud

1. Ve a [Google Cloud Console](https://console.cloud.google.com)
2. Haz clic en el dropdown de proyecto (arriba izquierda) → **Nuevo proyecto**
3. Nombre: `Music Bot` (o lo que quieras)
4. Espera a que se cree (1-2 min)
5. Selecciona tu nuevo proyecto

## Paso 2: Habilitar APIs

1. En el buscador de la consola, escribe `sheets` → abre **Google Sheets API** → clic en **Habilitar**
2. En el buscador, escribe `drive` → abre **Google Drive API** → clic en **Habilitar**

## Paso 3: Crear cuenta de servicio

1. En el menú izquierdo, busca **Credenciales** (Credentials)
2. Clic en **+ Crear credenciales** → **Cuenta de servicio** (Service Account)
3. Email: `music-bot@<tu-proyecto>.iam.gserviceaccount.com` (auto-generado, mantén como está)
4. Haz clic en **Crear y continuar**
5. Salta los pasos opcionales → **Crear**

## Paso 4: Descargar JSON de credenciales

1. Aparecerá la página de la cuenta de servicio. En la pestaña **Claves** (Keys)
2. Clic en **Agregar clave** (Add Key) → **Crear nueva clave** → **JSON**
3. Se descargará un archivo JSON
4. **Guárdalo en la raíz del proyecto como `google-credentials.json`**
   ```
   music-bot/
   ├── google-credentials.json   ← aquí
   ├── app/
   ├── requirements.txt
   └── ...
   ```

## Paso 5: Crear hoja de cálculo

1. Ve a [Google Sheets](https://sheets.google.com)
2. Clic en **+ Crear** (Create)
3. Dale un nombre: `Music Bot`
4. Copia el **ID de la hoja** desde la URL:
   ```
   https://docs.google.com/spreadsheets/d/AQUI-ES-EL-ID/edit
   ```

## Paso 6: Compartir hoja con la cuenta de servicio

1. En la hoja, clic en **Compartir** (Share) arriba derecha
2. Pega el email de la cuenta de servicio (aparece en Google Cloud Console):
   ```
   music-bot@<tu-proyecto>.iam.gserviceaccount.com
   ```
3. Dale acceso de **Editor** (Editor)
4. Clic en **Compartir**

## Paso 7: Configurar `.env`

Edita tu `.env` real (no `.env.example`):

```env
GOOGLE_SHEETS_ENABLED=true
GOOGLE_SHEETS_ID=AQUI-ES-EL-ID
GOOGLE_APPLICATION_CREDENTIALS=google-credentials.json
```

## Paso 8: Instalar gspread (si aún no lo hiciste)

```bash
pip install gspread google-auth
```

## Paso 9: Reinicia el bot

```bash
python -m uvicorn app.main:app --reload
```

Deberías ver en los logs:
```
[sheets] conexión establecida correctamente.
```

## ✅ Listo

Las hojas `Eventos`, `Solicitudes`, `Admins`, `Metricas` se crean automáticamente con sus encabezados.
