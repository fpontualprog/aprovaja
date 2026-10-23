# concursos-collector

Coletor de provas de concursos publicos, comecando pelo Cebraspe.

## O que faz

1. Descobre concursos encerrados via API do Cebraspe.
2. Baixa PDFs de provas objetivas do CDN.
3. Pre-processa o PDF (separacao de colunas, extracao de questoes).
4. Estrutura as questoes via DeepSeek (JSON).
5. Exporta para CSV/XLSX.

## Como rodar localmente

    pip install -r requirements.txt
    cp .env.example .env
    # edite .env e coloque sua DEEPSEEK_API_KEY
    python scripts/run_single.py --evento PF_25_ADM

## Estrutura

- src/discovery/ - descoberta de PDFs (API do Cebraspe).
- src/extraction/ - pre-processamento do PDF (pymupdf).
- src/structuring/ - chamada a DeepSeek.
- src/export/ - geracao de CSV/XLSX.
- src/pipeline.py - orquestra as etapas (ainda ausente).

## Limitacoes

- So Cebraspe por enquanto.
- So questoes certo/errado (formato do Cebraspe).
- Gabarito nao incluido (pode ser buscado em etapa separada).

## Estado da implementacao

O arquivo `scripts/run_single.py` e a estrutura inicial foram adicionados. O pipeline ainda nao executa ate que sejam implementados os modulos de descoberta, extracao, estruturacao, exportacao e `src/pipeline.py`.
