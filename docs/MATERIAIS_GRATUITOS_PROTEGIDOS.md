# Materiais Gratuitos protegidos — APROVAJÁ

## Estado do repositório

Este repositório contém principalmente o coletor de concursos e scripts de processamento. A aplicação web do APROVAJÁ (menu, telas de login e painel administrativo) não está presente na árvore atual. Por isso, esta alteração prepara a camada de dados e especifica a integração, mas não adiciona por si só uma aba visual ao site.

## Pasta de origem

Google Drive: https://drive.google.com/drive/folders/1BysxqbAhqmPxVkGzqYwL9MAST-Eo5yNC?usp=sharing

## Modelo de segurança

- O catálogo fica em `public.materiais_gratuitos`.
- A leitura exige sessão autenticada no Supabase.
- Usuários comuns veem apenas materiais publicados.
- Apenas usuários com `app_metadata.role = "admin"` podem cadastrar, alterar, publicar/despublicar ou excluir materiais.
- O papel de administrador deve ser atribuído pelo servidor/administrador do projeto Supabase. Não use `user_metadata` para autorização, pois o próprio usuário pode alterar esses metadados.
- A tabela guarda o ID do arquivo no Drive, não um link público de download.

## Entrega protegida de arquivos do Drive

A tabela e as políticas RLS protegem o catálogo, mas não protegem um arquivo cujo link do Google Drive esteja público. Para que o acesso seja realmente protegido:

1. Remova o compartilhamento público dos arquivos que devem ser restritos.
2. Configure uma identidade de serviço Google (ou OAuth de servidor) com acesso de leitura somente à pasta de materiais.
3. Guarde as credenciais exclusivamente como secrets da Supabase Edge Function; nunca no frontend, GitHub ou tabela.
4. Implemente uma Edge Function `material-download` que valide o JWT do usuário, consulte o registro, confirme que está publicado (ou que o solicitante é administrador) e faça streaming do arquivo via Google Drive API. Não aceite IDs de arquivo arbitrários fornecidos pelo cliente.
5. O painel administrativo cadastra título, descrição, disciplina, categoria, tipo, ID do arquivo do Drive, ordem e status de publicação.
6. A aba do usuário consulta apenas os registros autorizados e solicita o arquivo à Edge Function. Não exponha o URL de download do Drive.

A Edge Function precisa limitar tipos/tamanho de arquivo, validar autenticação em cada chamada, retornar erros sem vazar credenciais e registrar falhas relevantes. O segredo de serviço nunca deve ser incluído no bundle web.

## Migração

Aplicar `database/migrations/20261028_materiais_gratuitos_protegidos.sql` no projeto Supabase correto após confirmar que o JWT de administradores utiliza `app_metadata.role = "admin"`. Se o APROVAJÁ já utiliza outro modelo de papéis, ajuste a função `public.aprovaja_is_admin()` para reutilizar o mecanismo existente antes de aplicar a migração.

## Próximas peças para integração completa

- Frontend: incluir a rota/aba “Materiais Gratuitos” no menu já existente.
- Admin: CRUD com formulário e validação de metadados.
- Edge Function: `material-download` com Google Drive API e validação do JWT.
- Configuração: secrets do Google e permissões restritas da pasta.
- Testes: usuário anônimo bloqueado; usuário autenticado vê apenas publicados; usuário comum não consegue escrever nem obter arquivo não publicado; administrador gerencia materiais; ID arbitrário não permite acesso a arquivo fora do catálogo.
