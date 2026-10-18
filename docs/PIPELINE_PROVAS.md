# APROVAJÁ — pipeline independente de provas

Este pipeline é separado do coletor de concursos PCI. Não chama a Edge Function `receber-coleta-pci` e não grava no Supabase.

## Fluxo atual

1. Lê as fontes e domínios permitidos em `config/fontes_provas.json`.
2. Descobre links de PDF nas páginas configuradas.
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
