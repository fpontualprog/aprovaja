"""Regras de sanidade: questões incompletas ficam em quarentena."""
from __future__ import annotations
import re
from typing import Any

def validar_questao(q: dict[str, Any]) -> tuple[str, list[str]]:
    motivos: list[str] = []
    enunciado = str(q.get("enunciado") or "").strip()
    if len(enunciado) < 30:
        motivos.append("enunciado_muito_curto")
    tipo = q.get("tipo")
    alternativas = q.get("alternativas") or []
    if tipo == "multipla_escolha" and len(alternativas) != 5:
        motivos.append(f"num_alternativas_invalido_{len(alternativas)}")
    if tipo == "certo_errado" and alternativas:
        motivos.append("certo_errado_com_alternativas")
    letras = [str(a.get("letra", "")).upper() for a in alternativas]
    if letras and letras != ["A", "B", "C", "D", "E"]:
        motivos.append(f"letras_alternativas_invalidas_{letras}")
    for alternativa in alternativas:
        if len(str(alternativa.get("texto") or "").strip()) < 2:
            motivos.append(f"alternativa_{alternativa.get('letra', '?')}_vazia")
    bruto = str(q.get("texto_bruto") or "")
    if re.search(r"Bloco Temático|Página\s+\d+", bruto, re.I):
        motivos.append("texto_bruto_contem_ruido_de_pagina")
    if q.get("tem_imagem") is False and re.search(r"\b(gráfico|grafico|figura|imagem|observe a figura)\b", enunciado, re.I):
        motivos.append("menciona_grafico_sem_imagem")
    if tipo == "indeterminado":
        motivos.append("tipo_ou_alternativas_nao_identificados")
    if q.get("gabarito") in (None, ""):
        motivos.append("gabarito_ausente")
    return ("PRONTA_PARA_SUPABASE" if not motivos else "QUARENTENA", motivos)
