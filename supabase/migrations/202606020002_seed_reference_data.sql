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
   '¡Nuestra tierra huanca! La Ciudad Incontrastable siempre sabe celebrar bonito 🙌🎶',
   '¡Huancayo es casa! 🙌🎶 Qué bonito saber que nos escribes desde ahí.',
   'Nuestra tierra huanca siempre se hace presente 🙌🎶', true, 1),
  ('LOC-002', 'Tarma', 'tarma', 'Junín', 'Tarma',
   ARRAY['tierra de las flores','flores','tarmeño','tarmeña'],
   '¡Tarma, la tierra de las flores! 🌸 Ya suena a celebración bonita.',
   '¡Tarma presente! 🌸 Qué bonito saber que nos escribes desde la tierra de las flores.',
   'Tarma siempre tiene ese encanto especial de la tierra de las flores 🌸', true, 1),
  ('LOC-003', 'Lima', 'lima', 'Lima', 'Lima',
   ARRAY['lima capital','capital','todos salen adelante'],
   '¡Lima capital! Donde todos salen adelante y siempre hay motivo para celebrar 🙌',
   '¡Lima presente! 🙌🎶 Qué bueno saber que nos escribes desde la capital.',
   'Lima capital siempre tiene algo bonito por celebrar 🙌', true, 1),
  ('LOC-004', 'Jauja', 'jauja', 'Junín', 'Jauja',
   ARRAY['jauja querida','primera capital','aire bonito'],
   '¡Jauja querida! Con ese aire bonito y su gente alegre, el evento ya va tomando forma 🎶',
   '¡Jauja querida! 🙌🎶 Qué alegría saber que nos escribes desde ahí.',
   'Jauja querida siempre se siente con alegría 🙌🎶', true, 1),
  ('LOC-005', 'Concepción', 'concepcion', 'Junín', 'Concepción',
   ARRAY['concepcion','heroica','valle del mantaro'],
   '¡Concepción! Tierra bonita del Valle del Mantaro, ya va tomando forma esa celebración 🙌🎶',
   '¡Concepción presente! 🙌 Qué bonito saber que nos escribes desde ahí.',
   'Concepción siempre se hace presente con cariño 🙌', true, 1)
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
