"""Triagem conservadora de PDFs: prioriza provas objetivas e rejeita provas discursivas."""
from __future__ import annotations
import json
import os
import re
import unicodedata
import requests
import fitz

REJEITAR = re.compile(r"\\b(edital|diario oficial|resultado|convocacao|homologacao|retificacao|comunicado|aviso|extrato|contrato|ata de registro|gabarito preliminar|gabarito definitivo|lista de inscritos)\\b", re.I)
INDICIOS_DISCURSIVA = re.compile(
    r"\\b(discursiva|discursivas|redacao|estudo\\s+de\\s+caso|peca\\s+pratica|peca\\s+tecnica|"
    r"resposta\\s+definitiva|texto\\s+dissertativo|folha\\s+de\\s+texto\\s+definitivo)\\b", re.I
)
INDICIOS_OBJETIVA = [
    re.compile(r"\\bprova\\s+objetiva\\b", re.I),
    re.compile(r"\\bquestoes\\s+objetivas\\b", re.I),
    re.compile(r"\\bquestao\\s+de\\s+multipla\\s+escolha\\b", re.I),
    re.compile(r"\\balternativas\\s+[a-e]\\b", re.I),
    re.compile(r"\\b(A\\s*[).:-].{0,100}B\\s*[).:-].{0,100}C\\s*[).:-])", re.I),
    re.compile(r"\\bcerto\\s+ou\\s+errado\\b", re.I),
    re.compile(r"\\b(itens|afirmativas)\\s+de\\s+(certo|errado)\\b", re.I),
]

def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c))

def triagem_deepseek(nome: str, texto: str) -> dict | None:
    """Classifica documento antes de extrair questões. Falhas retornam None para fallback conservador."""
    key = os.getenv("DEEPSEEK_API_PUBLICA", "").strip()
    if not key or not texto.strip():
        return None
    prompt = (
        "Classifique o documento de concurso usando SOMENTE as evidências fornecidas. "
        "Categorias permitidas: prova_objetiva, prova_discursiva, gabarito, edital, resultado, "
        "documento_administrativo, outro, inconclusivo. "
        "O sistema aceita exclusivamente prova_objetiva para extração de questões. "
        "Prova discursiva, redação, estudo de caso e peça técnica devem ser rejeitados, "
        "mesmo que estejam no mesmo PDF. Gabaritos devem ser catalogados separadamente e não "
        "tratados como prova. Não confunda um edital que menciona prova objetiva com uma prova. "
        "Responda JSON com categoria, confianca (0 a 1), evidencias (lista curta) e justificativa. "
        "Se houver mistura ou dúvida, use inconclusivo.\\n"
        f"Nome do arquivo: {nome}\\nTexto inicial do PDF:\\n{texto[:14000]}"
    )
    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("APROVAJA_IA_MODEL", "deepseek-flash"),
                "messages": [
                    {"role": "system", "content": "Você é um classificador documental rigoroso. Não invente evidências."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
                "temperature": 0
            },
            timeout=35
        )
        response.raise_for_status()
        data = response.json()["choices"][0]["message"]["content"]
        result = json.loads(data)
        if result.get("categoria") not in {
            "prova_objetiva", "prova_discursiva", "gabarito", "edital",
            "resultado", "documento_administrativo", "outro", "inconclusivo"
        }:
            return None
        return result
    except Exception as exc:
        return {"categoria": "inconclusivo", "confianca": 0, "evidencias": [],
                "justificativa": f"Falha na triagem DeepSeek: {type(exc).__name__}"}

def validar_pdf_prova(payload: bytes, nome_arquivo: str = "", paginas_iniciais: int = 5) -> dict:
    """Só aprova provas objetivas; rejeita discursivas, documentos administrativos e inconclusivos."""
    nome = normalizar(nome_arquivo.replace("_", " ").replace("-", " "))
    if REJEITAR.search(nome):
        return {"aprovado": False, "motivo": "nome_indica_documento_administrativo", "evidencias": []}
    try:
        with fitz.open(stream=payload, filetype="pdf") as doc:
            if not len(doc):
                return {"aprovado": False, "motivo": "pdf_sem_paginas", "evidencias": []}
            texto = "\\n".join(doc[i].get_text("text") for i in range(min(len(doc), paginas_iniciais)))
            texto_norm = normalizar(texto)
            # Regra absoluta: qualquer sinal explícito de prova discursiva no nome ou no início
            # do documento rejeita o PDF, independentemente da classificação da IA.
            if INDICIOS_DISCURSIVA.search(nome) or INDICIOS_DISCURSIVA.search(texto_norm[:12000]):
                return {"aprovado": False, "motivo": "indicio_de_prova_discursiva", "evidencias": ["nome_ou_texto_inicial"]}
            if REJEITAR.search(texto_norm[:2500]):
                return {"aprovado": False, "motivo": "inicio_indica_documento_administrativo", "evidencias": []}

            ai = triagem_deepseek(nome_arquivo, texto_norm)
            if ai is not None:
                category = ai.get("categoria")
                confidence = float(ai.get("confianca", 0) or 0)
                evidence = {
                    "categoria_ia": category,
                    "confianca_ia": confidence,
                    "evidencias_ia": ai.get("evidencias", []),
                    "justificativa_ia": ai.get("justificativa", "")
                }
                if category == "prova_discursiva":
                    return {"aprovado": False, "motivo": "ia_identificou_prova_discursiva", **evidence}
                if category != "prova_objetiva" or confidence < 0.75:
                    return {"aprovado": False, "motivo": "ia_nao_confirmou_prova_objetiva_com_confianca", **evidence}
                evidencias = [p.pattern for p in INDICIOS_OBJETIVA if p.search(texto_norm)]
                return {"aprovado": True, "motivo": "deepseek_confirmou_prova_objetiva", "evidencias": evidencias, **evidence}

            # Fallback sem API: regras conservadoras; documentos inconclusivos não são processados.
            evidencias = [p.pattern for p in INDICIOS_OBJETIVA if p.search(texto_norm)]
            if len(evidencias) >= 2:
                return {"aprovado": True, "motivo": "regras_confirmaram_prova_objetiva_sem_ia", "evidencias": evidencias,
                        "categoria_ia": None, "confianca_ia": None}
            return {"aprovado": False, "motivo": "sem_evidencia_suficiente_de_prova_objetiva_ou_certo_errado",
                    "evidencias": evidencias, "categoria_ia": None, "confianca_ia": None}
    except Exception as exc:
        return {"aprovado": False, "motivo": f"pdf_invalido_ou_ilegivel: {exc}", "evidencias": []}
