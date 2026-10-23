"""Extração e segmentação inicial de itens em PDFs de provas."""
from __future__ import annotations
import re
from pathlib import Path
import fitz

ITEM_RE = re.compile(r"(?m)^\s*(\d{1,3})[.)]?\s+")

def extrair_texto_pdf(caminho: str | Path) -> str:
    texto = []
    with fitz.open(str(caminho)) as doc:
        for pagina in doc:
            texto.append(pagina.get_text("text", sort=True))
    resultado = "\n".join(texto).strip()
    if not resultado:
        raise ValueError(f"Nenhum texto extraível encontrado em {caminho}; o PDF pode ser digitalizado como imagem.")
    return resultado

def segmentar_itens(texto: str) -> list[dict[str, str | int]]:
    """Segmentação heurística para provas C/E; revisar casos com numeração ambígua."""
    matches = list(ITEM_RE.finditer(texto))
    itens = []
    for i, match in enumerate(matches):
        inicio = match.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        conteudo = texto[inicio:fim].strip()
        numero = int(match.group(1))
        if len(conteudo) >= 20:
            itens.append({"numero": numero, "texto": conteudo})
    if not itens:
        raise ValueError("Não foi possível identificar itens numerados no texto extraído do PDF.")
    return itens
