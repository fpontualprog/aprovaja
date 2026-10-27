"""Orquestra descoberta, download, extração, estruturação e exportação."""
from __future__ import annotations
import json
import re
from pathlib import Path
from src.discovery.cebraspe import descobrir_prova, baixar_pdf, listar_pdfs_gabarito
from src.extraction.pdf_parser import extrair_itens_pdf, extrair_imagens_questoes
from src.extraction.gabarito_parser import extrair_gabarito_pdf
from src.extraction.document_matcher import extrair_cabecalho_pdf, comparar_prova_gabarito
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

    if not itens_brutos:
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
                "justificativa": "Não foi possível extrair o cabeçalho da prova."
            })
            continue

        candidatos = []
        for nome_gabarito, respostas, cabecalho_gabarito in gabaritos_baixados:
            registro = comparar_prova_gabarito(cabecalho_prova, cabecalho_gabarito)
            registros_associacao.append(registro)
            if registro["status_associacao"] == "confirmado":
                candidatos.append((nome_gabarito, respostas, registro))

        # Só usa uma associação documental confirmada e não ambígua.
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
                "justificativa": "Mais de um gabarito foi documentalmente confirmado; revisão necessária."
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
