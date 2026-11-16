-- =====================================================================
-- Objetiva Mail · Rastreo de lectura de correos
-- =====================================================================
-- Diseño de privacidad:
--   * El servidor NUNCA guarda asunto, destinatarios, contenido ni enlaces
--     en texto claro. Solo un id aleatorio, la fecha y los eventos.
--   * "propietario" es el SHA-256 de un token que solo conoce la extensión
--     de cada persona. No contiene ni permite deducir su correo.
--   * "meta_cifrada" (asunto, destinatarios, enlaces) va cifrada con AES-GCM
--     en el navegador con una llave que nunca sale del Chrome de la persona.
--   * No se guarda la IP de quien abre: solo un hash con pimienta para
--     descartar duplicados.
--   * RLS activado y SIN políticas: ni la llave anon ni usuarios del CRM
--     pueden leer estas tablas; solo la Edge Function (service role).
-- =====================================================================

create table if not exists public.correo_rastreo (
  id              text primary key check (id ~ '^[a-f0-9]{32}$'),
  propietario     text not null check (propietario ~ '^[a-f0-9]{64}$'),
  meta_cifrada    text check (char_length(meta_cifrada) <= 20000),
  enlaces_hash    text[] not null default '{}',
  creado_en       timestamptz not null default now()
);

create index if not exists correo_rastreo_propietario_idx
  on public.correo_rastreo (propietario, creado_en desc);

create table if not exists public.correo_evento (
  id           bigserial primary key,
  rastreo_id   text not null references public.correo_rastreo(id) on delete cascade,
  tipo         text not null check (tipo in ('apertura', 'clic')),
  enlace       int,
  ocurrido_en  timestamptz not null default now(),
  origen       text not null default 'otro',   -- gmail | outlook | apple | yahoo | otro
  pais         text,
  ip_hash      text,
  descartado   text                            -- null = cuenta | propio | duplicado | bot
);

create index if not exists correo_evento_rastreo_idx
  on public.correo_evento (rastreo_id, ocurrido_en desc);

alter table public.correo_rastreo enable row level security;
alter table public.correo_evento  enable row level security;

-- Sin políticas a propósito: acceso solo vía service role (Edge Function).
revoke all on public.correo_rastreo from anon, authenticated;
revoke all on public.correo_evento  from anon, authenticated;
revoke all on sequence public.correo_evento_id_seq from anon, authenticated;

-- Limpieza: borra rastreos de más de 1 año (opcional, requiere pg_cron).
-- select cron.schedule('limpiar-correo-rastreo', '17 3 * * *',
--   $$delete from public.correo_rastreo where creado_en < now() - interval '365 days'$$);
