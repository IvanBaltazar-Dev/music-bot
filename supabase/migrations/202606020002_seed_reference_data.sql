-- Datos de referencia del Music Bot (localidades + contenidos "Conoce la agrupación").
-- Idempotente: usa ON CONFLICT para no duplicar si se corre más de una vez.
-- Los EVENTOS y ADMINS se gestionan aparte (panel admin / .env).

-- ---------------------------------------------------------------------------
-- Localidades (frases personalizadas por ciudad). normalized_name es único.
-- ---------------------------------------------------------------------------
insert into public.localities
  (legacy_id, name, normalized_name, region, province, keywords,
   hiring_phrase, events_phrase, general_phrase, active, priority)
values
  ('LOC-001', 'Huancayo', 'huancayo', 'Junín', 'Huancayo',
   ARRAY['huanca','ciudad incontrastable','incontrastable','wanka'],
   '¡Huancayo, la Ciudad Incontrastable! Nos encanta celebrar en casa 🎶',
   'Qué bueno que nos escribas desde Huancayo, nuestra tierra.',
   'Huancayo, nuestra tierra, siempre presente.', true, 1),
  ('LOC-002', 'Tarma', 'tarma', 'Junín', 'Tarma',
   ARRAY['tierra de las flores','flores','tarmeño','tarmeña'],
   '¡Tarma, la tierra de las flores! 🌸 Suena a una buena celebración.',
   'Qué bueno que nos escribas desde Tarma, la tierra de las flores.',
   'Tarma siempre tiene el encanto de la tierra de las flores.', true, 1),
  ('LOC-003', 'Lima', 'lima', 'Lima', 'Lima',
   ARRAY['lima capital','capital','todos salen adelante'],
   '¡Lima! Siempre hay un buen motivo para celebrar.',
   'Qué bueno que nos escribas desde la capital.',
   'Lima, la capital, siempre con algo que celebrar.', true, 1),
  ('LOC-004', 'Jauja', 'jauja', 'Junín', 'Jauja',
   ARRAY['jauja querida','primera capital','aire bonito'],
   '¡Jauja querida! Con su gente alegre, la celebración ya toma forma 🎶',
   'Qué alegría que nos escribas desde Jauja.',
   'Jauja querida, siempre con alegría.', true, 1),
  ('LOC-005', 'Concepción', 'concepcion', 'Junín', 'Concepción',
   ARRAY['concepcion','heroica','valle del mantaro'],
   '¡Concepción, en el Valle del Mantaro! Buena tierra para celebrar 🎶',
   'Qué bueno que nos escribas desde Concepción.',
   'Concepción siempre presente.', true, 1)
on conflict (normalized_name) do nothing;

-- ---------------------------------------------------------------------------
-- Contenidos de "Conoce la agrupación". legacy_id es único.
-- ---------------------------------------------------------------------------
insert into public.group_contents
  (legacy_id, category, title, description, url, active, priority)
values
  ('CONT-001', 'QUIENES_SON', '¿Quiénes son?',
   'Agrupación que lleva música, alegría y sentimiento a cada presentación 🎶',
   null, true, 1),
  ('CONT-002', 'VIDEO', 'Video principal',
   'Presentación destacada para compartir con interesados',
   'https://www.youtube.com/watch?v=Q5JuJFnXWvI', true, 1),
  ('CONT-003', 'MUSICA', 'Canciones',
   'Lista o enlace de música oficial',
   'https://www.youtube.com/@Carlosferoficial', true, 2),
  ('CONT-004', 'RED_SOCIAL', 'Facebook',
   'Página oficial de la agrupación',
   'https://www.facebook.com/carlosferoficialmusic', true, 1),
  ('CONT-005', 'RED_SOCIAL', 'TikTok',
   'Contenido corto y presentaciones',
   'https://www.tiktok.com/@carlosferoficial', true, 2)
on conflict (legacy_id) do nothing;
