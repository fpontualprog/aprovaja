"""Associação conservadora de imagens às questões por intervalo de páginas.

A coluna Supabase public.questoes_globais.imagens é text[]: para o banco,
a função associar_imagens_paths retorna somente caminhos (strings). Os metadados
de página e bbox continuam disponíveis no objeto de revisão local.
"""
from __future__ import annotations
from typing import Any


def associar_imagens_paths(
    questao_canonica: dict[str, Any],
    paginas: list[dict[str, Any]],
    pagina_inicio: int,
    pagina_fim: int,
) -> list[str]:
    """Retorna paths de imagens dentro do intervalo da questão, sem dicionários."""
    paths: list[str] = []
    for pagina in paginas:
        try:
            numero_pagina = int(pagina.get("pagina", 0))
        except (TypeError, ValueError):
            continue
        if not pagina_inicio <= numero_pagina <= pagina_fim:
            continue
        for bloco in pagina.get("blocos", []):
            if bloco.get("tipo") != "imagem":
                continue
            arquivo = bloco.get("arquivo")
            if isinstance(arquivo, str) and arquivo.strip():
                paths.append(arquivo.strip())
    # Preserva a ordem e elimina duplicatas.
    return list(dict.fromkeys(paths))


def associar_imagens(
    questao: dict[str, Any],
    paginas: list[dict[str, Any]],
    pagina_inicio: int,
    pagina_fim: int,
) -> dict[str, Any]:
    """Anexa metadados de revisão e uma lista de paths pronta para text[] do banco."""
    imagens_meta: list[dict[str, Any]] = []
    for pagina in paginas:
        try:
            numero_pagina = int(pagina.get("pagina", 0))
        except (TypeError, ValueError):
            continue
        if not pagina_inicio <= numero_pagina <= pagina_fim:
            continue
        for bloco in pagina.get("blocos", []):
            if bloco.get("tipo") != "imagem":
                continue
            arquivo = bloco.get("arquivo")
            if isinstance(arquivo, str) and arquivo.strip():
                imagens_meta.append({
                    "arquivo": arquivo.strip(),
                    "sha256": bloco.get("sha256"),
                    "pagina": numero_pagina,
                    "bbox": bloco.get("bbox"),
                })
    questao["pagina_inicio"] = pagina_inicio
    questao["pagina_fim"] = pagina_fim
    questao["tem_imagem"] = bool(imagens_meta)
    questao["imagens_associadas"] = imagens_meta
    questao["imagens"] = list(dict.fromkeys(x["arquivo"] for x in imagens_meta))
    questao["requer_conferencia_visual"] = bool(imagens_meta)
    return questao
