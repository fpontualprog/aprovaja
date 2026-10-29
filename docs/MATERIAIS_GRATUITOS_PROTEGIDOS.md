# Materiais Gratuitos — integração técnica

## O que esta etapa implementa
- Catálogo consultado diretamente em `public.materiais_gratuitos`.
- RLS: usuários autenticados leem apenas materiais publicados; administradores são reconhecidos por `profiles.role = 'admin'`, que é o mecanismo já usado pelo HTML atual.
- `material-download`: valida o JWT, consulta o registro por UUID, verifica publicação/perfil e transmite o arquivo pelo servidor sem devolver URL do Drive.
- `sync-drive-materials`: apenas administradores podem listar a pasta configurada e importar arquivos novos como rascunhos. Não publica automaticamente.

## Configuração obrigatória no Supabase
Aplicar a migration `database/migrations/20261028_materiais_gratuitos_protegidos.sql` somente após revisão no projeto correto.

Deploy das funções:
- `supabase functions deploy material-download`
- `supabase functions deploy sync-drive-materials`

Secrets necessários nas Edge Functions:
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY` (somente secrets de servidor)
- `GOOGLE_SERVICE_ACCOUNT_JSON` (JSON da service account, nunca no frontend/repositório)
- `GOOGLE_DRIVE_FOLDER_ID` (ID da pasta, apenas para sincronização)

Compartilhe a pasta com o e-mail da service account com permissão de leitura. Para manter a segurança, prefira arquivos privados ou restritos à service account; não use links públicos como mecanismo de autorização. Mesmo que a interface não mostre o Drive, um arquivo compartilhado publicamente pode ser acessado por quem obtenha o link.

## Limite desta etapa
A sincronização importa nome, tipo e data do arquivo como rascunho. Ainda não extrai o conteúdo dos PDFs nem gera automaticamente disciplina, resumo e tópicos. Isso é uma etapa seguinte (extração de texto/OCR + classificação), mantendo aprovação humana antes de publicar.

## Testes de aceitação
1. Anônimo: download retorna 401.
2. Usuário comum: só vê publicados; não pode cadastrar ou editar.
3. Usuário comum: UUID de material não publicado retorna 403.
4. Administrador: sincroniza a pasta, revisa rascunhos e edita catálogo.
5. Arquivo: resposta de download não inclui URL do Drive.
6. IDs arbitrários: não permitem baixar arquivos que não estejam cadastrados no catálogo.
