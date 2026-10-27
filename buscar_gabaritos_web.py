#!/usr/bin/env python3
"""Busca na web gabaritos oficiais ausentes e vincula respostas explicitamente publicadas."""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
from urllib.parse import quote, urlparse, unquote
import requests, fitz
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "provas_data" / "revisao" / "questoes_candidatas.json"
OFFICIAL = {"fgv":["conhecimento.fgv.br"],"cebraspe":["cebraspe.org.br"],"fcc":["fcc.org.br","concursosfcc.com.br"]}
KEYWORDS = re.compile(r"(?i)gabarito|respostas? das? quest|questões anuladas|questoes anuladas")

def norm(x): return re.sub(r"[^a-z0-9]+"," ",str(x or "").lower()).strip()

def source_slug(url):
    """Extrai identificador do PDF de prova; útil quando a coleta não trouxe metadados."""
    path = unquote(urlparse(str(url or "")).path)
    name = Path(path).stem.lower()
    name = re.sub(r"(?i)(gabarito|respostas?|prova|tipo|caderno|definitivo|preliminar)", " ", name)
    return norm(name)

def detect_exam_type(url, explicit=None):
    value = " ".join([str(explicit or ""), str(url or "")]).lower()
    for pattern in (r"tipo[\s_-]*0?([1-9])", r"caderno[\s_-]*(?:tipo[\s_-]*)?0?([1-9])", r"\bvers[aã]o\s*0?([1-9])\b"):
        match = re.search(pattern, value)
        if match: return "tipo " + match.group(1)
    return ""
def domains_for(meta):
    signal = norm(meta.get("banca")) + " " + norm(meta.get("fonte")) + " " + norm(meta.get("url_origem"))
    for key, domains in OFFICIAL.items():
        if key in signal: return domains
    host = (urlparse(str(meta.get("url_origem") or "")).hostname or "").lower()
    if host.endswith("conhecimento.fgv.br"): return OFFICIAL["fgv"]
    if host.endswith("cebraspe.org.br"): return OFFICIAL["cebraspe"]
    if host.endswith("fcc.org.br") or host.endswith("concursosfcc.com.br"): return OFFICIAL["fcc"]
    return []

def deepseek_search_queries(meta, key):
    """Pede à DeepSeek consultas específicas; a API não navega sozinha, então as consultas são executadas nos buscadores."""
    base = " ".join(str(meta.get(k) or "") for k in ("banca","concurso","titulo","orgao","cargo","ano","tipo_prova")).strip()
    fallback = [
        f'"{base}" gabarito definitivo site oficial filetype:pdf',
        f'"{base}" gabarito preliminar site oficial',
        f'"{base}" respostas questões banca oficial',
    ]
    if not key:
        return fallback
    prompt = (
        "Crie até 4 consultas de busca na web para localizar gabaritos oficiais de concurso público. "
        "Use apenas os metadados fornecidos, priorize gabarito definitivo, preliminar e retificações. "
        "Não invente URLs nem respostas. Retorne somente JSON: {\\"queries\\":[\\"consulta 1\\"]}. "
        f"Metadados: {json.dumps(meta, ensure_ascii=False)}"
    )
    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": os.getenv("APROVAJA_IA_MODEL", "deepseek-flash"),
                  "messages":[{"role":"system","content":"Você prepara consultas de pesquisa precisas; não afirme que pesquisou nem invente fontes."},
                              {"role":"user","content":prompt}],
                  "temperature":0.1},
            timeout=35,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            queries = json.loads(match.group(0)).get("queries", [])
            clean = [" ".join(str(q).split()) for q in queries if str(q).strip()]
            if clean:
                print(json.dumps({"deepseek_consultas_gabarito":len(clean)}, ensure_ascii=False))
                return clean[:4] + fallback[:1]
    except Exception as e:
        print("DeepSeek não gerou consultas de gabarito; usando consultas padrão:", str(e)[:160], file=sys.stderr)
    return fallback


def deepseek_rank_results(meta, hits, key):
    """A DeepSeek ordena apenas resultados reais já retornados pelos buscadores; URLs não são aceitas da resposta do modelo."""
    if not key or len(hits) < 2:
        return hits
    result_list = [{"index": i, "titulo": h.get("titulo"), "url": h.get("url")} for i, h in enumerate(hits)]
    prompt = (
        "Ordene os resultados para encontrar o gabarito oficial exato desta prova. "
        "Priorize domínio oficial, mesma banca, concurso, cargo, ano e tipo/caderno. "
        "Não invente URLs e não declare resposta de questão. Retorne JSON {\\"order\\":[0,1]} "
        "com índices dos resultados recebidos, do mais ao menos relevante. "
        f"Metadados: {json.dumps(meta, ensure_ascii=False)}\\nResultados: "
        f"{json.dumps(result_list, ensure_ascii=False)}"
    )
    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": os.getenv("APROVAJA_IA_MODEL", "deepseek-flash"),
                  "messages":[{"role":"system","content":"Você avalia relevância de resultados reais. Nunca crie links."},
                              {"role":"user","content":prompt}],
                  "temperature":0},
            timeout=35,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            order = json.loads(match.group(0)).get("order", [])
            indexes = []
            for value in order:
                if isinstance(value, int) and 0 <= value < len(hits) and value not in indexes:
                    indexes.append(value)
            if indexes:
                ranked = [hits[i] for i in indexes]
                ranked.extend(h for i,h in enumerate(hits) if i not in indexes)
                print(json.dumps({"deepseek_resultados_oficiais_ordenados":len(ranked)}, ensure_ascii=False))
                return ranked
    except Exception as e:
        print("DeepSeek não ordenou resultados; mantendo ordem do buscador:", str(e)[:160], file=sys.stderr)
    return hits


def search(meta, session):
    domains = domains_for(meta)
    if not domains:
        return []
    key = os.getenv("DEEPSEEK_API_PUBLICA", "").strip()
    queries = deepseek_search_queries(meta, key)
    found=[]
    # Os buscadores executam as consultas; somente domínios oficiais conhecidos são aceitos.
    for query in queries:
        for engine in ("https://www.google.com/search?q=", "https://www.bing.com/search?q="):
            try:
                r=session.get(engine+quote(query),headers={"User-Agent":"Mozilla/5.0"},timeout=20)
                if not r.ok: continue
                soup=BeautifulSoup(r.text,"html.parser")
                for a in soup.select("a[href]"):
                    url=a.get("href","")
                    if url.startswith("/url?q="): url=url.split("/url?q=",1)[1].split("&",1)[0]
                    host=(urlparse(url).hostname or "").lower()
                    if not url.startswith("http") or not any(host==d or host.endswith("."+d) for d in domains): continue
                    label=" ".join(a.get_text(" ",strip=True).split())
                    if ".pdf" in url.lower() or "gabarito" in (label+" "+url).lower():
                        if url not in [x["url"] for x in found]:
                            found.append({"url":url,"titulo":label})
                if len(found)>=12: break
            except Exception as e:
                print("Busca web falhou:",str(e)[:160],file=sys.stderr)
        if len(found)>=12: break
    ranked = deepseek_rank_results(meta, found, key)
    return ranked[:8]

def extract_pdf(pdf_bytes, meta, url, session, key=None):
    """Extrai gabaritos por regras locais; não chama API de IA."""
    if not pdf_bytes.startswith(b"%PDF") or len(pdf_bytes)>25000000: return {}
    pdf=fitz.open(stream=pdf_bytes,filetype="pdf")
    result={}
    # Formatos comuns em gabaritos: "1 A", "01 - B", "Questão 1: C".
    line_patterns = [
        re.compile(r"(?i)^\s*(?:quest[aã]o\s*)?(\d{1,3})\s*[\).:\-–]\s*(ANULADA|CANCELADA|[ABCDE])\s*[.*º°]?\s*$"),
        re.compile(r"(?i)^\s*(?:quest[aã]o\s*)?(\d{1,3})\s+(ANULADA|CANCELADA|[ABCDE])\s*[.*º°]?\s*$"),
    ]
    for page_num in range(len(pdf)):
        text=pdf[page_num].get_text("text") or ""
        if not KEYWORDS.search(text) and not re.search(r"(?i)gabarito|respostas", url):
            continue
        page_answers={}
        for line in text.splitlines():
            line=" ".join(line.strip().split())
            for pattern in line_patterns:
                m=pattern.match(line)
                if not m: continue
                n, ans=m.group(1),m.group(2).upper()
                ans="ANULADA" if ans in {"ANULADA","CANCELADA"} else ans
                if n in page_answers and page_answers[n]["resposta"]!=ans:
                    page_answers[n]={"resposta":"","confianca":"baixa","conflito":True}
                else:
                    page_answers[n]={"resposta":ans,"confianca":"alta","pagina":page_num+1}
                break
        if len(page_answers)>len(result):
            result=page_answers
    return result

def compatible(qmeta, ameta):
    q={k:norm(qmeta.get(k)) for k in ("banca","ano","concurso","titulo","cargo","orgao")}
    a={k:norm(ameta.get(k)) for k in ("banca","ano","concurso","titulo","cargo","orgao")}
    if q["ano"] and a["ano"] and q["ano"]!=a["ano"]: return False
    if q["banca"] and a["banca"] and q["banca"]!=a["banca"]: return False
    qt=norm(qmeta.get("tipo_prova")); at=norm(ameta.get("tipo_prova"))
    if qt and at and qt != at: return False
    if any(q[k] and a[k] and (q[k] in a[k] or a[k] in q[k]) for k in ("concurso","titulo","cargo","orgao")):
        return True
    # Fallback quando a extração deixou os metadados vazios: comparar o identificador
    # do PDF de origem com o nome/slug do gabarito oficial, sem ignorar conflito de ano/banca.
    qs=set(source_slug(qmeta.get("url_origem")).split())
    ans=set(source_slug(ameta.get("url_origem")).split())
    distinctive={t for t in qs & ans if len(t)>=3 and t not in {"tipo","prova","gabarito","definitivo","preliminar","caderno","questoes","questoes","auditor","analista","fiscal","tributario","tributaria","receita","federal"}}
    return bool(distinctive)

def main():
    if not OUT.exists(): print("JSON de questões não encontrado."); return 0
    data=json.loads(OUT.read_text(encoding="utf-8"))
    candidates=data.get("candidatos",[])
    session=requests.Session()
    bundles={}
    seen=set()
    for q in candidates:
        sha=str(q.get("documento_sha256") or "")
        if not sha or sha in seen or q.get("gabarito"): continue
        seen.add(sha)
        meta={"banca":q.get("banca"),"fonte":q.get("fonte"),"url_origem":q.get("url_fonte"),"titulo":q.get("concurso") or source_slug(q.get("url_fonte")),"concurso":q.get("concurso") or source_slug(q.get("url_fonte")),"cargo":q.get("cargo"),"orgao":q.get("orgao"),"ano":q.get("ano"),"tipo_prova":detect_exam_type(q.get("url_fonte"),q.get("tipo_prova")),"source_slug":source_slug(q.get("url_fonte"))}
        # Fill missing metadata from nearby candidates from the same PDF.
        same=[x for x in candidates if str(x.get("documento_sha256") or "")==sha]
        for field in ("banca","concurso","cargo","orgao","ano"):
            if not meta.get(field):
                meta[field]=next((x.get(field) for x in same if x.get(field)),None)
        for hit in search(meta,session):
            try:
                r=session.get(hit["url"],headers={"User-Agent":"Mozilla/5.0"},timeout=35)
                r.raise_for_status()
                answers=extract_pdf(r.content,meta,hit["url"],session)
                if answers:
                    answer_meta=dict(meta)
                    answer_meta["url_origem"]=hit["url"]
                    answer_meta["source_slug"]=source_slug(hit["url"])
                    bundles[hit["url"]]={"meta":answer_meta,"answers":answers}
                    print(json.dumps({"gabarito_oficial_encontrado":hit["url"],"respostas":len(answers)},ensure_ascii=False))
                    break
            except Exception as e: print("PDF oficial falhou:",str(e)[:180],file=sys.stderr)
    linked=annulled=0
    for q in candidates:
        if q.get("gabarito"): continue
        num=str(q.get("numero_detectado") or "").strip()
        qmeta={"banca":q.get("banca") or ("fgv" if "fgv" in norm(q.get("fonte")) else None),"ano":q.get("ano"),"concurso":q.get("concurso") or source_slug(q.get("url_fonte")),"titulo":q.get("concurso") or source_slug(q.get("url_fonte")),"cargo":q.get("cargo"),"orgao":q.get("orgao"),"url_origem":q.get("url_fonte"),"tipo_prova":detect_exam_type(q.get("url_fonte"),q.get("tipo_prova"))}
        same=[x for x in candidates if str(x.get("documento_sha256") or "")==str(q.get("documento_sha256") or "")]
        for field in ("banca","concurso","cargo","orgao","ano"):
            if not qmeta.get(field): qmeta[field]=next((x.get(field) for x in same if x.get(field)),None)
        matches=[]
        for url,bundle in bundles.items():
            if compatible(qmeta,bundle["meta"]) and num in bundle["answers"]:
                matches.append((url,bundle["answers"][num]))
        answers={m[1]["resposta"] for m in matches if m[1].get("resposta") and not m[1].get("conflito")}
        if len(answers)!=1 or any(m[1].get("confianca")!="alta" or m[1].get("conflito") for m in matches):
            continue
        url,entry=next(m for m in matches if m[1]["resposta"] in answers)
        ans=entry["resposta"]
        q["gabarito"]= {"CERTO":"C","ERRADO":"E"}.get(ans,ans)
        q["gabarito_status"]="ANULADA" if ans=="ANULADA" else "EXTRAIDO_GABARITO_WEB_OFICIAL"
        q["gabarito_fonte_oficial"]=url
        q["pagina_gabarito"]=entry.get("pagina")
        q["gabarito_confianca"]="alta"
        q["gabarito_metodo"]="busca oficial por banca/concurso/cargo/tipo + extração local; associação pelo número da questão"
        linked+=1
        if ans=="ANULADA": annulled+=1
    data["gabarito_web_fallback"]={"fontes_oficiais_encontradas":len(bundles),"questoes_vinculadas":linked,"anuladas":annulled,"politica":"Busca oficial por banca/concurso/cargo/tipo de prova; extrai respostas localmente sem API; vincula pelo número da questão; bloqueia conflitos e baixa confiança.","gravacao_supabase":False}
    tmp=OUT.with_suffix(".web.tmp.json"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(OUT)
    import csv
    fields=sorted({k for row in candidates for k in row})
    with (OUT.parent/"questoes_candidatas.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader()
        for row in candidates: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    print(json.dumps(data["gabarito_web_fallback"],ensure_ascii=False))
    return 0

if __name__=="__main__": raise SystemExit(main())
