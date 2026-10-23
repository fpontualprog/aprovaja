"""Leitura de gabaritos em PDF do Cebraspe."""
from __future__ import annotations
import re
from pathlib import Path
import fitz

# Aceita C/E e alternativas A-E, com ou sem hífen/dois-pontos entre os campos.
_PAIR_RE = re.compile(
    r"(?<!\d)(\d{1,3})\s*(?:[-.:)]\s*)?([A-E])(?=\s|$|[,;.)])",
    re.IGNORECASE,
)
_LINE_RE = re.compile(r"^\s*(\d{1,3})\s*(?:[-.:)]\s*)?([A-E])\s*$", re.IGNORECASE)


def extrair_gabarito_pdf(caminho_pdf: str | Path) -> dict[int, str]:
    """Retorna {número_da_questão: resposta}, ignorando texto sem par claro.

    Primeiro interpreta linhas isoladas (formato mais seguro); depois procura
    pares explícitos em linhas que tragam várias respostas, como tabelas extraídas.
    Em duplicidades mantém a primeira resposta encontrada.
    """
    respostas: dict[int, str] = {}
    with fitz.open(str(caminho_pdf)) as documento:
        texto = "\n".join(pagina.get_text("text", sort=True) for pagina in documento)

    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        match = _LINE_RE.fullmatch(linha)
        if match:
            numero, resposta = int(match.group(1)), match.group(2).upper()
            if 1 <= numero <= 300:
                respostas.setdefault(numero, resposta)
            continue

        # Em linhas tabulares, exige que o par esteja separado de outros
        # caracteres alfanuméricos para não confundir anos/códigos de cabeçalho.
        for match in _PAIR_RE.finditer(linha):
            numero, resposta = int(match.group(1)), match.group(2).upper()
            if 1 <= numero <= 300:
                respostas.setdefault(numero, resposta)

    return respostas
