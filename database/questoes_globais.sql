-- Banco mestre global de questões coletadas para o APROVAJÁ.
-- Execute no SQL Editor do Supabase antes de rodar o importador.
create extension if not exists pgcrypto;

create table if not exists public.questoes_globais (
    id uuid primary key default gen_random_uuid(),
    evento_url text not null,
    numero integer not null,
    enunciado text not null,
    texto_apoio text null,
    disciplina text null,
    tipo text not null default 'certo_errado',
    gabarito text null,
    imagens text[] not null default '{}'::text[],
    criado_em timestamptz not null default now(),
    constraint questoes_globais_evento_numero_key unique (evento_url, numero),
    constraint questoes_globais_gabarito_check
        check (gabarito is null or upper(gabarito) in ('C', 'E', 'X'))
);

create index if not exists questoes_globais_evento_numero_idx
    on public.questoes_globais (evento_url, numero);

-- A tabela é um acervo global. Não exponha a service-role key no frontend.
-- Configure RLS/policies conforme a política de leitura desejada pelo app.
alter table public.questoes_globais enable row level security;

-- Permite que usuários autenticados consultem o acervo global pelo cliente do app.
drop policy if exists "questoes_globais_select_authenticated" on public.questoes_globais;
create policy "questoes_globais_select_authenticated"
    on public.questoes_globais
    for select
    to authenticated
    using (true);
