#!/usr/bin/env python3
"""Validação local dos arquivos do coletor PCI. Não acessa internet, APROVAJÁ ou Supabase."""
from __future__ import annotations
import csv, json, re
from collections import Counter
from datetime import date
from pathlib import Path
BASE=Path(__file__).resolve().parent/"resultado_coleta_pci_v3"
JSON_IN=BASE/"concursos_pci_nordeste.json"; CSV_IN=BASE/"concursos_pci_nordeste.csv"
REL_JSON=BASE/"relatorio_validacao_qualidade.json"; REL_CSV=BASE/"pendencias_validacao.csv"
UFS_ESPERADAS={"PE","PB","AL","RN","SE","CE","BA"}
CAMPOS=["uf","concurso","vagas","nivel","salario","inscricao_ate","situacao_prazo","campos_ausentes","fonte_url","coletado_em","fonte"]
def _data(s):
    try: return date.fromisoformat(s)
    except (TypeError,ValueError): return None
def main():
    if not JSON_IN.exists(): raise SystemExit(f"Arquivo não encontrado: {JSON_IN}")
    registros=json.loads(JSON_IN.read_text(encoding="utf-8-sig"))
    if not isinstance(registros,list): raise SystemExit("O JSON principal não contém uma lista de registros.")
    hoje=date.today(); problemas=[]; contagem=Counter(r.get("uf") for r in registros)
    urls=Counter((r.get("fonte_url") or "").rstrip("/").casefold() for r in registros)
    duplicatas=[u for u,n in urls.items() if u and n>1]
    for i,r in enumerate(registros,start=1):
        ident=f"linha {i} | {r.get('uf','?')} | {r.get('concurso','(sem nome)')}"
        for campo in ("uf","concurso","fonte_url","fonte","coletado_em"):
            if not r.get(campo): problemas.append({"tipo":"campo_obrigatorio_vazio","registro":ident,"campo":campo,"detalhe":"Campo essencial vazio"})
        if r.get("uf") not in UFS_ESPERADAS: problemas.append({"tipo":"uf_inesperada","registro":ident,"campo":"uf","detalhe":str(r.get("uf"))})
        url=r.get("fonte_url") or ""
        if not re.match(r"^https://www?\.pciconcursos\.com\.br/",url,re.I): problemas.append({"tipo":"url_fora_do_dominio_esperado","registro":ident,"campo":"fonte_url","detalhe":url})
        prazo=r.get("inscricao_ate")
        if prazo and not _data(prazo): problemas.append({"tipo":"data_invalida","registro":ident,"campo":"inscricao_ate","detalhe":str(prazo)})
        for campo in ("vagas","nivel","salario","inscricao_ate"):
            valor=r.get(campo)
            if valor is None or str(valor).strip()=="": problemas.append({"tipo":"dado_ausente","registro":ident,"campo":campo,"detalhe":"Não inferir nem preencher por estimativa"})
        if r.get("salario") is None and "salario" not in (r.get("campos_ausentes") or ""):
            problemas.append({"tipo":"marcacao_ausente_inconsistente","registro":ident,"campo":"campos_ausentes","detalhe":"salario é null, mas não está indicado em campos_ausentes"})
    for u in duplicatas: problemas.append({"tipo":"url_duplicada","registro":"","campo":"fonte_url","detalhe":f"{urls[u]} ocorrências: {u}"})
    faltantes=sorted(UFS_ESPERADAS-set(contagem))
    for uf in faltantes: problemas.append({"tipo":"estado_sem_registros","registro":"","campo":"uf","detalhe":uf})
    csv_info={"existe":CSV_IN.exists(),"linhas":None,"colunas_esperadas_ausentes":[]}; csv_ok=False
    if CSV_IN.exists():
        try:
            with CSV_IN.open("r",encoding="utf-8-sig",newline="") as f:
                reader=csv.DictReader(f,delimiter=";"); linhas=list(reader); csv_info["linhas"]=len(linhas)
                csv_info["colunas_esperadas_ausentes"]=[c for c in CAMPOS if c not in (reader.fieldnames or [])]
                csv_ok=len(linhas)==len(registros) and not csv_info["colunas_esperadas_ausentes"]
                if len(linhas)!=len(registros): problemas.append({"tipo":"json_csv_contagens_diferentes","registro":"","campo":"CSV/JSON","detalhe":f"JSON={len(registros)}, CSV={len(linhas)}"})
                if csv_info["colunas_esperadas_ausentes"]: problemas.append({"tipo":"colunas_csv_ausentes","registro":"","campo":"CSV","detalhe":", ".join(csv_info["colunas_esperadas_ausentes"])})
        except Exception as e: problemas.append({"tipo":"csv_ilegivel","registro":"","campo":"CSV","detalhe":str(e)})
    else: problemas.append({"tipo":"csv_inexistente","registro":"","campo":"CSV","detalhe":str(CSV_IN)})
    rel={"data_validacao":hoje.isoformat(),"escopo":"Validação local estrutural; não acessa internet, APROVAJÁ ou Supabase.","total_json":len(registros),"por_uf":dict(sorted(contagem.items())),"estados_esperados":sorted(UFS_ESPERADAS),"estados_sem_registros":faltantes,"duplicatas_de_url":len(duplicatas),"campos_ausentes_por_tipo":dict(Counter(p["campo"] for p in problemas if p["tipo"]=="dado_ausente")),"csv":csv_info,"csv_json_consistentes_em_contagem_e_colunas":csv_ok,"total_apontamentos":len(problemas),"apontamentos":problemas,"limitacao":"Validação estrutural: não verifica páginas ou conteúdo oficial do edital."}
    REL_JSON.write_text(json.dumps(rel,ensure_ascii=False,indent=2),encoding="utf-8")
    with REL_CSV.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["tipo","registro","campo","detalhe"],delimiter=";",extrasaction="ignore"); w.writeheader(); w.writerows(problemas)
    print("VALIDAÇÃO LOCAL CONCLUÍDA"); print(f"JSON: {len(registros)} registros")
    print("Por UF: "+", ".join(f"{k}: {v}" for k,v in sorted(contagem.items())))
    print(f"URLs duplicadas: {len(duplicatas)} | Apontamentos: {len(problemas)}")
    print(f"CSV existe: {csv_info['existe']} | linhas: {csv_info['linhas']} | consistente: {csv_ok}")
    print(f"Relatório: {REL_JSON}"); print(f"Pendências: {REL_CSV}")
    return 0
if __name__=="__main__": main()
