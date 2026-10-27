"""Orquestra descoberta, download, extração, estruturação e exportação."""
from __future__ import annotations
import json
import re
from pathlib import Path
from src.discovery.cebraspe import descobrir_prova, baixar_pdf, listar_pdfs_gabarito
from src.extraction.pdf_parser import extrair_itens_pdf, extrair_imagens_questoes
from src.extraction.gabarito_parser import extrair_gabarito_pdf
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
        itens = extrair_itens_pdf(caminho)
        pasta_imagens_pdf = destino / "imagens" / _nome_seguro(Path(nome).stem)
        extrair_imagens_questoes(caminho, itens, pasta_imagens_pdf)
        for item in itens:
            item["arquivo_origem"] = nome
            item["url_origem"] = url_download
        itens_brutos.extend(itens)

    if not itens_brutos:
        raise RuntimeError(f"Nenhum item foi extraído dos PDFs do evento {evento}.")
    questoes = estruturar_itens(itens_brutos, evento)

    # Baixa e extrai gabaritos; a associação exige nome-base idêntico após normalização.
    # Se houver gabarito definitivo e preliminar do mesmo caderno, prioriza o definitivo.
    gabaritos = listar_pdfs_gabarito(evento)
    gabaritos_baixados: list[tuple[str, dict[int, str]]] = []
    pasta_gabaritos = trabalho / "gabaritos"
    pasta_gabaritos.mkdir(parents=True, exist_ok=True)

    def chave_caderno(nome_arquivo: str) -> str:
        base = Path(nome_arquivo).stem.lower()
        base = re.sub(r"^(?:gab(?:arito)?)(?:[_ .-]*(?:definitivo|preliminar))?[_ .-]*", "", base)
        return re.sub(r"[^a-z0-9]", "", base)

    for indice, gabarito in enumerate(gabaritos, start=1):
        url = gabarito.get("url_download") or gabarito.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        nome_gabarito = _nome_seguro(gabarito.get("nome") or f"gabarito_{indice}.pdf")
        if not nome_gabarito.lower().endswith(".pdf"):
            nome_gabarito += ".pdf"
        caminho_gabarito = pasta_gabaritos / f"{indice:02d}_{nome_gabarito}"
        try:
            baixar_pdf(url, str(caminho_gabarito))
            respostas = extrair_gabarito_pdf(caminho_gabarito)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"[gabarito] Não foi possível processar {nome_gabarito}: {exc}")
            continue
        if respostas:
            gabaritos_baixados.append((nome_gabarito, respostas))

    # Escolhe no máximo um gabarito por caderno. Não mistura respostas de PDFs
    # diferentes e não usa fallback global quando não existe correspondência.
    respostas_por_prova: dict[str, dict[int, str]] = {}
    nomes_provas = list(dict.fromkeys(
        str(q.get("arquivo_origem", "")) for q in itens_brutos if q.get("arquivo_origem")
    ))
    for nome_prova in nomes_provas:
        chave_prova = chave_caderno(nome_prova)
        correspondentes = [
            (nome, respostas) for nome, respostas in gabaritos_baixados
            if chave_prova and chave_caderno(nome) == chave_prova
        ]
        if correspondentes:
            correspondentes.sort(
                key=lambda item: (
                    "definitivo" not in item[0].lower(),
                    "preliminar" in item[0].lower(),
                )
            )
            nome_escolhido, respostas_escolhidas = correspondentes[0]
            respostas_por_prova[nome_prova] = respostas_escolhidas
            print(f"[gabarito] {nome_prova} associado a {nome_escolhido}")
        else:
            print(f"[gabarito] Sem correspondência exata para {nome_prova}; respostas não serão preenchidas automaticamente.")

    for questao in questoes:
        nome_origem = str(questao.get("arquivo_origem") or "")
        respostas = respostas_por_prova.get(nome_origem, {})
        numero = questao.get("numero")
        if numero is not None:
            try:
                resposta = respostas.get(int(numero))
            except (TypeError, ValueError):
                resposta = None
            if resposta is not None and not questao.get("gabarito"):
                questao["gabarito"] = resposta

    for questao in questoes:
        questao.setdefault("concurso", evento)
        questao.setdefault("banca", "CEBRASPE")
    exportar_questoes(questoes, destino, evento)
    return questoes
