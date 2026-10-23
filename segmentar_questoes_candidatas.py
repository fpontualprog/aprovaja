#!/usr/bin/env python3
"""Cria lote de questões candidatas para revisão humana; nunca grava no Supabase."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_JSON_DIR = ROOT / "provas_data" / "json"
DEFAULT_OUT = ROOT / "provas_data" / "revisao"

# Heurísticas deliberadamente conservadoras: cada resultado permanece como candidato.
START_PATTERNS = [
    re.compile(r"(?im)^\s*(?:QUEST(?:Ã|A)O|QUESTÃO)\s*(?:N[º°.]?\s*)?(\d{1,4})\s*[:.)-]?\s*"),
    re.compile(r"(?m)^\s*(\d{1,3})\s*[.)]\s+(?=\S)"),
    re.compile(r"(?im)^\s*(?:ITEM\s+)?(\d{1,4})\s*[-–]\s+(?=\S)"),
]
ALT_PATTERN = re.compile(r"(?im)^\s*(?:\(([A-E])\)|([A-E])[.)])\s+")


def normalized(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def digest(s: str) -> str:
    return hashlib.sha256(normalized(s).casefold().encode("utf-8")).hexdigest()

def find_starts(text: str) -> list[tuple[int, int, str]]:
    found = []
    for pattern in START_PATTERNS:
        for match in pattern.finditer(text):
            found.append((match.start(), match.end(), match.group(1)))
    # Deduplica marcadores coincidentes e mantém a ordem original.
    found.sort(key=lambda x: (x[0], x[1]))
    unique = []
    last_start = -1
    for item in found:
        if item[0] != last_start:
            unique.append(item)
            last_start = item[0]
    return unique

def parse_alternatives(body: str) -> tuple[str, dict[str, str], bool]:
    """Separa alternativas apenas quando os marcadores são explícitos e estruturados."""
    matches = list(ALT_PATTERN.finditer(body))
    if len(matches) < 4 or len(matches) > 5:
        return body.strip(), {}, False
    letters = [(m.group(1) or m.group(2) or "").upper() for m in matches]
    if len(set(letters)) != len(letters) or letters != list("ABCDE"[:len(letters)]):
        return body.strip(), {}, False
    options: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        option_text = normalized(body[match.end():end])
        if len(option_text) < 2:
            return body.strip(), {}, False
        options[letters[i]] = option_text
    stem = body[:matches[0].start()].strip()
    if len(normalized(stem)) < 25:
        return body.strip(), {}, False
    return stem, options, True

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    candidates = []
    docs = sorted(args.json_dir.glob("*.json"))
    for path in docs:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            candidates.append({"status": "ERRO_JSON", "arquivo_json": path.name, "erro": str(exc)})
            continue
        doc = data.get("documento", {})
        # Gabaritos alimentam a etapa de vínculo, mas não são segmentados como questões.
        if doc.get("categoria_documento") == "gabarito":
            continue
        pages = data.get("paginas", [])
        # A segmentação por página evita unir questões de páginas distantes; questões que
        # continuam na página seguinte ficam sinalizadas para revisão, não são fundidas.
        for page in pages:
            text = page.get("texto", "") or ""
            starts = find_starts(text)
            for i, (start, content_start, number) in enumerate(starts):
                end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
                body = text[content_start:end].strip()
                if len(normalized(body)) < 35:
                    continue
                question_text, alternatives, alternatives_valid = parse_alternatives(body)
                page_requires_ocr = bool(page.get("requer_ocr", False))
                blocks = page.get("blocos", []) if isinstance(page.get("blocos", []), list) else []
                image_blocks = [
                    {
                        "arquivo": b.get("arquivo"),
                        "pagina": page.get("pagina"),
                        "ordem_bloco": b.get("ordem"),
                        "bbox": b.get("bbox"),
                        "largura": b.get("largura"),
                        "altura": b.get("altura"),
                        "sha256": b.get("sha256")
                    }
                    for b in blocks if isinstance(b, dict) and b.get("tipo") == "imagem"
                ]
                visual_keywords = re.compile(r"\\b(figura|gráfico|grafico|tabela|quadro|mapa|imagem|observe|conforme a figura|conforme o gráfico|conforme o grafico|analise a tabela)\\b", re.I)
                visual_hint = bool(visual_keywords.search(question_text) or image_blocks or page_requires_ocr)
                segmentation_high = alternatives_valid and len(normalized(question_text)) >= 35 and not page_requires_ocr and not visual_hint
                candidate_payload = {
                    "id_candidato": digest(doc.get("sha256", path.stem) + "|" + str(page.get("pagina")) + "|" + number + "|" + body),
                    "status": "PENDENTE_REVISAO",
                    "fonte": doc.get("fonte"),
                    "url_fonte": doc.get("url_origem"),
                    "documento_sha256": doc.get("sha256", path.stem),
                    "arquivo_pdf": doc.get("pdf_armazenado"),
                    "arquivo_json": path.name,
                    "pagina_inicio": page.get("pagina"),
                    "pagina_fim": page.get("pagina"),
                    "numero_detectado": number,
                    "enunciado_candidato": question_text,
                    "alternativas": alternatives,
                    "quantidade_marcadores_alternativas": len(alternatives),
                    "gabarito": None,
                    "disciplina": None,
                    "assunto": None,
                    "orgao": None,
                    "cargo": None,
                    "tipo_estimado": "objetiva" if alternatives_valid else "certo_errado" if len(ALT_PATTERN.findall(body)) == 0 else "objetiva",
                    "confianca_segmentacao": "alta" if segmentation_high else "baixa",
                    "requer_revisao_humana": not segmentation_high,
                    "pagina_requer_ocr": page_requires_ocr,
                    "imagem_pagina_revisao": page.get("imagem_pagina"),
                    "imagens_associadas": image_blocks,
                    "elementos_visuais": {
                        "pagina_origem": page.get("pagina"),
                        "imagem_pagina_completa": page.get("imagem_pagina"),
                        "blocos_imagem_extraidos": image_blocks,
                        "requer_conferencia_visual": visual_hint,
                        "requer_ocr": page_requires_ocr,
                        "associacao_precisa_por_regiao": False
                    },
                    "status_validacao_visual": "PENDENTE_CONFERENCIA" if visual_hint else "SEM_SINAL_VISUAL_DETECTADO",
                    "motivos_revisao": ["conferir_vinculo_visual_com_pagina_original"] if visual_hint else [],
                    "observacao": "Alternativas estruturadas automaticamente quando os marcadores A-E são explícitos. Gabarito, disciplina e vínculo exato de figuras ainda precisam ser confirmados."
                }
                candidates.append(candidate_payload)
    json_path = args.out / "questoes_candidatas.json"
    json_path.write_text(json.dumps({
        "schema_version": "aprovaja.questoes_candidatas.v1",
        "modo": "somente_pre_validacao",
        "gravacao_supabase": False,
        "total_documentos_json": len(docs),
        "total_candidatos": len(candidates),
        "candidatos": candidates
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = args.out / "questoes_candidatas.csv"
    fields = ["id_candidato", "status", "fonte", "url_fonte", "documento_sha256", "arquivo_pdf",
              "arquivo_json", "pagina_inicio", "pagina_fim", "numero_detectado",
              "enunciado_candidato", "alternativas", "quantidade_marcadores_alternativas", "gabarito",
              "disciplina", "assunto", "orgao", "cargo", "tipo_estimado",
              "confianca_segmentacao", "requer_revisao_humana", "observacao"]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(candidates)
    print(json.dumps({"documentos_json": len(docs), "candidatos": len(candidates),
                      "json_revisao": str(json_path), "csv_revisao": str(csv_path),
                      "supabase_modificado": False}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
