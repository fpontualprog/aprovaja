-- Materiais Gratuitos do APROVAJÁ
-- Acesso autenticado; somente administradores podem gerenciar o catálogo.
-- Não armazene links públicos de download. O arquivo deve ser entregue por uma Edge Function autenticada.

create table if not exists public.materiais_gratuitos (
  id uuid primary key default gen_random_uuid(),
  titulo text not null check (char_length(trim(titulo)) between 3 and 180),
  descricao text,
  disciplina text not null,
  categoria text,
  tipo_arquivo text not null default 'PDF',
  drive_file_id text not null,
  nome_arquivo text,
  publicado boolean not null default false,
  ordem integer not null default 0,
  criado_por uuid references auth.users(id) on delete set null,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  constraint materiais_gratuitos_drive_file_id_nonempty
    check (char_length(trim(drive_file_id)) > 0)
);

create index if not exists materiais_gratuitos_publicados_idx
  on public.materiais_gratuitos (publicado, ordem, criado_em desc);

create index if not exists materiais_gratuitos_disciplina_idx
  on public.materiais_gratuitos (disciplina);

create or replace function public.aprovaja_is_admin()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin', false);
$$;

alter table public.materiais_gratuitos enable row level security;

revoke all on table public.materiais_gratuitos from anon;
grant select, insert, update, delete on table public.materiais_gratuitos to authenticated;

drop policy if exists "Usuários autenticados veem materiais publicados" on public.materiais_gratuitos;
create policy "Usuários autenticados veem materiais publicados"
  on public.materiais_gratuitos
  for select
  to authenticated
  using (publicado = true or public.aprovaja_is_admin());

drop policy if exists "Administradores cadastram materiais" on public.materiais_gratuitos;
create policy "Administradores cadastram materiais"
  on public.materiais_gratuitos
  for insert
  to authenticated
  with check (public.aprovaja_is_admin() and (criado_por is null or criado_por = auth.uid()));

drop policy if exists "Administradores editam materiais" on public.materiais_gratuitos;
create policy "Administradores editam materiais"
  on public.materiais_gratuitos
  for update
  to authenticated
  using (public.aprovaja_is_admin())
  with check (public.aprovaja_is_admin());

drop policy if exists "Administradores excluem materiais" on public.materiais_gratuitos;
create policy "Administradores excluem materiais"
  on public.materiais_gratuitos
  for delete
  to authenticated
  using (public.aprovaja_is_admin());

comment on table public.materiais_gratuitos is
  'Catálogo de materiais do APROVAJÁ. Os arquivos do Drive devem ser privados e servidos por endpoint autenticado.';
comment on column public.materiais_gratuitos.drive_file_id is
  'ID do arquivo no Google Drive; nunca deve ser exposto como URL pública de download ao usuário.';
