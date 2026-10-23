"""Constantes compartilhadas pelo pipeline."""

CEBRASPE_API_BASE = "https://apis.cebraspe.org.br/cebraspe"
CEBRASPE_API_LISTA = CEBRASPE_API_BASE + "/eventos/tipo/concursos/fase/encerrado"
CEBRASPE_API_DETALHE = CEBRASPE_API_BASE + "/eventos/{evento_url}"
CEBRASPE_CDN = "https://cdn.cebraspe.org.br/concursos/{evento_url}/arquivos/{nome_arquivo}"

CORTE_X = 300

MARCADORES_APOIO = [
    "julgue os itens",
    "julgue o proximo item",
    "julgue o item",
    "com base no texto",
    "com base na proposicao",
    "com base nas informacoes",
    "com base no disposto",
    "considere que",
    "considerando que",
    "julgue os seguintes",
    "julgue os proximos",
    "acerca das ideias",
    "acerca do regime",
    "acerca de",
]

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_MAX_TOKENS = 4096
