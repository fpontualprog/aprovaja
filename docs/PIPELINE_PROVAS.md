# APROVAJÁ — pipeline independente de provas

Este pipeline é separado do coletor de concursos PCI. Não chama a Edge Function `receber-coleta-pci` e não grava no Supabase.

## Fluxo atual

1. Lê as fontes e domínios permitidos em `config/fontes_provas.json`.
2. Descobre links de PDF nos domínios oficiais configurados das bancas.\n3. Valida cada PDF antes de processá-lo: o nome precisa identificar explicitamente prova/caderno de questões ou as páginas iniciais precisam conter sinais consistentes de prova. Editais, diários oficiais, resultados, convocações e documentos administrativos são rejeitados.\n4. Só então baixa/processa e preserva os PDFs aprovados.
3. Baixa PDFs, calcula SHA-256 e preserva os originais.
4. Gera JSON multimodal por documento, com texto por página, blocos posicionados, imagens extraídas e render de página.
5. Executa `segmentar_questoes_candidatas.py`, que aplica heurísticas conservadoras para localizar possíveis questões.
6. Publica os originais, JSON e arquivos de revisão como artefato do GitHub Actions.

## Lote de revisão

O artefato inclui:

- `provas_data/revisao/questoes_candidatas.json`
- `provas_data/revisao/questoes_candidatas.csv`

Cada candidato fica marcado como `PENDENTE_REVISAO`. A extração automática ainda não confirma limites, alternativas, disciplina, gabarito ou correspondência com figuras. O CSV serve para inspecionar e corrigir candidatos; confira sempre o PDF original.

## Limitações explícitas

- A segmentação é heurística e ocorre por página. Questões que continuam na página seguinte podem ficar divididas.
- Questões CEBRASPE de certo/errado e formatos de prova variados podem exigir regras específicas.
- Páginas com pouco texto continuam sinalizadas para OCR; OCR ainda não é executado.
- Gabaritos não são inferidos nem inventados.
- Nenhuma questão é inserida automaticamente no banco nesta fase.

## Próxima etapa

Após revisar a qualidade do lote, criar uma rotina de importação idempotente para `public.banco_questoes`, com validação de campos, deduplicação e preservação de mídia. A gravação em produção deve permanecer desativada até aprovação explícita.

## Segurança e direitos

Antes de ampliar as fontes ou redistribuir provas, verificar os termos de uso e os direitos aplicáveis. O pipeline deve continuar isolado do coletor PCI e dos dados de divulgação de concursos.
\n\n## Filtro de qualidade de documentos\n\nO módulo `validar_pdf_prova.py` aplica uma barreira antes da extração: rejeita nomes com marcadores administrativos (como edital, diário oficial, resultado e convocação); aceita nomes explicitamente identificados como prova/caderno de questões ou exige evidências no texto das três primeiras páginas. PDFs sem evidência suficiente ficam no relatório como `REJEITADO_NAO_E_PROVA` e não geram candidatos. O critério é deliberadamente conservador: pode deixar passar menos documentos, mas reduz o risco de misturar editais com provas. A validação ainda precisa ser calibrada com amostras reais de cada banca.\n