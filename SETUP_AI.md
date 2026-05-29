# 🤖 Configurar IA (Gemini)

La capa de IA es **completamente opcional**. El bot funciona perfectamente sin ella.

## ¿Cuándo usar IA?

La IA ayuda cuando:
- El usuario escribe algo ambiguo o poco claro
- Las reglas + coincidencia aproximada no son suficientes
- Necesitas mejor interpretación de mensajes naturales

La IA **nunca**:
- Es requerida para que el bot funcione
- Se expone al usuario (es interna)
- Rompe el bot si falla

## Pasos para activar Gemini

### 1. Crear API key en Google AI Studio

1. Ve a [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Haz clic en **Create API Key** (Crear clave de API)
3. Selecciona **Create API key in new Google Cloud project** (o proyecto existente)
4. Copia la clave (es una cadena larga como `AIza...`)

### 2. Instalar dependencia

```bash
pip install google-generativeai
```

### 3. Configurar `.env`

Edita tu `.env` real:

```env
AI_ENABLED=true
GEMINI_API_KEY=AIza...
AI_PROVIDER=gemini
AI_MODEL=gemini-2.5-flash
```

### 4. Reiniciar el bot

```bash
python -m uvicorn app.main:app --reload
```

Deberías ver en los logs:
```
[ai] inicializado con gemini-2.5-flash.
```

## Modelos disponibles

Recomendados por costo/velocidad:
- `gemini-2.5-flash` (recomendado) — rápido, barato, buena calidad
- `gemini-1.5-flash` — alternativa estable
- `gemini-1.5-pro` — más preciso, más lento, más caro

## Costo

Google ofrece **1 millón de tokens gratis por mes** (suficiente para probar).

Una solicitud típica de clasificación:
- Input: ~200 tokens
- Output: ~50 tokens
- Con fallback en memoria: ~1000 clasificaciones gratis/mes

## ¿Qué hace IA en Music Bot?

1. **Fallback de intención:** si las reglas no clasifican, IA lo intenta
2. **Extracción de datos:** si el usuario responde algo corto/ambiguo, IA ayuda
3. **Validación:** IA confirma valores extraídos en flujos de cotización

## Desactivar sin desinstalar

Si quieres dejar la librería pero desactivar IA:

```env
AI_ENABLED=false
```

El bot seguirá funcionando con reglas puras.

## Solucionar problemas

### "ModuleNotFoundError: No module named 'google.generativeai'"

Instala: `pip install google-generativeai`

### "GEMINI_API_KEY no configurado"

Agrega la variable en `.env` (obtenla de [Google AI Studio](https://aistudio.google.com/app/apikey))

### "Error de API: INVALID_ARGUMENT"

Verifica que el modelo en `AI_MODEL` existe. Modelos válidos:
- `gemini-2.5-flash`
- `gemini-1.5-flash`
- `gemini-1.5-pro`

### El bot sigue funcioando sin IA

Perfectamente normal. IA es un fallback. Si `AI_ENABLED=false` o falla, el bot usa solo reglas.
