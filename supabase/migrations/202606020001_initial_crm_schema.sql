-- Music Bot CRM schema for Supabase/PostgreSQL.
-- Backend-only access should use SUPABASE_SERVICE_ROLE_KEY.
-- RLS is enabled so future browser clients must go through explicit APIs/policies.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create sequence if not exists public.hiring_request_code_seq start 1;

create or replace function public.set_hiring_request_code()
returns trigger
language plpgsql
as $$
begin
  if new.code is null or btrim(new.code) = '' then
    new.code = 'SOL-' || lpad(nextval('public.hiring_request_code_seq')::text, 4, '0');
  end if;
  return new;
end;
$$;

create table public.clients (
  id uuid primary key default gen_random_uuid(),
  phone text not null unique,
  display_name text,
  profile_name text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  tags text[] not null default '{}',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint clients_phone_digits_chk check (phone ~ '^[0-9]{6,20}$')
);

create table public.admins (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  name text not null,
  phone text not null unique,
  role text not null default 'manager',
  active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint admins_phone_digits_chk check (phone ~ '^[0-9]{6,20}$')
);

create table public.conversation_threads (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  client_id uuid not null references public.clients(id) on delete restrict,
  channel text not null default 'whatsapp',
  client_phone text not null,
  state text not null default 'BOT_ACTIVO',
  current_admin_id uuid references public.admins(id) on delete set null,
  current_admin_phone text,
  current_request_id uuid,
  started_at timestamptz not null default now(),
  last_interaction_at timestamptz not null default now(),
  control_taken_at timestamptz,
  control_released_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint conversation_threads_unique_client_channel unique (client_id, channel),
  constraint conversation_threads_state_chk check (
    state in ('BOT_ACTIVO', 'ESPERANDO_RESPUESTA', 'ADMIN_CONTROL', 'CERRADA')
  )
);

create table public.hiring_requests (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  client_id uuid not null references public.clients(id) on delete restrict,
  thread_id uuid references public.conversation_threads(id) on delete set null,
  client_phone text not null,
  name_or_dni text,
  contact_phone text,
  assigned_admin_id uuid references public.admins(id) on delete set null,
  assigned_admin_phone text,
  status text not null default 'ABIERTA',
  attention_mode text not null default 'BOT',
  origin text not null default 'whatsapp',
  event_type text,
  event_date_text text,
  event_time_text text,
  locality text,
  last_client_message text,
  notes text,
  quote_amount numeric(12,2),
  quote_currency text default 'PEN',
  quoted_at timestamptz,
  closed_at timestamptz,
  discarded_at timestamptz,
  last_interaction_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint hiring_requests_status_chk check (
    status in ('ABIERTA', 'EN_SEGUIMIENTO', 'TOMADA_POR_ADMIN', 'EN_CONVERSACION', 'COTIZADA', 'CERRADA', 'DESCARTADA')
  ),
  constraint hiring_requests_attention_mode_chk check (attention_mode in ('BOT', 'ADMIN')),
  constraint hiring_requests_client_phone_digits_chk check (client_phone ~ '^[0-9]{6,20}$')
);

alter table public.conversation_threads
  add constraint conversation_threads_current_request_fk
  foreign key (current_request_id) references public.hiring_requests(id) on delete set null;

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  thread_id uuid references public.conversation_threads(id) on delete set null,
  client_id uuid references public.clients(id) on delete set null,
  request_id uuid references public.hiring_requests(id) on delete set null,
  admin_id uuid references public.admins(id) on delete set null,
  admin_phone text,
  phone text not null,
  direction text not null,
  sender_type text not null,
  message_type text not null default 'text',
  text text,
  button_payload text,
  flow text,
  intent text,
  external_message_id text unique,
  raw_json jsonb,
  raw_retained_until timestamptz,
  created_at timestamptz not null default now(),
  constraint messages_direction_chk check (
    direction in ('ENTRANTE', 'SALIENTE', 'ADMIN_A_CLIENTE', 'CLIENTE_A_ADMIN', 'ADMIN_INTERNO')
  ),
  constraint messages_sender_type_chk check (sender_type in ('CLIENT', 'BOT', 'ADMIN', 'SYSTEM')),
  constraint messages_phone_digits_chk check (phone ~ '^[0-9]{6,20}$')
);

create table public.message_attachments (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.messages(id) on delete cascade,
  media_type text not null,
  external_url text,
  storage_bucket text,
  storage_path text,
  mime_type text,
  file_size_bytes bigint,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.conversation_summaries (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.conversation_threads(id) on delete cascade,
  request_id uuid references public.hiring_requests(id) on delete cascade,
  summary text not null,
  client_intent text,
  pending_question text,
  event_details jsonb not null default '{}'::jsonb,
  last_message_id uuid references public.messages(id) on delete set null,
  generated_by text not null default 'bot',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint conversation_summaries_one_per_scope unique (thread_id, request_id)
);

create table public.events (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  event_date date,
  event_date_text text,
  start_time text,
  end_time text,
  city text not null,
  place text,
  google_maps_url text,
  status text not null default 'CONFIRMADO',
  ticket_price text,
  event_link text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint events_status_chk check (status in ('ACTIVO', 'CONFIRMADO', 'CANCELADO', 'BORRADOR'))
);

create table public.localities (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  name text not null,
  normalized_name text not null unique,
  region text,
  province text,
  keywords text[] not null default '{}',
  hiring_phrase text,
  events_phrase text,
  general_phrase text,
  active boolean not null default true,
  priority integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.follow_ups (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  request_id uuid references public.hiring_requests(id) on delete cascade,
  admin_id uuid references public.admins(id) on delete cascade,
  admin_phone text,
  client_id uuid references public.clients(id) on delete cascade,
  client_phone text not null,
  status text not null default 'ACTIVO',
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint follow_ups_status_chk check (status in ('ACTIVO', 'FINALIZADO'))
);

create table public.metrics (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  client_id uuid references public.clients(id) on delete set null,
  request_id uuid references public.hiring_requests(id) on delete set null,
  event_id uuid references public.events(id) on delete set null,
  phone text,
  intent text,
  flow text,
  step text,
  city text,
  chosen_option text,
  user_message text,
  bot_response text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.interests (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  client_id uuid references public.clients(id) on delete set null,
  phone text not null,
  name text,
  locality text,
  message text,
  status text not null default 'NUEVO',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint interests_status_chk check (status in ('NUEVO', 'CONTACTADO', 'CERRADO'))
);

create table public.group_contents (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  category text not null,
  title text not null,
  description text,
  url text,
  active boolean not null default true,
  priority integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.internal_errors (
  id uuid primary key default gen_random_uuid(),
  legacy_id text unique,
  module text,
  phone text,
  user_message text,
  error text not null,
  stacktrace text,
  raw_json jsonb,
  status text not null default 'NUEVO',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint internal_errors_status_chk check (status in ('NUEVO', 'REVISADO', 'IGNORADO'))
);

create trigger clients_set_updated_at
before update on public.clients
for each row execute function public.set_updated_at();

create trigger admins_set_updated_at
before update on public.admins
for each row execute function public.set_updated_at();

create trigger conversation_threads_set_updated_at
before update on public.conversation_threads
for each row execute function public.set_updated_at();

create trigger hiring_requests_set_code
before insert on public.hiring_requests
for each row execute function public.set_hiring_request_code();

create trigger hiring_requests_set_updated_at
before update on public.hiring_requests
for each row execute function public.set_updated_at();

create trigger conversation_summaries_set_updated_at
before update on public.conversation_summaries
for each row execute function public.set_updated_at();

create trigger events_set_updated_at
before update on public.events
for each row execute function public.set_updated_at();

create trigger localities_set_updated_at
before update on public.localities
for each row execute function public.set_updated_at();

create trigger follow_ups_set_updated_at
before update on public.follow_ups
for each row execute function public.set_updated_at();

create trigger interests_set_updated_at
before update on public.interests
for each row execute function public.set_updated_at();

create trigger group_contents_set_updated_at
before update on public.group_contents
for each row execute function public.set_updated_at();

create trigger internal_errors_set_updated_at
before update on public.internal_errors
for each row execute function public.set_updated_at();

create index clients_phone_idx on public.clients(phone);
create index admins_phone_active_idx on public.admins(phone, active);

create index conversation_threads_client_idx on public.conversation_threads(client_id);
create index conversation_threads_phone_state_idx on public.conversation_threads(client_phone, state);
create index conversation_threads_admin_idx on public.conversation_threads(current_admin_id);

create index hiring_requests_client_status_idx on public.hiring_requests(client_phone, status);
create index hiring_requests_status_updated_idx on public.hiring_requests(status, updated_at desc);
create index hiring_requests_assigned_admin_idx on public.hiring_requests(assigned_admin_id);
create index hiring_requests_code_idx on public.hiring_requests(code);

create index messages_thread_created_idx on public.messages(thread_id, created_at desc);
create index messages_phone_created_idx on public.messages(phone, created_at desc);
create index messages_request_created_idx on public.messages(request_id, created_at desc);
create index messages_intent_idx on public.messages(intent);
create index messages_raw_gin_idx on public.messages using gin (raw_json);

create index conversation_summaries_thread_idx on public.conversation_summaries(thread_id);
create index events_city_status_date_idx on public.events(city, status, event_date);
create index localities_active_priority_idx on public.localities(active, priority desc);
create index localities_keywords_gin_idx on public.localities using gin (keywords);
create index follow_ups_admin_status_idx on public.follow_ups(admin_id, status);
create unique index follow_ups_unique_active_idx
  on public.follow_ups(request_id, admin_id)
  where status = 'ACTIVO' and request_id is not null and admin_id is not null;
create index metrics_created_flow_idx on public.metrics(created_at desc, flow);
create index metrics_request_idx on public.metrics(request_id);
create index interests_phone_status_idx on public.interests(phone, status);
create index internal_errors_status_created_idx on public.internal_errors(status, created_at desc);

alter table public.clients enable row level security;
alter table public.admins enable row level security;
alter table public.conversation_threads enable row level security;
alter table public.hiring_requests enable row level security;
alter table public.messages enable row level security;
alter table public.message_attachments enable row level security;
alter table public.conversation_summaries enable row level security;
alter table public.events enable row level security;
alter table public.localities enable row level security;
alter table public.follow_ups enable row level security;
alter table public.metrics enable row level security;
alter table public.interests enable row level security;
alter table public.group_contents enable row level security;
alter table public.internal_errors enable row level security;
