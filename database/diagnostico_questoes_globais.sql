-- Diagnóstico somente leitura para public.questoes_globais.
-- Execute no Supabase SQL Editor antes de aplicar a migração.
select column_name, data_type, udt_name
from information_schema.columns
where table_schema = 'public'
  and table_name = 'questoes_globais'
  and column_name in ('gabarito', 'formato_gabarito');

select conname, pg_get_constraintdef(oid) as definicao
from pg_constraint
where conrelid = 'public.questoes_globais'::regclass
  and contype = 'c';

select t.typname, e.enumlabel
from pg_type t
join pg_enum e on e.enumtypid = t.oid
where t.typname ilike '%gabarito%'
order by t.typname, e.enumsortorder;
