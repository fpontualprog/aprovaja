"""Associação conservadora de imagens às questões por intervalo de páginas."""
from __future__ import annotations
from typing import Any

def associar_imagens(questao: dict[str, Any], paginas: list[dict[str, Any]], pagina_inicio: int, pagina_fim: int) -> dict[str, Any]:
    imagens = []
    for pagina in paginas:
        numero_pagina = int(pagina.get("pagina", 0))
        if not pagina_inicio <= numero_pagina <= pagina_fim:
            continue
        for bloco in pagina.get("blocos", []):
            if bloco.get("tipo") != "imagem":
                continue
            imagens.append({"arquivo": bloco.get("arquivo"), "sha256": bloco.get("sha256"), "pagina": numero_pagina, "bbox": bloco.get("bbox")})
    questao["pagina_inicio"] = pagina_inicio
    questao["pagina_fim"] = pagina_fim
    questao["tem_imagem"] = bool(imagens)
    questao["imagens_associadas"] = imagens
    questao["requer_conferencia_visual"] = bool(imagens)
    return questao
