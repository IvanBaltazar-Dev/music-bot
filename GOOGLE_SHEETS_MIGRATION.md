# Migración de Google Sheets - Music Bot

**Fecha:** 2026-06-01  
**Cambios:** Eliminar 4 hojas, limpiar campos, agregar auditoría

---

## ⚠️ INSTRUCCIONES IMPORTANTES

**NO importes archivos automáticamente.** Este es un documento de referencia para actualizar MANUALMENTE en Google Sheets.

**Orden de operaciones:**
1. **Primero:** Revisar estructura actual vs nueva
2. **Segundo:** Eliminar las 4 hojas muertas (abajo)
3. **Tercero:** Actualizar encabezados (abajo)
4. **Cuarto:** Borrar filas de datos si tienen columnas que ya no existen

---

## 🗑️ HOJAS A ELIMINAR (4)

En tu Google Sheets, **ELIMINA** estas hojas si existen:
- [ ] `ConfiguracionBot`
- [ ] `Usuarios`
- [ ] `NotificacionesAdmin`
- [ ] `Catalogos`

**Instrucciones:** Click derecho en la pestaña → Eliminar hoja → Confirmar

---

## 📋 HOJAS A MANTENER CON ENCABEZADOS NUEVOS (11)

### 1. **Eventos**
**Encabezados (12 columnas, A–L):**
```
id_evento | fecha_evento | hora_inicio | hora_fin | ciudad | lugar | google_maps_url | estado | fecha_creacion | fecha_actualizacion | precio_entrada | link_evento
```

**Columnas K–L (datos públicos del evento):**
- precio_entrada → precio que ve el cliente en "Entradas" (si está vacío, el bot
  ofrece avisar a un asesor).
- link_evento → link para "Pasar la voz" (compartir). Agrégalas a la derecha de
  `fecha_actualizacion`.

**Columnas a ELIMINAR (si existen):**
- provincia, region, entrada_descripcion, entrada_link, flyer_url, post_url, descripcion_publica, notas_internas, creado_por

---

### 2. **SolicitudesContratacion**
**Encabezados (14 columnas, A–N):**
```
codigo_solicitud | fecha_registro | estado | numero_cliente | nombre_o_dni | admin_asignado | modo_atencion | fecha_ultima_interaccion | observaciones | origen | tipo_evento | fecha_evento | horario_evento | localidad
```

**Columnas K–N (detalles del evento que pidió el cliente):**
- tipo_evento, fecha_evento, horario_evento, localidad
- Se muestran al admin en la notificación de nueva solicitud, "ver solicitud" y
  "tomar control". Agrégalas a la derecha de `origen`, en ese orden exacto.

**Columnas a ELIMINAR (si existen):**
- numero_contacto, cantidad_personas, ultimo_mensaje_cliente

---

### 3. **InteresesLocalidad**
**Encabezados (SIN CAMBIOS - 7 columnas):**
```
id_interes | fecha_hora | numero_usuario | nombre | localidad | mensaje | estado
```

---

### 4. **Conversaciones** ← CAMBIOS IMPORTANTES
**Encabezados NUEVOS (8 columnas):**
```
id_conversacion | numero_usuario | estado_conversacion | admin_numero | fecha_inicio | fecha_ultima_interaccion | fecha_toma_control | fecha_suelta_control
```

**Columnas a ELIMINAR (si existen):**
- flujo_actual (nunca se actualizaba)
- paso_actual (nunca se actualizaba)
- datos_temporales_json (dump sin schema)
- admin_en_control (redundante)

---

### 5. **Mensajes**
**Encabezados (SIN CAMBIOS - 12 columnas):**
```
id_mensaje | fecha_hora | numero_usuario | direccion | tipo_mensaje | texto | payload_boton | flujo_detectado | intencion_detectada | codigo_solicitud | admin_numero | raw_json
```

---

### 6. **Administradores**
**Encabezados (SIN CAMBIOS - 5 columnas):**
```
id_admin | nombre | telefono | rol | activo
```

---

### 7. **Seguimientos**
**Encabezados (SIN CAMBIOS - 6 columnas):**
```
id_seguimiento | codigo_solicitud | admin_numero | numero_cliente | fecha_inicio | estado
```

---

### 8. **Metricas**
**Encabezados (SIN CAMBIOS - 12 columnas):**
```
id_metrica | fecha_hora | numero_usuario | intencion_detectada | flujo | paso | ciudad_mencionada | opcion_elegida | mensaje_usuario | respuesta_bot | codigo_solicitud | id_evento
```

---

### 9. **ContenidosAgrupacion**
**Encabezados (SIN CAMBIOS - 8 columnas):**
```
id_contenido | tipo | titulo | descripcion | url | orden | activo | fecha_actualizacion
```

---

### 10. **Localidades**
**Encabezados (SIN CAMBIOS - 11 columnas):**
```
id_localidad | nombre_localidad | nombre_normalizado | region | provincia | palabras_clave | frase_contratacion | frase_eventos | frase_general | activo | prioridad | fecha_actualizacion
```

---

### 11. **Errores**
**Encabezados (SIN CAMBIOS - 9 columnas):**
```
id_error | fecha_hora | modulo | numero_usuario | mensaje_usuario | error | stacktrace | raw_json | estado
```

---

## 🔧 CÓMO ACTUALIZAR MANUALMENTE EN GOOGLE SHEETS

### Para cada hoja que CAMBIA (Eventos, SolicitudesContratacion, Conversaciones):

1. **Inserta fila nueva en el tope:**
   - Click en fila 1
   - Click derecho → Insertar 1 fila arriba
   
2. **Copia los encabezados nuevos** (de arriba) en esa fila 1

3. **Elimina las columnas viejas** que ya no se usan:
   - Selecciona la columna (click en la letra)
   - Click derecho → Eliminar columna
   
4. **Reorganiza columnas** si es necesario para que coincidan con el orden de arriba

5. **Verifica:** Fila 1 debe tener exactamente los encabezados listados

---

## 📊 RESUMEN DE CAMBIOS

| Hoja | Estado | Cambio |
|------|--------|--------|
| Eventos | MODIFICA | 12 cols (10 base + precio_entrada, link_evento al final) |
| SolicitudesContratacion | MODIFICA | 17 → 14 cols (quita 7, repone 4 del evento: tipo_evento, fecha_evento, horario_evento, localidad) |
| Conversaciones | MODIFICA | 10 → 8 cols (elimina 4, agrega 2 nuevas) |
| InteresesLocalidad | SIN CAMBIOS | 7 cols |
| Mensajes | SIN CAMBIOS | 12 cols |
| Administradores | SIN CAMBIOS | 5 cols |
| Seguimientos | SIN CAMBIOS | 6 cols |
| Metricas | SIN CAMBIOS | 12 cols |
| ContenidosAgrupacion | SIN CAMBIOS | 8 cols |
| Localidades | SIN CAMBIOS | 11 cols |
| Errores | SIN CAMBIOS | 9 cols |

**Hojas a ELIMINAR:** 4 (ConfiguracionBot, Usuarios, NotificacionesAdmin, Catalogos)

---

## ✅ CHECKLIST DE MIGRACIÓN

- [ ] Eliminar hoja `ConfiguracionBot`
- [ ] Eliminar hoja `Usuarios`
- [ ] Eliminar hoja `NotificacionesAdmin`
- [ ] Eliminar hoja `Catalogos`
- [ ] Actualizar hoja `Eventos` (agregar K–L: precio_entrada, link_evento)
- [ ] Actualizar hoja `SolicitudesContratacion` (quitar numero_contacto, cantidad_personas, ultimo_mensaje_cliente; agregar K–N: tipo_evento, fecha_evento, horario_evento, localidad)
- [ ] Actualizar hoja `Conversaciones` (eliminar 4, agregar 2)
- [ ] Verificar que todas las filas de datos sean compatibles
- [ ] Hacer backup antes de cambios (descargar como Excel)
- [ ] Probar que el bot siga funcionando (ejecutar `/ayuda admin`)

---

## ⚡ NOTAS IMPORTANTES

- **No se pierden datos de filas:** Solo se limpian columnas innecesarias
- **El bot crea hojas muertas automáticamente:** Pero solo si no existen
- **Cambios retroactivos:** Si tienes datos en columnas que se eliminan, esos datos se pierden. Haz backup primero.
- **Orden de columnas:** Debe coincidir EXACTAMENTE con el orden de arriba

---

## 🆘 SI ALGO SALE MAL

1. **Deshaz cambios en Google Sheets:** Ctrl+Z (o Cmd+Z)
2. **Restaura desde backup:** Descarga la versión anterior
3. **Contacta devops:** Si el bot se comporta raro después de cambios

---

**Estado:** Pronto el bot creará automáticamente las hojas nuevas si faltan, pero es mejor actualizar manualmente para estar seguro.
