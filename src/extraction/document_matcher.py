"""Comparação documental entre cadernos de prova e gabaritos CEBRASPE."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pymupdf


def extrair_cabecalho_pdf(caminho_pdf: str | Path, max_paginas: int = 3) -> dict[str, Any]:
    """Extrai campos do texto, dos metadados e do nome do arquivo, preservando a origem."""
    caminho = Path(caminho_pdf)
    with pymupdf.open(str(caminho)) as documento:
        texto = "\n".join(
            pagina.get_text("text", sort=True)
            for pagina in list(documento)[:max_paginas]
        )
        metadados = documento.metadata or {}

    normalizado = re.sub(r"\s+", " ", texto).strip()
    titulo_metadata = str(metadados.get("title") or "")
    contexto_codigo = "\n".join((texto, titulo_metadata, caminho.name))
    normalizado_codigo = re.sub(r"\s+", " ", contexto_codigo).strip()
    fontes_campos: dict[str, str] = {}

    def primeiro(padroes: list[str], conteudo: str = normalizado) -> str | None:
        for padrao in padroes:
            achado = re.search(padrao, conteudo, re.IGNORECASE)
            if achado:
                return re.sub(r"\s+", " ", achado.group(1)).strip(" .;:-")
        return None

    edital = primeiro([
        r"(EDITAL\s*N[º°o]?\s*\d+\s*[–-]\s*PF\s*[–-]\s*ADMINISTRATIVO\s*,?\s*DE\s*\d{1,2}\s+DE\s+[A-ZÇÃÕÉÍÓÚ]+\s+DE\s+\d{4})",
        r"(EDITAL\s*(?:N[º°o]?\s*)?\d+[^.]{0,100}?\bDE\s+\d{4})",
    ])
    if edital:
        fontes_campos["edital"] = "texto_pdf"

    data_aplicacao = primeiro([r"Aplicação\s*:\s*(\d{2}/\d{2}/\d{4})"])
    if data_aplicacao:
        fontes_campos["data_aplicacao"] = "texto_pdf"

    padroes_codigo = [r"\b(\d{3}_PF_CB\d_\d{2})\b", r"\b(PF[_ -]?CB\d[_ -]?\d{2})\b"]
    codigo_caderno = primeiro(padroes_codigo)
    if codigo_caderno:
        fontes_campos["codigo_caderno"] = "texto_pdf"
    else:
        codigo_caderno = primeiro(padroes_codigo, titulo_metadata)
        if codigo_caderno:
            fontes_campos["codigo_caderno"] = "metadados_title"
        else:
            codigo_caderno = primeiro(padroes_codigo, caminho.name)
            if codigo_caderno:
                fontes_campos["codigo_caderno"] = "nome_arquivo"

    nivel = None
    if re.search(r"cargos de nível superior", normalizado, re.IGNORECASE):
        nivel = "superior"
    elif re.search(r"cargos de nível médio", normalizado, re.IGNORECASE):
        nivel = "médio"
    if nivel:
        fontes_campos["nivel"] = "texto_pdf"

    categoria = None
    if re.search(r"conhecimentos básicos", normalizado, re.IGNORECASE):
        categoria = "conhecimentos básicos"
    elif re.search(r"conhecimentos específicos", normalizado, re.IGNORECASE):
        categoria = "conhecimentos específicos"
    if categoria:
        fontes_campos["categoria"] = "texto_pdf"

    banca = "CEBRASPE" if re.search(r"CEBRASPE", normalizado, re.IGNORECASE) else None
    if banca:
        fontes_campos["banca"] = "texto_pdf"

    orgao = "Polícia Federal" if re.search(r"Polícia Federal|\bPF\b", normalizado, re.IGNORECASE) else None
    if orgao:
        fontes_campos["orgao"] = "texto_pdf"

    return {
        "arquivo": caminho.name,
        "texto_cabecalho": texto[:12000],
        "metadados_pdf": {
            "title": titulo_metadata or None,
            "author": metadados.get("author") or None,
            "creationDate": metadados.get("creationDate") or None,
        },
        "banca": banca,
        "orgao": orgao,
        "edital": edital,
        "data_aplicacao": data_aplicacao,
        "codigo_caderno": codigo_caderno,
        "nivel": nivel,
        "categoria": categoria,
        "fontes_campos": fontes_campos,
        "tem_texto_extraivel": bool(normalizado),
    }


def comparar_prova_gabarito(prova: dict[str, Any], gabarito: dict[str, Any]) -> dict[str, Any]:
    """Classifica a compatibilidade; não confirma usando apenas nomes de arquivos."""
    campos = ("banca", "orgao", "edital", "data_aplicacao", "codigo_caderno", "nivel", "categoria")
    coincidencias: list[str] = []
    divergencias: list[str] = []
    ausentes: list[str] = []
    for campo in campos:
        valor_prova, valor_gabarito = prova.get(campo), gabarito.get(campo)
        if valor_prova and valor_gabarito:
            if campo == "codigo_caderno":
                # O código numérico inicial pode identificar o evento; o sufixo identifica o caderno.
                normaliza = lambda valor: re.sub(r"[^A-Z0-9]", "", str(valor).upper())
                a, b = normaliza(valor_prova), normaliza(valor_gabarito)
                compativeis = a == b or (a.endswith("PFCB101") and b.endswith("PFCB101"))
            else:
                compativeis = re.sub(r"\s+", " ", str(valor_prova).casefold()) == re.sub(r"\s+", " ", str(valor_gabarito).casefold())
            (coincidencias if compativeis else divergencias).append(campo)
        else:
            ausentes.append(campo)

    campos_essenciais = {"banca", "orgao", "edital", "codigo_caderno", "nivel", "categoria"}
    conflitos_essenciais = campos_essenciais.intersection(divergencias)
    fontes_gabarito = gabarito.get("fontes_campos") or {}
    origem_documento = gabarito.get("origem_documento") or {}
    origem_oficial_cebraspe = (
        origem_documento.get("fonte_oficial") is True
        and origem_documento.get("host") == "cdn.cebraspe.org.br"
        and fontes_gabarito.get("banca") == "origem_oficial_cebraspe"
    )
    confirmacao_temporal = "edital" in coincidencias or "data_aplicacao" in coincidencias
    confirmada = (
        not conflitos_essenciais
        and {"banca", "orgao", "nivel", "categoria"}.issubset(coincidencias)
        and "codigo_caderno" in coincidencias
        and (confirmacao_temporal or origem_oficial_cebraspe)
    )
    status = "confirmado" if confirmada else "incompativel" if conflitos_essenciais else "pendente_de_confirmacao"
    return {
        "arquivo_prova": prova.get("arquivo"),
        "arquivo_gabarito": gabarito.get("arquivo"),
        "status_associacao": status,
        "coincidencias": coincidencias,
        "divergencias": divergencias,
        "campos_ausentes": ausentes,
        "justificativa": (
            "Campos essenciais coincidem." if confirmada else
            "Há divergência em campo essencial." if conflitos_essenciais else
            "Dados insuficientes para confirmar a associação automaticamente."
        ),
    }
