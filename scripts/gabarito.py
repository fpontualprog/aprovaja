"""Parser inicial de gabaritos textuais; formatos ambíguos exigem conferência."""
from __future__ import annotations
import re

PADROES = [
    re.compile(r"(?im)^\s*(\d{1,3})\s*[-–:.)]?\s*\(?([A-E])\)?\s*$"),
    re.compile(r"(?im)^\s*QUEST(?:ÃO|AO)\s*(\d{1,3})\s*[:.-]?\s*\(?([A-E])\)?\s*$"),
]

def parsear_gabarito(texto: str) -> dict[int, str]:
    respostas: dict[int, str] = {}
    conflitos: set[int] = set()
    for padrao in PADROES:
        for numero, letra in padrao.findall(texto or ""):
            n, l = int(numero), letra.upper()
            if n in conflitos:
                continue
            if n not in respostas:
                respostas[n] = l
            elif respostas[n] != l:
                respostas.pop(n, None)
                conflitos.add(n)
    return respostas

def cruzar_gabarito(questoes: list[dict], gabarito: dict[int, str]) -> list[dict]:
    for q in questoes:
        q["gabarito"] = gabarito.get(int(q["numero"]))
        if q["gabarito"] is None:
            q.setdefault("motivos_revisao", []).append("gabarito_ausente")
            q["status"] = "QUARENTENA"
    return questoes
