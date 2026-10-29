-- APROVAJÁ: catálogo protegido de Materiais Gratuitos
-- Não aplicar em produção antes de confirmar o projeto e testar permissões.
create sequence if not exists public.materiais_gratuitos_codigo_seq;

create table if not exists public.materiais_gratuitos (
  id uuid primary key default gen_random_uuid(),
  codigo text unique,
  titulo text not null check (char_length(trim(titulo)) between 3 and 180),
  descricao text,
  disciplina text not null default 'A classificar',
  categoria text,
  tipo_arquivo text not null default 'PDF',
  drive_file_id text not null,
  nome_arquivo text,
  conteudos_abordados text,
  palavras_chave text,
  drive_modified_time timestamptz,
  publicado boolean not null default false,
  ordem integer not null default 0,
  criado_por uuid references auth.users(id) on delete set null,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  constraint materiais_gratuitos_drive_file_id_nonempty check (char_length(trim(drive_file_id)) > 0)
);

alter table public.materiais_gratuitos add column if not exists codigo text;
alter table public.materiais_gratuitos add column if not exists conteudos_abordados text;
alter table public.materiais_gratuitos add column if not exists palavras_chave text;
alter table public.materiais_gratuitos add column if not exists drive_modified_time timestamptz;
alter table public.materiais_gratuitos add column if not exists atualizado_em timestamptz not null default now();

create unique index if not exists materiais_gratuitos_codigo_uidx on public.materiais_gratuitos (codigo) where codigo is not null;
create unique index if not exists materiais_gratuitos_drive_file_id_uidx on public.materiais_gratuitos (drive_file_id);
create index if not exists materiais_gratuitos_publicados_idx on public.materiais_gratuitos (publicado, ordem, criado_em desc);
create index if not exists materiais_gratuitos_disciplina_idx on public.materiais_gratuitos (disciplina);

create or replace function public.aprovaja_is_admin()
returns boolean
language sql
stable
security invoker
set search_path = public, auth
as $$
  select exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'admin'
  );
$$;

create or replace function public.aprovaja_material_codigo()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.codigo is null or btrim(new.codigo) = '' then
    new.codigo := 'MAT-' || lpad(nextval('public.materiais_gratuitos_codigo_seq')::text, 6, '0');
  end if;
  new.atualizado_em := now();
  return new;
end;
$$;

drop trigger if exists trg_materiais_gratuitos_codigo on public.materiais_gratuitos;
create trigger trg_materiais_gratuitos_codigo
before insert or update on public.materiais_gratuitos
for each row execute function public.aprovaja_material_codigo();

update public.materiais_gratuitos set codigo = null where codigo is null;

alter table public.materiais_gratuitos enable row level security;
revoke all on table public.materiais_gratuitos from anon;
grant select, insert, update, delete on public.materiais_gratuitos to authenticated;
revoke all on function public.aprovaja_is_admin() from public;
grant execute on function public.aprovaja_is_admin() to authenticated;

drop policy if exists "Usuários autenticados veem materiais publicados" on public.materiais_gratuitos;
create policy "Usuários autenticados veem materiais publicados"
on public.materiais_gratuitos for select to authenticated
using (publicado = true or public.aprovaja_is_admin());

drop policy if exists "Administradores cadastram materiais" on public.materiais_gratuitos;
create policy "Administradores cadastram materiais"
on public.materiais_gratuitos for insert to authenticated
with check (public.aprovaja_is_admin() and (criado_por is null or criado_por = auth.uid()));

drop policy if exists "Administradores editam materiais" on public.materiais_gratuitos;
create policy "Administradores editam materiais"
on public.materiais_gratuitos for update to authenticated
using (public.aprovaja_is_admin()) with check (public.aprovaja_is_admin());

drop policy if exists "Administradores excluem materiais" on public.materiais_gratuitos;
create policy "Administradores excluem materiais"
on public.materiais_gratuitos for delete to authenticated
using (public.aprovaja_is_admin());

comment on table public.materiais_gratuitos is
'Catálogo APROVAJÁ. Arquivos devem ser entregues por Edge Function autenticada; não expor links do Drive.';
