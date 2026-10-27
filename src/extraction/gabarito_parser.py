"""Leitura de gabaritos em PDF do Cebraspe."""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

# Pares explícitos em formatos simples, inclusive itens anulados (X).
_PAIR_RE = re.compile(
    r"(?<!\d)(\d{1,3})\s*(?:[-.:)]\s*)?([A-EX])(?=\s|$|[,;.)])",
    re.IGNORECASE,
)
_LINE_RE = re.compile(
    r"^\s*(\d{1,3})\s*(?:[-.:)]\s*)?([A-EX])\s*$",
    re.IGNORECASE,
)
_ITEM_ROW_RE = re.compile(r"^\s*Item\b(.*)$", re.IGNORECASE)
_ANSWER_ROW_RE = re.compile(r"^\s*Gabarito\b(.*)$", re.IGNORECASE)


def _numeros_da_linha(conteudo: str) -> list[int]:
    return [int(valor) for valor in re.findall(r"\b\d{1,3}\b", conteudo)]


def _respostas_da_linha(conteudo: str) -> list[str]:
    return [
        valor.upper()
        for valor in re.findall(r"\b([CEX])\b", conteudo, re.IGNORECASE)
    ]


def extrair_gabarito_pdf(caminho_pdf: str | Path) -> dict[int, str]:
    """Extrai respostas de tabelas CEBRASPE e de formatos simples.

    Em tabelas, associa os números da linha Item às respostas da linha
    Gabarito pela posição da coluna. Aceita C, E e X (item anulado), ignora
    zeros de preenchimento e preserva o primeiro valor em duplicidades.
    """
    with pymupdf.open(str(caminho_pdf)) as documento:
        texto = "\n".join(
            pagina.get_text("text", sort=True) for pagina in documento
        )

    linhas = texto.splitlines()
    respostas: dict[int, str] = {}
    linhas_tabulares: set[int] = set()

    # Prioriza a estrutura tabular oficial: Item na linha e Gabarito abaixo.
    for indice, linha in enumerate(linhas):
        item_match = _ITEM_ROW_RE.match(linha)
        if not item_match:
            continue

        proximo = indice + 1
        while proximo < len(linhas) and not linhas[proximo].strip():
            proximo += 1
        if proximo >= len(linhas):
            continue

        gabarito_match = _ANSWER_ROW_RE.match(linhas[proximo])
        if not gabarito_match:
            continue

        numeros = _numeros_da_linha(item_match.group(1))
        valores = _respostas_da_linha(gabarito_match.group(1))
        for numero, resposta in zip(numeros, valores):
            if 1 <= numero <= 300 and resposta in {"C", "E", "X"}:
                respostas.setdefault(numero, resposta)

        linhas_tabulares.update({indice, proximo})

    # Fallback para gabaritos em linhas ou pares explícitos, como "1 C".
    for indice, linha in enumerate(linhas):
        if indice in linhas_tabulares:
            continue
        linha = linha.strip()
        if not linha:
            continue

        match = _LINE_RE.fullmatch(linha)
        if match:
            numero, resposta = int(match.group(1)), match.group(2).upper()
            if 1 <= numero <= 300:
                respostas.setdefault(numero, resposta)
            continue

        for match in _PAIR_RE.finditer(linha):
            numero, resposta = int(match.group(1)), match.group(2).upper()
            if 1 <= numero <= 300:
                respostas.setdefault(numero, resposta)

    return respostas
