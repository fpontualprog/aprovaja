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
ALT_PATTERN = re.compile(r"(?im)^\s*(?:\(?[A-E]\)|[A-E][.)])\s+")

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
                alternatives = ALT_PATTERN.findall(body)
                question_text = body
                candidates.append({
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
                    "quantidade_marcadores_alternativas": len(alternatives),
                    "gabarito": None,
                    "disciplina": None,
                    "assunto": None,
                    "orgao": None,
                    "cargo": None,
                    "tipo_estimado": "certo_errado" if len(alternatives) == 0 else "objetiva",
                    "confianca_segmentacao": "baixa" if len(alternatives) == 0 else ("media" if len(alternatives) in (4, 5) else "baixa"),
                    "requer_revisao_humana": True,
                    "observacao": "Candidato heurístico por página; confirmar limites, alternativas, imagens, disciplina e gabarito no PDF original."
                })
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
              "enunciado_candidato", "quantidade_marcadores_alternativas", "gabarito",
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
