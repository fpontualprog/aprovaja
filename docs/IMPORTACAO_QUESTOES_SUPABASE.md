# APROVAJÁ — Importação de questões de provas PDF

## Arquitetura

- O pipeline coleta e preserva os PDFs originais e gera JSON/CSV de candidatos.
- `segmentar_questoes_candidatas.py` separa alternativas A–E quando os marcadores são explícitos.
- `publicar_questoes_supabase.py` agrupa candidatos por SHA-256 do PDF e envia lotes à Edge Function `importar-questoes-pdf`.
- A Edge Function registra os lotes em `public.banco_questoes_import_lotes` e candidatos em `public.banco_questoes_import_itens`.
- Só questões com enunciado, disciplina, gabarito válido, alternativas estruturadas quando aplicável e confiança alta podem ser inseridas em `public.banco_questoes`. Os demais ficam em `pendente_revisao`.
- Reenvios do mesmo PDF/candidato são idempotentes; a rotina não apaga nem atualiza questões existentes.

## Extração assistida por IA

O script `enriquecer_questoes_ia.py` usa o modelo multimodal `gpt-4.1-mini` para estruturar questões a partir do texto extraído e, quando há OCR pendente ou imagens no PDF, também usa a imagem da página. Ele produz campos estruturados para enunciado, alternativas, disciplina, assunto, texto de apoio, confiança e motivos de revisão.

A IA não deve inventar gabaritos. Nesta fase, o gabarito permanece vazio até o cruzamento com um documento oficial; portanto, essas questões ficam na fila de revisão mesmo quando a extração do enunciado é confiável. Se a chamada à IA falhar, o lote heurístico é preservado como alternativa.

## Configuração segura necessária

A automação de publicação fica desativada até que os segredos sejam configurados.

1. No Supabase, abra **Project Settings → Edge Functions → Secrets** e crie `APROVAJA_IMPORT_SECRET` com um valor aleatório forte. Não coloque esse valor no código nem em logs.
2. No GitHub, abra **Settings → Secrets and variables → Actions → New repository secret** e crie:
   - `APROVAJA_SUPABASE_URL`: URL do projeto Supabase Aprovajá_v2.
   - `APROVAJA_IMPORT_SECRET`: exatamente o mesmo valor configurado no Supabase.\n   - `OPENAI_API_KEY`: chave da API da OpenAI para ativar o enriquecimento por IA. Se ausente, o pipeline mantém a extração heurística.
3. Execute **Actions → Pipeline independente de provas PDF → Run workflow** com um lote pequeno.
4. Confira o resumo da execução e as tabelas de importação no Supabase antes de ampliar a coleta.

Se os segredos não estiverem configurados, o pipeline continua a gerar os artefatos de revisão, mas não envia candidatos ao banco.

## Política de validação

- Não inferir gabaritos nem inventar alternativas.
- A extração heurística não classifica disciplina/assunto com segurança; candidatos sem esses dados ficam em revisão.
- Questões de certo/errado precisam de gabarito oficial reconhecido.
- Imagens de página são preservadas como evidência para revisão. O vínculo automático de uma figura específica a uma questão não é presumido.
- Antes de redistribuir provas, conferir os direitos e termos aplicáveis à fonte.

## Monitoramento

Consultar `banco_questoes_import_lotes` para totais e estado do lote e `banco_questoes_import_itens` para cada candidato, motivo de revisão, duplicidade, erro e ID da questão importada.
