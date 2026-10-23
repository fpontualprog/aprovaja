"""Orquestra descoberta, download, extração, estruturação e exportação."""
from __future__ import annotations
import json
import re
from pathlib import Path
from src.discovery.cebraspe import descobrir_prova, baixar_pdf
from src.extraction.pdf_parser import extrair_texto_pdf, segmentar_itens
from src.structuring.deepseek import estruturar_itens
from src.export.writers import exportar_questoes

def _nome_seguro(valor: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", valor).strip("._") or "prova"

def processar_concurso(evento: str, saida: str = "data") -> list[dict]:
    """Processa PDFs localizados na API do Cebraspe e exporta as questões estruturadas."""
    destino = Path(saida)
    destino.mkdir(parents=True, exist_ok=True)
    trabalho = destino / "pdfs" / _nome_seguro(evento)
    trabalho.mkdir(parents=True, exist_ok=True)

    descoberta = descobrir_prova(evento)
    (destino / f"{_nome_seguro(evento)}_descoberta.json").write_text(
        json.dumps(descoberta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    itens_brutos = []
    for indice, prova in enumerate(descoberta["provas"], start=1):
        nome = _nome_seguro(prova.get("nome") or f"prova_{indice}.pdf")
        if not nome.lower().endswith(".pdf"):
            nome += ".pdf"
        url_download = prova.get("url_download") or prova.get("url")
        if not isinstance(url_download, str) or not url_download.startswith("https://"):
            raise ValueError(f"URL de download ausente ou inválida para o arquivo {nome!r}: {url_download!r}")
        if nome.lower() in {"_", "_.pdf", "prova.pdf"} and url_download.rstrip("/").endswith("/_.pdf"):
            raise ValueError(f"A API do Cebraspe retornou um nome de arquivo inválido: {url_download}")

        caminho = trabalho / f"{indice:02d}_{nome}"
        baixar_pdf(url_download, str(caminho))
        texto = extrair_texto_pdf(caminho)
        itens = segmentar_itens(texto)
        for item in itens:
            item["arquivo_origem"] = nome
            item["url_origem"] = url_download
        itens_brutos.extend(itens)

    if not itens_brutos:
        raise RuntimeError(f"Nenhum item foi extraído dos PDFs do evento {evento}.")
    questoes = estruturar_itens(itens_brutos, evento)
    for questao in questoes:
        questao.setdefault("concurso", evento)
        questao.setdefault("banca", "CEBRASPE")
    exportar_questoes(questoes, destino, evento)
    return questoes
