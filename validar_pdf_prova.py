"""Validação conservadora: só aceitar PDFs identificados explicitamente como prova."""
from __future__ import annotations
import re
import unicodedata
import fitz

REJEITAR = re.compile(r"\b(edital|diario oficial|diário oficial|resultado|convocacao|convocação|homologacao|homologação|retificacao|retificação|comunicado|aviso|extrato|contrato|ata de registro|gabarito preliminar|gabarito definitivo|lista de inscritos)\b", re.I)
NOME_PROVA = re.compile(r"\b(prova|provas|caderno[ _-]*(de[ _-]*)?(questoes|questões|prova)|questoes[ _-]*objetivas|questões[ _-]*objetivas)\b", re.I)
CONTEUDO_PROVA = [
    re.compile(r"\bcaderno\s+(de\s+)?quest(?:ões|oes)\b", re.I),
    re.compile(r"\bprova\s+(objetiva|discursiva|tipo\s+[0-9ivx]+)\b", re.I),
    re.compile(r"\besta\s+prova\s+contém\s+\d+\s+quest(?:ões|oes)\b", re.I),
    re.compile(r"\bleia\s+atentamente\s+as\s+instruções\b", re.I),
    re.compile(r"\bquest(?:ão|ao)\s+\d{1,3}\b", re.I),
]

def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c))

def validar_pdf_prova(payload: bytes, nome_arquivo: str = "", paginas_iniciais: int = 3) -> dict:
    """Retorna aprovado apenas com evidência explícita no nome ou no início do PDF.
    Documentos administrativos são rejeitados, mesmo que mencionem prova/questões.
    """
    nome = normalizar(nome_arquivo.replace("_", " ").replace("-", " "))
    if REJEITAR.search(nome):
        return {"aprovado": False, "motivo": "nome_indica_documento_administrativo", "evidencias": []}
    nome_explicito = bool(NOME_PROVA.search(nome))
    try:
        with fitz.open(stream=payload, filetype="pdf") as doc:
            texto = "\n".join(doc[i].get_text("text") for i in range(min(len(doc), paginas_iniciais)))
            texto_norm = normalizar(texto)
            if REJEITAR.search(texto_norm[:1200]) and not nome_explicito:
                # Rejeita quando o início caracteriza o documento como edital/ato administrativo.
                return {"aprovado": False, "motivo": "inicio_indica_documento_administrativo", "evidencias": []}
            evidencias = [p.pattern for p in CONTEUDO_PROVA if p.search(texto_norm)]
            if nome_explicito:
                return {"aprovado": True, "motivo": "nome_do_arquivo_identifica_prova", "evidencias": ["nome_arquivo"]}
            # Conteúdo exige ao menos dois sinais independentes; uma ocorrência de "questão"
            # isolada em edital não é suficiente.
            if len(evidencias) >= 2 and any(
                p.search(texto_norm) for p in CONTEUDO_PROVA[:4]
            ):
                return {"aprovado": True, "motivo": "conteudo_inicial_identifica_prova", "evidencias": evidencias}
            return {"aprovado": False, "motivo": "sem_evidencia_suficiente_de_prova", "evidencias": evidencias}
    except Exception as exc:
        return {"aprovado": False, "motivo": f"pdf_invalido_ou_ilegivel: {exc}", "evidencias": []}
