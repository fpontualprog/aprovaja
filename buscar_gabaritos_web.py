#!/usr/bin/env python3
"""Busca na web gabaritos oficiais ausentes e vincula respostas explicitamente publicadas."""
from __future__ import annotations
import json, os, re, sys, time
from pathlib import Path
from urllib.parse import quote, urlparse, unquote
import requests, fitz
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "provas_data" / "revisao" / "questoes_candidatas.json"
API = "https://api.deepseek.com/chat/completions"
MODEL = os.getenv("APROVAJA_IA_MODEL", "deepseek-flash")
OFFICIAL = {"fgv":["conhecimento.fgv.br"],"cebraspe":["cebraspe.org.br"],"fcc":["fcc.org.br"]}
KEYWORDS = re.compile(r"(?i)gabarito|respostas? das? quest|questões anuladas|questoes anuladas")

def norm(x): return re.sub(r"[^a-z0-9]+"," ",str(x or "").lower()).strip()

def source_slug(url):
    """Extrai identificador do PDF de prova; útil quando a coleta não trouxe metadados."""
    path = unquote(urlparse(str(url or "")).path)
    name = Path(path).stem.lower()
    name = re.sub(r"(?i)(gabarito|respostas?|prova|tipo|caderno|definitivo|preliminar)", " ", name)
    return norm(name)

def domains_for(meta):
    signal = norm(meta.get("banca")) + " " + norm(meta.get("fonte")) + " " + norm(meta.get("url_origem"))
    for key, domains in OFFICIAL.items():
        if key in signal: return domains
    host = (urlparse(str(meta.get("url_origem") or "")).hostname or "").lower()
    if host.endswith("conhecimento.fgv.br"): return OFFICIAL["fgv"]
    if host.endswith("cebraspe.org.br"): return OFFICIAL["cebraspe"]
    if host.endswith("fcc.org.br") or host.endswith("concursosfcc.com.br"): return OFFICIAL["fcc"]
    return []

def search(meta, session):
    domains = domains_for(meta)
    if not domains:
        return []
    slug = source_slug(meta.get("url_origem"))
    parts = [meta.get(k) for k in ("banca","titulo","concurso","cargo","orgao","ano")]
    if slug: parts.append(slug)
    query = " ".join(str(x) for x in parts if x) + " gabarito filetype:pdf"
    found=[]
    # Google e Bing são alternativas: falha de um buscador não encerra a busca.
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
                    if url not in [x["url"] for x in found]: found.append({"url":url,"titulo":label})
            if len(found)>=4: break
        except Exception as e: print("Busca web falhou:",str(e)[:160],file=sys.stderr)
    return found[:4]

def extract_pdf(pdf_bytes, meta, url, session, key):
    if not pdf_bytes.startswith(b"%PDF") or len(pdf_bytes)>25000000: return {}
    pdf=fitz.open(stream=pdf_bytes,filetype="pdf")
    pages=[]
    for i in range(len(pdf)):
        t=pdf[i].get_text("text") or ""
        if KEYWORDS.search(t): pages.append((i+1,t))
    result={}
    for page_num, text in pages:
        prompt = ("Extraia apenas respostas impressas explicitamente nesta página de gabarito oficial. "
                  "Não resolva questões. Retorne JSON {\"itens\":[{\"numero\":\"1\",\"resposta\":\"A|B|C|D|E|CERTO|ERRADO|ANULADA\",\"confianca\":\"alta|media|baixa\"}]}. "
                  "Asterisco ou indicação explícita de anulação deve virar ANULADA. Se não for página de gabarito, lista vazia. "
                  "Metadados da prova: "+json.dumps(meta,ensure_ascii=False)+"\nURL oficial: "+url+"\nPágina "+str(page_num)+":\n"+text[:14000])
        try:
            r=session.post(API,headers={"Authorization":"Bearer "+key},json={"model":MODEL,"temperature":0,"response_format":{"type":"json_object"},"messages":[{"role":"system","content":"Você extrai gabaritos oficiais sem inferir respostas."},{"role":"user","content":prompt}],"max_tokens":3000},timeout=90)
            r.raise_for_status()
            items=json.loads(r.json()["choices"][0]["message"]["content"]).get("itens",[])
            for item in items:
                n=str(item.get("numero") or "").strip()
                ans=str(item.get("resposta") or "").strip().upper()
                conf=str(item.get("confianca") or "baixa").lower()
                if n.isdigit() and ans in {"A","B","C","D","E","CERTO","ERRADO","ANULADA"}:
                    if n in result and result[n]["resposta"]!=ans: result[n]={"resposta":"","confianca":"baixa","conflito":True}
                    else: result[n]={"resposta":ans,"confianca":conf,"pagina":page_num}
            time.sleep(.15)
        except Exception as e: print("DeepSeek falhou:",str(e)[:160],file=sys.stderr)
    return result

def compatible(qmeta, ameta):
    q={k:norm(qmeta.get(k)) for k in ("banca","ano","concurso","titulo","cargo","orgao")}
    a={k:norm(ameta.get(k)) for k in ("banca","ano","concurso","titulo","cargo","orgao")}
    if q["ano"] and a["ano"] and q["ano"]!=a["ano"]: return False
    if q["banca"] and a["banca"] and q["banca"]!=a["banca"]: return False
    if any(q[k] and a[k] and (q[k] in a[k] or a[k] in q[k]) for k in ("concurso","titulo","cargo","orgao")):
        return True
    # Fallback quando a extração deixou os metadados vazios: comparar o identificador
    # do PDF de origem com o nome/slug do gabarito oficial, sem ignorar conflito de ano/banca.
    qs=set(source_slug(qmeta.get("url_origem")).split())
    ans=set(source_slug(ameta.get("url_origem")).split())
    distinctive={t for t in qs & ans if len(t)>=3 and t not in {"tipo","prova","gabarito","definitivo","preliminar","caderno","questoes","questoes","auditor","analista","fiscal","tributario","tributaria","receita","federal"}}
    return bool(distinctive)

def main():
    key=os.getenv("DEEPSEEK_API_PUBLICA","").strip()
    if not key: print("DEEPSEEK_API_PUBLICA ausente; fallback web ignorado."); return 0
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
        meta={"banca":q.get("banca"),"fonte":q.get("fonte"),"url_origem":q.get("url_fonte"),"titulo":q.get("concurso") or source_slug(q.get("url_fonte")),"concurso":q.get("concurso") or source_slug(q.get("url_fonte")),"cargo":q.get("cargo"),"orgao":q.get("orgao"),"ano":q.get("ano"),"source_slug":source_slug(q.get("url_fonte"))}
        # Fill missing metadata from nearby candidates from the same PDF.
        same=[x for x in candidates if str(x.get("documento_sha256") or "")==sha]
        for field in ("banca","concurso","cargo","orgao","ano"):
            if not meta.get(field):
                meta[field]=next((x.get(field) for x in same if x.get(field)),None)
        for hit in search(meta,session):
            try:
                r=session.get(hit["url"],headers={"User-Agent":"Mozilla/5.0"},timeout=35)
                r.raise_for_status()
                answers=extract_pdf(r.content,meta,hit["url"],session,key)
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
        qmeta={"banca":q.get("banca") or ("fgv" if "fgv" in norm(q.get("fonte")) else None),"ano":q.get("ano"),"concurso":q.get("concurso") or source_slug(q.get("url_fonte")),"titulo":q.get("concurso") or source_slug(q.get("url_fonte")),"cargo":q.get("cargo"),"orgao":q.get("orgao"),"url_origem":q.get("url_fonte")}
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
        q["gabarito_metodo"]="DeepSeek + busca web em domínio oficial"
        linked+=1
        if ans=="ANULADA": annulled+=1
    data["gabarito_web_fallback"]={"fontes_oficiais_encontradas":len(bundles),"questoes_vinculadas":linked,"anuladas":annulled,"politica":"Busca em mais de um buscador e domínio oficial; usa identificador do PDF quando faltam metadados; conflitos e confiança baixa continuam bloqueados.","gravacao_supabase":False}
    tmp=OUT.with_suffix(".web.tmp.json"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(OUT)
    import csv
    fields=sorted({k for row in candidates for k in row})
    with (OUT.parent/"questoes_candidatas.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader()
        for row in candidates: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    print(json.dumps(data["gabarito_web_fallback"],ensure_ascii=False))
    return 0

if __name__=="__main__": raise SystemExit(main())
