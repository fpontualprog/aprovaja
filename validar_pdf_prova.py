"""Validação conservadora: aceitar apenas provas objetivas de múltipla escolha."""
from __future__ import annotations
import re
import unicodedata
import fitz

REJEITAR = re.compile(r"\b(edital|diario oficial|resultado|convocacao|homologacao|retificacao|comunicado|aviso|extrato|contrato|ata de registro|gabarito preliminar|gabarito definitivo|lista de inscritos)\b", re.I)
INDICIOS_DISCURSIVA = re.compile(
    r"\b(prova\s+discursiva|quest(?:ão|ao)\s+discursiva|quest(?:ões|oes)\s+discursivas|"
    r"redação|estudo\s+de\s+caso|peça\s+(?:prática|tecnica|técnica)|"
    r"resposta\s+definitiva|texto\s+dissertativo|folha\s+de\s+texto definitivo)\b", re.I
)
NOME_PROVA = re.compile(r"\b(prova|provas|caderno[ _-]*(de[ _-]*)?(questoes|prova)|questoes[ _-]*objetivas)\b", re.I)
INDICIOS_OBJETIVA = [
    re.compile(r"\bprova\s+objetiva\b", re.I),
    re.compile(r"\bquest(?:ões|oes)\s+objetivas\b", re.I),
    re.compile(r"\bquest(?:ão|ao)\s+de\s+m[uú]ltipla\s+escolha\b", re.I),
    re.compile(r"\balternativas\s+[a-e]\b", re.I),
    re.compile(r"\b(A\s*[).:-].{0,100}B\s*[).:-].{0,100}C\s*[).:-])", re.I),
]

def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c))

def validar_pdf_prova(payload: bytes, nome_arquivo: str = "", paginas_iniciais: int = 5) -> dict:
    """Aprova somente se houver evidência positiva de prova objetiva e nenhuma evidência discursiva."""
    nome = normalizar(nome_arquivo.replace("_", " ").replace("-", " "))
    if REJEITAR.search(nome):
        return {"aprovado": False, "motivo": "nome_indica_documento_administrativo", "evidencias": []}
    if INDICIOS_DISCURSIVA.search(nome):
        return {"aprovado": False, "motivo": "nome_indica_prova_discursiva", "evidencias": []}
    nome_explicito = bool(NOME_PROVA.search(nome))
    try:
        with fitz.open(stream=payload, filetype="pdf") as doc:
            texto = "\n".join(doc[i].get_text("text") for i in range(min(len(doc), paginas_iniciais)))
            texto_norm = normalizar(texto)
            inicio = texto_norm[:2500]
            if INDICIOS_DISCURSIVA.search(inicio):
                return {"aprovado": False, "motivo": "conteudo_indica_prova_discursiva", "evidencias": []}
            if REJEITAR.search(inicio) and not nome_explicito:
                return {"aprovado": False, "motivo": "inicio_indica_documento_administrativo", "evidencias": []}
            evidencias = [p.pattern for p in INDICIOS_OBJETIVA if p.search(texto_norm)]
            # Nome "prova" sozinho nunca é suficiente: exige sinais objetivos no conteúdo.
            if len(evidencias) >= 2 and any(INDICIOS_OBJETIVA[i].search(texto_norm) for i in range(3)):
                return {"aprovado": True, "motivo": "conteudo_identifica_prova_objetiva", "evidencias": evidencias}
            return {"aprovado": False, "motivo": "sem_evidencia_suficiente_de_prova_objetiva", "evidencias": evidencias}
    except Exception as exc:
        return {"aprovado": False, "motivo": f"pdf_invalido_ou_ilegivel: {exc}", "evidencias": []}
