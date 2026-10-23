#!/usr/bin/env python3
"""Extrai gabaritos explicitamente publicados e vincula apenas por número dentro do mesmo PDF."""
from __future__ import annotations
import base64, json, os, re, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "provas_data" / "json"
OUT_JSON = ROOT / "provas_data" / "revisao" / "questoes_candidatas.json"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = os.environ.get("APROVAJA_IA_MODEL", "deepseek-flash")
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
    # Páginas sem texto também podem conter gabarito digitalizado; o modelo só extrai respostas explícitas.
    content = [{"type":"text","text":"Documento: " + json.dumps({k:doc.get(k) for k in ("fonte","url_origem","sha256","titulo","banca","concurso","ano")},ensure_ascii=False) + "\nPágina: " + str(page.get("pagina")) + "\nTexto da página:\n" + text}]
    rel = str(page.get("imagem_pagina") or "")
    image_path = ROOT / "provas_data" / rel if rel and (page.get("requer_ocr") or not text.strip()) else None
    image_url = read_image(image_path)
    if image_url:
        content.append({"type":"image_url","image_url":{"url":image_url,"detail":"high"}})
    response = session.post(API_URL, headers={"Authorization":"Bearer "+key}, json={
        "model":MODEL,"temperature":0,"thinking":{"type":"disabled"},"response_format":{"type":"json_object"},
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
    api_key = os.environ.get("DEEPSEEK_API_PUBLICA", "").strip()
    if not OUT_JSON.exists():
        print("Arquivo de candidatos não encontrado; etapa de gabarito ignorada.")
        return 0
    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    candidates = data.get("candidatos", [])
    if not api_key:
        print("DEEPSEEK_API_PUBLICA ausente; gabaritos não foram inferidos e candidatos seguem sem gabarito.")
        return 0
    docs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(JSON_DIR.glob("*.json"))}
    # Primeiro extrai mapas de gabarito de TODOS os PDFs baixados; depois faz vínculo cruzado
    # somente quando metadados de banca/concurso/cargo/ano forem compatíveis.
    docs_by_sha = {str((v.get("documento") or {}).get("sha256") or k): v for k, v in docs.items()}
    answer_maps = {}
    errors = []
    session = requests.Session()

    def norm(value):
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    def doc_meta(doc):
        d = doc.get("documento", {})
        return {key: norm(d.get(key)) for key in ("banca", "concurso", "titulo", "cargo", "ano", "orgao")}

    def compatible(candidate_doc, answer_doc):
        q = doc_meta(candidate_doc)
        a = doc_meta(answer_doc)
        # Ano, se conhecido nos dois, deve coincidir.
        if q["ano"] and a["ano"] and q["ano"] != a["ano"]:
            return False
        # Se banca estiver informada em ambos, não pode divergir.
        if q["banca"] and a["banca"] and q["banca"] != a["banca"]:
            return False
        # Concurso/título/cargo/órgão devem ter ao menos um sinal forte em comum
        # quando existirem; evita cruzar questões de provas diferentes pelo número.
        fields = ("concurso", "titulo", "cargo", "orgao")
        matches = [key for key in fields if q[key] and a[key] and (q[key] in a[key] or a[key] in q[key])]
        return bool(matches)

    for doc_key, doc in docs.items():
        document = doc.get("documento", {})
        doc_sha = str(document.get("sha256") or doc_key)
        answer_map = {}
        for page in doc.get("paginas", []):
            page_text = str(page.get("texto") or "")
            # Inclui páginas sem camada de texto sinalizadas para OCR, sem enviar todas as páginas à IA.
            if not KEY_PAGE.search(page_text) and not page.get("requer_ocr") and page_text.strip():
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
        if answer_map:
            answer_maps[doc_sha] = {"map": answer_map, "doc": doc}

    extracted = 0
    linked_same_doc = 0
    linked_separate_doc = 0
    no_key_found = 0
    for candidate in candidates:
        source_sha = str(candidate.get("documento_sha256") or "")
        source_doc = docs_by_sha.get(source_sha)
        if not source_doc:
            candidate["gabarito"] = None
            candidate["gabarito_status"] = "DOCUMENTO_ORIGINAL_NAO_LOCALIZADO"
            continue
        number = str(candidate.get("numero_detectado") or "").strip()
        matches = []
        # Prioridade 1: gabarito encontrado dentro do mesmo PDF da questão.
        if source_sha in answer_maps and number in answer_maps[source_sha]["map"]:
            matches.append((source_sha, answer_maps[source_sha]["map"][number], True))
        # Prioridade 2: PDF separado, somente com metadados de prova compatíveis.
        for key, bundle in answer_maps.items():
            if key == source_sha or not compatible(source_doc, bundle["doc"]):
                continue
            if number in bundle["map"]:
                matches.append((key, bundle["map"][number], False))
        # Vários gabaritos com respostas divergentes = revisão, nunca escolher automaticamente.
        answers = {m[1].get("resposta") for m in matches if m[1].get("resposta") and not m[1].get("conflito")}
        if not matches:
            candidate["gabarito"] = None
            candidate["gabarito_status"] = "GABARITO_OFICIAL_NAO_ENCONTRADO_NOS_PDFS_BAIXADOS"
            no_key_found += 1
            continue
        if len(answers) != 1 or any(m[1].get("conflito") or m[1].get("confianca") != "alta" for m in matches):
            candidate["gabarito"] = None
            candidate["gabarito_status"] = "CONFLITO_OU_BAIXA_CONFIANCA"
            candidate.setdefault("motivos_revisao", []).append("gabarito_oficial_exige_conferencia")
            candidate["requer_revisao_humana"] = True
            continue
        chosen = next(m for m in matches if m[1].get("resposta") in answers)
        ans = chosen[1]["resposta"]
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
        candidate["gabarito_status"] = "EXTRAIDO_DOCUMENTO_ORIGINAL" if chosen[2] else "EXTRAIDO_GABARITO_SEPARADO_COMPATIVEL"
        candidate["pagina_gabarito"] = chosen[1].get("pagina_gabarito")
        candidate["gabarito_documento_sha256"] = chosen[0]
        candidate["gabarito_confianca"] = chosen[1]["confianca"]
        extracted += 1
        if chosen[2]:
            linked_same_doc += 1
        else:
            linked_separate_doc += 1
    data["gabarito_extraction"] = {
        "metodo":"DeepSeek, apenas respostas explicitamente publicadas",
        "modelo":MODEL,"gabaritos_vinculados":extracted,"vinculados_mesmo_pdf":linked_same_doc,"vinculados_pdf_separado":linked_separate_doc,"sem_gabarito_nos_pdfs_baixados":no_key_found,
        "erros":errors,
        "politica":"Busca em todos os PDFs baixados; vínculo cruzado exige compatibilidade de metadados e número; conflitos ficam sem gabarito."
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
    print(json.dumps({"documentos_com_candidatos":len(set(str(x.get("documento_sha256") or "") for x in candidates)),"gabaritos_vinculados":extracted,"vinculados_mesmo_pdf":linked_same_doc,"vinculados_pdf_separado":linked_separate_doc,"sem_gabarito_nos_pdfs_baixados":no_key_found,"erros":len(errors)},ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
