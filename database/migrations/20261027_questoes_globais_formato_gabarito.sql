-- Migração para aceitar gabaritos C/E/X (CEBRASPE) e A-E (múltipla escolha).
-- Execute primeiro os SELECTs de diagnóstico descritos na documentação.
-- Esta migração assume que a coluna é TEXT/VARCHAR e que a constraint antiga
-- se chama questoes_globais_gabarito_check. Não execute se gabarito for ENUM.

begin;

alter table public.questoes_globais
  add column if not exists formato_gabarito text;

update public.questoes_globais
set formato_gabarito = 'cebraspe'
where formato_gabarito is null;

alter table public.questoes_globais
  alter column formato_gabarito set default 'cebraspe';

alter table public.questoes_globais
  drop constraint if exists questoes_globais_gabarito_check;

alter table public.questoes_globais
  add constraint questoes_globais_gabarito_check
  check (
    gabarito is null
    or (formato_gabarito = 'cebraspe' and upper(gabarito) in ('C', 'E', 'X'))
    or (formato_gabarito = 'multipla_escolha' and upper(gabarito) in ('A', 'B', 'C', 'D', 'E'))
  );

commit;
