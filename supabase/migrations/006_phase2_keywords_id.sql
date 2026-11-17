-- Fase 2 — keyword tambahan berbahasa Indonesia (idempoten, non-destruktif).
--
-- Kenapa perlu: keyword seed 002 hampir semuanya frasa bahasa Inggris
-- ("Waste Management Equipment", dst.), sedangkan judul paket SPSE berbahasa
-- Indonesia ("Pembangunan Fasilitas Bank Sampah Induk ...", dst.). Akibatnya
-- pencocokan meleset hampir total. Keyword di bawah berupa kata/frasa yang
-- benar-benar muncul di judul paket. Admin tetap bisa mengubahnya di dashboard.
--
-- Aman dijalankan berulang: on conflict (keyword) do nothing.

insert into public.tender_keywords (keyword, category, language) values
  -- Waste Management
  ('sampah','Waste Management','id'),
  ('pengelolaan sampah','Waste Management','id'),
  ('pengolahan sampah','Waste Management','id'),
  ('persampahan','Waste Management','id'),
  ('bank sampah','Waste Management','id'),
  ('pemilahan sampah','Waste Management','id'),
  ('tpst','Waste Management','id'),
  ('tpa','Waste Management','id'),
  ('pltsa','Waste Management','id'),
  -- Environmental Facilities
  ('limbah','Environmental Facilities','id'),
  ('air limbah','Environmental Facilities','id'),
  ('pengelolaan limbah','Environmental Facilities','id'),
  ('pengolahan limbah','Environmental Facilities','id'),
  ('pengolahan air limbah','Environmental Facilities','id'),
  ('ipal','Environmental Facilities','id'),
  ('instalasi pengolahan air limbah','Environmental Facilities','id'),
  ('insinerator','Environmental Facilities','id'),
  ('lingkungan hidup','Environmental Facilities','id'),
  ('pengelolaan lingkungan','Environmental Facilities','id'),
  ('limbah b3','Environmental Facilities','id'),
  ('sanitasi','Environmental Facilities','id'),
  ('emisi','Environmental Facilities','id'),
  -- Recycling Equipment
  ('daur ulang','Recycling Equipment','id'),
  ('kompos','Recycling Equipment','id'),
  ('komposting','Recycling Equipment','id'),
  ('pengomposan','Recycling Equipment','id'),
  ('biogas','Recycling Equipment','id'),
  -- Industrial Machinery
  ('mesin pencacah','Industrial Machinery','id'),
  ('mesin pengolah','Industrial Machinery','id'),
  ('conveyor','Industrial Machinery','en'),
  ('crusher','Industrial Machinery','en'),
  ('shredder','Industrial Machinery','en')
on conflict (keyword) do nothing;
