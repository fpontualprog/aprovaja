"""Orquestra descoberta, download, extração, estruturação e exportação."""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.discovery.cebraspe import (
    descobrir_prova,
    baixar_pdf,
    listar_pdfs_gabarito,
)
from src.extraction.pdf_parser import extrair_itens_pdf, extrair_imagens_questoes
from src.extraction.gabarito_parser import extrair_gabarito_pdf
from src.extraction.document_matcher import (
    extrair_cabecalho_pdf,
    comparar_prova_gabarito,
)
from src.structuring.deepseek import estruturar_itens
from src.export.writers import exportar_questoes


def _nome_seguro(valor: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", valor).strip("._") or "prova"


def processar_concurso(evento: str, saida: str = "data") -> list[dict]:
    """Processa provas e associa gabaritos apenas com evidência documental suficiente."""
    destino = Path(saida)
    destino.mkdir(parents=True, exist_ok=True)
    trabalho = destino / "pdfs" / _nome_seguro(evento)
    trabalho.mkdir(parents=True, exist_ok=True)

    descoberta = descobrir_prova(evento)
    (destino / f"{_nome_seguro(evento)}_descoberta.json").write_text(
        json.dumps(descoberta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    itens_brutos: list[dict] = []
    cabecalhos_provas: dict[str, dict] = {}
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
        try:
            cabecalhos_provas[nome] = extrair_cabecalho_pdf(caminho)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"[cabecalho] Não foi possível ler {nome}: {exc}")
        itens = extrair_itens_pdf(caminho)
        pasta_imagens_pdf = destino / "imagens" / _nome_seguro(Path(nome).stem)
        extrair_imagens_questoes(caminho, itens, pasta_imagens_pdf)
        for item in itens:
            item["arquivo_origem"] = nome
            item["url_origem"] = url_download
        itens_brutos.extend(itens)

    # Baixa e lê os gabaritos separadamente. Falhas individuais são registradas,
    # sem transformar um documento não lido em candidato de associação.
    gabaritos_baixados: list[tuple[str, dict[int, str], dict]] = []
    registros_associacao: list[dict] = []
    pasta_gabaritos = trabalho / "gabaritos"
    pasta_gabaritos.mkdir(parents=True, exist_ok=True)
    try:
        candidatos_gabarito = listar_pdfs_gabarito(evento)
    except Exception as exc:
        candidatos_gabarito = []
        registros_associacao.append({
            "arquivo_prova": None,
            "arquivo_gabarito": None,
            "status_associacao": "pendente_de_confirmacao",
            "coincidencias": [],
            "divergencias": [],
            "campos_ausentes": ["lista_gabaritos"],
            "justificativa": f"Não foi possível consultar os gabaritos do evento: {exc}",
        })

    urls_gabaritos_vistos: set[str] = set()
    for indice, candidato in enumerate(candidatos_gabarito, start=1):
        url = candidato.get("url_download") or candidato.get("url")
        nome = _nome_seguro(candidato.get("nome") or f"gabarito_{indice}.pdf")
        if not nome.lower().endswith(".pdf"):
            nome += ".pdf"
        if not isinstance(url, str) or not url.startswith("https://"):
            registros_associacao.append({
                "arquivo_prova": None,
                "arquivo_gabarito": nome,
                "status_associacao": "pendente_de_confirmacao",
                "coincidencias": [],
                "divergencias": [],
                "campos_ausentes": ["url_gabarito"],
                "justificativa": "O registro de gabarito não possui URL HTTPS válida.",
            })
            continue
        if url in urls_gabaritos_vistos:
            continue
        urls_gabaritos_vistos.add(url)

        caminho_gabarito = pasta_gabaritos / f"{indice:03d}_{nome}"
        try:
            baixar_pdf(url, str(caminho_gabarito))
            respostas = extrair_gabarito_pdf(caminho_gabarito)
            cabecalho_gabarito = extrair_cabecalho_pdf(caminho_gabarito)

            # A banca pode não aparecer no texto do gabarito. Nesse caso, só
            # registramos CEBRASPE como evidência de origem quando o PDF veio
            # do CDN oficial listado pelo endpoint oficial de documentos.
            from urllib.parse import urlparse
            host_origem = (urlparse(url).hostname or "").lower()
            if host_origem == "cdn.cebraspe.org.br":
                fontes = cabecalho_gabarito.setdefault("fontes_campos", {})
                if not cabecalho_gabarito.get("banca"):
                    cabecalho_gabarito["banca"] = "CEBRASPE"
                    fontes["banca"] = "origem_oficial_cebraspe"
                cabecalho_gabarito["origem_documento"] = {
                    "url": url,
                    "host": host_origem,
                    "descoberto_por": "listar_pdfs_gabarito",
                    "fonte_oficial": True,
                }
        except (OSError, ValueError, RuntimeError) as exc:
            registros_associacao.append({
                "arquivo_prova": None,
                "arquivo_gabarito": nome,
                "status_associacao": "pendente_de_confirmacao",
                "coincidencias": [],
                "divergencias": [],
                "campos_ausentes": ["conteudo_gabarito"],
                "justificativa": f"Não foi possível baixar ou interpretar o PDF do gabarito: {exc}",
            })
            continue

        if not respostas:
            registros_associacao.append({
                "arquivo_prova": None,
                "arquivo_gabarito": nome,
                "status_associacao": "pendente_de_confirmacao",
                "coincidencias": [],
                "divergencias": [],
                "campos_ausentes": ["respostas_extraidas"],
                "justificativa": "O PDF foi lido, mas nenhuma resposta foi extraída.",
            })
            continue

        gabaritos_baixados.append((nome, respostas, cabecalho_gabarito))

    if not itens_brutos:
        (trabalho / "associacoes_gabaritos.json").write_text(
            json.dumps(registros_associacao, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        raise RuntimeError(f"Nenhum item foi extraído dos PDFs do evento {evento}.")

    questoes = estruturar_itens(itens_brutos, evento)

    # Associa gabaritos por evidências extraídas dos cabeçalhos dos próprios PDFs.
    # O nome do arquivo, isoladamente, nunca confirma a correspondência.
    respostas_por_prova: dict[str, dict[int, str]] = {}
    nomes_provas = list(dict.fromkeys(
        str(q.get("arquivo_origem", "")) for q in itens_brutos if q.get("arquivo_origem")
    ))
    for nome_prova in nomes_provas:
        cabecalho_prova = cabecalhos_provas.get(nome_prova)
        if not cabecalho_prova:
            registros_associacao.append({
                "arquivo_prova": nome_prova,
                "status_associacao": "pendente_de_confirmacao",
                "coincidencias": [],
                "divergencias": [],
                "campos_ausentes": ["cabecalho_prova"],
                "justificativa": "Não foi possível extrair o cabeçalho da prova.",
            })
            continue

        candidatos = []
        for nome_gabarito, respostas, cabecalho_gabarito in gabaritos_baixados:
            registro = comparar_prova_gabarito(cabecalho_prova, cabecalho_gabarito)
            registros_associacao.append(registro)
            if registro["status_associacao"] == "confirmado":
                candidatos.append((nome_gabarito, respostas, registro))

        if len(candidatos) == 1:
            nome_escolhido, respostas_escolhidas, registro = candidatos[0]
            respostas_por_prova[nome_prova] = respostas_escolhidas
            registro["selecionado"] = True
            print(f"[gabarito] Associação documental confirmada: {nome_prova} -> {nome_escolhido}")
        elif len(candidatos) > 1:
            registros_associacao.append({
                "arquivo_prova": nome_prova,
                "status_associacao": "pendente_de_confirmacao",
                "coincidencias": [],
                "divergencias": [],
                "campos_ausentes": [],
                "justificativa": "Mais de um gabarito foi documentalmente confirmado; revisão necessária.",
            })
            print(f"[gabarito] Associação ambígua para {nome_prova}; respostas não preenchidas.")
        else:
            print(f"[gabarito] Nenhuma correspondência documental confirmada para {nome_prova}; respostas não preenchidas.")

    (trabalho / "associacoes_gabaritos.json").write_text(
        json.dumps(registros_associacao, ensure_ascii=False, indent=2), encoding="utf-8"
    )

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
