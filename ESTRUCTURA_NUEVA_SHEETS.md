# Estructura NUEVA de Google Sheets - Music Bot

**Última actualización:** 2026-06-01  
**Estado:** Lista para copiar/pegar en Google Sheets

---

## 📋 LISTA RÁPIDA DE ENCABEZADOS POR HOJA

Copia los encabezados de abajo, pega en fila 1 de cada hoja en Google Sheets.

---

## 1. **Eventos**
```
id_evento	fecha_evento	hora_inicio	hora_fin	ciudad	lugar	google_maps_url	estado	fecha_creacion	fecha_actualizacion	precio_entrada	link_evento
```
**12 columnas (A–L).** Las últimas 2 (K–L: precio_entrada, link_evento) son
datos públicos del evento: se muestran al cliente (precio en "Entradas", link en
"Pasar la voz"). Agrégalas a la derecha de `fecha_actualizacion`, con esos
nombres exactos.

**Estados:** ACTIVO/CONFIRMADO = visible al cliente; CANCELADO = oculto.

---

## 2. **SolicitudesContratacion**
```
codigo_solicitud	fecha_registro	estado	numero_cliente	nombre_o_dni	admin_asignado	modo_atencion	fecha_ultima_interaccion	observaciones	origen	tipo_evento	fecha_evento	horario_evento	localidad
```
**14 columnas (A–N).** Las primeras 10 (A–J) son las base; las últimas 4 (K–N:
tipo_evento, fecha_evento, horario_evento, localidad) guardan lo que pidió el
cliente y se muestran al admin en la notificación, "ver solicitud" y "tomar
control".

**Si vienes de la versión de 10 columnas:** agrega SOLO esas 4 columnas a la
derecha de `origen` (columnas K, L, M, N), con esos nombres exactos y en ese
orden. No insertes columnas en medio.

**Siguen eliminadas (no las repongas):** numero_contacto, cantidad_personas,
ultimo_mensaje_cliente.

---

## 3. **InteresesLocalidad** (SIN CAMBIOS)
```
id_interes	fecha_hora	numero_usuario	nombre	localidad	mensaje	estado
```

---

## 4. **Conversaciones** ← IMPORTANTE
```
id_conversacion	numero_usuario	estado_conversacion	admin_numero	fecha_inicio	fecha_ultima_interaccion	fecha_toma_control	fecha_suelta_control
```
**Cambios:** 
- ❌ Elimina: flujo_actual, paso_actual, datos_temporales_json, admin_en_control
- ✅ Agrega: fecha_toma_control, fecha_suelta_control

---

## 5. **Mensajes** (SIN CAMBIOS)
```
id_mensaje	fecha_hora	numero_usuario	direccion	tipo_mensaje	texto	payload_boton	flujo_detectado	intencion_detectada	codigo_solicitud	admin_numero	raw_json
```

---

## 6. **Administradores** (SIN CAMBIOS)
```
id_admin	nombre	telefono	rol	activo
```

---

## 7. **Seguimientos** (SIN CAMBIOS)
```
id_seguimiento	codigo_solicitud	admin_numero	numero_cliente	fecha_inicio	estado
```

---

## 8. **Metricas** (SIN CAMBIOS)
```
id_metrica	fecha_hora	numero_usuario	intencion_detectada	flujo	paso	ciudad_mencionada	opcion_elegida	mensaje_usuario	respuesta_bot	codigo_solicitud	id_evento
```

---

## 9. **ContenidosAgrupacion** (SIN CAMBIOS)
```
id_contenido	tipo	titulo	descripcion	url	orden	activo	fecha_actualizacion
```

---

## 10. **Localidades** (SIN CAMBIOS)
```
id_localidad	nombre_localidad	nombre_normalizado	region	provincia	palabras_clave	frase_contratacion	frase_eventos	frase_general	activo	prioridad	fecha_actualizacion
```

---

## 11. **Errores** (SIN CAMBIOS)
```
id_error	fecha_hora	modulo	numero_usuario	mensaje_usuario	error	stacktrace	raw_json	estado
```

---

## 🗑️ HOJAS A ELIMINAR

Elimina estas 4 hojas de tu Google Sheets si existen:
1. ConfiguracionBot
2. Usuarios
3. NotificacionesAdmin
4. Catalogos

---

## 🔧 CÓMO ACTUALIZAR EN GOOGLE SHEETS

### Para hojas SIN CAMBIOS (7 hojas):
- ✅ No necesitas hacer nada

### Para hojas CON CAMBIOS (3 hojas):

**Paso 1:** Abre la hoja en Google Sheets  
**Paso 2:** Selecciona toda la fila 1 (encabezados)  
**Paso 3:** Copia los encabezados NUEVOS de arriba  
**Paso 4:** Pega en fila 1 (reemplaza los viejos)  
**Paso 5:** Elimina las columnas viejas que ya no están en la lista  

---

## ⚡ NOTAS IMPORTANTES

1. **Tab-separated:** Los encabezados arriba están separados por TABS (no espacios), así que cuando los copies y pegues en Google Sheets se van a columnas automáticamente.

2. **Datos existentes:** 
   - Los datos que ya tienes en columnas que se MANTIENEN, se quedan
   - Los datos en columnas que se ELIMINAN, se pierden (haz backup primero)

3. **Orden:** El orden de columnas debe coincidir EXACTAMENTE con lo de arriba. Si no, el bot no leerá correctamente.

4. **Backup:** Antes de cambiar, descarga tu Google Sheets actual como Excel por si algo sale mal.

---

## ✅ CHECKLIST FINAL

- [ ] Backup de Google Sheets actual (Archivo → Descargar)
- [ ] Eliminar 4 hojas muertas
- [ ] Actualizar encabezados de **Eventos** (12 cols; agregar K–L: precio_entrada, link_evento)
- [ ] Actualizar encabezados de **SolicitudesContratacion** (14 cols; agregar K–N: tipo_evento, fecha_evento, horario_evento, localidad)
- [ ] Actualizar encabezados de **Conversaciones** (copiar/pegar + eliminar 4 cols viejas)
- [ ] Verificar orden de columnas
- [ ] Probar que el bot funcione (`/ayuda admin`)

---

## 🆘 SI ALGO FALLA

**Opción 1:** Deshaz en Google Sheets (Ctrl+Z varias veces)  
**Opción 2:** Restaura desde el backup que descargaste  
**Opción 3:** Contacta devops

---

**Última nota:** Este documento refleja exactamente lo que el código espera. Si algo no funciona, probablemente es por orden de columnas.
