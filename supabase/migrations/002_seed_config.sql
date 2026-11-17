-- Seed KONFIGURASI (bukan data tender/lead). Keyword dapat diubah admin di dashboard.
insert into public.tender_keywords (keyword, category, language) values
 ('Waste Management Equipment','Waste Management','en'),
 ('Waste Processing Machine','Waste Management','en'),
 ('Waste Treatment','Waste Management','en'),
 ('Waste Sorting Equipment','Waste Management','en'),
 ('Recycling Machine','Recycling Equipment','en'),
 ('Plastic Recycling Machine','Recycling Equipment','en'),
 ('Plastic Processing Equipment','Recycling Equipment','en'),
 ('Material Recovery Facility','Recycling Equipment','en'),
 ('Crusher Machine','Industrial Machinery','en'),
 ('Shredder Machine','Industrial Machinery','en'),
 ('Industrial Shredder','Industrial Machinery','en'),
 ('Industrial Crusher','Industrial Machinery','en'),
 ('Conveyor System','Industrial Machinery','en'),
 ('Replacement Blades','Industrial Machinery','en'),
 ('Machine Spare Parts','Industrial Machinery','en'),
 ('Environmental Equipment','Environmental Facilities','en'),
 ('Environmental Facilities','Environmental Facilities','en'),
 ('Wastewater Treatment','Environmental Facilities','en'),
 ('Water Treatment Equipment','Environmental Facilities','en'),
 ('Incinerator','Environmental Facilities','en'),
 ('Solid Waste Management','Environmental Facilities','en'),
 ('Mesin pengolahan sampah','Waste Management','id'),
 ('Mesin pencacah sampah','Waste Management','id'),
 ('Mesin penghancur plastik','Recycling Equipment','id'),
 ('Mesin crusher','Industrial Machinery','id'),
 ('Mesin shredder','Industrial Machinery','id'),
 ('Pisau crusher','Industrial Machinery','id'),
 ('Pisau shredder','Industrial Machinery','id'),
 ('Instalasi pengolahan air limbah','Environmental Facilities','id'),
 ('Fasilitas pengolahan limbah','Environmental Facilities','id'),
 ('Peralatan pengelolaan lingkungan','Environmental Facilities','id');

-- Sumber awal. health_status 'untested' sampai konektor benar-benar diuji.
-- LPSE per-instansi ditambahkan admin lewat dashboard (Fase 2).
insert into public.tender_sources (name, adapter_type, base_url) values
 ('SIRUP LKPP','sirup','https://sirup.lkpp.go.id'),
 ('INAPROC LKPP','inaproc','https://inaproc.id');
