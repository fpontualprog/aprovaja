#!/usr/bin/env python3
"""Coletor PCI isolado v4. Somente arquivos locais; não acessa APROVAJÁ/Supabase."""
from __future__ import annotations
import csv, json, re, sys, unicodedata, tempfile
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

URL = "https://www.pciconcursos.com.br/concursos/"
SAIDA = Path(__file__).resolve().parent / "resultado_coleta_pci_v3"
REGIOES = ["PE", "PB", "AL", "RN", "SE", "CE", "BA"]
NOMES = {"PE":"PERNAMBUCO", "PB":"PARAIBA", "AL":"ALAGOAS", "RN":"RIO GRANDE DO NORTE", "SE":"SERGIPE", "CE":"CEARA", "BA":"BAHIA"}
CAMPOS = ["uf", "concurso", "vagas", "nivel", "salario", "inscricao_ate", "situacao_prazo", "campos_ausentes", "fonte_url", "coletado_em", "fonte"]

def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).strip().casefold()

def texto(node):
    return " ".join(node.stripped_strings) if node else ""

def data_iso(s):
    m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", s or "")
    if not m: return ""
    try: return datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
    except ValueError: return ""

def encontrar_cabecalho(soup, uf):
    alvo = norm(NOMES[uf])
    return next((n for n in soup.find_all("div", class_="uf") if norm(texto(n)) == alvo), None)

def cards_estado(soup, uf):
    cab = encontrar_cabecalho(soup, uf)
    if cab is None: raise ValueError(f"Cabeçalho do estado não encontrado: {uf} ({NOMES[uf]})")
    cards=[]
    for node in cab.find_all_next(True):
        if node.name == "div" and "uf" in (node.get("class") or []): break
        if "ca" in (node.get("class") or []): cards.append(node)
    if not cards: raise ValueError(f"Nenhum card encontrado na seção {uf}; estrutura do site pode ter mudado")
    return cards

def coletar(soup, uf, hoje):
    rows=[]
    for card in cards_estado(soup, uf):
        a=card.find("a", href=True)
        if not a: continue
        nome=texto(a); link=urljoin(URL, a["href"].strip())
        if not nome or (urlparse(link).hostname or "").lower() not in {"pciconcursos.com.br", "www.pciconcursos.com.br"}: continue
        detalhe=texto(card.find(class_="cd")); prazo=data_iso(texto(card.find(class_="ce")))
        vagas=" ".join(re.findall(r"\d[\d.]*\s*vaga(?:s)?", detalhe, re.I))
        niveis=re.findall(r"Superior|Médio|Fundamental|Alfabetizado|Técnico", detalhe, re.I)
        nivel="/".join(dict.fromkeys(x.capitalize() for x in niveis))
        salarios_extraidos=list(dict.fromkeys(re.findall(r"R\$\s*[\d.]+(?:,\d{2})?", detalhe, re.I)))
        salarios=" | ".join(salarios_extraidos) if salarios_extraidos else None
        if not prazo: status="sem_data_a_confirmar"
        elif date.fromisoformat(prazo) < hoje: status="prazo_vencido"
        else: status="prazo_futuro_ou_hoje_confirmar_inscricao"
        ausentes=[k for k,v in [("vagas",vagas),("nivel",nivel),("salario",salarios),("inscricao_ate",prazo)] if not v]
        rows.append({"uf":uf,"concurso":nome,"vagas":vagas,"nivel":nivel,"salario":salarios,"inscricao_ate":prazo,"situacao_prazo":status,"campos_ausentes":", ".join(ausentes),"fonte_url":link,"coletado_em":hoje.isoformat(),"fonte":"PCI Concursos"})
    if not rows: raise ValueError(f"Nenhum registro válido extraído para {uf}")
    return rows

def salvar_json(path, obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def publicar_arquivos(unicos, completa, saida):
    saida=Path(saida)
    if not completa:
        salvar_json(saida/"coleta_parcial_diagnostico.json",unicos)
        return False
    from io import StringIO
    buf=StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=CAMPOS,delimiter=";",extrasaction="ignore"); w.writeheader(); w.writerows(unicos)
    csvp=saida/"concursos_pci_nordeste.csv"; jsonp=saida/"concursos_pci_nordeste.json"
    ct=csvp.with_suffix(".csv.tmp"); jt=jsonp.with_suffix(".json.tmp")
    ct.write_text(buf.getvalue(),encoding="utf-8-sig"); jt.write_text(json.dumps(unicos,ensure_ascii=False,indent=2),encoding="utf-8")
    ct.replace(csvp); jt.replace(jsonp)
    return True

def teste_protecao():
    with tempfile.TemporaryDirectory(prefix="teste_coletor_pci_") as td:
        pasta=Path(td); csvp=pasta/"concursos_pci_nordeste.csv"; jsonp=pasta/"concursos_pci_nordeste.json"
        csvp.write_bytes(b"CSV ORIGINAL\n"); jsonp.write_bytes(b"JSON ORIGINAL\n")
        antes_csv,antes_json=csvp.read_bytes(),jsonp.read_bytes()
        exemplo=[{"uf":"PE","concurso":"Registro de teste","vagas":"1 vaga","nivel":"Médio","salario":None,"inscricao_ate":"","situacao_prazo":"sem_data_a_confirmar","campos_ausentes":"salario, inscricao_ate","fonte_url":"https://www.pciconcursos.com.br/teste","coletado_em":date.today().isoformat(),"fonte":"PCI Concursos"}]
        atualizou=publicar_arquivos(exemplo,False,pasta)
        preservou=csvp.read_bytes()==antes_csv and jsonp.read_bytes()==antes_json
        diagnostico=(pasta/"coleta_parcial_diagnostico.json").exists()
        if atualizou or not preservou or not diagnostico:
            print("FALHA no teste: proteção contra coleta parcial não passou."); return 1
        print("OK: coleta parcial preserva CSV e JSON principais.")
        print("OK: diagnóstico parcial é salvo separadamente.")
        print("OK: teste executado em pasta temporária; nenhum dado real foi alterado.")
        return 0

def main():
    if "--teste-protecao" in sys.argv: return teste_protecao()
    SAIDA.mkdir(parents=True,exist_ok=True); hoje=date.today()
    print(f"Coletor PCI isolado v4 — {URL}")
    print("Somente arquivos locais. Nenhuma conexão com APROVAJÁ/Supabase.")
    try:
        r=requests.get(URL,timeout=40,headers={"User-Agent":"Mozilla/5.0 (compatible; PCICollectorValidation/3.0)"}); r.raise_for_status()
        html=r.text
        if "Ã" in html and r.encoding and r.encoding.lower() not in ("utf-8","utf8"):
            try: html=r.content.decode("utf-8")
            except UnicodeDecodeError: pass
        soup=BeautifulSoup(html,"html.parser")
        if len(html)<1000: raise ValueError("Página retornou conteúdo inesperadamente curto")
    except Exception as e:
        salvar_json(SAIDA/"relatorio_teste.json",{"status":"falha_total","data_teste":hoje.isoformat(),"erro_fatal":str(e),"arquivos_principais_atualizados":False,"gravou_no_supabase":False,"alterou_aprovaja":False})
        print(f"Falha ao acessar/interpretar a fonte: {e}",file=sys.stderr); return 3
    resultados=[]; erros=[]
    for uf in REGIOES:
        try:
            rows=coletar(soup,uf,hoje); resultados.extend(rows); print(f"{uf}: {len(rows)} registros extraídos")
        except Exception as e: erros.append({"uf":uf,"erro":str(e)}); print(f"{uf}: FALHA — {e}")
    unicos=[]; vistos=set(); duplicatas=0
    for row in resultados:
        key=row["fonte_url"].rstrip("/").casefold()
        if key in vistos: duplicatas+=1; continue
        vistos.add(key); unicos.append(row)
    completa=bool(unicos) and not erros and all(any(x["uf"]==uf for x in unicos) for uf in REGIOES)
    por_uf={uf:sum(x["uf"]==uf for x in unicos) for uf in REGIOES}
    rel={"url_fonte":URL,"data_teste":hoje.isoformat(),"status":"coleta_completa" if completa else ("coleta_parcial" if unicos else "falha_total"),"total_extraido_antes_deduplicacao":len(resultados),"total_unico":len(unicos),"duplicatas_removidas":duplicatas,"por_uf":por_uf,"prazos":{"vencidos":sum(x["situacao_prazo"]=="prazo_vencido" for x in unicos),"futuros_ou_hoje_a_confirmar":sum(x["situacao_prazo"]=="prazo_futuro_ou_hoje_confirmar_inscricao" for x in unicos),"sem_data":sum(x["situacao_prazo"]=="sem_data_a_confirmar" for x in unicos)},"registros_com_campos_ausentes":sum(bool(x["campos_ausentes"]) for x in unicos),"erros":erros,"arquivos_principais_atualizados":False,"gravou_no_supabase":False,"alterou_aprovaja":False,"aviso":"Prazo futuro não confirma inscrição aberta; conferir edital e página de inscrição."}
    rel["arquivos_principais_atualizados"]=publicar_arquivos(unicos,completa,SAIDA)
    print("Coleta completa: arquivos principais atualizados." if completa else "Coleta incompleta: arquivos principais anteriores preservados.")
    salvar_json(SAIDA/"relatorio_teste.json",rel)
    print(f"Relatório: {SAIDA/'relatorio_teste.json'}")
    print(f"Total único: {len(unicos)} | Estados com erro: {len(erros)} | Duplicatas: {duplicatas} | Registros com campos ausentes: {rel['registros_com_campos_ausentes']}")
    return 0 if completa else (1 if unicos else 2)

if __name__=="__main__": sys.exit(main())
