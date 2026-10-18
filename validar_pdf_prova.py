"""Validação conservadora: aceitar provas objetivas de múltipla escolha ou certo/errado."""
from __future__ import annotations
import re
import unicodedata
import fitz

REJEITAR = re.compile(r"\b(edital|diario oficial|resultado|convocacao|homologacao|retificacao|comunicado|aviso|extrato|contrato|ata de registro|gabarito preliminar|gabarito definitivo|lista de inscritos)\b", re.I)
INDICIOS_DISCURSIVA = re.compile(
    r"\b(discursiva|discursivas|redacao|estudo\s+de\s+caso|peca\s+pratica|peca\s+tecnica|"
    r"resposta\s+definitiva|texto\s+dissertativo|folha\s+de\s+texto definitivo)\b", re.I
)
NOME_PROVA = re.compile(r"\b(prova|provas|caderno[ _-]*(de[ _-]*)?(questoes|prova)|questoes[ _-]*objetivas)\b", re.I)
INDICIOS_OBJETIVA = [
    re.compile(r"\bprova\s+objetiva\b", re.I),
    re.compile(r"\bquestoes\s+objetivas\b", re.I),
    re.compile(r"\bquestao\s+de\s+multipla\s+escolha\b", re.I),
    re.compile(r"\balternativas\s+[a-e]\b", re.I),
    re.compile(r"\b(A\s*[).:-].{0,100}B\s*[).:-].{0,100}C\s*[).:-])", re.I),
    re.compile(r"\bcerto\s+ou\s+errado\b", re.I),
    re.compile(r"\b(itens|afirmativas)\s+de\s+(certo|errado)\b", re.I),
]

def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c))

def validar_pdf_prova(payload: bytes, nome_arquivo: str = "", paginas_iniciais: int = 5) -> dict:
    """Descarta se a primeira página contém 'discursiva'; exige evidência de prova objetiva."""
    nome = normalizar(nome_arquivo.replace("_", " ").replace("-", " "))
    if REJEITAR.search(nome):
        return {"aprovado": False, "motivo": "nome_indica_documento_administrativo", "evidencias": []}
    if re.search(r"\bdiscursiva\b", nome, re.I):
        return {"aprovado": False, "motivo": "nome_indica_prova_discursiva", "evidencias": []}
    try:
        with fitz.open(stream=payload, filetype="pdf") as doc:
            if not len(doc):
                return {"aprovado": False, "motivo": "pdf_sem_paginas", "evidencias": []}
            primeira = normalizar(doc[0].get_text("text"))
            # Regra solicitada: a palavra "Discursiva" na primeira página elimina o PDF.
            if re.search(r"\bdiscursiva\b", primeira, re.I):
                return {"aprovado": False, "motivo": "primeira_pagina_contem_discursiva", "evidencias": ["primeira_pagina"]}
            texto = "\n".join(doc[i].get_text("text") for i in range(min(len(doc), paginas_iniciais)))
            texto_norm = normalizar(texto)
            if REJEITAR.search(texto_norm[:2500]):
                return {"aprovado": False, "motivo": "inicio_indica_documento_administrativo", "evidencias": []}
            evidencias = [p.pattern for p in INDICIOS_OBJETIVA if p.search(texto_norm)]
            # Exige duas evidências, incluindo prova objetiva, múltipla escolha ou certo/errado.
            if len(evidencias) >= 2 and any(p.search(texto_norm) for p in INDICIOS_OBJETIVA):
                return {"aprovado": True, "motivo": "conteudo_identifica_prova_objetiva_ou_certo_errado", "evidencias": evidencias}
            return {"aprovado": False, "motivo": "sem_evidencia_suficiente_de_prova_objetiva_ou_certo_errado", "evidencias": evidencias}
    except Exception as exc:
        return {"aprovado": False, "motivo": f"pdf_invalido_ou_ilegivel: {exc}", "evidencias": []}
