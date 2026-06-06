# Supabase CRM Design

Este diseno reemplaza Google Sheets por Supabase/PostgreSQL sin cambiar los
flujos del bot. La regla principal es conservar la conversacion completa, pero
no obligar al CRM ni al manager a leerla completa cada vez.

## Objetivos

- Mantener los servicios actuales del bot y cambiar solo repositorios.
- Guardar trazabilidad completa de WhatsApp, bot y administradores.
- Preparar un CRM futuro con historial, solicitudes, metricas y resumen.
- Evitar pantallas pesadas: el CRM debe paginar mensajes y usar resumen.
- Separar datos operativos de analitica y auditoria.

## Capas Del Modelo

### Identidad

`clients` guarda el telefono como identificador principal del cliente. El nombre
puede estar vacio porque el usuario puede no querer darlo.

`admins` guarda los managers autorizados. El bot debe seguir validando por
telefono y `active = true`.

### Conversacion

`conversation_threads` representa el estado actual del chat por cliente/canal:

- `BOT_ACTIVO`
- `ESPERANDO_RESPUESTA`
- `ADMIN_CONTROL`
- `CERRADA`

Esto reemplaza la hoja `Conversaciones`. Sirve para saber si el bot responde, si
hay una solicitud esperando o si un admin tiene el control.

`messages` guarda el historial completo. El CRM no debe cargar todo; debe pedir
los ultimos 50 mensajes y permitir "ver anteriores".

`message_attachments` guarda referencias a imagenes, audios o archivos. Los
binarios no deben guardarse dentro de Postgres; se guardan en Storage o por URL.

`conversation_summaries` guarda el resumen util para el admin/CRM. Ejemplo:

> Cliente busca precios para cumpleanos en Zapallanga, quincena de junio, 8 pm.
> No dejo nombre/DNI. Quiere cotizar antes de reservar.

### Solicitudes

`hiring_requests` reemplaza `SolicitudesContratacion`.

El codigo humano `SOL-0001` se genera con una secuencia, pero internamente se
usa `id uuid`. Esto permite escalar sin depender del codigo visible.

Caso importante:

- Si el cliente no da nombre: `name_or_dni = null`
- Siempre se conserva `client_phone`
- La observacion queda en `notes`

Estados esperados:

- `ABIERTA`
- `EN_CONVERSACION`
- `COTIZADA`
- `CERRADA`
- `DESCARTADA`

### Catalogos

`events` reemplaza `Eventos`.

`localities` reemplaza `Localidades` y guarda frases por localidad, keywords y
prioridad.

`group_contents` reemplaza `ContenidosAgrupacion`.

### CRM Y Seguimiento

`follow_ups` guarda administradores siguiendo una solicitud/cliente.

`interests` guarda interesados por localidad o presentacion.

`metrics` guarda eventos analiticos. No debe usarse como historial de chat; para
eso esta `messages`.

`internal_errors` reemplaza `Errores` para trazabilidad tecnica.

## Mapeo Desde Sheets

| Google Sheets | Supabase |
| --- | --- |
| Administradores | admins |
| Conversaciones | conversation_threads |
| SolicitudesContratacion | hiring_requests |
| Mensajes | messages |
| Eventos | events |
| Localidades | localities |
| Seguimientos | follow_ups |
| Metricas | metrics |
| InteresesLocalidad | interests |
| ContenidosAgrupacion | group_contents |
| Errores | internal_errors |

## Como Lo Usara El CRM

Vista de cliente:

1. Leer `clients`.
2. Leer `conversation_threads` activo.
3. Leer solicitud actual desde `hiring_requests`.
4. Leer resumen desde `conversation_summaries`.
5. Leer ultimos mensajes desde `messages order by created_at desc limit 50`.
6. Leer metricas agregadas desde `metrics`.

Vista de solicitudes:

1. Filtrar `hiring_requests` por `status`.
2. Ordenar por `last_interaction_at desc`.
3. Unirse con `clients` y `admins`.
4. Mostrar resumen si existe.

Vista de metricas:

1. Consultar `metrics` por rango de fechas.
2. Agregar por `flow`, `intent`, `city`, `step`.
3. Calcular conversion mirando `hiring_requests.status`.

## Politica De Historial

Recomendacion inicial:

- Guardar texto completo en `messages`.
- Guardar `raw_json` de WhatsApp solo mientras sea util para depuracion.
- Guardar multimedia como referencia en `message_attachments`.
- Crear resumen incremental por solicitud/thread.
- No borrar conversaciones por defecto; cerrar o archivar por estado.

Cuando haya volumen real:

- Retener `raw_json` 30 a 90 dias.
- Retener mensajes completos 12 a 24 meses segun necesidad legal/comercial.
- Archivar conversaciones antiguas si el CRM empieza a crecer mucho.

## Seguridad

El backend debe usar:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

No se debe exponer la service role key en frontend. Para el CRM web futuro, la
opcion mas segura es que el frontend llame a una API propia del backend, no
directamente a tablas sensibles.

La migracion SQL habilita RLS en todas las tablas. Sin politicas publicas, el
cliente anon no puede leer datos; el service role del backend si puede operar.

## Orden De Implementacion Recomendado

1. Crear proyecto Supabase y aplicar `supabase/migrations/202606020001_initial_crm_schema.sql`.
2. Agregar variables Supabase al `.env`.
3. Crear cliente Supabase backend.
4. Implementar repositorios nuevos manteniendo las mismas funciones publicas.
5. Empezar por `messages`, `conversation_threads`, `hiring_requests`.
6. Probar flujos completos del bot.
7. Migrar `events`, `localities`, `admins`.
8. Apagar Google Sheets cuando los flujos pasen en Supabase.

## Consultas Base Para El CRM

Ultimos mensajes:

```sql
select *
from public.messages
where thread_id = :thread_id
order by created_at desc
limit 50;
```

Solicitudes pendientes:

```sql
select hr.*, c.display_name, a.name as assigned_admin_name
from public.hiring_requests hr
join public.clients c on c.id = hr.client_id
left join public.admins a on a.id = hr.assigned_admin_id
where hr.status in ('ABIERTA', 'EN_CONVERSACION')
order by hr.last_interaction_at desc;
```

Resumen para tomar control:

```sql
select hr.code, hr.client_phone, hr.event_type, hr.event_date_text,
       hr.event_time_text, hr.locality, hr.name_or_dni, hr.notes,
       cs.summary
from public.hiring_requests hr
left join public.conversation_summaries cs on cs.request_id = hr.id
where hr.code = :code;
```
