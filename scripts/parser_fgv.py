"""Parser conservador para questões objetivas da FGV.

Este módulo é independente do segmentador genérico. Não remove números isolados
indiscriminadamente, pois eles podem representar o número de uma questão.
"""
from __future__ import annotations

import re
from typing import Any

# Números de questão isolados em linha própria. A validação de sequência é
# aplicada depois para reduzir falsos positivos de números de página/enunciado.
PADRAO_QUESTAO = re.compile(r"(?m)^[ \t]*(\d{1,3})[ \t]*\r?$")

# Alternativas em linha própria, aceitando (A), A) e A. como convenções comuns.
PADRAO_ALTERNATIVA = re.compile(
    r"(?m)^[ \t]*(?:\(([A-E])\)|([A-E])[.)])[ \t]+"
)

# Ruídos deliberadamente genéricos. Não remove cabeçalhos de concurso específicos
# sem que o chamador os informe.
PADROES_RUIDO_GENERICO = [
    re.compile(r"(?im)^\s*FGV\s+Conhecimento\s*$"),
    re.compile(r"(?im)^\s*Concurso\s+Público\s*$"),
    re.compile(r"(?im)^\s*Página\s+\d+\s*$"),
]


def limpar_texto(texto: str, ruidos_adicionais: list[str] | None = None) -> str:
    """Remove linhas de rodapé/cabeçalho conhecidas sem apagar números isolados."""
    for padrao in PADROES_RUIDO_GENERICO:
        texto = padrao.sub("", texto)
    for ruido in ruidos_adicionais or []:
        texto = re.sub(ruido, "", texto, flags=re.IGNORECASE | re.MULTILINE)
    return texto


def _marcadores_questao(texto: str, min_num: int, max_num: int):
    candidatos = []
    for m in PADRAO_QUESTAO.finditer(texto):
        numero = int(m.group(1))
        if min_num <= numero <= max_num:
            candidatos.append((m.start(), m.end(), numero))

    # Mantém apenas marcadores que participem de uma sequência crescente coerente.
    # Isso evita tratar cada número de página como uma questão independente.
    if not candidatos:
        return []
    aceitos = []
    for i, candidato in enumerate(candidatos):
        pos, fim, numero = candidato
        anterior = candidatos[i - 1][2] if i > 0 else None
        proximo = candidatos[i + 1][2] if i + 1 < len(candidatos) else None
        sequencia = (anterior is not None and numero == anterior + 1) or (
            proximo is not None and proximo == numero + 1
        )
        if sequencia or len(candidatos) == 1:
            aceitos.append(candidato)

    # Se a sequência não foi reconhecida, mantém os candidatos para não descartar
    # silenciosamente uma prova cujo primeiro número não seja 1.
    return aceitos or candidatos


def segmentar_questoes(
    texto: str,
    min_num: int = 1,
    max_num: int = 90,
    ruidos_adicionais: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Divide o texto em blocos de questão e preserva o texto bruto."""
    texto = limpar_texto(texto, ruidos_adicionais)
    matches = _marcadores_questao(texto, min_num, max_num)
    blocos = []
    for i, (pos, fim_marcador, numero) in enumerate(matches):
        fim = matches[i + 1][0] if i + 1 < len(matches) else len(texto)
        bloco = texto[fim_marcador:fim].strip()
        if bloco:
            blocos.append({"numero": numero, "texto_bruto": bloco})
    return blocos


def separar_alternativas(bloco: dict[str, Any]) -> dict[str, Any]:
    """Separa enunciado e alternativas apenas se houver estrutura A–E coerente."""
    texto = bloco["texto_bruto"].strip()
    matches = list(PADRAO_ALTERNATIVA.finditer(texto))
    letras = [(m.group(1) or m.group(2)).upper() for m in matches]

    # Aceita somente uma sequência completa A-E, sem repetição ou salto.
    if len(matches) not in (4, 5) or letras != list("ABCDE"[:len(matches)]):
        return {
            "numero": bloco["numero"],
            "tipo": "indeterminado",
            "enunciado": texto,
            "alternativas": [],
            "texto_bruto": texto,
            "revisao_necessaria": True,
        }

    enunciado = texto[:matches[0].start()].strip()
    alternativas = []
    for i, m in enumerate(matches):
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        alt_texto = texto[m.end():fim].strip()
        if not alt_texto:
            return {
                "numero": bloco["numero"],
                "tipo": "indeterminado",
                "enunciado": texto,
                "alternativas": [],
                "texto_bruto": texto,
                "revisao_necessaria": True,
            }
        alternativas.append({"letra": letras[i], "texto": alt_texto})

    return {
        "numero": bloco["numero"],
        "tipo": "multipla_escolha",
        "enunciado": enunciado,
        "alternativas": alternativas,
        "texto_bruto": texto,
        "revisao_necessaria": not bool(enunciado),
    }
