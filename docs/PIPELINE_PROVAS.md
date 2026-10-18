# APROVAJÁ — pipeline independente de provas

Este pipeline é separado do coletor de concursos PCI. Não altera a interface web, não chama a Edge Function `receber-coleta-pci`, não acessa o Supabase e não insere registros em `public.banco_questoes`.

## Fluxo

1. Lê fontes e domínios permitidos em `config/fontes_provas.json`.
2. Visita páginas de entrada e links internos dentro dos domínios configurados.
3. Descobre links para PDF, baixa os documentos e calcula SHA-256.
4. Guarda o PDF original sem modificá-lo em `provas_data/originais/`.
5. Gera um JSON por documento com páginas, blocos de texto ordenados, coordenadas, imagens extraídas e render visual de cada página.
6. Publica o resultado como artefato do GitHub Actions para revisão.

## Preservação do conteúdo

- O PDF original é mantido.
- Cada página recebe uma imagem completa, preservando visualmente tabelas, gráficos, fórmulas e a disposição do texto.
- Blocos de texto e imagens possuem coordenadas aproximadas na página.
- Páginas sem camada de texto suficiente são marcadas com `requer_ocr: true`; OCR não é simulado nem preenchido por inferência.
- O estágio atual não garante a segmentação semântica de questões e alternativas. Essa é uma etapa posterior, que deve ser validada contra o PDF original.

## Execução manual

No GitHub, abrir **Actions → Pipeline independente de provas PDF → Run workflow**. O artefato `aprovaja-provas-...` inclui PDFs, JSON, imagens de página, imagens extraídas e relatório.

## Execução local

```bash
python -m pip install -r requirements-provas.txt
python provas_pipeline.py --max-downloads 10
```

## Segurança e operação

- Os domínios permitidos são definidos explicitamente na configuração.
- O limite padrão é de 10 PDFs por execução.
- O pipeline não grava resultados em tabelas do banco de produção.
- Antes de ampliar as fontes, verificar termos de uso, direitos de acesso e redistribuição.
- A configuração inicial das páginas de entrada é uma hipótese operacional e precisa ser testada no workflow; se algum endereço oficial tiver mudado ou bloquear robôs, o relatório registrará o erro e a fonte deverá ser ajustada.
