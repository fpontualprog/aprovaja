"""Testes de comparação documental entre prova e gabarito."""
from pathlib import Path

import pymupdf

from src.extraction.document_matcher import comparar_prova_gabarito, extrair_cabecalho_pdf


def criar_pdf(caminho: Path, texto: str, titulo: str | None = None) -> Path:
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_textbox((40, 40, 560, 780), texto, fontsize=10)
    if titulo:
        metadados = documento.metadata
        metadados["title"] = titulo
        documento.set_metadata(metadados)
    documento.save(caminho)
    documento.close()
    return caminho


def test_extrai_campos_do_cabecalho_pf(tmp_path: Path) -> None:
    caminho = criar_pdf(
        tmp_path / "Gab_Definitivo_094_PF_CB1_01.pdf",
        "CEBRASPE\nPOLÍCIA FEDERAL\nEDITAL Nº 1 – PF – ADMINISTRATIVO, DE 25 DE ABRIL DE 2025\n"
        "Aplicação: 29/06/2025\nCONHECIMENTOS BÁSICOS PARA OS CARGOS DE NÍVEL SUPERIOR\n094_PF_CB1_01",
    )
    campos = extrair_cabecalho_pdf(caminho)
    assert campos["banca"] == "CEBRASPE"
    assert campos["orgao"] == "Polícia Federal"
    assert campos["data_aplicacao"] == "29/06/2025"
    assert campos["codigo_caderno"] == "094_PF_CB1_01"
    assert campos["nivel"] == "superior"
    assert campos["categoria"] == "conhecimentos básicos"
    assert campos["fontes_campos"]["codigo_caderno"] == "texto_pdf"


def test_extrai_codigo_do_titulo_interno_quando_nao_aparece_no_texto(tmp_path: Path) -> None:
    caminho = criar_pdf(
        tmp_path / "PF_25_ADM_CB1_download_teste.pdf",
        "CEBRASPE\nPROVAS OBJETIVAS\nCONHECIMENTOS BÁSICOS",
        titulo="Microsoft Word - 094_PF_CB1_01.docx",
    )
    campos = extrair_cabecalho_pdf(caminho)
    assert campos["codigo_caderno"] == "094_PF_CB1_01"
    assert campos["fontes_campos"]["codigo_caderno"] == "metadados_title"
    assert campos["metadados_pdf"]["title"] == "Microsoft Word - 094_PF_CB1_01.docx"


def test_confirma_prova_e_gabarito_com_campos_essenciais_coincidentes() -> None:
    prova = {
        "arquivo": "PF_25_ADM_CB1_download_teste.pdf", "banca": "CEBRASPE",
        "orgao": "Polícia Federal", "edital": "Edital nº 1 – PF – Administrativo, de 25 de abril de 2025",
        "data_aplicacao": "29/06/2025", "codigo_caderno": "PF_CB1_01",
        "nivel": "superior", "categoria": "conhecimentos básicos",
    }
    gabarito = {
        "arquivo": "Gab_Definitivo_094_PF_CB1_01.pdf", "banca": "CEBRASPE",
        "orgao": "Polícia Federal", "edital": "Edital nº 1 – PF – Administrativo, de 25 de abril de 2025",
        "data_aplicacao": "29/06/2025", "codigo_caderno": "094_PF_CB1_01",
        "nivel": "superior", "categoria": "conhecimentos básicos",
    }
    assert comparar_prova_gabarito(prova, gabarito)["status_associacao"] == "confirmado"


def test_nao_confirma_se_faltar_codigo_de_caderno() -> None:
    prova = {"arquivo": "prova.pdf", "banca": "CEBRASPE", "orgao": "Polícia Federal", "nivel": "superior", "categoria": "conhecimentos básicos"}
    gabarito = {"arquivo": "gabarito.pdf", "banca": "CEBRASPE", "orgao": "Polícia Federal", "nivel": "superior", "categoria": "conhecimentos básicos"}
    assert comparar_prova_gabarito(prova, gabarito)["status_associacao"] == "pendente_de_confirmacao"


def test_rejeita_divergencia_de_nivel() -> None:
    prova = {"arquivo": "prova.pdf", "banca": "CEBRASPE", "orgao": "Polícia Federal", "edital": "Edital 2025", "codigo_caderno": "PF_CB1_01", "nivel": "médio", "categoria": "conhecimentos básicos"}
    gabarito = {"arquivo": "gabarito.pdf", "banca": "CEBRASPE", "orgao": "Polícia Federal", "edital": "Edital 2025", "codigo_caderno": "094_PF_CB1_01", "nivel": "superior", "categoria": "conhecimentos básicos"}
    assert comparar_prova_gabarito(prova, gabarito)["status_associacao"] == "incompativel"

def test_confirma_gabarito_oficial_sem_edital_ou_data_no_pdf() -> None:
    prova = {
        "arquivo": "PF_25_ADM_CB1_download_teste.pdf",
        "banca": "CEBRASPE", "orgao": "Polícia Federal",
        "codigo_caderno": "PF_CB1_01", "nivel": "superior",
        "categoria": "conhecimentos básicos",
    }
    gabarito = {
        "arquivo": "Gab_Definitivo_094_PF_CB1_01.pdf",
        "banca": "CEBRASPE", "orgao": "Polícia Federal",
        "codigo_caderno": "094_PF_CB1_01", "nivel": "superior",
        "categoria": "conhecimentos básicos",
        "fontes_campos": {"banca": "origem_oficial_cebraspe"},
        "origem_documento": {
            "fonte_oficial": True,
            "host": "cdn.cebraspe.org.br",
        },
    }
    resultado = comparar_prova_gabarito(prova, gabarito)
    assert resultado["status_associacao"] == "confirmado"
