#!/usr/bin/env python3
"""Extrai gabaritos explicitamente publicados e vincula apenas por número dentro do mesmo PDF."""
from __future__ import annotations
import base64, json, os, re, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "provas_data" / "json"
OUT_JSON = ROOT / "provas_data" / "revisao" / "questoes_candidatas.json"
API_URL = "https://api.openai.com/v1/chat/completions"
MODEL = os.environ.get("APROVAJA_IA_MODEL", "gpt-4.1-mini")
KEY_PAGE = re.compile(r"(?i)\b(gabarito|respostas? (?:das? )?quest(?:õ|o)es|padr(?:ã|a)o de resposta|resultado dos recursos|quest(?:õ|o)es anuladas)\b")

PROMPT = """Você extrai gabaritos oficiais impressos em provas de concursos.
Extraia somente respostas explicitamente exibidas na página. Não resolva questões, não deduza respostas.
Se a página não for claramente uma seção de gabarito/respostas, retorne lista vazia.
Responda JSON {"itens":[{"numero":"1","resposta":"A|B|C|D|E|CERTO|ERRADO|ANULADA","confianca":"alta|media|baixa"}]}.
Não confunda número de página, alternativa ou número de questão. Preserve CERTO/ERRADO quando estiver escrito assim.
Se houver duas versões ou respostas conflitantes na página, não escolha: marque confiança baixa."""

def read_image(path: Path | None) -> str | None:
    if not path:
        return None
    try:
        data = path.read_bytes()
        if len(data) > 3_500_000:
            return None
        return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    except OSError:
        return None

def extract(session, key, doc, page):
    text = str(page.get("texto") or "")
    if not KEY_PAGE.search(text):
        return []
    content = [{"type":"text","text":"Documento: " + json.dumps({k:doc.get(k) for k in ("fonte","url_origem","sha256","titulo","banca","concurso","ano")},ensure_ascii=False) + "\nPágina: " + str(page.get("pagina")) + "\nTexto da página:\n" + text}]
    rel = str(page.get("imagem_pagina") or "")
    image_path = ROOT / "provas_data" / rel if rel and (page.get("requer_ocr") or not text.strip()) else None
    image_url = read_image(image_path)
    if image_url:
        content.append({"type":"image_url","image_url":{"url":image_url,"detail":"high"}})
    response = session.post(API_URL, headers={"Authorization":"Bearer "+key}, json={
        "model":MODEL,"temperature":0,"response_format":{"type":"json_object"},
        "messages":[{"role":"system","content":PROMPT},{"role":"user","content":content}],
        "max_tokens":3000
    }, timeout=120)
    if response.status_code == 429 or response.status_code >= 500:
        time.sleep(2)
        response = session.post(API_URL, headers={"Authorization":"Bearer "+key}, json={
            "model":MODEL,"temperature":0,"response_format":{"type":"json_object"},
            "messages":[{"role":"system","content":PROMPT},{"role":"user","content":content}],
            "max_tokens":3000
        }, timeout=120)
    response.raise_for_status()
    data = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(data)
    items = parsed.get("itens", [])
    return items if isinstance(items, list) else []

def normalize_answer(value):
    v = str(value or "").strip().upper()
    v = re.sub(r"^\(?\s*|\s*\)?$", "", v)
    return {"C": "CERTO", "E": "ERRADO"}.get(v, v)

def main():
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not OUT_JSON.exists():
        print("Arquivo de candidatos não encontrado; etapa de gabarito ignorada.")
        return 0
    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    candidates = data.get("candidatos", [])
    if not api_key:
        print("OPENAI_API_KEY ausente; gabaritos não foram inferidos e candidatos seguem sem gabarito.")
        return 0
    docs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(JSON_DIR.glob("*.json"))}
    # Gabaritos são vinculados apenas ao PDF de origem, nunca por número isolado entre provas.
    candidates_by_doc = {}
    for candidate in candidates:
        sha = str(candidate.get("documento_sha256") or "")
        candidates_by_doc.setdefault(sha, []).append(candidate)
    session = requests.Session()
    extracted = 0
    errors = []
    for doc_sha, doc_candidates in candidates_by_doc.items():
        doc = docs.get(doc_sha)
        if not doc:
            errors.append({"documento_sha256":doc_sha,"erro":"JSON original não localizado; gabarito não vinculado"})
            continue
        document = doc.get("documento", {})
        answer_map = {}
        for page in doc.get("paginas", []):
            if not KEY_PAGE.search(str(page.get("texto") or "")):
                continue
            try:
                for item in extract(session, api_key, document, page):
                    number = str(item.get("numero") or "").strip()
                    answer = normalize_answer(item.get("resposta"))
                    confidence = str(item.get("confianca") or "baixa").lower()
                    if not number.isdigit() or answer not in {"A","B","C","D","E","CERTO","ERRADO","ANULADA"}:
                        continue
                    if number in answer_map and answer_map[number]["resposta"] != answer:
                        answer_map[number] = {"resposta":"","confianca":"baixa","conflito":True}
                    else:
                        answer_map[number] = {"resposta":answer,"confianca":confidence,"pagina_gabarito":page.get("pagina")}
                time.sleep(0.15)
            except Exception as exc:
                errors.append({"documento_sha256":doc_sha,"pagina":page.get("pagina"),"erro":str(exc)[:300]})
        for candidate in doc_candidates:
            number = str(candidate.get("numero_detectado") or "").strip()
            answer = answer_map.get(number)
            if not answer:
                candidate["gabarito"] = None
                candidate["gabarito_status"] = "NAO_LOCALIZADO"
                continue
            if answer.get("conflito") or answer.get("confianca") != "alta" or not answer.get("resposta"):
                candidate["gabarito"] = None
                candidate["gabarito_status"] = "CONFLITO_OU_BAIXA_CONFIANCA"
                candidate.setdefault("motivos_revisao", []).append("gabarito_oficial_exige_conferencia")
                candidate["requer_revisao_humana"] = True
                continue
            ans = answer["resposta"]
            qtype = candidate.get("tipo") or candidate.get("tipo_estimado")
            if qtype == "certo_errado":
                if ans not in {"CERTO","ERRADO","ANULADA"}:
                    candidate["gabarito"] = None
                    candidate["gabarito_status"] = "TIPO_INCOMPATIVEL"
                    candidate["requer_revisao_humana"] = True
                    continue
            elif ans in {"CERTO","ERRADO"}:
                candidate["gabarito"] = None
                candidate["gabarito_status"] = "TIPO_INCOMPATIVEL"
                candidate["requer_revisao_humana"] = True
                continue
            candidate["gabarito"] = {"CERTO":"C","ERRADO":"E"}.get(ans, ans)
            candidate["gabarito_status"] = "EXTRAIDO_DOCUMENTO_ORIGINAL"
            candidate["pagina_gabarito"] = answer.get("pagina_gabarito")
            candidate["gabarito_confianca"] = answer["confianca"]
            extracted += 1
    data["gabarito_extraction"] = {
        "metodo":"IA multimodal, apenas respostas explicitamente publicadas",
        "modelo":MODEL,"gabaritos_vinculados":extracted,
        "erros":errors,
        "politica":"Correspondência apenas dentro do mesmo PDF e por número; conflitos ficam sem gabarito."
    }
    tmp = OUT_JSON.with_suffix(".gabaritos.tmp.json")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(OUT_JSON)
    import csv
    fields = sorted({k for row in candidates for k in row})
    with (OUT_JSON.parent/"questoes_candidatas.csv").open("w",newline="",encoding="utf-8-sig") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        for row in candidates:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    print(json.dumps({"documentos_com_candidatos":len(candidates_by_doc),"gabaritos_vinculados":extracted,"erros":len(errors)},ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
