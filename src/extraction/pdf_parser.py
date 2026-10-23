"""Extração e segmentação inicial de itens em PDFs de provas."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
import fitz
from src.config import CORTE_X

ITEM_RE = re.compile(r"(?m)^\s*(\d{1,3})[.)]?\s+")

def extrair_texto_pdf(caminho: str | Path) -> str:
    texto = []
    with fitz.open(str(caminho)) as doc:
        for pagina in doc:
            texto.append(pagina.get_text("text", sort=True))
    resultado = "\n".join(texto).strip()
    if not resultado:
        raise ValueError(f"Nenhum texto extraível encontrado em {caminho}; o PDF pode ser digitalizado como imagem.")
    return resultado

def segmentar_itens(texto: str) -> list[dict[str, Any]]:
    """Segmentação heurística para provas C/E; revisar casos com numeração ambígua."""
    matches = list(ITEM_RE.finditer(texto))
    itens = []
    for i, match in enumerate(matches):
        inicio = match.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        conteudo = texto[inicio:fim].strip()
        numero = int(match.group(1))
        if len(conteudo) >= 20:
            itens.append({
                "numero": numero,
                "texto": conteudo,
                "posicao_inicio": inicio,
                "posicao_fim": fim,
                "tem_imagem": False,
                "imagens": [],
            })
    if not itens:
        raise ValueError("Não foi possível identificar itens numerados no texto extraído do PDF.")
    return itens


QUESTION_START_RE = re.compile(r"(?m)^\\s*(\\d{1,3})[.)]?\\s+")


def _encontrar_questoes(caminho_pdf: str | Path) -> list[dict[str, Any]]:
    """Localiza questões a partir dos blocos do PDF, respeitando colunas.

    Cada coluna é percorrida de cima para baixo. Se um bloco contiver várias
    questões, os marcadores numéricos no início das linhas dividem o bloco.
    A posição global é recuperada no texto da página para manter compatibilidade
    com a extração heurística de imagens.
    """
    itens: list[dict[str, Any]] = []
    with fitz.open(str(caminho_pdf)) as documento:
        offset_pagina = 0
        for pagina in documento:
            texto_pagina = pagina.get_text("text", sort=True)
            blocos = [
                bloco for bloco in pagina.get_text("blocks")
                if len(bloco) >= 5 and isinstance(bloco[4], str) and bloco[4].strip()
            ]

            # Ordena por coluna e, dentro dela, de cima para baixo. O CORTE_X
            # já usado no projeto separa a coluna esquerda da direita.
            esquerda = sorted(
                (b for b in blocos if float(b[0]) < CORTE_X),
                key=lambda b: (float(b[1]), float(b[0])),
            )
            direita = sorted(
                (b for b in blocos if float(b[0]) >= CORTE_X),
                key=lambda b: (float(b[1]), float(b[0])),
            )
            blocos_ordenados = esquerda + direita

            for bloco in blocos_ordenados:
                texto_bloco = str(bloco[4]).strip()
                marcadores = list(QUESTION_START_RE.finditer(texto_bloco))
                if not marcadores:
                    continue

                # Só divide nos marcadores de início de linha do bloco; números
                # no meio de frases, datas e textos de apoio não iniciam questões.
                for i, marcador in enumerate(marcadores):
                    inicio_bloco = marcador.start()
                    fim_bloco = marcadores[i + 1].start() if i + 1 < len(marcadores) else len(texto_bloco)
                    conteudo = texto_bloco[inicio_bloco:fim_bloco].strip()
                    if len(conteudo) < 20:
                        continue
                    numero = int(marcador.group(1))
                    posicao = texto_pagina.find(conteudo[:60])
                    if posicao < 0:
                        posicao = texto_pagina.find(marcador.group(0).strip())
                    itens.append({
                        "numero": numero,
                        "texto": conteudo,
                        "posicao_inicio": offset_pagina + posicao if posicao >= 0 else offset_pagina,
                        "posicao_fim": (
                            offset_pagina + posicao + len(conteudo)
                            if posicao >= 0 else offset_pagina + len(texto_pagina)
                        ),
                        "tem_imagem": False,
                        "imagens": [],
                    })
            offset_pagina += len(texto_pagina) + 1

    if not itens:
        raise ValueError(
            f"Não foi possível identificar questões em blocos do PDF {caminho_pdf}."
        )

    # Evita duplicações ocasionais quando o mesmo bloco aparece em mais de uma
    # região do PDF, mantendo a ordem física de leitura.
    unicas: list[dict[str, Any]] = []
    vistos: set[tuple[int, str]] = set()
    for item in itens:
        chave = (item["numero"], item["texto"])
        if chave not in vistos:
            vistos.add(chave)
            unicas.append(item)
    return unicas


def extrair_itens_pdf(caminho_pdf: str | Path) -> list[dict[str, Any]]:
    """Extrai questões usando blocos e separação de colunas do PDF."""
    return _encontrar_questoes(caminho_pdf)

def extrair_imagens_questoes(
    caminho_pdf: str | Path,
    questoes: list[dict],
    pasta_saida: str | Path = "data/imagens",
) -> list[dict]:
    """Extrai imagens próximas a cada questão e anexa seus caminhos aos registros.

    A associação é heurística: usa o início textual da questão e o retângulo
    das imagens na mesma página. PDFs com diagramação complexa devem ser revisados.
    """
    if not questoes:
        return questoes

    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)

    with fitz.open(str(caminho_pdf)) as doc:
        # Mapeia offsets globais do texto extraído para página e coordenada vertical.
        page_data = []
        offset = 0
        for page_index, page in enumerate(doc):
            page_text = page.get_text("text", sort=True)
            blocks = page.get_text("blocks", sort=True)
            page_data.append({
                "page_index": page_index,
                "start": offset,
                "end": offset + len(page_text),
                "text": page_text,
                "blocks": blocks,
                "page": page,
            })
            offset += len(page_text) + 1

        for q_index, questao in enumerate(questoes):
            questao.setdefault("tem_imagem", False)
            questao.setdefault("imagens", [])
            pos = questao.get("posicao_inicio")
            if not isinstance(pos, int):
                # Sem posição global confiável, não atribui imagens por suposição.
                continue

            page_info = next(
                (p for p in page_data if p["start"] <= pos <= p["end"]),
                None,
            )
            if page_info is None:
                continue

            local_pos = max(0, min(pos - page_info["start"], len(page_info["text"])))
            prefix = page_info["text"][:local_pos]
            local_line_start = prefix.rfind("\n") + 1
            search_text = page_info["text"][local_line_start:local_pos + 120].strip()
            question_y0 = None
            for block in page_info["blocks"]:
                if len(block) < 5 or not isinstance(block[4], str):
                    continue
                block_text = block[4]
                if search_text and (search_text[:35] in block_text or block_text.strip()[:35] in search_text):
                    question_y0 = float(block[1])
                    break

            if question_y0 is None:
                # Fallback: usa a coordenada da linha mais próxima do offset textual.
                text_blocks = [b for b in page_info["blocks"] if len(b) >= 5 and isinstance(b[4], str) and b[4].strip()]
                if text_blocks:
                    question_y0 = float(text_blocks[0][1])

            if question_y0 is None:
                continue

            next_y0 = float("inf")
            for next_q in questoes[q_index + 1:]:
                next_pos = next_q.get("posicao_inicio")
                if not isinstance(next_pos, int):
                    continue
                next_page = next((p for p in page_data if p["start"] <= next_pos <= p["end"]), None)
                if next_page and next_page["page_index"] == page_info["page_index"]:
                    next_local = max(0, min(next_pos - next_page["start"], len(next_page["text"])))
                    next_prefix = next_page["text"][:next_local]
                    next_line_start = next_prefix.rfind("\n") + 1
                    next_search = next_page["text"][next_line_start:next_local + 120].strip()
                    for block in next_page["blocks"]:
                        if len(block) >= 5 and isinstance(block[4], str) and next_search and (
                            next_search[:35] in block[4] or block[4].strip()[:35] in next_search
                        ):
                            next_y0 = float(block[1])
                            break
                    break

            page = page_info["page"]
            seen = set(questao["imagens"])
            question_image_index = 0
            for image_info in page.get_images(full=True):
                xref = image_info[0]
                try:
                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue
                    matching_rect = next(
                        (rect for rect in rects if rect.y0 >= question_y0 - 2 and rect.y0 < next_y0),
                        None,
                    )
                    if matching_rect is None:
                        continue
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    safe_num = re.sub(r"[^A-Za-z0-9_-]", "_", str(questao.get("numero", q_index + 1)))
                    question_image_index += 1
                    output = pasta / f"q{safe_num}_img{question_image_index}.png"
                    pix.save(str(output))
                    pix = None
                    path = str(output)
                    if path not in seen:
                        questao["imagens"].append(path)
                        seen.add(path)
                except (RuntimeError, ValueError, OSError):
                    continue

            questao["tem_imagem"] = bool(questao["imagens"])

    return questoes
