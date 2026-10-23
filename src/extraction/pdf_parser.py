"""Extração e segmentação inicial de itens em PDFs de provas."""
from __future__ import annotations
import re
from pathlib import Path
import fitz

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

def segmentar_itens(texto: str) -> list[dict[str, str | int]]:
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
            for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                xref = image_info[0]
                try:
                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue
                    rect = rects[0]
                    if rect.y0 < question_y0 - 2 or rect.y0 >= next_y0:
                        continue
                    extracted = doc.extract_image(xref)
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    safe_num = re.sub(r"[^A-Za-z0-9_-]", "_", str(questao.get("numero", q_index + 1)))
                    output = pasta / f"q{safe_num}_img{image_index}.png"
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
