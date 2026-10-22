#!/usr/bin/env python3
"""Usa IA multimodal para estruturar questões candidatas; nunca grava diretamente no banco."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "provas_data" / "json"
OUT = ROOT / "provas_data" / "revisao"
API_URL = "https://api.openai.com/v1/chat/completions"
MODEL = os.environ.get("APROVAJA_IA_MODEL", "gpt-4.1-mini")
MAX_IMAGE_BYTES = 3_500_000

SYSTEM_PROMPT = """Você é um extrator rigoroso de questões de concursos públicos brasileiros.
Extraia apenas questões realmente visíveis no material fornecido. Não invente texto, alternativas,
disciplina, assunto, nem gabarito. Nunca deduza resposta correta a partir do enunciado.
Se o trecho estiver incompleto, misturar questões, ou houver dúvida, marque confianca='baixa'.
Preserve fórmulas, códigos, tabelas e referências visíveis. Associe imagens apenas se forem
claramente parte da questão; descreva a dependência de imagem em requer_imagem.
Responda exclusivamente JSON com a chave 'questoes', uma lista de objetos com:
numero (string ou null), enunciado (string), tipo ('objetiva'|'certo_errado'|'discursiva'),
alternativas (objeto com chaves A-E, ou {}), disciplina (string ou null), assunto (string ou null),
texto_apoio (string ou null), requer_imagem (boolean), confianca ('alta'|'media'|'baixa'),
motivos_revisao (lista de strings). Enunciado deve conter somente o texto da questão, não alternativas.
Não crie questão a partir de instruções administrativas, cabeçalhos ou gabaritos isolados."""

def digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def read_image(path: Path) -> str | None:
    try:
        payload = path.read_bytes()
        if len(payload) > MAX_IMAGE_BYTES:
            return None
        return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")
    except OSError:
        return None

def extract_page(session: requests.Session, api_key: str, doc: dict, page: dict, image_path: Path | None) -> list[dict]:
    content: list[dict] = [{
        "type": "text",
        "text": (
            "Metadados da prova (não inferir o que não estiver disponível): "
            + json.dumps({k: doc.get(k) for k in ("fonte", "url_origem", "sha256", "titulo", "banca", "concurso", "ano")},
                         ensure_ascii=False)
            + "\nPágina " + str(page.get("pagina")) + " de um PDF. Extraia as questões visíveis. "
            + "Texto extraído:\n" + str(page.get("texto") or "[SEM CAMADA DE TEXTO]")
        )
    }]
    image_url = read_image(image_path) if image_path else None
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url, "detail": "high"}})
    payload = {
        "model": MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ],
        "max_tokens": 5000
    }
    response = session.post(API_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=120)
    if response.status_code == 429 or response.status_code >= 500:
        time.sleep(2)
        response = session.post(API_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=120)
    response.raise_for_status()
    result = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(result)
    questions = parsed.get("questoes", [])
    return questions if isinstance(questions, list) else []

def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY ausente: mantendo o lote heurístico para revisão, sem falhar a coleta.")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    docs = sorted(JSON_DIR.glob("*.json"))
    if not docs:
        print("Nenhum JSON de prova encontrado; nada a enriquecer.")
        return 0

    session = requests.Session()
    all_candidates: list[dict] = []
    errors: list[dict] = []
    for path in docs:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            doc = data.get("documento", {})
            for page in data.get("paginas", []):
                text = str(page.get("texto") or "")
                blocks = page.get("blocos", [])
                has_images = any(b.get("tipo") == "imagem" for b in blocks)
                needs_visual = bool(page.get("requer_ocr")) or has_images
                image_path = ROOT / str(page.get("imagem_pagina")) if needs_visual and page.get("imagem_pagina") else None
                questions = extract_page(session, api_key, doc, page, image_path)
                for idx, q in enumerate(questions, start=1):
                    if not isinstance(q, dict):
                        continue
                    stem = str(q.get("enunciado") or "").strip()
                    if len(re.sub(r"\s+", " ", stem)) < 25:
                        continue
                    alternatives = q.get("alternativas") if isinstance(q.get("alternativas"), dict) else {}
                    qtype = q.get("tipo") if q.get("tipo") in ("objetiva", "certo_errado", "discursiva") else "objetiva"
                    confidence = q.get("confianca") if q.get("confianca") in ("alta", "media", "baixa") else "baixa"
                    reasons = q.get("motivos_revisao") if isinstance(q.get("motivos_revisao"), list) else []
                    if qtype == "objetiva" and list(alternatives.keys()) not in (list("ABCDE"), list("ABCD"), list("ABC"), []):
                        confidence = "baixa"
                        reasons.append("alternativas_ambiguas_ou_desordenadas")
                    if not alternatives and qtype == "objetiva":
                        confidence = "baixa"
                        reasons.append("alternativas_ausentes")
                    if q.get("requer_imagem") is True:
                        reasons.append("conferir_vinculo_de_imagem")
                    candidate = {
                        "id_candidato": digest(str(doc.get("sha256", path.stem)) + "|" + str(page.get("pagina")) + "|" + str(q.get("numero")) + "|" + stem),
                        "status": "PENDENTE_REVISAO",
                        "fonte": doc.get("fonte"),
                        "url_fonte": doc.get("url_origem"),
                        "documento_sha256": doc.get("sha256"),
                        "arquivo_pdf": doc.get("pdf_armazenado"),
                        "arquivo_json": path.name,
                        "pagina_inicio": page.get("pagina"),
                        "pagina_fim": page.get("pagina"),
                        "numero_detectado": str(q.get("numero") or idx),
                        "enunciado_candidato": stem,
                        "alternativas": alternatives,
                        "quantidade_marcadores_alternativas": len(alternatives),
                        "gabarito": None,
                        "disciplina": q.get("disciplina"),
                        "assunto": q.get("assunto"),
                        "texto_apoio": q.get("texto_apoio"),
                        "tipo_estimado": qtype,
                        "confianca_segmentacao": confidence,
                        "confianca_ia": confidence,
                        "requer_revisao_humana": confidence != "alta" or qtype == "discursiva",
                        "pagina_requer_ocr": bool(page.get("requer_ocr")),
                        "imagem_pagina_revisao": page.get("imagem_pagina"),
                        "motivos_revisao": list(dict.fromkeys(str(x) for x in reasons)),
                        "metodo_extracao": "openai_multimodal",
                        "modelo_ia": MODEL,
                        "observacao": "Gabarito não inferido; validar com documento oficial antes de importar."
                    }
                    all_candidates.append(candidate)
                time.sleep(0.15)
        except Exception as exc:
            errors.append({"arquivo_json": path.name, "erro": str(exc)[:500]})
            print(f"Falha IA em {path.name}: {exc}", file=sys.stderr)

    # Se a IA produziu candidatos, substitui o lote heurístico pelo lote estruturado;
    # se falhou completamente, mantém o lote anterior intacto.
    if all_candidates:
        result = {
            "schema_version": "aprovaja.questoes_candidatas.ia.v1",
            "modo": "extracao_ia_com_validacao",
            "gravacao_supabase": False,
            "modelo": MODEL,
            "total_documentos_json": len(docs),
            "total_candidatos": len(all_candidates),
            "erros_documentos": errors,
            "candidatos": all_candidates
        }
        json_path = OUT / "questoes_candidatas.json"
        temp_path = OUT / "questoes_candidatas.ia.tmp.json"
        temp_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(json_path)
        import csv
        fields = sorted({key for row in all_candidates for key in row})
        csv_path = OUT / "questoes_candidatas.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in all_candidates:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
        print(json.dumps({"modelo": MODEL, "documentos": len(docs), "candidatos_ia": len(all_candidates), "erros": len(errors)}, ensure_ascii=False))
    else:
        print(json.dumps({"modelo": MODEL, "candidatos_ia": 0, "erros": len(errors), "acao": "lote heurístico preservado"}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
